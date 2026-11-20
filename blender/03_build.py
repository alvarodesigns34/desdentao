"""
Paso 3 — Construcción completa de la escena de Vesper en Blender.

    blender -b -P blender/03_build.py -- [--hero-faces 520000] [--web-faces 120000] [--no-web]

Produce:
  output/vesper.blend         escena editable (modelo, materiales, rig, acciones, luces, cámaras)
  web/public/vesper.glb       versión optimizada para tiempo real
  web/public/rig.json         definición del rig expresivo (parámetros, emociones, plegado alar)
"""
import os, sys, json, math, time
import numpy as np
import bpy, bmesh
from mathutils import Vector, Matrix, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "lib"))
import anatomy as A  # noqa
import parts as PARTS  # noqa
import bodydata as BD  # noqa
import rigdef as RD  # noqa

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default
HERO_FACES = arg("--hero-faces", 520000)
WEB_FACES = arg("--web-faces", 120000)
DO_WEB = "--no-web" not in argv
RAW = arg("--raw", os.path.join(ROOT, "build", "body_raw.npz"))
TEX = os.path.join(ROOT, "assets", "textures")
OUT_BLEND = os.path.join(ROOT, "output", "vesper.blend")
OUT_WEB = os.path.join(ROOT, "web", "public")
os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
os.makedirs(OUT_WEB, exist_ok=True)
T0 = time.time()
def log(*a):
    print(f"[{time.time()-T0:7.1f}s]", *a, flush=True)


# ===========================================================================
# utilidades
# ===========================================================================
def mesh_from_arrays(name, V, F, smooth=True):
    me = bpy.data.meshes.new(name)
    V = np.asarray(V, np.float32)
    if isinstance(F, np.ndarray) and F.ndim == 2:
        loops = F.ravel(); counts = np.full(len(F), F.shape[1])
    else:
        counts = np.array([len(f) for f in F]); loops = np.array([i for f in F for i in f])
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    me.vertices.add(len(V)); me.vertices.foreach_set("co", V.ravel())
    me.loops.add(len(loops)); me.loops.foreach_set("vertex_index", loops.astype(np.int32))
    me.polygons.add(len(counts)); me.polygons.foreach_set("loop_start", starts.astype(np.int32))
    me.polygons.foreach_set("loop_total", counts.astype(np.int32))
    me.update(calc_edges=True); me.validate()
    if smooth:
        me.shade_smooth()
    return me


