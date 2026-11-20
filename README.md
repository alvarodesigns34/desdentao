# Vesper — dragón nocturno 3D, animado e interactivo

**Vesper** es un dragón de diseño **original**, creado para este proyecto. Ha seguido el mismo
nivel de exigencia que el encargo inicial, pero con una identidad visual propia:

- cabeza alargada de reptil con arcos superciliares marcados;
- dos pares de cuernos de queratina barridos hacia atrás (oscuros en la base, color hueso en la punta);
- gorgueras membranosas en las mejillas que se despliegan según el ánimo;
- ojos ámbar con pupila hendida que se dilata y se contrae;
- piel escamosa pizarra-carbón con iridiscencia sutil y placas ventrales más cálidas;
- vetas y fotóforos de **brasa** en los flancos, que laten con la respiración y se encienden con la emoción;
- alas de cuatro dedos con membranas translúcidas venosas;
- abanico de púas al final de la cola.

```
blender/            pipeline de producción (Python + bpy)
  lib/sdf.py          biblioteca SDF vectorizada (escultura, pesos, máscaras, AO)
  lib/anatomy.py      ÚNICA fuente de verdad: esqueleto y primitivas anatómicas
  lib/parts.py        ojos, párpados, dientes, lengua, gorgueras, abanico, membranas alares
  lib/bodydata.py     pesos de skinning, máscaras, coordenadas corporales, AO, shape keys
  lib/rigdef.py       rig expresivo compartido (parámetros, 8 emociones)
  01_sculpt.py        escultura SDF -> marching cubes por bloques (build/body_raw.npz)
  02_textures.py      texturas procedurales (escamas, iris, venas, mapa corporal)
  03_build.py         escena completa en Blender + exportación web (GLB + rig.json)
  04_render.py        renders de verificación / cinematográficos
  05_render_all.sh    tanda completa de renders finales
assets/textures/    texturas a resolución completa (usadas por el .blend)
output/vesper.blend escena editable
renders/            renders cinematográficos (Cycles)
web/                aplicación interactiva (three.js + Vite)
```

---

## 1. Abrir la experiencia interactiva

Requisitos: Node 18 o superior.

```bash
cd web
npm install
npm run dev          # http://localhost:5173  (accesible también desde la red local: iPad / móvil)
# o versión de producción:
npm run build && npm run preview   # http://localhost:4173
```

`web/dist/` es una web estática: se puede subir a cualquier hosting (GitHub Pages, Netlify…).

### Cómo interactuar

| Gesto | Respuesta |
|---|---|
| **Arrastrar** sobre cabeza, cuello, lomo o barbilla | Caricias: cierra los ojos, se inclina hacia la mano, relaja las gorgueras, sonríe y «ronronea» (brillo y garganta vibran). Al terminar puede buscar tu mano. |
| **Tocar el hocico** | Variantes al azar: olfatea, estornuda (con anticipación y bocanada de brasa), te da un lametón o bizquea mirando tu dedo. |
| Tocar la **barbilla** | Levanta la barbilla, encantado. |
| Tocar un **ojo** | Lo cierra de golpe, retrocede y se molesta (aumenta su irritación). |
| Tocar **cuernos / gorgueras** | Sacude la cabeza / despliega las gorgueras. |
| Tocar un **ala** | Mira el ala, la sacude o la estira por completo. |
| Tocar la **cola** | Latigazo con onda viajera, abre el abanico y se gira a mirarla. |
| Tocar una **pata** | La levanta (IK) y mira. |
| Mover el **cursor/dedo** | Lo sigue con los ojos (que se adelantan) y la cabeza (con retraso). |
| Arrastrar el **fondo** / rueda / pellizco | Cámara orbital y zoom. |

La reacción depende del ánimo. Enfadado lanza dentelladas o gruñe; desconfiado retrocede; con
sueño responde perezoso o bosteza; en modo juego se agazapa. Muchos toques seguidos lo irritan.

**Interfaz:**
- **Selector de ánimo**: *Autónomo* más las 8 emociones. En modo autónomo el ánimo deriva solo: las caricias llevan a ternura o alegría, la insistencia a desconfianza o enfado, la inactividad al sueño y el cursor activo a la curiosidad.
- **Interactuar / Inspeccionar**: en inspección la cámara es libre y se muestran datos técnicos.
- **Encuadres**: cuerpo completo, tres cuartos, retrato (sigue la cabeza), perfil, ojo, alas, cola y posterior.
- **Cine**: cámara automática con planos encadenados.
- **Capas**: malla, esqueleto y resplandor.

