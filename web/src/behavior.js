// Conducta de Vesper: controlador de estados emocionales, reacciones, atención y
// movimiento secundario. Produce objetivos de parámetros que el Animator suaviza con
// muelles críticamente amortiguados (dos velocidades: cabeza rápida / cuerpo lento).
import * as THREE from 'three';
import { spring, springZ } from './rig.js';

export const MOODS = {
  calma: { label: 'Calma', status: 'Vesper está en calma' },
  curiosidad: { label: 'Curiosidad', status: 'Vesper siente curiosidad' },
  alegria: { label: 'Alegría', status: 'Vesper está de buen humor' },
  desconfianza: { label: 'Desconfianza', status: 'Vesper desconfía' },
  enfado: { label: 'Enfado', status: 'Vesper está de mal humor' },
  ternura: { label: 'Ternura', status: 'Vesper se siente a gusto' },
  sorpresa: { label: 'Sorpresa', status: 'Vesper se ha sobresaltado' },
  somnolencia: { label: 'Sueño', status: 'Vesper tiene sueño' },
  juego: { label: 'Juego', status: 'Vesper quiere jugar' },
};

// Comportamiento dinámico por ánimo
const STYLE = {
  calma: { breath: [0.24, 0.8], blink: [2.8, 6.0], tail: [0.035, 1.2], follow: 0.65, interest: 1.0, react: 1.0 },
  curiosidad: { breath: [0.30, 0.7], blink: [3.5, 7.0], tail: [0.05, 2.6], follow: 0.85, interest: 1.6, react: 1.2 },
  alegria: { breath: [0.34, 0.8], blink: [2.5, 5.0], tail: [0.13, 5.2], follow: 0.75, interest: 1.3, react: 1.3 },
  desconfianza: { breath: [0.30, 0.6], blink: [4.0, 8.0], tail: [0.03, 1.0], follow: 0.9, interest: 1.2, react: 0.8 },
  enfado: { breath: [0.50, 1.0], blink: [5.0, 9.0], tail: [0.09, 6.5], follow: 0.95, interest: 1.0, react: 1.5 },
  ternura: { breath: [0.21, 0.9], blink: [2.2, 4.5], tail: [0.04, 1.1], follow: 0.55, interest: 0.8, react: 0.8 },
  sorpresa: { breath: [0.55, 1.0], blink: [5.0, 8.0], tail: [0.02, 1.0], follow: 1.0, interest: 1.5, react: 1.4 },
  somnolencia: { breath: [0.14, 1.0], blink: [1.6, 3.4], tail: [0.015, 0.6], follow: 0.35, interest: 0.4, react: 0.5 },
  juego: { breath: [0.42, 0.9], blink: [3.0, 6.0], tail: [0.15, 6.0], follow: 1.0, interest: 2.0, react: 1.6 },
};

// frecuencias propias de los muelles (rad/s) por grupo de parámetro
const OMEGA = (p) => {
  if (/^lid|^pupil/.test(p)) return 14;
  if (/^jaw|tongue|snarl|nostril|smile/.test(p)) return 11;
  if (/^frill|^fan/.test(p)) return 9;
  if (/^eye/.test(p)) return 20;
  if (/^head/.test(p)) return 6.5;
  if (/^neck/.test(p)) return 4.5;
  if (/^wing/.test(p)) return 4.0;
  if (/^body|front|shoulder/.test(p)) return 3.6;
  if (/^tail/.test(p)) return 3.0;
  if (/glow|throat/.test(p)) return 4.0;
  return 6;
};

const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const smooth = (x) => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
// envolvente: ataque a, mantenimiento hasta h, caída hasta 1
const env = (u, a = 0.2, h = 0.6) => (u < a ? smooth(u / a) : u < h ? 1 : 1 - smooth((u - h) / (1 - h)));
const bump = (u, c, w) => Math.exp(-(((u - c) / w) ** 2));
const rnd = (a, b) => a + Math.random() * (b - a);
const pick = (arr) => {
  const tot = arr.reduce((s, [w]) => s + w, 0);
  let r = Math.random() * tot;
  for (const [w, v] of arr) { if ((r -= w) <= 0) return v; }
  return arr[arr.length - 1][1];
};

