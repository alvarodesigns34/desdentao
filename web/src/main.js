// Vesper — estudio interactivo en tiempo real.
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { createStage, detectQuality } from './stage.js';
import { loadTextures, assignMaterials, shared } from './materials.js';
import { Rig, b2t } from './rig.js';
import { Behavior, MOODS } from './behavior.js';
import { CameraDirector } from './camera.js';
import { UI } from './ui.js';

const quality = detectQuality();
const canvas = document.getElementById('scene');
const stage = createStage(canvas, quality);
const { renderer, scene, camera, composer } = stage;

const ui = new UI();
const manager = new THREE.LoadingManager();
manager.onProgress = (_u, loaded, total) => ui.progress(loaded / total);

const state = { mode: 'interactuar', ready: false };
const raycaster = new THREE.Raycaster();
const ndc = new THREE.Vector2();
let rig, behavior, director, pickables = [], helpers = {};

// --- interacción: el listener debe registrarse ANTES que OrbitControls -------
const pointer = { down: false, onDragon: false, x: 0, y: 0, t0: 0, sx: 0, sy: 0, lastX: 0, lastY: 0, lastT: 0, hit: null, moved: 0 };
canvas.addEventListener('pointerdown', (e) => {
  if (!state.ready) return;
  director.userInput();
  pointer.down = true; pointer.sx = pointer.lastX = e.clientX; pointer.sy = pointer.lastY = e.clientY;
  pointer.t0 = e.timeStamp; pointer.lastT = performance.now(); pointer.moved = 0; pointer.strokeAcc = 0;
  pointer.hit = state.mode === 'interactuar' ? pick(e.clientX, e.clientY) : null;
  pointer.onDragon = !!pointer.hit;
  controls.enabled = !pointer.onDragon;
  if (pointer.onDragon) { canvas.setPointerCapture(e.pointerId); ui.touchMark(e.clientX, e.clientY); }
});
const controls = new OrbitControls(camera, canvas);
Object.assign(controls, {
  enableDamping: true, dampingFactor: 0.07, rotateSpeed: 0.55, zoomSpeed: 0.7, panSpeed: 0.6,
  minDistance: 0.9, maxDistance: 14, maxPolarAngle: Math.PI * 0.495, screenSpacePanning: true,
});
controls.target.set(0, 1.15, 0.2);

let lastPickT = 0;
canvas.addEventListener('pointermove', (e) => {
  if (!state.ready) return;
  const now = performance.now();
  const dtm = Math.max(1, now - pointer.lastT);
  const dx = e.clientX - pointer.lastX, dy = e.clientY - pointer.lastY;
  const speed = Math.hypot(dx, dy) / dtm * 1000;   // px/s
  pointer.lastX = e.clientX; pointer.lastY = e.clientY; pointer.lastT = now;
  if (pointer.down) { pointer.moved += Math.hypot(dx, dy); pointer.strokeAcc += Math.hypot(dx, dy); }
  // cursor como foco de atención (proyección sobre un plano a la altura de la cabeza)
  const wp = cursorWorld(e.clientX, e.clientY);
  if (wp && state.mode === 'interactuar') behavior.onCursor(wp, speed);
  // caricias: arrastrar sobre el dragón
  if (pointer.down && pointer.onDragon && now - lastPickT > 50) {
    lastPickT = now;
    const h = pick(e.clientX, e.clientY);
    if (h) {
      if (pointer.moved > 12) behavior.onStroke(h.region, h.point, pointer.strokeAcc, h.side, { leg: h.leg });
      pointer.strokeAcc = 0;
      ui.touchTrail(e.clientX, e.clientY);
    }
  }
  if (!pointer.down && state.mode === 'interactuar' && now - lastPickT > 120) {
    lastPickT = now;
    const h = pick(e.clientX, e.clientY);
    canvas.style.cursor = h ? 'grab' : 'default';
  }
});
const endPointer = (e) => {
  if (!pointer.down) return;
  pointer.down = false;
  controls.enabled = true;
  const dur = e.timeStamp - pointer.t0;
  if (pointer.onDragon && pointer.moved < 12 && dur < 600 && pointer.hit) {
    const h = pointer.hit;
    behavior.onTouch(h.region, h.point, { side: h.side, leg: h.leg });
  }
  pointer.onDragon = false;
  try { canvas.releasePointerCapture(e.pointerId); } catch { /* */ }
};
canvas.addEventListener('pointerup', endPointer);
canvas.addEventListener('pointercancel', endPointer);
canvas.addEventListener('wheel', () => director?.userInput(), { passive: true });

