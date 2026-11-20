"""
Datos por vértice del cuerpo, calculados a partir de las primitivas SDF:
  * pesos de skinning (softmax de distancias agrupado por hueso + reglas de mandíbula/cejas)
  * máscaras de material: queratina, gradiente de cuerno, boca, cavidades, 'tubo' corporal
  * coordenadas bodyuv (longitud del cuerpo, |ángulo| alrededor de la línea media)
  * oclusión ambiental basada en el campo de distancia
  * desplazamientos para shape keys (respiración, gruñido, narinas)
"""
import numpy as np
import anatomy as A
from sdf import smin, smax

TUBE_TAGS = {"neck", "throat", "ribs", "belly", "pelvis", "back", "tail", "tailbase", "pec"}


def _dist_matrix(prims, V, far=1.0):
    """D[p, n] con descarte por caja envolvente."""
    D = np.full((len(prims), len(V)), far, dtype=np.float32)
    for i, pr in enumerate(prims):
        lo, hi = pr.bbox()
        m = np.all((V >= lo) & (V <= hi), axis=1)
        if m.any():
            D[i, m] = pr.dist(V[m])
    return D


def eval_field(prims, P):
    """Campo completo con descarte por caja (rápido para AO)."""
    f = np.full(len(P), 10.0)
    for pr in prims:
        lo, hi = pr.bbox()
        m = np.all((P >= lo) & (P <= hi), axis=1)
        if not m.any():
            continue
        d = pr.dist(P[m])
        if pr.op == "union":
            f[m] = smin(f[m], d, pr.k)
    for pr in prims:
        if pr.op != "sub":
            continue
        lo, hi = pr.bbox()
        m = np.all((P >= lo) & (P <= hi), axis=1)
        if m.any():
            f[m] = smax(f[m], -pr.dist(P[m]), pr.k)
    return f


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -60, 60)))


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def head_local(V):
    Q = (V - A.HEAD_O) @ A.HEAD_M.T / A.HEAD_S
    return Q[:, 0], Q[:, 1], Q[:, 2]


def compute(prims, V, N, bones, chunk=40000, log=print):
    unions = [p for p in prims if p.op == "union"]
    subs = [p for p in prims if p.op == "sub"]
    bone_names = sorted({p.bone for p in unions if p.bone})
    bidx = {b: i for i, b in enumerate(bone_names)}
    nV = len(V)
    Wb = np.zeros((nV, len(bone_names)), np.float32)
    ker = np.zeros(nV, np.float32); tube = np.zeros(nV, np.float32)
    kgrad = np.zeros(nV, np.float32); mouth = np.zeros(nV, np.float32); cav = np.zeros(nV, np.float32)
    pb = np.array([bidx[p.bone] for p in unions])
    pm = np.array([p.mat for p in unions])
    ptube = np.array([p.tag in TUBE_TAGS for p in unions])
    skin_idx = np.where(pm == 0)[0]
    for c0 in range(0, nV, chunk):
        sl = slice(c0, min(c0 + chunk, nV))
        Vc = V[sl]
        D = _dist_matrix(unions, Vc)
        dmin = D.min(0)
        # pesos de hueso
        tau = 0.022
        E = np.exp(-(D - dmin) / tau)
        E /= E.sum(0, keepdims=True)
        for i in range(len(unions)):
            Wb[sl, pb[i]] += E[i]
        # máscaras de material (más nítidas)
        Em = np.exp(-(D - dmin) / 0.0035); Em /= Em.sum(0, keepdims=True)
        ker[sl] = Em[pm == 1].sum(0)
        Et = np.exp(-(D - dmin) / 0.03); Et /= Et.sum(0, keepdims=True)
        tube[sl] = Et[ptube].sum(0)
        dskin = D[skin_idx].min(0)
        kgrad[sl] = np.clip(dskin / 0.07, 0, 1)
        for p in subs:
            d = p.dist(Vc)
            g = np.exp(-(d / 0.004) ** 2)
            if p.tag in ("mouthslit", "mouthcav"):
                mouth[sl] = np.maximum(mouth[sl], g)
            elif p.tag == "nostril":
                cav[sl] = np.maximum(cav[sl], g)
            elif p.tag == "eyesocket":
                cav[sl] = np.maximum(cav[sl], 0.6 * g)
        log(f"  datos corporales {sl.stop}/{nV}")

    # --- regla de la mandíbula ---------------------------------------------
    x, f, u = head_local(V)
    tilt = np.radians(-5.0)
    # plano de la hendidura (centro 0.385,-0.070, inclinado)
    dz = (u + 0.070) * np.cos(tilt) - (f - 0.385) * np.sin(-tilt)
    dz = (u - (-0.070 + (f - 0.385) * np.tan(np.radians(5.0))))
    below_sharp = sigmoid(-dz / 0.0025)
    below_soft = sigmoid(-(dz + 0.005) / 0.012)
    front = smoothstep(0.10, 0.19, f)
    back = smoothstep(-0.04, 0.12, f) * 0.85
    jfrac = below_sharp * front + (1 - front) * below_soft * back
    hj = Wb[:, bidx["head"]] + Wb[:, bidx["jaw"]]
    Wb[:, bidx["jaw"]] = hj * jfrac
    Wb[:, bidx["head"]] = hj * (1 - jfrac)

    # --- cejas (zona de piel sobre el ojo) --------------------------------
    names = list(bone_names)
    def add_bone(n):
        nonlocal Wb
        if n not in bidx:
            bidx[n] = len(names); names.append(n)
            Wb = np.concatenate([Wb, np.zeros((nV, 1), np.float32)], 1)
    for s, sx in ((1, "L"), (-1, "R")):
        add_bone(f"brow.{sx}")
        c = A.H(s * 0.09, 0.17, 0.10)
        g = np.exp(-np.sum((V - c) ** 2, 1) / (0.045 * A.HEAD_S) ** 2) * 0.85
        g *= (u > 0.04)
        take = Wb[:, bidx["head"]] * g
        Wb[:, bidx["head"]] -= take
        Wb[:, bidx[f"brow.{sx}"]] += take

    # top-4 y normalizar
    order = np.argsort(-Wb, axis=1)[:, :4]
    top = np.take_along_axis(Wb, order, 1)
    top = np.where(top < 0.01, 0, top)
    top /= np.maximum(top.sum(1, keepdims=True), 1e-9)
    weights = (order, top, names)

    # --- bodyuv ---------------------------------------------------------------
    poly = A.chain_polyline()
    seg = poly[1:] - poly[:-1]
    L = np.linalg.norm(seg, axis=1)
    cum = np.concatenate([[0], np.cumsum(L)])
    total = cum[-1]
    best_d = np.full(nV, 1e9); best_s = np.zeros(nV); best_th = np.zeros(nV)
    for i in range(len(seg)):
        a = poly[i]; d = seg[i] / L[i]
        t = np.clip((V - a) @ d, 0, L[i])
        P = a + t[:, None] * d
        r = V - P
        dd = np.linalg.norm(r, axis=1)
        upv = np.array([0, 0, 1.0]) - d * d[2]
        upv /= np.linalg.norm(upv)
        lat = np.cross(d, upv)
        th = np.arctan2(r @ lat, r @ upv)
        m = dd < best_d
        best_d = np.where(m, dd, best_d)
        best_s = np.where(m, (cum[i] + t) / total, best_s)
        best_th = np.where(m, th, best_th)
    bodyuv = np.stack([best_s, np.abs(best_th) / np.pi], 1)
    # coordenadas métricas para orientar las escamas imbricadas a lo largo del cuerpo
    bodym = np.stack([best_s * total, np.abs(best_th) * best_d], 1)

    # --- oclusión ambiental por SDF -----------------------------------------
    ao = np.zeros(nV)
    hs = [0.008, 0.02, 0.04, 0.07, 0.12, 0.18]
    wsum = 0
    for i, h in enumerate(hs):
        fP = eval_field(prims, V + N * h)
        w = 1.0 / (1 + i) ** 0.7
        ao += w * np.clip(h - fP, 0, None) / h
        wsum += w
    ao = np.clip(1 - 1.3 * ao / wsum, 0, 1)

    masks = dict(keratin=ker, tube=tube, kgrad=kgrad, mouth=mouth, cavity=cav, ao=ao.astype(np.float32), bodym=bodym)
    return weights, masks, bodyuv


