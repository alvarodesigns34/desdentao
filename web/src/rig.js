// Controlador del rig de Vesper.
// Traduce los parámetros expresivos (definidos en rig.json, compartido con Blender)
// a rotaciones óseas, resuelve IK de las patas, la mirada de los ojos y los morph targets.
import * as THREE from 'three';

const sanitize = (n) => THREE.PropertyBinding.sanitizeNodeName(n);
// Blender (X, Y, Z) con Z arriba  ->  three (X, Z, -Y) con Y arriba
export const b2t = (v) => new THREE.Vector3(v[0], v[2], -v[1]);
const mirrorAxis = (name, ax) => (name.endsWith('.R') ? [ax[0], -ax[1], -ax[2]] : ax);

// Partición de huesos: los "lentos" usan una versión más amortiguada de los parámetros
// (produce acción superpuesta: la cabeza se adelanta al cuello, el cuerpo arrastra).
const SLOW = /^(neck1|neck2|chest|spine1|hips|root|tail|fan|humerus|wforearm|wing_root|f\d[ab]|shoulder)/;

const _q = new THREE.Quaternion();
const _q2 = new THREE.Quaternion();
const _v = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _v3 = new THREE.Vector3();
const _m = new THREE.Matrix4();

export class Rig {
  constructor(model, rig) {
    this.model = model;
    this.def = rig;
    this.bones = {};
    model.updateMatrixWorld(true);
    const inv = new THREE.Matrix4().copy(model.matrixWorld).invert();
    model.traverse((o) => {
      if (o.isBone) this.bones[o.name] = o;
    });
    this.rest = {};
    for (const [name, b] of Object.entries(this.bones)) {
      const mm = new THREE.Matrix4().multiplyMatrices(inv, b.matrixWorld);
      const mp = new THREE.Vector3(), mq = new THREE.Quaternion(), ms = new THREE.Vector3();
      mm.decompose(mp, mq, ms);
      const pq = new THREE.Quaternion();
      if (b.parent) {
        const pm = new THREE.Matrix4().multiplyMatrices(inv, b.parent.matrixWorld);
        pm.decompose(new THREE.Vector3(), pq, new THREE.Vector3());
      }
      this.rest[name] = { q: b.quaternion.clone(), p: b.position.clone(), mq, mp, pq };
    }
    this.get = (n) => this.bones[sanitize(n)];
    this.restOf = (n) => this.rest[sanitize(n)];

    // contribuciones de parámetros en ejes locales
    this.contrib = {};
    for (const [p, list] of Object.entries(rig.params)) {
      this.contrib[p] = [];
      for (const [bn, ax, gain, type] of list) {
        const name = sanitize(bn);
        const r = this.rest[name];
        if (!r) continue;
        const axisT = b2t(mirrorAxis(bn, ax)).normalize();
        const local = type === 'loc'
          ? axisT.clone().applyQuaternion(r.pq.clone().invert())
          : axisT.clone().applyQuaternion(r.mq.clone().invert());
        this.contrib[p].push({ name, local, gain, type, slow: SLOW.test(bn) });
      }
    }
    // plegado de alas
    this.fold = {};
    for (const [bn, [ax, ang]] of Object.entries(rig.wingFold)) {
      const name = sanitize(bn);
      const r = this.rest[name];
      if (!r) continue;
      this.fold[name] = { local: b2t(ax).normalize().applyQuaternion(r.mq.clone().invert()), ang };
    }
    // IK de patas: posición de reposo del efector (cabeza del hueso final) en espacio modelo
    this.ik = [];
    for (const [end, [up, low]] of Object.entries(rig.ik)) {
      const e = sanitize(end);
      if (!this.bones[e]) continue;
      this.ik.push({
        end: e, up: sanitize(up), low: sanitize(low),
        target: this.rest[e].mp.clone(), restEndQ: this.rest[e].mq.clone(),
        offset: new THREE.Vector3(),
      });
    }
    // ojos
    this.eyes = ['L', 'R'].map((s) => {
      const name = sanitize(`eye.${s}`);
      const r = this.rest[name];
      const axisModel = b2t(rig.eyes[s].axis).normalize();
      return { name, axisLocal: axisModel.clone().applyQuaternion(r.mq.clone().invert()), cur: new THREE.Quaternion() };
    });
    // mallas y morphs
    this.meshes = [];
    model.traverse((o) => { if (o.isSkinnedMesh || o.isMesh) this.meshes.push(o); });
    this.body = this.meshes.find((m) => m.name.startsWith('VesperBody_web'));
    this.extraRot = new Map();
    this._rv = new Map();
    this._loc = new Map();
  }

