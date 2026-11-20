#!/usr/bin/env bash
# Compila la app y copia el sitio estático a la raíz del repositorio (GitHub Pages: rama main, carpeta /).
set -e
cd "$(dirname "$0")"
npx vite build
cd ..
rm -rf app textures index.html vesper.glb rig.json
cp -r web/dist/app web/dist/textures web/dist/index.html web/dist/vesper.glb web/dist/rig.json .
touch .nojekyll
echo "Sitio listo en la raíz: index.html, app/, textures/, vesper.glb, rig.json"