const _plane = new THREE.Plane();
const _hp = new THREE.Vector3();
function cursorWorld(x, y) {
  ndc.set((x / innerWidth) * 2 - 1, -(y / innerHeight) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const head = rig.worldPos('head');
  const n = camera.getWorldDirection(new THREE.Vector3());
  _plane.setFromNormalAndCoplanarPoint(n, head.clone().addScaledVector(n, -0.6));
  return raycaster.ray.intersectPlane(_plane, _hp) ? _hp.clone() : null;
}

// --- selección por zonas ------------------------------------------------------
const REGION = [
  [/^(jaw|tongue)/, 'jaw'], [/^(head|brow|nostril|eye|lid)/, 'head'], [/^neck/, 'neck'],
  [/^(tail|fan)/, 'tail'], [/^(humerus|wforearm|f\d[ab]|wing_root)/, 'wing'],
  [/^(upperarm|forearm|hand|fingers|thigh|shin|foot|toes)/, 'leg'], [/^(chest|spine1|hips|shoulder|root)/, 'body'],
];
const headRest = {};
function pick(x, y) {
  ndc.set((x / innerWidth) * 2 - 1, -(y / innerHeight) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  for (const m of pickables) if (m.isSkinnedMesh) m.skeleton.update();
  const hits = raycaster.intersectObjects(pickables, false);
  if (!hits.length) return null;
  const h = hits[0];
  const o = h.object;
  const local = h.point.clone().applyMatrix4(rig.model.matrixWorld.clone().invert());
  const side = local.x >= 0 ? 1 : -1;
  let region = 'body', leg = null, boneName = '';
  if (/^(Eye|Cornea|Lid)/.test(o.name)) region = 'eye';
  else if (/^Frill/.test(o.name)) region = 'frill';
  else if (/^Wing/.test(o.name)) region = 'wing';
  else if (/^TailFan/.test(o.name)) region = 'tail';
  else if (o.isSkinnedMesh && h.face) {
    const si = o.geometry.attributes.skinIndex, sw = o.geometry.attributes.skinWeight;
    const acc = new Map();
    for (const vi of [h.face.a, h.face.b, h.face.c]) {
      for (let k = 0; k < 4; k++) {
        const bi = si.getComponent(vi, k), w = sw.getComponent(vi, k);
        acc.set(bi, (acc.get(bi) || 0) + w);
      }
    }
    let best = -1, bw = -1;
    for (const [bi, w] of acc) if (w > bw) { bw = w; best = bi; }
    boneName = o.skeleton.bones[best]?.name || '';
    for (const [re, r] of REGION) if (re.test(boneName)) { region = r; break; }
    if (region === 'head') {
      // refinar: hocico / cuernos según la posición en el marco de reposo de la cabeza
      const hb = rig.get('head');
      const inv = hb.matrixWorld.clone().invert();
      const p = h.point.clone().applyMatrix4(inv).applyMatrix4(headRest.mat);
      const f = p.clone().sub(headRest.O).dot(headRest.F) / headRest.S;
      const u = p.clone().sub(headRest.O).dot(headRest.U) / headRest.S;
      if (f > 0.30) region = 'snout';
      else if (u > 0.14 && f < 0.12) region = 'horn';
    }
    if (region === 'body') {
      const nrm = h.face.normal.clone().transformDirection(o.matrixWorld);
      if (nrm.y > 0.45) region = 'back';
    }
    if (region === 'leg') {
      const front = /upperarm|forearm|hand|fingers/.test(boneName);
      leg = `${front ? 'hand' : 'foot'}.${side > 0 ? 'L' : 'R'}`;
    }
  }
  return { region, point: h.point.clone(), side, leg, bone: boneName };
}

// --- carga -------------------------------------------------------------------------
const tex = loadTextures(manager);
const [gltf, rigDef] = await Promise.all([
  new GLTFLoader(manager).loadAsync('vesper.glb'),
  fetch('rig.json').then((r) => r.json()),
]);
const model = gltf.scene;
scene.add(model);
const mats = assignMaterials(model, tex);
model.traverse((o) => {
  if (o.isSkinnedMesh) {
    o.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 1, 0), 6);
    o.boundingBox = new THREE.Box3(new THREE.Vector3(-3.5, -0.5, -4), new THREE.Vector3(3.5, 3.5, 3));
  }
});
rig = new Rig(model, rigDef);
behavior = new Behavior(rig, rigDef);
pickables = rig.meshes.filter((m) => /^(VesperBody_pick|Eye|Cornea|Lid|Frill.*Membrane|Wing|TailFanMembrane)/.test(m.name));
if (!pickables.some((m) => m.name.startsWith('VesperBody_pick'))) pickables.push(rig.body);

// marco de reposo de la cabeza (espacio modelo)
{
  const hb = rigDef.bones.head;
  const O = b2t(hb.head), T = b2t(hb.tail);
  const F = T.clone().sub(O).normalize();
  const U = b2t(rigDef.headUp).normalize();
  const r = rig.restOf('head');
  headRest.mat = new THREE.Matrix4().compose(r.mp, r.mq, new THREE.Vector3(1, 1, 1));
  Object.assign(headRest, { O, F, U, S: 1.13 });
}

