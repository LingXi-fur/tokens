import { GRID, terrainHeight } from './terrain.js';

function clip(polygon, a, b) {
  const side = p => (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]);
  const output = [];
  for (let i = 0; i < polygon.length; i++) {
    const p = polygon[i], q = polygon[(i + 1) % polygon.length], sp = side(p), sq = side(q);
    if (sp >= -1e-10) output.push(p);
    if ((sp > 0 && sq < 0) || (sp < 0 && sq > 0)) {
      const t = sp / (sp - sq); output.push([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]);
    }
  }
  return output;
}
// Clip each path quad to actual terrain triangles. Every resulting triangle lies
// on a single affine ground face, eliminating interpolation through ridgelines.
export function drapeRibbon(points, width, lift = 0.035) {
  const pairs = points.map(([x, z], i) => {
    const next = points[Math.min(i + 1, points.length - 1)], prev = points[Math.max(0, i - 1)];
    const vx = next[0] - prev[0], vz = next[1] - prev[1], length = Math.hypot(vx, vz) || 1;
    return [-1, 1].map(sign => [x + vz / length * width * sign / 2, z - vx / length * width * sign / 2]);
  });
  const positions = [], indices = [], uvs = [];
  const dx = (GRID.maxX - GRID.minX) / GRID.nx, dz = (GRID.maxZ - GRID.minZ) / GRID.nz;
  for (let k = 1; k < pairs.length; k++) {
    const quad = [pairs[k - 1][0], pairs[k][0], pairs[k][1], pairs[k - 1][1]];
    const xs = quad.map(p => p[0]), zs = quad.map(p => p[1]);
    const lowX = Math.max(0, Math.floor((Math.min(...xs) - GRID.minX) / dx));
    const highX = Math.min(GRID.nx - 1, Math.floor((Math.max(...xs) - GRID.minX) / dx));
    const lowZ = Math.max(0, Math.floor((Math.min(...zs) - GRID.minZ) / dz));
    const highZ = Math.min(GRID.nz - 1, Math.floor((Math.max(...zs) - GRID.minZ) / dz));
    for (let j = lowZ; j <= highZ; j++) for (let i = lowX; i <= highX; i++) {
      const a = [GRID.minX + i * dx, GRID.minZ + j * dz], b = [a[0] + dx, a[1]], c = [a[0], a[1] + dz], d = [a[0] + dx, a[1] + dz];
      for (const triangle of [[a, b, c], [b, d, c]]) {
        let polygon = quad;
        for (let edge = 0; edge < 3 && polygon.length; edge++) polygon = clip(polygon, triangle[edge], triangle[(edge + 1) % 3]);
        if (polygon.length < 3) continue;
        const base = positions.length / 3;
        for (const [x, z] of polygon) { positions.push(x, terrainHeight(x, z) + lift, z); uvs.push(x, z); }
        for (let v = 1; v < polygon.length - 1; v++) indices.push(base, base + v + 1, base + v);
      }
    }
  }
  return { positions, indices, uvs };
}
export function entrancePoints(position, angle) {
  return [0.85, 1.3].map(distance => [position[0] + Math.sin(angle) * distance, position[1] + Math.cos(angle) * distance]);
}
