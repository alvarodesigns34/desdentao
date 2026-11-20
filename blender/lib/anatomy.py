"""
Anatomía de VESPER — dragón nocturno original.

Sistema de coordenadas (Blender): Z arriba, el dragón mira hacia -Y,
+X es el lado IZQUIERDO del dragón (sufijo .L). Unidades: metros.

Este módulo es la única fuente de verdad para:
  * el esqueleto (BONES),
  * las primitivas SDF que esculpen el cuerpo (build_prims()),
  * puntos de anclaje de ojos, gorgueras, alas y abanico de la cola.
"""
import numpy as np
from sdf import Prim, rot_from_axes, rot_euler

V = lambda *a: np.array(a, float)


def norm(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# Marco local de la cabeza
# ---------------------------------------------------------------------------
HEAD_O = V(0, -1.12, 1.72)                 # articulación cráneo-cuello
HEAD_F = norm((0, -1, -0.09))              # adelante (hocico)
HEAD_U = norm(np.cross(V(1, 0, 0), HEAD_F))  # arriba
if HEAD_U[2] < 0:
    HEAD_U = -HEAD_U
HEAD_M = np.stack([V(1, 0, 0), HEAD_F, HEAD_U])  # filas = ejes locales


HEAD_S = 1.13   # escala global de la cabeza


def H(x, f, u):
    """Coordenadas locales de la cabeza -> mundo."""
    return HEAD_O + HEAD_S * (x * HEAD_M[0] + f * HEAD_M[1] + u * HEAD_M[2])


def Hd(x, f, u):
    """Dirección local de la cabeza -> mundo."""
    return x * HEAD_M[0] + f * HEAD_M[1] + u * HEAD_M[2]


# ---------------------------------------------------------------------------
# Puntos clave
# ---------------------------------------------------------------------------
EYE_R = 0.040 * 1.13
def eye_center(s):  # s = +1 izquierda, -1 derecha
    return H(s * 0.090, 0.19, 0.062)

def eye_axis(s):
    return norm(Hd(s * 0.80, 0.52, 0.16))

JAW_HINGE = H(0, 0.02, -0.075)

def frill_root(s):
    return H(s * 0.125, -0.02, -0.085)

# patas delanteras
FS, FE, FW, FP = V(0.26, -0.55, 0.92), V(0.33, -0.40, 0.53), V(0.30, -0.60, 0.15), V(0.30, -0.71, 0.05)
# patas traseras
HH, HK, HA, HB = V(0.24, 0.55, 0.90), V(0.33, 0.24, 0.56), V(0.31, 0.68, 0.29), V(0.31, 0.54, 0.06)

# alas (pose de reposo extendida)
W_ROOT = V(0.13, -0.44, 1.27)
W_SH = V(0.25, -0.42, 1.37)
W_EL = V(0.80, -0.30, 1.50)
W_WR = V(1.47, -0.52, 1.56)
W_FINGERS = [  # (nudillo medio, punta)
    (V(2.12, -0.69, 1.63), V(2.78, -0.72, 1.62)),
    (V(2.06, -0.13, 1.56), V(2.66, 0.16, 1.50)),
    (V(1.80, 0.26, 1.47), V(2.14, 0.86, 1.36)),
    (V(1.40, 0.36, 1.41), V(1.33, 1.15, 1.22)),
]
W_HIP_ATTACH = V(0.22, 0.60, 1.10)

# cola
N_TAIL = 14
def _tail_points():
    pts, rad = [], []
    for i in range(N_TAIL + 1):
        t = i / N_TAIL
        y = 0.74 + i * 0.19
        z = 0.97 - 0.42 * (1 - np.exp(-i / 4.5)) + 0.04 * t * t
        pts.append(V(0, y, z))
        rad.append(0.035 + 0.17 * (1 - t) ** 1.35)
    return pts, rad
TAIL_PTS, TAIL_RAD = _tail_points()

SPINE_PTS = [V(0, 0.55, 0.98), V(0, 0.20, 1.02), V(0, -0.15, 1.05), V(0, -0.62, 1.15)]
NECK_PTS = [V(0, -0.62, 1.15), V(0, -0.86, 1.34), V(0, -1.02, 1.54), HEAD_O.copy()]
NECK_RAD = [0.22, 0.165, 0.132, 0.112]


# ---------------------------------------------------------------------------
# Esqueleto: nombre -> (cabeza, cola, padre, deforma)
# ---------------------------------------------------------------------------
def build_bones():
    B = {}
    def add(n, h, t, p, d=True):
        B[n] = (np.asarray(h, float), np.asarray(t, float), p, d)
    add("root", (0, 0, 0), (0, 0.5, 0), None, False)
    add("hips", SPINE_PTS[0], SPINE_PTS[1], "root")
    add("spine1", SPINE_PTS[1], SPINE_PTS[2], "hips")
    add("chest", SPINE_PTS[2], SPINE_PTS[3], "spine1")
    add("neck1", NECK_PTS[0], NECK_PTS[1], "chest")
    add("neck2", NECK_PTS[1], NECK_PTS[2], "neck1")
    add("neck3", NECK_PTS[2], NECK_PTS[3], "neck2")
    add("head", HEAD_O, H(0, 0.56, -0.02), "neck3")
    add("jaw", JAW_HINGE, H(0, 0.47, -0.10), "head")
    add("tongue", H(0, 0.12, -0.075), H(0, 0.36, -0.072), "jaw")
    for s, sx in ((1, "L"), (-1, "R")):
        c = eye_center(s)
        add(f"eye.{sx}", c, c + eye_axis(s) * 0.06, "head")
        # párpados: giran alrededor del centro del ojo
        add(f"lid_up.{sx}", c, c + norm(Hd(s * 0.25, 0.0, 1.0)) * 0.05, "head")
        add(f"lid_lo.{sx}", c, c + norm(Hd(s * 0.25, 0.0, -1.0)) * 0.05, "head")
        add(f"brow.{sx}", H(s * 0.09, 0.22, 0.11), H(s * 0.13, 0.10, 0.12), "head")
        add(f"nostril.{sx}", H(s * 0.035, 0.47, 0.03), H(s * 0.035, 0.53, 0.02), "head")
        r = frill_root(s)
        for i, d in enumerate(frill_dirs(s)):
            add(f"frill{i+1}.{sx}", r, r + d * FRILL_LEN[i] * 0.6, "head")
        # pata delantera
        m = V(s, 1, 1)
        add(f"shoulder.{sx}", V(0.13, -0.40, 1.20) * m, FS * m, "chest")
        add(f"upperarm.{sx}", FS * m, FE * m, f"shoulder.{sx}")
        add(f"forearm.{sx}", FE * m, FW * m, f"upperarm.{sx}")
        add(f"hand.{sx}", FW * m, FP * m, f"forearm.{sx}")
        add(f"fingers.{sx}", FP * m, (FP + V(0, -0.13, -0.02)) * m, f"hand.{sx}")
        # pata trasera
        add(f"thigh.{sx}", HH * m, HK * m, "hips")
        add(f"shin.{sx}", HK * m, HA * m, f"thigh.{sx}")
        add(f"foot.{sx}", HA * m, HB * m, f"shin.{sx}")
        add(f"toes.{sx}", HB * m, (HB + V(0, -0.14, -0.02)) * m, f"foot.{sx}")
        # ala
        add(f"wing_root.{sx}", W_ROOT * m, W_SH * m, "chest")
        add(f"humerus.{sx}", W_SH * m, W_EL * m, f"wing_root.{sx}")
        add(f"wforearm.{sx}", W_EL * m, W_WR * m, f"humerus.{sx}")
        for i, (mid, tip) in enumerate(W_FINGERS):
            add(f"f{i+1}a.{sx}", W_WR * m, mid * m, f"wforearm.{sx}")
            add(f"f{i+1}b.{sx}", mid * m, tip * m, f"f{i+1}a.{sx}")
    # cola
    prev = "hips"
    # primer segmento: de la pelvis al arranque de la cola
    for i in range(N_TAIL):
        n = f"tail{i+1:02d}"
        add(n, TAIL_PTS[i], TAIL_PTS[i + 1], prev)
        prev = n
    tip = TAIL_PTS[-1]
    for i, d in enumerate(fan_dirs()):
        add(f"fan{i+1}", tip, tip + d * FAN_LEN[i] * 0.6, prev)
    return B


# ---------------------------------------------------------------------------
# Gorgueras (abanicos membranosos de las mejillas) y abanico caudal
# ---------------------------------------------------------------------------
FRILL_LEN = [0.15, 0.20, 0.22, 0.17]
def frill_dirs(s):
    # radian hacia atrás y afuera, de arriba hacia abajo
    angs = np.radians([38, 12, -14, -40])
    out = []
    for a in angs:
        d = Hd(s * 0.55, -0.80, 0.0) * np.cos(a) + Hd(0, -0.15, 1.0) * np.sin(a)
        out.append(norm(d))
    return out

FAN_LEN = [0.20, 0.27, 0.31, 0.27, 0.20]
def fan_dirs():
    # abanico vertical-lateral al final de la cola (en forma de hoja de pica)
    angs = np.radians([-62, -30, 0, 30, 62])
    out = []
    for a in angs:
        d = V(np.sin(a), np.cos(a), 0.10 * np.cos(a))
        out.append(norm(d))
    return out


# ---------------------------------------------------------------------------
# Primitivas
# ---------------------------------------------------------------------------
def _frame_prim(kind, center, frame, scale=(1, 1, 1), **kw):
    """Crea una primitiva definida en un marco (O, M) con escala anisótropa.
    Los puntos a/b/center se pasan en coordenadas del marco, absolutas."""
    O, M, S = frame
    center = np.asarray(center, float)
    scale = np.asarray(scale, float)
    cw = O + S * (M.T @ center)
    params = {}
    meta = {k: kw.pop(k) for k in ("op", "k", "bone", "mat", "tag") if k in kw}
    for key, val in kw.items():
        if key in ("a", "b", "center"):
            params[key] = (np.asarray(val, float) - center) / scale
        else:
            params[key] = val
    if kind in ("sphere", "ellipsoid", "rbox") and "center" not in params:
        params["center"] = np.zeros(3)
    return Prim(kind, R=M, c=cw, scale=scale * S, **meta, **params)


HF = (HEAD_O, HEAD_M, HEAD_S)
WF = (np.zeros(3), np.eye(3), 1.0)


def hp(kind, center, scale=(1, 1, 1), **kw):
    return _frame_prim(kind, center, HF, scale, **kw)


def wp(kind, center, scale=(1, 1, 1), **kw):
    return _frame_prim(kind, center, WF, scale, **kw)


def rcone(a, b, r1, r2, k=0.03, bone=None, mat=0, tag=""):
    return Prim("rcone", a=a, b=b, r1=r1, r2=r2, k=k, bone=bone, mat=mat, tag=tag)


def ell_along(a, b, center, rx, ry, rz, k=0.04, bone=None, up=(0, 0, 1), mat=0, tag=""):
    """Elipsoide orientado con su eje Y a lo largo de a->b."""
    R = rot_from_axes(y=np.asarray(b) - np.asarray(a), z=up)
    return Prim("ellipsoid", R=R, c=center, r=(rx, ry, rz), center=(0, 0, 0),
                k=k, bone=bone, mat=mat, tag=tag)


def head_prims():
    P = []
    b = "head"
    # cráneo
    P += [hp("ellipsoid", (0, 0.05, 0.045), r=(0.150, 0.175, 0.130), k=0.04, bone=b, tag="cranium"),
          hp("ellipsoid", (0, -0.05, 0.015), r=(0.115, 0.10, 0.11), k=0.05, bone=b, tag="occiput")]
    # hocico (mandíbula superior), aplanado y ancho
    P.append(hp("rcone", (0, 0.33, -0.01), scale=(1.10, 1, 0.80),
                a=(0, 0.15, 0.0), b=(0, 0.485, -0.032), r1=0.112, r2=0.047,
                k=0.05, bone=b, tag="snout"))
    # arista nasal
    P.append(hp("rcone", (0, 0.3, 0.06), a=(0, 0.14, 0.098), b=(0, 0.47, 0.016),
                r1=0.028, r2=0.018, k=0.045, bone=b, tag="nasal"))
    for s in (1, -1):
        # arcos superciliares (dan la mirada encapotada)
        Rb = rot_from_axes(y=Hd(s * 0.45, 1.0, -0.25), z=HEAD_U)
        P.append(Prim("ellipsoid", R=Rb, c=H(s * 0.086, 0.165, 0.098), center=(0, 0, 0),
                      r=np.array((0.034, 0.070, 0.019)) * HEAD_S, k=0.05, bone=b, tag="brow"))
        # pómulos y maseteros
        P.append(hp("ellipsoid", (s * 0.112, 0.06, -0.035), r=(0.055, 0.10, 0.065), k=0.04, bone=b, tag="cheek"))
        # rebordes de las narinas
        P.append(hp("ellipsoid", (s * 0.034, 0.478, 0.016), r=(0.019, 0.028, 0.013), k=0.03, bone=b, tag="nostrilrim"))
        # cuernos principales: barridos hacia atrás y ligeramente afuera
        pts = [(s * 0.080, -0.02, 0.118), (s * 0.125, -0.16, 0.195),
               (s * 0.158, -0.31, 0.222), (s * 0.172, -0.45, 0.192)]
        rr = [0.040, 0.029, 0.017, 0.004]
        for i in range(3):
            P.append(hp("rcone", pts[i], a=pts[i], b=pts[i + 1], r1=rr[i], r2=rr[i + 1],
                        k=0.03 if i == 0 else 0.008, bone=b, mat=1 if i else 1, tag="horn"))
        # cuerno menor bajo el principal
        p0, p1, p2 = (s * 0.118, -0.02, 0.055), (s * 0.170, -0.13, 0.075), (s * 0.19, -0.22, 0.06)
        P.append(hp("rcone", p0, a=p0, b=p1, r1=0.020, r2=0.012, k=0.02, bone=b, mat=1, tag="horn2"))
        P.append(hp("rcone", p1, a=p1, b=p2, r1=0.012, r2=0.003, k=0.006, bone=b, mat=1, tag="horn2"))
        # pequeñas púas en el borde de la mandíbula
        for j, f in enumerate((0.02, 0.10)):
            a = (s * 0.118, f, -0.118)
            tip = (s * 0.150, f - 0.06, -0.135)
            P.append(hp("rcone", a, a=a, b=tip, r1=0.010, r2=0.002, k=0.012, bone="jaw", mat=1, tag="jawspike"))
    # mandíbula inferior
    P.append(hp("rcone", (0, 0.25, -0.090), scale=(1.20, 1, 0.66),
                a=(0, 0.04, -0.086), b=(0, 0.495, -0.076), r1=0.098, r2=0.046,
                k=0.03, bone="jaw", tag="jaw"))
    for s in (1, -1):
        P.append(hp("ellipsoid", (s * 0.10, 0.03, -0.095), r=(0.05, 0.085, 0.055), k=0.04, bone="jaw", tag="jawangle"))
    P.append(hp("sphere", (0, 0.465, -0.090), r=0.034, k=0.035, bone="jaw", tag="chin"))
    # --- sustracciones -----------------------------------------------------
    # hendidura de la boca (sonrisa reptiliana: sube hacia la comisura)
    R_m = HEAD_M  # en el marco de la cabeza, con giro adicional
    tilt = rot_euler(rx=np.radians(-5.0))
    M2 = tilt.T @ HEAD_M  # no se usa la escala
    cw = H(0, 0.385, -0.070)
    P.append(Prim("rbox", op="sub", R=M2, c=cw, center=(0, 0, 0), half=(0.30, 0.215, 0.0025),
                  r=0.0025, k=0.006, scale=(HEAD_S,) * 3, tag="mouthslit"))
    P.append(hp("ellipsoid", (0, 0.33, -0.072), r=(0.052, 0.17, 0.020), op="sub", k=0.010, tag="mouthcav"))
    for s in (1, -1):
        P.append(hp("ellipsoid", (s * 0.037, 0.513, 0.016), r=(0.0075, 0.016, 0.0065),
                    op="sub", k=0.006, tag="nostril"))
        c = eye_center(s)
        P.append(Prim("sphere", op="sub", center=c, r=EYE_R * 1.045, k=0.008, tag="eyesocket"))
    return P


def body_prims():
    P = []
    # --- cuello ---------------------------------------------------------
    names = ["neck1", "neck2", "neck3"]
    for i in range(3):
        P.append(rcone(NECK_PTS[i], NECK_PTS[i + 1], NECK_RAD[i], NECK_RAD[i + 1], k=0.06, bone=names[i], tag="neck"))
    # garganta
    P.append(ell_along(NECK_PTS[1], NECK_PTS[2], V(0, -0.94, 1.40), 0.105, 0.19, 0.125, k=0.06, bone="neck2", tag="throat"))
    P.append(ell_along(NECK_PTS[2], NECK_PTS[3], V(0, -1.07, 1.60), 0.09, 0.12, 0.10, k=0.06, bone="neck3", tag="throat"))
    # --- torso ----------------------------------------------------------
    P.append(Prim("ellipsoid", center=V(0, -0.36, 1.02), r=(0.30, 0.43, 0.33), k=0.08, bone="chest", tag="ribs"))
    P.append(Prim("ellipsoid", center=V(0, 0.04, 0.97), r=(0.255, 0.40, 0.27), k=0.10, bone="spine1", tag="belly"))
    P.append(Prim("ellipsoid", center=V(0, 0.50, 0.98), r=(0.25, 0.30, 0.25), k=0.10, bone="hips", tag="pelvis"))
    for s in (1, -1):
        m = V(s, 1, 1)
        P.append(Prim("ellipsoid", center=V(s * 0.15, -0.66, 0.97), r=(0.11, 0.12, 0.14), k=0.09, bone="chest", tag="pec"))
    # línea del lomo (columna marcada)
    P.append(rcone(V(0, 0.62, 1.12), V(0, -0.15, 1.22), 0.10, 0.11, k=0.10, bone="spine1", tag="back"))
    P.append(rcone(V(0, -0.15, 1.22), V(0, -0.62, 1.27), 0.11, 0.12, k=0.10, bone="chest", tag="back"))
    # --- patas ----------------------------------------------------------
    for s in (1, -1):
        m = V(s, 1, 1)
        S = "L" if s > 0 else "R"
        # escápula / hombro
        P.append(ell_along(V(0.13, -0.40, 1.20) * m, FS * m, V(0.22, -0.48, 1.08) * m, 0.10, 0.20, 0.16,
                           k=0.07, bone=f"shoulder.{S}", tag="scapula"))
        # brazo
        P.append(rcone(FS * m, FE * m, 0.15, 0.10, k=0.06, bone=f"upperarm.{S}", tag="arm"))
        P.append(ell_along(FS * m, FE * m, ((FS * 0.55 + FE * 0.45) + V(0, 0.04, 0)) * m, 0.10, 0.17, 0.10,
                           k=0.05, bone=f"upperarm.{S}", tag="triceps"))
        P.append(rcone(FE * m, FW * m, 0.088, 0.048, k=0.04, bone=f"forearm.{S}", tag="forearm"))
        # olécranon (punta del codo) y hueso de la muñeca
        P.append(Prim("sphere", center=(FE + V(0.0, 0.06, 0.02)) * m, r=0.05, k=0.04, bone=f"upperarm.{S}", tag="olecranon"))
        P.append(Prim("ellipsoid", center=(FW + V(0.0, 0.012, 0.01)) * m, r=(0.056, 0.05, 0.05), k=0.025, bone=f"forearm.{S}", tag="wristbone"))
        # deltoides y bíceps
        P.append(ell_along(FS * m, FE * m, (FS * 0.7 + FE * 0.3 + V(0.03, -0.05, 0)) * m, 0.085, 0.15, 0.09,
                           k=0.05, bone=f"upperarm.{S}", tag="deltoid"))
        P.append(ell_along(FE * m, FW * m, (FE * 0.72 + FW * 0.28 + V(0, -0.012, 0)) * m, 0.082, 0.14, 0.078,
                           k=0.04, bone=f"forearm.{S}", tag="forearmmuscle"))
        P.append(rcone(FW * m, (FP + V(0, 0.01, 0.0)) * m, 0.046, 0.054, k=0.03, bone=f"hand.{S}", tag="hand"))
        P += paw_prims(FP * m, s, f"hand.{S}", f"fingers.{S}", spread=1.0)
        # pata trasera
        P.append(ell_along(HH * m, HK * m, V(0.25, 0.45, 0.76) * m, 0.14, 0.26, 0.21,
                           k=0.08, bone=f"thigh.{S}", tag="thigh"))
        P.append(rcone(HH * m, HK * m, 0.13, 0.085, k=0.06, bone=f"thigh.{S}", tag="thighbone"))
        P.append(rcone(HK * m, HA * m, 0.090, 0.044, k=0.04, bone=f"shin.{S}", tag="shin"))
        # rótula y calcáneo (punta del corvejón) + tendón
        P.append(Prim("sphere", center=(HK + V(0, -0.05, 0.01)) * m, r=0.055, k=0.04, bone=f"thigh.{S}", tag="kneecap"))
        P.append(Prim("ellipsoid", center=(HA + V(0, 0.03, 0.01)) * m, r=(0.045, 0.05, 0.05), k=0.025, bone=f"shin.{S}", tag="calcaneus"))
        P.append(rcone((HK * 0.55 + HA * 0.45 + V(0, 0.05, 0)) * m, (HA + V(0, 0.045, 0.01)) * m, 0.02, 0.016, k=0.03,
                       bone=f"shin.{S}", tag="tendon"))
        P.append(ell_along(HK * m, HA * m, (HK * 0.65 + HA * 0.35 + V(0, 0.03, 0)) * m, 0.085, 0.16, 0.09,
                           k=0.04, bone=f"shin.{S}", tag="calf"))
        P.append(rcone(HA * m, (HB + V(0, 0.01, 0)) * m, 0.042, 0.052, k=0.03, bone=f"foot.{S}", tag="metatarsus"))
        P += paw_prims(HB * m, s, f"foot.{S}", f"toes.{S}", spread=0.9)
        # espolón del corvejón
        P.append(rcone(HA * m, (HA + V(0, 0.07, -0.03)) * m, 0.022, 0.004, k=0.015, bone=f"shin.{S}", mat=1, tag="spur"))
    # --- cola -----------------------------------------------------------
    P.append(rcone(V(0, 0.55, 0.98), TAIL_PTS[0], 0.24, TAIL_RAD[0], k=0.08, bone="hips", tag="tailbase"))
    for i in range(N_TAIL):
        P.append(rcone(TAIL_PTS[i], TAIL_PTS[i + 1], TAIL_RAD[i], TAIL_RAD[i + 1],
                       k=0.04, bone=f"tail{i+1:02d}", tag="tail"))
    # --- brazo del ala ----------------------------------------------------
    for s in (1, -1):
        m = V(s, 1, 1)
        S = "L" if s > 0 else "R"
        P.append(ell_along(W_ROOT * m, W_SH * m, V(0.19, -0.44, 1.30) * m, 0.085, 0.13, 0.075,
                           k=0.06, bone=f"wing_root.{S}", tag="wingmuscle"))
        P.append(rcone(W_SH * m, W_EL * m, 0.060, 0.038, k=0.03, bone=f"humerus.{S}", tag="humerus"))
        P.append(ell_along(W_SH * m, W_EL * m, (W_SH * 0.65 + W_EL * 0.35) * m, 0.06, 0.18, 0.05,
                           k=0.03, bone=f"humerus.{S}", tag="humerusmuscle"))
        P.append(rcone(W_EL * m, W_WR * m, 0.036, 0.030, k=0.02, bone=f"wforearm.{S}", tag="wforearm"))
        P.append(Prim("sphere", center=W_EL * m, r=0.042, k=0.02, bone=f"humerus.{S}", tag="welbow"))
        P.append(Prim("sphere", center=W_WR * m, r=0.036, k=0.02, bone=f"wforearm.{S}", tag="wwrist"))
        # pulgar con garra
        th = (W_WR + V(0.02, -0.07, 0.03))
        P.append(rcone(W_WR * m, th * m, 0.022, 0.016, k=0.012, bone=f"wforearm.{S}", tag="thumb"))
        P.append(rcone(th * m, (th + V(0.0, -0.045, -0.025)) * m, 0.013, 0.002, k=0.006,
                       bone=f"wforearm.{S}", mat=1, tag="thumbclaw"))
        for i, (mid, tip) in enumerate(W_FINGERS):
            r0 = 0.024 - 0.002 * i
            P.append(rcone(W_WR * m, mid * m, r0, r0 * 0.62, k=0.012, bone=f"f{i+1}a.{S}", tag="finger"))
            P.append(Prim("sphere", center=mid * m, r=r0 * 0.72, k=0.01, bone=f"f{i+1}a.{S}", tag="knuckle"))
            P.append(rcone(mid * m, tip * m, r0 * 0.62, 0.0045, k=0.01, bone=f"f{i+1}b.{S}", tag="finger"))
    return P


def paw_prims(P0, s, bone_palm, bone_toes, spread=1.0):
    out = []
    fwd = V(0, -1, 0)
    # almohadilla/palma
    out.append(Prim("ellipsoid", center=P0 + V(0, -0.025, -0.008), r=(0.075, 0.075, 0.035),
                    k=0.03, bone=bone_palm, tag="palm"))
    angs = np.radians([-34, -11, 11, 34]) * spread
    lens = [0.10, 0.13, 0.13, 0.10]
    for a, L in zip(angs, lens):
        d = V(np.sin(a) * s, -np.cos(a), 0)
        base = P0 + d * 0.035 + V(0, 0, -0.005)
        knuck = P0 + d * (L * 0.6) + V(0, 0, 0.012)
        tip = P0 + d * L + V(0, 0, -0.012)
        out.append(rcone(base, knuck, 0.028, 0.022, k=0.02, bone=bone_toes, tag="toe"))
        out.append(rcone(knuck, tip, 0.022, 0.017, k=0.012, bone=bone_toes, tag="toe"))
        c0 = tip + d * 0.006 + V(0, 0, 0.004)
        c1 = c0 + d * 0.032 + V(0, 0, -0.020)
        c2 = c1 + d * 0.014 + V(0, 0, -0.016)
        out.append(rcone(c0, c1, 0.0145, 0.008, k=0.004, bone=bone_toes, mat=1, tag="claw"))
        out.append(rcone(c1, c2, 0.008, 0.0015, k=0.002, bone=bone_toes, mat=1, tag="claw"))
    # espolón interior
    d = V(s * 0.85, 0.5, 0)
    b0 = P0 + V(s * 0.04, 0.02, 0.04)
    out.append(rcone(b0, b0 + d * 0.04 + V(0, 0, -0.02), 0.012, 0.002, k=0.008, bone=bone_palm, mat=1, tag="dewclaw"))
    return out


def chain_polyline():
    """Línea media del cuerpo: punta del hocico -> punta de la cola, con huesos."""
    pts = [H(0, 0.55, -0.03), H(0, 0.3, 0.0), HEAD_O] + NECK_PTS[2::-1] + SPINE_PTS[2::-1][1:] + TAIL_PTS
    # quitar duplicados consecutivos
    out = [pts[0]]
    for p in pts[1:]:
        if np.linalg.norm(p - out[-1]) > 1e-4:
            out.append(p)
    return np.array(out)


def dorsal_spines(base_prims):
    """Hilera de púas dorsales colocadas sobre la superficie real (raymarch)."""
    from sdf import eval_points
    poly = chain_polyline()[2:]  # desde el occipucio
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    out = []
    s = 0.10
    i = 0
    while s < total - 0.05:
        j = np.searchsorted(cum, s) - 1
        j = min(max(j, 0), len(poly) - 2)
        t = (s - cum[j]) / seg[j]
        c = poly[j] * (1 - t) + poly[j + 1] * t
        tang = norm(poly[j + 1] - poly[j])  # hacia la cola
        up = norm(np.cross(np.cross(tang, V(0, 0, 1)), tang))
        if up[2] < 0:
            up = -up
        # raymarch desde arriba hacia el centro
        ts = np.linspace(0.6, 0.0, 400)
        pts = c[None, :] + ts[:, None] * up[None, :]
        f = eval_points(base_prims, pts)
        k = np.argmax(f < 0)
        surf = pts[k]
        u = s / total
        # altura: crece en el cuello, máxima sobre los hombros, decrece en la cola
        h = 0.035 + 0.055 * np.exp(-((u - 0.22) / 0.16) ** 2) + 0.02 * np.exp(-((u - 0.05) / 0.05) ** 2)
        h *= 1.25 * (1.0 - 0.55 * max(0, u - 0.45) / 0.55)
        h = max(h, 0.018)
        base = surf - up * 0.018
        R = np.stack([norm(np.cross(tang, up)), tang, up])
        tip_l = V(0, h * 0.62, h * 0.80)
        bone = bone_for_point(c)
        out.append(Prim("rcone", R=R, c=base, scale=(0.42, 1, 1), a=(0, 0, 0), b=tip_l,
                        r1=0.30 * h + 0.008, r2=0.0035, k=0.012, bone=bone, mat=1, tag="dorsal"))
        # separación creciente hacia la cola
        s += 0.085 + 0.05 * u
        i += 1
    return out


def bone_for_point(p):
    B = build_bones()
    best, bd = None, 1e9
    for n in ["neck1", "neck2", "neck3", "head", "hips", "spine1", "chest"] + [f"tail{i+1:02d}" for i in range(N_TAIL)]:
        h, t, _, _ = B[n]
        ab = t - h
        u = np.clip(np.dot(p - h, ab) / np.dot(ab, ab), 0, 1)
        d = np.linalg.norm(p - (h + u * ab))
        if d < bd:
            bd, best = d, n
    return best


def build_prims():
    base = head_prims() + body_prims()
    unions = [p for p in base if p.op == "union"]
    spines = dorsal_spines(unions)
    # las sustracciones deben ir al final
    subs = [p for p in base if p.op == "sub"]
    return unions + spines + subs


BOUNDS = (V(-2.95, -1.85, -0.02), V(2.95, 3.55, 2.05))