export class Behavior {
  constructor(rig, def) {
    this.rig = rig;
    this.def = def;
    this.neutral = def.neutral;
    this.emotions = def.emotions;
    this.params = Object.keys(def.neutral);
    this.fast = {}; this.slow = {};
    for (const p of this.params) {
      this.fast[p] = { x: this.neutral[p], v: 0 };
      this.slow[p] = { x: this.neutral[p], v: 0 };
    }
    this.mood = 'calma';
    this.userMood = null;            // null => autónomo
    this.moodSince = 0;
    this.scores = Object.fromEntries(Object.keys(MOODS).map((k) => [k, 0]));
    this.clips = [];
    this.t = 0;
    this.blink = { next: 2, start: -10, dur: 0.22, closed: 0.04, slow: false, double: false };
    this.breathPhase = 0;
    this.pet = { level: 0, region: null, point: new THREE.Vector3(), side: 0, last: -10 };
    this.cursor = { point: new THREE.Vector3(0, 1.6, 4), interest: 0, last: -10 };
    this.viewer = new THREE.Vector3(0, 1.7, 5);
    this.gaze = { point: new THREE.Vector3(0, 1.6, 4), smooth: new THREE.Vector3(0, 1.6, 4), glance: null, glanceUntil: 0, nextGlance: 3 };
    this.tail = { impulse: 0, side: 1, phase: 0 };
    this.nextIdle = 4;
    this.lastInteraction = 0;
    this.taps = [];
    this.annoy = 0; this.affection = 0; this.excite = 0;
    this.activity = '';
    this.activityUntil = 0;
    this.ikLift = { leg: null, amt: 0 };
    this.headLookOffset = { yaw: 0, pitch: 0 };
    this.onStatus = null;
    this.bodyYaw = 0; this.relYaw = 0;
    this._sacc = { next: 0, off: new THREE.Vector3() };
  }

  // ------------------------------------------------------------------ API
  setMood(name) {
    this.userMood = name;
    if (name) this._enterMood(name, true);
  }

  _enterMood(name, user = false) {
    if (name === this.mood) return;
    const prev = this.mood;
    this.mood = name;
    this.moodSince = this.t;
    // transición con un gesto de entrada característico
    if (name === 'sorpresa') this._play('startle');
    else if (name === 'alegria' && prev !== 'juego') this._play('happyHop');
    else if (name === 'juego') this._play('pounce');
    else if (name === 'enfado') this._play('growl');
    else if (name === 'somnolencia' && user) this._play('yawn');
    else if (name === 'curiosidad') this._play('sniffAir');
    this._setActivity('', 0);
  }

  onCursor(point, speed) {
    this.cursor.point.copy(point);
    const st = STYLE[this.mood];
    this.cursor.interest = clamp(this.cursor.interest + speed * 0.0025 * st.interest, 0, 1.4);
    this.cursor.last = this.t;
    if (speed > 900 && this.mood === 'juego' && Math.random() < 0.02) this._play('pounce');
  }

  onStroke(region, point, dist, side, info = {}) {
    // pasar la mano por ojo, hocico, cuernos o gorgueras cuenta como caricia de cabeza
    if (['eye', 'snout', 'horn', 'frill'].includes(region)) region = 'head';
    if (!['head', 'neck', 'back', 'jaw'].includes(region)) {
      // en zonas no acariciables, el roce provoca una reacción (limitada en frecuencia)
      this._strokeReact = this._strokeReact || {};
      if (this.t - (this._strokeReact[region] ?? -9) > 2.5) {
        this._strokeReact[region] = this.t;
        this.onTouch(region, point, { stroke: true, ...info, side });
      }
      return;
    }
    const p = this.pet;
    p.region = region; p.point.copy(point); p.side = side; p.last = this.t;
    p.level = clamp(p.level + clamp(dist, 0, 120) * 0.0035, 0, 1);
    this.lastInteraction = this.t;
    this.affection = clamp(this.affection + 0.004, 0, 1);
    this.annoy = Math.max(0, this.annoy - 0.004);
  }

  onTouch(region, point, info = {}) {
    this.lastInteraction = this.t;
    if (!info.stroke) {
      this.taps.push(this.t);
      this.taps = this.taps.filter((x) => this.t - x < 3);
      if (this.taps.length > 4) { this.annoy = clamp(this.annoy + 0.25, 0, 1); }
    }
    if (this.clips.some((c) => c.blocking && this.t < c.start + c.dur * 0.7)) return;
    const m = this.mood;
    const P = point.clone();
    // reacciones dominadas por el ánimo
    if (m === 'enfado' && region !== 'eye') return this._play(pick([[0.6, 'snap'], [0.4, 'growl']]), { point: P });
    if (m === 'desconfianza' && Math.random() < 0.7 && region !== 'eye') return this._play('flinch', { point: P, side: info.side });
    if (m === 'sorpresa') return this._play('startle', { point: P });
    if (m === 'somnolencia' && Math.random() < 0.55) return this._play(pick([[0.6, 'drowsy'], [0.4, 'yawn']]), { point: P });
    if (m === 'juego' && Math.random() < 0.45 && region !== 'eye') return this._play('pounce', { point: P });
    // reacciones por zona
    switch (region) {
      case 'snout': return this._play(pick([[0.35, 'sniff'], [0.2, 'sneeze'], [0.25, 'lick'], [0.2, 'crossEyed']]), { point: P });
      case 'jaw': return this._play('chinScratch', { point: P, side: info.side });
      case 'eye': this.annoy = clamp(this.annoy + 0.3, 0, 1); return this._play('eyePoke', { point: P, side: info.side });
      case 'horn': return this._play('hornShake', { point: P, side: info.side });
      case 'frill': return this._play('frillFlick', { point: P });
      case 'head': return this._play(pick([[0.5, 'nuzzle'], [0.5, 'crossEyed']]), { point: P, side: info.side });
      case 'wing': return this._play(pick([[0.35, 'lookWing'], [0.35, 'stretch'], [0.3, 'wingFlick']]), { point: P, side: info.side });
      case 'tail': return this._play(pick([[0.6, 'tailFlick'], [0.4, 'tailLook']]), { point: P, side: info.side });
      case 'leg': return this._play('pawLift', { point: P, leg: info.leg });
      default: return this._play('shiver', { point: P });
    }
  }

