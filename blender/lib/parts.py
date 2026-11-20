"""
Piezas paramétricas de Vesper (numpy puro):
ojos, párpados, dientes, lengua, gorgueras, abanico caudal y membranas alares.

Cada generador devuelve un dict:
  V (n,3)  F (m,3 ó 4, lista)  UV (n,2) opcional
  W  -> lista de dicts {hueso: peso} por vértice
  mat -> nombre de material
"""
import numpy as np
import anatomy as A
from sdf import eval_points

norm = A.norm


def _grid_faces(nu, nv, off=0, wrap_u=False):
    F = []
    for i in range(nu - (0 if wrap_u else 1)):
        for j in range(nv - 1):
            i2 = (i + 1) % nu
            a = off + i * nv + j
            b = off + i2 * nv + j
            F.append((a, b, b + 1, a + 1))
    return F


def _single(bone, n):
    return [{bone: 1.0} for _ in range(n)]


def _mirror(part):
    V = part["V"].copy(); V[:, 0] *= -1
    F = [tuple(reversed(f)) for f in part["F"]]
    W = [{_flip(b): w for b, w in d.items()} for d in part["W"]]
    out = dict(part); out.update(V=V, F=F, W=W)
    return out


def _flip(name):
    if name.endswith(".L"):
        return name[:-2] + ".R"
    if name.endswith(".R"):
        return name[:-2] + ".L"
    return name


def eye_frame(s):
    a = A.eye_axis(s)
    up = A.HEAD_U - a * np.dot(A.HEAD_U, a)
    up = norm(up)
    lat = norm(np.cross(up, a))   # eje horizontal del ojo (eje de giro de los párpados)
    return a, up, lat


# ---------------------------------------------------------------------------
# Ojos
# ---------------------------------------------------------------------------
IRIS_ANGLE = np.radians(52)


def eyeball(s=1, nr=56, ns=72):
    R = A.EYE_R
    c = A.eye_center(s)
    a, up, lat = eye_frame(s)
    V, UV = [], []
    ti = IRIS_ANGLE
    zi = R * np.cos(ti)
    for i in range(nr + 1):
        th = np.pi * i / nr
        for j in range(ns):
            ph = 2 * np.pi * j / ns
            x, y = np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph)
            z = np.cos(th)
            rr = R
            p = np.array([x, y, z]) * rr
            if th < ti:
                # iris ligeramente cóncavo, hundido bajo la córnea
                q = np.sin(th) / np.sin(ti)
                p = np.array([x / np.sin(th) if th > 0 else 0, y / np.sin(th) if th > 0 else 0, 0]) * R * np.sin(ti) * q
                p[2] = zi - 0.10 * R * (1 - q * q) - 0.02 * R
            V.append(c + p[0] * lat + p[1] * up + p[2] * a)
            u_ = p[0] / (R * np.sin(ti)); v_ = p[1] / (R * np.sin(ti))
            UV.append((0.5 + 0.5 * u_ * s, 0.5 + 0.5 * v_))
    V = np.array(V); UV = np.array(UV)
    F = []
    for i in range(nr):
        for j in range(ns):
            j2 = (j + 1) % ns
            a0 = i * ns + j; b0 = i * ns + j2
            F.append((a0, a0 + ns, b0 + ns, b0))
    W = _single(f"eye.{'L' if s > 0 else 'R'}", len(V))
    return dict(name=f"Eye.{'L' if s > 0 else 'R'}", V=V, F=F, UV=UV, W=W, mat="Eye")


def cornea(s=1, nr=24, ns=72):
    R = A.EYE_R
    c = A.eye_center(s)
    a, up, lat = eye_frame(s)
    tmax = IRIS_ANGLE + np.radians(9)
    V = []
    for i in range(nr + 1):
        th = tmax * i / nr
        # abombamiento suave: radio 1.022R en el centro, R en el borde
        rr = R * (1.0 + 0.022 * np.cos(np.pi / 2 * th / tmax) ** 2) + 0.0004
        for j in range(ns):
            ph = 2 * np.pi * j / ns
            p = np.array([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]) * rr
            V.append(c + p[0] * lat + p[1] * up + p[2] * a)
    V = np.array(V)
    F = []
    for i in range(nr):
        for j in range(ns):
            j2 = (j + 1) % ns
            a0 = i * ns + j; b0 = i * ns + j2
            F.append((a0, b0, b0 + ns, a0 + ns))
    # quitar polo degenerado (anillo 0) -> abanico
    W = _single(f"eye.{'L' if s > 0 else 'R'}", len(V))
    return dict(name=f"Cornea.{'L' if s > 0 else 'R'}", V=V, F=F, W=W, mat="Cornea")


