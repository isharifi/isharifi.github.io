import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createIllustrativeScene } from "./placeholder.js";

const $ = (id) => document.getElementById(id);
const modeButtons = Array.from(document.querySelectorAll("[data-mode]"));
const modeDetails = {
  original: "The original point cloud's RGB appearance. No material labels are applied.",
  methodA: "Global point–text matching: every processed point is compared with the full eight-material vocabulary.",
  methodB: "Object-conditioned material pseudo-labels are visualized only within annotated structured regions.",
  hybrid: "Method B labels refine annotated regions; Method A labels cover the remaining scene."
};
const requestedModes = ["original", "methodA", "methodB", "hybrid"];
// Source coordinate up directions; all rendered scenes use Three.js +Y-up.
const UP_AXES = {
  Z: new THREE.Vector3(0, 0, 1),
  "-Z": new THREE.Vector3(0, 0, -1),
  Y: new THREE.Vector3(0, 1, 0),
  "-Y": new THREE.Vector3(0, -1, 0),
  X: new THREE.Vector3(1, 0, 0),
  "-X": new THREE.Vector3(-1, 0, 0)
};

let renderer, camera, controls, grid, cloud, currentScene, currentMode = "original";
let sceneRegistry = [];
let loadToken = 0;
const scene3d = new THREE.Scene();
const canvasHost = $("viewerCanvas");

function status(message) { $("footStatus").textContent = message; }
function loading(message = "") { $("loadingStatus").textContent = message; }
function error(message) { const e = $("errorPanel"); e.hidden = false; e.textContent = message; loading(""); }
function clearError() { $("errorPanel").hidden = true; }
function number(n) { return new Intl.NumberFormat("en-US").format(n); }

function initRenderer() {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x0b1523, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  canvasHost.appendChild(renderer.domElement);
  camera = new THREE.PerspectiveCamera(48, 1, 0.01, 2000);
  camera.position.set(9, 5, 9);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.075;
  controls.rotateSpeed = 0.72;
  controls.panSpeed = 0.75;
  controls.zoomSpeed = 1;
  controls.minDistance = 0.15;
  controls.maxDistance = 300;
  grid = new THREE.GridHelper(12, 24, 0x34546b, 0x294052);
  grid.material.transparent = true;
  grid.material.opacity = 0.35;
  scene3d.add(grid);
  resize();
  const observer = new ResizeObserver(resize);
  observer.observe(canvasHost);
  window.addEventListener("resize", resize);
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene3d, camera); });
}

function resize() {
  if (!renderer || !camera) return;
  const width = Math.max(canvasHost.clientWidth, 1);
  const height = Math.max(canvasHost.clientHeight, 1);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
}

function arrayToGeometry(data) {
  if (!data || !data.positions || !data.colors) throw Error("Invalid scene data: missing position or color attributes.");
  if (data.positions.length % 3 !== 0 || data.colors.length !== data.positions.length) throw Error("Invalid point-cloud attribute counts.");
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(data.positions, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(data.colors, 3, true));
  geo.computeBoundingSphere();
  return geo;
}

function showMode(mode) {
  if (!currentScene || !requestedModes.includes(mode)) return;
  const data = currentScene.modes[mode];
  if (!data) return error("This scene does not contain the selected visualization mode.");
  clearError();
  const geometry = arrayToGeometry(data);
  const material = new THREE.PointsMaterial({
    size: Number($("pointSize").value), sizeAttenuation: false, vertexColors: true,
    depthWrite: true, transparent: false, fog: false
  });
  const next = new THREE.Points(geometry, material);
  // Apply the single source-to-Three.js orientation to all four modes.
  // Source xyz and RGB data are never modified.
  next.quaternion.copy(currentScene.orientationQuaternion || new THREE.Quaternion());
  next.frustumCulled = false;
  if (cloud) {
    scene3d.remove(cloud);
    cloud.geometry.dispose();
    cloud.material.dispose();
  }
  cloud = next;
  scene3d.add(cloud);
  currentMode = mode;
  modeButtons.forEach((btn) => {
    const active = btn.dataset.mode === mode;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-pressed", String(active));
  });
  $("modeExplanation").textContent = modeDetails[mode];
  $("legend").style.opacity = mode === "original" ? "0.45" : "1";
  $("scenePointCount").textContent = number(data.positions.length / 3) + " visible points";
  status((currentScene.isPlaceholder ? "Illustrative geometry" : "Research scene") + " · " + (mode === "original" ? "Original RGB" : mode === "methodA" ? "Method A" : mode === "methodB" ? "Method B" : "Hybrid"));
}

