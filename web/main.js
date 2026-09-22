// Cat Breads lounge. A procedural room that reflows with the viewport: the camera frustum sets the
// back wall's width, shelf groups anchor to its edges, the camera backs off on narrow screens so a
// minimum room still fits. 23 SDF cats (skinned GLBs from Blender) sit at strategic spots and turn
// their heads toward the cursor.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const THREE_VER = '0.170.0';
const BUILD = 'audio-4';   // bump after re-exporting models so browsers drop their cached copies
const canvas = document.getElementById('c');

// ------------------------------------------------------------------ renderer, scene, camera
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
const COARSE = matchMedia('(pointer: coarse)').matches;          // finger-first device (iPad, phone)
renderer.setPixelRatio(Math.min(window.devicePixelRatio, COARSE ? 1.5 : 2));   // tablets: a little cheaper per frame
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x3a2418);
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.35;

const BACK_Z = -9, W_MIN = 18, W_MAX = 44, D_DEFAULT = 27, COUCH_Z = -6.3;
const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 300);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.enablePan = false;
controls.minDistance = 12;
controls.maxDistance = 46;
controls.minPolarAngle = 0.95;
controls.maxPolarAngle = 1.78;
controls.minAzimuthAngle = -0.5;
controls.maxAzimuthAngle = 0.5;
controls.target.set(0, 3.0, -5.5);
const CAM_MIN_Y = 0.6, MAX_POLAR = 1.78;
function keepCameraAboveFloor() {   // the tilt limit depends on zoom: never let the eye dip below the floor
  const d = camera.position.distanceTo(controls.target);
  controls.maxPolarAngle = Math.min(MAX_POLAR, Math.acos(THREE.MathUtils.clamp((CAM_MIN_Y - controls.target.y) / d, -1, 1)));
}

// ------------------------------------------------------------------ lights
const hemi = new THREE.HemisphereLight(0xfff0e0, 0x7a4a34, 0.5);
scene.add(hemi);
const key = new THREE.DirectionalLight(0xffeedd, 2.3);
key.position.set(-9, 16, 14);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.radius = 5;
key.shadow.bias = -0.0004;
key.shadow.normalBias = 0.03;
scene.add(key, key.target);
const fill = new THREE.DirectionalLight(0xdde8ff, 0.35);
fill.position.set(10, 6, 10);
scene.add(fill);
const rim = new THREE.DirectionalLight(0xfff2e0, 0.6);   // from behind and above: separates the cats from the wall
rim.position.set(2, 9, -14);
scene.add(rim);
const lamp = new THREE.PointLight(0xffc98a, 18, 16, 1.6);
scene.add(lamp);
const MOOD = { target: 0, value: 0, dirty: true };   // 0 = day, 1 = night (declared early: fitCamera runs at startup)
const CAT_MATS = new Set();
const rand = (a, b) => a + Math.random() * (b - a);   // declared early: the room (and its dust motes) is built by the first camera fit

// ------------------------------------------------------------------ shader FX
// Injected into the standard materials with onBeforeCompile so lighting, shadows and skinning stay intact:
// felted fuzz + a petting ripple on the cats, grain-bending ripples in the floor, sway in the plant. Plus a
// volumetric cone under the lamp, and a post pass (chromatic pulse) that only runs while a treat impact rings.
const FX = { time: { value: 0 }, fuzz: { value: 0.32 } };
const GLSL_NOISE = `
  float fxHash(vec3 p) { p = fract(p * 0.1031); p += dot(p, p.zyx + 31.32); return fract((p.x + p.y) * p.z); }
  float fxNoise(vec3 x) {
    vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(fxHash(i), fxHash(i + vec3(1, 0, 0)), f.x), mix(fxHash(i + vec3(0, 1, 0)), fxHash(i + vec3(1, 1, 0)), f.x), f.y),
               mix(mix(fxHash(i + vec3(0, 0, 1)), fxHash(i + vec3(1, 0, 1)), f.x), mix(fxHash(i + vec3(0, 1, 1)), fxHash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
  }`;
const CAT_VERT = `
  vFxPos = transformed;                                     // object space after skinning: the fuzz sticks to the skin
  if (uTouchAmp > 0.0) {                                    // petting: a dent that recovers and a ring that runs outward
    float d = distance(transformed, uTouch), t = uTouchT;
    float front = d - t * 3.4;
    float ring = sin(front * 9.0) * exp(-front * front * 3.5) * exp(-t * 2.4);
    float dent = -exp(-d * d * 6.0) * exp(-t * 5.0);
    transformed += objectNormal * (ring * 0.07 + dent * 0.09) * uTouchAmp;
  }`;
const CAT_FRAG_NORMAL = `
  #ifdef FX_FUZZ
  { vec3 q = vFxPos * 30.0;
    vec3 nz = vec3(fxNoise(q), fxNoise(q + 11.3), fxNoise(q + 23.7)) - 0.5;
    normal = normalize(normal + uFuzz * nz); }               // fibres: the normal wanders at felt scale
  #endif`;
const CAT_FRAG_COLOR = `
  #ifdef FX_FUZZ
  { float sp = fxNoise(vFxPos * 55.0) - 0.5;
    diffuseColor.rgb *= 1.0 + 0.22 * uFuzz * sp;             // speckle
    float fr = pow(1.0 - abs(dot(normalize(vNormal), normalize(vViewPosition))), 3.0);
    diffuseColor.rgb += uFuzz * 0.10 * fr; }                 // a soft halo of fibres on the silhouette
  #endif`;
function makeCatFX() { return { uTouch: { value: new THREE.Vector3(1e3, 1e3, 1e3) }, uTouchT: { value: 1e3 }, uTouchAmp: { value: 0 }, t0: -1e3 }; }
function catFX(material, fx, fuzz = true) {
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, { uTouch: fx.uTouch, uTouchT: fx.uTouchT, uTouchAmp: fx.uTouchAmp, uFuzz: FX.fuzz });
    shader.vertexShader = 'uniform vec3 uTouch; uniform float uTouchT; uniform float uTouchAmp; varying vec3 vFxPos;\n' +
      shader.vertexShader.replace('#include <skinning_vertex>', '#include <skinning_vertex>' + CAT_VERT);
    shader.fragmentShader = 'uniform float uFuzz; varying vec3 vFxPos;\n' + GLSL_NOISE + '\n' +
      shader.fragmentShader.replace('#include <normal_fragment_maps>', '#include <normal_fragment_maps>' + CAT_FRAG_NORMAL)
        .replace('#include <color_fragment>', '#include <color_fragment>' + CAT_FRAG_COLOR);
  };
  material.defines = Object.assign({}, material.defines || {}, fuzz ? { FX_FUZZ: '' } : {});
  material.customProgramCacheKey = () => `catfx${fuzz ? 1 : 0}`;
  material.needsUpdate = true;
}

// floor: up to 8 live ripples bend the wood grain and tilt the normal so the lights catch the rings
const RIP = { n: 8, i: 0, value: Array.from({ length: 8 }, () => new THREE.Vector4(0, 0, -1e3, 0)) };
function floorRipple(x, z, amp = 1) { RIP.value[RIP.i].set(x, z, FX.time.value, amp); RIP.i = (RIP.i + 1) % RIP.n; }
function floorFX(material) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uRip = { value: RIP.value };
    shader.uniforms.uTime = FX.time;
    shader.vertexShader = 'varying vec3 vWPos;\n' + shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n  vWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    shader.fragmentShader = `uniform vec4 uRip[8]; uniform float uTime; varying vec3 vWPos;
      vec2 fxRipple(vec3 p, out vec2 grad) {
        vec2 off = vec2(0.0); grad = vec2(0.0);
        for (int i = 0; i < 8; i++) {
          vec4 r = uRip[i]; float t = uTime - r.z;
          if (r.w <= 0.0 || t < 0.0 || t > 2.6) continue;
          vec2 dv = p.xz - r.xy; float d = length(dv); vec2 dir = dv / max(d, 1e-3);
          float front = d - t * 2.6;
          float w = sin(front * 7.0) * exp(-front * front * 2.5) * exp(-t * 1.6) * r.w * smoothstep(0.0, 0.15, d);
          off += dir * w * 0.012; grad += dir * w;
        }
        return off;
      }\n` + shader.fragmentShader
      .replace('#include <map_fragment>', `
        vec2 fxG = vec2(0.0);
        #ifdef USE_MAP
          vec2 fxOff = fxRipple(vWPos, fxG);
          vec4 sampledDiffuseColor = texture2D(map, vMapUv + fxOff);
          diffuseColor *= sampledDiffuseColor;
        #endif`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        if (dot(fxG, fxG) > 0.0) { vec3 nW = normalize(vec3(-fxG.x * 1.6, 1.0, -fxG.y * 1.6)); normal = normalize((viewMatrix * vec4(nW, 0.0)).xyz); }`);
  };
  material.customProgramCacheKey = () => 'floorfx';
  material.needsUpdate = true;
}

// plant: leaves flex across their thin axis, more toward the tip, phased by where they stand
function swayFX(material) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = FX.time;
    shader.vertexShader = 'uniform float uTime;\n' + shader.vertexShader.replace('#include <begin_vertex>', `#include <begin_vertex>
      { float h = clamp(transformed.y + 0.5, 0.0, 1.0);
        float ph = dot(modelMatrix[3].xz, vec2(1.7, 2.3));
        float sw = sin(uTime * 1.3 + ph) * 0.40 + sin(uTime * 4.7 + ph * 2.0) * 0.08;
        transformed.x += sw * h * h; transformed.z += 0.4 * sw * h * h * sin(ph); }`);
  };
  material.customProgramCacheKey = () => 'swayfx';
  material.needsUpdate = true;
}

// impact: a chromatic shockwave from the treat's screen position, and a camera shake, both decaying
const PULSE = { amp: 0, radius: 0, center: new THREE.Vector2(0.5, 0.5) };
const SHAKE = { amp: 0, seed: 0 };
function impact(worldPos, strength) {
  const v = worldPos.clone().project(camera);
  PULSE.center.set(v.x * 0.5 + 0.5, v.y * 0.5 + 0.5);
  PULSE.amp = Math.max(PULSE.amp, strength); PULSE.radius = 0;
  SHAKE.amp = Math.max(SHAKE.amp, strength); SHAKE.seed = Math.random() * 100;
}
const PulseShader = {
  uniforms: { tDiffuse: { value: null }, uAmp: { value: 0 }, uRadius: { value: 0 }, uAspect: { value: 1 }, uCenter: { value: new THREE.Vector2(0.5, 0.5) } },
  vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: `uniform sampler2D tDiffuse; uniform float uAmp, uRadius, uAspect; uniform vec2 uCenter; varying vec2 vUv;
    void main() {
      vec2 d = vUv - uCenter; float dist = length(d * vec2(uAspect, 1.0));
      float ring = exp(-pow((dist - uRadius) * 9.0, 2.0)) * uAmp;                 // an expanding shockwave
      vec2 uv = vUv + normalize(d + 1e-5) * ring * 0.012 - d * uAmp * 0.02;        // pushed by the ring, pulled toward the impact
      vec2 ca = d * (0.012 * uAmp + 0.02 * ring);                                  // colour fringes split away from the centre
      float r = texture2D(tDiffuse, uv + ca).r, g = texture2D(tDiffuse, uv).g, b = texture2D(tDiffuse, uv - ca).b;
      gl_FragColor = vec4(r, g, b, 1.0) * (1.0 + 0.10 * ring);
    }`,
};
const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 }));
composer.addPass(new RenderPass(scene, camera));
const pulsePass = new ShaderPass(PulseShader);
composer.addPass(pulsePass);
composer.addPass(new OutputPass());

// ------------------------------------------------------------------ materials
function canvasTexture(w, h, draw, repeat = [1, 1]) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(...repeat);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}
function woodDraw(base, grain, seams, planks) {
  return (g, w, h) => {
    g.fillStyle = base; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 260; i++) {
      g.strokeStyle = grain; g.globalAlpha = 0.05 + Math.random() * 0.12; g.lineWidth = 0.6 + Math.random() * 2.2;
      const y = Math.random() * h, k = 20 + Math.random() * 60, a = 2 + Math.random() * 6;
      g.beginPath(); g.moveTo(0, y);
      for (let x = 0; x <= w; x += 8) g.lineTo(x, y + a * Math.sin(x / k + i));
      g.stroke();
    }
    g.globalAlpha = 1;
    for (let p = 1; p < planks; p++) { g.fillStyle = seams; g.fillRect(0, Math.round(p * h / planks) - 1, w, 3); }
  };
}
const MAT = {
  floor: new THREE.MeshStandardMaterial({ map: canvasTexture(1024, 1024, woodDraw('#a9773f', '#6e4723', 'rgba(50,28,12,0.7)', 8), [4, 4]), roughness: 0.7 }),
  walnut: new THREE.MeshStandardMaterial({ map: canvasTexture(512, 512, woodDraw('#5c3a24', '#2f1c10', 'rgba(0,0,0,0)', 1), [1, 1]), roughness: 0.55 }),
  oak: new THREE.MeshStandardMaterial({ map: canvasTexture(512, 512, woodDraw('#d9b98a', '#a88452', 'rgba(0,0,0,0)', 1), [1, 1]), roughness: 0.6 }),
  lacquer: new THREE.MeshPhysicalMaterial({ color: 0xf6f1ea, roughness: 0.22, clearcoat: 0.8, clearcoatRoughness: 0.15 }),
  sage: new THREE.MeshStandardMaterial({ color: 0x6f9186, roughness: 0.85 }),
  brass: new THREE.MeshStandardMaterial({ color: 0xc9a04a, metalness: 0.9, roughness: 0.32 }),
  fabric: new THREE.MeshStandardMaterial({ color: 0x4f8a80, roughness: 0.95 }),
  mustard: new THREE.MeshStandardMaterial({ color: 0xd9a441, roughness: 0.95 }),
  cream: new THREE.MeshStandardMaterial({ color: 0xf1e3cc, roughness: 0.95 }),
  wallUpper: new THREE.MeshStandardMaterial({ color: 0xa2553f, roughness: 0.95 }),
  wallLower: new THREE.MeshStandardMaterial({ color: 0xead9c2, roughness: 0.9 }),
  trim: new THREE.MeshStandardMaterial({ color: 0x3d2a1e, roughness: 0.6 }),
  terracotta: new THREE.MeshStandardMaterial({ color: 0xb5623f, roughness: 0.8 }),
  treat: new THREE.MeshStandardMaterial({ color: 0xf0905a, roughness: 0.55 }),
  soil: new THREE.MeshStandardMaterial({ color: 0x3b2a1c, roughness: 1 }),
  leaf: new THREE.MeshStandardMaterial({ color: 0x4d7a3a, roughness: 0.7 }),
  leaf2: new THREE.MeshStandardMaterial({ color: 0x6a9a48, roughness: 0.7 }),
  shade: new THREE.MeshStandardMaterial({ color: 0xf5e2c0, roughness: 0.9, side: THREE.DoubleSide, emissive: 0xffb877, emissiveIntensity: 0.25 }),
  bulb: new THREE.MeshStandardMaterial({ color: 0xfff1d6, emissive: 0xffd9a0, emissiveIntensity: 3 }),
  rug: new THREE.MeshStandardMaterial({ map: canvasTexture(768, 480, (g, w, h) => {
    g.fillStyle = '#d9b48f'; g.fillRect(0, 0, w, h);
    g.strokeStyle = '#a2553f'; g.lineWidth = 26; g.strokeRect(24, 24, w - 48, h - 48);
    g.strokeStyle = '#7a4a34'; g.lineWidth = 6; g.strokeRect(62, 62, w - 124, h - 124);
    g.fillStyle = 'rgba(162,85,63,0.35)';
    for (let i = 0; i < 9; i++) for (let j = 0; j < 5; j++) { g.beginPath(); g.arc(120 + i * 66, 120 + j * 60, 9, 0, Math.PI * 2); g.fill(); }
  }), roughness: 1 }),
};

// ------------------------------------------------------------------ furniture
floorFX(MAT.floor); swayFX(MAT.leaf); swayFX(MAT.leaf2);
const room = new THREE.Group();
scene.add(room);
const draco0 = new DRACOLoader().setDecoderPath(`https://cdn.jsdelivr.net/npm/three@${THREE_VER}/examples/jsm/libs/draco/gltf/`);
let roomW = 0;
const box = (w, h, d, mat, r = 0.04) => { const m = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, r), mat); m.castShadow = m.receiveShadow = true; return m; };
const place = (m, x, y, z, ry = 0) => { m.position.set(x, y, z); m.rotation.y = ry; room.add(m); return m; };

