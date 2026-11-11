import * as THREE from 'three';
import { biome, hash, noise, roadX, surface, terrainHeight, terrainMesh, terrainVisible } from './terrain.js';
import { createMaterials } from './materials.js';
import { drapeRibbon, entrancePoints } from './paths.js';
import { cameraAt, targetAt } from './camera.js';
export { terrainHeight } from './terrain.js';

export function createWorld(container, bridge) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, innerWidth < 700 ? 1.25 : 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.info.autoReset = false;
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(40, 1, 0.1, 260);
  const palette = createMaterials(renderer), geometries = new Set(), batches = new Set();
  // Late low sun from the west rakes across the strata and the west flight flank.
  const sunlight = new THREE.DirectionalLight(0xffe8c8, 3.4);
  sunlight.position.set(-30, 26, 8); sunlight.target.position.set(0, 2, 4);
  sunlight.shadow.mapSize.set(1024, 1024);
  Object.assign(sunlight.shadow.camera, { left: -28, right: 28, top: 28, bottom: -28, near: 1, far: 95 });
  sunlight.shadow.bias = -0.0005; sunlight.shadow.normalBias = 0.045;
  scene.add(sunlight, sunlight.target);
  const skyLight = new THREE.HemisphereLight(0xc8dce7, 0x8a8168, 1.5); scene.add(skyLight);
  const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
  const anchors = new Map(), targets = new Map(), blockers = [];
  let objects = new THREE.Group(); scene.add(objects);
  let selected = null, hovered = null, progress = 0, renderedProgress = -1;
  let reduced = bridge.reduced(), dark = bridge.dark(), disposed = false, frame = 0, draws = 0, lastTime = 0;
  let projectionMs = 0, frameMs = 0;
  const parallax = new THREE.Vector2(), desiredParallax = new THREE.Vector2();
  const own = geometry => { geometries.add(geometry); return geometry; };
  function mesh(geometry, material, parent = scene, cast = false) {
    const value = new THREE.Mesh(geometry, material); parent.add(value);
    value.castShadow = cast; value.receiveShadow = true; return value;
  }
  function geometryFrom(data) {
    const geometry = own(new THREE.BufferGeometry());
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(data.positions, 3));
    if (data.uvs) geometry.setAttribute('uv', new THREE.Float32BufferAttribute(data.uvs, 2));
    geometry.setIndex(data.indices); geometry.computeVertexNormals(); return geometry;
  }
  function ribbon(points, width, material, parent = scene) {
    return mesh(geometryFrom(drapeRibbon(points, width)), material, parent);
  }
  const pathMaterial = palette.material(0xb1a28a, { side: THREE.DoubleSide });
  const matrix = new THREE.Matrix4(), dummy = new THREE.Object3D();
  function instances(geometry, material, items, arrange, cast = false) {
    const batch = new THREE.InstancedMesh(geometry, material, items.length);
    batch.castShadow = cast; batch.receiveShadow = true;
    items.forEach((item, i) => {
      dummy.position.set(0, 0, 0); dummy.rotation.set(0, 0, 0); dummy.scale.set(1, 1, 1);
      const color = arrange(item, i, dummy); dummy.updateMatrix(); batch.setMatrixAt(i, dummy.matrix);
      if (color) batch.setColorAt(i, new THREE.Color(color));
    });
    batch.instanceMatrix.needsUpdate = true; batch.computeBoundingSphere(); scene.add(batch); batches.add(batch); return batch;
  }
  const treeSites = [];
  const houseGeometryParts = {};
  const sharedParts = new Map();
  function sharedPart(key, build) {
    if (!sharedParts.has(key)) sharedParts.set(key, build());
    return sharedParts.get(key);
  }
  // ---------- staged construction ----------
  // Heavy geometry work is split into phases on macrotasks so the exact-value
  // HTML paints between them; update()/scroll() are buffered until done.
  let built = false, pendingModel = null, pendingProgress = null, phaseTimer = 0;
  let groundColors = null, groundGeometry = null, readyResolve = null;
  const readyPromise = new Promise(resolve => { readyResolve = resolve; });
  const tintStrength = () => palette.upgraded ? 0.45 : 0;
  function applyGroundTint() {
    if (!groundColors || !groundGeometry || disposed) return;
    // Mutate the live color attribute in place: replacing it with a new
    // BufferAttribute would orphan the uploaded GPU buffer.
    const attribute = groundGeometry.getAttribute('color');
    if (!attribute) return;
    for (let i = 0; i < groundColors.length; i++) attribute.array[i] = groundColors[i] + (1 - groundColors[i]) * tintStrength();
    attribute.needsUpdate = true;
  }
  function buildGround() {
    const land = terrainMesh(), grass = new THREE.Color(0x778765), rock = new THREE.Color(0x96958a), snow = new THREE.Color(0xe0e5de);
    groundColors = new Float32Array(land.positions.length);
    for (let k = 0, c = 0; k < land.positions.length; k += 3, c += 3) {
      const x = land.positions[k], z = land.positions[k + 2], mix = biome(x, z);
      const color = grass.clone().multiplyScalar(0.82 + noise(x * 0.25, z * 0.25) * 0.25);
      color.lerp(rock, mix.rock).lerp(snow, mix.snow);
      groundColors[c] = color.r; groundColors[c + 1] = color.g; groundColors[c + 2] = color.b;
    }
    groundGeometry = geometryFrom(land);
    groundGeometry.setAttribute('color', new THREE.Float32BufferAttribute(groundColors, 3));
    // The terrain receives shadows but does not cast: its 24.5k triangles
    // would re-render in the shadow pass for little visual gain (the low sun
    // lights the west flight flank directly).
    mesh(groundGeometry, palette.ground, scene, false);
    // Layered distant ridgelines: mid, far and haze bands extend the range
    // without an island edge or asset sky.
    for (const [layer, zBase, top] of [[0, -62, 22], [1, -84, 30], [2, -108, 38]]) {
      const positions = [], indices = [];
      for (let i = 0; i <= 64; i++) {
        const x = -150 + i * 4.7;
        const h = 6 + noise(i * 0.31 + layer * 23, layer * 19) * top;
        positions.push(x, -8, zBase, x, h, zBase);
        if (i < 64) { const a = i * 2; indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
      }
      mesh(geometryFrom({ positions, indices }), palette.material([0x788981, 0x84939a, 0x8fa0ab][layer], { side: THREE.DoubleSide }));
    }
  }
  function buildTrees() {
    // Lower slopes up to the treeline, including the west flank the camera rides.
    for (let i = 0; i < 900 && treeSites.length < 88; i++) {
      const x = -28 + hash(i, 2) * 53, z = -26 + hash(i, 5) * 58;
      if (terrainHeight(x, z) > 12 || surface(x, z).slope > 0.85 || Math.abs(x - roadX(z)) < 1.5) continue;
      // Leave the village clearing and its interactive houses unobstructed.
      if (z > 8 && x > -13 && x < 14) continue;
      treeSites.push({ x, z, y: terrainHeight(x, z), scale: 0.8 + hash(i, 8) * 0.55, seed: i });
    }
    // Stunted trees poke above the treeline near the massif: a living scale
    // reference against the summit, not more canopy clusters.
    for (let i = 900; i < 1400 && treeSites.length < 100; i++) {
      const x = -20 + hash(i, 3) * 28, z = -30 + hash(i, 6) * 28;
      const h = terrainHeight(x, z);
      if (h < 12 || h > 16 || surface(x, z).slope > 1.4 || Math.abs(x - roadX(z)) < 1.2) continue;
      treeSites.push({ x, z, y: h, scale: 0.35 + hash(i, 8) * 0.25, seed: i });
    }
    instances(own(new THREE.CylinderGeometry(0.07, 0.13, 1, 5)), palette.timber, treeSites, (tree, i, obj) => {
      obj.position.set(tree.x, tree.y + tree.scale * 0.9, tree.z); obj.scale.set(1, tree.scale * 1.8, 1);
      // Trunks/branches do not cast: the crowns alone carry the tree shadow.
    }, false);
    const branches = treeSites.flatMap(tree => [0, 1, 2].map(branch => ({ tree, branch })));
    instances(own(new THREE.CylinderGeometry(0.025, 0.055, 1, 5)), palette.timber, branches, ({ tree, branch }, i, obj) => {
      const angle = branch * 2.4 + hash(tree.seed, 9) * 6.28;
      obj.position.set(tree.x + Math.cos(angle) * 0.25, tree.y + (1.45 + branch * 0.2) * tree.scale, tree.z + Math.sin(angle) * 0.25);
      obj.rotation.set(Math.cos(angle) * 0.8, 0, -Math.sin(angle) * 0.8); obj.scale.set(1, tree.scale * 0.9, 1);
    }, false);
    const crowns = treeSites.flatMap(tree => Array.from({ length: 3 }, (_, branch) => ({ tree, branch })));
    instances(own(new THREE.IcosahedronGeometry(1, 1)), palette.leaves, crowns, ({ tree, branch }, i, obj) => {
      const angle = branch * 2.4 + hash(tree.seed, 9) * 6.28;
      const spread = branch === 0 ? 0 : 0.48 * tree.scale;
      obj.position.set(tree.x + Math.cos(angle) * spread, tree.y + (1.8 + branch * 0.2) * tree.scale, tree.z + Math.sin(angle) * spread);
      obj.scale.set(0.7 * tree.scale, (0.85 + hash(i, 6) * 0.5) * tree.scale, 0.64 * tree.scale); obj.rotation.y = angle;
      const color = new THREE.Color(0x3d5944).lerp(new THREE.Color(0x7a8456), hash(i, 17)); return color;
    }, true);
    for (const tree of treeSites) blockers.push({ id: null, box: new THREE.Box3(new THREE.Vector3(tree.x - 0.75, tree.y, tree.z - 0.75), new THREE.Vector3(tree.x + 0.75, tree.y + tree.scale * 3, tree.z + 0.75)) });
  }
  function buildVegetation() {
    const vegetation = [];
    for (let i = 0; i < 1650; i++) {
      const x = -19 + hash(i, 22) * 39, z = -3 + hash(i, 25) * 38;
      if (terrainHeight(x, z) > 9 || Math.abs(x - roadX(z)) < 0.7 || (z > 8 && x > -13 && x < 14)) continue;
      vegetation.push({ x, z, y: terrainHeight(x, z), seed: i });
    }
    const blade = own(new THREE.BufferGeometry());
    blade.setAttribute('position', new THREE.Float32BufferAttribute([-0.06, 0, 0, 0.05, 0.36, 0.02, 0.08, 0, 0, 0, 0, -0.06, 0.02, 0.28, 0.04, 0, 0, 0.07], 3)); blade.computeVertexNormals();
    instances(blade, palette.material(0xffffff, { side: THREE.DoubleSide }), vegetation, (plant, i, obj) => {
      obj.position.set(plant.x, plant.y, plant.z); obj.rotation.y = hash(i, 35) * 6.28; obj.scale.setScalar(0.6 + hash(i, 36));
      return new THREE.Color(0x697949).lerp(new THREE.Color(0xaca575), hash(i, 33));
    });
    instances(own(new THREE.IcosahedronGeometry(0.065, 0)), palette.material(0xffffff), vegetation.filter((_, i) => i % 5 === 0), (plant, i, obj) => {
      obj.position.set(plant.x, plant.y + 0.23, plant.z); obj.scale.set(1.3, 0.5, 1.3); return i % 3 ? 0xd0bd88 : 0xb39cab;
    });
    const stones = Array.from({ length: 64 }, (_, i) => ({ x: -28 + hash(i, 40) * 56, z: -25 + hash(i, 41) * 57, i }));
    instances(own(new THREE.IcosahedronGeometry(1, 0)), palette.rock, stones, (stone, i, obj) => {
      obj.position.set(stone.x, terrainHeight(stone.x, stone.z) + 0.08, stone.z); obj.scale.set(0.2 + hash(i, 44) * 0.5, 0.14 + hash(i, 45) * 0.4, 0.35); obj.rotation.set(0, hash(i, 46) * 6.28, 0.2);
    });
    // Foreground boulders anchor the opening frames: near-camera rock gives
    // depth layering and a hard scale cue for the massif behind them.
    const boulderGeometry = own(new THREE.IcosahedronGeometry(1, 2));
    const vertices = boulderGeometry.getAttribute('position');
    for (let i = 0; i < vertices.count; i++) {
      const px = vertices.getX(i), py = vertices.getY(i), pz = vertices.getZ(i);
      const d = 0.72 + 0.42 * noise(px * 1.9 + 31, pz * 1.6 + py * 1.4);
      vertices.setXYZ(i, px * d, py * d * 0.82, pz * d);
    }
    boulderGeometry.computeVertexNormals();
    const boulders = Array.from({ length: 12 }, (_, i) => ({
      x: [-31.5, -29, -26.5, -24, -18.5, -14, 4.8, -3.2, 6.2, -9, -20, -12][i],
      z: [-28, -22, -26, -17.5, -9, -5.5, -12, -9, -6, -13, -3, 1][i], i
    }));
    instances(boulderGeometry, palette.rock, boulders, (b, i, obj) => {
      obj.position.set(b.x, terrainHeight(b.x, b.z) - 0.25 * (0.4 + hash(i, 52) * 0.6), b.z);
      obj.scale.set(1.4 + hash(i, 53) * 1.9, 1.1 + hash(i, 54) * 1.4, 1.6 + hash(i, 55) * 1.7);
      obj.rotation.set(hash(i, 56) * 0.3, hash(i, 57) * 6.28, hash(i, 58) * 0.25);
    }, true);
    ribbon(Array.from({ length: 145 }, (_, i) => { const z = -18 + i * 0.34; return [roadX(z), z]; }), 0.72, pathMaterial);
    const halo = mesh(own(new THREE.TorusGeometry(0.95, 0.023, 5, 48)), palette.material(0xf1d697, { emissive: 0xc0a35c, emissiveIntensity: 0.2 }));
    halo.rotation.x = -Math.PI / 2; halo.visible = false;
    houseGeometryParts.halo = halo;
  }
  const phases = [buildGround, buildTrees, buildVegetation];
  function runPhases() {
    phaseTimer = 0;
    if (disposed) return;
    const step = phases.shift();
    if (!step) { finishInit(); return; }
    step();
    if (disposed) return;
    phaseTimer = setTimeout(runPhases, 0);
    invalidate();
  }
  function finishInit() {
    built = true;
    if (pendingModel) { const model = pendingModel; pendingModel = null; update(model); }
    if (pendingProgress !== null) { const value = pendingProgress; pendingProgress = null; scroll(value); }
    // Optional real-texture upgrade; the procedural set stays as fallback and
    // any failure keeps it silently rather than dropping the scene.
    palette.upgradeReal().then(upgraded => {
      if (disposed || !upgraded) return;
      applyGroundTint();
      palette.ground.normalScale.set(0.55, 0.55);
      palette.rock.normalScale.set(0.85, 0.85);
      invalidate();
    }).catch(() => {}).finally(readyResolve);
  }
  function buildHouseGeometry() {
    if (houseGeometryParts.geometry) return houseGeometryParts.geometry;
    const box = own(new THREE.BoxGeometry(1, 1, 1));
    const roof = own(new THREE.BufferGeometry());
    roof.setAttribute('position', new THREE.Float32BufferAttribute([-0.5, 0, -0.5, 0.5, 0, -0.5, 0, 0.42, -0.5, -0.5, 0, 0.5, 0.5, 0, 0.5, 0, 0.42, 0.5], 3));
    roof.setIndex([0, 2, 1, 3, 4, 5, 0, 3, 5, 0, 5, 2, 2, 5, 4, 2, 4, 1, 0, 1, 4, 0, 4, 3]); roof.computeVertexNormals();
    const pieces = [];
    const part = (geometry, color, position, scale) => pieces.push({ geometry, color, position, scale });
    part(box, 0x999183, [0, 0.03, 0], [1.55, 0.66, 1.45]);
    part(box, 0xd4c6ad, [0, 0.88, 0], [1.4, 1.12, 1.28]);
    part(roof, 0x605f59, [0, 1.43, 0], [1.72, 1.65, 1.6]);
    part(box, 0x544b40, [0, 0.74, 0.655], [0.36, 0.92, 0.07]);
    part(box, 0x746a58, [0.49, 1.78, -0.28], [0.17, 0.8, 0.19]);
    for (const x of [-0.7, 0.7]) part(box, 0x7e715b, [x, 0.9, 0.64], [0.055, 1.1, 0.055]);
    part(box, 0x7e715b, [0, 1.37, 0.655], [1.4, 0.085, 0.055]);
    for (const x of [-0.46, 0.46]) {
      part(box, 0x675948, [x, 0.99, 0.663], [0.29, 0.37, 0.045]);
      part(box, 0xd0bf8f, [x, 0.99, 0.692], [0.22, 0.28, 0.025]);
      part(box, 0x675948, [x, 0.99, 0.713], [0.023, 0.29, 0.019]);
      part(box, 0x675948, [x, 0.99, 0.713], [0.23, 0.023, 0.019]);
    }
    const positions = [], normals = [], vertexColors = [], uvs = [];
    for (const piece of pieces) {
      const data = piece.geometry.index ? piece.geometry.toNonIndexed() : piece.geometry.clone();
      matrix.compose(new THREE.Vector3(...piece.position), new THREE.Quaternion(), new THREE.Vector3(...piece.scale)); data.applyMatrix4(matrix);
      const color = new THREE.Color(piece.color), pos = data.getAttribute('position'), norm = data.getAttribute('normal'), uv = data.getAttribute('uv');
      for (let i = 0; i < pos.count; i++) {
        positions.push(pos.getX(i), pos.getY(i), pos.getZ(i)); normals.push(norm.getX(i), norm.getY(i), norm.getZ(i)); vertexColors.push(color.r, color.g, color.b); uvs.push(uv?.getX(i) || 0, uv?.getY(i) || 0);
      }
      data.dispose();
    }
    const houseGeometry = own(new THREE.BufferGeometry());
    houseGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3)); houseGeometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
    houseGeometry.setAttribute('color', new THREE.Float32BufferAttribute(vertexColors, 3)); houseGeometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
    houseGeometryParts.geometry = houseGeometry;
    houseGeometryParts.box = box; houseGeometryParts.roof = roof;
    return houseGeometry;
  }
  function register(value, id, anchor) {
    value.userData.id = id; targets.set(id, value); anchors.set(id, anchor);
  }
  function update(model) {
    if (!built) { pendingModel = model; return; }
    for (const child of objects.children) {
      if (child.isInstancedMesh) child.dispose();
      if (child.userData.dynamicGeometry) { geometries.delete(child.geometry); child.geometry.dispose(); }
    }
    scene.remove(objects); objects = new THREE.Group(); scene.add(objects); targets.clear(); anchors.clear();
    blockers.splice(treeSites.length);
    const houseGeometry = buildHouseGeometry();
    // Marker posts/spheres and their material are rebuilt every refresh of the
    // model; allocate them once and reuse across update() calls so repeated
    // rebuilds hold geometries/memory stable instead of leaking 2 per pass.
    const postGeometry = sharedPart('postGeometry', () => own(new THREE.CylinderGeometry(0.045, 0.06, 0.8, 6)));
    const markerGeometry = sharedPart('markerGeometry', () => own(new THREE.SphereGeometry(0.16, 8, 5)));
    const markerMaterial = sharedPart('markerMaterial', () => palette.material(0xd8bb75, { metalness: 0.35, roughness: 0.5 }));
    model.hotspots.forEach((item, i) => {
      const x = -6 + i * 2.3, z = -15 + Math.abs(i - 1) * 1.3, y = terrainHeight(x, z);
      const value = mesh(markerGeometry, markerMaterial, objects); value.position.set(x, y + 0.65, z); value.scale.setScalar(1.9);
      register(value, item.id, new THREE.Vector3(x, y + 1.12, z));
    });
    model.stations.forEach((item, i) => {
      const z = -3 + i * 1.5, x = roadX(z) + (i % 2 ? -0.8 : 0.8), y = terrainHeight(x, z);
      const post = mesh(postGeometry, palette.timber, objects); post.position.set(x, y + 0.4, z);
      const value = mesh(markerGeometry, markerMaterial, objects); value.position.set(x, y + 0.82, z);
      register(value, item.id, new THREE.Vector3(x, y + 1.12, z)); post.userData.id = item.id;
      targets.set(item.id + ':post', post);
    });
    const windows = new THREE.InstancedMesh(houseGeometryParts.box, palette.windowMaterial, model.houses.length * 2);
    let windowIndex = 0;
    model.houses.forEach(item => {
      const [x, z] = item.position, angle = item.rotation || 0;
      // Seat the foundation below the lowest corner while its top clears the highest.
      const corners = [[-0.78, -0.73], [0.78, -0.73], [-0.78, 0.73], [0.78, 0.73]].map(([px, pz]) => terrainHeight(x + px * Math.cos(angle) + pz * Math.sin(angle), z - px * Math.sin(angle) + pz * Math.cos(angle)));
      const y = Math.max(...corners) - 0.07;
      const value = mesh(houseGeometry, palette.building, objects, true); value.position.set(x, y, z); value.rotation.y = angle;
      register(value, item.id, new THREE.Vector3(x, y + 2.38, z)); value.updateMatrixWorld(true);
      for (const wx of [-0.46, 0.46]) {
        dummy.position.set(x + wx * Math.cos(angle) + 0.704 * Math.sin(angle), y + 0.99, z - wx * Math.sin(angle) + 0.704 * Math.cos(angle));
        dummy.rotation.set(0, angle, 0); dummy.scale.set(0.19, 0.25, 0.012); dummy.updateMatrix(); windows.setMatrixAt(windowIndex++, dummy.matrix);
      }
      blockers.push({ id: item.id, box: new THREE.Box3().setFromObject(value) });
      const path = ribbon(entrancePoints(item.position, angle), 0.35, pathMaterial, objects);
      path.userData.dynamicGeometry = true;
    });
    if (windowIndex) { windows.instanceMatrix.needsUpdate = true; windows.computeBoundingSphere(); objects.add(windows); } else windows.dispose();
    if (!anchors.has(selected)) selected = null;
    if (!anchors.has(hovered)) { hovered = null; bridge.hover(null); }
    invalidate();
  }
  function unblocked(position, id) {
    if (!terrainVisible(camera.position.toArray(), position.toArray())) return false;
    const direction = position.clone().sub(camera.position), distance = direction.length();
    const ray = new THREE.Ray(camera.position, direction.normalize()), intersection = new THREE.Vector3();
    return !blockers.some(item => item.id !== id && ray.intersectBox(item.box, intersection) && intersection.distanceTo(camera.position) < distance - 0.03);
  }
  function pick(event) {
    pointer.set(event.clientX / innerWidth * 2 - 1, 1 - event.clientY / innerHeight * 2);
    raycaster.setFromCamera(pointer, camera);
    for (const hit of raycaster.intersectObjects([...targets.values()], false)) if (unblocked(hit.point, hit.object.userData.id)) return hit.object.userData.id;
    return null;
  }
  function project() {
    const start = performance.now(), labels = [];
    for (const [id, position] of anchors) {
      const p = position.clone().project(camera);
      if (p.z > -1 && p.z < 1 && Math.abs(p.x) < 0.98 && Math.abs(p.y) < 0.96 && unblocked(position, id)) labels.push({ id, x: (p.x + 1) * innerWidth / 2, y: (1 - p.y) * innerHeight / 2 });
    }
    bridge.project(labels); projectionMs = performance.now() - start;
  }
  function render(time) {
    frame = 0; if (disposed || document.hidden) return;
    const start = performance.now(), delta = Math.min(0.05, (time - lastTime) / 1000 || 0.016); lastTime = time;
    const target = reduced ? (progress < 0.3 ? 0 : progress < 0.7 ? 0.5 : 1) : progress;
    renderedProgress = renderedProgress < 0 || reduced ? target : THREE.MathUtils.damp(renderedProgress, target, 12, delta);
    if (reduced) parallax.set(0, 0); else parallax.lerp(desiredParallax, Math.min(1, delta * 10));
    const mobile = innerWidth < 700, shot = THREE.MathUtils.clamp(renderedProgress, 0, 1);
    camera.position.set(...cameraAt(shot, mobile));
    camera.position.x += parallax.x * 0.8; camera.position.y += parallax.y * 0.45;
    camera.lookAt(...targetAt(shot)); camera.updateMatrixWorld();
    const active = anchors.get(hovered || selected); const halo = houseGeometryParts.halo;
    if (halo) { halo.visible = !!active; if (active) halo.position.set(active.x, terrainHeight(active.x, active.z) + 0.14, active.z); }
    renderer.info.reset(); renderer.render(scene, camera); draws++; project(); frameMs = performance.now() - start;
    if (Math.abs(renderedProgress - target) > 0.00015 || (!reduced && parallax.distanceTo(desiredParallax) > 0.0005)) invalidate();
  }
  function invalidate() { if (!frame && !disposed && !document.hidden) frame = requestAnimationFrame(render); }
  function resize() {
    camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight);
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, innerWidth < 700 ? 1.25 : 1.75));
    // Viewport quality policy is independent of reduced-motion preference.
    const shadows = innerWidth >= 1000;
    if (renderer.shadowMap.enabled !== shadows) palette.materials.forEach(value => { value.needsUpdate = true; });
    renderer.shadowMap.enabled = shadows; sunlight.castShadow = shadows;
    invalidate();
  }
  function theme() {
    dark = bridge.dark(); scene.background = new THREE.Color(dark ? 0x182b35 : 0xbcced4);
    scene.fog = new THREE.Fog(scene.background, dark ? 34 : 46, dark ? 130 : 170);
    renderer.toneMappingExposure = dark ? 0.8 : 1.05;
    sunlight.color.set(dark ? 0xaac5df : 0xffe8c8); sunlight.intensity = dark ? 0.75 : 3.4;
    skyLight.intensity = dark ? 0.8 : 1.5; skyLight.color.set(dark ? 0x739bb5 : 0xc8dce7);
    palette.windowMaterial.emissiveIntensity = dark ? 1.2 : 0.12; invalidate();
  }
  function motion() { reduced = bridge.reduced(); if (reduced) { parallax.set(0, 0); desiredParallax.set(0, 0); } invalidate(); }
  function scroll(value) { const next = THREE.MathUtils.clamp(value, 0, 1); if (!built) { pendingProgress = next; return; } progress = next; invalidate(); }
  function select(id) { selected = id; invalidate(); }
  function move(event) {
    if (event.pointerType === 'touch') return;
    desiredParallax.set((event.clientX / innerWidth - 0.5) * 2, (0.5 - event.clientY / innerHeight) * 2);
    const id = pick(event); if (id !== hovered) { hovered = id; bridge.hover(id); } invalidate();
  }
  function leave() { desiredParallax.set(0, 0); hovered = null; bridge.hover(null); invalidate(); }
  function visibility() { if (document.hidden) { cancelAnimationFrame(frame); frame = 0; } else { lastTime = 0; invalidate(); } }
  function lost(event) { event.preventDefault(); cancelAnimationFrame(frame); frame = 0; bridge.fail('context'); }
  renderer.domElement.addEventListener('webglcontextlost', lost); window.addEventListener('resize', resize); document.addEventListener('visibilitychange', visibility);
  resize(); theme();
  phaseTimer = setTimeout(runPhases, 0);
  return { update, select, scroll, move, leave, pick, theme, motion,
    initialize: () => readyPromise, ready: readyPromise,
    metrics: () => ({ draws, pending: !!frame, triangles: renderer.info.render.triangles, calls: renderer.info.render.calls, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures, ownedTextures: palette.textures.size, upgraded: !!palette.upgraded, shadow: renderer.shadowMap.enabled, camera: camera.position.toArray(), progress: renderedProgress, projectionMs, frameMs }),
    // Synthetic test coordinates use real mesh centers, not floating DOM anchors.
    probes: () => [...anchors].map(([id, anchor]) => { const object = targets.get(id), center = new THREE.Box3().setFromObject(object).getCenter(new THREE.Vector3()), p = center.clone().project(camera); return { id, x: (p.x + 1) * innerWidth / 2, y: (1 - p.y) * innerHeight / 2, visible: unblocked(center, id), labelVisible: unblocked(anchor, id) }; }),
    dispose() {
      if (disposed) return; disposed = true; cancelAnimationFrame(frame);
      if (phaseTimer) clearTimeout(phaseTimer);
      window.removeEventListener('resize', resize); document.removeEventListener('visibilitychange', visibility); renderer.domElement.removeEventListener('webglcontextlost', lost);
      geometries.forEach(value => value.dispose()); batches.forEach(value => value.dispose()); objects.traverse(value => { if (value.isInstancedMesh) value.dispose(); }); palette.dispose(); sunlight.shadow.dispose();
      targets.clear(); anchors.clear(); blockers.length = 0; pendingModel = null; renderer.dispose(); renderer.domElement.remove();
      readyResolve();
    }
  };
}