director = new CameraDirector(camera, controls, rig);
helpers.skeleton = new THREE.SkeletonHelper(model);
helpers.skeleton.visible = false;
scene.add(helpers.skeleton);

// --- interfaz -------------------------------------------------------------------
ui.buildMoods(MOODS, (m) => behavior.setMood(m));
ui.onMode = (m) => {
  state.mode = m;
  canvas.style.cursor = 'default';
  document.body.dataset.mode = m;
};
ui.onCamera = (name) => director.go(name);
ui.onCinema = (on) => director.cinema(on);
ui.onToggle = (what, on) => {
  if (what === 'malla') model.traverse((o) => { if (o.isMesh && o.material) o.material.wireframe = on; });
  if (what === 'esqueleto') helpers.skeleton.visible = on;
  if (what === 'bloom') stage.bloom.enabled = on;
};
ui.stats({
  tris: rig.meshes.filter((m) => m.visible).reduce((s, m) => s + (m.geometry.index ? m.geometry.index.count / 3 : 0), 0),
  bones: Object.keys(rig.bones).length,
  morphs: Object.keys(rig.body.morphTargetDictionary || {}).length,
  quality,
});
director.cinemaChanged = (on) => ui.setCinema(on);

// --- bucle ------------------------------------------------------------------------
const clock = new THREE.Clock();
const UP = new THREE.Vector3(0, 1, 0), RIGHT = new THREE.Vector3(1, 0, 0);
let statusTimer = 0, frames = 0, fpsT = 0;
state.ready = true;
ui.ready();

let simT = 0;
function frame() {
  // tiempo simulado: paso real acotado (sin saltos al volver de otra pestaña),
  // o paso fijo si se solicita (pruebas automatizadas / capturas fotograma a fotograma)
  const real = Math.min(clock.getDelta(), 1 / 20);
  const dt = window.__vesperFixedDt || real;
  simT += dt;
  const t = simT;
  shared.uTime.value = t;
  const out = behavior.update(dt, t, { camera });
  const v = out.values;

  // cola procedural: onda viajera + impulso por contacto
  const tl = out.tail;
  for (let i = 0; i < 14; i++) {
    const w = 0.3 + i / 13;
    const yaw = tl.amp * Math.sin(tl.phase * Math.PI * 2 - i * 0.45) * w
      + tl.impulse * tl.impSide * 0.22 * Math.sin(t * 9 - i * 0.7) * w;
    const pitch = tl.amp * 0.25 * Math.sin(tl.phase * Math.PI - i * 0.3 + 1.0) * w;
    const name = `tail${String(i + 1).padStart(2, '0')}`;
    rig.addRot(name, UP, yaw);
    rig.addRot(name, RIGHT, -pitch);
  }
  rig.addRot('chest', RIGHT, 0.018 * (out.values.chestBreath - 0.5));
  rig.addRot('neck1', RIGHT, -0.01 * (out.values.chestBreath - 0.5));
  rig.apply(v, out.slow);

  // IK de patas (con pata levantada si procede)
  const lift = behavior.ikLift;
  for (const leg of rig.ik) {
    leg.offset.set(0, 0, 0);
    if (lift && lift.leg && THREE.PropertyBinding.sanitizeNodeName(lift.leg) === leg.end) {
      const u = (behavior.t - lift.start) / lift.dur;
      if (u >= 0 && u <= 1) {
        const k = Math.sin(Math.PI * Math.min(1, u * 1.2)) ** 2;
        leg.offset.set(0, 0.16 * k, 0.06 * k);
      }
    }
  }
  rig.solveIK();
  rig.aimEyes(out.gaze, 0.5);

  // morphs y uniformes de material
  rig.setMorph('Breathe', v.breath);
  rig.setMorph('Snarl', THREE.MathUtils.clamp(v.snarl, 0, 1.2));
  rig.setMorph('Smile', THREE.MathUtils.clamp(v.smile, 0, 1.2));
  rig.setMorph('NostrilFlare', THREE.MathUtils.clamp(v.nostril, 0, 1.2));
  rig.setMorph('ThroatPuff', THREE.MathUtils.clamp(v.throat, 0, 1.2));
  shared.uGlow.value = Math.max(0, v.glow);
  shared.uThroat.value = Math.max(0, v.throat);
  shared.uPupil.value = THREE.MathUtils.clamp(v.pupil, 0.02, 1);

  director.update(dt, t);
  controls.update();
  stage.updateLightUniforms();
  composer.render();

  statusTimer -= dt;
  if (statusTimer <= 0) { ui.status(behavior.statusText(), behavior.mood, behavior.userMood); statusTimer = 0.25; }
  ui.pulse(v.glow, v.breath);
  frames++; fpsT += dt;
  if (fpsT > 1) { ui.fps(frames / fpsT); frames = 0; fpsT = 0; }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// para pruebas automatizadas
window.__vesper = { behavior, rig, director, pick, ui, state, camera, controls };