# Párpados ------------------------------------------------------------------
LID_UP_MARGIN = np.radians(36)    # elevación del borde del párpado superior en reposo
LID_LO_MARGIN = np.radians(-40)
LID_PHI = np.radians(84)


def eyelid(s=1, upper=True, nphi=56):
    R = A.EYE_R
    c = A.eye_center(s)
    a, up, lat = eye_frame(s)
    ro, ri = R * 1.085, R * 1.032
    # perfil (rho, delta_theta) desde el lado exterior lejano hasta el interior lejano
    prof = []
    far = np.radians(105)
    for t in np.linspace(far, np.radians(5), 12):
        prof.append((ro, t))
    for k in range(1, 8):  # borde redondeado (margen del párpado)
        ang = np.pi * k / 8
        rm = (ro + ri) / 2 + (ro - ri) / 2 * np.cos(ang)
        dt = np.radians(5) - np.radians(5.5) * np.sin(ang)
        prof.append((rm, dt))
    for t in np.linspace(np.radians(5), np.radians(80), 8):
        prof.append((ri, t))
    prof = np.array(prof)
    V = []
    for j in range(nphi):
        phi = -LID_PHI + 2 * LID_PHI * j / (nphi - 1)
        q = phi / LID_PHI
        if upper:
            m = LID_UP_MARGIN - np.radians(30) * q * q   # arco del párpado superior
        else:
            m = LID_LO_MARGIN + np.radians(26) * q * q
        for rho, dt in prof:
            th = m + dt if upper else m - dt
            p = rho * np.array([np.sin(phi), np.cos(phi) * np.sin(th), np.cos(phi) * np.cos(th)])
            V.append(c + p[0] * lat * s + p[1] * up + p[2] * a)
    V = np.array(V)
    npf = len(prof)
    F = _grid_faces(nphi, npf)
    if (not upper) ^ (s < 0):
        F = [tuple(reversed(f)) for f in F]
    sx = "L" if s > 0 else "R"
    W = _single(f"lid_{'up' if upper else 'lo'}.{sx}", len(V))
    # coordenada para el shader: 0 en el margen, 1 lejos (para oscurecer el borde húmedo)
    UV = np.array([(j / (nphi - 1), k / (npf - 1)) for j in range(nphi) for k in range(npf)])
    return dict(name=f"Lid{'Up' if upper else 'Lo'}.{sx}", V=V, F=F, UV=UV, W=W, mat="Skin")


# ---------------------------------------------------------------------------
# Dientes y lengua
# ---------------------------------------------------------------------------
def _cone(base, tip, r, n=8, flat=0.7, side=np.array([1.0, 0, 0]), curve=None, rings=4):
    d = tip - base
    L = np.linalg.norm(d); d = d / L
    s1 = norm(side - d * np.dot(side, d))
    s2 = np.cross(d, s1)
    V, F = [], []
    for k in range(rings + 1):
        t = k / rings
        rr = r * (1 - t) ** 0.9 + 0.0004
        cen = base + d * L * t
        if curve is not None:
            cen = cen + curve * (t * t) * L
        for j in range(n):
            ang = 2 * np.pi * j / n
            V.append(cen + rr * (np.cos(ang) * s1 * flat + np.sin(ang) * s2))
    F = _grid_faces(rings + 1, n, wrap_u=False)
    # reordenar: anillos x segmentos
    F = []
    for k in range(rings):
        for j in range(n):
            j2 = (j + 1) % n
            F.append((k * n + j, k * n + j2, (k + 1) * n + j2, (k + 1) * n + j))
    tipi = len(V); V.append(tip + (curve * L if curve is not None else 0))
    for j in range(n):
        F.append((rings * n + j, rings * n + (j + 1) % n, tipi))
    return np.array(V), F


def _surface_x(prims, f, u, x0=0.3):
    """Busca la superficie lateral (x>0) de la cabeza a una altura dada."""
    xs = np.linspace(x0, 0.0, 600)
    P = np.array([A.H(x, f, u) for x in xs])
    d = eval_points(prims, P)
    if not (d < 0).any():
        return None
    return xs[np.argmax(d < 0)]


