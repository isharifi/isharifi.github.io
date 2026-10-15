#!/usr/bin/env python3
"""Uniform random selection of ScanBIM 20k observation PLYs.

All nonempty original PLY files with nonempty saved Method A/B NPZ files
are eligible, independent of their file sizes or scene types.

This selects uniformly across eligible scene IDs (observations). Multiple
observations of the same underlying room can be drawn; this is intentional.
Runs on the AAU login node and only reads filesystem metadata.
"""
import argparse
import csv
import json
import random
import re
from pathlib import Path


VALID_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def read_ids(path):
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", type=Path, default=Path.home() / "scanbim")
    ap.add_argument("--manifest", type=Path, required=True,
                    help="Existing ScanBIM website scenes.json; exclude already published IDs")
    ap.add_argument("--exclude-list", type=Path,
                    help="Optional text list of additional IDs to exclude, e.g. earlier 200 selections")
    ap.add_argument("--out", type=Path, required=True, help="Write frozen selected IDs here")
    ap.add_argument("--report", type=Path, required=True, help="Write selected file size report here")
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261016)
    args = ap.parse_args()

    if args.count < 1:
        ap.error("--count must be positive")
    if args.out.resolve() == args.report.resolve():
        ap.error("--out and --report must be different files")
    for path in (args.out, args.report):
        if path.exists():
            ap.error("Refusing to overwrite existing output: {}".format(path))
    if not args.manifest.is_file():
        ap.error("Manifest not found: {}".format(args.manifest))
    if args.exclude_list and not args.exclude_list.is_file():
        ap.error("Exclude list not found: {}".format(args.exclude_list))
    root = args.project_root.expanduser()
    pcd = root / "data/spatiallm_dataset_20000/pcd"
    method_a = root / "outputs/spatiallm_20000_deterministic/method_A/material_npz"
    method_b = root / "outputs/spatiallm_20000_deterministic/method_B/objectaware_material_npz"
    for directory in (pcd, method_a, method_b):
        if not directory.is_dir():
            ap.error("Missing required directory: {}".format(directory))

    published = {row["id"] for row in json.loads(
        args.manifest.read_text(encoding="utf-8")).get("scenes", [])}
    other_exclusions = set(read_ids(args.exclude_list)) if args.exclude_list else set()
    excluded = published | other_exclusions
    eligible = []
    num_ply = 0
    missing_predictions = 0
    excluded_count = 0
    invalid = 0
    for ply in pcd.glob("*.ply"):
        num_ply += 1
        sid = ply.stem
        if not VALID_ID.fullmatch(sid) or ply.stat().st_size == 0:
            invalid += 1
            continue
        if sid in excluded:
            excluded_count += 1
            continue
        a = method_a / (sid + "_material.npz")
        b = method_b / (sid + "_objectaware_material.npz")
        if not a.is_file() or not b.is_file() or a.stat().st_size == 0 or b.stat().st_size == 0:
            missing_predictions += 1
            continue
        eligible.append((sid, ply.stat().st_size))

    # Stable ordering makes the sample reproducible independent of directory order.
    eligible.sort(key=lambda row: row[0])
    if len(eligible) < args.count:
        ap.error("Only {} eligible unexcluded scene IDs; need {}.".format(len(eligible), args.count))
    chosen = random.Random(args.seed).sample(eligible, args.count)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(sid + "\n" for sid, _ in chosen), encoding="utf-8")
    with args.report.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("scene_id", "original_ply_bytes", "original_ply_MiB"))
        for sid, size in chosen:
            writer.writerow((sid, size, "{:.2f}".format(size / 1048576)))

    print("Original PLYs scanned: {:,}".format(num_ply))
    print("Published IDs in manifest: {:,}".format(len(published)))
    print("Previously selected IDs in exclude list: {:,}".format(len(other_exclusions)))
    print("Excluded PLY IDs encountered: {:,}".format(excluded_count))
    print("Missing/empty saved predictions: {:,}".format(missing_predictions))
    print("Invalid/empty source PLYs: {:,}".format(invalid))
    print("Eligible scene IDs: {:,}".format(len(eligible)))
    print("Selected uniformly at random: {:,}; seed {}".format(len(chosen), args.seed))
    print("Selected PLY sizes: {:.2f}–{:.2f} MiB (not filtered or weighted)".format(
        min(size for _, size in chosen) / 1048576,
        max(size for _, size in chosen) / 1048576))
    print("Selection list:", args.out)
    print("Size report:", args.report)
    print("First 10 IDs:")
    for sid, size in chosen[:10]:
        print("  {:25s} {:.2f} MiB".format(sid, size / 1048576))


if __name__ == "__main__":
    main()
