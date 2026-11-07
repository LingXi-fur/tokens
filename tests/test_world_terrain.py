"""Pure terrain contracts, run without browser, private data or asset loading."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestWorldTerrain(unittest.TestCase):
    def run_js(self, body):
        terrain = (ROOT / "ui/world/terrain.js").as_uri()
        script = f"import assert from 'node:assert/strict'; import * as t from {terrain!r};\n" + body
        result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[:4000])

    def test_mesh_height_and_normals(self):
        self.run_js("""
const data=t.terrainMesh(), g=t.GRID, dx=(g.maxX-g.minX)/g.nx, dz=(g.maxZ-g.minZ)/g.nz;
assert.equal(data.positions.length,(g.nx+1)*(g.nz+1)*3);
assert.equal(data.indices.length,g.nx*g.nz*6);
for(let j=0;j<g.nz;j+=7)for(let i=0;i<g.nx;i+=7){
  const k=(j*(g.nx+1)+i)*3, a=data.positions[k+1], b=data.positions[k+4], c=data.positions[k+3*(g.nx+1)+1], d=data.positions[k+3*(g.nx+2)+1];
  for(const [u,v] of [[.2,.3],[.7,.8]]){
    const x=g.minX+(i+u)*dx,z=g.minZ+(j+v)*dz;
    const expected=u+v<=1?a+(b-a)*u+(c-a)*v:d+(c-d)*(1-u)+(b-d)*(1-v);
    assert.ok(Math.abs(t.terrainHeight(x,z)-expected)<1e-10);
    const s=t.surface(x,z); assert.ok(Number.isFinite(s.height)&&Number.isFinite(s.slope));
    assert.ok(Math.abs(Math.hypot(...s.normal)-1)<1e-10);
    const biome=t.biome(x,z); assert.ok(Math.abs(biome.snow+biome.rock+biome.grass-1)<1e-10);
  }
}
assert.deepEqual(t.terrainMesh(),data);
""")

    def test_sites_roads_and_foundations(self):
        self.run_js("""
const sites=Array.from({length:24},(_,i)=>t.villageSite(i));
for(let i=0;i<sites.length;i++){
 const s=sites[i], [x,z]=s.position;
 assert.deepEqual(s,t.villageSite(i)); assert.ok(t.surface(x,z).slope<.32);
 assert.ok(Math.abs(x-t.roadX(z))>=2.2);
 for(let j=i+1;j<sites.length;j++)assert.ok(Math.hypot(x-sites[j].position[0],z-sites[j].position[1])>=3.05);
 const corners=[[-.78,-.73],[.78,-.73],[-.78,.73],[.78,.73]].map(([px,pz])=>t.terrainHeight(x+px*Math.cos(s.rotation)+pz*Math.sin(s.rotation),z-px*Math.sin(s.rotation)+pz*Math.cos(s.rotation)));
 const origin=Math.max(...corners)-.07;
 assert.ok(origin-.30<Math.min(...corners)); assert.ok(origin+.36>Math.max(...corners));
}
for(let z=-18;z<31;z+=.13){const p=t.roadPoint(z);assert.ok(Math.abs(p[1]-t.terrainHeight(p[0],p[2])-.045)<1e-10);}
""")

    def test_occlusion_crosses_ridges_and_small_triangles(self):
        self.run_js("""
assert.equal(t.terrainVisible([-5,8,-32],[-5,8,1]),false);
assert.equal(t.terrainVisible([-5,40,-32],[-5,40,1]),true);
assert.equal(t.terrainVisible([0,10,18],[0,3,18]),true);
assert.equal(t.terrainVisible([0,10,18],[0,0,18]),false);
// Reference oversamples only tests; production checks every triangle boundary.
for(let i=0;i<50;i++){
 const a=[-30+t.hash(i,61)*60,3+t.hash(i,62)*20,-32+t.hash(i,63)*60];
 const b=[-30+t.hash(i,64)*60,3+t.hash(i,65)*20,-32+t.hash(i,66)*60];
 let reference=true;
 for(let j=0;j<=2500;j++){const u=j/2500,x=a[0]+(b[0]-a[0])*u,y=a[1]+(b[1]-a[1])*u,z=a[2]+(b[2]-a[2])*u;if(y<t.terrainHeight(x,z)+.025){reference=false;break;}}
 assert.equal(t.terrainVisible(a,b),reference);
}
""")

    def test_draped_paths_and_entrance_clearance(self):
        paths = (ROOT / 'ui/world/paths.js').as_uri()
        self.run_js(f"""
