"""Report-day, trusted-component and shared-cost contracts for synthetic world."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "ui" / "world"
CORE = ROOT / "src/tokens_cli/dashboard_assets/cost_core.js"


def builder():
    spec = importlib.util.spec_from_file_location("world_usage_builder", ROOT / "scripts/build_world_prototype.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(shutil.which("node"), "Node required for usage projection")
class TestWorldUsage(unittest.TestCase):
    def run_js(self, body, payload=None):
        source = """import assert from 'node:assert/strict';
import fs from 'node:fs'; import vm from 'node:vm';
""" + "import { buildUsageModel, reportDay } from " + json.dumps((WORLD / "usage-data.js").as_uri()) + ";\n"
        source += "vm.runInThisContext(fs.readFileSync(" + json.dumps(str(CORE)) + ", 'utf8'));\n"
        source += "const core=globalThis.CostCore, config=core.defaultConfig();\n"
        source += "const fixture=" + json.dumps(payload) + ";\n" + body
        result = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_report_date_not_last_row_or_machine_date(self):
        self.run_js("""
const p={generated:'2026-10-13T18:00:00+00:00',models:['a'],day:[
 {period:'2026-10-13',models:{a:10},model_calls:{a:2}},
 {period:'2026-10-14',models:{a:80},model_calls:{a:4}}]};
const m=buildUsageModel(p,{core,config});
assert.equal(m.date,'2026-10-13');assert.equal(m.today.total,10n);assert.equal(m.loaded.total,90n);
assert.equal(m.from,'2026-10-13');assert.equal(m.until,'2026-10-14');
assert.equal(m.today.unknownTokens,10n);assert.equal(m.today.unknownCalls,2n);
assert.equal(reportDay({generated:'2026-02-30T00:00:00Z'}),'');
assert.equal(reportDay({generated:'yesterday'}),'');
""")

    def test_no_day_zero_record_and_empty_filter_are_distinct(self):
        self.run_js("""
const p={generated:'2026-10-13T00:00:00Z',models:['a'],day:[{period:'2026-10-12',models:{a:25},model_calls:{a:1}}]};
assert.equal(buildUsageModel(p,{core,config}).today.hasRows,false);
p.day.push({period:'2026-10-13',models:{a:0},model_calls:{a:1}});
const full=buildUsageModel(p,{core,config});assert.equal(full.today.hasRows,true);assert.equal(full.today.total,0n);
const empty=buildUsageModel(p,{core,config,models:[]});assert.equal(empty.today.hasRows,false);assert.equal(empty.loaded.total,0n);
assert.equal(full.loaded.total,25n);assert.equal(full.today.unknownCalls,1n);
""")

    def test_unknown_and_multiple_sources_preserved(self):
        self.run_js("""
const models=[{identity:'a',source:'one',model:'manual',hidden:false},{identity:'a',source:'two',model:'manual',hidden:false},{identity:'other',source:'three',model:'',hidden:true}];
const p={generated:'2026-10-13T00:00:00Z',models:['a','other'],day:[{period:'2026-10-13',models:{a:50,other:11},model_calls:{a:3,other:1}}],cost:{schema:1,models,components:core.parts,rows:[
 ['2026-10-13',0,[10,0,0,0,0],10,1,false],
 ['2026-10-13',1,[20,0,0,0,0],20,1,false],
 ['2026-10-13',0,[0,0,0,0,0],20,1,true],
 ['2026-10-13',2,[0,0,0,0,0],11,1,true]]}};
const m=buildUsageModel(p,{core,config}),a=m.today.entries.find(e=>e.identity==='a');
assert.equal(a.priced.length,2);assert.equal(a.tokens,50n);assert.deepEqual(a.parts,[30n,0n,0n,0n,0n]);
assert.equal(a.unknownTokens,20n);assert.equal(a.unknownCalls,1n);
const other=m.today.entries.find(e=>e.identity==='other');assert.equal(other.tokens,11n);assert.equal(other.priced.length,0);
assert.equal(m.today.unknownTokens,31n);assert.equal(m.today.total,61n);
""")

    def test_bigint_accumulation_and_trusted_components(self):
        self.run_js("""
const n=Number.MAX_SAFE_INTEGER;
const p={generated:'2026-10-13T00:00:00Z',models:['a'],day:[{period:'2026-10-13',models:{a:n},model_calls:{a:1}},{period:'2026-10-13',models:{a:n},model_calls:{a:1}}],cost:{schema:1,models:[{identity:'a',source:'one',model:'unknown',hidden:false}],components:core.parts,rows:[['2026-10-13',0,[n,0,0,0,0],n,1,false],['2026-10-13',0,[n,0,0,0,0],n,1,false]]}};
const m=buildUsageModel(p,{core,config});assert.equal(m.today.total,BigInt(n)*2n);assert.equal(m.today.parts[0],BigInt(n)*2n);assert.equal(m.today.unknownTokens,0n);
""")

    def test_synthetic_fixture_priced_pending_unknown_and_no_private_reads(self):
        module = builder()
        payload = module.synthetic_payload()
        self.run_js("""