function couch(x, z) {
  const g = new THREE.Group();
  const add = (m, px, py, pz, rx = 0) => { m.position.set(px, py, pz); m.rotation.x = rx; g.add(m); return m; };
  add(box(6.4, 0.5, 2.3, MAT.fabric, 0.12), 0, 0.5, 0);
  add(box(6.4, 1.15, 0.5, MAT.fabric, 0.12), 0, 1.15, -1.0, -0.12);
  for (const s of [-1, 1]) add(box(0.55, 0.95, 2.3, MAT.fabric, 0.14), s * 3.2, 0.72, 0);
  for (const cx of [-1.95, 0, 1.95]) add(box(1.85, 0.22, 1.9, MAT.fabric, 0.09), cx, 0.85, 0.12);
  for (const cx of [-1.6, 1.6]) add(box(2.6, 0.9, 0.34, MAT.fabric, 0.12), cx, 1.35, -0.72, -0.12);
  const p1 = add(box(0.9, 0.9, 0.28, MAT.mustard, 0.1), -2.55, 1.3, -0.62, -0.12); p1.rotation.z = 0.25;
  const p2 = add(box(0.9, 0.9, 0.28, MAT.cream, 0.1), 2.6, 1.3, -0.62, -0.12); p2.rotation.z = -0.2;
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.08, 0.3, 10), MAT.walnut);
    leg.castShadow = true; add(leg, sx * 2.9, 0.14, sz * 0.9); leg.rotation.z = sx * 0.15; leg.rotation.x = -sz * 0.12;
  }
  g.position.set(x, 0, z);
  room.add(g);
}

function bookshelf(x, z) {  // walnut: two sides, back, four boards; three shelf tops at 0.16, 1.96, 3.76
  const g = new THREE.Group();
  const s = (w, h, d, px, py, pz) => { const m = box(w, h, d, MAT.walnut, 0.02); m.position.set(px, py, pz); g.add(m); };
  s(0.12, 5.6, 1.5, -1.54, 2.8, 0); s(0.12, 5.6, 1.5, 1.54, 2.8, 0); s(3.2, 5.6, 0.08, 0, 2.8, -0.71);
  for (const y of [0.1, 1.9, 3.7, 5.55]) s(3.0, 0.12, 1.5, 0, y, 0);
  g.position.set(x, 0, z);
  room.add(g);
  return { tops: [0.16, 1.96, 3.76].map((y) => [x, y, z]) };
}

function cubby(x, y, z, cols = 1, rows = 2) {  // oak grid of open 1.5-unit cubes
  const g = new THREE.Group();
  const s = (w, h, d, px, py, pz) => { const m = box(w, h, d, MAT.oak, 0.02); m.position.set(px, py, pz); g.add(m); };
  const W = cols * 1.5, H = rows * 1.5;
  for (let r = 0; r <= rows; r++) s(W + 0.1, 0.1, 1.4, 0, r * 1.5, 0);
  for (let c = 0; c <= cols; c++) s(0.1, H + 0.1, 1.4, -W / 2 + c * 1.5, H / 2, 0);
  s(W + 0.1, H + 0.1, 0.06, 0, H / 2, -0.67);
  g.position.set(x, y, z);
  room.add(g);
  const cells = [];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) cells.push([x - W / 2 + 0.75 + c * 1.5, y + r * 1.5 + 0.06, z]);
  return { cells };
}

function archShape(w, h, r, inner) {
  const s = new THREE.Shape();
  s.moveTo(-w / 2, 0); s.lineTo(w / 2, 0); s.lineTo(w / 2, h); s.absarc(0, h, w / 2, 0, Math.PI, false); s.lineTo(-w / 2, 0);
  if (inner) {
    const hole = new THREE.Path();
    hole.moveTo(-w / 2 + r, r); hole.lineTo(w / 2 - r, r); hole.lineTo(w / 2 - r, h); hole.absarc(0, h, w / 2 - r, 0, Math.PI, false); hole.lineTo(-w / 2 + r, r);
    s.holes.push(hole);
  }
  return s;
}
function archNiche(x, z) {  // sage: an arched frame with a back panel and a middle shelf
  const g = new THREE.Group();
  const frame = new THREE.Mesh(new THREE.ExtrudeGeometry(archShape(2.5, 3.0, 0.14, true), { depth: 1.5, bevelEnabled: false }), MAT.sage);
  frame.castShadow = frame.receiveShadow = true;
  frame.position.z = -0.75;
  g.add(frame);
  const back = new THREE.Mesh(new THREE.ExtrudeGeometry(archShape(2.5, 3.0, 0, false), { depth: 0.06, bevelEnabled: false }), MAT.sage);
  back.receiveShadow = true; back.position.z = -0.78; g.add(back);
  const shelf = box(2.24, 0.1, 1.4, MAT.sage, 0.02); shelf.position.set(0, 2.05, 0); g.add(shelf);
  g.position.set(x, 0, z);
  room.add(g);
  return { tops: [[x, 0.14, z], [x, 2.1, z]] };
}

function floating(x, z) {  // white lacquer slabs, staggered
  const tops = [];
  for (const [y, dx, w] of [[2.6, 0.2, 2.8], [4.0, -0.3, 2.4], [5.4, 0.35, 2.0]]) {
    const m = box(w, 0.12, 1.4, MAT.lacquer, 0.03); m.position.set(x + dx, y, z); room.add(m);
    tops.push([x + dx, y + 0.06, z]);
  }
  return { tops };
}

function hexagon(x, y, z) {  // brass hexagonal frame
  const hex = (r) => { const s = new THREE.Shape(); for (let i = 0; i < 6; i++) { const a = i * Math.PI / 3 + Math.PI / 6; const p = [r * Math.cos(a), r * Math.sin(a)]; i ? s.lineTo(...p) : s.moveTo(...p); } s.closePath(); return s; };
  const s = hex(1.4); const h = hex(1.2); s.holes.push(h);
  const m = new THREE.Mesh(new THREE.ExtrudeGeometry(s, { depth: 1.3, bevelEnabled: false }), MAT.brass);
  m.castShadow = m.receiveShadow = true;
  m.position.set(x, y, z - 0.65);
  room.add(m);
  return { top: [x, y - 1.2 * Math.cos(Math.PI / 6) + 0.02, z] };  // the flat bottom edge of the hexagon
}

function sideTable(x, z) {
  const top = new THREE.Mesh(new THREE.CylinderGeometry(0.85, 0.85, 0.08, 32), MAT.walnut); top.castShadow = top.receiveShadow = true; place(top, x, 0.96, z);
  for (let i = 0; i < 3; i++) {
    const a = i * Math.PI * 2 / 3;
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.06, 0.95, 8), MAT.walnut); leg.castShadow = true;
    place(leg, x + 0.5 * Math.cos(a), 0.48, z + 0.5 * Math.sin(a));
    leg.rotation.z = 0.18 * Math.cos(a); leg.rotation.x = -0.18 * Math.sin(a);
  }
  return [x, 1.0, z];
}

