#!/usr/bin/env bash
# Renders cinematográficos finales (Cycles CPU). Uso: bash blender/05_render_all.sh [muestras]
set -e
cd "$(dirname "$0")/.."
S=${1:-128}
OUT=renders
mkdir -p $OUT/angulos $OUT/expresiones
blender -b output/vesper.blend -P blender/04_render.py -- \
  --cams Cam_Heroe,Cam_Frontal,Cam_Perfil,Cam_Posterior,Cam_Cabeza,Cam_Ojo,Cam_Ala,Cam_Cola \
  --action Reposo --frame 40 --samples $S --res 1920x1080 --out $OUT/angulos
for e in curiosidad alegria desconfianza enfado ternura sorpresa somnolencia juego; do
  blender -b output/vesper.blend -P blender/04_render.py -- --cams Cam_Cabeza --action $e --frame 75 \
    --samples $S --res 1280x720 --out $OUT/expresiones --tag $e --track
done
# alas extendidas (pose de reposo del rig)
blender -b output/vesper.blend -P blender/04_render.py -- --cams Cam_Heroe,Cam_Frontal --rest \
  --samples $S --res 1920x1080 --out $OUT/angulos --tag alas_extendidas
