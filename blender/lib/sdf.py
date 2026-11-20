"""
Biblioteca SDF (campos de distancia con signo) vectorizada en numpy.

Se usa para esculpir el cuerpo de Vesper como una unión suave de primitivas
anatómicas (huesos, músculos, cráneo, cuernos, espinas...). El mismo módulo
sirve para:
  * generar la malla (marching cubes por bloques),
  * calcular pesos de skinning (softmax de distancias por hueso),
  * calcular máscaras de material y oclusión ambiental basada en SDF.

Funciona tanto con el Python del sistema como con el Python embebido de
Blender (solo depende de numpy).
"""
import numpy as np


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def _dot(a, b):
    return np.einsum("...i,...i->...", a, b)


def _len(a):
    return np.sqrt(_dot(a, a))


def smin(a, b, k):
    """Unión suave polinómica (Inigo Quilez)."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1.0 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def rot_from_axes(x=None, y=None, z=None):
    """Matriz cuyas FILAS son los ejes locales expresados en el mundo."""
    if y is not None:
        y = np.asarray(y, float)
        y = y / np.linalg.norm(y)
        up = np.asarray(z if z is not None else (0, 0, 1), float)
        x = np.cross(y, up)
        if np.linalg.norm(x) < 1e-6:
            x = np.array([1.0, 0, 0])
        x /= np.linalg.norm(x)
        z = np.cross(x, y)
        return np.stack([x, y, z])
    raise ValueError


def rot_euler(rx=0.0, ry=0.0, rz=0.0):
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


# ---------------------------------------------------------------------------
# primitivas
# ---------------------------------------------------------------------------
class Prim:
    """Primitiva genérica.

    kind   : 'sphere' | 'ellipsoid' | 'rcone' | 'rbox'
    op     : 'union' | 'sub'
    k      : radio de mezcla suave
    bone   : hueso que la controla (para el skinning)
    mat    : 0 piel, 1 queratina (cuernos/garras/espinas), 2 boca
    R      : matriz de rotación (filas = ejes locales en mundo) opcional
    c      : centro del marco local (para R / escala)
    scale  : escala anisótropa aplicada en el marco local
    """

    def __init__(self, kind, op="union", k=0.02, bone=None, mat=0, R=None,
                 c=(0, 0, 0), scale=(1, 1, 1), tag="", **params):
        self.kind = kind
        self.op = op
        self.k = float(k)
        self.bone = bone
        self.mat = mat
        self.R = None if R is None else np.asarray(R, float)
        self.c = np.asarray(c, float)
        self.scale = np.asarray(scale, float)
        self.p = {kk: (np.asarray(v, float) if not np.isscalar(v) else float(v))
                  for kk, v in params.items()}
        self.tag = tag
        self._bbox = None

    # -- transformación al marco local ----------------------------------
    def _local(self, P):
        Q = P - self.c
        if self.R is not None:
            Q = Q @ self.R.T
        return Q / self.scale

    def dist(self, P):
        Q = self._local(P)
        k = self.kind
        p = self.p
        if k == "sphere":
            d = _len(Q - p["center"]) - p["r"]
        elif k == "ellipsoid":
            r = p["r"]
            q = Q - p["center"]
            k0 = _len(q / r)
            k1 = _len(q / (r * r))
            d = k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)
        elif k == "rcone":
            d = sd_round_cone(Q, p["a"], p["b"], p["r1"], p["r2"])
        elif k == "rbox":
            q = np.abs(Q - p["center"]) - p["half"]
            d = _len(np.maximum(q, 0.0)) + np.minimum(q.max(axis=-1), 0.0) - p["r"]
        else:
            raise ValueError(k)
        return d * self.scale.min()

    # -- caja envolvente en mundo ----------------------------------------
    def bbox(self):
        if self._bbox is not None:
            return self._bbox
        p = self.p
        if self.kind == "sphere":
            lo = p["center"] - p["r"]; hi = p["center"] + p["r"]
        elif self.kind == "ellipsoid":
            m = p["r"].max()
            lo = p["center"] - m; hi = p["center"] + m
        elif self.kind == "rcone":
            m = max(p["r1"], p["r2"])
            lo = np.minimum(p["a"], p["b"]) - m
            hi = np.maximum(p["a"], p["b"]) + m
        elif self.kind == "rbox":
            m = p["half"] + p["r"]
            lo = p["center"] - m; hi = p["center"] + m
        # esquinas del cubo local -> mundo
        corners = np.array([[x, y, z] for x in (lo[0], hi[0])
                            for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        corners = corners * self.scale
        if self.R is not None:
            corners = corners @ self.R
        corners = corners + self.c
        margin = self.k * 1.5 + 0.01
        self._bbox = (corners.min(0) - margin, corners.max(0) + margin)
        return self._bbox


def sd_round_cone(p, a, b, r1, r2):
    """Cono redondeado entre a (radio r1) y b (radio r2) — IQ, vectorizado."""
    ba = b - a
    l2 = float(np.dot(ba, ba))
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    v = pa * l2 - y[..., None] * ba
    x2 = _dot(v, v)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    d3 = (np.sqrt(np.maximum(x2 * a2 * il2, 0)) + y * rr) * il2 - r1
    d1 = np.sqrt(x2 + z2) * il2 - r2
    d2 = np.sqrt(x2 + y2) * il2 - r1
    out = np.where(np.sign(y) * a2 * y2 < k, d2, d3)
    out = np.where(np.sign(z) * a2 * z2 > k, d1, out)
    return out


# ---------------------------------------------------------------------------
# evaluación del campo
# ---------------------------------------------------------------------------
def eval_points(prims, P, init=10.0):
    """Evalúa el campo completo en puntos arbitrarios (N,3)."""
    f = np.full(P.shape[:-1], init, dtype=np.float64)
    for pr in prims:
        if pr.op != "union":
            continue
        f = smin(f, pr.dist(P), pr.k)
    for pr in prims:
        if pr.op == "sub":
            f = smax(f, -pr.dist(P), pr.k)
    return f


DETAILS = []        # capa de detalle (detail.py); se rellena desde 01_sculpt.py
DETAIL_BAND = 0.012


def apply_details(f, P):
    """Suma el desplazamiento de detalle en la banda cercana a la superficie."""
    if not DETAILS:
        return f
    from detail import total_disp
    band = np.abs(f) < DETAIL_BAND
    if band.any():
        f[band] = f[band] - total_disp(DETAILS, P[band]).astype(f.dtype)
    return f


def eval_grid_block(prims, origin, h, shape, init=10.0):
    """Evalúa el campo en un bloque regular usando cajas envolventes."""
    f = np.full(shape, init, dtype=np.float32)
    gx = origin[0] + h * np.arange(shape[0])
    gy = origin[1] + h * np.arange(shape[1])
    gz = origin[2] + h * np.arange(shape[2])
    hi_block = origin + h * (np.array(shape) - 1)

    def rng(lo, hi, o, n):
        i0 = int(np.floor((lo - o) / h))
        i1 = int(np.ceil((hi - o) / h)) + 1
        return max(i0, 0), min(i1, n)

    for phase in ("union", "sub"):
        for pr in prims:
            if pr.op != phase:
                continue
            lo, hi = pr.bbox()
            if np.any(hi < origin) or np.any(lo > hi_block):
                continue
            ix = rng(lo[0], hi[0], origin[0], shape[0])
            iy = rng(lo[1], hi[1], origin[1], shape[1])
            iz = rng(lo[2], hi[2], origin[2], shape[2])
            if ix[0] >= ix[1] or iy[0] >= iy[1] or iz[0] >= iz[1]:
                continue
            X, Y, Z = np.meshgrid(gx[ix[0]:ix[1]], gy[iy[0]:iy[1]],
                                  gz[iz[0]:iz[1]], indexing="ij")
            P = np.stack([X, Y, Z], -1)
            d = pr.dist(P).astype(np.float32)
            sub = f[ix[0]:ix[1], iy[0]:iy[1], iz[0]:iz[1]]
            if phase == "union":
                sub[...] = smin(sub, d, pr.k)
            else:
                sub[...] = smax(sub, -d, pr.k)
    if DETAILS:
        band = np.abs(f) < DETAIL_BAND
        if band.any():
            idx = np.nonzero(band)
            P = np.stack([gx[idx[0]], gy[idx[1]], gz[idx[2]]], -1)
            from detail import total_disp
            f[band] -= total_disp(DETAILS, P).astype(np.float32)
    return f


def mesh_from_prims(prims, lo, hi, h, block=96, coarse=0.02, log=print):
    """Marching cubes por bloques con detección de bloques activos."""
    from skimage.measure import marching_cubes

    lo = np.asarray(lo, float); hi = np.asarray(hi, float)
    n = np.ceil((hi - lo) / h).astype(int) + 1
    # pasada gruesa para descartar bloques vacíos / macizos
    nc = np.ceil((hi - lo) / coarse).astype(int) + 1
    fc = eval_grid_block(prims, lo, coarse, tuple(nc))
    verts_all, faces_all = [], []
    voff = 0
    step = block - 1
    nb = np.ceil((n - 1) / step).astype(int)
    total = int(np.prod(nb)); done = 0
    for bi in range(nb[0]):
        for bj in range(nb[1]):
            for bk in range(nb[2]):
                done += 1
                i0 = np.array([bi, bj, bk]) * step
                shp = np.minimum(i0 + block, n) - i0
                if np.any(shp < 2):
                    continue
                o = lo + i0 * h
                # test grosero
                c0 = np.floor((o - lo) / coarse).astype(int) - 1
                c1 = np.ceil((o + (shp - 1) * h - lo) / coarse).astype(int) + 2
                c0 = np.maximum(c0, 0); c1 = np.minimum(c1, nc)
                sub = fc[c0[0]:c1[0], c0[1]:c1[1], c0[2]:c1[2]]
                if sub.size == 0 or np.abs(sub).min() > coarse * 2.0:
                    continue
                f = eval_grid_block(prims, o, h, tuple(shp))
                if f.min() > 0 or f.max() < 0:
                    continue
                v, fa, _, _ = marching_cubes(f, 0.0, spacing=(h, h, h))
                v = v + o
                verts_all.append(v)
                faces_all.append(fa + voff)
                voff += len(v)
                if done % 50 == 0:
                    log(f"  bloque {done}/{total}  verts={voff}")
    V = np.concatenate(verts_all)
    F = np.concatenate(faces_all)
    # soldar vértices duplicados en las fronteras de bloque
    key = np.round(V / (h * 1e-3)).astype(np.int64)
    _, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    V = V[idx]
    F = inv.reshape(-1)[F]
    good = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    F = F[good]
    return V, F
