import * as THREE from '/assets/three.module.min.js';

const canvas3d = document.getElementById('tankCanvas');
const hud3d = document.getElementById('tankHud');
const badge3d = document.getElementById('tankBadge');
const fallback3d = document.getElementById('tankFallback');

let renderer3d = null;
let camera3d = null;
let scene3d = null;
let tankRoot = null;
let waterMesh = null;
let glassMesh = null;
let bioAob = null;
let bioNob = null;
let fish = null;
let agentFishGroup = null;
let frames3d = 0;
let tankRows = [];
let currentStats = {day: 0, TAN: 0, NO2: 0, NO3: 0, DO: 0, NH3_free: 0, pH: 7.4};
let drag = {active: false, x: 0, y: 0, yaw: -0.35, pitch: -0.08};

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function norm(v, maxValue) { return clamp(Number(v || 0) / Math.max(maxValue || 1, 1e-6), 0, 1); }

function makeMaterial(color, opacity=1, roughness=.45, metalness=0) {
  return new THREE.MeshStandardMaterial({
    color, transparent: opacity < 1, opacity, roughness, metalness,
    side: THREE.DoubleSide,
  });
}

function particleCloud(color, count, radius) {
  const group = new THREE.Group();
  const geom = new THREE.SphereGeometry(radius, 10, 8);
  const mat = makeMaterial(color, .82, .4, 0);
  for (let i = 0; i < count; i += 1) {
    const mesh = new THREE.Mesh(geom, mat);
    mesh.position.set((Math.random()-.5)*5.1, -1 + Math.random()*2.1, (Math.random()-.5)*2.2);
    mesh.userData.seed = Math.random() * 1000;
    group.add(mesh);
  }
  return group;
}

function buildFish() {
  const group = new THREE.Group();
  const body = new THREE.Mesh(new THREE.SphereGeometry(.34, 24, 14), makeMaterial(0xf3a23a, .96, .35, 0));
  body.scale.set(1.55, .78, .58);
  const tail = new THREE.Mesh(new THREE.ConeGeometry(.22, .45, 3), makeMaterial(0xd45a2a, .94, .4, 0));
  tail.rotation.z = Math.PI / 2;
  tail.position.x = -.62;
  const eye = new THREE.Mesh(new THREE.SphereGeometry(.035, 10, 8), makeMaterial(0x101820));
  eye.position.set(.43, .12, .18);
  group.add(body, tail, eye);
  group.position.set(-1.8, .25, .25);
  return group;
}

