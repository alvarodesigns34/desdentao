// Interfaz: selector de ánimo, modos, cámaras, capas de inspección, estado y ayudas.
import { PRESETS } from './camera.js';

const $ = (s, r = document) => r.querySelector(s);

export class UI {
  constructor() {
    this.onMode = null; this.onCamera = null; this.onCinema = null; this.onToggle = null;
    this.statusEl = $('#status-text');
    this.ember = $('#ember');
    this._lastStatus = '';
    this._bind();
  }

  _bind() {
    // modo
    for (const b of document.querySelectorAll('[data-mode-btn]')) {
      b.addEventListener('click', () => {
        document.querySelectorAll('[data-mode-btn]').forEach((x) => x.setAttribute('aria-pressed', x === b));
        this.onMode?.(b.dataset.modeBtn);
      });
    }
    // cámaras
    const list = $('#cam-list');
    for (const [k, p] of Object.entries(PRESETS)) {
      const li = document.createElement('button');
      li.className = 'menu-item'; li.textContent = p.label; li.dataset.cam = k;
      li.addEventListener('click', () => { this.onCamera?.(k); this._closeMenus(); });
      list.appendChild(li);
    }
    for (const t of document.querySelectorAll('[data-menu]')) {
      t.addEventListener('click', (e) => {
        e.stopPropagation();
        const m = $(`#${t.dataset.menu}`);
        const open = m.hasAttribute('hidden');
        this._closeMenus();
        if (open) { m.removeAttribute('hidden'); t.setAttribute('aria-expanded', 'true'); }
      });
    }
    document.addEventListener('pointerdown', (e) => { if (!e.target.closest('.menu, [data-menu]')) this._closeMenus(); });
    $('#cine').addEventListener('click', () => {
      const on = $('#cine').getAttribute('aria-pressed') !== 'true';
      this.setCinema(on); this.onCinema?.(on);
    });
    for (const c of document.querySelectorAll('[data-toggle]')) {
      c.addEventListener('change', () => this.onToggle?.(c.dataset.toggle, c.checked));
    }
    $('#help').addEventListener('click', () => this.showHint(true));
    $('#hint-close').addEventListener('click', () => this.showHint(false));
  }

  _closeMenus() {
    document.querySelectorAll('.menu').forEach((m) => m.setAttribute('hidden', ''));
    document.querySelectorAll('[data-menu]').forEach((t) => t.setAttribute('aria-expanded', 'false'));
  }

  buildMoods(moods, cb) {
    const nav = $('#moods');
    const mk = (key, label) => {
      const b = document.createElement('button');
      b.className = 'chip'; b.dataset.mood = key ?? 'auto';
      b.innerHTML = `<span class="dot" aria-hidden="true"></span>${label}`;
      b.addEventListener('click', () => { cb(key); this._markMood(key); this.dismissHintSoon(); });
      nav.appendChild(b);
    };
    mk(null, 'Autónomo');
    for (const [k, m] of Object.entries(moods)) mk(k, m.label);
    this._markMood(null);
  }

  _markMood(user, current) {
    for (const c of document.querySelectorAll('.chip')) {
      const k = c.dataset.mood;
      c.setAttribute('aria-pressed', String(user ? k === user : k === 'auto'));
      c.classList.toggle('is-current', !user && k === current);
    }
  }

  status(text, mood, user) {
    if (text !== this._lastStatus) {
      this._lastStatus = text;
      const el = this.statusEl;
      el.classList.add('is-out');
      setTimeout(() => { el.textContent = text; el.classList.remove('is-out'); }, 140);
    }
    if (mood !== this._mood || user !== this._user) { this._mood = mood; this._user = user; this._markMood(user, mood); }
  }

  pulse(glow, breath) {
    const s = 0.75 + 0.35 * breath;
    this.ember.style.transform = `scale(${s.toFixed(3)})`;
    this.ember.style.opacity = (0.45 + 0.55 * Math.min(1, glow * 1.4)).toFixed(3);
  }

  progress(f) {
    $('#loader-bar').style.transform = `scaleX(${f.toFixed(3)})`;
    $('#loader-pct').textContent = `${Math.round(f * 100)}`;
  }

  ready() {
    document.body.classList.add('is-ready');
    setTimeout(() => this.showHint(true), 1200);
    this._hintTimer = setTimeout(() => this.showHint(false), 14000);
    document.getElementById('scene').addEventListener('pointerdown', () => this.dismissHintSoon(), { once: true });
  }

  showHint(on) {
    const h = $('#hint');
    if (on) h.removeAttribute('hidden'); else h.setAttribute('hidden', '');
  }

  dismissHintSoon() { clearTimeout(this._hintTimer); this._hintTimer = setTimeout(() => this.showHint(false), 2500); }

  setCinema(on) {
    $('#cine').setAttribute('aria-pressed', String(on));
    document.body.classList.toggle('is-cinema', on);
  }

  stats(s) {
    $('#st-tris').textContent = Math.round(s.tris).toLocaleString('es-ES');
    $('#st-bones').textContent = s.bones;
    $('#st-morphs').textContent = s.morphs;
    $('#st-q').textContent = s.quality;
  }

  fps(f) { $('#st-fps').textContent = f.toFixed(0); }

  touchMark(x, y) {
    const d = document.createElement('div');
    d.className = 'touch'; d.style.left = `${x}px`; d.style.top = `${y}px`;
    document.body.appendChild(d);
    setTimeout(() => d.remove(), 700);
  }

  touchTrail(x, y) {
    const d = document.createElement('div');
    d.className = 'trail'; d.style.left = `${x}px`; d.style.top = `${y}px`;
    document.body.appendChild(d);
    setTimeout(() => d.remove(), 600);
  }
}
