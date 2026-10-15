#!/usr/bin/env python3
"""Select random large ScanBIM scenes with complete 20k A/B predictions.

Uses PLY file size as a proxy for point-cloud complexity, not a measurement
of room floor area. The default keeps the largest 25% of eligible PLYs,
then randomly chooses 200 different room IDs (one view per room).

Standard library only. Run on the AAU login node; this reads file metadata,
not point-cloud contents.
"""
import argparse
import csv
import json
import math
import random
import re
from pathlib import Path

ROOM_RE = re.compile(r"^(scene_[0-9]+_[0-9]+)_[0-9]+$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project-root", type=Path, default=Path.home() / "scanbim")
    p.add_argument("--manifest", type=Path, required=True,
                   help="Current website scanbim/scenes.json; existing scenes are excluded")
    p.add_argument("--out", type=Path, required=True,
                   help="Write selected scene IDs here (outside public Git repository)")
    p.add_argument("--report", type=Path, required=True,
                   help="Write scene sizes and selection details as a CSV")
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--top-percent", type=float, default=25.0,
                   help="Candidate pool: largest N percent of eligible PLYs (default: 25)")
    p.add_argument("--seed", type=int, default=20261015)
    p.add_argument("--allow-multiple-views", action="store_true",
                   help="Allow different panorama observations of the same room")
    args = p.parse_args()

    if args.count <= 0 or not (0 < args.top_percent <= 100):
        p.error("--count must be positive and --top-percent in (0, 100]")
    if args.out.resolve() == args.report.resolve():
        p.error("--out and --report must be different paths")
    if args.out.exists() or args.report.exists():
        p.error("An output file already exists. Choose fresh paths; do not overwrite a frozen selection.")
    if not args.manifest.is_file():
        p.error("Could not find the current website manifest: {}".format(args.manifest))

    root = args.project_root.expanduser()
    pcd = root / "data/spatiallm_dataset_20000/pcd"
    folder_a = root / "outputs/spatiallm_20000_deterministic/method_A/material_npz"
    folder_b = root / "outputs/spatiallm_20000_deterministic/method_B/objectaware_material_npz"
    for path in (pcd, folder_a, folder_b):
        if not path.is_dir():
            p.error("Required source folder is missing: {}".format(path))

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    existing = {str(row["id"]) for row in manifest["scenes"]}
    eligible = []
    original_count = 0
    no_predictions = 0
    excluded = 0

    for ply in pcd.glob("*.ply"):
        original_count += 1
        sid = ply.stem
        if not ID_RE.fullmatch(sid):
            continue
        if sid in existing:
            excluded += 1
            continue
        file_a = folder_a / (sid + "_material.npz")
        file_b = folder_b / (sid + "_objectaware_material.npz")
        if not file_a.is_file() or not file_b.is_file() or file_a.stat().st_size == 0 or file_b.stat().st_size == 0:
            no_predictions += 1
            continue
        size = ply.stat().st_size
        if size > 0:
            eligible.append((sid, size))

    eligible.sort(key=lambda r: (-r[1], r[0]))
    if len(eligible) < args.count:
        p.error("Only {} eligible scenes, need {}.".format(len(eligible), args.count))
    pool_n = max(1, math.ceil(len(eligible) * args.top_percent / 100))
    pool = eligible[:pool_n]
    if not args.allow_multiple_views:
        distinct = {}
        for item in pool:
            match = ROOM_RE.fullmatch(item[0])
            room_key = match.group(1) if match else item[0]
            # Sorted largest first: keep the largest PLY view for each room.
            if room_key not in distinct:
                distinct[room_key] = item
        pool = list(distinct.values())
    if len(pool) < args.count:
        p.error("Only {} eligible distinct rooms in the largest {:.1f}%; try a larger --top-percent."
                .format(len(pool), args.top_percent))

    selected = random.Random(args.seed).sample(pool, args.count)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(sid + "\n" for sid, _ in selected), encoding="utf-8")
    with args.report.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("scene_id", "original_ply_bytes", "original_ply_MiB"))
        for sid, size in selected:
            writer.writerow((sid, size, "{:.2f}".format(size / 1048576)))

    print("Original PLY files: {:,}".format(original_count))
    print("Existing published IDs excluded: {:,}".format(excluded))
    print("Missing/empty A or B predictions: {:,}".format(no_predictions))
    print("Complete, unpublished scene IDs: {:,}".format(len(eligible)))
    print("Largest {:.1f}% threshold: {:.2f} MiB".format(
        args.top_percent, eligible[pool_n - 1][1] / 1048576))
    print("Selection pool after room deduplication: {:,}".format(len(pool)))
    print("Randomly selected: {:,} distinct IDs; seed {}".format(len(selected), args.seed))
    print("Selected PLY file sizes: {:.2f} to {:.2f} MiB".format(
        min(size for _, size in selected) / 1048576,
        max(size for _, size in selected) / 1048576))
    print("List:", args.out)
    print("CSV report:", args.report)
    print("First ten selected IDs:")
    for sid, size in selected[:10]:
        print("  {:22s} {:8.2f} MiB".format(sid, size / 1048576))


if __name__ == "__main__":
    main()