def shape_keys(V, N, masks, bodyuv):
    """Desplazamientos para shape keys."""
    x, f, u = head_local(V)
    keys = {}
    # respiración: expansión de costillas y vientre
    s = bodyuv[:, 0]; v = bodyuv[:, 1]
    torso = np.exp(-((s - 0.36) / 0.07) ** 2) * masks["tube"]
    keys["Breathe"] = N * (0.022 * torso * (0.6 + 0.4 * smoothstep(0.3, 0.8, v)))[:, None]
    # garganta (bolsa de brasas al enfadarse)
    throat = np.exp(-((s - 0.20) / 0.05) ** 2) * smoothstep(0.6, 0.9, v) * masks["tube"]
    keys["ThroatPuff"] = N * (0.02 * throat)[:, None]
    # gruñido: levanta el labio superior sobre los colmillos y arruga el hocico
    S = A.HEAD_S
    lip = np.exp(-(((f - 0.40) / 0.08) ** 2)) * np.exp(-(((u + 0.05) / 0.025) ** 2)) * smoothstep(0.03, 0.07, np.abs(x))
    lip *= (u > -0.071).astype(float)
    nose = np.exp(-(((f - 0.40) / 0.07) ** 2)) * np.exp(-(((u - 0.05) / 0.04) ** 2))
    up = A.HEAD_U
    snarl = up[None, :] * (0.012 * S * lip)[:, None] + N * (0.004 * nose)[:, None]
    keys["Snarl"] = snarl
    # narinas: dilatación radial
    disp = np.zeros_like(V)
    for sgn in (1, -1):
        c = A.H(sgn * 0.037, 0.513, 0.016)
        r = V - c
        d = np.linalg.norm(r, axis=1)
        g = np.exp(-(d / (0.022 * S)) ** 2)
        disp += r * (0.35 * g)[:, None]
    keys["NostrilFlare"] = disp
    # sonrisa: comisuras hacia atrás y arriba
    corner = np.exp(-(((f - 0.19) / 0.06) ** 2)) * np.exp(-(((u + 0.07) / 0.03) ** 2))
    keys["Smile"] = (up[None, :] * 0.006 * S + A.HEAD_F[None, :] * -0.006 * S) * corner[:, None]
    return keys
