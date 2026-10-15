#!/usr/bin/env python3
"""Safely remove the first temporary large-scene preview batch.

Designed specifically to preserve the original published ScanBIM scenes.
Dry-run by default. Before applying, checks that the final manifest scene
IDs exactly match the specified first IDs of the frozen old selection and
that every soon-to-be-removed folder contains only the expected 4 .bin files.

Run from a clean Git checkout. Git stores the old files for recovery.
"""
import argparse
import json
import os
import re
from pathlib import Path


MODE_FILENAMES = {
    "original": "original.bin",
    "methodA": "method_a.bin",
    "methodB": "method_b.bin",
    "hybrid": "hybrid.bin",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site-dir", type=Path, required=True,
                    help="Existing website scanbim directory")
    ap.add_argument("--old-list", type=Path, required=True,
                    help="Frozen list used to export the old 20 large previews")
    ap.add_argument("--remove-count", type=int, default=20)
    ap.add_argument("--preserve-count", type=int, default=25)
    ap.add_argument("--apply", action="store_true",
                    help="Actually remove validated preview files and manifest entries")
    args = ap.parse_args()
    if args.remove_count <= 0 or args.preserve_count <= 0:
        ap.error("Both counts must be positive")
    site = args.site_dir.expanduser().resolve()
    manifest_path = site / "scenes.json"
    if not manifest_path.is_file() or not args.old_list.is_file():
        ap.error("Missing website manifest or frozen old selection list")
    old_ids = [s.strip() for s in args.old_list.read_text(encoding="utf-8").splitlines()
               if s.strip() and not s.lstrip().startswith("#")]
    if len(old_ids) < args.remove_count or len(set(old_ids)) != len(old_ids):
        ap.error("Old selection list is too short or contains duplicates")
    doomed = old_ids[:args.remove_count]
    content = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenes = content["scenes"]
    ids = [s["id"] for s in scenes]
    if len(set(ids)) != len(ids):
        ap.error("The manifest contains duplicate scene IDs")
    if len(scenes) != args.preserve_count + args.remove_count:
        ap.error("Expected exactly {} existing scenes; found {}. Refusing to delete."
                 .format(args.preserve_count + args.remove_count, len(scenes)))
    if ids[-args.remove_count:] != doomed:
        ap.error("The last {} manifest entries do not exactly match the frozen first {} selected IDs."
                 .format(args.remove_count, args.remove_count))
    folders = []
    for scene in scenes[-args.remove_count:]:
        sid = scene["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
            ap.error("Unexpected scene ID: {}".format(sid))
        folder = site / "data" / sid
        if folder.is_symlink() or not folder.is_dir():
            ap.error("Missing or symlink scene folder: {}".format(folder))
        observed = {item.name for item in folder.iterdir()}
        expected = set(MODE_FILENAMES.values())
        if observed != expected:
            ap.error("Unexpected files for {}: found {}, expected {}".format(
                sid, sorted(observed), sorted(expected)))
        for mode, filename in MODE_FILENAMES.items():
            spec = scene["modes"][mode]
            expected_url = "data/{}/{}".format(sid, filename)
            if spec["url"] != expected_url:
                ap.error("Unexpected manifest URL: {} {}".format(sid, spec["url"]))
            candidate = folder / filename
            if candidate.is_symlink() or not candidate.is_file():
                ap.error("Unexpected file: {}".format(candidate))
            if candidate.stat().st_size != int(spec["pointCount"]) * 16:
                ap.error("Binary size mismatch: {}".format(candidate))
        folders.append(folder)

    print("Preserving original scenes:", args.preserve_count)
    print("Removing temporary large previews:", args.remove_count)
    print("Current manifest entries:", len(scenes))
    print("After removal:", args.preserve_count)
    for sid in doomed:
        print("  REMOVE", sid)
    if not args.apply:
        print("\nDRY RUN ONLY; nothing changed. Re-run with --apply to delete exactly these previews.")
        return

    content["scenes"] = scenes[:-args.remove_count]
    temp = manifest_path.with_name("scenes.json.tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(content, f, indent=2)
        f.write("\n")
    os.replace(str(temp), str(manifest_path))
    for folder in folders:
        for filename in MODE_FILENAMES.values():
            (folder / filename).unlink()
        folder.rmdir()
    print("\nCompleted. Stage the manifest and deleted binaries in Git when ready.")


if __name__ == "__main__":
    main()