  addRot(bone, axisModel, angle) {
    const name = sanitize(bone);
    const r = this.rest[name];
    if (!r) return;
    const local = _v.copy(axisModel).applyQuaternion(_q.copy(r.mq).invert()).multiplyScalar(angle);
    const cur = this.extraRot.get(name);
    if (cur) cur.add(local); else this.extraRot.set(name, local.clone());
  }

  // values: parámetros rápidos; slow: versión amortiguada
  apply(values, slow) {
    const rv = this._rv; const loc = this._loc;
    rv.clear(); loc.clear();
    for (const [p, list] of Object.entries(this.contrib)) {
      const vf = values[p] ?? 0; const vs = slow?.[p] ?? vf;
      if (vf === 0 && vs === 0) continue;
      for (const c of list) {
        const v = c.slow ? vs : vf;
        if (v === 0) continue;
        const map = c.type === 'loc' ? loc : rv;
        let acc = map.get(c.name);
        if (!acc) { acc = new THREE.Vector3(); map.set(c.name, acc); }
        acc.addScaledVector(c.local, c.gain * v);
      }
    }
    for (const [n, v] of this.extraRot) {
      let acc = rv.get(n);
      if (!acc) { acc = new THREE.Vector3(); rv.set(n, acc); }
      acc.add(v);
    }
    this.extraRot.clear();
    const wo = Math.min(1, Math.max(0, slow?.wing_open ?? values.wing_open ?? 0));
    for (const [name, b] of Object.entries(this.bones)) {
      const r = this.rest[name];
      b.quaternion.copy(r.q);
      const f = this.fold[name];
      if (f) {
        _q.setFromAxisAngle(f.local, f.ang * (1 - wo));
        b.quaternion.multiply(_q);
      }
      const a = rv.get(name);
      if (a) {
        const ang = a.length();
        if (ang > 1e-7) { _q.setFromAxisAngle(_v.copy(a).divideScalar(ang), ang); b.quaternion.multiply(_q); }
      }
      const l = loc.get(name);
      b.position.copy(r.p);
      if (l) b.position.add(l);
    }
    this.model.updateMatrixWorld(true);
  }