def mesh_arrays(me):
    V = np.zeros(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", V)
    me.calc_loop_triangles() if hasattr(me, "calc_loop_triangles") else None
    N = np.zeros(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("normal", N)
    return V.reshape(-1, 3).astype(np.float64), N.reshape(-1, 3).astype(np.float64)


def link(ob, coll=None):
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def new_coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def set_weights(ob, order, top, names):
    """Asigna pesos top-4 agrupando por valor cuantizado (rápido)."""
    vgs = {}
    q = np.round(top * 1000).astype(int)
    for k in range(order.shape[1]):
        for bi in np.unique(order[:, k]):
            m = (order[:, k] == bi) & (q[:, k] > 0)
            if not m.any():
                continue
            name = names[bi]
            vg = vgs.get(name) or ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
            vgs[name] = vg
            idx = np.where(m)[0]; vals = q[m, k]
            for val in np.unique(vals):
                vg.add(idx[vals == val].tolist(), val / 1000.0, "ADD")


def set_weights_dicts(ob, W):
    names = sorted({b for d in W for b in d})
    bi = {n: i for i, n in enumerate(names)}
    M = np.zeros((len(W), len(names)), np.float32)
    for i, d in enumerate(W):
        for b, w in d.items():
            M[i, bi[b]] += w
    order = np.argsort(-M, axis=1)[:, :4]
    top = np.take_along_axis(M, order, 1)
    top = np.where(top < 0.005, 0, top)
    top /= np.maximum(top.sum(1, keepdims=True), 1e-9)
    set_weights(ob, order, top, names)


def add_uv(me, name, UVv):
    """UV por vértice -> por bucle."""
    uvl = me.uv_layers.new(name=name)
    li = np.zeros(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", li)
    uvl.data.foreach_set("uv", np.asarray(UVv, np.float32)[li].ravel())
    return uvl


def add_color(me, name, C):
    ca = me.color_attributes.new(name=name, type="FLOAT_COLOR", domain="POINT")
    ca.data.foreach_set("color", np.asarray(C, np.float32).ravel())
    return ca


def decimate(ob, faces_target, name):
    nf = len(ob.data.polygons)
    ratio = min(1.0, faces_target / nf)
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.ratio = ratio; mod.use_symmetry = True; mod.symmetry_axis = "X"
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.remove(mod)
    me.name = name
    return me


def smooth_mesh(me, iters=2, fac=0.5):
    bm = bmesh.new(); bm.from_mesh(me)
    for _ in range(iters):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=fac, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(me); bm.free(); me.update()


# ===========================================================================
# escena
# ===========================================================================
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.name = "Vesper"
scene.unit_settings.system = "METRIC"
scene.render.fps = 30

prims = A.build_prims()
BONES = A.build_bones()
log(f"{len(prims)} primitivas, {len(BONES)} huesos")

C_MODEL = new_coll("Vesper")
C_WEB = new_coll("Vesper_web")
C_ENV = new_coll("Estudio")

# ===========================================================================
# 1. Armature
# ===========================================================================
arm_data = bpy.data.armatures.new("VesperRig")
arm = link(bpy.data.objects.new("VesperRig", arm_data), C_MODEL)
arm_data.display_type = "OCTAHEDRAL"
arm.show_in_front = True
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones
for name, (h, t, p, d) in BONES.items():
    b = eb.new(name)
    b.head = Vector(h); b.tail = Vector(t)
    b.use_deform = d
    # roll: eje Z local lo más cercano posible al "arriba" del mundo
    b.align_roll(Vector((0, 0, 1)) if abs((Vector(t) - Vector(h)).normalized().z) < 0.9 else Vector((0, -1, 0)))
for name, (h, t, p, d) in BONES.items():
    if p:
        eb[name].parent = eb[p]
        eb[name].use_connect = False
# controles IK (no deforman)
IK = {}
for sx, s in (("L", 1), ("R", -1)):
    for leg, bone, pole_off in (("hand", f"hand.{sx}", (0, 0.9, 0)), ("foot", f"foot.{sx}", (0, -0.9, 0))):
        # el control IK se coloca en la cabeza del hueso final (muñeca / corvejón) y con su misma
        # orientación, de modo que en reposo la cadena no cambia y la pata copia su rotación
        h0, t0 = Vector(BONES[bone][0]), Vector(BONES[bone][1])
        c = eb.new(f"IK_{leg}.{sx}"); c.head = h0; c.tail = t0; c.use_deform = False
        c.roll = eb[bone].roll
        c.parent = eb["root"]
        lower = f"forearm.{sx}" if leg == "hand" else f"shin.{sx}"
        mid = Vector(BONES[lower][0])
        pl = eb.new(f"POLE_{leg}.{sx}"); pl.head = mid + Vector(pole_off); pl.tail = pl.head + Vector((0, 0, 0.1))
        pl.use_deform = False; pl.parent = eb["root"]
        IK[lower] = (c.name, pl.name)
bpy.ops.object.mode_set(mode="POSE")
for lower, (tgt, pole) in IK.items():
    pb = arm.pose.bones[lower]
    con = pb.constraints.new("IK")
    con.target = arm; con.subtarget = tgt; con.pole_target = arm; con.pole_subtarget = pole
    con.chain_count = 2; con.pole_angle = math.radians(-90)
    # la mano/pie mantiene la orientación del control
    pe = arm.pose.bones[lower.replace("forearm", "hand").replace("shin", "foot")]
    cr = pe.constraints.new("COPY_ROTATION"); cr.target = arm; cr.subtarget = tgt
    cr.mix_mode = "REPLACE"; cr.target_space = "WORLD"; cr.owner_space = "WORLD"
    cr.influence = 1.0
for pb in arm.pose.bones:
    pb.rotation_mode = "QUATERNION"
# grupos de color (colecciones de huesos)
bc_def = arm_data.collections.new("Deformación")
bc_ctl = arm_data.collections.new("Controles")
for b in arm_data.bones:
    (bc_def if b.use_deform else bc_ctl).assign(b)
bpy.ops.object.mode_set(mode="OBJECT")
# propiedades personalizadas que gobiernan materiales y shape keys
for k in RD.EXTRA:
    arm[k] = float(RD.NEUTRAL.get(k, 0.0))
    arm.id_properties_ui(k).update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0)
log("armature lista")

# ===========================================================================
# 2. Cuerpo (malla SDF)
# ===========================================================================
d = np.load(RAW)
raw_ob = link(bpy.data.objects.new("raw", mesh_from_arrays("raw", d["V"], d["F"])), C_WEB)
log(f"malla bruta: {len(d['V'])} v, {len(d['F'])} caras")


def build_body(name, faces, coll, smooth_iters=2):
    me = decimate(raw_ob, faces, name)
    smooth_mesh(me, smooth_iters, 0.35)
    me.shade_smooth()
    ob = link(bpy.data.objects.new(name, me), coll)
    V, N = mesh_arrays(me)
    log(f"{name}: {len(V)} vértices, {len(me.polygons)} caras — calculando datos")
    (order, top, names), masks, bodyuv = BD.compute(prims, V, N, BONES, log=lambda *a: None)
    set_weights(ob, order, top, names)
    add_uv(me, "bodyuv", bodyuv)
    add_uv(me, "kdata", np.stack([masks["kgrad"], masks["cavity"]], 1))
    add_uv(me, "bodym", masks["bodym"])
    add_color(me, "masks", np.stack([masks["keratin"], masks["tube"], masks["mouth"], masks["ao"]], 1))
    me.color_attributes.active_color_name = "masks"
    me.color_attributes.render_color_index = me.color_attributes.find("masks")
    # shape keys
    keys = BD.shape_keys(V, N, masks, bodyuv)
    ob.shape_key_add(name="Basis", from_mix=False)
    for kname, disp in keys.items():
        sk = ob.shape_key_add(name=kname, from_mix=False)
        sk.data.foreach_set("co", (V + disp).astype(np.float32).ravel())
    log(f"{name}: datos listos")
    return ob


body = build_body("VesperBody", HERO_FACES, C_MODEL)

# ===========================================================================
# 3. Piezas
# ===========================================================================
PARTS_LIST = PARTS.all_parts(prims)


def build_part(p, coll, suffix=""):
    me = mesh_from_arrays(p["name"] + suffix, p["V"], p["F"])
    ob = link(bpy.data.objects.new(p["name"] + suffix, me), coll)
    if "UV" in p:
        add_uv(me, "UVMap", p["UV"])
    set_weights_dicts(ob, p["W"])
    ob["mat"] = p["mat"]
    return ob


part_obs = [build_part(p, C_MODEL) for p in PARTS_LIST]
log(f"{len(part_obs)} piezas")

# ===========================================================================
# 4. Materiales (Cycles / Principled BSDF)
# ===========================================================================
def img(name, colorspace="sRGB"):
    im = bpy.data.images.load(os.path.join(TEX, name), check_existing=True)
    im.colorspace_settings.name = colorspace
    return im


class NB:
    """Ayudante para construir árboles de nodos."""
    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree; self.n = self.nt.nodes; self.l = self.nt.links
        self.n.clear()
        self.x = 0
    def node(self, kind, **kw):
        nd = self.n.new(kind)
        for k, v in kw.items():
            if k == "inputs":
                for ik, iv in v.items():
                    nd.inputs[ik].default_value = iv
            else:
                setattr(nd, k, v)
        return nd
    def link(self, a, b):
        self.l.new(a, b)
    def math(self, op, a, b=None, c=None, clamp=False):
        nd = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                nd.inputs[i].default_value = v
            else:
                self.link(v, nd.inputs[i])
        return nd.outputs[0]
    def mix(self, fac, a, b, blend="MIX"):
        nd = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        for k, (sock, v) in enumerate(((nd.inputs[0], fac), (nd.inputs[6], a), (nd.inputs[7], b))):
            if isinstance(v, (int, float)):
                sock.default_value = v if k == 0 else (v, v, v, 1.0)
            elif isinstance(v, tuple):
                sock.default_value = v
            else:
                self.link(v, sock)
        return nd.outputs[2]
    def attr(self, name, kind="GEOMETRY"):
        nd = self.node("ShaderNodeAttribute", attribute_name=name, attribute_type=kind)
        return nd
    def uv(self, name):
        nd = self.node("ShaderNodeUVMap", uv_map=name)
        return nd.outputs[0]
    def sep(self, vec):
        nd = self.node("ShaderNodeSeparateXYZ"); self.link(vec, nd.inputs[0]); return nd.outputs
    def drv_value(self, prop, default=0.0):
        """Nodo Valor con driver desde una propiedad del rig."""
        nd = self.node("ShaderNodeValue"); nd.outputs[0].default_value = default
        fc = nd.outputs[0].driver_add("default_value")
        dv = fc.driver; dv.type = "AVERAGE"
        var = dv.variables.new(); var.name = "v"; var.type = "SINGLE_PROP"
        var.targets[0].id = arm; var.targets[0].data_path = f'["{prop}"]'
        return nd.outputs[0]


BBOX_LO = np.array([-2.95, -1.85, -0.02]); BBOX_SIZE = None


def generated_meters(nb, ob):
    """Coordenadas 'Generated' (sin deformar) reescaladas a metros."""
    dims = np.array(ob.data.vertices[0].co) * 0  # placeholder
    V, _ = mesh_arrays(ob.data)
    lo, hi = V.min(0), V.max(0)
    tc = nb.node("ShaderNodeTexCoord")
    mp = nb.node("ShaderNodeMapping", vector_type="POINT")
    mp.inputs["Scale"].default_value = tuple(hi - lo)
    mp.inputs["Location"].default_value = tuple(lo)
    # Generated (0..1) * size + lo -> metros; el orden de Mapping es escala, rotación, traslación
    nb.link(tc.outputs["Generated"], mp.inputs[0])
    return mp.outputs[0]


def box_tex(nb, vec, image, scale, colorspace="Non-Color"):
    mp = nb.node("ShaderNodeMapping", vector_type="POINT")
    mp.inputs["Scale"].default_value = (1 / scale,) * 3
    nb.link(vec, mp.inputs[0])
    t = nb.node("ShaderNodeTexImage", image=image, projection="BOX", projection_blend=0.25, interpolation="Cubic")
    t.image.colorspace_settings.name = colorspace
    nb.link(mp.outputs[0], t.inputs[0])
    return t


GLOW_COL = (1.0, 0.36, 0.06, 1.0)


def mat_skin(ob):
    m = bpy.data.materials.new("VesperSkin")
    nb = NB(m)
    out = nb.node("ShaderNodeOutputMaterial")
    bs = nb.node("ShaderNodeBsdfPrincipled")
    nb.link(bs.outputs[0], out.inputs[0])
    gm = generated_meters(nb, ob)
    sc = box_tex(nb, gm, img("scales_data.png", "Non-Color"), 0.30)
    sc_fine = box_tex(nb, gm, img("scales_data.png", "Non-Color"), 0.11)
    scs = nb.node("ShaderNodeSeparateColor"); nb.link(sc.outputs[0], scs.inputs[0])
    scf = nb.node("ShaderNodeSeparateColor"); nb.link(sc_fine.outputs[0], scf.inputs[0])
    masks = nb.attr("masks")
    ms = nb.node("ShaderNodeSeparateColor"); nb.link(masks.outputs["Color"], ms.inputs[0])
    ker, tube, mouth = ms.outputs[0], ms.outputs[1], ms.outputs[2]
    ao = masks.outputs["Alpha"]
    kd = nb.sep(nb.uv("kdata"))
    kgrad, cav = kd[0], kd[1]
    # mapa corporal
    bm = nb.node("ShaderNodeTexImage", image=img("bodymap.png", "Non-Color"), interpolation="Linear", extension="EXTEND")
    nb.link(nb.uv("bodyuv"), bm.inputs[0])
    bms = nb.node("ShaderNodeSeparateColor"); nb.link(bm.outputs[0], bms.inputs[0])
    glowmask = nb.math("MULTIPLY", bms.outputs[0], tube)
    scute = nb.math("MULTIPLY", bms.outputs[1], tube)
    belly = nb.math("MULTIPLY", bms.outputs[2], tube)
    # variación de baja frecuencia
    noise = nb.node("ShaderNodeTexNoise", inputs={"Scale": 3.0, "Detail": 4.0, "Roughness": 0.55})
    nb.link(gm, noise.inputs["Vector"])
    # --- color base ---------------------------------------------------------
    back = (0.008, 0.009, 0.013, 1); flank = (0.016, 0.017, 0.025, 1); bellyc = (0.060, 0.050, 0.043, 1)
    vrng = nb.node("ShaderNodeMapRange", inputs={"From Min": 0.25, "From Max": 0.65})
    bu = nb.sep(nb.uv("bodyuv"))
    nb.link(bu[1], vrng.inputs[0])
    col = nb.mix(vrng.outputs[0], back, flank)
    col = nb.mix(belly, col, bellyc)
    # variación por escama y ruido
    tint = nb.math("MULTIPLY_ADD", scs.outputs[1], 0.35, 0.80)
    col = nb.mix(1.0, col, tint, "MULTIPLY") if False else col
    tintc = nb.node("ShaderNodeCombineColor"); [nb.link(tint, tintc.inputs[i]) for i in range(3)]
    col = nb.mix(1.0, col, tintc.outputs[0], "MULTIPLY")
    nz = nb.node("ShaderNodeMapRange", inputs={"From Min": 0.3, "From Max": 0.7, "To Min": 0.75, "To Max": 1.25})
    nb.link(noise.outputs[0], nz.inputs[0])
    nzc = nb.node("ShaderNodeCombineColor"); [nb.link(nz.outputs[0], nzc.inputs[i]) for i in range(3)]
    col = nb.mix(1.0, col, nzc.outputs[0], "MULTIPLY")
    # cavidades entre escamas más oscuras
    cavd = nb.math("MULTIPLY_ADD", scs.outputs[2], -0.45, 1.0)
    cavc = nb.node("ShaderNodeCombineColor"); [nb.link(cavd, cavc.inputs[i]) for i in range(3)]
    col = nb.mix(1.0, col, cavc.outputs[0], "MULTIPLY")
    # queratina: base oscura -> punta marfil
    kc = nb.mix(nb.math("POWER", kgrad, 1.7), (0.020, 0.018, 0.016, 1), (0.13, 0.11, 0.08, 1))
    col = nb.mix(ker, col, kc)
    col = nb.mix(mouth, col, (0.20, 0.035, 0.04, 1))
    col = nb.mix(cav, col, (0.004, 0.003, 0.003, 1))
    aop = nb.math("POWER", ao, 0.8)
    aoc = nb.node("ShaderNodeCombineColor"); [nb.link(aop, aoc.inputs[i]) for i in range(3)]
    col = nb.mix(1.0, col, aoc.outputs[0], "MULTIPLY")
    nb.link(col, bs.inputs["Base Color"])
    # --- rugosidad -------------------------------------------------------------
    rough = nb.math("MULTIPLY_ADD", scs.outputs[2], 0.20, 0.46)
    rough = nb.math("ADD", rough, nb.math("MULTIPLY", scs.outputs[1], 0.10))
    rough = nb.math("ADD", rough, nb.math("MULTIPLY", belly, 0.10))
    rough = nb.mix(ker, rough, 0.30)
    rough = nb.mix(mouth, rough, 0.22)
    nb.link(rough, bs.inputs["Roughness"])
    # --- relieve ---------------------------------------------------------------
    h = nb.math("ADD", nb.math("MULTIPLY", scs.outputs[0], nb.math("SUBTRACT", 1.0, ker)),
                nb.math("MULTIPLY", scf.outputs[0], 0.35))
    h = nb.math("ADD", h, nb.math("MULTIPLY", scute, 1.4))
    bump = nb.node("ShaderNodeBump", inputs={"Strength": 0.55, "Distance": 0.0035})
    nb.link(h, bump.inputs["Height"])
    nb.link(bump.outputs[0], bs.inputs["Normal"])
    # --- iridiscencia, capa, SSS ---------------------------------------------
    tf = nb.math("MULTIPLY_ADD", noise.outputs[0], 200.0, 280.0)
    nb.link(tf, bs.inputs["Thin Film Thickness"])
    bs.inputs["Thin Film IOR"].default_value = 1.38
    bs.inputs["Coat Weight"].default_value = 0.06
    bs.inputs["Coat Roughness"].default_value = 0.35
    bs.inputs["Subsurface Weight"].default_value = 0.04
    bs.inputs["Subsurface Radius"].default_value = (0.9, 0.25, 0.12)
    bs.inputs["Subsurface Scale"].default_value = 0.012
    bs.inputs["Specular IOR Level"].default_value = 0.28
    # --- brillo de brasa -----------------------------------------------------
    glow = nb.drv_value("glow", RD.NEUTRAL["glow"])
    pulse = nb.math("MULTIPLY", glowmask, glow)
    throat = nb.drv_value("throat", 0.0)
    nb.link(pulse, bs.inputs["Emission Strength"]) if False else None
    es = nb.math("MULTIPLY", nb.math("ADD", pulse, nb.math("MULTIPLY", nb.math("MULTIPLY", mouth, throat), 0.0012)), 7.0)
    nb.link(es, bs.inputs["Emission Strength"])
    bs.inputs["Emission Color"].default_value = GLOW_COL
    return m


def mat_lid():
    """Párpados: misma piel, sin mapas corporales (UV propias)."""
    m = bpy.data.materials.new("VesperLid")
    nb = NB(m)
    out = nb.node("ShaderNodeOutputMaterial"); bs = nb.node("ShaderNodeBsdfPrincipled")
    nb.link(bs.outputs[0], out.inputs[0])
    tc = nb.node("ShaderNodeTexCoord")
    sc = box_tex(nb, tc.outputs["Object"], img("scales_data.png", "Non-Color"), 0.07)
    scs = nb.node("ShaderNodeSeparateColor"); nb.link(sc.outputs[0], scs.inputs[0])
    uvs = nb.sep(nb.uv("UVMap"))
    margin = nb.math("GREATER_THAN", uvs[1], 0.50)  # margen redondeado + cara interior
    col = nb.mix(margin, (0.014, 0.015, 0.021, 1), (0.035, 0.012, 0.012, 1))
    nb.link(col, bs.inputs["Base Color"])
    nb.link(nb.mix(margin, 0.42, 0.15), bs.inputs["Roughness"])
    bump = nb.node("ShaderNodeBump", inputs={"Strength": 0.4, "Distance": 0.002})
    nb.link(scs.outputs[0], bump.inputs["Height"]); nb.link(bump.outputs[0], bs.inputs["Normal"])
    bs.inputs["Thin Film Thickness"].default_value = 320
    bs.inputs["Coat Weight"].default_value = 0.15
    return m


def mat_eye():
    m = bpy.data.materials.new("VesperEye")
    nb = NB(m)
    out = nb.node("ShaderNodeOutputMaterial"); bs = nb.node("ShaderNodeBsdfPrincipled")
    nb.link(bs.outputs[0], out.inputs[0])
    uv = nb.uv("UVMap")
    iris = nb.node("ShaderNodeTexImage", image=img("iris.png"), extension="EXTEND", interpolation="Cubic")
    nb.link(uv, iris.inputs[0])
    # pupila hendida: ((x/w)^2 + (y/h)^2) < 1
    s = nb.sep(uv)
    x = nb.math("MULTIPLY_ADD", s[0], 2.0, -1.0); y = nb.math("MULTIPLY_ADD", s[1], 2.0, -1.0)
    pup = nb.drv_value("pupil", RD.NEUTRAL["pupil"])
    w = nb.math("MULTIPLY_ADD", pup, 0.58, 0.06)
    hgt = nb.math("MULTIPLY_ADD", pup, 0.10, 0.80)
    r = nb.math("SQRT", nb.math("ADD", nb.math("POWER", nb.math("DIVIDE", x, w), 2.0),
                                       nb.math("POWER", nb.math("DIVIDE", y, hgt), 2.0)))
    pm = nb.node("ShaderNodeMapRange", inputs={"From Min": 0.92, "From Max": 1.08, "To Min": 1.0, "To Max": 0.0})
    nb.link(r, pm.inputs[0])
    col = nb.mix(pm.outputs[0], iris.outputs[0], (0.002, 0.0015, 0.001, 1))
    nb.link(col, bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = 0.35
    em = nb.mix(pm.outputs[0], iris.outputs[0], (0, 0, 0, 1))
    nb.link(em, bs.inputs["Emission Color"])
    bs.inputs["Emission Strength"].default_value = 0.12
    bump = nb.node("ShaderNodeBump", inputs={"Strength": 0.25, "Distance": 0.001})
    nb.link(iris.outputs["Alpha"], bump.inputs["Height"]); nb.link(bump.outputs[0], bs.inputs["Normal"])
    return m


def mat_simple(name, col, rough, sss=0.0, coat=0.0, trans=0.0, ior=1.45, emit=None, tf=0):
    m = bpy.data.materials.new(name)
    nb = NB(m)
    out = nb.node("ShaderNodeOutputMaterial"); bs = nb.node("ShaderNodeBsdfPrincipled")
    nb.link(bs.outputs[0], out.inputs[0])
    bs.inputs["Base Color"].default_value = col
    bs.inputs["Roughness"].default_value = rough
    bs.inputs["Subsurface Weight"].default_value = sss
    bs.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
    bs.inputs["Subsurface Scale"].default_value = 0.004
    bs.inputs["Coat Weight"].default_value = coat
    bs.inputs["Transmission Weight"].default_value = trans
    bs.inputs["IOR"].default_value = ior
    bs.inputs["Thin Film Thickness"].default_value = tf
    if emit:
        bs.inputs["Emission Color"].default_value = emit[0]; bs.inputs["Emission Strength"].default_value = emit[1]
    return m


def mat_membrane(name, veins_scale=(1.0, 1.0), kind="wing"):
    m = bpy.data.materials.new(name)
    nb = NB(m)
    out = nb.node("ShaderNodeOutputMaterial"); bs = nb.node("ShaderNodeBsdfPrincipled")
    tr = nb.node("ShaderNodeBsdfTranslucent")
    mx = nb.node("ShaderNodeMixShader")
    uv = nb.uv("UVMap")
    vt = nb.node("ShaderNodeTexImage", image=img("wing_veins.png", "Non-Color"), extension="EXTEND")
    nb.link(uv, vt.inputs[0])
    vs = nb.node("ShaderNodeSeparateColor"); nb.link(vt.outputs[0], vs.inputs[0])
    veins, thick, edge = vs.outputs[0], vs.outputs[1], vs.outputs[2]
    base = nb.mix(veins, (0.020, 0.019, 0.027, 1), (0.008, 0.007, 0.010, 1))
    nb.link(base, bs.inputs["Base Color"])
    nb.link(nb.math("MULTIPLY_ADD", thick, 0.15, 0.62), bs.inputs["Roughness"])
    bs.inputs["Specular IOR Level"].default_value = 0.3
    bump = nb.node("ShaderNodeBump", inputs={"Strength": 0.6, "Distance": 0.002})
    nb.link(veins, bump.inputs["Height"]); nb.link(bump.outputs[0], bs.inputs["Normal"])
    bs.inputs["Thin Film Thickness"].default_value = 300
    bs.inputs["Coat Weight"].default_value = 0.05
    # translucidez: rojo profundo, venas más opacas
    tcol = nb.mix(veins, (0.05, 0.010, 0.009, 1), (0.008, 0.002, 0.002, 1))
    nb.link(tcol, tr.inputs["Color"])
    nb.link(bump.outputs[0], tr.inputs["Normal"])
    fac = nb.math("MULTIPLY_ADD", thick, -0.04, 0.10)
    nb.link(fac, mx.inputs[0]); nb.link(bs.outputs[0], mx.inputs[1]); nb.link(tr.outputs[0], mx.inputs[2])
    # brillo en el borde de fuga
    glow = nb.drv_value("glow", RD.NEUTRAL["glow"])
    e = nb.math("MULTIPLY", nb.math("MULTIPLY", edge, glow), 2.5 if kind == "wing" else 4.0)
    em = nb.node("ShaderNodeEmission"); em.inputs["Color"].default_value = GLOW_COL
    nb.link(e, em.inputs["Strength"])
    add = nb.node("ShaderNodeAddShader"); nb.link(mx.outputs[0], add.inputs[0]); nb.link(em.outputs[0], add.inputs[1])
    nb.link(add.outputs[0], out.inputs[0])
    return m


def mat_keratin():
    m = bpy.data.materials.new("VesperKeratin")
    nb = NB(m)
    out = nb.node("ShaderNodeOutputMaterial"); bs = nb.node("ShaderNodeBsdfPrincipled")
    nb.link(bs.outputs[0], out.inputs[0])
    tc = nb.node("ShaderNodeTexCoord")
    n = nb.node("ShaderNodeTexNoise", inputs={"Scale": 60.0, "Detail": 6.0})
    nb.link(tc.outputs["Object"], n.inputs[0])
    col = nb.mix(n.outputs[0], (0.03, 0.026, 0.024, 1), (0.10, 0.085, 0.07, 1))
    nb.link(col, bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = 0.32
    bs.inputs["Coat Weight"].default_value = 0.2
    return m


def mat_skin(ob):
    """Piel hiperrealista: escama por regiones con desplazamiento real, moteado, polvo,
    zonas húmedas, queratina estriada, iridiscencia sutil, SSS y brasa."""
    m = bpy.data.materials.new("VesperSkin")
    m.displacement_method = "BUMP"
    nb = NB(m)
    out = nb.node("ShaderNodeOutputMaterial")
    bs = nb.node("ShaderNodeBsdfPrincipled")
    nb.link(bs.outputs[0], out.inputs[0])
    gm = generated_meters(nb, ob)
    sep = lambda sock: (lambda n: (nb.link(sock, n.inputs[0]), n)[1])(nb.node("ShaderNodeSeparateColor")).outputs
    # --- mapas de escama ---------------------------------------------------
    gran = sep(box_tex(nb, gm, img("granular_data.png", "Non-Color"), 0.26).outputs[0])
    med = sep(box_tex(nb, gm, img("scales_data.png", "Non-Color"), 0.30).outputs[0])
    fine = sep(box_tex(nb, gm, img("granular_data.png", "Non-Color"), 0.09).outputs[0])
    mk = nb.node("ShaderNodeMapping", vector_type="POINT"); mk.inputs["Scale"].default_value = (1 / 0.36, 1 / 0.30, 1)
    nb.link(nb.uv("bodym"), mk.inputs[0])
    kt = nb.node("ShaderNodeTexImage", image=img("keeled_data.png", "Non-Color"), interpolation="Cubic")
    nb.link(mk.outputs[0], kt.inputs[0])
    keel = sep(kt.outputs[0])
    masks = nb.attr("masks")
    ms = sep(masks.outputs["Color"])
    ker, tube, mouth = ms[0], ms[1], ms[2]
    ao = masks.outputs["Alpha"]
    kd = nb.sep(nb.uv("kdata")); kgrad, cav = kd[0], kd[1]
    bm = nb.node("ShaderNodeTexImage", image=img("bodymap.png", "Non-Color"), interpolation="Linear", extension="EXTEND")
    nb.link(nb.uv("bodyuv"), bm.inputs[0])
    bms = sep(bm.outputs[0])
    glowmask = nb.math("MULTIPLY", bms[0], tube)
    scute = nb.math("MULTIPLY", bms[1], tube)
    belly = nb.math("MULTIPLY", bms[2], tube)
    bu = nb.sep(nb.uv("bodyuv"))
    # región: escama aquillada en lomo/cuello/cola, granular en cabeza y patas, lisa-ventral en el vientre
    wk = nb.math("MULTIPLY", nb.math("POWER", tube, 2.0), nb.math("SUBTRACT", 1.0, belly), clamp=True)
    hb = nb.mix(wk, gran[0], keel[0])
    hb = nb.mix(belly, hb, med[0])
    hb = nb.math("ADD", hb, nb.math("MULTIPLY", fine[0], 0.25))
    height = nb.math("ADD", nb.math("MULTIPLY", hb, nb.math("SUBTRACT", 1.0, ker)), nb.math("MULTIPLY", scute, 1.2))
    # estrías de crecimiento de la queratina (cuernos, garras, púas)
    kstr = nb.node("ShaderNodeTexWave", wave_type="RINGS", rings_direction="SPHERICAL", inputs={"Scale": 60.0, "Distortion": 3.0, "Detail": 3.0})
    nb.link(gm, kstr.inputs["Vector"])
    height = nb.math("ADD", height, nb.math("MULTIPLY", ker, nb.math("MULTIPLY", kstr.outputs[1], 0.5)))
    rnd = nb.mix(wk, gran[1], keel[1]); rnd = nb.mix(belly, rnd, med[1])
    crev = nb.mix(wk, gran[2], keel[2]); crev = nb.mix(belly, crev, med[2])
    # --- ruido de gran escala (moteado y matiz) -------------------------------
    n1 = nb.node("ShaderNodeTexNoise", inputs={"Scale": 1.6, "Detail": 6.0, "Roughness": 0.6})
    n2 = nb.node("ShaderNodeTexNoise", inputs={"Scale": 7.0, "Detail": 3.0, "Roughness": 0.5})
    nb.link(gm, n1.inputs["Vector"]); nb.link(gm, n2.inputs["Vector"])
    vr = nb.node("ShaderNodeMapRange", inputs={"From Min": 0.2, "From Max": 0.7}); nb.link(bu[1], vr.inputs[0])
    col = nb.mix(vr.outputs[0], (0.0075, 0.0085, 0.011, 1), (0.015, 0.016, 0.021, 1))
    col = nb.mix(nb.math("MULTIPLY", n1.outputs[0], 0.7), col, (0.011, 0.015, 0.015, 1))        # matiz verdoso
    col = nb.mix(nb.math("MULTIPLY", n2.outputs[0], 0.45), col, (0.018, 0.013, 0.010, 1))       # matiz bronce
    mott = nb.node("ShaderNodeMapRange", inputs={"From Min": 0.45, "From Max": 0.62, "To Min": 1.0, "To Max": 0.62})
    nb.link(n1.outputs[0], mott.inputs[0])                                                    # manchas dorsales
    mm = nb.node("ShaderNodeCombineColor"); [nb.link(mott.outputs[0], mm.inputs[i]) for i in range(3)]
    col = nb.mix(nb.math("SUBTRACT", 1.0, vr.outputs[0]), col, nb.mix(1.0, col, mm.outputs[0], "MULTIPLY"))
    col = nb.mix(belly, col, (0.050, 0.041, 0.034, 1))
    # escama a escama: variación, puntas pulidas algo más claras, juntas oscuras
    var = nb.math("MULTIPLY_ADD", rnd, 0.36, 0.82)
    tip = nb.math("MULTIPLY_ADD", hb, 0.45, 0.80)
    k1 = nb.math("MULTIPLY", var, tip)
    k2 = nb.math("MULTIPLY_ADD", crev, -0.55, 1.0)
    kk = nb.math("MULTIPLY", k1, k2)
    kc = nb.node("ShaderNodeCombineColor"); [nb.link(kk, kc.inputs[i]) for i in range(3)]
    col = nb.mix(1.0, col, kc.outputs[0], "MULTIPLY")
    # polvo en las juntas de las zonas bajas (patas, vientre)
    zsep = nb.sep(gm)
    low = nb.node("ShaderNodeMapRange", inputs={"From Min": 0.55, "From Max": 0.05}); nb.link(zsep[2], low.inputs[0])
    dust = nb.math("MULTIPLY", nb.math("MULTIPLY", crev, low.outputs[0]), nb.math("MULTIPLY_ADD", n2.outputs[0], 0.8, 0.2), clamp=True)
    col = nb.mix(nb.math("MULTIPLY", dust, 0.8), col, (0.070, 0.062, 0.052, 1))
    # queratina: base oscura -> punta hueso, con estrías longitudinales
    strn = nb.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Z", inputs={"Scale": 40.0, "Distortion": 6.0, "Detail": 4.0})
    nb.link(gm, strn.inputs["Vector"])
    kcol = nb.mix(nb.math("POWER", kgrad, 2.2), (0.014, 0.012, 0.011, 1), (0.085, 0.070, 0.050, 1))
    kcol = nb.mix(nb.math("MULTIPLY", strn.outputs[1], 0.35), kcol, (0.010, 0.009, 0.008, 1))
    col = nb.mix(ker, col, kcol)
    col = nb.mix(mouth, col, (0.16, 0.028, 0.032, 1))
    col = nb.mix(cav, col, (0.003, 0.002, 0.002, 1))
    aop = nb.math("POWER", ao, 0.9)
    aoc = nb.node("ShaderNodeCombineColor"); [nb.link(aop, aoc.inputs[i]) for i in range(3)]
    col = nb.mix(1.0, col, aoc.outputs[0], "MULTIPLY")
    nb.link(col, bs.inputs["Base Color"])
    # --- rugosidad --------------------------------------------------------------
    wet = nb.math("MAXIMUM", nb.math("MULTIPLY", mouth, 1.0), cav)
    r = nb.math("MULTIPLY_ADD", crev, 0.24, 0.56)
    r = nb.math("SUBTRACT", r, nb.math("MULTIPLY", hb, 0.14))
    r = nb.math("ADD", r, nb.math("MULTIPLY", rnd, 0.08))
    r = nb.math("ADD", r, nb.math("MULTIPLY", dust, 0.25))
    r = nb.mix(ker, r, nb.math("MULTIPLY_ADD", strn.outputs[1], 0.12, 0.28))
    r = nb.mix(wet, r, 0.16)
    nb.link(r, bs.inputs["Roughness"])
    nb.link(nb.math("MULTIPLY", wet, 0.6), bs.inputs["Coat Weight"])
    bs.inputs["Coat Roughness"].default_value = 0.08
    # --- relieve fino (bump) + desplazamiento real -----------------------------
    bump = nb.node("ShaderNodeBump", inputs={"Strength": 0.35, "Distance": 0.0012})
    nb.link(nb.math("MULTIPLY", fine[0], 0.6), bump.inputs["Height"])
    nb.link(bump.outputs[0], bs.inputs["Normal"])
    disp = nb.node("ShaderNodeDisplacement", inputs={"Midlevel": 0.45, "Scale": 0.0024})
    nb.link(height, disp.inputs["Height"])
    nb.link(disp.outputs[0], out.inputs["Displacement"])
    # --- iridiscencia sutil (sólo cuerpo), SSS, especular -------------------
    tf = nb.math("MULTIPLY", tube, nb.math("MULTIPLY_ADD", n2.outputs[0], 160.0, 200.0))
    nb.link(tf, bs.inputs["Thin Film Thickness"])
    bs.inputs["Thin Film IOR"].default_value = 1.36
    bs.inputs["Subsurface Weight"].default_value = 0.05
    bs.inputs["Subsurface Radius"].default_value = (1.0, 0.28, 0.12)
    bs.inputs["Subsurface Scale"].default_value = 0.01
    bs.inputs["Specular IOR Level"].default_value = 0.38
    # --- brasa --------------------------------------------------------------
    glow = nb.drv_value("glow", RD.NEUTRAL["glow"])
    throat = nb.drv_value("throat", 0.0)
    es = nb.math("MULTIPLY", nb.math("ADD", nb.math("MULTIPLY", glowmask, glow),
                                     nb.math("MULTIPLY", nb.math("MULTIPLY", mouth, throat), 0.0012)), 7.0)
    nb.link(es, bs.inputs["Emission Strength"])
    bs.inputs["Emission Color"].default_value = GLOW_COL
    return m


MATS = {
    "Skin": mat_skin(body),
    "Lid": mat_lid(),
    "Eye": mat_eye(),
    "Cornea": mat_simple("VesperCornea", (1, 1, 1, 1), 0.0, trans=1.0, ior=1.376, coat=0.0),
    "Teeth": mat_simple("VesperTeeth", (0.62, 0.57, 0.47, 1), 0.28, sss=0.15, coat=0.3),
    "Mouth": mat_simple("VesperMouth", (0.24, 0.045, 0.05, 1), 0.22, sss=0.35, coat=0.5),
    "Keratin": mat_keratin(),
    "Wing": mat_membrane("VesperWing"),
    "Membrane": mat_membrane("VesperFrill", kind="frill"),
}
body.data.materials.append(MATS["Skin"])
for ob in part_obs:
    key = ob["mat"]
    if ob.name.startswith("Lid"):
        key = "Lid"
    ob.data.materials.append(MATS[key])
log("materiales listos")

# ===========================================================================
# 5. Skinning (modificadores Armature) y drivers de shape keys
# ===========================================================================
def skin(ob):
    ob.parent = arm
    mod = ob.modifiers.new("Armature", "ARMATURE"); mod.object = arm
    mod.use_deform_preserve_volume = False


for ob in [body] + part_obs:
    skin(ob)
# microdesplazamiento: subdivisión adaptativa en render (Cycles) para que la escama sea geometría real
# NOTA: el desplazamiento real con subdivisión adaptativa agota los 15 GB de este entorno con
# una malla de 600k caras; se deja preparado pero desactivado y se usa relieve (bump) desde la
# misma altura. Con más memoria: activar el modificador y poner displacement_method = "BOTH".
_sub = body.modifiers.new("Microdesplazamiento", "SUBSURF")
_sub.levels = 0; _sub.render_levels = 1; _sub.subdivision_type = "SIMPLE"
_sub.show_render = False; _sub.show_viewport = False
body.cycles.use_adaptive_subdivision = False
SK_DRIVERS = {"Breathe": "breath", "ThroatPuff": "throat", "Snarl": "snarl", "NostrilFlare": "nostril", "Smile": "smile"}
for kname, prop in SK_DRIVERS.items():
    kb = body.data.shape_keys.key_blocks[kname]
    fc = kb.driver_add("value"); dv = fc.driver; dv.type = "AVERAGE"
    var = dv.variables.new(); var.type = "SINGLE_PROP"; var.targets[0].id = arm; var.targets[0].data_path = f'["{prop}"]'
# la membrana y las piezas finas no proyectan sombras demasiado duras
for ob in part_obs:
    if ob.name.startswith("Cornea"):
        ob.visible_shadow = False

# ===========================================================================
# 6. Rig expresivo: evaluación de parámetros, plegado de alas, rig.json
# ===========================================================================
PARAMS = RD.build_params()
REST = {b.name: b.matrix_local.to_3x3() for b in arm_data.bones}


def mirror_axis(name, ax):
    if name.endswith(".R"):
        return (ax[0], -ax[1], -ax[2])
    return ax


def compute_wing_fold():
    """Pliega el ala apuntando cada hueso a una dirección objetivo (en cadena)."""
    targets_L = {
        "humerus.L": (0.42, 0.86, 0.30),
        "wforearm.L": (-0.06, -0.98, 0.17),
        "f1a.L": (0.07, 0.99, -0.12), "f1b.L": (0.04, 0.97, -0.24),
        "f2a.L": (0.10, 0.97, -0.20), "f2b.L": (0.06, 0.92, -0.38),
        "f3a.L": (0.13, 0.93, -0.33), "f3b.L": (0.08, 0.83, -0.55),
        "f4a.L": (0.15, 0.84, -0.50), "f4b.L": (0.08, 0.66, -0.74),
    }
    fold = {}
    for sx, s in (("L", 1), ("R", -1)):
        for pb in arm.pose.bones:
            pb.rotation_quaternion = Quaternion()
        bpy.context.view_layer.update()
        for name_L, tdir in targets_L.items():
            name = name_L[:-1] + sx
            pb = arm.pose.bones[name]
            bpy.context.view_layer.update()
            M = pb.matrix.copy()
            cur = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
            tgt = Vector((tdir[0] * s, tdir[1], tdir[2])).normalized()
            q = cur.rotation_difference(tgt)
            R = q.to_matrix() @ M.to_3x3()
            newM = Matrix.Translation(M.translation) @ R.to_4x4()
            pb.matrix = newM
            bpy.context.view_layer.update()
        for name_L in targets_L:
            name = name_L[:-1] + sx
            ql = arm.pose.bones[name].rotation_quaternion.copy()
            axis_l, ang = ql.to_axis_angle()
            axis_a = REST[name] @ axis_l
            fold[name] = [list(axis_a), ang]
    for pb in arm.pose.bones:
        pb.rotation_quaternion = Quaternion()
    return fold


WING_FOLD = compute_wing_fold()
log("plegado de alas calculado")


def pose_params(vals, extra_rot=None):
    """Aplica un diccionario de parámetros al rig (rotvec sumados por hueso)."""
    rv = {}; loc = {}
    for p, v in vals.items():
        for b, ax, g, t in PARAMS.get(p, []):
            if b not in arm.pose.bones:
                continue
            ax = mirror_axis(b, ax)
            vec = Vector(ax) * (g * v)
            if t == "loc":
                loc[b] = loc.get(b, Vector()) + vec
            else:
                rv[b] = rv.get(b, Vector()) + vec
    if extra_rot:
        for b, vec in extra_rot.items():
            rv[b] = rv.get(b, Vector()) + Vector(vec)
    wo = vals.get("wing_open", 0.0)
    for pb in arm.pose.bones:
        q = Quaternion()
        if pb.name in rv:
            v = REST[pb.name].inverted() @ rv[pb.name]
            if v.length > 1e-9:
                q = Quaternion(v.normalized(), v.length)
        if pb.name in WING_FOLD:
            ax, ang = WING_FOLD[pb.name]
            qf = Quaternion((REST[pb.name].inverted() @ Vector(ax)).normalized(), ang * (1 - wo))
            q = qf @ q
        pb.rotation_quaternion = q
        pb.location = REST[pb.name].inverted() @ loc[pb.name] if pb.name in loc else Vector()
    for k in RD.EXTRA:
        if k in vals:
            arm[k] = float(vals[k])


rig_json = dict(
    params=PARAMS, extra=RD.EXTRA, neutral=RD.NEUTRAL, emotions=RD.EMOTIONS, wingFold=WING_FOLD,
    lidAxis=RD.lid_axis(), headUp=list(map(float, A.HEAD_U)),
    eyes={sx: dict(center=list(map(float, A.eye_center(s))), axis=list(map(float, A.eye_axis(s))))
          for sx, s in (("L", 1), ("R", -1))},
    ik={"hand.L": ["upperarm.L", "forearm.L"], "hand.R": ["upperarm.R", "forearm.R"],
        "foot.L": ["thigh.L", "shin.L"], "foot.R": ["thigh.R", "shin.R"]},
    regions={},
    bones={n: dict(head=list(map(float, h)), tail=list(map(float, t)), parent=p) for n, (h, t, p, d) in BONES.items()},
    glowColor=list(GLOW_COL[:3]),
)
with open(os.path.join(OUT_WEB, "rig.json"), "w") as fh:
    json.dump(rig_json, fh, indent=1)
log("rig.json escrito")

# ===========================================================================
# 7. Acciones (emociones + reposo)
# ===========================================================================
def key_pose(frame):
    for pb in arm.pose.bones:
        pb.keyframe_insert("rotation_quaternion", frame=frame)
        pb.keyframe_insert("location", frame=frame)
    for k in RD.EXTRA:
        arm.keyframe_insert(f'["{k}"]', frame=frame)


def idle_overlay(t, amp=1.0, breath_rate=0.28, tail_amp=1.0):
    """Movimiento secundario: respiración, cola, cabeza."""
    ph = 2 * math.pi * breath_rate * t
    br = 0.5 + 0.5 * math.sin(ph)
    d = {}
    d["breath"] = br * amp
    rot = {}
    for i in range(A.N_TAIL):
        a = 0.035 * tail_amp * math.sin(2 * math.pi * 0.22 * t - i * 0.42) * (0.4 + i / A.N_TAIL)
        rot[f"tail{i+1:02d}"] = (0, 0, a)
    rot["chest"] = (0.012 * amp * math.sin(ph), 0, 0)
    rot["head"] = (0.01 * math.sin(2 * math.pi * 0.13 * t), 0, 0.015 * math.sin(2 * math.pi * 0.09 * t))
    return d, rot


def make_action(name, target, frames=150, blink_at=(70,)):
    act = bpy.data.actions.new(name); act.use_fake_user = True
    arm.animation_data_create(); arm.animation_data.action = act
    neutral = dict(RD.NEUTRAL)
    for f in range(0, frames + 1, 3):
        t = f / scene.render.fps
        w = min(1.0, f / 18.0); w = w * w * (3 - 2 * w)
        vals = {k: neutral.get(k, 0) * (1 - w) + target.get(k, neutral.get(k, 0)) * w for k in neutral}
        dv, rot = idle_overlay(t, tail_amp=1.0 + 2.0 * max(0, target.get("tail_raise", 0)))
        for k, v in dv.items():
            vals[k] = v
        for b in blink_at:
            g = max(0.0, 1 - abs(f - b) / 5.0)
            vals["lid_up"] = vals["lid_up"] + (1.0 - vals["lid_up"]) * g
            vals["lid_lo"] = vals["lid_lo"] + (0.9 - vals["lid_lo"]) * g
        pose_params(vals, rot)
        key_pose(f)
    act.frame_range = (0, frames)
    return act


ACTIONS = {}
ACTIONS["Reposo"] = make_action("Reposo", {}, frames=180, blink_at=(60, 150))
for emo, target in RD.EMOTIONS.items():
    if emo == "calma":
        continue
    ACTIONS[emo] = make_action(f"Emocion_{emo}", target)
arm.animation_data.action = ACTIONS["Reposo"]
scene.frame_start, scene.frame_end = 0, 180
log(f"{len(ACTIONS)} acciones")

# ===========================================================================
# 8. Estudio: luces, suelo, mundo, cámaras
# ===========================================================================
def area(name, loc, target, energy, size, color, shape="RECTANGLE", size_y=None):
    L = bpy.data.lights.new(name, "AREA"); L.energy = energy; L.color = color
    L.shape = shape; L.size = size
    if size_y:
        L.size_y = size_y
    o = link(bpy.data.objects.new(name, L), C_ENV); o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


area("Key", (3.2, -4.2, 4.2), (0, -0.6, 1.2), 750, 2.6, (1.0, 0.90, 0.80))
area("Fill", (-4.5, -3.5, 2.2), (0, -0.4, 1.1), 110, 4.0, (0.75, 0.82, 1.0))
area("RimL", (-3.2, 3.0, 3.2), (0, -0.6, 1.3), 1300, 0.5, (0.55, 0.70, 1.0), "RECTANGLE", 4.0)
area("RimR", (3.6, 2.4, 2.8), (0, -0.4, 1.2), 900, 0.5, (0.65, 0.78, 1.0), "RECTANGLE", 4.0)
area("Top", (0, 0.4, 6.0), (0, 0.4, 0), 120, 5.0, (0.9, 0.92, 1.0))
# suelo
bpy.ops.mesh.primitive_circle_add(vertices=128, radius=14, fill_type="NGON")
floor = bpy.context.active_object; floor.name = "Suelo"
for c in floor.users_collection:
    c.objects.unlink(floor)
C_ENV.objects.link(floor)
fm = bpy.data.materials.new("Suelo"); nb = NB(fm)
out = nb.node("ShaderNodeOutputMaterial"); bs = nb.node("ShaderNodeBsdfPrincipled"); nb.link(bs.outputs[0], out.inputs[0])
tc = nb.node("ShaderNodeTexCoord"); gr = nb.node("ShaderNodeTexGradient", gradient_type="SPHERICAL")
mp = nb.node("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (0.11, 0.11, 0.11); mp.inputs["Location"].default_value = (0, -0.05, 0)
nb.link(tc.outputs["Object"], mp.inputs[0]); nb.link(mp.outputs[0], gr.inputs[0])
nb.link(nb.mix(gr.outputs[0], (0.0, 0.0, 0.0, 1), (0.016, 0.017, 0.020, 1)), bs.inputs["Base Color"])
bs.inputs["Roughness"].default_value = 0.42; bs.inputs["Specular IOR Level"].default_value = 0.35
floor.data.materials.append(fm)
# mundo
world = bpy.data.worlds.new("Noche"); scene.world = world; world.use_nodes = True
wn = world.node_tree.nodes; wl = world.node_tree.links
bg = wn["Background"]; bg.inputs[0].default_value = (0.006, 0.007, 0.011, 1); bg.inputs[1].default_value = 1.0
# HDRI de estudio (Poly Haven, CC0) sólo para iluminación y reflejos; la cámara ve el fondo oscuro
hdr_path = os.path.join(ROOT, "assets", "hdri", "studio_2k.hdr")
if os.path.exists(hdr_path):
    env = wn.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(hdr_path)
    mapw = wn.new("ShaderNodeMapping"); tcw = wn.new("ShaderNodeTexCoord")
    mapw.inputs["Rotation"].default_value = (0, 0, math.radians(120))
    wl.new(tcw.outputs["Generated"], mapw.inputs[0]); wl.new(mapw.outputs[0], env.inputs[0])
    bg2 = wn.new("ShaderNodeBackground"); bg2.inputs[1].default_value = 0.22
    wl.new(env.outputs[0], bg2.inputs[0])
    lp = wn.new("ShaderNodeLightPath"); mixw = wn.new("ShaderNodeMixShader")
    wl.new(lp.outputs["Is Camera Ray"], mixw.inputs[0])
    wl.new(bg2.outputs[0], mixw.inputs[1]); wl.new(bg.outputs[0], mixw.inputs[2])
    wl.new(mixw.outputs[0], wn["World Output"].inputs[0])

CAMS = {
    "Cam_Heroe": ((4.6, -5.6, 2.25), (0.0, -0.35, 1.05), 50, None),
    "Cam_Frontal": ((0.0, -7.2, 1.55), (0.0, -0.4, 1.05), 50, None),
    "Cam_Perfil": ((8.6, 0.55, 1.3), (0.0, 0.75, 0.95), 42, None),
    "Cam_Posterior": ((-3.4, 7.6, 2.8), (0.0, 0.3, 1.1), 45, None),
    "Cam_Cabeza": ((1.25, -2.85, 1.98), (0.0, -1.42, 1.74), 85, (-1.42, 1.74)),
    "Cam_Ojo": ((0.62, -1.84, 1.86), (0.14, -1.37, 1.80), 100, None),
    "Cam_Ala": ((2.6, -1.6, 3.6), (1.0, 0.1, 1.5), 40, None),
    "Cam_Cola": ((1.9, 4.6, 1.2), (0.0, 3.0, 0.75), 50, None),
}
for name, (loc, tgt, lens, _) in CAMS.items():
    cam = bpy.data.cameras.new(name); cam.lens = lens
    o = link(bpy.data.objects.new(name, cam), C_ENV); o.location = loc
    o.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    cam.dof.use_dof = lens >= 80
    cam.dof.focus_distance = (Vector(tgt) - Vector(loc)).length
    cam.dof.aperture_fstop = 2.8
scene.camera = bpy.data.objects["Cam_Heroe"]

# render
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 192
scene.cycles.feature_set = "EXPERIMENTAL"
scene.cycles.dicing_rate = 1.0
scene.cycles.offscreen_dicing_scale = 30.0
scene.cycles.max_subdivisions = 3
scene.cycles.dicing_rate = 1.5
scene.cycles.use_denoising = True
scene.cycles.denoiser = "OPENIMAGEDENOISE"
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.render.film_transparent = False
C_WEB.hide_render = True
bpy.context.view_layer.layer_collection.children["Vesper_web"].exclude = True

# ===========================================================================
# 9. Exportación web (GLB)
# ===========================================================================
if DO_WEB:
    bpy.context.view_layer.layer_collection.children["Vesper_web"].exclude = False
    web_body = build_body("VesperBody_web", WEB_FACES, C_WEB, smooth_iters=1)
    web_body.data.materials.append(MATS["Skin"])
    skin(web_body)
    # proxy de baja resolución para detección de toques (raycast en la app)
    pick_body = build_body("VesperBody_pick", 9000, C_WEB, smooth_iters=1)
    pick_body.shape_key_clear()
    skin(pick_body)
    web_parts = []
    for ob in part_obs:
        o2 = ob.copy(); o2.data = ob.data.copy(); o2.name = ob.name + "_web"
        C_WEB.objects.link(o2)
        o2.modifiers.clear(); skin(o2)
        web_parts.append(o2)
    # ---------------------------------------------------------------------
    # Horneado: del modelo de alta resolución (con su material completo) al web
    # ---------------------------------------------------------------------
    BAKE_DIR = os.path.join(ROOT, "assets", "bake"); os.makedirs(BAKE_DIR, exist_ok=True)
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_quaternion = Quaternion(); pb.location = Vector()
        for c in pb.constraints:
            c.mute = True
    for k in RD.EXTRA:
        arm[k] = 0.0
    bpy.context.view_layer.update()
    me = web_body.data
    me.uv_layers.new(name="bake")
    me.uv_layers.active = me.uv_layers["bake"]
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = web_body; web_body.select_set(True)
    # desplegar sobre una copia muy suavizada (misma topología): islas grandes y limpias
    _co = np.zeros(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", _co)
    _sk = web_body.data.shape_keys
    web_body.active_shape_key_index = 0
    bm_ = bmesh.new(); bm_.from_mesh(me)
    for _ in range(40):
        bmesh.ops.smooth_vert(bm_, verts=bm_.verts, factor=0.6, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    _sm = np.array([v.co[:] for v in bm_.verts], np.float32).ravel(); bm_.free()
    me.vertices.foreach_set("co", _sm); me.update()
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(70), island_margin=0.003, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin=0.003)
    bpy.ops.object.mode_set(mode="OBJECT")
    me.vertices.foreach_set("co", _co); me.update()
    if _sk:
        _sk.key_blocks[0].data.foreach_set("co", _co)
    tgt = bpy.data.materials.new("BakeTarget"); tgt.use_nodes = True
    tnode = tgt.node_tree.nodes.new("ShaderNodeTexImage")
    tgt.node_tree.nodes.active = tnode
    web_body.data.materials[0] = tgt
    skin_mat = MATS["Skin"]; skin_mat.displacement_method = "BUMP"
    body.modifiers["Microdesplazamiento"].show_render = False
    sc_ = bpy.context.scene
    C_WEB.hide_render = False
    sc_.render.bake.use_selected_to_active = True
    sc_.render.bake.cage_extrusion = 0.015
    sc_.render.bake.max_ray_distance = 0.04
    sc_.render.bake.margin = 16
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True); web_body.select_set(True); bpy.context.view_layer.objects.active = web_body

    def do_bake(name, size, kind, samples=1, **kw):
        im = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
        im.colorspace_settings.name = "sRGB" if kind == "DIFFUSE" else "Non-Color"
        tnode.image = im
        sc_.cycles.samples = samples
        t0 = time.time()
        bpy.ops.object.bake(type=kind, **kw)
        im.filepath_raw = os.path.join(BAKE_DIR, name + ".png"); im.file_format = "PNG"; im.save()
        log(f"horneado {name} ({kind}, {size}px) en {time.time()-t0:.0f}s")

    do_bake("bake_normal", 4096, "NORMAL", 12, normal_space="TANGENT")
    do_bake("bake_color", 2048, "DIFFUSE", 6, pass_filter={"COLOR"})
    do_bake("bake_rough", 2048, "ROUGHNESS", 6)
    sc_.cycles.samples = 192
    C_WEB.hide_render = True
    skin_mat.displacement_method = "BUMP"
    web_body.data.materials[0] = MATS["Skin"]
    for nm in ("kdata", "bodym"):
        me.uv_layers.remove(me.uv_layers[nm])
    me.uv_layers.active = me.uv_layers["bodyuv"]
    # pose de reposo pura para exportar
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_quaternion = Quaternion(); pb.location = Vector()
    # quitar drivers de shape keys en la copia web (la app los gobierna)
    if web_body.data.shape_keys.animation_data:
        web_body.data.shape_keys.animation_data_clear()
    for kb in web_body.data.shape_keys.key_blocks:
        kb.value = 0.0
    bpy.ops.object.select_all(action="DESELECT")
    for o in [arm, web_body, pick_body] + web_parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    # desactivar restricciones IK durante la exportación de la pose de reposo
    for pb in arm.pose.bones:
        for c in pb.constraints:
            c.mute = True
    glb = os.path.join(OUT_WEB, "vesper.glb")
    bpy.ops.export_scene.gltf(
        filepath=glb, export_format="GLB", use_selection=True,
        export_apply=False, export_skins=True, export_morph=True, export_morph_normal=True,
        export_animations=False, export_texcoords=True, export_normals=True,
        export_vertex_color="ACTIVE", export_all_vertex_colors=False,
        export_def_bones=False, export_yup=True, export_materials="PLACEHOLDER",
        export_attributes=False,
    )
    for pb in arm.pose.bones:
        for c in pb.constraints:
            c.mute = False
    log(f"GLB exportado: {os.path.getsize(glb)/1e6:.1f} MB")
    arm.animation_data.action = ACTIONS["Reposo"]
    bpy.context.view_layer.layer_collection.children["Vesper_web"].exclude = True

# eliminar la malla bruta (pesada) del .blend
bpy.data.objects.remove(raw_ob)
bpy.ops.file.pack_all() if False else None
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True, relative_remap=True)
log("guardado", OUT_BLEND)