def teeth(prims):
    S = A.HEAD_S
    parts_up, parts_lo = [], []
    slit_u = lambda f: -0.070 + (f - 0.385) * np.tan(np.radians(5.0))
    Vs, Fs, Ws = [], [], []
    def add(v, f, bone):
        off = sum(len(x) for x in Vs)
        Vs.append(v); Fs.extend([tuple(i + off for i in ff) for ff in f]); Ws.extend(_single(bone, len(v)))
    for s in (1, -1):
        for upper in (True, False):
            fs = np.arange(0.20, 0.50 if upper else 0.47, 0.020)
            for i, f in enumerate(fs):
                u0 = slit_u(f)
                xs = None
                for du in (0.016, 0.022, 0.030):
                    xs = _surface_x(prims, f, u0 + (du if upper else -du))
                    if xs is not None:
                        break
                if xs is None:
                    continue
                x = max(xs - 0.014, 0.015)
                fang = abs(f - 0.405) < 0.011 if upper else abs(f - 0.36) < 0.011
                L = (0.030 if fang else 0.012 + 0.006 * np.sin(i * 1.7) ** 2) * S
                r = (0.0065 if fang else 0.0040) * S
                base = A.H(s * x, f, u0 + (0.010 if upper else -0.010))
                dirn = norm(A.Hd(s * 0.12, -0.25, -1.0 if upper else 1.0))
                tip = base + dirn * L
                v, ff = _cone(base, tip, r, n=8, flat=0.65, side=A.Hd(0, 1, 0),
                              curve=A.Hd(0, -0.15, 0), rings=4)
                add(v, ff, "head" if upper else "jaw")
    V = np.concatenate(Vs)
    return dict(name="Teeth", V=V, F=Fs, W=Ws, mat="Teeth")


def tongue(nu=28, nv=16):
    S = A.HEAD_S
    V, W = [], []
    for i in range(nu):
        t = i / (nu - 1)
        f = 0.10 + 0.30 * t
        wdt = 0.042 * np.sin(np.pi * (0.15 + 0.85 * t)) ** 0.6 * (1 - 0.35 * t)
        th = 0.010 * (1 - 0.5 * t)
        for j in range(nv):
            ang = 2 * np.pi * j / nv
            x = np.cos(ang) * wdt
            u = -0.084 + np.sin(ang) * th + 0.003 * np.cos(ang * 2)
            # surco central
            if np.sin(ang) > 0:
                u -= 0.003 * np.exp(-(x / 0.01) ** 2)
            V.append(A.H(x, f, u))
            W.append({"tongue": 0.6 + 0.4 * t, "jaw": 0.4 - 0.4 * t})
    V = np.array(V)
    F = []
    for i in range(nu - 1):
        for j in range(nv):
            j2 = (j + 1) % nv
            F.append((i * nv + j, i * nv + j2, (i + 1) * nv + j2, (i + 1) * nv + j))
    # tapas
    c0 = len(V); V = np.vstack([V, V[:nv].mean(0), V[-nv:].mean(0)])
    W += [{"jaw": 1.0}, {"tongue": 1.0}]
    for j in range(nv):
        F.append((c0, (j + 1) % nv, j))
        F.append((c0 + 1, (nu - 1) * nv + j, (nu - 1) * nv + (j + 1) % nv))
    return dict(name="Tongue", V=V, F=F, W=W, mat="Mouth")


# ---------------------------------------------------------------------------
# Aletas: gorgueras y abanico caudal (espinas + membrana festoneada)
# ---------------------------------------------------------------------------
def _polyline_eval(P, t):
    """Evalúa una polilínea por longitud de arco normalizada (t en [0,1])."""
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)]) / seg.sum()
    t = np.clip(t, 0, 1)
    j = np.clip(np.searchsorted(cum, t, side="right") - 1, 0, len(seg) - 1)
    f = (t - cum[j]) / np.maximum(cum[j + 1] - cum[j], 1e-9)
    return P[j] * (1 - f)[..., None] + P[j + 1] * f[..., None]


