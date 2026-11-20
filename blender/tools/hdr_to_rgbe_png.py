"""Convierte un .hdr a PNG RGBA con codificación RGBE (sin pérdida de rango dinámico) para la web.
blender -b -P blender/tools/hdr_to_rgbe_png.py -- in.hdr out.png"""
import sys, bpy, numpy as np
a = sys.argv[sys.argv.index("--") + 1:]
im = bpy.data.images.load(a[0]); w, h = im.size
px = np.array(im.pixels[:], np.float32).reshape(h, w, 4)[..., :3]
m = px.max(-1)
e = np.where(m > 1e-32, np.ceil(np.log2(np.maximum(m, 1e-32))), -128).astype(np.int32)
sc = np.where(m > 1e-32, 256.0 / np.exp2(e.astype(np.float32)), 0)
rgb = np.clip(np.floor(px * sc[..., None]), 0, 255)
out = np.concatenate([rgb, np.clip(e + 128, 0, 255)[..., None]], -1) / 255.0
o = bpy.data.images.new("rgbe", w, h, alpha=True, float_buffer=False)
o.colorspace_settings.name = "Non-Color"; o.alpha_mode = "STRAIGHT"
o.pixels = out.astype(np.float32).ravel()
o.filepath_raw = a[1]; o.file_format = "PNG"; o.save()
print("rgbe", w, h)
