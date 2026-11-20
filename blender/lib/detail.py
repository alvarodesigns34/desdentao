"""
Capa de detalle anatómico para el SDF de Vesper (desplazamiento cerca de la superficie).

Se aplica después de la unión de primitivas, sólo en una banda estrecha alrededor de la
superficie, y añade lo que hace que una criatura parezca real y no "inflada":
  * irregularidad orgánica de la piel (ruido multiescala + tubérculos)
  * osteodermos en hileras alternas sobre lomo, cuello y cola
  * placas ventrales con surcos transversales
  * pliegues transversales del cuello y de la garganta
  * anillos (verticilos) de la cola y surco lateral de su musculatura
  * costillas insinuadas en los flancos
  * pliegues de flexión en codos, muñecas, rodillas y corvejones
  * placas craneales (escudos) en hocico y cráneo
Convención: valor positivo = relieve hacia fuera (el campo disminuye).
"""
import numpy as np
import anatomy as A

_rng = np.random.default_rng(1234)
_PERM = np.concatenate([_rng.permutation(256)] * 2).astype(np.int64)
_G = _rng.normal(size=(256, 3)); _G /= np.linalg.norm(_G, axis=1, keepdims=True)


def gnoise(P, freq):
    """Ruido de gradiente 3D (tipo Perlin), salida aprox. en [-1, 1]."""
    p = P * freq
    i = np.floor(p).astype(np.int64)
    f = p - i
    u = f * f * f * (f * (f * 6 - 15) + 10)
    ix, iy, iz = i[:, 0] & 255, i[:, 1] & 255, i[:, 2] & 255
    out = 0
    acc = {}
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                h = _PERM[_PERM[_PERM[(ix + dx) & 255] + ((iy + dy) & 255)] + ((iz + dz) & 255)] & 255
                g = _G[h]
                acc[(dx, dy, dz)] = np.einsum("ij,ij->i", g, f - np.array([dx, dy, dz]))
    lerp = lambda a, b, t: a + (b - a) * t
    x00 = lerp(acc[0, 0, 0], acc[1, 0, 0], u[:, 0]); x10 = lerp(acc[0, 1, 0], acc[1, 1, 0], u[:, 0])
    x01 = lerp(acc[0, 0, 1], acc[1, 0, 1], u[:, 0]); x11 = lerp(acc[0, 1, 1], acc[1, 1, 1], u[:, 0])
    y0 = lerp(x00, x10, u[:, 1]); y1 = lerp(x01, x11, u[:, 1])
    return lerp(y0, y1, u[:, 2]) * 1.6


def fbm(P, freq, octaves=3, gain=0.5):
    s, a, tot = 0, 1.0, 0
    for o in range(octaves):
        s = s + a * gnoise(P + o * 17.3, freq * 2 ** o)
        tot += a; a *= gain
    return s / tot


def worley(P, cell):
    """Distancias F1 y F2 a puntos de una rejilla con jitter (Voronoi 3D)."""
    q = P / cell
    i = np.floor(q).astype(np.int64)
    F1 = np.full(len(P), 9.0); F2 = np.full(len(P), 9.0)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = i + np.array([dx, dy, dz])
                h = _PERM[_PERM[_PERM[c[:, 0] & 255] + (c[:, 1] & 255)] + (c[:, 2] & 255)] & 255
                jit = 0.5 + 0.4 * _G[h]
                d = np.linalg.norm(q - (c + jit), axis=1)
                F2 = np.where(d < F1, F1, np.minimum(F2, d))
                F1 = np.minimum(F1, d)
    return F1, F2


