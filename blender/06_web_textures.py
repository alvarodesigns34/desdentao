"""Paso 6 — Convierte los mapas horneados (assets/bake) a WebP para la app (web/public/textures)."""
import os
import numpy as np
from PIL import Image
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
S, D = os.path.join(R, "assets", "bake"), os.path.join(R, "web", "public", "textures")
os.makedirs(D, exist_ok=True)
Image.open(os.path.join(S, "bake_normal.png")).convert("RGB").save(os.path.join(D, "bake_normal.webp"), quality=90)
Image.open(os.path.join(S, "bake_color.png")).convert("RGB").save(os.path.join(D, "bake_color.webp"), quality=92)
ro = np.asarray(Image.open(os.path.join(S, "bake_rough.png")).convert("L")); ao = np.full_like(ro, 255)
Image.fromarray(np.stack([ao, ro, np.zeros_like(ao)], -1)).save(os.path.join(D, "bake_orm.webp"), quality=92)
for n in ("granular_data", "keeled_data"):
    Image.open(os.path.join(R, "assets", "textures", n + ".png")).convert("RGB").resize((1024, 1024)).save(os.path.join(D, n + ".webp"), quality=92)
print("texturas web listas:", sorted(os.listdir(D)))