def fin(name, bases, dirs, lens, bones, curl, normal_hint, depth=0.28, ns=10, nt=22,
        spine_r=0.0075, mat_membrane="Membrane", uv_off=0.0, billow=0.012):
    """Membrana festoneada entre espinas. curl: vector de curvatura de las espinas."""
    curves = []
    for b, d, L in zip(bases, dirs, lens):
        pts = [b + d * L * t + curl * L * (t ** 2) for t in np.linspace(0, 1, 8)]
        curves.append(np.array(pts))
    Vm, Fm, Wm, UVm = [], [], [], []
    for k in range(len(curves) - 1):
        off = len(Vm)
        for i in range(ns + 1):
            s = i / ns
            e = 1 - depth * np.sin(np.pi * s) ** 1.3
            for j in range(nt + 1):
                t = 0.0 + 1.0 * j / nt
                te = t * e
                p = _polyline_eval(curves[k], te) * (1 - s) + _polyline_eval(curves[k + 1], te) * s
                p = p + normal_hint * billow * np.sin(np.pi * s) * np.sin(np.pi * min(te, 1.0))
                Vm.append(p)
                Wm.append({bones[k]: 1 - s, bones[k + 1]: s} if 0 < s < 1 else {bones[k] if s == 0 else bones[k + 1]: 1.0})
                UVm.append((uv_off + (k + s) / (len(curves) - 1), te))
        Fm += _grid_faces(ns + 1, nt + 1, off)
    Vm = np.array(Vm)
    mem = dict(name=name + "Membrane", V=Vm, F=Fm, W=Wm, UV=np.array(UVm), mat=mat_membrane)
    # espinas
    Vs, Fs, Ws = [], [], []
    for c, bn in zip(curves, bones):
        v, f = _cone(c[0], c[-1], spine_r, n=8, flat=0.75, side=normal_hint, rings=6)
        # doblar siguiendo la curva
        rings = 6
        for kk in range(rings + 1):
            t = kk / rings
            delta = _polyline_eval(c, np.array(t)) - (c[0] + (c[-1] - c[0]) * t)
            v[kk * 8:(kk + 1) * 8] += delta
        off = sum(len(x) for x in Vs)
        Vs.append(v); Fs += [tuple(i + off for i in q) for q in f]; Ws += _single(bn, len(v))
    spines = dict(name=name + "Spines", V=np.concatenate(Vs), F=Fs, W=Ws, mat="Keratin")
    return mem, spines


def frills(s=1):
    S = A.HEAD_S
    sx = "L" if s > 0 else "R"
    root = A.frill_root(s)
    dirs = A.frill_dirs(s)
    up = A.HEAD_U
    bases = [root + up * (0.045 - 0.03 * i) * S for i in range(4)]
    lens = [L * S for L in A.FRILL_LEN]
    bones = [f"frill{i+1}.{sx}" for i in range(4)]
    lateral = norm(A.Hd(s, 0, 0))
    curl = lateral * 0.10 + A.Hd(0, -0.05, 0) * 0.0
    mem, sp = fin(f"Frill.{sx}", bases, dirs, lens, bones, curl, lateral, depth=0.30,
                  spine_r=0.0065, billow=0.006)
    if s < 0:
        mem["F"] = [tuple(reversed(f)) for f in mem["F"]]
    return mem, sp


def tail_fan():
    tip = A.TAIL_PTS[-1]
    dirs = A.fan_dirs()
    tdir = norm(A.TAIL_PTS[-1] - A.TAIL_PTS[-2])
    bases = []
    for i, d in enumerate(dirs):
        lat = (i - 2) * 0.012
        bases.append(tip - tdir * 0.10 + np.array([lat, 0, 0]) + np.array([0, 0, 0.004]))
    bones = [f"fan{i+1}" for i in range(5)]
    mem, sp = fin("TailFan", bases, dirs, A.FAN_LEN, bones, np.array([0, 0, 0.05]),
                  np.array([0, 0, 1.0]), depth=0.26, spine_r=0.009, billow=0.008)
    return mem, sp


