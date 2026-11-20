"""Vista previa rápida (arcilla) de una malla .npz — blender -b -P preview_raw.py -- in.npz outprefix"""
import sys, math
import bpy, numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
src, prefix = argv[0], argv[1]
views = argv[2].split(",") if len(argv) > 2 else ["front", "side", "q34", "back", "top", "head"]

bpy.ops.wm.read_factory_settings(use_empty=True)
d = np.load(src)
V, F = d["V"], d["F"]
me = bpy.data.meshes.new("raw")
me.vertices.add(len(V)); me.vertices.foreach_set("co", V.ravel())
me.loops.add(F.size); me.loops.foreach_set("vertex_index", F.ravel())
me.polygons.add(len(F)); me.polygons.foreach_set("loop_start", np.arange(0, F.size, 3)); me.polygons.foreach_set("loop_total", np.full(len(F), 3))
me.update(); me.validate()
me.shade_smooth()
ob = bpy.data.objects.new("raw", me); bpy.context.scene.collection.objects.link(ob)
mat = bpy.data.materials.new("clay"); mat.use_nodes = True
bs = mat.node_tree.nodes["Principled BSDF"]; bs.inputs["Base Color"].default_value = (0.55, 0.55, 0.58, 1); bs.inputs["Roughness"].default_value = 0.55
me.materials.append(mat)

sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = 24; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 960, 640
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.37, 0.42, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
for loc, e in (((3, -4, 5), 600), ((-4, -2, 3), 250), ((0, 5, 4), 300)):
    L = bpy.data.lights.new("l", "AREA"); L.energy = e; L.size = 3
    lo = bpy.data.objects.new("l", L); sc.collection.objects.link(lo); lo.location = loc
    lo.rotation_euler = (Vector((0, 0.5, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
cam = bpy.data.cameras.new("c"); co = bpy.data.objects.new("c", cam); sc.collection.objects.link(co); sc.camera = co
VIEWS = {
    "front": ((0, -7.5, 1.5), (0, -0.2, 1.0), 40),
    "side": ((8.5, 0.6, 1.2), (0, 0.8, 0.9), 40),
    "q34": ((4.5, -5.5, 2.4), (0, 0.2, 1.0), 40),
    "back": ((-2.5, 7.5, 2.5), (0, 0.3, 1.0), 40),
    "top": ((0, 0.8, 10), (0, 0.8, 0), 40),
    "head": ((1.1, -2.6, 1.9), (0, -1.38, 1.7), 50),
    "headside": ((1.6, -1.4, 1.75), (0, -1.4, 1.72), 50),
    "headfront": ((0.0, -2.9, 1.75), (0, -1.4, 1.72), 60),
}
for v in views:
    loc, tgt, lens = VIEWS[v]
    co.location = loc; cam.lens = lens
    co.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = f"{prefix}_{v}.png"
    bpy.ops.render.render(write_still=True)
