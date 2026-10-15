#!/usr/bin/env python3
"""Export one chunk of an existing ScanBIM preview selection.

Run with Python 3.8 inside the OpenScene Singularity image on an AAU Slurm
compute node. Invokes the verified single-scene exporter; no GPU or inference.
Supports resuming successful exports after preemptions or failed jobs.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REQUIRED = ("original", "methodA", "methodB", "hybrid")


def already_exported(manifest_path, site, sid, max_points):
    if not manifest_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene = next((s for s in manifest.get("scenes", []) if s.get("id") == sid), None)
    if not scene:
        return False
    modes = scene.get("modes", {})
    try:
        original_count = int(modes["original"]["pointCount"])
        if original_count <= 0 or original_count > max_points:
            return False
        if original_count != int(modes["methodA"]["pointCount"]):
            return False
        if original_count != int(modes["hybrid"]["pointCount"]):
            return False
        if not 0 <= int(modes["methodB"]["pointCount"]) <= original_count:
            return False
        for mode in REQUIRED:
            spec = modes[mode]
            rel = Path(spec["url"])
            if rel.is_absolute() or ".." in rel.parts:
                return False
            file = site / rel
            if not file.is_file() or file.stat().st_size != int(spec["pointCount"]) * 16:
                return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--list", type=Path, required=True, help="Frozen scene ID list")
    p.add_argument("--start", type=int, required=True, help="Zero-based first scene index")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--project-root", type=Path, default=Path.home() / "scanbim")
    p.add_argument("--site-dir", type=Path, required=True, help="Existing Git checkout's scanbim directory")
    p.add_argument("--max-points", type=int, default=50000)
    p.add_argument("--force", action="store_true", help="Regenerate even when existing assets validate")
    args = p.parse_args()

    if args.start < 0 or args.count <= 0 or args.max_points <= 0:
        p.error("start >= 0, count > 0, and max-points > 0 are required")
    if not args.list.is_file():
        p.error("Selection list not found: {}".format(args.list))
    ids = [line.strip() for line in args.list.read_text(encoding="utf-8").splitlines()
           if line.strip() and not line.lstrip().startswith("#")]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", sid) for sid in ids):
        p.error("Scene list contains duplicate or invalid scene IDs")
    if args.start >= len(ids) or args.start + args.count > len(ids):
        p.error("Requested indices {}..{} exceed list of {} items".format(
            args.start, args.start + args.count - 1, len(ids)))
    site = args.site_dir.expanduser().resolve()
    manifest = site / "scenes.json"
    if not site.is_dir() or not manifest.is_file():
        p.error("Expected an existing website directory with scenes.json: {}".format(site))
    exporter = Path(__file__).with_name("export_scanbim_web_scene.py")
    if not exporter.is_file():
        p.error("Missing existing single-scene exporter: {}".format(exporter))

    selected = ids[args.start:args.start + args.count]
    for position, sid in enumerate(selected, start=args.start + 1):
        print("\n===== [{}/{}] {} =====".format(position, len(ids), sid), flush=True)
        if not args.force and already_exported(manifest, site, sid, args.max_points):
            print("Already exported and size-verified; skipping.", flush=True)
            continue
        cmd = [
            sys.executable, "-u", str(exporter),
            "--scene-id", sid,
            "--project-root", str(args.project_root.expanduser()),
            "--out-dir", str(site),
            "--max-points", str(args.max_points),
        ]
        subprocess.run(cmd, check=True)
        if not already_exported(manifest, site, sid, args.max_points):
            raise RuntimeError("Export missing or binary sizes are inconsistent: {}".format(sid))
    print("\nBatch complete: IDs {} to {} of {}.".format(
        args.start + 1, args.start + args.count, len(ids)), flush=True)


if __name__ == "__main__":
    main()
