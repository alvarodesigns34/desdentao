"""
Paso 4 — Renders de verificación / cinematográficos.

    blender -b output/vesper.blend -P blender/04_render.py -- \
        --cams Cam_Heroe,Cam_Cabeza --action Reposo --frame 40 \
        --samples 128 --res 1600x900 --out renders/ --tag v1 [--wings 0..1] [--rest]

--rest        : pose de reposo (T-pose) sin acción, para revisar la escultura
--wings X     : fuerza la apertura de alas (sobrescribe la acción)
"""
import sys, os
import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d):
    return type(d)(argv[argv.index(n) + 1]) if n in argv else d

cams = arg("--cams", "Cam_Heroe").split(",")
action = arg("--action", "Reposo")
frame = arg("--frame", 40)
samples = arg("--samples", 96)
res = arg("--res", "1600x900")
out = arg("--out", "renders")
tag = arg("--tag", "")
wings = arg("--wings", -1.0)
rest = "--rest" in argv

sc = bpy.context.scene
arm = bpy.data.objects["VesperRig"]
sc.cycles.samples = samples
sc.render.resolution_x, sc.render.resolution_y = map(int, res.split("x"))
if rest:
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
        for c in pb.constraints:
            c.mute = True
else:
    act = bpy.data.actions.get(action) or bpy.data.actions.get("Emocion_" + action)
    arm.animation_data.action = act
sc.frame_set(frame)
if wings >= 0:
    # se aplica tras la acción mediante un manejador
    arm["wing_open"] = wings
os.makedirs(out, exist_ok=True)
from mathutils import Vector
track = "--track" in argv
for c in cams:
    sc.camera = bpy.data.objects[c]
    if track:
        # encuadre que sigue a la cabeza posada (para expresiones)
        bpy.context.view_layer.update()
        hb = arm.pose.bones["head"]
        M = arm.matrix_world @ hb.matrix
        hp = M @ Vector((0, 0.22, 0.02))           # centro del cráneo/hocico
        fwd = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
        side = Vector((1, 0, 0))
        cam = sc.camera
        cam.location = hp + fwd * 1.15 + side * 0.85 + Vector((0, 0, 0.18))
        cam.rotation_euler = (hp - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = 70
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = (hp - cam.location).length - 0.05
        cam.data.dof.aperture_fstop = 4.0
    sc.render.filepath = os.path.join(out, f"{c}{('_' + tag) if tag else ''}.png")
    bpy.ops.render.render(write_still=True)
    print("render:", sc.render.filepath)
