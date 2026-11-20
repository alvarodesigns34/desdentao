// Materiales en tiempo real de Vesper (equivalentes a los de Cycles en el .blend).
// La piel usa escamas triplanares en espacio de reposo (no "nadan" al deformarse),
// el mapa corporal (placas ventrales y vetas de brasa) en coordenadas bodyuv y
// máscaras por vértice calculadas desde el SDF (queratina, boca, oclusión).
import * as THREE from 'three';

export const shared = {
  uTime: { value: 0 },
  uGlow: { value: 0.15 },
  uThroat: { value: 0 },
  uPupil: { value: 0.3 },
  uGlowColor: { value: new THREE.Color(1.0, 0.36, 0.06) },
  // luces para la translucidez de las membranas (dirección en espacio vista + color)
  uBackDir: { value: [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()] },
  uBackCol: { value: [new THREE.Color(), new THREE.Color(), new THREE.Color()] },
};

const BUMP_FN = /* glsl */`
vec3 perturbNormalH( vec3 surf_pos, vec3 surf_norm, vec2 dHdxy, float faceDirection ) {
  // protegido frente a derivadas nulas (líneas, triángulos de canto): evita NaN que el bloom propagaría
  vec3 dx = dFdx( surf_pos.xyz ), dy = dFdy( surf_pos.xyz );
  if ( dot( dx, dx ) < 1e-14 || dot( dy, dy ) < 1e-14 ) return surf_norm;
  vec3 vSigmaX = normalize( dx );
  vec3 vSigmaY = normalize( dy );
  vec3 vN = surf_norm;
  vec3 R1 = cross( vSigmaY, vN );
  vec3 R2 = cross( vN, vSigmaX );
  float fDet = dot( vSigmaX, R1 ) * faceDirection;
  vec3 vGrad = sign( fDet ) * ( dHdxy.x * R1 + dHdxy.y * R2 );
  vec3 r = abs( fDet ) * surf_norm - vGrad;
  return dot( r, r ) > 1e-12 ? normalize( r ) : surf_norm;
}
vec3 triplanar( sampler2D t, vec3 p, vec3 n, float scale ) {
  vec3 w = pow( abs( n ), vec3( 4.0 ) );
  w /= ( w.x + w.y + w.z + 1e-5 );
  return texture2D( t, p.yz / scale ).rgb * w.x
       + texture2D( t, p.xz / scale ).rgb * w.y
       + texture2D( t, p.xy / scale ).rgb * w.z;
}
float hash13( vec3 p ) { p = fract( p * 0.1031 ); p += dot( p, p.zyx + 31.32 ); return fract( ( p.x + p.y ) * p.z ); }
float vnoise( vec3 p ) {
  vec3 i = floor( p ); vec3 f = fract( p ); f = f * f * ( 3.0 - 2.0 * f );
  return mix( mix( mix( hash13( i ), hash13( i + vec3(1,0,0) ), f.x ), mix( hash13( i + vec3(0,1,0) ), hash13( i + vec3(1,1,0) ), f.x ), f.y ),
              mix( mix( hash13( i + vec3(0,0,1) ), hash13( i + vec3(1,0,1) ), f.x ), mix( hash13( i + vec3(0,1,1) ), hash13( i + vec3(1,1,1) ), f.x ), f.y ), f.z );
}
`;

function restVaryings(shader, extraVert = '') {
  shader.vertexShader = shader.vertexShader
    .replace('#include <common>', `#include <common>
      varying vec3 vRest; varying vec3 vRestN; ${extraVert}`)
    .replace('#include <beginnormal_vertex>', `#include <beginnormal_vertex>
      vRestN = objectNormal;`)
    .replace('#include <begin_vertex>', `#include <begin_vertex>
      vRest = position;`);
}