  // ------------------------------------------------------------------ clips
  _play(name, opts = {}) {
    const mk = CLIPS[name];
    if (!mk) return;
    const c = mk(opts, this);
    c.name = name; c.start = this.t; c.opts = opts;
    // una sola instancia por nombre
    this.clips = this.clips.filter((x) => x.name !== name);
    this.clips.push(c);
    if (c.status) this._setActivity(c.status, c.dur);
    if (c.onStart) c.onStart(this);
  }

  _setActivity(text, dur) {
    this.activity = text; this.activityUntil = this.t + dur;
  }

  statusText() {
    const base = MOODS[this.mood].status;
    if (this.pet.level > 0.25) return this.pet.level > 0.6 ? 'Vesper ronronea con las caricias' : 'Vesper disfruta de las caricias';
    if (this.activity && this.t < this.activityUntil) return `Vesper ${this.activity}`;
    if (this.cursor.interest > 0.35 && this.t - this.cursor.last < 1.5) return `${base} · sigue tu mano`;
    return base;
  }

  // ------------------------------------------------------------------ ánimo autónomo
  _autoMood(dt) {
    if (this.userMood) return;
    const s = this.scores;
    const idle = this.t - this.lastInteraction;
    const decay = Math.exp(-dt / 10);
    for (const k in s) s[k] *= decay;
    s.calma += 0.05 * dt * 10;
    s.ternura += this.pet.level * dt * 1.2 + this.affection * dt * 0.2;
    s.alegria += this.affection * dt * 0.35;
    s.curiosidad += (this.cursor.interest > 0.3 ? 0.9 : 0) * dt;
    s.desconfianza += this.annoy * dt * 1.4;
    s.enfado += Math.max(0, this.annoy - 0.55) * dt * 4;
    s.somnolencia += idle > 25 ? dt * 0.9 : 0;
    s.juego += this.excite * dt * 1.5;
    this.affection *= Math.exp(-dt / 40);
    this.annoy *= Math.exp(-dt / 18);
    this.excite *= Math.exp(-dt / 8);
    if (this.t - this.moodSince < 5) return;
    let best = this.mood, bv = s[this.mood] * 1.25;  // histéresis
    for (const k in s) if (s[k] > bv) { bv = s[k]; best = k; }
    if (best !== this.mood) this._enterMood(best);
    if (idle < 2 && this.mood === 'somnolencia') this._enterMood('calma');
  }