function plant(x, z) {
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.42, 0.8, 24), MAT.terracotta); pot.castShadow = pot.receiveShadow = true; place(pot, x, 0.4, z);
  place(new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.06, 24), MAT.soil), x, 0.78, z);
  for (let i = 0; i < 9; i++) {
    const a = i * 2.4, r = 0.25 + (i % 3) * 0.12;
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.5, 12, 8), i % 2 ? MAT.leaf : MAT.leaf2);
    leaf.scale.set(0.22, 0.9 + (i % 3) * 0.3, 0.5); leaf.castShadow = true;
    place(leaf, x + r * Math.cos(a), 1.35 + (i % 3) * 0.25, z + r * Math.sin(a), a);
    leaf.rotation.z = 0.35 * Math.cos(a); leaf.rotation.x = -0.35 * Math.sin(a);
  }
}

const LAMP = { center: new THREE.Vector3(), radius: 1.4, uOn: { value: 1 } };   // uOn: the lamp is on by day, off at night
const NIGHTLIGHTS = [];   // { light, mats: [material...], max, em }
function nightlight(x, y, z, color, max, mesh, em = 3.0) {
  const light = new THREE.PointLight(color, 0, 8, 2);
  light.position.set(x, y + 0.35, z);
  room.add(light);
  const mats = [];
  if (mesh) { mesh.traverse((o) => { if (o.isMesh && o.material.emissive) { o.material.emissiveIntensity = 0; mats.push(o.material); } }); room.add(mesh); }
  NIGHTLIGHTS.push({ light, mats, max, em });
}
function glowMat(color, emissive) { return new THREE.MeshStandardMaterial({ color, emissive, emissiveIntensity: 0, roughness: 0.6 }); }
function mushroomLamp(x, y, z) {
  const g = new THREE.Group();
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.12, 0.36, 12), MAT.cream); stem.position.y = 0.18; stem.castShadow = true; g.add(stem);
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.34, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2), glowMat(0xffc6a0, 0xff9a5a)); cap.position.y = 0.34; cap.scale.y = 0.7; g.add(cap);
  g.position.set(x, y, z);
  return g;
}
function candleJar(x, y, z) {
  const g = new THREE.Group();
  const jar = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.13, 0.3, 16, 1, true), new THREE.MeshPhysicalMaterial({ color: 0xfff1dc, transparent: true, opacity: 0.35, roughness: 0.1, side: THREE.DoubleSide, depthWrite: false })); jar.position.y = 0.15; g.add(jar);
  const wax = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.16, 16), glowMat(0xfff0d0, 0xffb060)); wax.position.y = 0.08; g.add(wax);
  const flame = new THREE.Mesh(new THREE.SphereGeometry(0.045, 10, 8), glowMat(0xfff4c0, 0xffd070)); flame.position.y = 0.24; flame.scale.y = 1.6; g.add(flame);
  g.position.set(x, y, z);
  return g;
}
function starLamp(x, y, z) {
  const m = new THREE.Mesh(new THREE.OctahedronGeometry(0.3, 0), glowMat(0xfff3c4, 0xffe08a)); m.position.set(x, y + 0.3, z); m.rotation.y = 0.4; m.castShadow = true;
  return m;
}
function saltLamp(x, y, z) {
  const g = new THREE.Group();
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.32, 0.12, 12), MAT.trim); base.position.y = 0.06; g.add(base);
  const rock = new THREE.Mesh(new THREE.DodecahedronGeometry(0.38, 0), glowMat(0xffa070, 0xff7a44)); rock.position.y = 0.48; rock.scale.set(0.9, 1.15, 0.9); rock.castShadow = true; g.add(rock);
  g.position.set(x, y, z);
  return g;
}

