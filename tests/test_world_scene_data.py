"""Synthetic-only 3D adapter and standalone build contracts."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "ui" / "world"


def builder():
    spec = importlib.util.spec_from_file_location("build_world_prototype", ROOT / "scripts" / "build_world_prototype.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(shutil.which("node"), "Node required for world adapter tests")
class TestWorldSceneData(unittest.TestCase):
    def run_js(self, body):
        source = "import assert from 'node:assert/strict'; import { buildSceneModel,stableSlot } from " + json.dumps((WORLD / "scene-data.js").as_uri()) + ";\n" + body
        result = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_empty_and_zero_selection(self):
        self.run_js("""
const empty=buildSceneModel({});assert.equal(empty.total,0);assert.equal(empty.projects.length,0);
const p={models:['a'],day:[{period:'2026-10-01',models:{a:10},model_calls:{a:2}}],day_details:{'2026-10-01':{cwds:[['demo',10,'p',{a:10}]]}}};
assert.equal(buildSceneModel(p,{models:[]}).total,0);assert.equal(buildSceneModel(p,{models:[]}).houses.length,0);
assert.equal(buildSceneModel(p,{days:[]}).total,0);
""")

    def test_filter_scope_and_aggregates(self):
        self.run_js("""
const p={models:['a','other'],day:[{period:'2026-10-02',models:{a:20,other:7},model_calls:{a:3,other:1}},{period:'2026-10-01',models:{a:10,other:5},model_calls:{a:2,other:1}}],day_details:{'2026-10-01':{cwds:[['Project-X',15,'Project-X',{a:10,other:5}]]},'2026-10-02':{cwds:[['Project-X',27,'Project-X',{a:20,other:7}]]}}};
const all=buildSceneModel(p);assert.equal(all.total,42);assert.equal(all.calls,7);assert.equal(all.projects[0].total,42);assert.deepEqual(all.projects[0].days,['2026-10-01','2026-10-02']);
const scoped=buildSceneModel(p,{models:['a'],days:['2026-10-02']});assert.equal(scoped.total,20);assert.equal(scoped.calls,3);assert.equal(scoped.projects[0].total,20);assert.deepEqual(scoped.models,['a']);assert.equal(scoped.projects[0].cost,undefined);
assert.equal(all.rows[0].period,'2026-10-01');assert.equal(scoped.houses[0].position.join(),all.houses[0].position.join());
""")

    def test_large_catalog_deterministic_and_other_private(self):
        self.run_js("""
const rows=Array.from({length:100},(_,i)=>['Project-'+i,100-i,'Project-'+i,{other:100-i}]);
const p={models:['other'],day:[],day_details:{'2026-10-01':{cwds:rows}}};
const a=buildSceneModel(p),b=buildSceneModel(p);assert.equal(a.projects.length,100);assert.ok(a.houses.length<=24);assert.deepEqual(a,b);assert.deepEqual(a.models,['other']);
assert.equal(new Set(a.houses.map(h=>h.position.join())).size,a.houses.length);assert.equal(stableSlot('Project-7'),stableSlot('Project-7'));
""")

    def test_limited_fallback_and_no_fake_identity(self):
        self.run_js("""
const p={models:['other'],day_details:{'2026-10-01':{top_cwds:[['Project-X',5,'Project-X',{other:5}]]}}};const m=buildSceneModel(p);assert.equal(m.limited,true);assert.equal(m.projects[0].total,5);assert.equal(m.projects[0].label,'Project-X');
""")

    def test_synthetic_calls_cannot_read_private_logs(self):
        module = builder()
        payload = module.synthetic_payload()
        self.assertTrue(payload["day"])
        self.assertTrue(payload["day_details"])
        self.assertTrue(all(row["period"].startswith("2026-10-") for row in payload["day"]))

    @unittest.skipUnless((WORLD / "generated" / "world.bundle.js").is_file(), "Build prototype bundle first")
    def test_inline_security_and_single_canvas_source(self):
        module = builder()
        html = module.build_html({"models": [], "day": [], "pretty": {"x": "</script><script>alert(1)</script>__STYLE__"}})
        self.assertNotIn("</script><script>alert(1)</script>", html)
        self.assertIn("\\u003c/script\\u003e", html)
        self.assertIn("__STYLE__", html)  # literal payload label, not second-pass replacement
        self.assertNotIn('<script src=', html)
        self.assertNotIn('<link href=', html)
        self.assertIn("three.js authors", html)
        self.assertEqual((WORLD / "scene.js").read_text().count("new THREE.WebGLRenderer("), 1)
        self.assertNotIn("localStorage", (WORLD / "app.js").read_text())


if __name__ == "__main__":
    unittest.main()