def ss(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def groove(t, sharp=10):
    """Surcos estrechos en los enteros de t (0 fuera del surco, 1 en el fondo)."""
    c = 0.5 + 0.5 * np.cos(2 * np.pi * t)
    return c ** sharp


# ---------------------------------------------------------------------------
class BodyDetail:
    """Detalle definido en coordenadas del cuerpo (s a lo largo de la línea media, ángulo θ)."""

    def __init__(self):
        poly = A.chain_polyline()
        self.poly = poly
        self.seg = poly[1:] - poly[:-1]
        self.L = np.linalg.norm(self.seg, axis=1)
        self.cum = np.concatenate([[0], np.cumsum(self.L)])
        self.total = self.cum[-1]
        def s_at(p):
            d = np.linalg.norm(poly - p, axis=1)
            return self.cum[np.argmin(d)]
        self.s_head = s_at(A.HEAD_O)
        self.s_neck = s_at(A.NECK_PTS[0])
        self.s_hips = s_at(A.SPINE_PTS[0])
        self.s_end = self.total

    def coords(self, P):
        n = len(P)
        bd = np.full(n, 1e9); bs = np.zeros(n); bth = np.zeros(n)
        for i in range(len(self.seg)):
            a = self.poly[i]; d = self.seg[i] / self.L[i]
            t = np.clip((P - a) @ d, 0, self.L[i])
            r = P - (a + t[:, None] * d)
            dd = np.linalg.norm(r, axis=1)
            up = np.array([0, 0, 1.0]) - d * d[2]; up /= np.linalg.norm(up)
            lat = np.cross(d, up)
            th = np.arctan2(r @ lat, r @ up)
            m = dd < bd
            bd = np.where(m, dd, bd); bs = np.where(m, self.cum[i] + t, bs); bth = np.where(m, th, bth)
        return bs, bth, bd

    def disp(self, P):
        s, th, r = self.coords(P)
        ath = np.abs(th)
        out = np.zeros(len(P))
        # --- irregularidad orgánica general ---------------------------------
        out += 0.0011 * fbm(P, 22, 3) + 0.0008 * np.maximum(0, gnoise(P, 70)) ** 2 * 2.0
        body = (s > self.s_head + 0.08)
        tail = s > self.s_hips + 0.15
        # --- osteodermos en hileras alternas (lomo, cuello, cola) -----------
        region = body & (s < self.s_end - 0.45) & (ath < 0.47 * np.pi)
        if region.any():
            sp = 0.034 + 0.055 * np.clip(r, 0.03, 0.30)          # separación a lo largo
            acc = np.zeros(len(P))
            for k, th0 in enumerate((0.10, 0.22, 0.34, 0.45)):
                th0 *= np.pi
                ph = 0.5 * (k % 2)
                u = s / sp + ph
                du = (u - np.round(u)) * sp
                dth = (ath - th0) * r
                a = sp * 0.36; b = np.maximum(0.11 * np.pi * r * 0.42, 0.004)
                q = 1 - (du / a) ** 2 - (dth / b) ** 2
                hgt = (0.0034 - 0.0007 * k) * np.sqrt(np.clip(r / 0.22, 0.25, 1.3))
                acc = np.maximum(acc, hgt * np.clip(q, 0, 1) ** 1.5)
            out += np.where(region, acc, 0)
        # --- placas ventrales -------------------------------------------------
        belly = body & (s < self.s_end - 0.15) & (ath > 0.70 * np.pi) & (r < 0.45)
        if belly.any():
            spv = np.where(s < self.s_hips, 0.052, 0.040)
            g = groove(s / spv, 14) * ss(0.70 * np.pi, 0.80 * np.pi, ath)
            out -= np.where(belly, 0.0026 * g, 0)
            # surco longitudinal que delimita las placas
            side = np.exp(-(((ath - 0.74 * np.pi) / (0.025 * np.pi)) ** 2))
            out -= np.where(belly, 0.0018 * side, 0)
        # --- pliegues del cuello y la garganta -------------------------------
        neck = (s > self.s_head - 0.05) & (s < self.s_neck + 0.05) & (ath > 0.38 * np.pi)
        if neck.any():
            # pliegues irregulares: separación variable, se bifurcan y se desvanecen
            t = s / 0.034 + 1.6 * fbm(P, 4, 3) + 0.25 * (ath / np.pi) * gnoise(P, 3)
            w = ss(0.38 * np.pi, 0.75 * np.pi, ath) * np.clip(0.3 + 0.9 * gnoise(P * 1.3, 6), 0, 1)
            out -= np.where(neck, 0.0024 * groove(t, 5) * w, 0)
        # --- anillos de la cola y surco lateral ------------------------------
        if tail.any():
            rings = 0.0011 * groove(s / 0.024, 8)
            lat = np.exp(-(((ath - 0.55 * np.pi) / (0.05 * np.pi)) ** 2)) * 0.0032 * ss(0.0, 0.12, r)
            out -= np.where(tail, rings + lat, 0)
        # --- costillas en los flancos ----------------------------------------
        ribs = (s > self.s_neck + 0.12) & (s < self.s_hips - 0.25) & (ath > 0.35 * np.pi) & (ath < 0.72 * np.pi)
        if ribs.any():
            t = (s - 0.35 * (ath - 0.35 * np.pi) * r) / 0.085
            c = 0.5 + 0.5 * np.cos(2 * np.pi * t)
            m = np.sin(np.pi * np.clip((ath - 0.35 * np.pi) / (0.37 * np.pi), 0, 1))
            out += np.where(ribs, 0.0028 * c ** 3 * m, 0)
        return out


class SegmentCreases:
    """Pliegues de flexión anulares alrededor de una articulación."""

    def __init__(self, a, b, t_center, n=3, spacing=0.016, depth=0.0024, flex=None, reach=0.16):
        self.a = np.asarray(a, float); self.b = np.asarray(b, float)
        self.d = self.b - self.a; self.Lseg = np.linalg.norm(self.d); self.d /= self.Lseg
        self.tc = t_center * self.Lseg; self.n = n; self.sp = spacing; self.depth = depth
        self.flex = None if flex is None else np.asarray(flex, float) / np.linalg.norm(flex)
        self.reach = reach
        c = self.a + self.d * self.tc
        self.lo = c - reach; self.hi = c + reach

    def disp(self, P):
        out = np.zeros(len(P))
        m = np.all((P > self.lo) & (P < self.hi), axis=1)
        if not m.any():
            return out
        Q = P[m]
        t = (Q - self.a) @ self.d
        rad = Q - (self.a + t[:, None] * self.d)
        rn = rad / np.maximum(np.linalg.norm(rad, axis=1, keepdims=True), 1e-6)
        x = (t - self.tc) / self.sp
        win = np.clip(1 - np.abs(x) / (self.n * 0.5 + 0.5), 0, 1)
        g = groove(x + 0.5 * (self.n % 2 == 0), 8) * win
        w = 1.0 if self.flex is None else np.clip(0.35 + 0.65 * (rn @ self.flex), 0, 1)
        out[m] = -self.depth * g * w * (0.7 + 0.3 * gnoise(Q, 40))
        return out


class HeadPlates:
    """Escudos craneales: placas poligonales irregulares en hocico, cráneo y cejas."""

    def __init__(self):
        self.lo = A.HEAD_O - 0.75; self.hi = A.HEAD_O + 0.75

    def disp(self, P):
        out = np.zeros(len(P))
        m = np.all((P > self.lo) & (P < self.hi), axis=1)
        if not m.any():
            return out
        Q = P[m]
        L = (Q - A.HEAD_O) @ A.HEAD_M.T / A.HEAD_S
        x, f, u = L[:, 0], L[:, 1], L[:, 2]
        # tamaño de placa: grandes en el hocico y frente, menores hacia las mejillas
        top = ss(-0.02, 0.06, u) * ss(-0.12, 0.0, f) * (1 - ss(0.56, 0.62, f))
        F1, F2 = worley(Q, 0.016)
        edge = F2 - F1
        plate = ss(0.0, 0.22, edge) * (1.0 - 0.35 * F1)
        # escamas supralabiales: hilera de placas alargadas sobre el labio
        slit = -0.070 + (f - 0.385) * np.tan(np.radians(5.0))
        lip_u = np.abs(u - slit)
        lip = ss(0.03, 0.006, lip_u) * ss(0.12, 0.2, f) * (np.abs(x) > 0.03)
        cells = groove(f / 0.024, 10)
        v = (0.0016 * plate - 0.0009) * top + lip * (0.0012 - 0.0022 * cells)
        # tubérculos de la mejilla y la línea mandibular
        cheek = np.exp(-(((f - 0.02) / 0.09) ** 2 + ((u + 0.06) / 0.05) ** 2)) * (np.abs(x) > 0.06)
        v += cheek * 0.0022 * np.maximum(0, gnoise(Q, 85)) ** 1.5
        out[m] = v
        return out


def build_details():
    D = [BodyDetail(), HeadPlates()]
    for s in (1, -1):
        mm = np.array([s, 1, 1.0])
        # codo, muñeca, rodilla, corvejón
        D.append(SegmentCreases(A.FS * mm, A.FE * mm, 0.92, n=3, flex=np.array([0, -1, 0.3]), depth=0.0028))
        D.append(SegmentCreases(A.FE * mm, A.FW * mm, 0.93, n=3, spacing=0.013, flex=np.array([0, 1, 0.2]), depth=0.0022))
        D.append(SegmentCreases(A.HH * mm, A.HK * mm, 0.90, n=3, flex=np.array([0, 1, 0.3]), depth=0.0028))
        D.append(SegmentCreases(A.HK * mm, A.HA * mm, 0.92, n=3, spacing=0.013, flex=np.array([0, -1, 0.4]), depth=0.0022))
        # axila / ingle
        D.append(SegmentCreases(A.FS * mm, A.FE * mm, 0.08, n=2, spacing=0.02, depth=0.002, reach=0.2))
    return D


def total_disp(details, P):
    out = np.zeros(len(P))
    for d in details:
        out += d.disp(P)
    return out