  // IK analítico de dos huesos para mantener las patas apoyadas
  solveIK(weight = 1) {
    const inv = _m.copy(this.model.matrixWorld).invert();
    for (const leg of this.ik) {
      const up = this.bones[leg.up], low = this.bones[leg.low], end = this.bones[leg.end];
      const A = new THREE.Vector3().setFromMatrixPosition(up.matrixWorld);
      const B = new THREE.Vector3().setFromMatrixPosition(low.matrixWorld);
      const C = new THREE.Vector3().setFromMatrixPosition(end.matrixWorld);
      const T = leg.target.clone().add(leg.offset).applyMatrix4(this.model.matrixWorld);
      T.lerp(C, 1 - weight);
      const a = A.distanceTo(B), b = B.distanceTo(C);
      let d = A.distanceTo(T);
      d = Math.min(Math.max(d, Math.abs(a - b) + 1e-3), a + b - 1e-3);
      // dirección de flexión actual (polo)
      const mid = A.clone().add(C).multiplyScalar(0.5);
      const pole = B.clone().sub(mid);
      const at = T.clone().sub(A).normalize();
      pole.addScaledVector(at, -pole.dot(at));
      if (pole.lengthSq() < 1e-8) pole.set(0, 0, 1);
      pole.normalize();
      const cosA = (a * a + d * d - b * b) / (2 * a * d);
      const sinA = Math.sqrt(Math.max(0, 1 - cosA * cosA));
      const Bn = A.clone().addScaledVector(at, a * cosA).addScaledVector(pole, a * sinA);
      this._rotateBoneWorld(up, B.clone().sub(A).normalize(), Bn.clone().sub(A).normalize());
      up.updateMatrixWorld(true);
      const B2 = new THREE.Vector3().setFromMatrixPosition(low.matrixWorld);
      const C2 = new THREE.Vector3().setFromMatrixPosition(end.matrixWorld);
      this._rotateBoneWorld(low, C2.clone().sub(B2).normalize(), T.clone().sub(B2).normalize());
      low.updateMatrixWorld(true);
      // la pata conserva su orientación de reposo (apoyada)
      const pq = new THREE.Quaternion();
      low.matrixWorld.decompose(_v2, pq, _v3);
      const mq = new THREE.Quaternion();
      this.model.matrixWorld.decompose(_v2, mq, _v3);
      const want = mq.clone().multiply(leg.restEndQ);
      end.quaternion.copy(pq.invert().multiply(want));
      end.updateMatrixWorld(true);
    }
    void inv;
  }

  _rotateBoneWorld(bone, from, to) {
    const dq = _q.setFromUnitVectors(from, to);
    const wq = new THREE.Quaternion();
    bone.matrixWorld.decompose(_v2, wq, _v3);
    const pw = new THREE.Quaternion();
    if (bone.parent) bone.parent.matrixWorld.decompose(_v2, pw, _v3);
    // nuevo mundo = dq * wq ; local = pw^-1 * nuevo
    const nw = dq.clone().multiply(wq);
    bone.quaternion.copy(pw.invert().multiply(nw));
  }

  // Orienta cada ojo hacia un punto (convergencia natural para objetos cercanos)
  aimEyes(worldPoint, maxAngle = 0.5, blend = 1) {
    for (const e of this.eyes) {
      const b = this.bones[e.name];
      const r = this.rest[e.name];
      const pw = new THREE.Quaternion();
      b.parent.matrixWorld.decompose(_v2, pw, _v3);
      const restW = pw.clone().multiply(r.q);
      const pos = new THREE.Vector3().setFromMatrixPosition(b.matrixWorld);
      const fwd = e.axisLocal.clone().applyQuaternion(restW);
      const d = worldPoint.clone().sub(pos).normalize();
      let ang = fwd.angleTo(d);
      const dq = new THREE.Quaternion();
      if (ang > 1e-4) {
        const axis = new THREE.Vector3().crossVectors(fwd, d).normalize();
        ang = Math.min(ang, maxAngle) * blend;
        dq.setFromAxisAngle(axis, ang);
      }
      // a local: restW^-1 * dq * restW
      const local = restW.clone().invert().multiply(dq).multiply(restW);
      e.cur.slerp(local, 1);
      b.quaternion.copy(r.q).multiply(e.cur);
      b.updateMatrixWorld(true);
    }
  }

  setMorph(name, v) {
    const m = this.body;
    if (!m || !m.morphTargetDictionary) return;
    const i = m.morphTargetDictionary[name];
    if (i !== undefined) m.morphTargetInfluences[i] = v;
  }

  worldPos(bone, out = new THREE.Vector3()) {
    return out.setFromMatrixPosition(this.get(bone).matrixWorld);
  }
}

// Muelle críticamente amortiguado (integración implícita, estable)
export function spring(s, target, omega, dt) {
  const f = 1 + 2 * dt * omega;
  const oo = omega * omega;
  const hoo = dt * oo;
  const hhoo = dt * hoo;
  const det = 1 / (f + hhoo);
  const x = (f * s.x + dt * s.v + hhoo * target) * det;
  s.v = (s.v + hoo * (target - s.x)) * det;
  s.x = x;
  return x;
}