const {{drapeRibbon,entrancePoints}}=await import({paths!r});
const road=Array.from({{length:145}},(_,i)=>{{const z=-18+i*.34;return[t.roadX(z),z]}});
const surfaces=[drapeRibbon(road,.72)];
for(let i=0;i<24;i++){{
 const site=t.villageSite(i), points=entrancePoints(site.position,site.rotation), data=drapeRibbon(points,.35);surfaces.push(data);
 for(let j=0;j<24;j++){{if(i===j)continue;const other=t.villageSite(j);
  for(const [x,z] of points){{
   const lx=(x-other.position[0])*Math.cos(other.rotation)-(z-other.position[1])*Math.sin(other.rotation);
   const lz=(x-other.position[0])*Math.sin(other.rotation)+(z-other.position[1])*Math.cos(other.rotation);
   assert.ok(Math.abs(lx)>.98||Math.abs(lz)>.93,'entrance crosses neighboring foundation');
  }}
 }}
}}
for(const data of surfaces)for(let i=0;i<data.indices.length;i+=3){{
 const vertices=data.indices.slice(i,i+3).map(k=>data.positions.slice(k*3,k*3+3));
 for(const [u,v] of [[.2,.3],[.6,.1],[1/3,1/3]]){{
  const point=[0,1,2].map(k=>vertices[0][k]*u+vertices[1][k]*v+vertices[2][k]*(1-u-v));
  assert.ok(Math.abs(point[1]-t.terrainHeight(point[0],point[2])-.035)<1e-7,'ribbon not coplanar with terrain face');
 }}
}}
""")

    def test_original_texture_channels_and_disposal(self):
        material = (ROOT / "ui/world/materials.js").as_uri()
        self.run_js(f"""
const {{texturePixels,createMaterials}}=await import({material!r});
assert.deepEqual(texturePixels('stone',16),texturePixels('stone',16));
const pixels=texturePixels('wood',16); assert.notDeepEqual(pixels.color,pixels.roughness);
for(const key of ['color','roughness','normal']){{
 assert.equal(pixels[key].length,16*16*4);
 for(let i=0;i<16;i++){{
  assert.deepEqual(pixels[key].slice(i*16*4,i*16*4+4),pixels[key].slice((i*16+15)*4,(i*16+16)*4));
  assert.deepEqual(pixels[key].slice(i*4,i*4+4),pixels[key].slice((15*16+i)*4,(15*16+i+1)*4));
 }}
}}
const p=createMaterials();assert.equal(p.textures.size,6);
// Crowns use instanceColor; their base geometry has no vertex color attribute.
assert.equal(p.leaves.vertexColors,false);
let disposed=0;for(const texture of p.textures)texture.addEventListener('dispose',()=>disposed++);
assert.equal(p.ground.map.colorSpace,'srgb');assert.equal(p.ground.normalMap.colorSpace,'');assert.equal(p.ground.roughnessMap.colorSpace,'');
p.dispose();assert.equal(disposed,6);assert.equal(p.textures.size,0);assert.equal(p.materials.size,0);
""")

    def test_camera_trajectory_contract(self):
        camera = (ROOT / "ui/world/camera.js").as_uri()
        self.run_js(f"""
const {{validateTrajectory,cameraAt,targetAt,CAMERA_POINTS,TARGET_POINTS}}=await import({camera!r});
assert.equal(CAMERA_POINTS.length,6);
// Uniform Catmull-Rom endpoints reproduce control points exactly.
assert.deepEqual(cameraAt(0),CAMERA_POINTS[0].slice());
assert.deepEqual(targetAt(1),TARGET_POINTS[5].slice());
const r=validateTrajectory();
for(const key of ['cameraClearance','targetClearance','minDistance','maxDistance'])
 assert.ok(Number.isFinite(r[key]),key);