function init3d() {
  try {
    renderer3d = new THREE.WebGLRenderer({
      canvas: canvas3d, antialias: true, alpha: false, preserveDrawingBuffer: true,
    });
    renderer3d.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer3d.setClearColor(0x071c24, 1);
    scene3d = new THREE.Scene();
    scene3d.fog = new THREE.Fog(0x071c24, 7, 16);
    camera3d = new THREE.PerspectiveCamera(44, 1, .1, 100);
    camera3d.position.set(0, 1.35, 8.2);
    camera3d.lookAt(0, -.05, 0);

    const hemi = new THREE.HemisphereLight(0xc7eef7, 0x18313a, 2.2);
    const key = new THREE.DirectionalLight(0xffffff, 2.4);
    key.position.set(3, 5, 4);
    scene3d.add(hemi, key);

    tankRoot = new THREE.Group();
    tankRoot.rotation.y = drag.yaw;
    tankRoot.rotation.x = drag.pitch;
    scene3d.add(tankRoot);

    const glassGeom = new THREE.BoxGeometry(5.8, 2.75, 2.55);
    glassMesh = new THREE.Mesh(glassGeom, makeMaterial(0xbfeaf5, .16, .08, 0));
    tankRoot.add(glassMesh);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(glassGeom),
      new THREE.LineBasicMaterial({color: 0xcbeaf1, transparent: true, opacity: .55}),
    );
    tankRoot.add(edges);

    waterMesh = new THREE.Mesh(
      new THREE.BoxGeometry(5.65, 2.12, 2.38),
      makeMaterial(0x2ca9c7, .34, .15, 0),
    );
    waterMesh.position.y = -.18;
    tankRoot.add(waterMesh);

    const substrate = new THREE.Mesh(new THREE.BoxGeometry(5.65, .18, 2.36), makeMaterial(0xb9925a, .95, .8, 0));
    substrate.position.y = -1.48;
    tankRoot.add(substrate);

    const filter = new THREE.Mesh(new THREE.CylinderGeometry(.22, .28, 2.1, 24), makeMaterial(0x26333f, .9, .55, 0));
    filter.position.set(2.35, -.25, -.88);
    tankRoot.add(filter);
    bioAob = new THREE.Mesh(new THREE.TorusGeometry(.34, .045, 10, 34), makeMaterial(0x2e933c, .9, .35, 0));
    bioAob.position.copy(filter.position); bioAob.position.y += .5; bioAob.rotation.x = Math.PI / 2;
    bioNob = new THREE.Mesh(new THREE.TorusGeometry(.45, .045, 10, 34), makeMaterial(0x7d4f50, .9, .35, 0));
    bioNob.position.copy(filter.position); bioNob.position.y += .15; bioNob.rotation.x = Math.PI / 2;
    tankRoot.add(bioAob, bioNob);

    tankRoot.add(particleCloud(0xd1495b, 34, .045));
    tankRoot.add(particleCloud(0xedae49, 34, .042));
    tankRoot.add(particleCloud(0x00798c, 42, .04));
    tankRoot.children.slice(-3).forEach((g, i) => { g.name = ['tanParticles', 'no2Particles', 'no3Particles'][i]; });

    const bubbleGroup = new THREE.Group();
    bubbleGroup.name = 'bubbles';
    const bubbleGeom = new THREE.SphereGeometry(.035, 10, 8);
    const bubbleMat = makeMaterial(0xd7f8ff, .72, .05, 0);
    for (let i = 0; i < 34; i += 1) {
      const b = new THREE.Mesh(bubbleGeom, bubbleMat);
      b.position.set(2.35 + (Math.random()-.5)*.35, -1.22 + Math.random()*2.1, -.88 + (Math.random()-.5)*.38);
      b.userData.seed = Math.random() * 1000;
      bubbleGroup.add(b);
    }
    tankRoot.add(bubbleGroup);

    fish = buildFish();
    fish.visible = false;  // 装饰占位鱼默认隐藏:只显示真实 ABM 鱼,无鱼即无鱼
    tankRoot.add(fish);
    agentFishGroup = new THREE.Group();
    agentFishGroup.name = 'agentFish';
    tankRoot.add(agentFishGroup);

    resize3d();
    new ResizeObserver(resize3d).observe(canvas3d.parentElement);
    canvas3d.addEventListener('pointerdown', onPointerDown);
    canvas3d.addEventListener('pointermove', onPointerMove);
    canvas3d.addEventListener('pointerup', onPointerUp);
    canvas3d.addEventListener('pointerleave', onPointerUp);
    renderer3d.setAnimationLoop(animate3d);
    window.__fishtank3dStatus = () => ({
      renderer: 'three.js',
      frames: frames3d,
      rows: tankRows.length,
      canvasWidth: canvas3d.width,
      canvasHeight: canvas3d.height,
      stats: currentStats,
    });
    window.__fishtank3dPixels = () => {
      const gl = renderer3d.getContext();
      const w = gl.drawingBufferWidth;
      const h = gl.drawingBufferHeight;
      const x0 = Math.floor(w * .2);
      const y0 = Math.floor(h * .2);
      const sw = Math.max(1, Math.floor(w * .6));
      const sh = Math.max(1, Math.floor(h * .6));
      const pixels = new Uint8Array(sw * sh * 4);
      gl.readPixels(x0, y0, sw, sh, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      let hits = 0;
      for (let i = 0; i < pixels.length; i += 16) {
        if (pixels[i] > 10 || pixels[i + 1] > 10 || pixels[i + 2] > 10) hits += 1;
      }
      return {nonblank: hits > 100, hits, checked: sw * sh};
    };
  } catch (err) {
    fallback3d.style.display = 'grid';
    fallback3d.textContent = `3D renderer unavailable: ${err.message}`;
    window.__fishtank3dStatus = () => ({renderer: 'unavailable', error: err.message, frames: frames3d});
  }
}