  // ------------------------------------------------------------------ actualización
  update(dt, t, ctx) {
    this.t = t;
    this.viewer.copy(ctx.camera.position);
    this._autoMood(dt);
    const st = STYLE[this.mood];
    const target = {};
    const emo = this.emotions[this.mood] || {};
    for (const p of this.params) target[p] = emo[p] ?? this.neutral[p];

    // --- caricias -------------------------------------------------------
    const pet = this.pet;
    if (t - pet.last > 0.6) pet.level = Math.max(0, pet.level - dt * 0.3);
    const pl = smooth(pet.level);
    if (pl > 0.01) {
      const grumpy = this.mood === 'enfado' ? 0.4 : 1;
      target.lid_up += (0.85 - target.lid_up) * pl * grumpy;
      target.lid_lo += (0.5 - target.lid_lo) * pl * grumpy;
      target.smile += 0.7 * pl * grumpy;
      target.snarl *= 1 - pl;
      target.frill_flare += (-0.55 - target.frill_flare) * pl;
      target.frill_spread += (-0.2 - target.frill_spread) * pl;
      target.neck_reach += 0.22 * pl;
      target.head_tilt += 0.45 * pl * (pet.side || 1);
      target.tail_curl += 0.5 * pl;
      target.glow += 0.30 * pl;
      if (pet.region === 'back') { target.tail_raise += 0.3 * pl; target.front_lower -= 0.1 * pl; }
      if (pet.region === 'jaw') { target.neck_raise += 0.35 * pl; target.head_pitch -= 0.35 * pl; }
    }
    if (pet.level > 0.55 && t - pet.last > 0.6 && t - pet.last < 0.7 && Math.random() < 0.5) this._play('nuzzle', { point: pet.point.clone(), side: pet.side });

    // --- clips ----------------------------------------------------------
    let gazeOverride = null, gazeW = 0;
    const add = {};
    this.clips = this.clips.filter((c) => t - c.start < c.dur);
    for (const c of this.clips) {
      const u = (t - c.start) / c.dur;
      const off = c.fn(u, t - c.start, this);
      for (const [k, v] of Object.entries(off)) add[k] = (add[k] ?? 0) + v;
      if (c.gaze) {
        const g = typeof c.gaze === 'function' ? c.gaze(u, this) : c.gaze;
        const w = c.gazeW ? c.gazeW(u) : env(u, 0.1, 0.85);
        if (g && w > gazeW) { gazeOverride = g; gazeW = w; }
      }
    }
    for (const [k, v] of Object.entries(add)) if (k in target) target[k] += v;

    // --- movimiento secundario ------------------------------------------
    const n1 = Math.sin(t * 0.31) * 0.6 + Math.sin(t * 0.77 + 1.3) * 0.4;
    const n2 = Math.sin(t * 0.23 + 2.1) * 0.6 + Math.sin(t * 0.61 + 0.4) * 0.4;
    const n3 = Math.sin(t * 0.17 + 4.0);
    target.head_tilt += 0.05 * n1;
    target.body_lower += 0.06 * n3;
    target.front_lower += 0.04 * n2;
    target.frill_flare += 0.06 * Math.sin(t * 0.9 + 0.5);
    target.wing_lift += 0.04 * n2;

    // --- idle ---------------------------------------------------------------
    if (t > this.nextIdle) {
      const m = this.mood;
      const options = [[1.0, 'lookAround'], [0.5, 'sniffAir'], [0.35, 'headShake'], [0.35, 'lickLips'], [0.4, 'weightShift']];
      if (m === 'calma' || m === 'alegria') options.push([0.25, 'stretch']);
      if (m === 'somnolencia') options.push([1.2, 'yawn'], [1.0, 'nod']);
      if (m === 'alegria') options.push([0.8, 'happyHop']);
      if (m === 'juego') options.push([1.0, 'pounce'], [0.6, 'tailLook']);
      if (m === 'enfado') options.push([0.9, 'growl']);
      if (m === 'desconfianza') options.push([0.8, 'lookAround']);
      if (m === 'curiosidad') options.push([0.8, 'sniffAir'], [0.6, 'tiltCurious']);
      if (!this.clips.length && this.pet.level < 0.1) this._play(pick(options));
      this.nextIdle = t + rnd(3.5, 8) / (0.6 + 0.4 * st.react);
    }

    // --- mirada / atención ---------------------------------------------
    const cur = this.cursor;
    cur.interest = Math.max(0, cur.interest - dt * 0.22);
    const follow = cur.interest > 0.3 && t - cur.last < 2.5;
    let gp = follow ? cur.point : this.viewer;
    if (!follow && t > this.gaze.nextGlance) {
      // miradas ocasionales a otro sitio
      const hp = this.rig.worldPos('head');
      this.gaze.glance = hp.clone().add(new THREE.Vector3(rnd(-3, 3), rnd(-1.2, 0.6), rnd(1, 4)));
      this.gaze.glanceUntil = t + rnd(0.8, 2.2);
      this.gaze.nextGlance = t + rnd(4, 10);
    }
    if (!follow && t < this.gaze.glanceUntil && this.gaze.glance) gp = this.gaze.glance;
    if (pl > 0.2) gp = pet.point;
    if (gazeOverride) gp = gp.clone().lerp(gazeOverride, gazeW);
    this.gaze.point.copy(gp);
    // la mirada suavizada (la cabeza va con retraso)
    const k = 1 - Math.exp(-dt * 6);
    this.gaze.smooth.lerp(gp, k);
    const headFollow = st.follow * (1 - 0.6 * pl);
    this._headToward(target, this.gaze.smooth, headFollow);

    // --- parpadeo ------------------------------------------------------
    const bl = this._blink(t, st);

    // --- muelles -------------------------------------------------------
    const out = {}, outSlow = {};
    // ajustes perceptivos: párpados que acompañan la mirada vertical, pupila según cercanía e interés
    {
      const hb = this.rig.get('head');
      const hp = this.rig.worldPos('head');
      const inv = hb.matrixWorld.clone().invert();
      const g = this.gaze.point.clone().applyMatrix4(inv).normalize();
      const restAx = this.rig.restOf('head');
      void restAx;
      // elevación aproximada respecto al plano de la cabeza (eje Y local = hacia el hocico)
      const elev = Math.asin(THREE.MathUtils.clamp(g.z, -1, 1));
      target.lid_up += THREE.MathUtils.clamp(-elev, -0.5, 0.5) * 0.35;
      const camD = this.viewer.distanceTo(hp);
      target.pupil += (camD < 1.4 ? -0.12 * (1.4 - camD) : 0) + 0.12 * Math.min(1, this.cursor.interest);
    }
    // muelles: membranas (gorgueras, abanico) subamortiguadas para un rebote orgánico
    for (const p of this.params) {
      const om = OMEGA(p);
      if (/^frill|^fan/.test(p)) {
        out[p] = springZ(this.fast[p], target[p], om * 1.2, 0.42, dt);
        outSlow[p] = springZ(this.slow[p], target[p], om * 0.8, 0.38, dt);
      } else {
        out[p] = spring(this.fast[p], target[p], om, dt);
        outSlow[p] = spring(this.slow[p], target[p], om * 0.55, dt);
      }
    }
    out.lid_up = out.lid_up + (1.0 - out.lid_up) * bl;
    out.lid_lo = out.lid_lo + (0.92 - out.lid_lo) * bl;

    // --- respiración -----------------------------------------------------
    const [rate, depth] = st.breath;
    const purr = pl > 0.2;
    this.breathPhase += dt * 2 * Math.PI * (purr ? rate * 0.8 : rate);
    const br = 0.5 + 0.5 * Math.sin(this.breathPhase);
    out.breath = depth * br;
    // las narinas se abren al inspirar
    const inhale = Math.max(0, Math.cos(this.breathPhase));
    out.nostril = Math.max(out.nostril, 0.22 * inhale * depth);
    out.throat = Math.max(out.throat, purr ? 0.08 + 0.06 * Math.sin(t * 52) * pl : 0);
    out.glow = out.glow * (0.82 + 0.18 * br) + (purr ? 0.12 * pl * (0.5 + 0.5 * Math.sin(t * 7)) : 0);
    out.chestBreath = br;
    out.blink = bl;
    if (t >= this._sacc.next) {
      const dist = this.gaze.point.distanceTo(this.rig.worldPos('head'));
      this._sacc = { next: t + rnd(0.25, 0.9), off: new THREE.Vector3(rnd(-1, 1), rnd(-1, 1), rnd(-1, 1)).multiplyScalar(0.012 * dist) };
    }
    const eyeGaze = this.gaze.point.clone().add(this._sacc.off);
    return { values: out, slow: outSlow, gaze: eyeGaze, tail: this._tailMotion(dt, t, st) };
  }

