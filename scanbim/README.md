# ScanBIM — Interactive Material Explorer

A static, GPU-free browser demo for the research project **Open-Vocabulary Material Pseudo-Labeling of Indoor Point Clouds Using Structured Object Context**.

## Open the viewer

When GitHub Pages is enabled for this repository (main branch, repository root):

**https://isharifi.github.io/scanbim/**

The viewer is designed for research readers and reviewers and supports four inspection modes:

| Mode | Meaning |
|---|---|
| Original | Point-cloud RGB appearance |
| Method A | Global eight-material prompting |
| Method B | Object-conditioned material prompting in annotated regions |
| Hybrid | Method B in annotated regions and Method A outside them |

Orbit with the left mouse button; zoom with the wheel; pan with the right mouse button.
Use keyboard **1–4** to switch modes, **R** to reset the camera, the point-size slider to tune visual density, and the camera button to save a PNG.

**Important:** The initial sample is a *synthetic illustrative placeholder* and does **not** contain actual ScanBIM predictions. It is labeled clearly in the UI and must be replaced before citing the viewer as an experimental results demo.

## Hosting

The viewer contains only static HTML, CSS, JavaScript and binary point data; no server-side software, backend, GPU or user account is needed.

In [GitHub repository settings](https://github.com/isharifi/isharifi.github.io/settings/pages), select:

- **Build and deployment → Source:** Deploy from a branch
- **Branch:** main
- **Folder:** /(root)
- Save.

The files live in the independent \`scanbim/\` directory to avoid altering the main GitHub Pages homepage.

## Add the first research scene (later)

Export four **colored PLY files** for the same scene, ideally in common coordinates:

1. original RGB cloud;
2. Method A material pseudo-label cloud;
3. Method B object-conditioned pseudo-label cloud;
4. hybrid cloud.

The colors in the material PLYs should use the eight ScanBIM material colors. PLYs may have different numbers of points (e.g., Method B covers only annotated regions).

From a local clone, install converter dependencies:

\`\`\`bash
python -m pip install numpy plyfile
\`\`\`

Then run:

\`\`\`bash
python scanbim/tools/prepare_scene.py \
  --scene-id scene_000000_00_0 \
  --name "Example indoor scene" \
  --original /path/original_rgb.ply \
  --method-a /path/method_A.ply \
  --method-b /path/method_B.ply \
  --hybrid /path/hybrid.ply \
  --out-dir scanbim \
  --max-points 180000
\`\`\`

The converter writes:

\`\`\`text
scanbim/
├── scenes.json
└── data/
    └── scene_000000_00_0/
        ├── original.bin
        ├── method_a.bin
        ├── method_b.bin
        └── hybrid.bin
\`\`\`

Commit and push the generated files to the \`main\` branch. The app will detect the new scene automatically and select it by default. It keeps the illustrative placeholder available in the selector for UI checks.

Repeat the converter with another scene ID to add more scenes later; the manifest retains earlier entries.

### Binary format

The converter uses a 16-byte-per-point record: three little-endian float32 coordinates (XYZ), followed by four uint8 bytes (RGB + reserved). No JavaScript decompression dependency is needed.

The default limit of 180,000 points per mode keeps web data manageable. Point selection is deterministic given the seed. When PLY vertex ordering matches, the exact same indices are used for all modes. Larger source clouds can be visualized with higher \`--max-points\` settings if necessary.

## Coordinate system and orientation

**SpatialLM/OpenScene PLY exports are treated as Z-up**; the viewer uses the conventional Three.js Y-up scene. To display the clouds upright without editing the source PLY or exported binary values, it applies a -90° rotation around the X axis:

```text
dataset (x, y, z)  →  viewer (x, z, -y)
```

The same transform is applied to Original, Method A, Method B, and Hybrid. Camera framing and the reference grid use the transformed bounds. The illustrative placeholder is authored directly in Y-up and is not rotated.

Use the **Scene orientation (source up axis)** dropdown in the viewer to try `+Z`, `−Z`, `+Y`, `−Y`, `+X`, or `−X` as the source up direction if a scene appears tipped or inverted. The viewer applies the selected rotation consistently to Original, Method A, Method B, and Hybrid, and recalculates the bounding box and camera. Each selection is remembered for that scene in the current browser using local storage; it does not change the hosted data or other visitors' settings.

For a permanent published default, set the scene's `"upAxis"` in `scenes.json` to a supported value such as `"Y"`, `"-Y"`, `"X"`, `"-X"`, `"Z"`, or `"-Z"` after inspecting the actual scene. The SpatialLM default is `"Z"`. Changes to the point data or re-exporting scene files are **not required** to change the up-axis metadata.

## Research interpretation

This viewer is for inspecting *material pseudo-labels* and contextual effects, **not ground-truth material accuracy**. Method B and Hybrid depend on structured object annotations. Areas without annotations may be omitted in Method B mode. Color correspondence and class lists should be documented when experimental scenes are added.

## Technical

Built with Three.js ES modules (CDN), OrbitControls, and the browser WebGL API. Point data is loaded locally by the browser using HTTP GET from GitHub Pages. The site uses no tracking or external analytics.

For local testing:

\`\`\`bash
cd scanbim
python -m http.server 8000
\`\`\`

Open http://localhost:8000/ . A local HTTP server is necessary for ES modules and fetch; opening index.html via file:// is not supported.

Source: https://github.com/isharifi/isharifi.github.io/tree/main/scanbim
