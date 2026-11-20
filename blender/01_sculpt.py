"""
Paso 1 — Escultura SDF del cuerpo de Vesper (Python del sistema).

    python3 blender/01_sculpt.py [resolucion_m]

Genera build/body_raw.npz con vértices y caras (marching cubes por bloques).
Resolución por defecto: 0.0025 m (2,5 mm).
"""
import os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
from sdf import mesh_from_prims  # noqa
import anatomy  # noqa

h = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0025
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "build", "body_raw.npz")
os.makedirs(os.path.dirname(out), exist_ok=True)

t = time.time()
prims = anatomy.build_prims()
print(f"{len(prims)} primitivas")
lo, hi = anatomy.BOUNDS
V, F = mesh_from_prims(prims, lo, hi, h, block=112 if h < 0.004 else 80, coarse=max(0.015, h * 4))
print(f"malla: {len(V)} vértices, {len(F)} caras  ({time.time()-t:.1f}s)")
np.savez_compressed(out, V=V.astype(np.float32), F=F.astype(np.int32), h=h)
print("guardado", out)
