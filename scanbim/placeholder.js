import * as THREE from "three";

// This preview is deliberately synthetic. It is NOT derived from ScanBIM predictions.
// Replace it with four actual scene PLY files using tools/prepare_scene.py.
const palette = [
  [151, 90, 43],    // wood
  [162, 162, 162],  // metal
  [110, 110, 110],  // concrete
  [117, 200, 249],  // glass
  [218, 68, 175],   // plastic
  [221, 162, 91],   // fabric
  [245, 244, 220],  // plasterboard
  [60, 158, 210]    // tile
];
function seededRandom(seed) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function tinted(color, rand) {
  const factor = 0.83 + rand() * 0.33;
  return color.map((v) => Math.min(255, Math.max(0, Math.round(v * factor))));
}
export function createIllustrativeScene() {
  const rand = seededRandom(68459);
  const originalPositions = [], originalColors = [];
  const methodAPositions = [], methodAColors = [];
  const methodBPositions = [], methodBColors = [];
  const hybridPositions = [], hybridColors = [];

  function put(x, y, z, material, originalRGB, annotated) {
    const p = [x, y, z];
    const original = tinted(originalRGB, rand);
    // The intentionally noisy Method A and cleaner Method B colors only demonstrate
    // the UI interaction. They are never presented as experimental predictions.
    const roll = rand();
    let a = material;
    if (roll < 0.39) a = 6;
    else if (roll < 0.56) a = 1;
    else if (roll < 0.67) a = 5;
    else if (roll < 0.78) a = 0;
    else if (roll < 0.84) a = 7;
    const b = rand() < 0.94 ? material : (material === 0 ? 1 : material === 3 ? 1 : material === 5 ? 4 : material);
    originalPositions.push(...p); originalColors.push(...original);
    methodAPositions.push(...p); methodAColors.push(...palette[a]);
    hybridPositions.push(...p); hybridColors.push(...palette[annotated ? b : a]);
    if (annotated) { methodBPositions.push(...p); methodBColors.push(...palette[b]); }
  }

  function panel(origin, axisU, axisV, nU, nV, material, rgb, annotated = true) {
    for (let i = 0; i < nU; i++) {
      for (let j = 0; j < nV; j++) {
        const u = (i + 0.15 + 0.7 * rand()) / nU;
        const v = (j + 0.15 + 0.7 * rand()) / nV;
        const jiggle = (rand() - 0.5) * 0.012;
        put(
          origin[0] + u * axisU[0] + v * axisV[0] + jiggle,
          origin[1] + u * axisU[1] + v * axisV[1] + jiggle,
          origin[2] + u * axisU[2] + v * axisV[2] + jiggle,
          material, rgb, annotated
        );
      }
    }
  }
  function box(x, y, z, width, height, depth, material, rgb, density = 18, annotated = true) {
    const nx = Math.max(3, Math.round(width * density));
    const ny = Math.max(3, Math.round(height * density));
    const nz = Math.max(3, Math.round(depth * density));
    panel([x - width/2,y - height/2,z - depth/2], [width,0,0],[0,height,0],nx,ny,material,rgb,annotated);
    panel([x - width/2,y - height/2,z + depth/2], [width,0,0],[0,height,0],nx,ny,material,rgb,annotated);
    panel([x - width/2,y - height/2,z - depth/2], [0,0,depth],[0,height,0],nz,ny,material,rgb,annotated);
    panel([x + width/2,y - height/2,z - depth/2], [0,0,depth],[0,height,0],nz,ny,material,rgb,annotated);
    panel([x - width/2,y + height/2,z - depth/2], [width,0,0],[0,0,depth],nx,nz,material,rgb,annotated);
    panel([x - width/2,y - height/2,z - depth/2], [width,0,0],[0,0,depth],nx,nz,material,rgb,annotated);
  }

  // Room structure: floor, back wall and left wall; the front is open to the camera.
  panel([-4.3,0,-3.2], [8.6,0,0], [0,0,6.4], 151,112,7,[152,150,137],false);
  panel([-4.3,0,-3.2], [8.6,0,0], [0,3.15,0],151,56,6,[214,213,202],true);
  panel([-4.3,0,-3.2], [0,0,6.4], [0,3.15,0],112,56,6,[208,207,198],true);
  // Architectural opening and door.
  box(1.65,1.98,-3.13,1.75,1.25,0.035,3,[132,168,179],13);
  box(1.65,1.98,-3.07,1.79,1.27,0.045,1,[120,126,129],5);
  box(-3.35,1.05,-3.07,0.92,2.1,0.06,0,[144,115,82],13);
  // Sofa, cushions, low wooden coffee table.
  box(-1.85,0.56,1.0,2.25,0.5,1.18,5,[130,168,166],17);
  box(-1.85,1.04,0.52,2.25,0.84,0.30,5,[116,149,153],16);
  box(-3.06,0.73,1.0,0.28,0.77,1.22,5,[112,152,153],14);
  box(-0.65,0.73,1.0,0.28,0.77,1.22,5,[112,152,153],14);
  box(-1.9,0.79,1.24,0.80,0.16,0.78,5,[166,189,169],11);
  box(0.55,0.55,1.55,1.75,0.11,1.08,0,[157,117,81],17);
  for (const x of [-0.16,1.24]) for (const z of [1.11,1.99]) box(x,0.28,z,.10,.55,.10,0,[124,93,66],10);
  // Dining table and chairs.
  box(1.8,0.74,-0.55,1.55,0.10,1.05,0,[141,99,67],15);
  for (const x of [1.16,2.44]) for (const z of [-0.94,-0.16]) box(x,0.35,z,.09,.7,.08,1,[82,91,99],9);
  for (const x of [0.65,2.95]) {
    box(x,.53,-.55,.55,.10,.60,0,[149,113,82],14);
    box(x,.95,-.84,.55,.84,.12,0,[140,107,78],12);
    for (const zx of [-.78,-.32]) box(x,.27,zx,.08,.54,.09,1,[105,105,108],8);
  }
  // A bookshelf with a few distinct book volumes.
  box(3.50,1.28,-2.25,0.95,2.4,0.35,0,[112,91,78],16);
  for (let h=0;h<4;h++) {
    box(3.5,.38+h*.52,-2.00,.84,.055,.34,0,[171,129,86],13);
    for (let b=0;b<6;b++) {
      const colors=[[172,102,87],[108,139,146],[178,161,115],[119,126,165]];
      box(3.15+b*.13,.55+h*.52,-1.98,.09,.29,.19,b%4===0?4:5,colors[(b+h)%4],7);
    }
  }
  // A wall-mounted screen.
  box(-1.2,1.9,-3.04,1.25,.74,.045,3,[57,80,97],16);
  box(-1.2,1.9,-2.998,1.33,.82,.028,1,[46,52,58],7);
  // Pendant lights, with no enclosed front wall to obstruct the view.
  for (const x of [-1.6,2.1]) {
    box(x,2.74,.1,.04,.56,.04,1,[153,150,142],6);
    box(x,2.48,.1,.48,.16,.48,1,[178,179,172],11);
  }

  const original = { positions:new Float32Array(originalPositions), colors:new Uint8Array(originalColors) };
  const methodA = { positions:new Float32Array(methodAPositions), colors:new Uint8Array(methodAColors) };
  const methodB = { positions:new Float32Array(methodBPositions), colors:new Uint8Array(methodBColors) };
  const hybrid = { positions:new Float32Array(hybridPositions), colors:new Uint8Array(hybridColors) };
  const bounds = new THREE.Box3(new THREE.Vector3(-4.5,-0.08,-3.4),new THREE.Vector3(4.5,3.25,3.4));
  return {
    id:"illustrative-demo", name:"Illustrative indoor scene",
    description:"Synthetic point cloud for interface testing only",
    isPlaceholder:true, bounds, modes:{original,methodA,methodB,hybrid}
  };
}