  _headToward(target, point, follow) {
    const rig = this.rig;
    const base = rig.worldPos('neck2');
    const d = point.clone().sub(base);
    const m = rig.model.matrixWorld.clone().invert();
    d.transformDirection(m);
    const yaw0 = Math.atan2(d.x, d.z);
    const yaw = Math.atan2(Math.sin(yaw0 - this.bodyYaw), Math.cos(yaw0 - this.bodyYaw));
    this.relYaw = yaw;
    const horiz = Math.hypot(d.x, d.z);
    const elev = Math.atan2(d.y - 0.45, horiz);
    target.head_yaw += clamp(yaw * follow / 0.98, -1.35, 1.35);
    target.head_pitch += clamp((-elev * follow) / 0.74, -0.7, 0.8);
  }

  _blink(t, st) {
    const b = this.blink;
    if (t > b.next) {
      b.start = t;
      b.slow = this.mood === 'ternura' ? Math.random() < 0.5 : this.mood === 'somnolencia' ? Math.random() < 0.7 : false;
      b.dur = b.slow ? rnd(0.7, 1.3) : rnd(0.16, 0.24);
      b.double = !b.slow && Math.random() < 0.18;
      b.next = t + rnd(st.blink[0], st.blink[1]) + (b.double ? 0.35 : 0);
      if (this.mood === 'somnolencia' && Math.random() < 0.3) b.dur = rnd(1.5, 2.8);
    }
    const u = (t - b.start) / b.dur;
    let v = 0;
    if (u >= 0 && u <= 1) v = u < 0.35 ? smooth(u / 0.35) : u < 0.5 ? 1 : 1 - smooth((u - 0.5) / 0.5);
    if (b.double) {
      const u2 = (t - b.start - b.dur - 0.08) / b.dur;
      if (u2 >= 0 && u2 <= 1) v = Math.max(v, u2 < 0.35 ? smooth(u2 / 0.35) : u2 < 0.5 ? 1 : 1 - smooth((u2 - 0.5) / 0.5));
    }
    for (const c of this.clips) if (c.blink) v = Math.max(v, c.blink((t - c.start) / c.dur));
    return v;
  }

  _tailMotion(dt, t, st) {
    const tl = this.tail;
    tl.impulse *= Math.exp(-dt * 1.4);
    let [amp, freq] = st.tail;
    amp += 0.05 * this.pet.level;
    tl.phase += dt * freq;
    return { amp, phase: tl.phase, impulse: tl.impulse, impSide: tl.side, t };
  }
}

// ---------------------------------------------------------------------------
// Biblioteca de reacciones. Cada una: { dur, fn(u, s) -> offsets, gaze?, status?, blink? }
// Se usan anticipación (movimiento contrario breve), acción y recuperación.
// ---------------------------------------------------------------------------
const sideOf = (o) => (o.side ?? (Math.random() < 0.5 ? -1 : 1));