function floorLamp(x, z) {
  LAMP.center.set(x, 4.9, z);
  place(new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.06, 24), MAT.brass), x, 0.03, z);
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 5.2, 8), MAT.brass); pole.castShadow = true; place(pole, x, 2.65, z);
  place(new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.8, 0.9, 32, 1, true), MAT.shade), x, 5.4, z);
  place(new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 8), MAT.bulb), x, 5.35, z);
  lamp.position.set(x, 5.3, z);
  lampCone(x, z);
}
function lampCone(x, z) {   // a soft volumetric cone of warm light from the shade to the floor, with drifting dust
  const h = 5.0;
  const cone = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 2.1, h, 40, 1, true), new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    uniforms: { uOn: LAMP.uOn, uTime: FX.time, uColor: { value: new THREE.Color(0xffc98a) } },
    vertexShader: 'varying vec2 vUv; varying vec3 vN; varying vec3 vV; void main() { vUv = uv; vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = -mv.xyz; gl_Position = projectionMatrix * mv; }',
    fragmentShader: `uniform float uOn; uniform float uTime; uniform vec3 uColor; varying vec2 vUv; varying vec3 vN; varying vec3 vV;
      void main() {
        float rim = abs(dot(normalize(vN), normalize(vV)));                        // thin where the cone is seen edge-on
        float a = pow(vUv.y, 1.6) * smoothstep(0.0, 0.7, rim) * (0.95 + 0.05 * sin(uTime * 9.0 + vUv.y * 20.0)) * 0.13 * uOn;
        gl_FragColor = vec4(uColor * a, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  }));
  cone.position.set(x, h / 2, z); cone.renderOrder = 5; room.add(cone);
  const n = 70, pos = new Float32Array(n * 3), seed = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const y = rand(0.3, h - 0.3), r = THREE.MathUtils.lerp(2.0, 0.55, y / h) * Math.sqrt(Math.random()), a = Math.random() * 6.283;
    pos.set([x + r * Math.cos(a), y, z + r * Math.sin(a)], i * 3); seed[i] = Math.random() * 100;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('seed', new THREE.BufferAttribute(seed, 1));
  const motes = new THREE.Points(g, new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { uOn: LAMP.uOn, uTime: FX.time },
    vertexShader: `attribute float seed; uniform float uTime; varying float vS;
      void main() { vS = seed; vec3 p = position + vec3(sin(uTime * 0.37 + seed) * 0.16, sin(uTime * 0.23 + seed * 2.0) * 0.22, cos(uTime * 0.31 + seed * 3.0) * 0.16);
        vec4 mv = modelViewMatrix * vec4(p, 1.0); gl_PointSize = 120.0 / -mv.z; gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform float uOn; uniform float uTime; varying float vS;
      void main() { float d = length(gl_PointCoord - 0.5); float a = smoothstep(0.5, 0.12, d) * (0.35 + 0.3 * sin(uTime * 1.7 + vS)) * 0.55 * uOn;
        gl_FragColor = vec4(vec3(1.0, 0.86, 0.66) * a, 1.0); }`,
  }));
  motes.frustumCulled = false; room.add(motes);
}

const photo = new THREE.TextureLoader().load('cards_photo.jpg');
photo.colorSpace = THREE.SRGBColorSpace;
photo.anisotropy = 8;
function pictureFrame(x, y, z) {  // the original cards, framed in walnut with a cream mat
  const g = new THREE.Group();
  const ph = 6.4, pw = ph * 0.75;
  const frame = box(pw + 0.5, ph + 0.5, 0.14, MAT.walnut, 0.03); frame.position.z = 0.07; g.add(frame);
  const mat = new THREE.Mesh(new THREE.PlaneGeometry(pw + 0.28, ph + 0.28), MAT.cream); mat.position.z = 0.145; g.add(mat);
  const pic = new THREE.Mesh(new THREE.PlaneGeometry(pw, ph), new THREE.MeshStandardMaterial({ map: photo, roughness: 0.6 })); pic.position.z = 0.15; g.add(pic);
  g.position.set(x, y, z);
  room.add(g);
}

// ---- the sign above everything: extruded letters from Blender, lit from both sides
const SIGN = { mesh: null, width: 1, group: null };
new GLTFLoader().setDRACOLoader(draco0).load(`models/sign.glb?b=${BUILD}`, (gltf) => {
  const mesh = gltf.scene.getObjectByProperty('isMesh', true);
  mesh.material = new THREE.MeshPhysicalMaterial({ color: 0xf3e2bf, roughness: 0.38, clearcoat: 0.5, clearcoatRoughness: 0.2, emissive: 0xffd9a8, emissiveIntensity: 0.03 });
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  const box = new THREE.Box3().setFromObject(gltf.scene);
  SIGN.width = box.max.x - box.min.x;
  SIGN.mesh = gltf.scene;
  if (roomW) placeSign(roomW);
});
const signLights = [];
function placeSign(W) {
  if (!SIGN.mesh) return;
  if (SIGN.group) { room.remove(SIGN.group); SIGN.group = null; }
  const g = new THREE.Group();
  const scale = Math.min(4.7, (W - 5) / SIGN.width);        // ~3-unit letters; wide screens cap here
  SIGN.mesh.scale.setScalar(scale);
  SIGN.mesh.position.set(0, 0, 0);
  g.add(SIGN.mesh);
  const half = SIGN.width * scale / 2;
  // two coloured spots from the sides, with small brass fixtures so the light has a source
  signLights.length = 0;
  for (const [sx, color, power] of [[-1, 0xffa552, 68], [1, 0x35d4c8, 112]]) {   // teal needs more push against terracotta
    const spot = new THREE.SpotLight(color, power, 26, 0.5, 0.75, 1.3);
    spot.userData.base = power;
    signLights.push(spot);
    spot.position.set(sx * (half + 2.6), 1.6, 3.4);
    spot.target.position.set(sx * half * 0.55, 0, 0);   // each colour owns its half; they blend in the middle
    spot.castShadow = true;
    spot.shadow.mapSize.set(1024, 1024);
    spot.shadow.bias = -0.0005;
    g.add(spot, spot.target);
    const fixture = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.3, 0.55, 20, 1, true), MAT.brass);
    fixture.position.copy(spot.position);
    fixture.lookAt(spot.target.position);
    fixture.rotateX(Math.PI / 2);
    g.add(fixture);
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 3.6, 8), MAT.brass);
    arm.position.set(spot.position.x, spot.position.y, spot.position.z / 2);
    arm.rotation.x = Math.PI / 2;
    g.add(arm);
    const glow = new THREE.Mesh(new THREE.SphereGeometry(0.11, 12, 8), new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: color, emissiveIntensity: 4 }));
    glow.position.copy(spot.position);
    g.add(glow);
  }
  g.position.set(0, 11.0, BACK_Z + 0.36);
  room.add(g);
  SIGN.group = g;
}

function buildRoom(W) {
  while (room.children.length) { const c = room.children.pop(); if (c !== SIGN.group) c.traverse((o) => o.geometry && o.geometry.dispose()); }
  roomW = W;
  const half = W / 2;
  // floor, walls, trim
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(W + 30, 40), MAT.floor); floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; place(floor, 0, 0, BACK_Z + 20);
  MAT.floor.map.repeat.set((W + 30) / 7, 40 / 7);
  const wallU = new THREE.Mesh(new THREE.PlaneGeometry(W + 30, 16), MAT.wallUpper); wallU.receiveShadow = true; place(wallU, 0, 9.4, BACK_Z);
  const wallL = new THREE.Mesh(new THREE.PlaneGeometry(W + 30, 1.4), MAT.wallLower); wallL.receiveShadow = true; place(wallL, 0, 0.7, BACK_Z + 0.005);
  place(box(W + 30, 0.08, 0.06, MAT.trim, 0.01), 0, 1.42, BACK_Z + 0.03);
  place(box(W + 30, 0.18, 0.08, MAT.trim, 0.01), 0, 0.09, BACK_Z + 0.04);
  for (const s of [-1, 1]) {  // side walls, angled a touch inward so they read as walls
    const wall = new THREE.Mesh(new THREE.PlaneGeometry(22, 16), MAT.wallUpper); wall.receiveShadow = true;
    place(wall, s * (half + 0.2), 8, BACK_Z + 11, -s * (Math.PI / 2 - 0.06));
  }
  // furniture
  const couchZ = COUCH_Z;
  couch(0, couchZ);
  pictureFrame(0, 6.0, BACK_Z);
  SIGN.group = null;  // the room was cleared; re-add the sign for this width
  placeSign(W);
  const rug = new THREE.Mesh(new THREE.PlaneGeometry(9.5, 5.6), MAT.rug); rug.rotation.x = -Math.PI / 2; rug.receiveShadow = true; place(rug, 0, 0.012, -3.2);
  const table = sideTable(4.7, couchZ + 0.3);
  const spread = Math.max(0, (W - W_MIN) * 0.18);
  plant(Math.min(half - 1.6, 6.6 + spread), -2.2);
  floorLamp(-Math.min(half - 1.6, 6.9 + spread), -3.3);
  const xL = -half + 0.5, xR = half - 0.5, wallZ = BACK_Z + 0.78;
  const bs = bookshelf(xL + 1.6, wallZ);
  const cb = cubby(xL + 3.2 + 0.6 + 0.8, 2.9, wallZ);
  const an = archNiche(xR - 1.25, wallZ);
  const fl = floating(xR - 2.5 - 0.4 - 1.2, wallZ);
  // soft nightlights near the cats: on the bookshelf, the side table, the top floating slab, by the plant, under the couch
  NIGHTLIGHTS.length = 0;
  nightlight(xL + 2.5, 5.62, wallZ + 0.1, 0xffa070, 6, mushroomLamp(xL + 2.5, 5.62, wallZ + 0.1), 2.6);
  nightlight(table[0] + 0.55, 1.0, table[2] - 0.45, 0xffb060, 5, candleJar(table[0] + 0.55, 1.0, table[2] - 0.45), 3.0);
  nightlight(fl.tops[2][0], fl.tops[2][1], fl.tops[2][2], 0xffe08a, 5, starLamp(...fl.tops[2]), 2.4);
  const plantX = Math.min(half - 1.6, 6.6 + spread);
  nightlight(plantX - 1.4, 0, -1.5, 0xff8a50, 6, saltLamp(plantX - 1.4, 0, -1.5), 2.2);
  nightlight(0, 0.15, couchZ + 0.4, 0xffb890, 4, null);
  const hxL = hexagon(xL + 1.6, 7.3, wallZ), hxR = hexagon(xR - 1.25, 6.6, wallZ);
  // shadows follow the room size
  Object.assign(key.shadow.camera, { left: -(half + 8), right: half + 8, top: 16, bottom: -16, near: 1, far: 70 });
  key.shadow.camera.updateProjectionMatrix();
  const sideX = Math.min(half - 2.4, 5.9 + spread);
  return {
    'seat.1': { p: [-1.9, 0.97, couchZ + 0.25], yaw: 8, s: 0.92 }, 'seat.2': { p: [0, 0.97, couchZ + 0.25], yaw: 0, s: 0.95 }, 'seat.3': { p: [1.9, 0.97, couchZ + 0.25], yaw: -8, s: 0.92 },
    'back.1': { p: [-1.1, 1.75, couchZ - 1.0], yaw: 10, s: 0.7 }, 'back.2': { p: [1.3, 1.75, couchZ - 1.0], yaw: -12, s: 0.7 },
    'arm.L': { p: [-3.25, 1.2, couchZ + 0.1], yaw: 18, s: 0.8 }, 'arm.R': { p: [3.25, 1.2, couchZ + 0.1], yaw: -18, s: 0.8 },
    'rug.1': { p: [0.4, 0, -2.4], yaw: -6, s: 1 }, 'rug.2': { p: [-2.7, 0, -3.3], yaw: 22, s: 1 }, 'rug.3': { p: [2.9, 0, -3.0], yaw: -18, s: 1 },
    'side.L': { p: [-sideX, 0, couchZ + 1.6], yaw: 28, s: 1 }, 'side.R': { p: [sideX, 0, couchZ + 1.9], yaw: -35, s: 1 },
    'table': { p: table, yaw: -10, s: 0.8 },
    'shelf.1': { p: bs.tops[2], yaw: 14, s: 0.72 }, 'shelf.2': { p: bs.tops[1], yaw: 6, s: 0.72 }, 'shelf.3': { p: bs.tops[0], yaw: 16, s: 0.72 },
    'cubby.1': { p: cb.cells[1], yaw: 8, s: 0.66 }, 'cubby.2': { p: cb.cells[0], yaw: 12, s: 0.66 },
    'niche': { p: an.tops[0], yaw: -8, s: 0.72 },
    'float.1': { p: fl.tops[1], yaw: -10, s: 0.66 }, 'float.2': { p: fl.tops[0], yaw: -14, s: 0.7 },
    'hex.L': { p: hxL.top, yaw: 10, s: 0.6 }, 'hex.R': { p: hxR.top, yaw: -10, s: 0.6 },
  };
}

// who sits where
const SPOT_OF = {
  LuckyCat: 'seat.2', LargeHearted: 'seat.1', Unimeow: 'seat.3', AngelCat: 'back.1', DevilCat: 'back.2', Accountcat: 'arm.L', HolidayKitty: 'arm.R',
  Mascot: 'rug.1', Stretcher: 'rug.2', BoxTester: 'rug.3', Dozer: 'side.L', InvestigatorOne: 'side.R', Catuccino: 'table',
  Siamese: 'shelf.1', Sphynx: 'shelf.2', Wanderer: 'shelf.3', KittyRoll: 'cubby.1', NorwegianForest: 'cubby.2', Explorer: 'niche',
  DayCat: 'float.1', BumbleCat: 'float.2', ShowOff: 'hex.L', NatureLover: 'hex.R',
};
let spots = {};
const cats = [];
function placeCat(cat) {
  const sp = spots[SPOT_OF[cat.name]];
  if (!sp) return;
  cat.base = { p: [...sp.p], yaw: sp.yaw, s: sp.s };
  cat.root.position.set(...sp.p);
  cat.root.rotation.y = THREE.MathUtils.degToRad(sp.yaw + cat.ownYaw);
  cat.root.scale.setScalar(sp.s);
}

// ------------------------------------------------------------------ responsive camera + room
let fitted = { w: 0, h: 0 };
function fitCamera() {
  const w = window.innerWidth, h = window.innerHeight;
  fitted = { w, h };
  renderer.setSize(w, h);                                      // explicit CSS size: robust to odd embedding
  composer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  const tanH = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * camera.aspect;
  const d = Math.max(D_DEFAULT, W_MIN / (2 * tanH));          // back off until the minimum room fits
  const W = THREE.MathUtils.clamp(2 * d * tanH, W_MIN, W_MAX);  // and let the room grow into wide screens
  controls.minDistance = Math.max(10, d * 0.45);
  controls.maxDistance = d + 12;
  camera.position.set(0.3, 1.9, BACK_Z + d);   // low, at cat eye level
  keepCameraAboveFloor();
  controls.update();
  if (Math.abs(W - roomW) > 0.6) { spots = buildRoom(W); cats.forEach(placeCat); MOOD.dirty = true; }
}
window.addEventListener('resize', fitCamera);
fitCamera();

// ------------------------------------------------------------------ cats
const draco = new DRACOLoader();
draco.setDecoderPath(`https://cdn.jsdelivr.net/npm/three@${THREE_VER}/examples/jsm/libs/draco/gltf/`);
const loader = new GLTFLoader();
loader.setDRACOLoader(draco);
const layout = await (await fetch(`layout.json?b=${BUILD}`)).json();
const names = Object.keys(layout);
let loaded = 0;
for (const name of names) {
  loader.load(`models/${name}.glb?b=${BUILD}`, (gltf) => {
    const root = gltf.scene;
    const fx = makeCatFX();
    root.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true; o.receiveShadow = true; o.frustumCulled = false;
      const m = o.material;
      if (m && (m.transmission > 0 || /bowl$/.test(m.name))) { m.transmission = 0; m.transparent = true; m.opacity = 0.28; m.roughness = 0.05; m.depthWrite = false; }
      else if (m && m.transparent && m.opacity < 1) m.depthWrite = false;
      if (!m) return;
      catFX(m, fx, !m.transparent);               // ripple on everything, fuzz only on the opaque clay
      if (!m.transparent) CAT_MATS.add(m);
    });
    // GLTFLoader strips [ ] . : / from node names (PropertyBinding rules), so 'ear.L' arrives as 'earL'
    const bone = (n) => root.getObjectByName(n) || root.getObjectByName(n.replace(/[\[\]\.:\/\s]/g, ''));
    const cat = {
      name, root, ownYaw: name === 'ShowOff' ? 150 : 0, head: bone('head'), body: bone('body'),
      ears: ['ear.L', 'ear.R'].map(bone).filter(Boolean), tails: ['tail.001', 'tail.002', 'tail.003'].map(bone).filter(Boolean),
      eyes: ['eye.L', 'eye.R'].map(bone).filter(Boolean),
      phase: Math.random() * 100, lag: 0.05 + Math.random() * 0.07, rest: new Map(),
      lookQ: null, bodyQ: null, move: null, lastMove: null,
      blink: { next: rand(1, 5), t: -9 }, twitch: [{ next: rand(1, 6), t: -9 }, { next: rand(1, 6), t: -9 }],
      base: { p: [0, 0, 0], yaw: 0, s: 1 }, fx,
    };
    for (const b of [cat.head, cat.body, ...cat.ears, ...cat.tails, ...cat.eyes]) if (b) cat.rest.set(b, b.quaternion.clone());
    splitEyes(cat);
    if (cat.head) cat.lookQ = cat.head.quaternion.clone();
    if (cat.body) cat.bodyQ = cat.body.quaternion.clone();
    cats.push(cat);
    placeCat(cat);
    scene.add(root);
    loaded += 1;
  }, undefined, (err) => { console.error(name, err); });
}

// ------------------------------------------------------------------ glowing eyes (night)
const EYE_COLOR = { DevilCat: 0xff5a40, Unimeow: 0xe2a6ff, Siamese: 0x6fd6ff, LuckyCat: 0xffe27a, BumbleCat: 0xffd042, Explorer: 0x8fe8ff };
const EYE_DEFAULT = 0xc4ff6e;   // the green-gold of a real tapetum
const EYE_GLOWS = [];           // { mat, sprites }
const haloTexture = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'); const r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.35, 'rgba(255,255,255,0.55)'); r.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = r; g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
})();
function splitEyes(cat) {
  if (!cat.eyes.length) return;
  let mesh = null;
  cat.root.traverse((o) => { if (!mesh && o.isSkinnedMesh && o.skeleton.bones.some((b) => /^eye/.test(b.name))) mesh = o; });
  if (!mesh) return;
  const eyeIdx = new Set(mesh.skeleton.bones.map((b, i) => (/^eye/.test(b.name) ? i : -1)).filter((i) => i >= 0));
  const g = mesh.geometry, si = g.attributes.skinIndex, sw = g.attributes.skinWeight;
  if (!si || !sw) return;
  const n = si.count, isEye = new Uint8Array(n);
  for (let v = 0; v < n; v++) {
    let w = 0;
    for (let k = 0; k < 4; k++) if (eyeIdx.has(si.getComponent(v, k))) w += sw.getComponent(v, k);
    if (w > 0.5) isEye[v] = 1;
  }
  const idx = g.index ? g.index.array : Uint32Array.from({ length: g.attributes.position.count }, (_, i) => i);
  const body = [], eye = [];
  for (let t = 0; t < idx.length; t += 3) {
    const a = idx[t], b = idx[t + 1], c = idx[t + 2];
    (isEye[a] && isEye[b] && isEye[c] ? eye : body).push(a, b, c);
  }
  if (!eye.length) return;
  g.setIndex(new THREE.BufferAttribute(new Uint32Array(body.concat(eye)), 1));
  g.clearGroups();
  g.addGroup(0, body.length, 0);
  g.addGroup(body.length, eye.length, 1);
  const color = EYE_COLOR[cat.name] ?? EYE_DEFAULT;
  const eyeMat = mesh.material.clone();
  eyeMat.emissive = new THREE.Color(color);
  eyeMat.emissiveIntensity = 0;
  catFX(eyeMat, cat.fx, false);   // eyes ripple with the face but stay glossy
  mesh.material = [mesh.material, eyeMat];
  const sprites = cat.eyes.map((bone) => {
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: haloTexture, color, blending: THREE.AdditiveBlending, transparent: true, opacity: 0, depthWrite: false }));
    sp.scale.set(0.36, 0.36, 1);
    sp.visible = false;
    bone.add(sp);
    return sp;
  });
  EYE_GLOWS.push({ mat: eyeMat, sprites });
}