export function makeSkin(tex) {
  const m = new THREE.MeshPhysicalMaterial({
    color: 0xffffff, roughness: 0.5, metalness: 0,
    vertexColors: true,
    iridescence: 0.30, iridescenceIOR: 1.38, iridescenceThicknessRange: [280, 480],
    clearcoat: 0.03, clearcoatRoughness: 0.4,
    sheen: 0.12, sheenColor: new THREE.Color(0.10, 0.12, 0.18), sheenRoughness: 0.6,
    specularIntensity: 0.38, envMapIntensity: 0.6,
  });
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, {
      tScales: { value: tex.scales }, tBody: { value: tex.body },
      uGlow: shared.uGlow, uThroat: shared.uThroat, uTime: shared.uTime, uGlowColor: shared.uGlowColor,
      uBump: { value: 1.0 },
    });
    restVaryings(sh, `varying vec2 vBUV; varying vec2 vKD;
      #ifndef USE_UV1
        attribute vec2 uv1;
      #endif`);
    sh.vertexShader = sh.vertexShader.replace('#include <uv_vertex>', `#include <uv_vertex>
      vBUV = uv; vKD = uv1;`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform sampler2D tScales; uniform sampler2D tBody;
        uniform float uGlow; uniform float uThroat; uniform float uTime; uniform vec3 uGlowColor; uniform float uBump;
        varying vec3 vRest; varying vec3 vRestN; varying vec2 vBUV; varying vec2 vKD;
        ${BUMP_FN}`)
      .replace('#include <color_fragment>', `
        vec3 rn = normalize( vRestN );
        vec3 sc  = triplanar( tScales, vRest, rn, 0.30 );
        vec3 scf = triplanar( tScales, vRest + 0.37, rn, 0.11 );
        vec3 bm = texture2D( tBody, vBUV ).rgb;
        float ker = vColor.r, tube = vColor.g, mouthM = vColor.b, aoV = vColor.a;
        float belly = bm.b * tube, scute = bm.g * tube, glowM = bm.r * tube;
        vec3 cBack = vec3( 0.010, 0.011, 0.016 ), cFlank = vec3( 0.020, 0.021, 0.031 ), cBelly = vec3( 0.068, 0.056, 0.048 );
        vec3 col = mix( cBack, cFlank, smoothstep( 0.25, 0.65, vBUV.y ) );
        col = mix( col, cBelly, belly );
        float nz = vnoise( vRest * 3.0 ) * 0.6 + vnoise( vRest * 7.0 ) * 0.4;
        col *= ( 0.80 + 0.35 * sc.g ) * ( 0.75 + 0.5 * nz ) * ( 1.0 - 0.45 * sc.b );
        vec3 kc = mix( vec3( 0.020, 0.018, 0.016 ), vec3( 0.16, 0.135, 0.10 ), pow( clamp( vKD.x, 0.0, 1.0 ), 1.7 ) );
        col = mix( col, kc, ker );
        col = mix( col, vec3( 0.20, 0.035, 0.04 ), mouthM );
        col = mix( col, vec3( 0.004, 0.003, 0.003 ), vKD.y );
        col *= pow( max( aoV, 0.0 ), 0.8 );
        diffuseColor.rgb = col;
        float hgt = sc.r * ( 1.0 - ker ) + 0.35 * scf.r + 1.4 * scute;
        float roughV = 0.55 + 0.18 * sc.b + 0.10 * sc.g + 0.08 * belly;
        roughV = mix( roughV, 0.42, ker ); roughV = mix( roughV, 0.22, mouthM );
      `)
      .replace('#include <roughnessmap_fragment>', `float roughnessFactor = roughV;`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        {
          // relieve por derivadas en pantalla (independiente de la escala); se atenúa
          // a distancia para evitar el centelleo de las escamas sub-píxel
          float fw = clamp( 0.004 / max( length( fwidth( vRest ) ), 1e-5 ), 0.0, 1.0 );
          vec2 dHdxy = vec2( dFdx( hgt ), dFdy( hgt ) ) * 0.55 * uBump * fw;
          normal = perturbNormalH( -vViewPosition, normal, dHdxy, faceDirection );
        }`)
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        float flow = 0.80 + 0.20 * sin( vBUV.x * 70.0 - uTime * 1.6 );
        totalEmissiveRadiance += uGlowColor * ( glowM * uGlow * flow * 9.0 + mouthM * uThroat * 0.25 );`);
  };
  return m;
}

export function makeLid(tex) {
  const m = new THREE.MeshPhysicalMaterial({
    color: 0xffffff, roughness: 0.42, iridescence: 0.4, iridescenceIOR: 1.38,
    iridescenceThicknessRange: [300, 420], clearcoat: 0.15, clearcoatRoughness: 0.3,
  });
  m.onBeforeCompile = (sh) => {
    sh.uniforms.tScales = { value: tex.scales };
    restVaryings(sh, 'varying vec2 vLUv;');
    sh.vertexShader = sh.vertexShader.replace('#include <uv_vertex>', '#include <uv_vertex>\n vLUv = uv;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform sampler2D tScales; varying vec3 vRest; varying vec3 vRestN; varying vec2 vLUv; ${BUMP_FN}`)
      .replace('#include <color_fragment>', `
        vec3 sc = triplanar( tScales, vRest, normalize( vRestN ), 0.07 );
        float margin = step( 0.5, vLUv.y );
        diffuseColor.rgb = mix( vec3( 0.014, 0.015, 0.021 ), vec3( 0.035, 0.012, 0.012 ), margin ) * ( 0.8 + 0.4 * sc.g );
        float hgt = sc.r;`)
      .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = mix( 0.44, 0.18, margin );')
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        normal = perturbNormalH( -vViewPosition, normal, vec2( dFdx( hgt ), dFdy( hgt ) ) * 0.4, faceDirection );`);
  };
  return m;
}

export function makeEye(tex) {
  const m = new THREE.MeshStandardMaterial({ map: tex.iris, roughness: 0.35, emissive: 0xffffff, emissiveIntensity: 0.0 });
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uPupil = shared.uPupil;
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform float uPupil;')
      .replace('#include <map_fragment>', `
        vec4 irisC = texture2D( map, vMapUv );
        vec2 pc = vMapUv * 2.0 - 1.0;
        float pw = mix( 0.06, 0.64, uPupil ), ph = mix( 0.80, 0.90, uPupil );
        float r = length( vec2( pc.x / pw, pc.y / ph ) );
        float pupilM = 1.0 - smoothstep( 0.90, 1.08, r );
        // anillo de iris algo más brillante junto a la pupila
        vec3 irisCol = irisC.rgb * ( 1.0 + 0.35 * smoothstep( 1.6, 1.0, r ) * ( 1.0 - pupilM ) );
        diffuseColor.rgb = mix( irisCol, vec3( 0.002, 0.0015, 0.001 ), pupilM );
        float irisEmit = ( 1.0 - pupilM );`)
      .replace('#include <emissivemap_fragment>', `
        totalEmissiveRadiance = diffuseColor.rgb * irisEmit * 0.35;`);
  };
  return m;
}

export function makeCornea() {
  return new THREE.MeshPhysicalMaterial({
    color: 0xffffff, roughness: 0.0, metalness: 0, transparent: true, opacity: 0.12,
    clearcoat: 1, clearcoatRoughness: 0.0, specularIntensity: 1, envMapIntensity: 2.5,
    depthWrite: false,
  });
}

export function makeMembrane(tex, kind = 'wing') {
  const m = new THREE.MeshPhysicalMaterial({ map: tex.veins, roughness: 0.7, side: THREE.DoubleSide, envMapIntensity: 0.35, specularIntensity: 0.35 });
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, {
      uGlow: shared.uGlow, uGlowColor: shared.uGlowColor, uTime: shared.uTime,
      uBackDir: shared.uBackDir, uBackCol: shared.uBackCol,
      uEdgeGain: { value: kind === 'wing' ? 1.6 : 3.0 },
    });
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        ${BUMP_FN}
        uniform float uGlow; uniform vec3 uGlowColor; uniform float uTime; uniform float uEdgeGain;
        uniform vec3 uBackDir[3]; uniform vec3 uBackCol[3];`)
      .replace('#include <map_fragment>', `
        vec3 vt = texture2D( map, vMapUv ).rgb;
        float veins = vt.r, thick = vt.g, edge = vt.b;
        diffuseColor.rgb = mix( vec3( 0.026, 0.025, 0.034 ), vec3( 0.010, 0.008, 0.012 ), veins );
        float hgt = veins;`)
      .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = 0.68 + 0.15 * thick;')
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        normal = perturbNormalH( -vViewPosition, normal, vec2( dFdx( hgt ), dFdy( hgt ) ) * 0.6, faceDirection );`)
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        {
          // translucidez: luz que atraviesa la membrana desde detrás
          vec3 tcol = mix( vec3( 0.09, 0.022, 0.018 ), vec3( 0.015, 0.004, 0.004 ), veins ) * ( 1.2 - 0.4 * thick );
          for ( int i = 0; i < 3; i ++ ) {
            float t = max( 0.0, -dot( normal, uBackDir[ i ] ) );
            totalEmissiveRadiance += tcol * uBackCol[ i ] * t * 0.35;
          }
          totalEmissiveRadiance += uGlowColor * edge * uGlow * uEdgeGain * ( 0.8 + 0.2 * sin( uTime * 2.0 + vMapUv.x * 30.0 ) );
        }`);
  };
  return m;
}

