// Dirección de cámara: encuadres predefinidos con transiciones suaves,
// seguimiento de la cabeza en planos cercanos y modo cinematográfico automático.
import * as THREE from 'three';

const ease = (x) => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 3);           // salida suave
const easeIO = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);

export const PRESETS = {
  completo: { label: 'Cuerpo completo', pos: [5.3, 2.4, 6.3], target: [0, 1.0, -0.3], fov: 32 },
  tresCuartos: { label: 'Tres cuartos', pos: [3.4, 2.1, 4.4], target: [0, 1.35, 0.6], fov: 30 },
  retrato: { label: 'Retrato', offset: [0.9, 0.18, 2.1], track: 'head', fov: 26 },
  perfil: { label: 'Perfil', pos: [7.4, 1.35, -0.4], target: [0, 1.05, -0.4], fov: 30 },
  ojo: { label: 'Detalle del ojo', offset: [0.42, 0.06, 0.5], track: 'eye.L', fov: 22 },
  alas: { label: 'Alas y lomo', pos: [2.3, 3.9, -1.4], target: [0.3, 1.35, -0.4], fov: 34 },
  cola: { label: 'Cola', pos: [2.4, 1.0, -5.4], target: [0, 0.75, -2.7], fov: 30 },
  posterior: { label: 'Posterior', pos: [-2.8, 2.6, -7.2], target: [0, 1.1, -0.4], fov: 32 },
};

const SHOTS = [
  { a: { pos: [6.8, 2.5, 7.2], target: [0, 1.1, 0], fov: 30 }, b: { pos: [4.9, 2.1, 5.4], target: [0, 1.25, 0.4], fov: 28 }, dur: 9 },
  { a: { offset: [1.6, 0.3, 1.8], track: 'head', fov: 24 }, b: { offset: [-0.7, 0.15, 2.3], track: 'head', fov: 24 }, dur: 9 },
  { a: { pos: [7.2, 0.8, -1.8], target: [0, 1.0, -0.9], fov: 26 }, b: { pos: [7.0, 1.15, 1.1], target: [0, 1.25, 0.5], fov: 26 }, dur: 8 },
  { a: { offset: [0.55, 0.1, 0.55], track: 'eye.L', fov: 20 }, b: { offset: [0.42, 0.04, 0.66], track: 'eye.L', fov: 18 }, dur: 6.5 },
  { a: { pos: [-2.9, 3.7, -3.2], target: [0, 1.3, -0.6], fov: 32 }, b: { pos: [-3.4, 2.9, -0.8], target: [0, 1.35, -0.2], fov: 32 }, dur: 8 },
  { a: { pos: [2.4, 0.55, -5.4], target: [0, 0.8, -2.8], fov: 30 }, b: { pos: [1.0, 0.8, -4.4], target: [0, 0.9, -2.2], fov: 30 }, dur: 7 },
];

export class CameraDirector {
  constructor(camera, controls, rig) {
    this.camera = camera; this.controls = controls; this.rig = rig;
    this.tween = null; this.trackName = null; this.trackOffset = new THREE.Vector3();
    this.cine = null; this.cinemaChanged = null;
    this._ht = new THREE.Vector3();
    this.go('completo', 0.01);
  }

  _anchor(name) {
    return this.rig.worldPos(name, new THREE.Vector3());
  }

  _resolve(p) {
    if (p.track) {
      const a = this._anchor(p.track);
      return { pos: a.clone().add(new THREE.Vector3(...p.offset)), target: a, fov: p.fov, track: p.track, offset: new THREE.Vector3(...p.offset) };
    }
    // adaptación a pantallas verticales (móvil / tablet en vertical): alejar y centrar en la cabeza
    const aspect = this.camera.aspect;
    const k = aspect < 1.2 ? 1 + (1.2 - aspect) * 1.05 : 1;
    const target = new THREE.Vector3(...p.target);
    const pos = new THREE.Vector3(...p.pos).sub(target).multiplyScalar(k);
    if (k > 1) target.z += (k - 1) * 0.9;
    return { pos: pos.add(target), target, fov: p.fov };
  }

  go(name, dur = 1.8) {
    this.stopCinema();
    const p = PRESETS[name];
    if (!p) return;
    this._tweenTo(p, dur);
  }

  _tweenTo(p, dur) {
    this.tween = {
      from: { pos: this.camera.position.clone(), target: this.controls.target.clone(), fov: this.camera.fov },
      to: p, t: 0, dur,
    };
    this.trackName = null;
  }

  userInput() {
    if (this.cine) this.stopCinema();
    if (this.tween && this.tween.t > 0.15) this.tween = null;
  }

  cinema(on) {
    if (!on) return this.stopCinema();
    this.cine = { i: 0, t: 0, blend: 1.4 };
    this.cinemaChanged?.(true);
  }

  stopCinema() {
    if (!this.cine) return;
    this.cine = null;
    this.controls.enabled = true;
    this.cinemaChanged?.(false);
  }

  update(dt) {
    const cam = this.camera, ctl = this.controls;
    if (this.cine) {
      const c = this.cine;
      c.t += dt;
      const s = SHOTS[c.i];
      if (c.t > s.dur) { c.i = (c.i + 1) % SHOTS.length; c.t = 0; c.from = { pos: cam.position.clone(), target: ctl.target.clone(), fov: cam.fov }; }
      const sh = SHOTS[c.i];
      const u = easeIO(c.t / sh.dur);
      const A = this._resolve(sh.a), B = this._resolve(sh.b);
      const pos = A.pos.clone().lerp(B.pos, u), tgt = A.target.clone().lerp(B.target, u);
      const fov = A.fov + (B.fov - A.fov) * u;
      if (c.from && c.t < c.blend) {
        const k = ease(c.t / c.blend);
        pos.lerpVectors(c.from.pos, pos, k); tgt.lerpVectors(c.from.target, tgt, k);
      }
      cam.position.copy(pos); ctl.target.copy(tgt); cam.fov = fov; cam.updateProjectionMatrix();
      return;
    }
    if (this.tween) {
      const tw = this.tween;
      tw.t += dt;
      const k = ease(tw.t / tw.dur);
      const to = this._resolve(tw.to);
      cam.position.lerpVectors(tw.from.pos, to.pos, k);
      ctl.target.lerpVectors(tw.from.target, to.target, k);
      cam.fov = tw.from.fov + (to.fov - tw.from.fov) * k;
      cam.updateProjectionMatrix();
      if (tw.t >= tw.dur) {
        this.tween = null;
        if (to.track) { this.trackName = to.track; this._ht.copy(to.target); }
      }
      return;
    }
    if (this.trackName) {
      // seguir la cabeza: desplazar cámara y objetivo con el mismo delta (suavizado)
      const a = this._anchor(this.trackName);
      const prev = this._ht.clone();
      this._ht.lerp(a, 1 - Math.exp(-dt * 3));
      const d = this._ht.clone().sub(prev);
      cam.position.add(d); ctl.target.add(d);
    }
  }
}