// ------------------------------------------------------------------ the move palette
// Each move maps u in [0,1] onto pose offsets; the frame loop adds them on top of spot, look and idle.
const bump = (u) => Math.sin(Math.PI * u);
const env = (u, k = 4) => Math.min(1, u * k, (1 - u) * k);            // ease in, hold, ease out
const decay = (u, k) => Math.exp(-k * u);
const T = Math.PI * 2;
const MOVES = {
  hop:      { d: 0.65, f: (u, o) => { o.y = 0.9 * bump(u); o.bodySy = 1 + 0.2 * Math.sin(T * u); o.earPitch = -0.3 * bump(u); o.tailPitch = 0.4 * bump(u); } },
  doubleHop:{ d: 1.0,  f: (u, o) => { const v = (u * 2) % 1; o.y = 0.55 * bump(v); o.bodySy = 1 + 0.15 * Math.sin(T * v); o.earPitch = -0.2 * bump(v); } },
  spin:     { d: 0.8,  f: (u, o) => { const e = u * u * (3 - 2 * u); o.yaw = T * e; o.y = 0.5 * bump(u); o.bodySy = 1 + 0.12 * bump(u); o.tailRoll = 0.6 * bump(u); } },
  wiggle:   { d: 0.9,  f: (u, o) => { const w = Math.sin(T * 4 * u) * decay(u, 2); o.bodyRoll = 0.22 * w; o.headRoll = -0.45 * w; o.tailRoll = 0.5 * w; } },
  stretch:  { d: 1.5,  f: (u, o) => { const e = env(u, 3); o.bodySy = 1 + 0.28 * e; o.bodySxz = 1 - 0.08 * e; o.headPitch = 0.35 * e; o.earPitch = -0.4 * e; o.eye = 1 - 0.95 * e; o.tailPitch = 0.5 * e; } },
  shake:    { d: 0.8,  f: (u, o) => { o.headYaw = 0.55 * Math.sin(T * 3 * u) * decay(u, 1.5); o.earRoll = 0.2 * Math.sin(T * 3 * u); } },
  nod:      { d: 0.9,  f: (u, o) => { o.headPitch = 0.3 * Math.sin(T * 3 * u) * decay(u, 1); } },
  surprise: { d: 0.8,  f: (u, o) => { const sq = Math.min(u / 0.2, 1) * (u < 0.2 ? 1 : 0), st = u >= 0.2 ? env((u - 0.2) / 0.8, 3) : 0;
                                       o.bodySy = 1 - 0.22 * sq + 0.25 * st; o.bodySxz = 1 + 0.1 * sq - 0.06 * st; o.earPitch = 0.55 * st; o.eye = 1 + 0.5 * st; o.y = 0.5 * bump(Math.max(0, (u - 0.2) / 0.6)); o.tailPitch = 0.7 * st; } },
  sleepy:   { d: 2.4,  f: (u, o) => { const e = env(u, 3); o.eye = 1 - 0.95 * e; o.headPitch = 0.45 * e; o.bodySy = 1 - 0.06 * e; o.earPitch = -0.35 * e; o.headYaw = 0.25 * Math.sin(40 * u) * Math.max(0, (u - 0.85) / 0.15); } },
  dance:    { d: 1.7,  f: (u, o) => { o.y = 0.45 * Math.abs(Math.sin(T * 2 * u)); o.bodyRoll = 0.2 * Math.sin(T * 2 * u); o.headRoll = -0.35 * Math.sin(T * 2 * u); o.tailRoll = 0.6 * Math.sin(T * 4 * u); o.earPitch = 0.25 * Math.sin(T * 4 * u); o.bodySy = 1 + 0.08 * Math.abs(Math.sin(T * 2 * u)); } },
  bow:      { d: 1.1,  f: (u, o) => { const e = bump(u); o.bodyPitch = 0.4 * e; o.headPitch = 0.3 * e; o.earPitch = -0.2 * e; o.eye = 1 - 0.6 * e; } },
};
const MOVE_NAMES = Object.keys(MOVES);
function play(cat, name) {
  if (cat.trip) return null;
  if (!name) {
    const pool = MOVE_NAMES.filter((n) => n !== cat.lastMove);
    name = pool[Math.floor(Math.random() * pool.length)];
  }
  cat.move = { def: MOVES[name], name, t0: clock.elapsedTime };
  cat.lastMove = name;
  return name;
}

