#!/usr/bin/env python3
"""Convert four colored PLY point clouds into lightweight ScanBIM web scene assets.

All four inputs must be from the SAME scene: original RGB, Method A, Method B,
and the hybrid. The script NEVER synthesizes missing experimental results.
Point order need not match, but using corresponding PLY exports is recommended.

Requires Python 3.8+ and numpy, plyfile:
  python -m pip install numpy plyfile

Example:
  python tools/prepare_scene.py --scene-id scene_000000_00_0 \
    --original /path/original.ply \
    --method-a /path/methodA.ply \
    --method-b /path/methodB.ply \
    --hybrid /path/hybrid.ply \
    --out-dir /path/to/isharifi.github.io/scanbim

All four modes are stored independently, so Method B can contain fewer points.
Each point is 16 bytes: little-endian f32 X,Y,Z and u8 R,G,B,padding.
"""
from __future__ import print_function

import argparse
import json
import re
from pathlib import Path

import numpy as np

try:
    from plyfile import PlyData
except ImportError as exc:
    raise SystemExit("Missing plyfile. Install with: python -m pip install plyfile") from exc

MODE_FILES = {
    "original": "original.bin",
    "methodA": "method_a.bin",
    "methodB": "method_b.bin",
    "hybrid": "hybrid.bin",
}

RECORD_DTYPE = np.dtype([
    ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
    ("red", "u1"), ("green", "u1"), ("blue", "u1"), ("padding", "u1"),
])
assert RECORD_DTYPE.itemsize == 16


def load_ply(path):
    cloud = PlyData.read(str(path))
    if "vertex" not in cloud:
        raise ValueError("{} contains no vertex element".format(path))
    vertices = cloud["vertex"].data
    columns = vertices.dtype.names or ()
    if not set(("x", "y", "z")).issubset(columns):
        raise ValueError("{} lacks vertex x/y/z".format(path))
    xyz = np.column_stack([
        vertices["x"], vertices["y"], vertices["z"]
    ]).astype(np.float32)
    if not np.isfinite(xyz).all():
        raise ValueError("{} contains invalid xyz coordinates".format(path))

    if set(("red", "green", "blue")).issubset(columns):
        names = ("red", "green", "blue")
    elif set(("r", "g", "b")).issubset(columns):
        names = ("r", "g", "b")
    else:
        raise ValueError(
            "{} has no RGB vertex properties. Export a colored PLY "
            "for each visualization mode.".format(path)
        )
    rgb = np.column_stack([vertices[n] for n in names])
    if not np.isfinite(rgb).all():
        raise ValueError("{} contains invalid RGB values".format(path))
    rgb = rgb.astype(np.float32)
    if rgb.size and float(np.max(rgb)) <= 1.01:
        rgb *= 255.0
    rgb = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    if len(xyz) == 0:
        raise ValueError("{} contains no points".format(path))
    return xyz, rgb


def subsample(xyz, rgb, limit, seed, shared_indices=None):
    if shared_indices is not None:
        indices = shared_indices
    elif limit and len(xyz) > limit:
        rng = np.random.RandomState(seed)
        indices = np.sort(rng.choice(len(xyz), size=limit, replace=False))
    else:
        indices = np.arange(len(xyz))
    return xyz[indices], rgb[indices], indices


def write_bin(path, xyz, rgb):
    record = np.empty(len(xyz), dtype=RECORD_DTYPE)
    for j, name in enumerate(("x", "y", "z")):
        record[name] = xyz[:, j]
    for j, name in enumerate(("red", "green", "blue")):
        record[name] = rgb[:, j]
    record["padding"] = 0
    record.tofile(str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scene-id", required=True,
                        help="Unique stable scene ID, e.g. scene_000000_00_0")
    parser.add_argument("--name", default=None, help="Display label in scene selector")
    parser.add_argument("--description", default="ScanBIM experimental point cloud")
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--method-a", type=Path, required=True)
    parser.add_argument("--method-b", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="Local copy of the scanbim/ GitHub Pages directory")
    parser.add_argument("--max-points", type=int, default=180000,
                        help="Maximum retained points per mode (default 180000)")
    parser.add_argument("--seed", type=int, default=20261015)
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.scene_id):
        parser.error("--scene-id must contain only letters, digits, hyphens and underscores")
    if args.max_points < 1000:
        parser.error("--max-points must be at least 1000")
    paths = {
        "original": args.original,
        "methodA": args.method_a,
        "methodB": args.method_b,
        "hybrid": args.hybrid,
    }
    for key, path in paths.items():
        if not path.is_file():
            parser.error("Missing {} PLY: {}".format(key, path))

    output = args.out_dir.resolve()
    target = output / "data" / args.scene_id
    target.mkdir(parents=True, exist_ok=True)

    modes = {}
    original_xyz, original_rgb = load_ply(paths["original"])
    base_xyz, base_rgb, shared_idx = subsample(
        original_xyz, original_rgb, args.max_points, args.seed
    )
    write_bin(target / MODE_FILES["original"], base_xyz, base_rgb)
    modes["original"] = {
        "url": "data/{}/{}".format(args.scene_id, MODE_FILES["original"]),
        "pointCount": len(base_xyz),
    }
    print("original: {:,} → {:,} points".format(len(original_xyz), len(base_xyz)))

    for key in ("methodA", "methodB", "hybrid"):
        xyz, rgb = load_ply(paths[key])
        same_order = (
            len(xyz) == len(original_xyz)
            and np.allclose(xyz[:min(100, len(xyz))],
                            original_xyz[:min(100, len(xyz))], atol=1e-4, rtol=0)
            and np.allclose(xyz[-min(100, len(xyz)):],
                            original_xyz[-min(100, len(xyz)):], atol=1e-4, rtol=0)
        )
        # Reuse exact point indices when vertex order is the same, to avoid
        # artificial point-to-point jumps on mode switching.
        chosen, colors, _ = subsample(
            xyz, rgb, args.max_points, args.seed,
            shared_indices=shared_idx if same_order else None,
        )
        write_bin(target / MODE_FILES[key], chosen, colors)
        modes[key] = {
            "url": "data/{}/{}".format(args.scene_id, MODE_FILES[key]),
            "pointCount": len(chosen),
        }
        print("{}: {:,} → {:,} points{}".format(
            key, len(xyz), len(chosen),
            " (matching sample indices)" if same_order else ""
        ))

    item = {
        "id": args.scene_id,
        "name": args.name or args.scene_id,
        "description": args.description,
        "modes": modes,
    }
    manifest_path = output / "scenes.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        data = {"version": 1, "scenes": []}
    data["version"] = 1
    data["scenes"] = [
        other for other in data.get("scenes", [])
        if other.get("id") != args.scene_id
    ] + [item]
    manifest_path.write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    print("Saved scene manifest:", manifest_path)
    print("Generated binary scene files:", target)
    print("Scene is ready to commit to GitHub Pages.")


if __name__ == "__main__":
    main()