---

## 2. Regenerar el modelo (Blender)

Requisitos: Blender 4.5 LTS (probado con 4.5.16), Python 3 con `numpy`, `scikit-image` y `Pillow`.

```bash
python3 blender/01_sculpt.py 0.003          # escultura (≈1,7 M vértices, ~90 s)
python3 blender/02_textures.py              # texturas procedurales
blender -b -P blender/03_build.py -- --hero-faces 520000 --web-faces 110000
blender -b output/vesper.blend -P blender/04_render.py -- --cams Cam_Heroe,Cam_Cabeza --action enfado --frame 60
bash blender/05_render_all.sh 128           # tanda completa de renders
```

`03_build.py` regenera de una vez `output/vesper.blend`, `web/public/vesper.glb` y `web/public/rig.json`.
Si cambias las texturas, copia las versiones WebP a `web/public/textures/`
(conversión incluida al final de este README).

### Cómo está construido

- **Geometría.** El cuerpo se esculpe como unión suave de unas 240 primitivas anatómicas: cráneo, hocico,
  mandíbula, músculos, huesos de las patas, dedos, garras, cuernos y espinas dorsales colocadas sobre la
  superficie por *raymarching*. Las sustracciones suaves crean la boca, la cavidad bucal, las narinas y
  las cuencas oculares. Se malla por *marching cubes* por bloques a 3 mm, se suaviza y se diezma de forma
  simétrica (520 k caras en el `.blend`, 110 k en la web).
- **Piezas paramétricas.**
  - Ojos con iris cóncavo y córnea separada (refracción real en Cycles).
  - Párpados como cáscaras articuladas con borde redondeado.
  - Dientes y colmillos colocados sobre el labio real.
  - Lengua con surco central.
  - Gorgueras y abanico caudal: espinas curvadas con membrana festoneada.
  - Membranas alares lofteadas entre los dedos, con festón en el borde de fuga y comba.
- **Rig: 87 huesos de deformación más controles IK.**
  - Cuello, cabeza, mandíbula, lengua, ojos, párpados, cejas y narinas.
  - Gorgueras con 4 radios por lado.
  - Patas con IK y polos; brazo alar más 4 dedos de 2 falanges por lado.
  - 14 vértebras caudales y 5 radios del abanico.
- **Pesos.** Calculados desde el propio SDF con un *softmax* de distancias agrupado por hueso. Las uniones
  suaves dan transiciones suaves en las articulaciones. Se añade una regla geométrica específica para la
  mandíbula (plano de la boca) y para las cejas.
- **Shape keys.** `Breathe`, `ThroatPuff`, `Snarl`, `NostrilFlare` y `Smile`. En el `.blend` las gobiernan
  *drivers* desde propiedades del rig; en la web son *morph targets*.
- **Materiales (Cycles).**
  - Piel con escamas proyectadas en coordenadas de reposo (no «nadan» al deformarse), placas ventrales,
    variación por escama, cavidades, iridiscencia de capa fina, *coat*, SSS y emisión de brasa.
  - Queratina con degradado base → punta.
  - Membranas con venas, translucidez y brillo de borde.
  - Iris con pupila procedural; córnea de vidrio; dientes y boca con SSS.
- **Acciones.** `Reposo` y una acción por emoción (`Emocion_*`). Combinan pose emocional, respiración,
  onda de cola, micro-movimiento de cabeza y parpadeo. Las propiedades `pupil`, `glow`, `snarl`… del rig
  (en **VesperRig > Propiedades personalizadas**) controlan materiales y shape keys.

### Rig expresivo compartido

`blender/lib/rigdef.py` define los parámetros: `head_pitch`, `head_yaw`, `head_tilt`, `neck_raise`,
`neck_reach`, `jaw_open`, `lid_up`, `lid_lo`, `frill_flare`, `frill_spread`, `tail_raise`, `fan_spread`,
`front_lower`, `wing_open`, etc. Cada uno es una lista de rotaciones con eje en **espacio del esqueleto
en reposo**. Blender y three.js los convierten al marco local de cada hueso de la misma forma, así que una
emoción se ve igual en ambos. Se ha verificado que las posiciones óseas coinciden numéricamente.

- **Añadir o retocar una emoción:** edita `EMOTIONS` en `rigdef.py` y vuelve a ejecutar `03_build.py`.
- **Retocar su conducta dinámica** (respiración, parpadeo, cola, reacciones): ajusta `STYLE` y `CLIPS`
  en `web/src/behavior.js`.

