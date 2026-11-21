// Deterministic terrain. Rendering, roads and objects share this triangle surface.
export const GRID = Object.freeze({ minX: -38, maxX: 38, minZ: -42, maxZ: 38, nx: 96, nz: 128 });
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const smooth = v => v * v * (3 - 2 * v);
export function hash(x, z, seed = 73) {
  let h = Math.imul(x | 0, 374761393) ^ Math.imul(z | 0, 668265263) ^ seed;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
export function noise(x, z) {
  const ix = Math.floor(x), iz = Math.floor(z), u = smooth(x - ix), v = smooth(z - iz);
  const a = hash(ix, iz), b = hash(ix + 1, iz), c = hash(ix, iz + 1), d = hash(ix + 1, iz + 1);
  return (a + (b - a) * u) * (1 - v) + (c + (d - c) * u) * v;
}
function fbm(x, z) {
  let value = 0, amplitude = 0.55;
  for (let octave = 0; octave < 4; octave++) {
    value += (noise(x, z) * 2 - 1) * amplitude;
    x = x * 2.07 + 13.2; z = z * 2.07 - 7.8; amplitude *= 0.47;
  }
  return value;
}
// Sharpened ridged noise: 0 in valleys, 1 on ridge crests, squared for crested silhouettes.
function ridged(x, z) {
  const r = 1 - Math.abs(fbm(x, z));
  return r * r;
}
// Soft staircase: quantises v into step-sized benches with rounded risers.
function terrace(v, step, blend) {
  const q = Math.floor(v / step), f = (v - q * step) / step;
  return (q + smooth(clamp((f - 0.5) / blend + 0.5))) * step;
}
export function roadX(z) { return 1.6 + Math.sin(z * 0.13) * 3.2 + Math.sin(z * 0.31) * 0.65; }
// Massif anchor: the summit sits near (-4, -16); the ridge runs NE-SW with a
// steeper headwall toward the village side and a long shoulder to the southwest.
function sourceHeight(x, z) {
  const warp = fbm(x * 0.06, z * 0.06) * 2.4;
  const wx = x + 4 + warp * 0.8, wz = z + 16 + warp * 0.5;
  const across = wx / 30, along = wz / 30;
  const core = Math.exp(-(across * across * 2.1 + along * along * 0.62 + Math.max(0, across) * along * 0.5));
  const crest = ridged(x * 0.13 + warp * 0.3, z * 0.11);
  let mountain = 26 * Math.pow(core, 1.12) * (0.6 + 0.4 * crest);
  // Rock-strata benches on the mid flanks only: shoulders stay walkable ledges,
  // the summit keeps its crest and the village plain is never benched.
  const flank = smooth(clamp((mountain - 1.2) / 5)) * (1 - smooth(clamp((mountain - 15) / 8)));
  mountain = mountain * (1 - flank * 0.6) + terrace(mountain, 3.4, 0.4) * flank * 0.6;
  // Talus apron so the massif roots into the land instead of sitting like a bun.
  const apron = 5.5 * Math.exp(-Math.pow((wx * wx) / 900 + (wz * wz) / 520, 0.8));
  const east = 7 * Math.exp(-((x - 21) ** 2 / 100 + (z + 21) ** 2 / 230)) * (0.75 + 0.25 * crest);
  const west = 9 * Math.exp(-((x + 26) ** 2 / 130 + (z + 9) ** 2 / 270)) * (0.75 + 0.25 * crest);
  const village = smooth(clamp((z - 1.5) / 5));
  const relief = fbm(x * 0.16, z * 0.16) * (1 - village * 0.87) * (1 - flank * 0.85);
  let height = 0.7 + mountain + apron + east + west + relief
    + 1.5 * Math.exp(-(x * x / 540 + z * z / 650)) + (1 - village) * fbm(x * 0.52, z * 0.43) * core * 0.6 * (1 - flank * 0.85);
  // Village bench: a firm gentle plain under the houses and road approach.
  const flat = village * smooth(clamp((20 - Math.abs(x - 0.5)) / 6));
  const base = 1.25 + fbm(x * 0.05, z * 0.05) * 0.5;
  return height * (1 - flat * 0.94) + base * flat * 0.94;
}
const dx = (GRID.maxX - GRID.minX) / GRID.nx, dz = (GRID.maxZ - GRID.minZ) / GRID.nz;
const heights = new Float64Array((GRID.nx + 1) * (GRID.nz + 1));
for (let j = 0; j <= GRID.nz; j++) for (let i = 0; i <= GRID.nx; i++) {
  heights[j * (GRID.nx + 1) + i] = sourceHeight(GRID.minX + i * dx, GRID.minZ + j * dz);
}
function cell(x, z) {
  const gx = clamp((x - GRID.minX) / dx, 0, GRID.nx - 1e-8);
  const gz = clamp((z - GRID.minZ) / dz, 0, GRID.nz - 1e-8);
  const i = Math.floor(gx), j = Math.floor(gz), k = j * (GRID.nx + 1) + i;
  return { u: gx - i, v: gz - j, a: heights[k], b: heights[k + 1], c: heights[k + GRID.nx + 1], d: heights[k + GRID.nx + 2] };
}
export function terrainHeight(x, z) {
  const { u, v, a, b, c, d } = cell(x, z);
  return u + v <= 1 ? a + (b - a) * u + (c - a) * v : d + (c - d) * (1 - u) + (b - d) * (1 - v);
}
export function surface(x, z) {
  const { u, v, a, b, c, d } = cell(x, z);
  const sx = (u + v <= 1 ? b - a : d - c) / dx;
  const sz = (u + v <= 1 ? c - a : d - b) / dz;
  const length = Math.hypot(sx, 1, sz);
  return { height: terrainHeight(x, z), slope: Math.hypot(sx, sz), normal: [-sx / length, 1 / length, -sz / length] };
}
export function biome(x, z) {
  const { height, slope } = surface(x, z);
  const snow = smooth(clamp((height - 14.5 + noise(x * 0.4, z * 0.4) * 1.2 - slope * 1.6) / 3));
  const rock = smooth(clamp((slope - 0.35) / 0.75)) * (1 - snow);
  return { snow, rock, grass: 1 - snow - rock };
}
export function terrainMesh() {
  const positions = [], indices = [], uvs = [];
  for (let j = 0; j <= GRID.nz; j++) for (let i = 0; i <= GRID.nx; i++) {
    positions.push(GRID.minX + i * dx, heights[j * (GRID.nx + 1) + i], GRID.minZ + j * dz);
    uvs.push(i * dx / 3, j * dz / 3);
  }
  for (let j = 0; j < GRID.nz; j++) for (let i = 0; i < GRID.nx; i++) {
    const a = j * (GRID.nx + 1) + i, b = a + 1, c = a + GRID.nx + 1, d = c + 1;
    indices.push(a, c, b, b, c, d);
  }
  return { positions, indices, uvs };
}
// Piecewise-affine height along a segment has extrema at triangle edges. Check
// every crossed x/z grid edge and diagonal, rather than undersampling a ridge.
export function terrainVisible(from, to, clearance = 0.025) {
  const vx = to[0] - from[0], vy = to[1] - from[1], vz = to[2] - from[2];
  const crossings = [0, 1];
  for (const [start, delta, min, step, count] of [[from[0], vx, GRID.minX, dx, GRID.nx], [from[2], vz, GRID.minZ, dz, GRID.nz]]) {
    if (Math.abs(delta) < 1e-10) continue;
    const low = Math.max(0, Math.ceil((Math.min(start, start + delta) - min) / step));
    const high = Math.min(count, Math.floor((Math.max(start, start + delta) - min) / step));
    for (let i = low; i <= high; i++) { const t = (min + i * step - start) / delta; if (t > 0 && t < 1) crossings.push(t); }
  }
  crossings.sort((a, b) => a - b);
  const checks = [...crossings];
  for (let k = 1; k < crossings.length; k++) {
    const lo = crossings[k - 1], hi = crossings[k], mid = (lo + hi) / 2;
    const x = from[0] + vx * mid, z = from[2] + vz * mid;
    if (x < GRID.minX || x > GRID.maxX || z < GRID.minZ || z > GRID.maxZ) continue;
    const i = Math.min(GRID.nx - 1, Math.floor((x - GRID.minX) / dx));
    const j = Math.min(GRID.nz - 1, Math.floor((z - GRID.minZ) / dz));
    const denom = vx / dx + vz / dz;
    if (Math.abs(denom) > 1e-10) {
      const t = (1 + i + j - (from[0] - GRID.minX) / dx - (from[2] - GRID.minZ) / dz) / denom;
      if (t > lo && t < hi) checks.push(t);
    }
  }
  return checks.every(t => {
    const x = from[0] + vx * t, z = from[2] + vz * t;
    return x < GRID.minX || x > GRID.maxX || z < GRID.minZ || z > GRID.maxZ
      || from[1] + vy * t >= terrainHeight(x, z) + clearance;
  });
}
const sites = [];
for (let attempt = 0; sites.length < 24 && attempt < 10000; attempt++) {
  const x = -11 + hash(attempt, 7) * 23, z = 9 + hash(attempt, 11) * 17;
  if (Math.abs(x - roadX(z)) < 2.2 || surface(x, z).slope > 0.32) continue;
  if (sites.some(site => Math.hypot(site.position[0] - x, site.position[1] - z) < 3.05)) continue;
  sites.push(Object.freeze({ position: Object.freeze([x, z]), rotation: Math.atan2(roadX(z) - x, 0.9) }));
}
if (sites.length !== 24) throw new Error('Cannot place village without overlap');
export function villageSite(slot) { return sites[slot]; }
export function roadPoint(z) { const x = roadX(z); return [x, terrainHeight(x, z) + 0.045, z]; }