// ------------------------------------------------------------------ pointer: cursor target, hover, press
const pointer = new THREE.Vector2(0, 0.15);
const raycaster = new THREE.Raycaster();
const lookPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), -4);
const target = new THREE.Vector3(0, 3, 4), targetSmooth = target.clone();
const press = { x: 0, y: 0, down: false, id: null, count: 0, multi: false, pet: null, petT: 0, petX: 0, petY: 0 };
const touch = { active: false, last: -1e9 };                                  // finger state: look-back timer when it lifts
const _sphere = new THREE.Sphere(), _hit = new THREE.Vector3();
function pickLamp(clientX, clientY, fat = false) {
  const ndc = new THREE.Vector2((clientX / window.innerWidth) * 2 - 1, -(clientY / window.innerHeight) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  _sphere.center.copy(LAMP.center);
  _sphere.radius = LAMP.radius * (fat ? 1.4 : 1);
  return !!raycaster.ray.intersectSphere(_sphere, _hit);
}
function pick(clientX, clientY, fat = false) {
  const ndc = new THREE.Vector2((clientX / window.innerWidth) * 2 - 1, -(clientY / window.innerHeight) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  let best = null, bestD = Infinity;
  for (const cat of cats) {   // proxy spheres: far cheaper than raycasting skinned meshes
    const s = cat.base.s;
    _sphere.center.set(cat.root.position.x, cat.root.position.y + 0.8 * s, cat.root.position.z);
    _sphere.radius = (fat ? 1.35 : 1.05) * s;                                  // fingers get a bigger target than a cursor
    if (raycaster.ray.intersectSphere(_sphere, _hit)) { const d = _hit.distanceTo(camera.position); if (d < bestD) { bestD = d; best = cat; } }
  }
  return best;
}
function petAt(cat, clientX, clientY) {   // a press or stroke on a cat: dent + ring in its material, from the point under the finger
  const ndc = new THREE.Vector2((clientX / window.innerWidth) * 2 - 1, -(clientY / window.innerHeight) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const s = cat.base.s, R = 1.05 * s;
  const c = _sphere.center.set(cat.root.position.x, cat.root.position.y + 0.8 * s, cat.root.position.z);
  _sphere.radius = R;
  const p = raycaster.ray.closestPointToPoint(c, _hit);
  if (p.distanceTo(c) > R * 1.25) return false;                                // slid off the cat
  if (!raycaster.ray.intersectSphere(_sphere, p)) p.copy(_hit).sub(c).setLength(R).add(c);   // grazing: snap to the surface
  cat.root.worldToLocal(p);
  cat.fx.uTouch.value.copy(p); cat.fx.t0 = FX.time.value; cat.fx.uTouchT.value = 0; cat.fx.uTouchAmp.value = 1;
  return true;
}
function onPointer(e) {
  if (e.pointerType === 'touch' && !e.isPrimary) return;                      // the second finger of a pinch does not steer the look
  pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
  pointer.y = -(e.clientY / window.innerHeight) * 2 + 1;
  if (press.down && press.pet) {                                               // stroking: a new ripple every so often along the way
    const now = performance.now();
    if (now - press.petT > 90 && Math.hypot(e.clientX - press.petX, e.clientY - press.petY) > 6) { press.petT = now; press.petX = e.clientX; press.petY = e.clientY; petAt(press.pet, e.clientX, e.clientY); }
  }
  if (e.pointerType === 'touch') { touch.last = performance.now(); return; }
  touch.last = -1e9;                                                           // a mouse is steering again: no look-back
  canvas.style.cursor = (pickLamp(e.clientX, e.clientY) || pick(e.clientX, e.clientY)) ? 'pointer' : 'default';
}
window.addEventListener('pointermove', onPointer);
window.addEventListener('pointerdown', (e) => {
  if (e.isPrimary) press.count = 0;                                            // a new gesture: forget any finger we lost track of
  press.count++;
  if (press.count > 1) { press.multi = true; return; }                         // pinch: never a tap
  press.x = e.clientX; press.y = e.clientY; press.down = true; press.multi = false; press.id = e.pointerId;
  if (e.pointerType === 'touch') { touch.active = true; onPointer(e); }        // the cats look at the finger the moment it lands
  const held = pick(e.clientX, e.clientY, e.pointerType === 'touch');
  if (held) { press.pet = held; press.petT = performance.now(); press.petX = e.clientX; press.petY = e.clientY; controls.enableRotate = false; petAt(held, e.clientX, e.clientY); }   // a drag that starts on a cat pets it instead of orbiting
});
function endPress(e) {
  press.count = Math.max(0, press.count - 1);
  if (press.pet && (e.pointerId === press.id || e.type === 'pointercancel')) { press.pet = null; controls.enableRotate = true; }
  if (e.pointerType === 'touch') { touch.last = performance.now(); if (press.count === 0) touch.active = false; }
  if (!press.down || e.pointerId !== press.id) return;
  press.down = false;
  if (e.type === 'pointercancel' || press.multi) return;
  const fat = e.pointerType === 'touch';
  if (Math.hypot(e.clientX - press.x, e.clientY - press.y) > (fat ? 12 : 6)) return;   // that was an orbit drag
  const now = performance.now();
  const isDouble = now - lastTap.t < 420 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < (fat ? 48 : 30);
  lastTap.t = now; lastTap.x = e.clientX; lastTap.y = e.clientY;
  if (pickLamp(e.clientX, e.clientY, fat)) { toggleNight(); return; }
  const cat = pick(e.clientX, e.clientY, fat);
  if (cat) { play(cat); meow(cat); return; }
  if (isDouble) { const pt = floorPoint(e.clientX, e.clientY); if (pt) { dropTreat(pt); lastTap.t = 0; } }
}
window.addEventListener('pointerup', endPress);
window.addEventListener('pointercancel', endPress);
// Safari on iPad: no page pinch-zoom, no scroll bounce, no long-press menu on the scene
document.addEventListener('gesturestart', (e) => e.preventDefault(), { passive: false });
canvas.addEventListener('touchmove', (e) => e.preventDefault(), { passive: false });
canvas.addEventListener('contextmenu', (e) => e.preventDefault());

// ------------------------------------------------------------------ treats: double-press the floor, a treat drops, a cat comes to eat it
const TRIPPERS = ['Mascot', 'BoxTester', 'Stretcher', 'LuckyCat', 'Unimeow', 'LargeHearted'];
const floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const RIPPLES = [], TREATS = [];
const lastTap = { t: 0, x: 0, y: 0 };
const TREAT_REST_Y = 0.12, GRAVITY = 22;
function floorPoint(clientX, clientY) {
  const ndc = new THREE.Vector2((clientX / window.innerWidth) * 2 - 1, -(clientY / window.innerHeight) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const pt = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(floorPlane, pt)) return null;
  if (Math.abs(pt.x) > roomW / 2 - 1.2 || pt.z < BACK_Z + 1 || pt.z > 16) return null;
  if (pt.z < COUCH_Z + 1.7 && Math.abs(pt.x) < 4.3) pt.z = COUCH_Z + 1.8;   // not inside the couch
  return pt;
}
function ripple(pt, color = 0xfff1dc) {
  floorRipple(pt.x, pt.z, 1.0);
  if (color === 0xfff1dc) return;   // plain ripples live in the floor shader; coloured rings are dust
  const m = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.3, 40), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85, depthWrite: false }));
  m.rotation.x = -Math.PI / 2;
  m.position.set(pt.x, 0.02, pt.z);
  scene.add(m);
  RIPPLES.push({ m, t: 0 });
}
function makeTreat() {   // a little fish biscuit
  const g = new THREE.Group();
  const body = new THREE.Mesh(new THREE.SphereGeometry(0.22, 16, 12), MAT.treat); body.scale.set(1.3, 0.55, 0.8); g.add(body);
  const tail = new THREE.Mesh(new THREE.ConeGeometry(0.15, 0.24, 3), MAT.treat); tail.rotation.z = Math.PI / 2; tail.position.x = -0.33; tail.scale.set(1, 1, 0.45); g.add(tail);
  const eye = new THREE.Mesh(new THREE.SphereGeometry(0.035, 8, 6), MAT.trim); eye.position.set(0.15, 0.07, 0.13); g.add(eye);
  g.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  return g;
}
function dropTreat(point) {
  const mesh = makeTreat();
  mesh.position.set(point.x, 8.5 + Math.random() * 1.5, point.z);
  mesh.rotation.set(Math.random() * 6, Math.random() * 6, Math.random() * 6);
  scene.add(mesh);
  const treat = { mesh, x: point.x, z: point.z, vy: 0, spin: new THREE.Vector3(rand(-5, 5), rand(-5, 5), rand(-5, 5)), settled: false, claimed: null, eaten: false, restYaw: Math.random() * 6.28 };
  TREATS.push(treat);
  assignTreats();
  return treat;
}
function updateTreat(tr, dt) {
  const m = tr.mesh;
  if (tr.eaten) return;
  if (!tr.settled) {
    tr.vy -= GRAVITY * dt;
    m.position.y += tr.vy * dt;
    m.rotation.x += tr.spin.x * dt; m.rotation.y += tr.spin.y * dt; m.rotation.z += tr.spin.z * dt;
    if (m.position.y <= TREAT_REST_Y) {
      m.position.y = TREAT_REST_Y;
      tr.bounces = (tr.bounces || 0) + 1;
      thud(Math.abs(tr.vy), m.position.x);                 // every impact sounds, softer and duller as the bounces die
      impact(m.position, tr.bounces === 1 ? 1.0 : 0.25);   // the first hit shakes the room, later bounces just tick
      tr.vy = -tr.vy * 0.42;
      tr.spin.multiplyScalar(0.45);
      if (Math.abs(tr.vy) < 1.2) { tr.settled = true; tr.vy = 0; ripple(new THREE.Vector3(tr.x, 0, tr.z)); }
    }
  } else {   // ease flat
    m.rotation.x += (0 - m.rotation.x) * Math.min(1, dt * 8);
    m.rotation.z += (0 - m.rotation.z) * Math.min(1, dt * 8);
    m.rotation.y += (tr.restYaw - m.rotation.y) * Math.min(1, dt * 8);
  }
}
function removeTreat(tr) {
  scene.remove(tr.mesh);
  tr.mesh.traverse((o) => o.geometry && o.geometry.dispose());
  const i = TREATS.indexOf(tr);
  if (i >= 0) TREATS.splice(i, 1);
}
function crunch() {   // three short filtered noise bursts
  if (!AUDIO.ctx || AUDIO.muted) return;
  const ctx = AUDIO.ctx, len = Math.floor(ctx.sampleRate * 0.07);
  const buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2);
  for (let k = 0; k < 3; k++) {
    const src = ctx.createBufferSource(); src.buffer = buf;
    const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 1500 + k * 400; bp.Q.value = 0.8;
    const g = ctx.createGain(); g.gain.value = 0.35;
    src.connect(bp); bp.connect(g); g.connect(AUDIO.sfx);
    src.start(ctx.currentTime + 0.05 + k * 0.17);
  }
}
function thud(speed, x = 0) {   // a biscuit hitting the boards: a pitched thump plus a click, both scaled by impact speed
  if (!AUDIO.ctx || AUDIO.muted || speed < 0.6) return;
  const ctx = AUDIO.ctx, t0 = ctx.currentTime, v = THREE.MathUtils.clamp(speed / 20, 0, 1);   // 20 units/s: the drop from the ceiling
  const out = ctx.createGain(); out.gain.value = 1;
  let dest = AUDIO.sfx;
  if (ctx.createStereoPanner) { const pan = ctx.createStereoPanner(); pan.pan.value = THREE.MathUtils.clamp(x / 9, -0.8, 0.8); pan.connect(AUDIO.sfx); dest = pan; }
  out.connect(dest);
  // body: a triangle thump whose pitch drops; harder hits start lower, ring longer and hit louder
  const f0 = (230 - 70 * v) * (0.95 + Math.random() * 0.1), decay = 0.07 + 0.11 * v;
  const osc = ctx.createOscillator(), og = ctx.createGain();
  osc.type = 'triangle';
  osc.frequency.setValueAtTime(f0 * 1.6, t0); osc.frequency.exponentialRampToValueAtTime(f0 * 0.55, t0 + decay);
  og.gain.setValueAtTime(0.0001, t0); og.gain.exponentialRampToValueAtTime(0.55 * Math.pow(v, 0.8), t0 + 0.004); og.gain.exponentialRampToValueAtTime(0.0001, t0 + decay);
  osc.connect(og); og.connect(out); osc.start(t0); osc.stop(t0 + decay + 0.02);
  // click: a few milliseconds of bandpassed noise, brighter and louder the harder it lands
  const len = Math.floor(ctx.sampleRate * 0.02), buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
  const src = ctx.createBufferSource(), bp = ctx.createBiquadFilter(), cg = ctx.createGain();
  src.buffer = buf; bp.type = 'bandpass'; bp.frequency.value = 1600 + 2600 * v; bp.Q.value = 0.9; cg.gain.value = 0.35 * v;
  src.connect(bp); bp.connect(cg); cg.connect(out); src.start(t0);
}
const lerpAngle = (a, b, t) => a + ((((b - a) % (2 * Math.PI)) + 3 * Math.PI) % (2 * Math.PI) - Math.PI) * t;
const rotY = (v, a) => new THREE.Vector3(v.x * Math.cos(a) + v.z * Math.sin(a), 0, -v.x * Math.sin(a) + v.z * Math.cos(a));
function assignTreats() {
  for (const tr of TREATS) {
    if (tr.claimed || tr.eaten) continue;
    const dist = (c) => Math.hypot(c.base.p[0] - tr.x, c.base.p[2] - tr.z);
    const free = cats.filter((c) => TRIPPERS.includes(c.name) && !c.trip).sort((a, b) => dist(a) - dist(b));
    if (!free.length) return;
    const a = free[0], dA = dist(a);
    let b = null;
    if (free.length > 1) { const dB = dist(free[1]); if (dB < Math.max(dA * 1.5, dA + 1.5) && dB < 9) b = free[1]; }
    tr.claimed = true;
    if (!b) { startTrip(a, tr, null, null); continue; }
    // two contenders: give them separate sides of the treat
    let va = new THREE.Vector3(a.base.p[0] - tr.x, 0, a.base.p[2] - tr.z).normalize();
    let vb = new THREE.Vector3(b.base.p[0] - tr.x, 0, b.base.p[2] - tr.z).normalize();
    const between = Math.acos(THREE.MathUtils.clamp(va.dot(vb), -1, 1));
    if (between < 1.2) {
      const mean = va.clone().add(vb);
      if (mean.lengthSq() < 1e-4) mean.set(0, 0, 1);
      mean.normalize();
      const side = (va.x * mean.z - va.z * mean.x) >= 0 ? 1 : -1;   // keep each on its own side of the mean
      va = rotY(mean, side * 0.78); vb = rotY(mean, -side * 0.78);
    }
    tr.winner = Math.random() < a.base.s / (a.base.s + b.base.s) ? a : b;   // the bigger cat usually wins
    startTrip(a, tr, b, va);
    startTrip(b, tr, a, vb);
  }
}
function startTrip(cat, treat, rival, side) {
  const from = new THREE.Vector3(...cat.base.p);
  const dir = new THREE.Vector3(treat.x - from.x, 0, treat.z - from.z);
  if (dir.length() < 1.2) dir.set(0, 0, 1);
  dir.normalize();
  const away = side ? side.clone() : dir.clone().negate();   // which side of the treat this cat stops on
  const to = new THREE.Vector3(treat.x, 0, treat.z).add(away.multiplyScalar(0.95 * cat.base.s));   // nose on the treat
  const goDist = Math.hypot(to.x - from.x, to.z - from.z);
  const goDir = new THREE.Vector3(to.x - from.x, 0, to.z - from.z).normalize();
  cat.trip = { from, to, treat, rival, dir: goDir, goT: Math.max(0.7, goDist / 3.0), eatT: 2.4, fightT: 2.6, phase: 'watch', t: 0, slow: false,
               yawGo: Math.atan2(goDir.x, goDir.z), yawEat: Math.atan2(treat.x - to.x, treat.z - to.z), yawBack: Math.atan2(from.x - to.x, from.z - to.z), baseYaw: THREE.MathUtils.degToRad(cat.base.yaw + cat.ownYaw), yaw: 0,
               crunched: false, rivalLook: new THREE.Vector3(), phaseShift: Math.random() * 6.28 };
  cat.trip.yaw = cat.trip.baseYaw;
  cat.lookAt = treat.mesh.position;   // eyes on the falling treat
}
// returns the root position and yaw for a travelling cat, and adds hop / eat offsets to O
const _tp = new THREE.Vector3();
function tripPose(cat, dt) {
  const tr = cat.trip, s = cat.base.s, fromY = cat.base.p[1], treat = tr.treat;
  tr.t += dt;
  const hop = (t) => { const ph = t * 2.6 * Math.PI; O.y += Math.abs(Math.sin(ph)) * 0.42; O.bodySy *= 1 + 0.10 * Math.sin(2 * ph); O.earPitch -= 0.2; O.tailPitch += 0.25;
    const n = Math.floor(t * 2.6); if (tr.hopN !== undefined && n > tr.hopN && groundY === 0) floorRipple(_tp.x, _tp.z, 0.45); tr.hopN = n; };   // each landing rings the floor
  let groundY = 0;
  if (tr.phase === 'watch') {                                   // watch it fall, turning toward it
    _tp.copy(tr.from);
    groundY = fromY;
    O.earPitch += 0.3;
    tr.yaw = lerpAngle(tr.baseYaw, tr.yawGo, Math.min(1, tr.t / 0.6));
    if (treat.settled && tr.t > 0.5) { tr.phase = 'go'; tr.t = 0; }
  } else if (tr.phase === 'go') {
    const u = Math.min(1, tr.t / tr.goT);
    _tp.lerpVectors(tr.from, tr.to, u);
    groundY = fromY * (1 - Math.min(1, u / 0.3));              // couch cats hop down during the first stretch
    hop(tr.t);
    tr.yaw = tr.yawGo;
    if (u >= 1) { tr.t = 0; if (tr.rival && tr.rival.trip && tr.rival.trip.treat === treat) tr.phase = 'wait'; else { tr.phase = 'eat'; meow(cat); } }
  } else if (tr.phase === 'wait' || tr.phase === 'fight') {   // squaring up over the treat
    const rival = tr.rival, rt = rival.trip;
    const toRival = new THREE.Vector3(rival.root.position.x - tr.to.x, 0, rival.root.position.z - tr.to.z);
    const yawFight = Math.atan2(toRival.x, toRival.z);
    tr.rivalLook.set(rival.root.position.x, 0.9 * rival.base.s, rival.root.position.z);
    cat.lookAt = tr.rivalLook;
    tr.yaw = lerpAngle(tr.yaw, yawFight, Math.min(1, dt * 6));
    if (tr.phase === 'wait') {
      _tp.copy(tr.to);
      O.earPitch -= 0.35; O.tailPitch += 0.5; O.bodySy *= 0.96;          // crouched, ears flat, tail up
      if (!rt || rt.treat !== treat) { tr.phase = 'eat'; tr.t = 0; cat.lookAt = treat.mesh.position; meow(cat); }
      else if (rt.phase === 'wait') { tr.phase = 'fight'; tr.t = 0; rt.phase = 'fight'; rt.t = 0; meow(cat, 1.15); meow(rival, 1.22); ripple(new THREE.Vector3(treat.x, 0, treat.z), 0xd8b58a); }
    } else {
      const f = tr.t, ph = tr.phaseShift;
      toRival.normalize();
      const lunge = 0.24 * Math.max(0, Math.sin(f * 7 + ph));               // alternating lunges at each other
      _tp.copy(tr.to).addScaledVector(toRival, lunge);
      O.y += 0.14 * Math.abs(Math.sin(f * 9 + ph));
      O.bodyRoll += 0.2 * Math.sin(f * 13 + ph);
      O.bodySy *= 1 + 0.06 * Math.sin(f * 18 + ph);
      O.headYaw += 0.35 * Math.sin(f * 15 + ph);
      O.headPitch -= 0.12;
      O.earPitch -= 0.55;
      O.tailPitch += 0.55 + 0.3 * Math.sin(f * 12 + ph);
      if (Math.floor(f / 0.55) !== Math.floor((f - dt) / 0.55)) ripple(new THREE.Vector3(treat.x + rand(-0.4, 0.4), 0, treat.z + rand(-0.4, 0.4)), 0xd8b58a);
      if (f > 1.3 && f - dt <= 1.3) meow(cat, 1.1);
      if (f >= tr.fightT) {
        tr.t = 0;
        if (treat.winner === cat) { tr.phase = 'eat'; cat.lookAt = treat.mesh.position; meow(cat); }
        else { tr.phase = 'sulk'; cat.lookAt = null; }
      }
    }
  } else if (tr.phase === 'sulk') {                                         // lost: ears back, head down, a slow turn away
    _tp.copy(tr.to);
    const e = env(Math.min(1, tr.t / 1.2), 4);
    O.earPitch -= 0.5 * e; O.headPitch += 0.35 * e; O.bodySy *= 1 - 0.06 * e; O.tailPitch -= 0.3 * e;
    tr.yaw = lerpAngle(tr.yaw, tr.yawBack, Math.min(1, dt * 2.5));
    if (tr.t >= 1.2) { tr.phase = 'back'; tr.t = 0; tr.slow = true; }
  } else if (tr.phase === 'eat') {
    _tp.copy(tr.to);
    const e = env(Math.min(1, tr.t / tr.eatT), 5);
    O.bodyPitch += 0.32 * e;                                    // head down to the treat
    O.headPitch += 0.12 * e + (tr.t < 1.5 ? 0.09 * Math.sin(tr.t * 22) : 0.03 * Math.sin(tr.t * 6));   // chewing, then a satisfied sway
    O.headYaw += 0.06 * Math.sin(tr.t * 11) * e;
    O.earPitch += 0.2 * e + 0.15 * Math.sin(tr.t * 22) * e;
    O.tailPitch += 0.35 * e;
    if (!tr.crunched && tr.t > 0.35) { tr.crunched = true; crunch(); }
    const bite = THREE.MathUtils.clamp((tr.t - 0.4) / 0.9, 0, 1);   // the treat disappears in a few bites
    treat.mesh.scale.setScalar(Math.max(0.001, 1 - Math.floor(bite * 3) / 3));
    if (tr.t > 1.3 && !treat.eaten) { treat.eaten = true; removeTreat(treat); }
    tr.yaw = lerpAngle(tr.yaw, tr.yawEat, Math.min(1, dt * 6));   // after a scuffle, turn from the rival back to the treat
    if (tr.t >= tr.eatT) { tr.phase = 'back'; tr.t = 0; cat.lookAt = null; }
  } else if (tr.phase === 'back') {
    const backT = tr.goT * (tr.slow ? 1.6 : 1);
    const u = Math.min(1, tr.t / backT);
    _tp.lerpVectors(tr.to, tr.from, u);
    groundY = fromY * Math.max(0, (u - 0.7) / 0.3);             // and hop back up at the end
    if (tr.slow) { const ph = tr.t * 1.8 * Math.PI; O.y += Math.abs(Math.sin(ph)) * 0.22; O.earPitch -= 0.4; O.headPitch += 0.15; } else hop(tr.t);
    tr.yaw = lerpAngle(tr.yaw, tr.yawBack, Math.min(1, dt * 5));
    if (u >= 1) { tr.phase = 'settle'; tr.t = 0; }
  } else {
    _tp.copy(tr.from);
    groundY = fromY;
    tr.yaw = lerpAngle(tr.yawBack, tr.baseYaw, Math.min(1, tr.t / 0.4));
    if (tr.t >= 0.4) { cat.trip = null; assignTreats(); }
  }
  return { x: _tp.x, y: groundY, z: _tp.z, yaw: tr.yaw };
}