---

## 3. Arquitectura de la app web

| Archivo | Función |
|---|---|
| `src/rig.js` | Aplica los parámetros a los huesos y resuelve el IK analítico de dos huesos (patas apoyadas al agacharse o al jugar). Gestiona la mirada independiente de cada ojo (convergen en objetos cercanos), los morphs y los muelles críticamente amortiguados. |
| `src/behavior.js` | Controlador de conducta. Ánimo autónomo con histéresis; caricias continuas; unas 30 reacciones con anticipación, acción y recuperación, variantes aleatorias y modulación por ánimo. Incluye atención y mirada (cursor, espectador, miradas furtivas), parpadeo (simple, doble y lento), respiración por ánimo y ronroneo. Cada parámetro tiene dos versiones suavizadas: rápida para la cabeza y lenta para cuello, cuerpo, cola y alas, lo que crea la acción superpuesta. |
| `src/materials.js` | Shaders de piel (escamas triplanares en espacio de reposo, mapa corporal, relieve), párpados, iris con pupila dinámica, córnea, membranas con translucidez real respecto a las luces y brillo de borde. |
| `src/stage.js` | Estudio oscuro: luz clave cálida con sombras suaves, contraluces fríos, entorno PMREM tenue, suelo con caída radial, motas de brasa, *bloom* HDR, AgX. Calidad adaptativa (alta / media). |
| `src/camera.js` | Encuadres con transición, seguimiento de cabeza y ojo, modo cine y adaptación a pantallas verticales. |
| `src/ui.js`, `src/style.css` | Interfaz adaptable a escritorio, iPad y móvil. |

Para detectar los toques se usa un proxy de baja resolución (`VesperBody_pick`, 9 k caras) con el mismo
esqueleto. La zona se identifica por el hueso dominante del triángulo tocado y se refina en el marco
de reposo de la cabeza (hocico, cuernos).

---

## 4. Verificación realizada

- Renders Cycles desde frontal, perfil, tres cuartos, posterior, cabeza, ojo, alas y cola, más primeros
  planos de las 8 emociones (`renders/`). Se corrigieron de forma iterativa: proporciones de cabeza,
  mandíbula y pectorales; grosor de patas; dientes mal colocados; párpados; plegado de alas; tono de la
  piel; translucidez de las membranas; brillo de la boca; color de cuernos.
- App web probada en Chromium sin interfaz gráfica (WebGL por software).
  - Captura de las 8 emociones y verificación de que las posiciones óseas en reposo coinciden con Blender.
  - Simulación de caricias y toques con eventos de puntero reales y comprobación de la zona detectada
    (cabeza, hocico, ala, cola, pata).
  - Secuencias de reacciones a paso fijo (caricia, estornudo, bostezo).
  - Maquetación a 1440×900, 1024×1366 (iPad) y 390×844 (móvil).

### Limitaciones conocidas (honestas)

- **Rendimiento:** no se ha podido medir en una GPU real; en el entorno de desarrollo solo había
  renderizado por software. El panel de inspección muestra los FPS reales en tu dispositivo.
- **Topología:** procede de *marching cubes* más diezmado (triángulos regulares), no de una retopología
  manual en quads. Deforma bien en los rangos del rig, pero no es la malla que entregaría un estudio para
  esculpir encima en ZBrush.
- **Microdetalle:** las escamas son relieve procedural (bump y textura), no geometría desplazada.
- **Alas plegadas:** el *skinning* lineal comprime algo la membrana; no hay simulación de tela.
- **Acciones del `.blend`:** reproducen las poses emocionales con respiración, cola y parpadeo. La conducta
  reactiva completa (caricias, toques, atención) vive en la app web.
- **EEVEE:** no se usó porque el entorno no tenía GPU ni EGL; todos los renders son Cycles por CPU.

### Conversión de texturas para la web

```bash
python3 -c "
from PIL import Image; s='assets/textures/'; d='web/public/textures/'
Image.open(s+'scales_data.png').convert('RGB').resize((1024,1024)).save(d+'scales_data.webp',quality=92)
Image.open(s+'iris.png').save(d+'iris.webp',quality=92)
Image.open(s+'wing_veins.png').save(d+'wing_veins.webp',quality=90)
Image.open(s+'bodymap.png').save(d+'bodymap.webp',lossless=True)"
```