function resize3d() {
  if (!renderer3d || !camera3d) return;
  const box = canvas3d.parentElement.getBoundingClientRect();
  const width = Math.max(320, Math.floor(box.width));
  const height = Math.max(520, Math.floor(box.height));
  renderer3d.setSize(width, height, false);
  camera3d.aspect = width / height;
  camera3d.updateProjectionMatrix();
}

function onPointerDown(event) {
  drag.active = true;
  drag.x = event.clientX;
  drag.y = event.clientY;
  canvas3d.setPointerCapture(event.pointerId);
}

function onPointerMove(event) {
  if (!drag.active || !tankRoot) return;
  const dx = event.clientX - drag.x;
  const dy = event.clientY - drag.y;
  drag.x = event.clientX;
  drag.y = event.clientY;
  drag.yaw += dx * .006;
  drag.pitch = clamp(drag.pitch + dy * .004, -.45, .35);
  tankRoot.rotation.y = drag.yaw;
  tankRoot.rotation.x = drag.pitch;
}

function onPointerUp() { drag.active = false; }

function updateHud(row) {
  hud3d.innerHTML = [
    ['day', Number(row.day || 0).toFixed(1)],
    ['TAN', Number(row.TAN || 0).toFixed(2)],
    ['NO2', Number(row.NO2 || 0).toFixed(2)],
    ['NO3', Number(row.NO3 || 0).toFixed(1)],
    ['DO', Number(row.DO || 0).toFixed(2)],
  ].map(([label, value]) => `<div class="tank-stat"><span class="label">${t(label)}</span><span class="value">${value}</span></div>`).join('');
  const pH = Number(row.pH || currentStats.pH || 7.4);
  badge3d.textContent = `pH ${pH.toFixed(2)} | ${t('NH3_free')} ${Number(row.NH3_free || 0).toFixed(3)} mg/L`;
}

function updateAgentFish3d(snapshot) {
  if (!agentFishGroup || !fish) return;
  agentFishGroup.clear();
  const agents = Array.isArray(snapshot?.fish) ? snapshot.fish.filter(agent => agent.alive) : [];
  // 不再显示装饰占位鱼:鱼数=0 时缸内就没有鱼(与 KPI/ABM 图一致)
  fish.visible = false;
  for (const agent of agents.slice(0, 48)) {
    const mesh = buildFish();
    const stress = clamp(Number(agent.stress || 0) / 3, 0, 1);
    const scale = .32 + Math.min(.38, Math.sqrt(Number(agent.biomass_g || 1)) * .055);
    mesh.scale.setScalar(scale);
    mesh.position.set(Number(agent.x || 0) * 2.45, Number(agent.y || 0) * 1.15, Number(agent.z || 0) * 1.18);
    mesh.rotation.y = stress * -.35;
    mesh.children[0].material.color.set(stress > .65 ? 0xc75c45 : 0xf3a23a);
    agentFishGroup.add(mesh);
  }
}