assert.equal(r.failures.length,0,r.failures.slice(0,5));
assert.equal(r.occluded,0); assert.equal(r.houseHits,0);
assert.ok(r.cameraClearance>=4); assert.ok(r.targetClearance>=0.5);
assert.ok(r.minDistance>=6); assert.ok(r.maxDistance<=36);
""")

    def test_asset_manifest_integrity(self):
        textures = (ROOT / "ui/world/assets/textures.js").as_uri()
        manifest = ROOT / "ui/world/assets/manifest.json"
        script = f"""
const {{ROCK_CLIFF,GROUND_ROCKY,ASSET_SOURCES}}=await import({textures!r});
const crypto=(await import('node:crypto')).default;
const byExport=Object.fromEntries(ASSET_SOURCES.map(s=>[s.export,s]));
let total=0;
for(const [sources,exported] of [[byExport.ROCK_CLIFF,ROCK_CLIFF],[byExport.GROUND_ROCKY,GROUND_ROCKY]]){{
 assert.equal(sources.license.slice(0,4),'CC0 ');
 for(const name of ['albedo','normal']){{
  const uri=exported[name], expected=sources.maps[name];
  assert.ok(uri.startsWith('data:image/jpeg;base64,'));
  const bytes=Buffer.from(uri.split(',')[1],'base64');
  total+=bytes.length;
  assert.equal(bytes.length,expected.bytes);
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),expected.sha256);
  assert.equal(expected.width,1024); assert.equal(expected.height,1024); assert.equal(expected.channels,'RGB');
 }}
}}
// Bundled inline payload stays within the approved HTML inline budget.
assert.ok(total<=8*1024*1024,total);
assert.ok(ASSET_SOURCES.length===2);
"""
        import json
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        budget = manifest_data["budget"]
        self.assertLessEqual(budget["downloadedBytes"], budget["maxDownloadBytes"])
        self.run_js(script)

    def test_materials_upgrade_guards_and_cancellation(self):
        material = (ROOT / "ui/world/materials.js").as_uri()
        self.run_js(f"""
const {{createMaterials}}=await import({material!r});
const p=createMaterials();
// Node has no createImageBitmap: the upgrade must decline, keep the
// procedural set intact and report not-upgraded.
let disposed=0;for(const texture of p.textures)texture.addEventListener('dispose',()=>disposed++);
const result=await p.upgradeReal();
assert.equal(result,false); assert.equal(p.upgraded,false);
assert.equal(p.textures.size,6); assert.equal(disposed,0);
// Dispose during pending upgrade: declines again and never leaks or rejects.
p.dispose();
assert.equal(await p.upgradeReal(),false);
assert.equal(p.textures.size,0); assert.equal(p.materials.size,0);
// A second createMaterials call is a fresh, complete procedural set.
const q=createMaterials(); assert.equal(q.textures.size,6); q.dispose();
""")

    def test_massif_silhouette_and_landings(self):
        self.run_js("""
// Summit: tall enough to read as a massif, inside the mesh budget band.
let peak=0,peakAt=null;
for(let x=t.GRID.minX;x<=t.GRID.maxX;x+=.5)for(let z=t.GRID.minZ;z<=t.GRID.maxZ;z+=.5){
 const h=t.terrainHeight(x,z); if(h>peak){peak=h;peakAt=[x,z];}
}
assert.ok(peak>30&&peak<36,peak); assert.ok(peakAt[0]<8&&peakAt[0]>-12&&peakAt[1]<-8&&peakAt[1]>-24);
// Village bench: flat enough for houses and approach road on the shared surface.
for(const site of Array.from({length:24},(_,i)=>t.villageSite(i))){
 assert.ok(t.terrainHeight(...site.position)<6);
 assert.ok(t.surface(...site.position).slope<=.32);
}
// Strata benches exist on mid flanks: along the west ridge the height holds
// flat over multiple consecutive samples (staircase treads), which a smooth
// dome or pure fbm slope never produces.
let benches=0,run=0,last=t.terrainHeight(-16,-26);
for(let z=-26;z<-8;z+=.25){
 const h=t.terrainHeight(-16,z);
 run=Math.abs(h-last)<.022?run+1:0;
 if(run===3)benches++;
 last=h;
}
assert.ok(benches>=2,benches);
// Snowline above the treeline, below the summit.
assert.ok(t.biome(peakAt[0],peakAt[1]).snow>.5);
assert.ok(t.biome(0,20).snow===0||t.biome(0,20).snow<.05);
""")


if __name__ == "__main__":
    unittest.main()
