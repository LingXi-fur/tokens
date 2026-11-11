import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(fileURLToPath(import.meta.url));
const threeLicense = await readFile(path.join(root, 'node_modules/three/LICENSE'), 'utf8');
const result = await build({
  entryPoints: [path.join(root, 'app.js')], bundle: true, write: false,
  format: 'iife', platform: 'browser', target: ['es2020'], minify: true,
  legalComments: 'inline', charset: 'ascii', sourcemap: false,
  banner: { js: '/* Three.js 0.186.1\n' + threeLicense + '*/' },
});
const script = result.outputFiles[0].text;
if (/<\/script/i.test(script) || /__DATA__|__STYLE__|__SCRIPT__/.test(script)) {
  throw new Error('Bundle contains unsafe inline script text or a template marker');
}
await mkdir(path.join(root, 'generated'), { recursive: true });
await writeFile(path.join(root, 'generated/world.bundle.js'), script);
console.log('world bundle generated; bytes=' + Buffer.byteLength(script));