# ---------------------------------------------------------------------------
# Membrana alar
# ---------------------------------------------------------------------------
def wing_membrane(prims, s=1, ns=22, nt=44):
    m = np.array([s, 1, 1.0])
    sx = "L" if s > 0 else "R"
    W_WR, W_EL, W_SH = A.W_WR, A.W_EL, A.W_SH
    fingers = [np.array([W_WR, mid, tip]) for mid, tip in A.W_FINGERS]
    # borde del cuerpo: muñeca -> codo -> hombro -> flanco -> cadera (justo bajo la piel)
    flank = []
    for y, z in ((-0.30, 1.32), (-0.05, 1.27), (0.22, 1.20), (0.45, 1.14), (A.W_HIP_ATTACH[1], A.W_HIP_ATTACH[2])):
        xs = np.linspace(0.6, 0.0, 400)
        P = np.stack([xs, np.full_like(xs, y), np.full_like(xs, z)], -1)
        d = eval_points(prims, P)
        x = xs[np.argmax(d < 0)] - 0.025
        flank.append(np.array([x, y, z]))
    body_edge = np.array([W_WR, W_EL, W_SH] + flank)
    curves = fingers + [body_edge]
    # pesos a lo largo de cada curva
    def finger_w(i, t):
        seg = np.linalg.norm(np.diff(fingers[i], axis=0), axis=1)
        tm = seg[0] / seg.sum()
        b = np.clip((t - tm + 0.06) / 0.12, 0, 1)
        b = b * b * (3 - 2 * b)
        w = {f"f{i+1}a.{sx}": 1 - b, f"f{i+1}b.{sx}": b}
        # cerca de la muñeca, algo de antebrazo
        g = np.clip(1 - t / 0.08, 0, 1)
        if g > 0:
            w = {k: v * (1 - g) for k, v in w.items()}
            w[f"wforearm.{sx}"] = w.get(f"wforearm.{sx}", 0) + g
        return w
    seg = np.linalg.norm(np.diff(body_edge, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)]) / seg.sum()
    def body_w(t):
        # tramos: 0 muñeca-codo, 1 codo-hombro, 2+ flanco
        bones_seg = [f"wforearm.{sx}", f"humerus.{sx}", "chest", "chest", "spine1", "spine1", "hips"]
        x = np.interp(t, cum, np.arange(len(cum)))
        i0 = int(np.clip(np.floor(x), 0, len(bones_seg) - 1)); f = x - i0
        i1 = min(i0 + 1, len(bones_seg) - 1)
        w = {}
        # mezcla suave entre tramos vecinos
        bf = np.clip((f - 0.75) / 0.25, 0, 1) * 0.5
        w[bones_seg[i0]] = w.get(bones_seg[i0], 0) + 1 - bf
        w[bones_seg[i1]] = w.get(bones_seg[i1], 0) + bf
        return w

    V, F, W, UV = [], [], [], []
    for k in range(4):
        off = len(V)
        A_c, B_c = curves[k], curves[k + 1]
        depth = (0.20, 0.17, 0.15, 0.20)[k]
        for i in range(ns + 1):
            sp = i / ns
            e = 1 - depth * np.sin(np.pi * sp) ** 1.25
            for j in range(nt + 1):
                t = 0.025 + 0.975 * j / nt
                te = t * e
                p = _polyline_eval(A_c, te) * (1 - sp) + _polyline_eval(B_c, te) * sp
                chord = np.linalg.norm(_polyline_eval(A_c, te) - _polyline_eval(B_c, te))
                p = p + np.array([0, 0, -1.0]) * 0.08 * chord * np.sin(np.pi * sp) * np.sin(np.pi * min(te, 1)) ** 0.8
                V.append(p * m)
                wa = finger_w(k, te)
                wb = finger_w(k + 1, te) if k < 3 else body_w(te)
                w = {}
                for b_, v_ in wa.items():
                    w[b_] = w.get(b_, 0) + v_ * (1 - sp)
                for b_, v_ in wb.items():
                    w[b_] = w.get(b_, 0) + v_ * sp
                W.append(w)
                UV.append(((k + sp) / 4.0, te))
        F += _grid_faces(ns + 1, nt + 1, off)
    V = np.array(V)
    if s < 0:
        F = [tuple(reversed(f)) for f in F]
    return dict(name=f"WingMembrane.{sx}", V=V, F=F, W=W, UV=np.array(UV), mat="Wing")


def all_parts(prims):
    out = []
    for s in (1, -1):
        out += [eyeball(s), cornea(s), eyelid(s, True), eyelid(s, False)]
        out += list(frills(s))
        out.append(wing_membrane(prims, s))
    out.append(teeth(prims))
    out.append(tongue())
    out += list(tail_fan())
    return out
