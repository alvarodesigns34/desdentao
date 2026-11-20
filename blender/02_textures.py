"""
Paso 2 — Texturas procedurales (Python del sistema, numpy + Pillow).

    python3 blender/02_textures.py

Genera en assets/textures/:
  scales_height.png   (16 bit)  relieve de escamas, mosaico continuo
  scales_normal.png             normal map tangente (para tiempo real, triplanar)
  scales_data.png               R: altura  G: valor aleatorio por escama  B: cavidad (bordes)
  iris.png                      iris ámbar (la pupila se dibuja en el shader)
  wing_veins.png                R: venas  G: variación de grosor  B: borde de fuga
  bodymap.png                   en espacio 'bodyuv' (u: longitud del cuerpo, v: |ángulo|/pi)
                                R: vetas de brillo (brasa)  G: relieve de placas ventrales  B: máscara ventral
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "textures")
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(7)


def save8(arr, name):
    a = np.clip(arr, 0, 1)
    Image.fromarray((a * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, name), optimize=True)


def save16(arr, name):
    a = np.clip(arr, 0, 1)
    Image.fromarray((a * 65535 + 0.5).astype(np.uint16)).save(os.path.join(OUT, name))


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def tile_noise(n, freq, octaves=4, seed=0):
    """Ruido de valor periódico (mosaico) sumando octavas."""
    r = np.random.default_rng(seed)
    out = np.zeros((n, n))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        f = freq * (2 ** o)
        g = r.random((f, f))
        x = np.arange(n) * f / n
        i0 = np.floor(x).astype(int); t = x - i0
        t = t * t * (3 - 2 * t)
        i1 = (i0 + 1) % f
        a = g[i0][:, i0] * (1 - t)[None, :] + g[i0][:, i1] * t[None, :]
        b = g[i1][:, i0] * (1 - t)[None, :] + g[i1][:, i1] * t[None, :]
        out += amp * (a * (1 - t)[:, None] + b * t[:, None])
        tot += amp; amp *= 0.5
    return out / tot


# ---------------------------------------------------------------------------
# 1. Escamas
# ---------------------------------------------------------------------------
def make_scales(N=2048, cells=34):
    """Escamas tipo reptil: rejilla hexagonal con jitter, cúpulas solapadas."""
    rows = cells
    cols = cells
    jit = 0.28
    # centros (en unidades de celda), periódicos
    cx = np.zeros((rows, cols)); cy = np.zeros((rows, cols))
    for r in range(rows):
        for c in range(cols):
            cx[r, c] = c + 0.5 + (0.5 if r % 2 else 0.0) + (rng.random() - 0.5) * jit
            cy[r, c] = r + 0.5 + (rng.random() - 0.5) * jit
    crand = rng.random((rows, cols))
    csize = 0.85 + 0.3 * rng.random((rows, cols))
    yy, xx = np.mgrid[0:N, 0:N] / N * cells
    ri = np.floor(yy).astype(int); ci = np.floor(xx).astype(int)
    F1 = np.full((N, N), 9.0); F2 = np.full((N, N), 9.0)
    id1 = np.zeros((N, N), int); dx1 = np.zeros((N, N)); dy1 = np.zeros((N, N))
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            r = ri + dr; c = ci + dc
            rr = r % rows; cc = c % cols
            px = cx[rr, cc] + (c - cc); py = cy[rr, cc] + (r - rr)
            # ajuste del desplazamiento hexagonal en filas envueltas
            dx = xx - px; dy = yy - py
            d = np.sqrt(dx * dx + dy * dy) / csize[rr, cc]
            closer = d < F1
            F2 = np.where(closer, F1, np.minimum(F2, d))
            id1 = np.where(closer, rr * cols + cc, id1)
            dx1 = np.where(closer, dx, dx1); dy1 = np.where(closer, dy, dy1)
            F1 = np.where(closer, d, F1)
    edge = F2 - F1                          # distancia al borde
    rnd = crand.ravel()[id1]
    dome = np.sqrt(np.clip(1 - (F1 / 0.75) ** 2, 0, 1))
    h = smoothstep(0.0, 0.22, edge) * (0.55 + 0.45 * dome)
    # solape: cada escama se levanta hacia su borde posterior (+y)
    h += 0.18 * np.clip(dy1, -0.6, 0.6) * smoothstep(0.0, 0.2, edge)
    h *= 0.8 + 0.2 * rnd
    # microrrelieve
    h += 0.05 * (tile_noise(N, 64, 3, seed=3) - 0.5)
    h = (h - h.min()) / (h.max() - h.min())
    cav = 1 - smoothstep(0.0, 0.10, edge)
    save16(h, "scales_height.png")
    save8(np.stack([h, rnd, cav], -1), "scales_data.png")
    # normal map tangente (periódico)
    s = 6.0
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * s
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * s
    n = np.stack([-gx, gy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    save8(n * 0.5 + 0.5, "scales_normal.png")
    print("escamas OK")


# ---------------------------------------------------------------------------
# 2. Iris
# ---------------------------------------------------------------------------
def make_iris(N=1024):
    yy, xx = (np.mgrid[0:N, 0:N] + 0.5) / N * 2 - 1
    r = np.sqrt(xx ** 2 + yy ** 2)
    a = np.arctan2(yy, xx)
    # fibras radiales (ruido en el ángulo, estirado radialmente)
    ang_n = np.zeros_like(r)
    for k, amp in ((90, 0.5), (180, 0.3), (37, 0.4), (260, 0.2)):
        ph = rng.random(8) * 6.28
        ang_n += amp * np.sin(a * k + 3.0 * np.sin(r * 7 + ph[0]) + ph[1])
    ang_n = ang_n * 0.5 + 0.5
    rad_n = tile_noise(N, 8, 4, seed=11)
    c_in = np.array([1.00, 0.78, 0.12])    # oro
    c_mid = np.array([0.95, 0.45, 0.02])   # ámbar
    c_out = np.array([0.45, 0.12, 0.01])   # cobre oscuro
    t = np.clip(r / 0.92, 0, 1)[..., None]
    col = np.where(t < 0.45, c_in + (c_mid - c_in) * (t / 0.45),
                   c_mid + (c_out - c_mid) * ((t - 0.45) / 0.55))
    col = col * (0.72 + 0.45 * ang_n[..., None]) * (0.85 + 0.3 * rad_n[..., None])
    # collarete (anillo claro alrededor de la pupila)
    coll = np.exp(-((r - 0.30) / 0.05) ** 2) * (0.6 + 0.4 * ang_n)
    col += coll[..., None] * np.array([0.35, 0.28, 0.08])
    # motas oscuras
    sp = tile_noise(N, 24, 2, seed=5)
    sp2 = tile_noise(N, 96, 2, seed=6)
    col *= (1 - 0.35 * smoothstep(0.70, 0.80, sp2))[..., None]
    # anillo limbal
    limb = smoothstep(0.80, 0.97, r)
    col *= (1 - 0.92 * limb)[..., None]
    col = np.clip(col, 0, 1)
    # alfa: altura del iris (relieve para bump)
    hgt = 0.5 + 0.5 * (ang_n - 0.5) * (1 - limb)
    save8(np.concatenate([col, hgt[..., None]], -1), "iris.png")
    print("iris OK")


# ---------------------------------------------------------------------------
# 3. Venas de las membranas alares (u: 0..4 paneles, v: raíz->borde)
# ---------------------------------------------------------------------------
def make_wing(W=2048, Hh=512, panels=4):
    img = Image.new("L", (W, Hh), 0)
    dr = ImageDraw.Draw(img)

    def branch(x, y, ang, width, length, depth):
        pts = [(x, y)]
        for i in range(int(length)):
            ang += rng.normal(0, 0.06)
            ang = np.clip(ang, np.pi / 2 - 0.9, np.pi / 2 + 0.9)
            x += np.cos(ang) * 3; y += np.sin(ang) * 3
            pts.append((x, y))
            if depth < 3 and rng.random() < 0.012:
                branch(x, y, ang + rng.choice([-1, 1]) * rng.uniform(0.35, 0.7),
                       max(1, width * 0.6), length * rng.uniform(0.3, 0.6), depth + 1)
        for i in range(len(pts) - 1):
            w = max(1, int(width * (1 - i / len(pts)) + 0.5))
            dr.line([pts[i], pts[i + 1]], fill=255, width=w)

    pw = W / panels
    for p in range(panels):
        for k in range(6):
            x0 = p * pw + pw * (0.08 + 0.84 * (k + rng.random() * 0.6) / 6)
            branch(x0, 0, np.pi / 2 + rng.normal(0, 0.12), 5, Hh / 3 * 1.05, 0)
    v = np.asarray(img.filter(ImageFilter.GaussianBlur(1.6)), float) / 255
    thick = tile_noise(W, 16, 4, seed=21)[:Hh, :W]
    yy = np.arange(Hh)[:, None] / Hh
    edge = smoothstep(0.86, 1.0, yy) * np.ones((1, W))
    save8(np.stack([v, thick, edge], -1), "wing_veins.png")
    print("venas OK")


# ---------------------------------------------------------------------------
# 4. Mapa corporal (bodyuv)
# ---------------------------------------------------------------------------
def make_bodymap(W=4096, Hh=512):
    u = (np.arange(W) + 0.5)[None, :] / W   # 0 = hocico, 1 = punta de la cola
    v = (np.arange(Hh) + 0.5)[:, None] / Hh  # 0 = lomo, 1 = vientre
    # placas ventrales: bandas transversales, más anchas en el torso
    # densidad: ~ 1 placa cada 4,5 cm (longitud total ~ 5,4 m)
    L = 5.4
    s = u * L
    freq = 1 / (0.045 + 0.03 * np.exp(-((u - 0.40) / 0.15) ** 2))
    ph = (np.cumsum(freq[0]) * (L / W))[None, :]
    band = 0.5 - 0.5 * np.cos(2 * np.pi * ph)
    band = smoothstep(0.08, 0.6, band)
    belly = smoothstep(0.62, 0.78, v)
    scute = band * belly
    # vetas de brasa: dos líneas sinuosas por flanco que se ramifican, discontinuas
    glow = np.zeros((Hh, W))
    for v0, amp, fr, w, ph0 in ((0.46, 0.035, 9.0, 0.010, 0.0), (0.58, 0.025, 13.0, 0.007, 1.7),
                                (0.33, 0.02, 7.0, 0.006, 3.1)):
        center = v0 + amp * np.sin(s * fr + ph0) + 0.012 * np.sin(s * fr * 2.7 + ph0)
        d = np.abs(v - center)
        line = np.exp(-(d / w) ** 2)
        dash = smoothstep(0.15, 0.45, 0.5 + 0.5 * np.sin(s * fr * 0.5 + ph0 * 2 + 0.6 * np.sin(s * 3.1)))
        glow += line * dash
    # puntos (fotóforos) a lo largo del flanco inferior
    spots_u = np.arange(0.20, 0.97, 0.018)
    for su in spots_u:
        sv = 0.70 + 0.02 * np.sin(su * 40)
        d2 = ((u - su) * L / 0.012) ** 2 + ((v - sv) / 0.014) ** 2
        glow += 0.9 * np.exp(-d2)
    # sólo en cuello, torso y cola (no en la cabeza)
    glow *= smoothstep(0.12, 0.20, u) * (1 - smoothstep(0.985, 1.0, u))
    glow = np.clip(glow, 0, 1)
    belly = belly * np.ones((1, W))
    save8(np.stack([glow, scute, belly], -1), "bodymap.png")
    print("bodymap OK")


def _cells(N, cols, rows, jit, seed, hexo=True):
    r = np.random.default_rng(seed)
    cx = np.zeros((rows, cols)); cy = np.zeros((rows, cols))
    for i in range(rows):
        for j in range(cols):
            cx[i, j] = j + 0.5 + (0.5 if (hexo and i % 2) else 0) + (r.random() - 0.5) * jit
            cy[i, j] = i + 0.5 + (r.random() - 0.5) * jit
    return cx, cy, r.random((rows, cols)), 0.8 + 0.4 * r.random((rows, cols))


def _voronoi(N, cols, rows, cx, cy, size, aniso=(1.0, 1.0)):
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    xx = xx / N * cols; yy = yy / N * rows
    ri = np.floor(yy).astype(int); ci = np.floor(xx).astype(int)
    F1 = np.full((N, N), 9.0, np.float32); F2 = np.full((N, N), 9.0, np.float32)
    idc = np.zeros((N, N), int); DX = np.zeros((N, N), np.float32); DY = np.zeros((N, N), np.float32)
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            r_ = ri + dr; c_ = ci + dc
            rr = r_ % rows; cc = c_ % cols
            dx = (xx - (cx[rr, cc] + (c_ - cc))) * aniso[0]
            dy = (yy - (cy[rr, cc] + (r_ - rr))) * aniso[1]
            d = np.sqrt(dx * dx + dy * dy) / size[rr, cc]
            cl = d < F1
            F2 = np.where(cl, F1, np.minimum(F2, d)); idc = np.where(cl, rr * cols + cc, idc)
            DX = np.where(cl, dx, DX); DY = np.where(cl, dy, DY); F1 = np.where(cl, d, F1)
    return F1, F2, idc, DX, DY


def _save_set(name, h, rnd, cav):
    h = (h - h.min()) / (h.max() - h.min())
    save16(h, f"{name}_height.png")
    save8(np.stack([h, rnd, cav], -1), f"{name}_data.png")
    print(name, "OK")


def make_granular(N=2048, cells=56):
    """Escama granular (tubérculos redondeados, sin solape): cabeza, articulaciones, patas."""
    cx, cy, rnd, size = _cells(N, cells, cells, 0.55, 31)
    F1, F2, idc, DX, DY = _voronoi(N, cells, cells, cx, cy, size)
    edge = F2 - F1
    dome = np.sqrt(np.clip(1 - (F1 / 0.62) ** 2, 0, 1))
    r = rnd.ravel()[idc]
    h = smoothstep(0.0, 0.16, edge) * (0.35 + 0.65 * dome) * (0.75 + 0.25 * r)
    h += 0.04 * (tile_noise(N, 128, 2, seed=8) - 0.5)
    _save_set("granular", h, r, 1 - smoothstep(0.0, 0.07, edge))


def make_keeled(N=2048, cols=26, rows=40):
    """Escama aquillada imbricada (lomo, cuello, cola). Eje X = a lo largo del cuerpo (hacia la cola)."""
    cx, cy, rnd, size = _cells(N, cols, rows, 0.25, 47)
    F1, F2, idc, DX, DY = _voronoi(N, cols, rows, cx, cy, size, aniso=(0.62, 1.0))
    edge = F2 - F1
    r = rnd.ravel()[idc]
    # imbricación: cada escama sube hacia su borde posterior (+x) y cae bajo la siguiente
    slope = np.clip(0.5 + 0.9 * DX, 0, 1.2)
    keel = np.exp(-(DY / 0.06) ** 2) * np.clip(0.3 + DX * 1.2, 0, 1)   # quilla central
    h = smoothstep(0.0, 0.12, edge) * (0.45 * slope + 0.35 * keel + 0.2) * (0.8 + 0.2 * r)
    h += 0.03 * (tile_noise(N, 128, 2, seed=9) - 0.5)
    _save_set("keeled", h, r, 1 - smoothstep(0.0, 0.06, edge))


if __name__ == "__main__":
    if "--nuevas" in sys.argv:
        make_granular(); make_keeled(); sys.exit(0)
    make_scales()
    make_iris()
    make_wing()
    make_bodymap()
