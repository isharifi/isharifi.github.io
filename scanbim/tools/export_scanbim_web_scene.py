#!/usr/bin/env python3
"""Export one ScanBIM 20k scene to the public browser viewer and optional PLYs.

Run inside the existing OpenScene Singularity container (Python 3.8+,
numpy and plyfile installed). This is a CPU-only export: NO GPU inference.

The two NPZ files from the same scene and the original RGB PLY must have
matching point order/coordinates. The exporter fails safely otherwise.

Website binary format: little-endian XYZ float32 + RGB uint8 + padding
(16 bytes per displayed point), compatible with scanbim/app.js.
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np

MATERIAL_NAMES = (
    "wood", "metal", "concrete", "glass", "plastic", "fabric", "plasterboard", "tile"
)
# Exactly the palette in tools/object_material_config.py.
MATERIAL_COLORS_RGB = np.asarray([
    [150, 90, 40], [160, 160, 160], [110, 110, 110], [120, 200, 255],
    [220, 80, 180], [220, 160, 90], [245, 245, 220], [60, 160, 220],
], dtype=np.uint8)
RECORD = np.dtype([
    ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
    ("red", "u1"), ("green", "u1"), ("blue", "u1"), ("reserved", "u1"),
])
assert RECORD.itemsize == 16


def read_original(path):
    from plyfile import PlyData
    v = PlyData.read(str(path))["vertex"]
    names = set(v.data.dtype.names)
    if not {"x", "y", "z"}.issubset(names):
        raise ValueError("Original PLY lacks XYZ vertex properties: {}".format(path))
    cols = ("red", "green", "blue") if {"red", "green", "blue"}.issubset(names) else ("r", "g", "b")
    if not set(cols).issubset(names):
        raise ValueError("Original PLY has no RGB vertex properties: {}".format(path))
    xyz = np.column_stack([v[k] for k in ("x", "y", "z")]).astype(np.float32)
    colors = np.column_stack([v[k] for k in cols]).astype(np.float32)
    if not np.isfinite(xyz).all() or not np.isfinite(colors).all():
        raise ValueError("Original PLY contains non-finite coordinates/colors")
    if colors.size and colors.max() <= 1.0 and colors.min() >= 0.0:
        colors *= 255.0
    rgb = np.clip(np.rint(colors), 0, 255).astype(np.uint8)
    return xyz, rgb


def read_labels(path, method):
    with np.load(str(path), allow_pickle=False) as saved:
        if not {"coords", "material_id"}.issubset(saved.files):
            raise ValueError("Prediction NPZ missing coords/material_id: {}".format(path))
        xyz = np.asarray(saved["coords"], dtype=np.float32)
        labels = np.asarray(saved["material_id"], dtype=np.int16)
        if "material_names" in saved.files:
            names = [v.decode("utf-8") if isinstance(v, bytes) else str(v)
                     for v in saved["material_names"].tolist()]
            if names != list(MATERIAL_NAMES):
                raise ValueError("Material-name order differs from the website palette in {}: {}".format(path, names))
    if xyz.ndim != 2 or xyz.shape[1] != 3 or labels.shape != (len(xyz),):
        raise ValueError("Invalid prediction shapes in {}".format(path))
    invalid = (labels < (-1 if method == "B" else 0)) | (labels >= len(MATERIAL_NAMES))
    if np.any(invalid):
        raise ValueError("Unexpected material IDs in {}".format(path))
    if not np.isfinite(xyz).all():
        raise ValueError("Non-finite coordinates in {}".format(path))
    return xyz, labels


def assert_same_xyz(reference, xyz, label):
    if reference.shape != xyz.shape:
        raise ValueError("{} coordinate shape differs: {} vs {}".format(label, reference.shape, xyz.shape))
    delta = float(np.max(np.abs(reference - xyz))) if len(xyz) else 0.0
    if delta > 1e-4:
        raise ValueError("{} has different coordinates/vertex ordering (max XYZ delta {:g} m). "
                         "Do not combine incompatible scenes; check PLY and NPZ inputs.".format(label, delta))


def write_binary(path, xyz, rgb):
    if len(xyz) != len(rgb):
        raise ValueError("Mismatched XYZ/RGB for {}".format(path))
    arr = np.empty(len(xyz), dtype=RECORD)
    for j, name in enumerate(("x", "y", "z")):
        arr[name] = xyz[:, j]
    for j, name in enumerate(("red", "green", "blue")):
        arr[name] = rgb[:, j]
    arr["reserved"] = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    arr.tofile(str(path))
    return len(arr)


def write_ply(path, xyz, rgb):
    from plyfile import PlyData, PlyElement
    fields = np.empty(len(xyz), dtype=[
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1")
    ])
    for i, name in enumerate(("x", "y", "z")):
        fields[name] = xyz[:, i]
    for i, name in enumerate(("red", "green", "blue")):
        fields[name] = rgb[:, i]
    path.parent.mkdir(parents=True, exist_ok=True)
    PlyData([PlyElement.describe(fields, "vertex")], text=False).write(str(path))


def generate(scene_id, original_path, a_path, b_path, output, max_points, seed,
             ply_dir=None, name=None):
    orig_xyz, orig_rgb = read_original(original_path)
    a_xyz, a_id = read_labels(a_path, "A")
    b_xyz, b_id = read_labels(b_path, "B")
    assert_same_xyz(orig_xyz, a_xyz, "Method A")
    assert_same_xyz(orig_xyz, b_xyz, "Method B")
    if len(orig_xyz) == 0:
        raise ValueError("Empty scene")
    if len(orig_xyz) > max_points:
        rng = np.random.RandomState(seed)
        take = np.sort(rng.choice(len(orig_xyz), max_points, replace=False))
    else:
        take = np.arange(len(orig_xyz))
    xyz = orig_xyz[take]
    rgb = orig_rgb[take]
    labels_a = a_id[take]
    labels_b = b_id[take]
    assigned = labels_b >= 0
    a_rgb = MATERIAL_COLORS_RGB[labels_a]
    b_rgb = MATERIAL_COLORS_RGB[labels_b[assigned]]
    hybrid_rgb = a_rgb.copy()
    hybrid_rgb[assigned] = b_rgb
    data = {
        "original": (xyz, rgb, "original.bin"),
        "methodA": (xyz, a_rgb, "method_a.bin"),
        "methodB": (xyz[assigned], b_rgb, "method_b.bin"),
        "hybrid": (xyz, hybrid_rgb, "hybrid.bin"),
    }
    out_dir = output / "data" / scene_id
    modes = {}
    for mode, (positions, colors, filename) in data.items():
        write_binary(out_dir / filename, positions, colors)
        modes[mode] = {
            "url": "data/{}/{}".format(scene_id, filename),
            "pointCount": int(len(positions)),
        }
        print("{:9s}: {:8,d} points -> {}".format(mode, len(positions), out_dir / filename))
        if ply_dir is not None:
            write_ply(ply_dir / (scene_id + "_" + mode + ".ply"), positions, colors)
    meta = output / "scenes.json"
    content = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {"version": 1, "scenes": []}
    content["version"] = 1
    entry = {
        "id": scene_id,
        "name": name or scene_id,
        "description": "ScanBIM 20k material pseudo-labeling experiment",
        "modes": modes,
    }
    content["scenes"] = [s for s in content.get("scenes", []) if s.get("id") != scene_id] + [entry]
    output.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    print("Manifest:", meta)
    print("Processed {:,} original points; displayed {:,} ({:.1f}%).".format(
        len(orig_xyz), len(take), 100.0 * len(take) / len(orig_xyz)))
    print("Method B annotated points in displayed subset: {:,} ({:.1f}%).".format(
        int(assigned.sum()), 100.0 * assigned.mean()))
    print("No new inference was performed.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scene-id", required=True)
    p.add_argument("--project-root", type=Path, default=Path.home() / "scanbim")
    p.add_argument("--out-dir", type=Path, required=True,
                   help="Website staging directory. Contains scenes.json and data/<scene-id>/*.bin")
    p.add_argument("--ply-dir", type=Path, default=None,
                   help="Optional export of four colored PLYs (keep outside public website)")
    p.add_argument("--max-points", type=int, default=180000)
    p.add_argument("--seed", type=int, default=20261015)
    p.add_argument("--name", default=None, help="Friendly displayed scene name")
    args = p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.scene_id):
        p.error("Scene ID may only contain A-Z, a-z, 0-9, _ and -")
    if args.max_points <= 0:
        p.error("--max-points must be positive")
    root = args.project_root.expanduser()
    sid = args.scene_id
    original = root / "data/spatiallm_dataset_20000/pcd" / (sid + ".ply")
    a_file = root / "outputs/spatiallm_20000_deterministic/method_A/material_npz" / (sid + "_material.npz")
    b_file = root / "outputs/spatiallm_20000_deterministic/method_B/objectaware_material_npz" / (sid + "_objectaware_material.npz")
    for path in (original, a_file, b_file):
        if not path.is_file():
            p.error("Missing required scene source: {}".format(path))
    generate(sid, original, a_file, b_file, args.out_dir.expanduser(),
             args.max_points, args.seed,
             ply_dir=args.ply_dir.expanduser() if args.ply_dir else None,
             name=args.name)


if __name__ == "__main__":
    main()