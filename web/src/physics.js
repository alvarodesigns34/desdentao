// Dinámica secundaria y locomoción de Vesper:
//  * TailSim: cola con inercia (Verlet), restricción de longitud y colisión con el suelo,
//    que sigue a la pose animada como un músculo (rigidez decreciente hacia la punta).
//  * Locomotion: el cuerpo gira para encarar su foco de atención y las patas dan pasos
//    en pares diagonales (las pisadas quedan clavadas al suelo entre paso y paso).
import * as THREE from 'three';
import { b2t } from './rig.js';

const UP = new THREE.Vector3(0, 1, 0);
const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion();
const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _s = new THREE.Vector3();

export class TailSim {
  constructor(rig, names) {
    this.rig = rig;
    this.bones = names.map((n) => rig.get(n));
    const def = rig.def.bones;
    const pts = names.map((n) => b2t(def[n].head));
    pts.push(b2t(def[names[names.length - 1]].tail));
    this.len = [];
    for (let i = 0; i < pts.length - 1; i++) this.len.push(pts[i].distanceTo(pts[i + 1]));
    this.pos = pts.map((p) => p.clone());
    this.prev = pts.map((p) => p.clone());
    this.target = pts.map((p) => p.clone());
    this.rad = pts.map((_, i) => 0.035 + 0.17 * Math.pow(1 - i / pts.length, 1.35));
    // punta en el espacio local del último hueso
    const last = this.bones[this.bones.length - 1];
    rig.model.updateMatrixWorld(true);
    this.tipLocal = pts[pts.length - 1].clone().applyMatrix4(new THREE.Matrix4().copy(last.matrixWorld).invert());
    this.ready = false;
  }

  update(dt, enabled = true) {
    const B = this.bones, n = B.length;
    for (let i = 0; i < n; i++) this.target[i].setFromMatrixPosition(B[i].matrixWorld);
    this.target[n].copy(this.tipLocal).applyMatrix4(B[n - 1].matrixWorld);
    if (!this.ready || !enabled) {
      for (let i = 0; i <= n; i++) { this.pos[i].copy(this.target[i]); this.prev[i].copy(this.target[i]); }
      this.ready = true;
      if (!enabled) return;
    }
    const steps = 2, h = dt / steps;
    for (let st = 0; st < steps; st++) {
      this.pos[0].copy(this.target[0]);
      for (let i = 1; i <= n; i++) {
        const p = this.pos[i], pv = this.prev[i];
        _v.subVectors(p, pv).multiplyScalar(0.965);        // inercia con amortiguación
        pv.copy(p);
        p.add(_v);
        p.y -= 2.2 * h * h;                                  // gravedad (atenuada: la cola es musculosa)
        const k = 1 - Math.exp(-h * (22 - 15.5 * (i / n)));  // rigidez: base firme, punta suelta
        p.lerp(this.target[i], k);
      }
      for (let it = 0; it < 2; it++) {
        for (let i = 1; i <= n; i++) {
          _v.subVectors(this.pos[i], this.pos[i - 1]);
          const d = _v.length() || 1e-6;
          this.pos[i].copy(this.pos[i - 1]).addScaledVector(_v, this.len[i - 1] / d);
          const floor = this.rad[i] * 0.85;
          if (this.pos[i].y < floor) this.pos[i].y = floor;
        }
      }
    }
    // orientar cada vértebra hacia el punto simulado siguiente
    for (let i = 0; i < n; i++) {
      const b = B[i];
      b.updateMatrixWorld(true);
      const head = _v.setFromMatrixPosition(b.matrixWorld);
      const cur = i < n - 1 ? _v2.setFromMatrixPosition(B[i + 1].matrixWorld) : _v2.copy(this.tipLocal).applyMatrix4(b.matrixWorld);
      const from = cur.sub(head).normalize();
      const to = _s.subVectors(this.pos[i + 1], this.pos[i]).normalize();
      _q.setFromUnitVectors(from, to);
      const wq = new THREE.Quaternion(); b.matrixWorld.decompose(new THREE.Vector3(), wq, new THREE.Vector3());
      const pq = new THREE.Quaternion(); b.parent.matrixWorld.decompose(new THREE.Vector3(), pq, new THREE.Vector3());
      b.quaternion.copy(pq.invert().multiply(_q.multiply(wq)));
      b.updateMatrixWorld(true);
    }
  }
}

const ease = (x) => (x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2);

export class Locomotion {
  constructor(rig) {
    this.rig = rig;
    this.yaw = 0; this.yawV = 0; this.goalYaw = 0; this.hold = 0;
    this.legs = rig.ik.map((l) => ({
      l, rest: l.target.clone(), plant: l.target.clone(), footYaw: 0,
      step: null, front: /hand/.test(l.end), left: /L$/.test(l.end),
    }));
    this.cool = 0;
  }

  // relYaw: ángulo del foco de atención respecto a la orientación actual del cuerpo
  desire(relYaw, dt) {
    if (Math.abs(relYaw) > 0.85) this.hold += dt; else this.hold = Math.max(0, this.hold - dt * 1.5);
    if (this.hold > 1.1) {
      this.goalYaw = THREE.MathUtils.clamp(this.yaw + relYaw * 0.8, -1.6, 1.6);
      this.hold = 0;
    }
  }

  stepping() { return this.legs.some((g) => g.step); }

  update(dt) {
    // giro del cuerpo: muelle lento y sólo mientras las patas acompañan
    const om = 2.2;
    const acc = om * om * (this.goalYaw - this.yaw) - 2 * om * this.yawV;
    this.yawV += acc * dt; this.yaw += this.yawV * dt;
    _q2.setFromAxisAngle(UP, this.yaw);
    // pasos
    this.cool -= dt;
    const goals = this.legs.map((g) => g.rest.clone().applyQuaternion(_q2));
    if (!this.stepping() && this.cool <= 0) {
      let worst = -1, we = 0.09;
      this.legs.forEach((g, i) => { const e = g.plant.distanceTo(goals[i]) + Math.abs(g.footYaw - this.yaw) * 0.12; if (e > we) { we = e; worst = i; } });
      if (worst >= 0) {
        const a = this.legs[worst];
        const partner = this.legs.find((g) => g.front !== a.front && g.left !== a.left);
        for (const g of [a, partner]) {
          const i = this.legs.indexOf(g);
          if (g === a || g.plant.distanceTo(goals[i]) > 0.035) {
            g.step = { from: g.plant.clone(), to: goals[i].clone(), fy: g.footYaw, ty: this.yaw, u: 0, dur: 0.34 + Math.random() * 0.06 };
          }
        }
        this.cool = 0.12;
      }
    }
    for (const g of this.legs) {
      if (g.step) {
        const s = g.step;
        s.u = Math.min(1, s.u + dt / s.dur);
        const k = ease(s.u);
        g.plant.lerpVectors(s.from, s.to, k);
        g.plant.y += 0.10 * Math.sin(Math.PI * s.u) * (g.front ? 1.0 : 0.85);
        g.footYaw = s.fy + (s.ty - s.fy) * k;
        if (s.u >= 1) { g.plant.copy(s.to); g.step = null; }
      }
      g.l.offset.copy(g.plant).sub(g.rest);
      g.l.footYaw = g.footYaw;
    }
    return this.yaw;
  }
}
