"""
Definición del rig expresivo de Vesper, compartida por Blender y la app web.

Cada parámetro es una lista de (hueso, eje, ganancia, tipo):
  * eje en ESPACIO DE ARMATURE EN REPOSO (coordenadas Blender: X lado izq., -Y adelante, Z arriba)
  * tipo 'rot' -> rotación de (ganancia * valor) radianes alrededor del eje
  * tipo 'loc' -> traslación de (ganancia * valor) metros a lo largo del eje
Para los huesos .R el eje se refleja como pseudovector: (x, -y, -z).

Las rotaciones de todos los parámetros se suman como vectores de rotación
(conmutativo) y se aplican en el marco local del hueso. El plegado de alas se
calcula en Blender (03_build.py) y se añade a rig.json como 'wingFold'.
"""
import numpy as np
import anatomy as A

X = [1, 0, 0]          # + = inclinar hacia abajo (para huesos que apuntan hacia delante)
Z = [0, 0, 1]          # + = girar hacia la izquierda del dragón
FW = [0, -1, 0]        # balanceo
HU = list(map(float, A.HEAD_U))


def lid_axis():
    from parts import eye_frame
    a, up, lat = eye_frame(1)
    return list(map(float, lat))


def build_params():
    LID = lid_axis()
    P = {}
    P["head_pitch"] = [("head", X, 0.42), ("neck3", X, 0.22), ("neck2", X, 0.10)]
    P["head_yaw"] = [("head", Z, 0.38), ("neck3", Z, 0.26), ("neck2", Z, 0.18), ("neck1", Z, 0.12), ("chest", Z, 0.04)]
    P["head_tilt"] = [("head", FW, 0.42), ("neck3", FW, 0.10)]
    P["neck_raise"] = [("neck1", X, -0.30), ("neck2", X, -0.16), ("neck3", X, 0.14), ("head", X, 0.30)]
    P["neck_reach"] = [("neck1", X, 0.30), ("neck2", X, 0.14), ("neck3", X, -0.08), ("head", X, -0.32)]
    P["jaw_open"] = [("jaw", X, 0.52), ("tongue", X, -0.10)]
    P["tongue_out"] = [("tongue", X, -0.25)]
    P["lid_up"] = []
    P["lid_lo"] = []
    P["eye_yaw"] = []
    P["eye_pitch"] = []
    P["brow_down"] = []
    P["frill_flare"] = []
    P["frill_spread"] = []
    for sx in ("L", "R"):
        P["lid_up"].append((f"lid_up.{sx}", LID, 0.78))
        P["lid_lo"].append((f"lid_lo.{sx}", LID, -0.60))
        # la mirada es conjugada (no simétrica): el eje del ojo derecho se pre-refleja
        hu = HU if sx == "L" else [HU[0], -HU[1], -HU[2]]
        P["eye_yaw"].append((f"eye.{sx}", hu, 0.40))
        P["eye_pitch"].append((f"eye.{sx}", X, 0.30))
        P["brow_down"].append((f"brow.{sx}", X, -0.16))
        for i, g in enumerate((0.36, 0.13, -0.13, -0.36)):
            P["frill_spread"].append((f"frill{i+1}.{sx}", X, g))
            P["frill_flare"].append((f"frill{i+1}.{sx}", Z, -0.55))
    P["tail_raise"] = [(f"tail{i+1:02d}", X, 0.10 if i == 0 else 0.045) for i in range(A.N_TAIL)]
    P["tail_side"] = [(f"tail{i+1:02d}", Z, 0.05 + 0.01 * (i < 4)) for i in range(A.N_TAIL)]
    P["tail_curl"] = [(f"tail{i+1:02d}", Z, 0.02 + 0.012 * i) for i in range(A.N_TAIL)]
    P["fan_spread"] = [("fan1", Z, 0.32), ("fan2", Z, 0.14), ("fan4", Z, -0.14), ("fan5", Z, -0.32)]
    P["fan_raise"] = [(f"fan{i+1}", X, 0.25) for i in range(5)]
    P["body_lower"] = [("hips", Z, -0.12, "loc")]
    P["front_lower"] = [("hips", X, 0.16), ("chest", X, 0.06), ("neck1", X, -0.10)]
    P["body_lean"] = [("hips", Z, 0.0), ("root", X, 0.0)]  # reservado
    P["shoulders_up"] = [("shoulder.L", FW, 0.10), ("shoulder.R", FW, 0.10)]
    # ajustes de ala sobre la pose plegada
    P["wing_lift"] = [("humerus.L", FW, 0.25), ("humerus.R", FW, 0.25)]
    P["wing_open"] = []  # 0 plegada, 1 extendida (mezcla con wingFold)
    out = {}
    for k, lst in P.items():
        out[k] = [[b, list(map(float, ax)), float(g), (t[0] if (t := rest) else "rot")]
                  for (b, ax, g, *rest) in lst]
    return out