const CLIPS = {
  sniff: (o) => ({ dur: rnd(1.4, 1.9), status: 'olfatea tu mano', gaze: o.point,
    fn: (u) => ({ nostril: 0.9 * Math.abs(Math.sin(u * Math.PI * 4.5)) * env(u, 0.1, 0.85),
      neck_reach: 0.22 * env(u, 0.25, 0.7), head_pitch: 0.06 * Math.sin(u * Math.PI * 9) * env(u),
      lid_up: -0.15 * env(u), pupil: 0.15 * env(u), frill_flare: 0.25 * env(u) }) }),

  sneeze: (o) => ({ dur: 1.5, status: 'estornuda', gaze: o.point, blocking: true,
    fn: (u) => {
      const a = smooth(u / 0.45) * (u < 0.5 ? 1 : 0);            // anticipación
      const s = bump(u, 0.52, 0.06);                               // estornudo
      const r = u > 0.5 ? 1 - smooth((u - 0.5) / 0.5) : 0;
      return { neck_raise: 0.35 * a - 0.2 * s, head_pitch: -0.25 * a + 0.75 * s, neck_reach: 0.45 * s,
        nostril: a + 0.3 * r, lid_up: 0.4 * a + 0.6 * s, jaw_open: 0.12 * a + 0.35 * s,
        glow: 0.9 * s, throat: 0.8 * s, frill_flare: 0.6 * s, wing_lift: 0.3 * s };
    }, blink: (u) => bump(u, 0.53, 0.05) }),

  lick: (o) => ({ dur: 1.6, status: 'te da un lametón', gaze: o.point,
    fn: (u) => ({ jaw_open: 0.38 * bump(u, 0.45, 0.2), tongue_out: 1.2 * bump(u, 0.47, 0.13),
      neck_reach: 0.3 * env(u, 0.3, 0.6), smile: 0.6 * env(u), lid_up: 0.25 * env(u), pupil: 0.2 * env(u) }) }),

  crossEyed: (o) => ({ dur: 2.0, status: 'mira tu dedo con atención', gaze: o.point,
    gazeW: (u) => env(u, 0.05, 0.9),
    fn: (u) => ({ neck_raise: 0.22 * env(u, 0.15), lid_up: -0.3 * env(u), pupil: 0.35 * env(u),
      frill_flare: 0.4 * env(u), head_tilt: 0.25 * Math.sin(u * Math.PI), brow_down: -0.5 * env(u) }) }),

  chinScratch: (o) => ({ dur: 2.6, status: 'levanta la barbilla, encantado', gaze: o.point,
    fn: (u) => ({ neck_raise: 0.45 * env(u, 0.25), head_pitch: -0.45 * env(u, 0.25), lid_up: 0.6 * env(u, 0.3),
      lid_lo: 0.3 * env(u), smile: 0.7 * env(u), glow: 0.3 * env(u), frill_flare: -0.3 * env(u),
      head_tilt: 0.3 * sideOf(o) * env(u) }) }),

  eyePoke: (o) => {
    const sd = sideOf(o);
    return { dur: 1.6, status: 'cierra los ojos de golpe', blocking: true, gaze: o.point, gazeW: (u) => (u < 0.2 ? 0 : env(u)),
      fn: (u) => ({ neck_raise: 0.6 * env(u, 0.06, 0.45), head_yaw: -0.35 * sd * env(u, 0.08, 0.5),
        brow_down: 0.9 * env(u), frill_flare: -0.6 * env(u, 0.05), body_lower: 0.4 * env(u),
        lid_up: 0.3 * env(u), snarl: 0.4 * env(u, 0.1, 0.4), pupil: -0.2 * env(u) }),
      blink: (u) => env(u, 0.03, 0.35) };
  },

  hornShake: (o) => ({ dur: 1.6, status: 'sacude la cabeza', gaze: o.point, gazeW: (u) => 0.4 * env(u),
    fn: (u) => ({ head_yaw: 0.18 * Math.sin(u * Math.PI * 6) * (1 - u), head_tilt: 0.3 * Math.sin(u * Math.PI * 6 + 1) * (1 - u),
      frill_flare: 0.5 * Math.abs(Math.sin(u * Math.PI * 6)) * (1 - u), brow_down: 0.3 * env(u) }),
    blink: (u) => bump(u, 0.15, 0.06) }),

  frillFlick: (o) => ({ dur: 1.3, status: 'despliega las gorgueras', gaze: o.point, gazeW: (u) => 0.5 * env(u),
    fn: (u) => ({ frill_flare: 1.2 * env(u, 0.08, 0.5) + 0.3 * Math.sin(u * 20) * (1 - u), frill_spread: 1.0 * env(u, 0.08, 0.5),
      head_tilt: 0.2 * Math.sin(u * Math.PI), glow: 0.3 * env(u) }) }),

  nuzzle: (o) => ({ dur: 1.9, status: 'busca tu mano', gaze: o.point,
    fn: (u) => ({ neck_reach: 0.55 * env(u, 0.3, 0.55), head_tilt: 0.4 * (o.side || 1) * env(u), lid_up: 0.55 * env(u),
      smile: 0.7 * env(u), frill_flare: -0.4 * env(u), glow: 0.2 * env(u), head_pitch: 0.12 * Math.sin(u * Math.PI * 3) }) }),

  lookWing: (o) => ({ dur: 2.4, status: 'mira su ala', gaze: o.point,
    fn: (u) => ({ wing_lift: 0.25 * env(u), frill_flare: 0.3 * env(u), lid_up: -0.15 * env(u), wing_open: 0.08 * bump(u, 0.6, 0.15) }) }),

  stretch: () => ({ dur: rnd(3.6, 4.6), status: 'estira las alas', blocking: true,
    fn: (u) => ({ wing_open: 1.0 * env(u, 0.3, 0.62), wing_lift: 0.6 * env(u, 0.25, 0.65), neck_raise: 0.35 * env(u, 0.3, 0.6),
      head_pitch: -0.2 * env(u, 0.3, 0.6), jaw_open: 0.45 * bump(u, 0.5, 0.12), lid_up: 0.5 * bump(u, 0.5, 0.15),
      frill_spread: 0.8 * env(u, 0.3, 0.6), frill_flare: 0.5 * env(u, 0.3, 0.6), front_lower: 0.4 * bump(u, 0.2, 0.12),
      tail_raise: 0.3 * env(u) }) }),

  wingFlick: (o) => ({ dur: 1.1, status: 'sacude el ala', gaze: o.point, gazeW: (u) => 0.6 * env(u),
    fn: (u) => ({ wing_open: 0.32 * bump(u, 0.35, 0.15), wing_lift: 0.5 * bump(u, 0.3, 0.12), frill_flare: 0.2 * env(u) }) }),

  tailFlick: (o, s) => ({ dur: 1.8, status: 'agita la cola', gaze: o.point, gazeW: (u) => 0.7 * env(u, 0.15, 0.6),
    onStart: (b) => { b.tail.impulse = 1.0; b.tail.side = Math.random() < 0.5 ? -1 : 1; b.excite += 0.2; },
    fn: (u) => ({ fan_spread: 1.0 * env(u, 0.1, 0.5), fan_raise: 0.5 * env(u), tail_raise: 0.35 * env(u, 0.1, 0.5) }) }),

  tailLook: (o) => ({ dur: 2.6, status: 'se gira para mirar su cola', gaze: (u, b) => o.point || b.rig.worldPos('tail08'),
    fn: (u) => ({ tail_curl: 0.9 * env(u, 0.3), fan_spread: 0.6 * env(u), lid_up: -0.2 * env(u), pupil: 0.3 * env(u) }) }),

  shiver: (o) => ({ dur: 0.9, status: 'se estremece', gaze: o.point, gazeW: (u) => 0.6 * env(u, 0.2),
    fn: (u) => ({ shoulders_up: 0.5 * Math.sin(u * 60) * (1 - u), body_lower: 0.15 * Math.sin(u * 47) * (1 - u),
      frill_flare: 0.3 * env(u), wing_lift: 0.2 * Math.sin(u * 55) * (1 - u) }) }),

  pawLift: (o, s) => ({ dur: 1.5, status: 'levanta la pata', gaze: o.point, gazeW: (u) => 0.7 * env(u),
    onStart: (b) => { b.ikLift = { leg: o.leg, start: b.t, dur: 1.5 }; },
    fn: (u) => ({ head_pitch: 0.15 * env(u), body_lower: 0.2 * env(u) }) }),

  snap: (o) => ({ dur: 1.4, status: 'lanza una dentellada', gaze: o.point, blocking: true,
    fn: (u) => {
      const a = env(u, 0.18, 0.25) * (u < 0.3 ? 1 : 0);
      const l = bump(u, 0.36, 0.08);
      const rec = env(u, 0.3, 0.5);
      return { neck_raise: 0.35 * a - 0.3 * l, neck_reach: 0.9 * l, jaw_open: 0.25 * a + 0.75 * l, snarl: 0.6 * rec,
        frill_flare: 0.6 * rec, glow: 0.8 * rec, throat: 0.8 * rec, head_pitch: -0.15 * a + 0.2 * l, wing_open: 0.25 * l };
    } }),

  growl: (o = {}) => ({ dur: 2.2, status: 'gruñe por lo bajo', gaze: o.point,
    fn: (u) => ({ snarl: 1.0 * env(u, 0.15), jaw_open: 0.18 * env(u) + 0.03 * Math.sin(u * 80), throat: 1.0 * env(u),
      glow: 0.6 * env(u) * (0.7 + 0.3 * Math.sin(u * 30)), head_pitch: 0.2 * env(u), lid_up: 0.2 * env(u),
      body_lower: 0.3 * env(u), nostril: 0.7 * env(u) }) }),

  flinch: (o) => {
    const sd = sideOf(o);
    return { dur: 1.7, status: 'retrocede con cautela', gaze: o.point,
      fn: (u) => ({ neck_raise: 0.55 * env(u, 0.1, 0.45), head_yaw: -0.3 * sd * env(u, 0.1, 0.5), lid_up: 0.35 * env(u),
        body_lower: 0.6 * env(u, 0.1), frill_flare: -0.7 * env(u), pupil: -0.1 * env(u), snarl: 0.3 * env(u, 0.2, 0.5),
        wing_lift: -0.3 * env(u) }) };
  },

  startle: (o = {}) => ({ dur: 1.5, status: 'da un respingo', gaze: o.point, blocking: true,
    fn: (u) => ({ neck_raise: 0.8 * env(u, 0.06, 0.45), wing_open: 0.55 * bump(u, 0.2, 0.12), wing_lift: 0.8 * env(u, 0.06, 0.4),
      lid_up: -0.5 * env(u, 0.04), pupil: 0.5 * env(u, 0.04), frill_flare: 1.0 * env(u, 0.05), frill_spread: 0.9 * env(u, 0.05),
      body_lower: -0.6 * bump(u, 0.15, 0.1), jaw_open: 0.25 * bump(u, 0.18, 0.1), tail_raise: 0.4 * env(u) }) }),

  drowsy: (o) => ({ dur: 2.2, status: 'abre un ojo, perezoso', gaze: o.point, gazeW: (u) => 0.5 * env(u, 0.4),
    fn: (u) => ({ lid_up: -0.35 * env(u, 0.35, 0.7), neck_raise: 0.15 * env(u, 0.4) }) }),

  yawn: () => ({ dur: rnd(3.0, 3.8), status: 'bosteza', blocking: true,
    fn: (u) => {
      const j = env(u, 0.35, 0.62);
      return { jaw_open: 1.05 * j, neck_raise: 0.35 * j, head_pitch: -0.3 * j, lid_up: 0.75 * j, tongue_out: 0.3 * j,
        frill_spread: 0.9 * j, frill_flare: 0.4 * j, nostril: 0.6 * j, throat: 0.25 * j, wing_lift: 0.3 * j };
    } }),

  nod: () => ({ dur: 2.8, status: 'cabecea', fn: (u) => ({ head_pitch: 0.35 * env(u, 0.6, 0.75) - 0.25 * bump(u, 0.82, 0.05), lid_up: 0.3 * env(u, 0.5, 0.8) }) }),

  pounce: (o = {}) => ({ dur: 1.6, status: 'se agazapa para jugar', gaze: o.point,
    onStart: (b) => { b.excite += 0.3; },
    fn: (u) => ({ front_lower: 0.9 * env(u, 0.25, 0.45) - 0.6 * bump(u, 0.58, 0.07), body_lower: -0.4 * bump(u, 0.58, 0.08),
      tail_raise: 0.4 * env(u), wing_open: 0.18 * bump(u, 0.6, 0.08), pupil: 0.2 * env(u), head_pitch: -0.15 * env(u),
      jaw_open: 0.2 * bump(u, 0.6, 0.1) }) }),

  happyHop: () => ({ dur: 1.8, status: 'da saltitos de alegría',
    fn: (u) => ({ body_lower: -0.45 * Math.max(0, Math.sin(u * Math.PI * 4)) * (1 - u), wing_lift: 0.5 * Math.abs(Math.sin(u * Math.PI * 4)) * (1 - u),
      neck_raise: 0.2 * Math.sin(u * Math.PI * 4 + 0.6) * (1 - u), frill_flare: 0.5 * env(u), smile: 0.5 * env(u) }) }),

  lookAround: (o, b) => {
    const hp = b.rig.worldPos('head');
    const pts = [0, 1, 2].map(() => hp.clone().add(new THREE.Vector3(rnd(-3.5, 3.5), rnd(-1.2, 0.8), rnd(0.5, 4))));
    return { dur: rnd(3.0, 4.5), gaze: (u) => pts[Math.min(2, Math.floor(u * 3))], gazeW: (u) => env(u, 0.1, 0.85),
      fn: () => ({}) };
  },

  sniffAir: () => ({ dur: 2.2, status: 'olfatea el aire',
    fn: (u) => ({ neck_raise: 0.3 * env(u, 0.25), head_pitch: -0.3 * env(u, 0.25), nostril: 0.8 * Math.abs(Math.sin(u * Math.PI * 5)) * env(u),
      lid_up: 0.2 * env(u), frill_flare: 0.2 * env(u) }) }),

  headShake: () => ({ dur: 1.4, status: 'sacude la cabeza',
    fn: (u) => ({ head_yaw: 0.16 * Math.sin(u * Math.PI * 7) * (1 - u), head_tilt: 0.35 * Math.sin(u * Math.PI * 7 + 0.8) * (1 - u),
      frill_flare: 0.6 * Math.abs(Math.sin(u * Math.PI * 7)) * (1 - u) }),
    blink: (u) => bump(u, 0.2, 0.08) }),

  lickLips: () => ({ dur: 1.2, fn: (u) => ({ jaw_open: 0.14 * bump(u, 0.5, 0.2), tongue_out: 0.7 * bump(u, 0.5, 0.12), smile: 0.2 * env(u) }) }),

  weightShift: () => ({ dur: 2.5, fn: (u) => ({ body_lower: 0.25 * Math.sin(u * Math.PI), front_lower: -0.12 * Math.sin(u * Math.PI), tail_side: 0.4 * Math.sin(u * Math.PI) }) }),

  tiltCurious: () => ({ dur: 2.0, status: 'ladea la cabeza', fn: (u) => ({ head_tilt: (Math.random() < 0.5 ? 1 : -1) * 0 + 0.6 * env(u, 0.2), lid_up: -0.2 * env(u), pupil: 0.2 * env(u) }) }),
};