function update3d(row, t) {
  currentStats = row;
  const maxes = tankRows.reduce((acc, r) => ({
    TAN: Math.max(acc.TAN, Number(r.TAN || 0)),
    NO2: Math.max(acc.NO2, Number(r.NO2 || 0)),
    NO3: Math.max(acc.NO3, Number(r.NO3 || 0)),
    X_AOB: Math.max(acc.X_AOB, Number(r.X_AOB || 0)),
    X_NOB: Math.max(acc.X_NOB, Number(r.X_NOB || 0)),
  }), {TAN: 1, NO2: 1, NO3: 1, X_AOB: 1, X_NOB: 1});

  const tanN = norm(row.TAN, maxes.TAN);
  const no2N = norm(row.NO2, maxes.NO2);
  const no3N = norm(row.NO3, maxes.NO3);
  const doN = norm(row.DO, 8);
  const stress = clamp(tanN * .42 + no2N * .42 + (1 - doN) * .35, 0, 1);

  const pH = Number(row.pH || 7.4);
  const waterColor = pH < 6.4 ? new THREE.Color(0x8a5d44) : new THREE.Color(0x2ca9c7);
  waterMesh.material.color.lerp(waterColor, .08);
  waterMesh.material.opacity = .25 + .18 * stress;
  glassMesh.material.opacity = .11 + .06 * (1 - doN);

  const groups = {
    tanParticles: [tanN, .9],
    no2Particles: [no2N, 1.3],
    no3Particles: [no3N, .55],
  };
  for (const group of tankRoot.children.filter(obj => groups[obj.name])) {
    const [level, speed] = groups[group.name];
    const visibleCount = Math.round(group.children.length * (.18 + .82 * level));
    group.children.forEach((p, i) => {
      p.visible = i < visibleCount;
      p.position.y += Math.sin(t * speed + p.userData.seed) * .0009 + .0008;
      if (p.position.y > 1.1) p.position.y = -1.15;
      p.position.x += Math.sin(t * .23 + p.userData.seed) * .002;
      p.position.z += Math.cos(t * .27 + p.userData.seed) * .002;
    });
  }

  bioAob.scale.setScalar(.45 + 1.45 * norm(row.X_AOB, maxes.X_AOB));
  bioNob.scale.setScalar(.45 + 1.45 * norm(row.X_NOB, maxes.X_NOB));

  const bubbles = tankRoot.getObjectByName('bubbles');
  const bubbleCount = Math.round(bubbles.children.length * clamp(.18 + doN, .12, 1));
  bubbles.children.forEach((b, i) => {
    b.visible = i < bubbleCount;
    b.position.y += .01 + doN * .012;
    b.position.x += Math.sin(t * 1.7 + b.userData.seed) * .003;
    if (b.position.y > 1.05) b.position.y = -1.2;
  });

  fish.position.x = Math.sin(t * .55) * 1.55 - stress * .55;
  fish.position.y = .08 + Math.sin(t * .8) * (.18 - stress * .08) - stress * .35;
  fish.rotation.y = Math.sin(t * .55) * .25;
  fish.rotation.z = Math.sin(t * 2.8) * (.05 + .13 * stress);
  fish.children[0].material.color.lerp(new THREE.Color(stress > .55 ? 0xc75c45 : 0xf3a23a), .08);
  if (agentFishGroup) {
    agentFishGroup.children.forEach((mesh, i) => {
      mesh.position.y += Math.sin(t * 1.4 + i) * .0009;
      mesh.rotation.z = Math.sin(t * 2.2 + i) * .05;
    });
  }
  updateHud(row);
}

function animate3d(timeMs) {
  // Skip the expensive WebGL render while the 3D tab is hidden. setAnimationLoop
  // otherwise renders at ~60fps on EVERY tab, stalling weak GPUs / remote-desktop
  // sessions ("GPU stall due to ReadPixels") and making clicks feel unresponsive.
  // The loop keeps ticking; it just does no work until the 3D tab is active again.
  if (!$('tank3d').classList.contains('active')) return;
  frames3d += 1;
  const t = timeMs * .001;
  if (tankRows.length > 0) {
    const idx = Math.floor((t * 3) % tankRows.length);
    update3d(tankRows[idx], t);
  }
  if (tankRoot && !drag.active) {
    tankRoot.rotation.y = drag.yaw + Math.sin(t * .22) * .045;
  }
  renderer3d.render(scene3d, camera3d);
}

window.addEventListener('fishtank:result', event => {
  tankRows = Array.isArray(event.detail?.timeseries) ? event.detail.timeseries : [];
  if (tankRows.length) update3d(tankRows[0], performance.now() * .001);
});
window.addEventListener('fishtank:agents', event => {
  updateAgentFish3d(event.detail?.agents);
});

init3d();