// ------------------------------------------------------------------ pose assembly
const _q = new THREE.Quaternion(), _qd = new THREE.Quaternion(), _qRoot = new THREE.Quaternion(), _qRootInv = new THREE.Quaternion();
const _qParent = new THREE.Quaternion(), _qParentInv = new THREE.Quaternion(), _qT = new THREE.Quaternion();
const _v = new THREE.Vector3(), _h = new THREE.Vector3(), _e = new THREE.Euler();
const O = {};
function resetOffsets() {
  O.y = 0; O.yaw = 0; O.bodySy = 1; O.bodySxz = 1; O.bodyPitch = 0; O.bodyRoll = 0;
  O.headPitch = 0; O.headYaw = 0; O.headRoll = 0; O.earPitch = 0; O.earRoll = 0; O.eye = 1; O.tailPitch = 0; O.tailRoll = 0;
}

function updateLook(cat, t, dt) {   // where the head and body want to be, before any move offsets
  const head = cat.head;
  if (!head) return;
  head.parent.getWorldQuaternion(_qParent);
  _qParentInv.copy(_qParent).invert();
  _h.copy(head.position);
  head.parent.localToWorld(_h);
  cat.root.getWorldQuaternion(_qRoot);
  _qRootInv.copy(_qRoot).invert();
  _v.copy(t).sub(_h).applyQuaternion(_qRootInv);
  const yaw = THREE.MathUtils.clamp(Math.atan2(_v.x, _v.z), -1.0, 1.0);
  const pitch = THREE.MathUtils.clamp(Math.atan2(_v.y, Math.hypot(_v.x, _v.z)), -0.5, 0.6);
  _qd.setFromEuler(_e.set(-pitch, yaw, 0, 'YXZ'));
  _q.copy(_qRoot).multiply(_qd).multiply(_qRootInv);
  _qT.copy(_qParentInv).multiply(_q).multiply(_qParent).multiply(cat.rest.get(head));
  cat.lookQ.slerp(_qT, 1 - Math.pow(1 - cat.lag, dt * 60));
  if (cat.body) {
    _qd.setFromEuler(_e.set(0, yaw * 0.2, 0, 'YXZ'));
    _q.copy(_qRoot).multiply(_qd).multiply(_qRootInv);
    cat.body.parent.getWorldQuaternion(_qParent);
    _qParentInv.copy(_qParent).invert();
    _qT.copy(_qParentInv).multiply(_q).multiply(_qParent).multiply(cat.rest.get(cat.body));
    cat.bodyQ.slerp(_qT, 1 - Math.pow(1 - cat.lag * 0.5, dt * 60));
  }
}

function applyPose(cat, time) {
  resetOffsets();
  if (cat.move) {                                   // the current move, if any
    const u = (time - cat.move.t0) / cat.move.def.d;
    if (u >= 1) cat.move = null; else cat.move.def.f(u, O);
  }
  const p = cat.phase, s = cat.base.s;
  // root: spot (or the current point of a trip) + hop/spin offsets
  let bx = cat.base.p[0], by = cat.base.p[1], bz = cat.base.p[2], byaw = THREE.MathUtils.degToRad(cat.base.yaw + cat.ownYaw);
  if (cat.trip) { const tp = tripPose(cat, cat._dt); bx = tp.x; by = tp.y; bz = tp.z; byaw = tp.yaw; }
  cat.root.position.set(bx, by + O.y * s, bz);
  cat.root.rotation.y = byaw + O.yaw;
  // body: look yaw, then breathing and move scale, then bow/roll
  if (cat.body) {
    const br = 1 + 0.02 * Math.sin(time * 1.5 + p);
    cat.body.scale.set((1 - (br - 1) * 0.5) * O.bodySxz, br * O.bodySy, (1 - (br - 1) * 0.5) * O.bodySxz);
    _qd.setFromEuler(_e.set(O.bodyPitch, 0, O.bodyRoll));
    cat.body.quaternion.copy(cat.bodyQ).multiply(_qd);
  }
  // head: look, then move offsets
  if (cat.head) {
    _qd.setFromEuler(_e.set(O.headPitch, O.headYaw, O.headRoll));
    cat.head.quaternion.copy(cat.lookQ).multiply(_qd);
  }
  // ears: gentle sway + scheduled flicks + move offsets
  cat.ears.forEach((ear, i) => {
    const tw = cat.twitch[i];
    if (time > tw.next) { tw.t = time; tw.next = time + rand(1.5, 7); }
    const k = (time - tw.t) / 0.32;
    const flick = k < 1 ? 0.45 * Math.sin(T * k) * decay(k, 1.5) : 0;
    const swayX = 0.05 * Math.sin(time * 4.3 + p + i * 2), swayZ = 0.04 * Math.sin(time * 3.1 + p * 1.3 + i);
    _qd.setFromEuler(_e.set(swayX + flick + O.earPitch, 0, swayZ + O.earRoll * (i ? -1 : 1)));
    ear.quaternion.copy(cat.rest.get(ear)).multiply(_qd);
  });
  // eyes: scheduled blinks (sometimes double) + move scale
  if (cat.eyes.length) {
    const bl = cat.blink;
    if (time > bl.next) { bl.t = time; bl.next = time + (Math.random() < 0.2 ? 0.35 : rand(2, 6)); }
    const k = (time - bl.t) / 0.16;
    const blink = k < 1 ? 1 - 0.95 * Math.sin(Math.PI * k) : 1;
    const sy = Math.max(0.05, blink * O.eye);
    for (const eye of cat.eyes) eye.scale.set(1, sy, 1);
  }
  // tail: sway wave + move offsets
  cat.tails.forEach((tb, i) => {
    _qd.setFromEuler(_e.set(0.12 * Math.sin(time * 2.2 + p + i * 0.9) + O.tailPitch * (0.5 + 0.25 * i), 0, 0.10 * Math.sin(time * 1.7 + p * 0.7 + i * 0.9) + O.tailRoll * (0.4 + 0.3 * i)));
    tb.quaternion.copy(cat.rest.get(tb)).multiply(_qd);
  });
}