function resetCamera() {
  if (!currentScene || !camera || !controls) return;
  const bounds = currentScene.bounds;
  const center = bounds.getCenter(new THREE.Vector3());
  const size = bounds.getSize(new THREE.Vector3());
  const extent = Math.max(size.x, size.y, size.z, 1);
  const viewDir = new THREE.Vector3(1, 0.62, 1.08).normalize();
  camera.position.copy(center).addScaledVector(viewDir, extent * 1.53);
  camera.near = Math.max(0.01, extent / 1000);
  camera.far = Math.max(300, extent * 40);
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
  grid.position.set(center.x, bounds.min.y - 0.06, center.z);
  grid.scale.setScalar(Math.max(extent / 12, 0.2));
}

async function decodeBinary(url, expectedCount) {
  const response = await fetch(url);
  if (!response.ok) throw Error("Couldn't load " + url + " (HTTP " + response.status + ").");
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength % 16 !== 0) throw Error("Unexpected binary scene data length: " + url);
  const count = buffer.byteLength / 16;
  if (expectedCount != null && count !== expectedCount) throw Error("Point count mismatch for " + url);
  const view = new DataView(buffer);
  const positions = new Float32Array(count * 3);
  const colors = new Uint8Array(count * 3);
  for (let i = 0; i < count; i++) {
    const j = i * 3, k = i * 16;
    positions[j] = view.getFloat32(k, true);
    positions[j + 1] = view.getFloat32(k + 4, true);
    positions[j + 2] = view.getFloat32(k + 8, true);
    colors[j] = view.getUint8(k + 12);
    colors[j + 1] = view.getUint8(k + 13);
    colors[j + 2] = view.getUint8(k + 14);
  }
  return { positions, colors };
}

async function loadRealScene(entry) {
  const modes = {};
  await Promise.all(requestedModes.map(async (mode) => {
    const spec = entry.modes && entry.modes[mode];
    if (!spec || !spec.url) throw Error("Scene '" + entry.id + "' is missing " + mode + " data.");
    const sourceUrl = new URL(spec.url, new URL("./", window.location.href)).href;
    modes[mode] = await decodeBinary(sourceUrl, spec.pointCount);
  }));
  const bbox = new THREE.Box3();
  const samples = modes.original.positions;
  for (let i = 0; i < samples.length; i += 3) bbox.expandByPoint(new THREE.Vector3(samples[i], samples[i + 1], samples[i + 2]));
  if (bbox.isEmpty()) throw Error("No points in original scene.");
  // Preserve unmodified bounds. A per-scene orientation is applied when selected.
  const upAxis = String(entry.upAxis || "Z").toUpperCase();
  if (!Object.prototype.hasOwnProperty.call(UP_AXES, upAxis)) {
    throw Error("Unsupported upAxis '" + upAxis + "' for scene " + entry.id);
  }
  return {
    id: entry.id, name: entry.name || entry.id,
    description: entry.description || "Research point cloud",
    isPlaceholder: false, modes,
    upAxis,
    sourceBounds: bbox,
    bounds: bbox.clone()
  };
}

function applySceneOrientation(scene) {
  // SpatialLM/OpenScene research scenes are Z-up; the synthetic placeholder
  // was authored Y-up. Optional scene manifest upAxis can handle future datasets.
  // No browser override: previously stored selections cannot affect rendering.
  const axis = scene.isPlaceholder ? "Y" : (scene.upAxis || "Z");
  const rotation = new THREE.Quaternion().setFromUnitVectors(UP_AXES[axis], UP_AXES.Y);
  scene.orientationQuaternion = rotation;
  const sourceBounds = scene.sourceBounds || scene.bounds;
  scene.bounds = sourceBounds.clone().applyMatrix4(
    new THREE.Matrix4().makeRotationFromQuaternion(rotation)
  );
}

async function selectScene(key) {
  const token = ++loadToken;
  clearError();
  loading("Loading point-cloud data…");
  try {
    const entry = sceneRegistry.find((s) => s.id === key);
    const data = key === "placeholder" ? createIllustrativeScene() : await loadRealScene(entry);
    if (token !== loadToken) return;
    currentScene = data;
    if (!currentScene.sourceBounds) currentScene.sourceBounds = currentScene.bounds.clone();
    applySceneOrientation(currentScene);
    resetCamera();
    $("sceneBadge").textContent = data.isPlaceholder ? "ILLUSTRATIVE INDOOR SCENE" : data.name.toUpperCase();
    $("placeholderBadge").hidden = !data.isPlaceholder;
    $("sceneType").textContent = data.isPlaceholder ? "Synthetic preview" : "Experimental scene";
    showMode(currentMode);
    loading("");
  } catch (e) {
    console.error(e);
    error("Unable to load this scene. " + (e && e.message ? e.message : String(e)));
    status("Scene loading failed");
  }
}

