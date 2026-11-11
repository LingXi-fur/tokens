// Mountain-side camera trajectory. Pure data + geometry checks, no three.js.
// The flight enters from the southwest shoulder of the massif at summit height,
// rides the west flank (foreground boulders/stunted trees occlude the frame),
// then descends south of the toe along the road into the village plain.
import { terrainHeight, terrainVisible, villageSite } from './terrain.js';

export const CAMERA_POINTS = Object.freeze([
  [-31, 23, -31], [-27, 25, -18], [-22, 29, -8], [-18, 26, 0], [-9, 16, 12], [14, 8, 18]
].map(point => Object.freeze(point.slice())));
export const TARGET_POINTS = Object.freeze([
  [-4, 35, -15], [-8, 33, -14], [-8, 28, -9], [-4, 28, -2], [0, 25.5, 2], [-2, 6, 15]
].map(point => Object.freeze(point.slice())));
// Narrow viewports pull the camera back from the origin and soften the x swing.
export const MOBILE_SCALE = 1.14, MOBILE_X = 0.8;

// Uniform Catmull-Rom, shared by rendering and pure trajectory checks.
export function curvePoint(points, u) {
  const n = points.length - 1, s = Math.min(Math.max(u, 0), 1) * n;
  const k = Math.min(n - 1, Math.floor(s)), f = s - k;
  const P = i => points[Math.max(0, Math.min(n, i))];
  const a = P(k - 1), b = P(k), c = P(k + 1), d = P(k + 2), out = [0, 0, 0];
  for (let j = 0; j < 3; j++) {
    const v0 = (c[j] - a[j]) / 2, v1 = (d[j] - b[j]) / 2;
    out[j] = b[j] * (2 * f ** 3 - 3 * f * f + 1) + v0 * (f ** 3 - 2 * f * f + f)
      + c[j] * (-2 * f ** 3 + 3 * f * f) + v1 * (f ** 3 - f * f);
  }
  return out;
}
export function cameraAt(u, mobile = false) {
  const p = curvePoint(CAMERA_POINTS, u);
  return mobile ? [p[0] * MOBILE_X * MOBILE_SCALE, p[1] * MOBILE_SCALE, p[2] * MOBILE_SCALE] : p;
}
export function targetAt(u) { return curvePoint(TARGET_POINTS, u); }

// Trajectory contract shared by tests and (indirectly) by scene framing:
// camera and look-at stay above the shared triangle surface, every sampled
// look-at ray reaches its target unblocked by terrain, the camera never dips
// into a house volume, and shot distance stays in a sane band.
export function validateTrajectory({ samples = 160, cameraClearance = 4,
  targetClearance = 0.5, houseMargin = 3.1, houseRoof = 3.6, minDistance = 6, maxDistance = 36 } = {}) {
  const sites = Array.from({ length: 24 }, (_, i) => villageSite(i));
  const result = { cameraClearance: Infinity, targetClearance: Infinity, occluded: 0,
    houseHits: 0, minDistance: Infinity, maxDistance: 0, failures: [] };
  for (let i = 0; i <= samples; i++) {
    const u = i / samples;
    for (const mobile of [false, true]) {
      const p = cameraAt(u, mobile), q = targetAt(u);
      const tag = `u=${u.toFixed(3)}${mobile ? ' mobile' : ''}`;
      result.cameraClearance = Math.min(result.cameraClearance, p[1] - terrainHeight(p[0], p[2]));
      result.targetClearance = Math.min(result.targetClearance, q[1] - terrainHeight(q[0], q[2]));
      if (p[1] - terrainHeight(p[0], p[2]) < cameraClearance) result.failures.push(`camera below clearance at ${tag}`);
      if (q[1] - terrainHeight(q[0], q[2]) < targetClearance) result.failures.push(`target under terrain at ${tag}`);
      if (!terrainVisible(p, q)) { result.occluded++; result.failures.push(`look-at blocked by terrain at ${tag}`); }
      const distance = Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
      result.minDistance = Math.min(result.minDistance, distance);
      result.maxDistance = Math.max(result.maxDistance, distance);
      if (distance < minDistance || distance > maxDistance) result.failures.push(`shot distance ${distance.toFixed(1)} at ${tag}`);
      for (const site of sites) {
        const flat = Math.hypot(p[0] - site.position[0], p[2] - site.position[1]);
        if (flat < houseMargin && p[1] < terrainHeight(site.position[0], site.position[1]) + houseRoof) {
          result.houseHits++; result.failures.push(`camera near house at ${tag}`); break;
        }
      }
    }
  }
  return result;
}