export function makeBasic() {
  return {
    keratin: new THREE.MeshPhysicalMaterial({ color: new THREE.Color(0.06, 0.052, 0.046), roughness: 0.42, clearcoat: 0.1, clearcoatRoughness: 0.4, specularIntensity: 0.4 }),
    teeth: new THREE.MeshPhysicalMaterial({ color: new THREE.Color(0.50, 0.46, 0.38), roughness: 0.38, clearcoat: 0.15, specularIntensity: 0.5 }),
    mouth: new THREE.MeshPhysicalMaterial({ color: new THREE.Color(0.24, 0.045, 0.05), roughness: 0.22, clearcoat: 0.6, clearcoatRoughness: 0.15 }),
  };
}

export function loadTextures(manager) {
  const L = new THREE.TextureLoader(manager);
  const lin = (u, rep = true) => {
    const t = L.load(u);
    t.colorSpace = THREE.NoColorSpace;
    if (rep) t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.anisotropy = 8;
    return t;
  };
  const iris = L.load('textures/iris.webp');
  iris.colorSpace = THREE.SRGBColorSpace; iris.anisotropy = 8;
  const body = lin('textures/bodymap.webp', false);
  body.wrapS = body.wrapT = THREE.ClampToEdgeWrapping;
  const veins = lin('textures/wing_veins.webp', false);
  veins.colorSpace = THREE.NoColorSpace;
  return { scales: lin('textures/scales_data.webp'), body, iris, veins };
}