async function getSceneManifest() {
  // GitHub Pages/browser caches may serve the previously published manifest
  // immediately after a commit. Request a fresh copy; use GitHub's raw copy
  // as a fallback if the Pages URL is temporarily unavailable or stale.
  const sources = [
    new URL("./scenes.json", import.meta.url).href,
    "https://raw.githubusercontent.com/isharifi/isharifi.github.io/main/scanbim/scenes.json"
  ];
  const errors = [];
  let emptyManifest = null;
  for (const source of sources) {
    try {
      const url = source + (source.includes("?") ? "&" : "?") + "v=" + Date.now();
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw Error("HTTP " + response.status + " from " + source);
      const manifest = await response.json();
      if (!manifest || !Array.isArray(manifest.scenes)) {
        throw Error("Manifest is missing its scenes array at " + source);
      }
      if (!manifest.scenes.length) {
        emptyManifest = manifest;
        continue;
      }
      console.info("ScanBIM: loaded " + manifest.scenes.length + " scenes from " + source);
      return manifest;
    } catch (cause) {
      errors.push(cause instanceof Error ? cause.message : String(cause));
    }
  }
  if (emptyManifest) return emptyManifest;
  throw Error(errors.join(" | ") || "No valid scene manifest was found");
}

async function initScenes() {
  let manifestError = "";
  try {
    const manifest = await getSceneManifest();
    sceneRegistry = manifest.scenes.filter((entry) =>
      entry && typeof entry.id === "string" && entry.modes &&
      requestedModes.every((mode) => entry.modes[mode] && entry.modes[mode].url)
    );
  } catch (cause) {
    manifestError = cause instanceof Error ? cause.message : String(cause);
    console.error("ScanBIM scene manifest loading failed:", cause);
  }
  const select = $("sceneSelect");
  select.replaceChildren();
  const placeholderOption = document.createElement("option");
  placeholderOption.value = "placeholder";
  placeholderOption.textContent = "Illustrative example (synthetic)";
  select.appendChild(placeholderOption);
  sceneRegistry.forEach((entry) => {
    const option = document.createElement("option");
    option.value = entry.id;
    option.textContent = entry.name || entry.id;
    select.appendChild(option);
  });
  select.value = sceneRegistry.length ? sceneRegistry[0].id : "placeholder";
  await selectScene(select.value);
  if (manifestError) {
    error("The published scene list could not be loaded. " + manifestError +
      ". You can also inspect /scanbim/scenes.json directly.");
  } else {
    console.info("ScanBIM scene selector initialized with " + sceneRegistry.length + " research scenes");
  }
}

modeButtons.forEach((button) => button.addEventListener("click", () => showMode(button.dataset.mode)));
$("sceneSelect").addEventListener("change", (event) => selectScene(event.target.value));
$("pointSize").addEventListener("input", (event) => {
  const n = Number(event.target.value);
  $("pointSizeValue").textContent = n.toFixed(n % 1 ? 2 : 1) + " px";
  if (cloud) cloud.material.size = n;
});
$("showGrid").addEventListener("change", (event) => { if (grid) grid.visible = event.target.checked; });
$("autoRotate").addEventListener("change", (event) => { if (controls) controls.autoRotate = event.target.checked; });
$("resetView").addEventListener("click", resetCamera);
$("screenshot").addEventListener("click", () => {
  if (!renderer || !currentScene) return;
  renderer.render(scene3d, camera);
  const a = document.createElement("a");
  a.download = "ScanBIM_" + currentScene.id + "_" + currentMode + ".png";
  a.href = renderer.domElement.toDataURL("image/png");
  a.click();
});
$("fullscreen").addEventListener("click", async () => {
  if (document.fullscreenElement) await document.exitFullscreen();
  else if ($("viewerCanvas").requestFullscreen) await $("viewerCanvas").requestFullscreen();
});
document.addEventListener("keydown", (event) => {
  if (event.target && ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
  if (event.key >= "1" && event.key <= "4") showMode(requestedModes[Number(event.key) - 1]);
  if (event.key.toLowerCase() === "r") resetCamera();
});
try {
  initRenderer();
  await initScenes();
} catch (e) {
  console.error(e);
  error("The 3D viewer could not initialize. Check that your browser supports WebGL and that external JavaScript modules are accessible. " + e.message);
}
