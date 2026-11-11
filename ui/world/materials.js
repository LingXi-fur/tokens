import * as THREE from 'three';
import { hash, noise } from './terrain.js';
import { ROCK_CLIFF, GROUND_ROCKY } from './assets/textures.js';

// Original local textures; no canvas image decoding, assets or network requests.
export function texturePixels(kind, size = 256) {
  const color = new Uint8Array(size * size * 4), normal = new Uint8Array(size * size * 4);
  const roughness = new Uint8Array(size * size * 4), heights = new Float32Array(size * size);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const period = size - 1;
    const grain = hash(x % period, y % period, kind === 'wood' ? 19 : 83);
    const u = x / period, v = y / period;
    const broad = noise(x / 17, y / 17) * (1 - u) * (1 - v) + noise((x - period) / 17, y / 17) * u * (1 - v)
      + noise(x / 17, (y - period) / 17) * (1 - u) * v + noise((x - period) / 17, (y - period) / 17) * u * v;
    const h = kind === 'wood' ? 0.5 + Math.sin(u * Math.PI * 28 + broad * 4) * 0.16 + grain * 0.15
      : broad * 0.6 + grain * 0.4;
    heights[y * size + x] = h;
    const index = (y * size + x) * 4, shade = Math.round(185 + h * 52);
    color.set([shade, shade, shade, 255], index);
    const r = Math.round((kind === 'wood' ? 0.76 : 0.88) * 255 + grain * 13);
    roughness.set([r, r, r, 255], index);
  }
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const period = size - 1, px = x % period, py = y % period;
    const sx = (heights[py * size + (px + 1) % period] - heights[py * size + (px + period - 1) % period]) * 0.7;
    const sy = (heights[((py + 1) % period) * size + px] - heights[((py + period - 1) % period) * size + px]) * 0.7;
    const len = Math.hypot(sx, sy, 1), index = (y * size + x) * 4;
    normal.set([Math.round((0.5 - sx / len * 0.5) * 255), Math.round((0.5 - sy / len * 0.5) * 255), Math.round((0.5 + 0.5 / len) * 255), 255], index);
  }
  return { color, normal, roughness };
}
export function createMaterials(renderer = null) {
  const textures = new Set(), materials = new Set();
  let upgraded = false, disposed = false;
  function maps(kind) {
    const pixels = texturePixels(kind), result = {};
    for (const [key, bytes] of Object.entries(pixels)) {
      const texture = new THREE.DataTexture(bytes, 256, 256, THREE.RGBAFormat);
      texture.colorSpace = key === 'color' ? THREE.SRGBColorSpace : THREE.NoColorSpace;
      texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
      texture.magFilter = THREE.LinearFilter;
      texture.minFilter = THREE.LinearMipmapLinearFilter;
      texture.generateMipmaps = true; texture.needsUpdate = true;
      textures.add(texture);
      result[key === 'color' ? 'map' : key === 'normal' ? 'normalMap' : 'roughnessMap'] = texture;
    }
    return result;
  }
  const stone = maps('stone'), wood = maps('wood');
  function material(color, extra = {}) {
    const value = new THREE.MeshStandardMaterial({ color, roughness: 0.9, ...extra });
    materials.add(value); return value;
  }
  const ground = material(0xffffff, { ...stone, vertexColors: true, normalScale: new THREE.Vector2(0.3, 0.3) });
  const building = material(0xffffff, { ...stone, vertexColors: true, normalScale: new THREE.Vector2(0.12, 0.12) });
  const timber = material(0x685342, { ...wood, normalScale: new THREE.Vector2(0.2, 0.2) });
  const rock = material(0x797973, { ...stone, normalScale: new THREE.Vector2(0.45, 0.45) });
  const roofs = [0x665d55, 0x596466, 0x756457].map(color => material(color, { ...stone, normalScale: new THREE.Vector2(0.15, 0.15) }));
  const leaves = material(0xffffff);
  const windowMaterial = material(0xf3cd86, { emissive: 0xffbd66, emissiveIntensity: 0.12, roughness: 0.35 });
  // Decode one CC0 map from its bundled data URI into a texture. flipY is
  // handled at decode time (imageOrientation) so the THREE texture keeps
  // flipY=false consistently with the procedural DataTextures.
  async function decodeTexture(uri, srgb) {
    const blob = await (await fetch(uri)).blob();
    const bitmap = await createImageBitmap(blob, { imageOrientation: 'flipY' });
    const texture = new THREE.Texture(bitmap);
    texture.flipY = false;
    texture.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.magFilter = THREE.LinearFilter;
    texture.minFilter = THREE.LinearMipmapLinearFilter;
    texture.generateMipmaps = true;
    if (renderer && renderer.capabilities) texture.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());
    texture.needsUpdate = true;
    return texture;
  }
  // Async real-texture upgrade for the two hero surfaces (terrain ground and
  // boulder/stone rock). Browser-only; any failure, or a dispose() landing
  // mid-decode, keeps the procedural set and cleans up what it allocated.
  async function upgradeReal() {
    if (upgraded || disposed) return false;
    if (typeof fetch !== 'function' || typeof createImageBitmap !== 'function') return false;
    const created = [];
    try {
      const load = async (uri, srgb) => {
        if (disposed) throw new Error('disposed');
        const texture = await decodeTexture(uri, srgb);
        if (disposed) { texture.dispose(); throw new Error('disposed'); }
        created.push(texture); return texture;
      };
      const groundMaps = { map: await load(GROUND_ROCKY.albedo, true), normalMap: await load(GROUND_ROCKY.normal, false) };
      const rockMaps = { map: await load(ROCK_CLIFF.albedo, true), normalMap: await load(ROCK_CLIFF.normal, false) };
      if (disposed) throw new Error('disposed');
      // Roughness stays procedural: it is shared with building/roof materials.
      ground.map = groundMaps.map; ground.normalMap = groundMaps.normalMap; ground.needsUpdate = true;
      rock.map = rockMaps.map; rock.normalMap = rockMaps.normalMap; rock.needsUpdate = true;
      created.forEach(texture => textures.add(texture));
      upgraded = true;
      return true;
    } catch (error) {
      created.forEach(texture => texture.dispose());
      return false;
    }
  }
  return { ground, building, timber, rock, roofs, leaves, windowMaterial,
    material, textures, materials,
    get upgraded() { return upgraded; },
    upgradeReal,
    dispose() { disposed = true; textures.forEach(texture => texture.dispose()); materials.forEach(value => value.dispose()); textures.clear(); materials.clear(); } };
}