// ------------------------------------------------------------------ audio: per-cat voices + ambient loop
const AUDIO = { ctx: null, master: null, sfx: null, music: null, voices: new Map(), loop: null, muted: true, started: false, unlocked: false, keepAlive: null };   // starts muted: the button brings the sound in
// iPhone: Safari runs Web Audio in an 'ambient' session that the ringer switch silences. Asking for 'playback'
// (Safari 16.4+) before the context exists lifts that; older iOS gets a looping silent track instead, which promotes
// the session the same way. `?ios=1` forces the iOS path on a desktop for testing.
try { if (navigator.audioSession) navigator.audioSession.type = 'playback'; } catch {}
const IOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) || location.search.includes('ios=1');
function silentWavURL(seconds = 5) {   // a few seconds of 8 kHz silence, built in memory
  const rate = 8000, n = rate * seconds, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const tag = (o, t) => { for (let i = 0; i < t.length; i++) v.setUint8(o + i, t.charCodeAt(i)); };
  tag(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); tag(8, 'WAVE'); tag(12, 'fmt '); v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); tag(36, 'data'); v.setUint32(40, n * 2, true);
  return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
}
function audioInit() {
  if (AUDIO.ctx) return;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  AUDIO.ctx = new Ctx();
  AUDIO.master = AUDIO.ctx.createGain();
  AUDIO.master.connect(AUDIO.ctx.destination);
  AUDIO.sfx = AUDIO.ctx.createGain(); AUDIO.sfx.gain.value = 0.9; AUDIO.sfx.connect(AUDIO.master);
  AUDIO.music = AUDIO.ctx.createGain(); AUDIO.music.gain.value = 0.0; AUDIO.music.connect(AUDIO.master);
  const load = async (url) => { const r = await fetch(url); if (!r.ok) throw new Error(url); return AUDIO.ctx.decodeAudioData(await r.arrayBuffer()); };
  for (const name of names) load(`audio/${name}.mp3?b=${BUILD}`).then((b) => AUDIO.voices.set(name, b)).catch(() => {});
  load(`audio/ambient.mp3?b=${BUILD}`).then((buf) => {   // gapless loop through a buffer source
    const src = AUDIO.ctx.createBufferSource();
    src.buffer = buf; src.loop = true; src.connect(AUDIO.music); src.start();
    AUDIO.loop = src;
    AUDIO.music.gain.setTargetAtTime(AUDIO.muted ? 0 : 0.35, AUDIO.ctx.currentTime, 2.0);  // fade in
  }).catch(() => {});
}
function audioStart() {   // browsers only allow sound after a user gesture
  if (!AUDIO.started) { AUDIO.started = true; audioInit(); }
  const ctx = AUDIO.ctx;
  if (!ctx) return;
  if (ctx.state !== 'running') ctx.resume();   // 'suspended' at first; WebKit's 'interrupted' after a call, the lock screen or an app switch
  if (AUDIO.unlocked) return;
  AUDIO.unlocked = true;
  try {   // the classic iOS unlock: actually start a (silent) source inside the gesture
    const src = ctx.createBufferSource();
    src.buffer = ctx.createBuffer(1, 1, ctx.sampleRate); src.connect(ctx.destination); src.start(0);
  } catch {}
  if (IOS && !navigator.audioSession) {   // older iOS without the Audio Session API: keep a silent track looping
    if (!AUDIO.keepAlive) { const a = AUDIO.keepAlive = document.createElement('audio'); a.src = silentWavURL(); a.loop = true; a.setAttribute('playsinline', ''); a.playsInline = true; a.preload = 'auto'; }
    AUDIO.keepAlive.play().catch(() => { AUDIO.unlocked = false; });   // pointerdown is not a gesture for media on iOS: try again on the release
  }
}
document.addEventListener('visibilitychange', () => {   // back from the lock screen or another app: pick the context up on the next gesture, or now if allowed
  if (document.visibilityState === 'visible' && AUDIO.ctx && AUDIO.ctx.state !== 'running') AUDIO.ctx.resume().catch(() => {});
});
function meow(cat, rate = 1) {
  const buf = AUDIO.voices.get(cat.name);
  if (!AUDIO.ctx || !buf || AUDIO.muted) return;
  const src = AUDIO.ctx.createBufferSource();
  src.buffer = buf;
  src.playbackRate.value = rate * (0.94 + Math.random() * 0.12);   // a little variety on every press
  src.connect(AUDIO.sfx);
  src.start();
}
function toggleMute() {
  AUDIO.muted = !AUDIO.muted;
  if (AUDIO.music) AUDIO.music.gain.setTargetAtTime(AUDIO.muted ? 0 : 0.35, AUDIO.ctx.currentTime, 0.3);
  muteBtn.classList.toggle('muted', AUDIO.muted);
  muteBtn.title = muteBtn.ariaLabel = AUDIO.muted ? 'Unmute music' : 'Mute music';
}
const muteBtn = document.getElementById('mute');
muteBtn.addEventListener('click', (e) => { e.stopPropagation(); audioStart(); toggleMute(); });
window.addEventListener('pointerdown', audioStart, { once: false });
window.addEventListener('pointerup', audioStart);                 // iOS only counts the release as a gesture for audio
window.addEventListener('touchend', audioStart);
window.addEventListener('keydown', audioStart, { once: true });

// ------------------------------------------------------------------ day / night
const DAY = { hemiSky: new THREE.Color(0xfff0e0), hemiGround: new THREE.Color(0x7a4a34), hemiI: 0.5, keyC: new THREE.Color(0xffeedd), keyI: 2.3,
  fillC: new THREE.Color(0xdde8ff), fillI: 0.35, rimC: new THREE.Color(0xfff2e0), rimI: 0.6, lampI: 18, bg: new THREE.Color(0x3a2418), env: 0.35,
  spot: 1.0, signEm: 0.03, catEm: 0.0, shadeEm: 0.25, bulbEm: 3.0, exposure: 1.0 };
const NIGHT = { hemiSky: new THREE.Color(0x2b3d8a), hemiGround: new THREE.Color(0x120c14), hemiI: 0.22, keyC: new THREE.Color(0x8fa4ff), keyI: 0.12,
  fillC: new THREE.Color(0x5a6ac0), fillI: 0.04, rimC: new THREE.Color(0x9fb2ff), rimI: 0.2, lampI: 0, bg: new THREE.Color(0x120a10), env: 0.06,
  spot: 0.3, signEm: 0.35, catEm: 0.07, shadeEm: 0.0, bulbEm: 0.0, exposure: 0.95 };
const _c = new THREE.Color();
const lerp = (a, b, m) => a + (b - a) * m;
function applyMood(m) {
  hemi.color.copy(DAY.hemiSky).lerp(NIGHT.hemiSky, m); hemi.groundColor.copy(DAY.hemiGround).lerp(NIGHT.hemiGround, m); hemi.intensity = lerp(DAY.hemiI, NIGHT.hemiI, m);
  key.color.copy(DAY.keyC).lerp(NIGHT.keyC, m); key.intensity = lerp(DAY.keyI, NIGHT.keyI, m);
  fill.color.copy(DAY.fillC).lerp(NIGHT.fillC, m); fill.intensity = lerp(DAY.fillI, NIGHT.fillI, m);
  rim.color.copy(DAY.rimC).lerp(NIGHT.rimC, m); rim.intensity = lerp(DAY.rimI, NIGHT.rimI, m);
  lamp.intensity = lerp(DAY.lampI, NIGHT.lampI, m);
  MAT.shade.emissiveIntensity = lerp(DAY.shadeEm, NIGHT.shadeEm, m);
  MAT.bulb.emissiveIntensity = lerp(DAY.bulbEm, NIGHT.bulbEm, m);
  scene.background.copy(DAY.bg).lerp(NIGHT.bg, m);
  scene.environmentIntensity = lerp(DAY.env, NIGHT.env, m);
  renderer.toneMappingExposure = lerp(DAY.exposure, NIGHT.exposure, m);
  for (const sp of signLights) sp.intensity = sp.userData.base * lerp(DAY.spot, NIGHT.spot, m);
  if (SIGN.mesh) SIGN.mesh.traverse((o) => { if (o.isMesh) o.material.emissiveIntensity = lerp(DAY.signEm, NIGHT.signEm, m); });
  for (const nl of NIGHTLIGHTS) { nl.light.intensity = nl.max * m; for (const mat of nl.mats) mat.emissiveIntensity = nl.em * m; }
  for (const mat of CAT_MATS) { mat.emissive.setHex(0xffd8b0); mat.emissiveIntensity = lerp(DAY.catEm, NIGHT.catEm, m); }
  LAMP.uOn.value = 1 - m;
  for (const e of EYE_GLOWS) { e.mat.emissiveIntensity = 2.4 * m; for (const sp of e.sprites) { sp.visible = m > 0.02; sp.material.opacity = 0.6 * m; } }
}
function toggleNight() {
  MOOD.target = MOOD.target > 0.5 ? 0 : 1;
  MOOD.dirty = true;
  if (AUDIO.ctx) {   // a soft switch click
    const o = AUDIO.ctx.createOscillator(), g = AUDIO.ctx.createGain();
    o.frequency.value = MOOD.target ? 520 : 760; o.type = 'triangle';
    g.gain.setValueAtTime(0.0001, AUDIO.ctx.currentTime); g.gain.exponentialRampToValueAtTime(0.25, AUDIO.ctx.currentTime + 0.005); g.gain.exponentialRampToValueAtTime(0.0001, AUDIO.ctx.currentTime + 0.09);
    o.connect(g); g.connect(AUDIO.sfx); o.start(); o.stop(AUDIO.ctx.currentTime + 0.1);
  }
}

const clock = new THREE.Clock();
function frame() {
  if (window.innerWidth !== fitted.w || window.innerHeight !== fitted.h) fitCamera();
  const dt = Math.min(clock.getDelta(), 0.05), time = clock.elapsedTime;
  FX.time.value = time;
  for (const cat of cats) if (cat.fx.uTouchAmp.value > 0) { cat.fx.uTouchT.value = time - cat.fx.t0; if (cat.fx.uTouchT.value > 2.5) cat.fx.uTouchAmp.value = 0; }
  raycaster.setFromCamera(pointer, camera);
  if (raycaster.ray.intersectPlane(lookPlane, _v)) target.copy(_v);
  if (!touch.active && performance.now() - touch.last > 2500 && touch.last > 0) {   // finger lifted a while ago: look back at the viewer
    const k = 1 - Math.pow(0.97, dt * 60);
    pointer.x += (0 - pointer.x) * k; pointer.y += (0.15 - pointer.y) * k;
  }
  targetSmooth.lerp(target, 1 - Math.pow(0.85, dt * 60));
  keepCameraAboveFloor();
  controls.update();
  if (MOOD.dirty) {
    MOOD.value += (MOOD.target - MOOD.value) * (1 - Math.pow(0.92, dt * 60));
    if (Math.abs(MOOD.target - MOOD.value) < 0.002) { MOOD.value = MOOD.target; MOOD.dirty = false; }
    applyMood(MOOD.value);
  }
  for (const cat of cats) { cat._dt = dt; updateLook(cat, cat.lookAt || targetSmooth, dt); applyPose(cat, time); }
  for (const tr of TREATS) updateTreat(tr, dt);
  for (let i = RIPPLES.length - 1; i >= 0; i--) { const r = RIPPLES[i]; r.t += dt; const u = r.t / 0.7; r.m.scale.setScalar(1 + 3.2 * u); r.m.material.opacity = 0.85 * (1 - u); if (u >= 1) { scene.remove(r.m); r.m.geometry.dispose(); r.m.material.dispose(); RIPPLES.splice(i, 1); } }
  let sx = 0, sy = 0, roll = 0;
  if (SHAKE.amp > 0.002) {
    const a = SHAKE.amp, sd = SHAKE.seed;
    sx = Math.sin(time * 41 + sd) * 0.16 * a; sy = Math.sin(time * 53 + sd * 2) * 0.10 * a; roll = Math.sin(time * 37 + sd) * 0.012 * a;
    SHAKE.amp *= Math.exp(-dt * 6);
  }
  camera.position.x += sx; camera.position.y += sy; camera.rotateZ(roll);          // the shake is applied around the render only
  if (PULSE.amp > 0.003) {
    pulsePass.uniforms.uAmp.value = PULSE.amp; pulsePass.uniforms.uRadius.value = PULSE.radius;
    pulsePass.uniforms.uCenter.value.copy(PULSE.center); pulsePass.uniforms.uAspect.value = camera.aspect;
    composer.render();
    PULSE.amp *= Math.exp(-dt * 5.5); PULSE.radius += dt * 1.6;
  } else renderer.render(scene, camera);
  camera.rotateZ(-roll); camera.position.x -= sx; camera.position.y -= sy;
  requestAnimationFrame(frame);
}
frame();
window.lounge = { cats, MOVES, camera, controls, AUDIO, pointer, touch, FX, thud, RIP, PULSE, SHAKE, LAMP, impact, floorRipple, petAt, toggleNight, MOOD, treat: (x, z) => dropTreat(new THREE.Vector3(x, 0, z)), TREATS, meow: (name) => { const c = cats.find((x) => x.name === name); if (c) meow(c); }, play: (name, move) => { const c = cats.find((x) => x.name === name); return c ? play(c, move) : null; } };