const m=buildUsageModel(fixture,{core,config});assert.equal(m.date,'2026-10-13');assert.equal(m.from,'2026-10-01');assert.equal(m.until,'2026-10-13');
assert.ok(m.today.hasRows);assert.ok(m.today.total>0n);
assert.ok(m.loaded.cost.entries.some(e=>e.fullPriced&&e.costScaled>0n));
assert.ok(m.loaded.cost.entries.some(e=>!e.fullPriced));assert.ok(m.loaded.unknownCalls>0n);
assert.equal(m.loaded.total,m.loaded.parts.reduce((a,b)=>a+b,0n)+m.loaded.unknownTokens);
assert.equal(m.today.total,m.today.parts.reduce((a,b)=>a+b,0n)+m.today.unknownTokens);
""", payload)

    def test_missing_ledger_coverage_unknown_schema_and_hidden(self):
        self.run_js("""
const p={generated:'2026-10-13',models:['a','other'],day:[{period:'2026-10-13',models:{a:30,other:9},model_calls:{a:2,other:1}}],cost:{schema:1,components:core.parts,models:[{identity:'a',source:'one',model:'unknown',hidden:false},{identity:'other',source:'one',model:'gpt-6.1-sol',hidden:true}],rows:[['2026-10-13',0,[10,0,0,0,0],10,1,false],['2026-10-13',1,[9,0,0,0,0],9,1,false]]}};
const m=buildUsageModel(p,{core,config}),a=m.today.entries.find(e=>e.identity==='a');
assert.equal(a.unknownTokens,20n);assert.equal(a.unknownCalls,1n);
assert.ok(!m.today.entries.find(e=>e.identity==='other').priced[0].fullPriced);
p.cost.schema=99;const unsupported=buildUsageModel(p,{core,config});
assert.equal(unsupported.today.cost.supported,false);assert.equal(unsupported.today.unknownTokens,39n);assert.equal(unsupported.today.unknownCalls,3n);
""")

    def test_ledger_only_models_remain_in_cost_details(self):
        self.run_js("""
const p={generated:'2026-10-13',models:['a','b'],day:[{period:'2026-10-13',models:{a:10},model_calls:{a:1}}],cost:{schema:1,components:core.parts,
models:[{identity:'b',source:'one',model:'gpt-6.1-sol',hidden:false}],rows:[['2026-10-13',0,[20,0,0,0,0],20,1,false]]}};
const m=buildUsageModel(p,{core,config});
assert.equal(m.today.total,10n);assert.equal(m.today.entries.length,1);
const b=m.loaded.costEntries.find(e=>e.identity==='b');assert.ok(b);assert.equal(b.priced[0].tokens,20n);
assert.equal(m.loaded.costEntries.flatMap(e=>e.priced).reduce((sum,e)=>sum+e.costScaled,0n),m.loaded.cost.subtotal);
""")

    def test_invalid_descriptor_never_produces_trusted_components(self):
        self.run_js("""
const p={generated:'2026-10-13',models:['a'],day:[{period:'2026-10-13',models:{a:10},model_calls:{a:1}}],cost:{schema:1,components:core.parts,
models:[{identity:'a',source:123,model:'gpt-6.1-sol',hidden:false}],rows:[['2026-10-13',0,[10,0,0,0,0],10,1,false]]}};
const m=buildUsageModel(p,{core,config});assert.equal(m.today.cost.invalidRows,1);assert.equal(m.today.parts[0],0n);
assert.equal(m.today.unknownTokens,10n);assert.equal(m.today.unknownCalls,1n);
""")

    def test_fixture_copy_and_codex_cache_conservation(self):
        module = builder()
        record = {"date": "2026-10-13", "source": "codex", "model": "gpt-5-codex", "input": 100, "output": 20, "cache_read": 30, "cache_write": 5, "total": 125}
        original = copy.deepcopy(record)
        result = module.synthetic_records([record])[0]
        self.assertEqual(record, original)
        self.assertEqual(result["model"], "gpt-6-sol")
        self.assertEqual(result["billing"]["parts"], [70, 20, 30, 5, 0])
        record["date"] = "2026-10-02"
        self.assertNotIn("billing", module.synthetic_records([record])[0])
        record["total"] = 500
        with self.assertRaises(AssertionError):
            module.synthetic_records([record])


if __name__ == "__main__":
    unittest.main()