// Asigna materiales por nombre de malla
export function assignMaterials(model, tex) {
  const skin = makeSkin(tex), lid = makeLid(tex), eye = makeEye(tex), cornea = makeCornea();
  const wing = makeMembrane(tex, 'wing'), frill = makeMembrane(tex, 'frill');
  const basic = makeBasic();
  model.traverse((o) => {
    if (!o.isMesh) return;
    const n = o.name;
    o.castShadow = true; o.receiveShadow = true;
    o.frustumCulled = false;
    if (n.startsWith('VesperBody_pick')) { o.visible = false; return; }
    if (n.startsWith('VesperBody')) o.material = skin;
    else if (n.startsWith('Lid')) o.material = lid;
    else if (n.startsWith('Eye')) o.material = eye;
    else if (n.startsWith('Cornea')) { o.material = cornea; o.castShadow = false; o.renderOrder = 2; }
    else if (n.startsWith('Wing')) { o.material = wing; o.receiveShadow = false; }
    else if (n.includes('Membrane')) { o.material = frill; o.receiveShadow = false; }
    else if (n.includes('Spines')) o.material = basic.keratin;
    else if (n.startsWith('Teeth')) o.material = basic.teeth;
    else if (n.startsWith('Tongue')) o.material = basic.mouth;
  });
  return { skin, lid, eye, cornea, wing, frill, ...basic };
}
