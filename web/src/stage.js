// Estudio: renderer, iluminación cinematográfica, suelo, partículas de brasa y posprocesado.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { shared } from './materials.js';

export const BG = new THREE.Color(0x050609);

export function detectQuality() {
  const coarse = matchMedia('(pointer: coarse)').matches;
  const small = Math.min(innerWidth, innerHeight) < 700;
  return coarse || small ? 'media' : 'alta';
}

export function createStage(canvas, quality) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
  const dprMax = quality === 'alta' ? 2 : 1.5;
  renderer.setPixelRatio(Math.min(devicePixelRatio, dprMax));
  renderer.setSize(innerWidth, innerHeight, false);
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  scene.background = BG;
  scene.fog = new THREE.FogExp2(BG, 0.045);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.16;

  const camera = new THREE.PerspectiveCamera(32, innerWidth / innerHeight, 0.05, 80);
  camera.position.set(4.6, 2.3, 5.6);

  // --- luces (equivalentes al estudio del .blend) -------------------------
  const key = new THREE.DirectionalLight(new THREE.Color(1.0, 0.9, 0.8), 2.4);
  key.position.set(3.2, 4.2, 4.2);
  key.target.position.set(0, 1.0, 0.4);
  key.castShadow = true;
  const sm = quality === 'alta' ? 2048 : 1024;
  key.shadow.mapSize.set(sm, sm);
  Object.assign(key.shadow.camera, { left: -4.5, right: 4.5, top: 4.5, bottom: -4.5, near: 0.5, far: 16 });
  key.shadow.bias = -0.0003; key.shadow.normalBias = 0.02;
  scene.add(key, key.target);

  const rimL = new THREE.SpotLight(new THREE.Color(0.55, 0.70, 1.0), 95, 18, 0.55, 0.65, 1.6);
  rimL.position.set(-3.4, 3.4, -3.2); rimL.target.position.set(0, 1.3, 0.5);
  const rimR = new THREE.SpotLight(new THREE.Color(0.65, 0.78, 1.0), 70, 18, 0.55, 0.65, 1.6);
  rimR.position.set(3.8, 2.9, -2.6); rimR.target.position.set(0, 1.2, 0.2);
  const top = new THREE.SpotLight(new THREE.Color(0.9, 0.92, 1.0), 22, 14, 0.7, 0.9, 1.6);
  top.position.set(0, 6.5, -0.4); top.target.position.set(0, 0.8, -0.4);
  const fill = new THREE.HemisphereLight(new THREE.Color(0.32, 0.38, 0.5), new THREE.Color(0.02, 0.02, 0.025), 0.35);
  scene.add(rimL, rimL.target, rimR, rimR.target, top, top.target, fill);
  const backLights = [key, rimL, rimR];

  // --- suelo -------------------------------------------------------------
  const floorMat = new THREE.MeshStandardMaterial({ color: 0x0c0d11, roughness: 0.62, metalness: 0 });
  floorMat.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec2 vFP;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvFP = position.xy;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec2 vFP;')
      .replace('#include <color_fragment>', `#include <color_fragment>
        float rr = length( vFP - vec2( 0.0, 0.3 ) );
        diffuseColor.rgb *= mix( 0.9, 0.2, smoothstep( 1.0, 8.0, rr ) );`);
  };
  const floor = new THREE.Mesh(new THREE.CircleGeometry(18, 96), floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  // --- motas de brasa flotantes ------------------------------------------
  const N = quality === 'alta' ? 220 : 120;
  const g = new THREE.BufferGeometry();
  const pos = new Float32Array(N * 3), seed = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 9; pos[i * 3 + 1] = Math.random() * 4; pos[i * 3 + 2] = (Math.random() - 0.5) * 9;
    seed[i] = Math.random();
  }
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('seed', new THREE.BufferAttribute(seed, 1));
  const motes = new THREE.Points(g, new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { uTime: shared.uTime, uGlow: shared.uGlow, uPx: { value: renderer.getPixelRatio() } },
    vertexShader: /* glsl */`
      attribute float seed; uniform float uTime; uniform float uPx; varying float vA;
      void main() {
        vec3 p = position;
        float t = uTime * ( 0.04 + 0.05 * seed );
        p.y = mod( p.y + t * 3.0, 4.0 );
        p.x += sin( uTime * 0.3 + seed * 40.0 ) * 0.25;
        p.z += cos( uTime * 0.23 + seed * 30.0 ) * 0.25;
        vec4 mv = modelViewMatrix * vec4( p, 1.0 );
        gl_Position = projectionMatrix * mv;
        gl_PointSize = uPx * ( 1.5 + 2.5 * seed ) * ( 4.0 / -mv.z );
        vA = smoothstep( 0.0, 0.6, p.y ) * smoothstep( 4.0, 2.8, p.y ) * ( 0.25 + 0.75 * fract( seed * 7.3 ) );
      }`,
    fragmentShader: /* glsl */`
      uniform float uGlow; varying float vA;
      void main() {
        float d = length( gl_PointCoord - 0.5 );
        float a = smoothstep( 0.5, 0.0, d ) * vA * ( 0.18 + 0.5 * uGlow );
        gl_FragColor = vec4( vec3( 1.0, 0.45, 0.12 ) * a, a );
      }`,
  }));
  scene.add(motes);

  // --- posprocesado ------------------------------------------------------
  const rt = new THREE.WebGLRenderTarget(innerWidth, innerHeight, {
    type: THREE.HalfFloatType, samples: quality === 'alta' ? 4 : 2,
  });
  const composer = new EffectComposer(renderer, rt);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth / 2, innerHeight / 2), 0.6, 0.5, 1.4);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  function resize() {
    const w = innerWidth, h = innerHeight;
    renderer.setSize(w, h, false);
    composer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  addEventListener('resize', resize);

  // direcciones de las luces para la translucidez (espacio vista)
  const _v = new THREE.Vector3();
  function updateLightUniforms() {
    backLights.forEach((L, i) => {
      _v.copy(L.position).sub(L.target.position).normalize().transformDirection(camera.matrixWorldInverse);
      shared.uBackDir.value[i].copy(_v);
      shared.uBackCol.value[i].copy(L.color).multiplyScalar(i === 0 ? 1.4 : 1.0);
    });
  }

  return { renderer, scene, camera, composer, bloom, key, floor, motes, updateLightUniforms, resize };
}