# Parámetros "de material/forma" (no óseos)
EXTRA = ["pupil", "glow", "snarl", "smile", "nostril", "throat", "breath", "wing_open"]

NEUTRAL = dict(head_pitch=0.0, head_yaw=0.0, head_tilt=0.0, neck_raise=0.0, neck_reach=0.0,
               jaw_open=0.0, tongue_out=0.0, lid_up=0.10, lid_lo=0.05, eye_yaw=0.0, eye_pitch=0.0,
               brow_down=0.0, frill_flare=0.0, frill_spread=0.0, tail_raise=0.0, tail_side=0.0,
               tail_curl=0.0, fan_spread=0.0, fan_raise=0.0, body_lower=0.0, front_lower=0.0,
               shoulders_up=0.0, wing_lift=0.0, wing_open=0.0,
               pupil=0.30, glow=0.15, snarl=0.0, smile=0.0, nostril=0.0, throat=0.0, breath=0.0)

# Preajustes emocionales (valores objetivo; la app añade la conducta dinámica)
EMOTIONS = {
    "calma": dict(),
    "curiosidad": dict(head_tilt=0.55, head_pitch=-0.10, neck_reach=0.25, lid_up=-0.20, lid_lo=0.0,
                       pupil=0.55, frill_flare=0.35, frill_spread=0.30, brow_down=-0.5, tail_raise=0.2,
                       fan_spread=0.3, glow=0.35, nostril=0.3),
    "alegria": dict(head_pitch=-0.12, neck_raise=0.25, jaw_open=0.22, smile=1.0, lid_lo=0.35, lid_up=0.0,
                    pupil=0.70, frill_flare=0.80, frill_spread=0.85, tail_raise=0.45, fan_spread=0.9,
                    fan_raise=0.4, glow=0.6, brow_down=-0.4, wing_lift=0.25, tongue_out=0.3),
    "desconfianza": dict(head_pitch=0.30, neck_raise=-0.30, neck_reach=0.15, lid_up=0.45, lid_lo=0.35,
                         pupil=0.10, frill_flare=-0.55, frill_spread=-0.3, brow_down=0.7, tail_raise=-0.25,
                         fan_spread=-0.4, glow=0.15, body_lower=0.6, shoulders_up=0.4),
    "enfado": dict(head_pitch=0.30, neck_reach=0.55, neck_raise=-0.15, jaw_open=0.55, snarl=1.0, lid_up=0.30,
                   lid_lo=0.30, pupil=0.04, frill_flare=1.0, frill_spread=1.0, brow_down=1.0, tail_raise=0.35,
                   fan_spread=1.0, fan_raise=0.6, glow=1.0, throat=1.0, nostril=1.0, wing_open=0.30,
                   wing_lift=0.6, body_lower=0.8, front_lower=0.4, shoulders_up=1.0),
    "ternura": dict(head_tilt=-0.35, head_pitch=0.18, neck_reach=0.35, lid_up=0.42, lid_lo=0.25, pupil=0.65,
                    frill_flare=-0.30, frill_spread=-0.2, smile=0.6, brow_down=-0.3, tail_raise=-0.1,
                    tail_curl=0.6, glow=0.45),
    "sorpresa": dict(neck_raise=0.65, head_pitch=-0.15, lid_up=-0.45, lid_lo=-0.2, pupil=0.95, jaw_open=0.18,
                     frill_flare=1.0, frill_spread=0.9, brow_down=-1.0, tail_raise=0.3, fan_spread=0.8,
                     glow=0.55, wing_open=0.25, wing_lift=0.7, nostril=0.6),
    "somnolencia": dict(head_pitch=0.35, neck_raise=-0.55, neck_reach=0.1, lid_up=0.72, lid_lo=0.45, pupil=0.80,
                        frill_flare=-0.6, frill_spread=-0.4, tail_raise=-0.4, tail_curl=0.9, glow=0.12,
                        body_lower=0.9, front_lower=0.25, fan_spread=-0.5),
    "juego": dict(front_lower=1.0, head_pitch=-0.25, neck_raise=-0.1, jaw_open=0.30, tongue_out=0.4, smile=0.8,
                  pupil=0.85, lid_up=-0.15, lid_lo=0.2, frill_flare=0.7, frill_spread=0.8, tail_raise=0.9,
                  fan_spread=1.0, fan_raise=0.5, glow=0.7, wing_lift=0.4, wing_open=0.12, brow_down=-0.5),
}
