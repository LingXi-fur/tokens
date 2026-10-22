"""Node-guarded tests for the shared cost core (dashboard_assets/cost_core.js).

The core is the single source of cost math shared by the production dashboard
(thin wrappers in dashboard.js) and the world prototype. These tests run the
classic-script IIFE under Node's vm with no DOM/storage/DATA: they pin the
public CostCore API, the pure-compute contracts (BigInt accumulation beyond
2^53, uncertain rows never billed, pending vs free-zero, whole-entry override
priority, non-USD reference blocking, hidden models, unknown schema,
total_incomplete, half-up rounding inputs, days/models scoping, invalid-row
accounting) and the sanitize/parse helpers. Python-side tests pin the asset
assembly order (cost_core.js concatenated before dashboard.js inside the single
<script>) so production cannot silently ship without the shared core.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CORE = SRC / "tokens_cli" / "dashboard_assets" / "cost_core.js"
DASHBOARD = SRC / "tokens_cli" / "dashboard_assets" / "dashboard.js"

import sys
sys.path.insert(0, str(SRC))

from tokens_cli import report_dashboard  # noqa: E402

HAVE_NODE = shutil.which("node") is not None
requires_node = unittest.skipUnless(HAVE_NODE, "Node.js is required for cost core contract tests")


def cost_block(rows, models, total_incomplete=None, schema=1):
    block = {
        "schema": schema,
        "components": ["input", "output", "cache_read", "cache_write", "thoughts"],
        "models": models,
        "rows": rows,
    }
    if total_incomplete is not None:
        block["total_incomplete"] = total_incomplete
    return block


def model(name, identity=None, source="synthetic", hidden=False):
    return {"source": source, "model": name, "identity": identity or name, "hidden": hidden}


USD = {"v": 1, "currency": "USD", "reference": True, "prices": {}}


def with_prices(currency="USD", reference=True, **entries):
    return {"v": 1, "currency": currency, "reference": reference, "prices": entries}


KEY = '["synthetic","model-a"]'
REF_KEY = '["openai","gpt-6.1-sol"]'

CASES = [
    # (name, cost, days, identities, config)
    ("bigint-beyond-2-53",
     # per-row values stay JS safe ints (2^53-1); BigInt exactness kicks in across rows
     cost_block([
         ["2026-07-01", 0, [9007199254740991, 9007199254740991, 0, 0, 0], 9007199254740991, 3, False],
         ["2026-07-02", 0, [9007199254740991, 0, 0, 0, 0], 9007199254740991, 2, False],
     ], [model("gpt-6.1-sol", "m", "openai")]),
     ["2026-07-01", "2026-07-02"], ["m"], USD),
    ("uncertain-rows-never-billed",
     cost_block([
         ["2026-07-01", 0, [1000, 1000, 0, 0, 0], 2000, 2, True],
         ["2026-07-01", 0, [1000, 0, 0, 0, 0], 1000, 1, False],
     ], [model("model-a")]),
     ["2026-07-01"], ["model-a"],
     with_prices(**{KEY: {"rates": ["1", "1", "1", "1", "1"], "note": ""}})),
    ("free-zero-is-priced",
     cost_block([["2026-07-01", 0, [100, 100, 0, 0, 0], 200, 1, False]], [model("model-a")]),
     ["2026-07-01"], ["model-a"],
     with_prices(**{KEY: {"rates": ["0", "0", "0", "0", "0"], "note": ""}})),
    ("pending-empty-rate",
     cost_block([["2026-07-01", 0, [100, 100, 0, 0, 0], 200, 1, False]], [model("model-a")]),
     ["2026-07-01"], ["model-a"],
     with_prices(**{KEY: {"rates": ["1", "", "", "", ""], "note": ""}})),
    ("override-beats-reference",
     cost_block([["2026-07-01", 0, [1000000, 0, 0, 0, 0], 1000000, 1, False]],
                [model("gpt-6.1-sol", "m", "openai")]),
     ["2026-07-01"], ["m"],
     with_prices(**{REF_KEY: {"rates": ["3.5", "7.25", "0.5", "1", ""], "note": "team"}})),
    ("reference-active-usd",
     cost_block([["2026-07-01", 0, [1000000, 1000000, 0, 0, 0], 2000000, 1, False]],
                [model("gpt-6.1-sol", "m", "openai")]),
     ["2026-07-01"], ["m"], USD),
    ("non-usd-blocks-reference",
     cost_block([["2026-07-01", 0, [1000000, 0, 0, 0, 0], 1000000, 1, False]],
                [model("gpt-6.1-sol", "m", "openai")]),
     ["2026-07-01"], ["m"],
     with_prices(currency="CNY")),
    ("hidden-model-never-priced",
     cost_block([["2026-07-01", 0, [100, 100, 0, 0, 0], 200, 1, False]], [model("model-a", hidden=True)]),
     ["2026-07-01"], ["model-a"], USD),
    ("unknown-schema-unsupported",
     cost_block([["2026-07-01", 0, [1, 1, 0, 0, 0], 2, 1, False]], [model("model-a")], schema=2),
     ["2026-07-01"], ["model-a"], USD),
    ("total-incomplete-blocks-full-estimate",
     cost_block([["2026-07-01", 0, [1000000, 0, 0, 0, 0], 1000000, 1, False]],
                [model("gpt-6.1-sol", "m", "openai")], total_incomplete=True),
     ["2026-07-01"], ["m"], USD),
    ("rounding-input-boundaries",
     cost_block([
         ["2026-07-01", 0, [5000000000, 0, 0, 0, 0], 5000000000, 1, False],   # scaled 5e9  -> $0.005
         ["2026-07-01", 1, [4999999999, 0, 0, 0, 0], 4999999999, 1, False],  # scaled <5e9 -> <$0.005
     ], [model("round-a"), model("round-b")]),
     ["2026-07-01"], ["round-a", "round-b"],
     with_prices(
         **{'["synthetic","round-a"]': {"rates": ["0.000001", "", "", "", ""], "note": ""},
            '["synthetic","round-b"]': {"rates": ["0.000001", "", "", "", ""], "note": ""}})),
    ("day-and-model-scope",
     cost_block([
         ["2026-07-02", 0, [9000000, 0, 0, 0, 0], 9000000, 1, False],
         ["2026-07-01", 1, [9000000, 0, 0, 0, 0], 9000000, 1, False],
         ["2026-07-01", 0, [2500000, 0, 0, 0, 0], 2500000, 1, False],
     ], [model("gpt-6.1-sol", "in", "openai"), model("gpt-6.1-sol", "out", "openai")]),
     ["2026-07-01"], ["in"], USD),
    ("invalid-rows-counted-as-unknown",
     cost_block([
         ["2026-07-01", 0],
         ["2026/07/01", 0, [1, 1, 0, 0, 0], 2, 1, False],
         ["2026-07-01", 99, [1, 1, 0, 0, 0], 2, 1, False],
         ["2026-07-01", 0, [1, 1, 0, 0, 0], 2, 1.5, False],
         ["2026-07-01", 0, [1000000, 0, 0, 0, 0], 1000000, 2, False],
     ], [model("gpt-6.1-sol", "m", "openai")]),
     ["2026-07-01"], ["m"], USD),
]

VIEW_KEYS = ["supported", "currency", "referenceCount", "totalIncomplete", "entries",
             "subtotal", "anyPriced", "fullEstimate", "pricedCount", "pendingCount",
             "pendingTokens", "totalCalls", "totalTokens", "unknownCalls", "unknownTokens",
             "invalidRows", "hasCacheWrite", "maxCost"]
ENTRY_KEYS = ["key", "model", "partSums", "activeParts", "rates", "rateTexts",
              "costScaled", "fullPriced", "hidden", "calls", "tokens", "note", "reference"]

NODE_RUNNER = r'''
const fs=require('fs');
const vm=require('vm');
const ctx={};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),ctx,{filename:'cost_core.js'});
const Core=ctx.CostCore;
const out={api:{},views:{},helpers:{},shape:{}};
for(const k of ['parts','reference','defaultConfig','sanitizeConfig','parseRate','modelKey','effectivePrice','moneyText','moneyExact','compute','sanitizeEntryRates','referenceFor'])
  out.api[k]=typeof Core[k];
const bi=(k,v)=>typeof v==='bigint'?'BigInt:'+v.toString():v;
const cases=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
for(const c of cases){
  try{
    const view=Core.compute(c.cost,{days:new Set(c.days),models:new Set(c.identities),config:c.config});
    out.views[c.name]=JSON.parse(JSON.stringify(view,bi));
  }catch(e){out.views[c.name]={threw:String(e&&e.message)};}
}
const refView=out.views['reference-active-usd'];
out.shape.view=Object.keys(refView);
out.shape.entry=Object.keys(refView.entries[0]);
out.helpers.parseRate=[
  JSON.stringify(Core.parseRate('2.5'),bi),
  JSON.stringify(Core.parseRate('x')),
  JSON.stringify(Core.parseRate('')),
  JSON.stringify(Core.parseRate('0.1234567')),
  JSON.stringify(Core.parseRate('1000000000000000.000001'))
];
out.helpers.moneyText=[
  Core.moneyText(0n,'USD',false),
  Core.moneyText(5n,'USD',true),
  Core.moneyText(1499999999999n,'USD',false),
  Core.moneyText(500000000000n,'CNY',false),
  Core.moneyText(123456789012345678n,'USD',false),
  Core.moneyText(4999999999n,'USD',false)
];
out.helpers.moneyExact=[
  Core.moneyExact(0n),
  Core.moneyExact(120000000000n),
  Core.moneyExact(123456789012n),
  Core.moneyExact(1n)
];
out.helpers.modelKey=Core.modelKey({source:'a"b',model:'c\\d'});
out.helpers.sanitizeEntryRates=[
  JSON.stringify(Core.sanitizeEntryRates(['1','','0.5','1','1'])),
  JSON.stringify(Core.sanitizeEntryRates(null)),
  JSON.stringify(Core.sanitizeEntryRates(['1','1'])),
  JSON.stringify(Core.sanitizeEntryRates(['1','x','1','1','1']))
];
out.helpers.sanitizeConfig=[
  JSON.stringify(Core.sanitizeConfig(null)),
  JSON.stringify(Core.sanitizeConfig({v:1,currency:'EUR',prices:{}})),
  JSON.stringify(Core.sanitizeConfig({v:1,currency:'USD',prices:{'["a","b"]':{rates:['1','','x','1','1'],note:''}}})),
  JSON.stringify(Core.sanitizeConfig({v:1,currency:'USD',reference:'yes',prices:{}})),
  JSON.stringify(Core.sanitizeConfig({v:1,currency:'CNY',prices:{'["a","b"]':{rates:['1','','','',''],note:'x'.repeat(200)}}}))
];
out.helpers.effectivePrice=[
  JSON.stringify(Core.effectivePrice({source:'openai',model:'gpt-6.1-sol',hidden:false},{currency:'USD',reference:true,prices:{}}),bi),
  JSON.stringify(Core.effectivePrice({source:'openai',model:'gpt-6.1-sol',hidden:true},Core.defaultConfig()),bi),
  JSON.stringify(Core.effectivePrice({source:'openai',model:'nope',hidden:false},Core.defaultConfig()),bi),
  JSON.stringify(Core.effectivePrice({source:'synthetic',model:'a',hidden:false},{currency:'USD',reference:true,prices:{'["synthetic","a"]':{rates:['1','','','',''],note:'n'}}}),bi)
];
out.helpers.defaultConfig=JSON.stringify(Core.defaultConfig());
out.helpers.referenceDate=Core.reference.date;
out.helpers.referenceVendors=Object.keys(Core.reference.vendors).join(',');
out.helpers.parts=JSON.stringify(Core.parts);
out.helpers.version=Core.VERSION;
process.stdout.write(JSON.stringify(out));
'''


class CostCoreAssetAssemblyTests(unittest.TestCase):
    """Asset-loading contract: the shared core is shipped and loaded first."""

    def test_cost_core_asset_exists_and_is_classic_script(self):
        text = CORE.read_text(encoding="utf-8")
        self.assertGreater(CORE.stat().st_size, 1000)
        self.assertIn("(function(global){", text)
        self.assertIn("global.CostCore={", text)
        self.assertNotIn("module.exports", text)
        self.assertNotIn("export ", text)
        # no storage access (the header comment names localStorage only as an excluded dep)
        self.assertNotIn("localStorage.", text)
        self.assertNotIn("localStorage[", text)

    def test_template_concatenates_core_before_dashboard(self):
        template = report_dashboard._TEMPLATE
        core_pos = template.find("global.CostCore={")
        wrap_pos = template.find("function costComputeView")
        self.assertGreater(core_pos, 0, "cost_core.js missing from assembled template")
        self.assertGreater(wrap_pos, core_pos, "cost_core.js must be concatenated before dashboard.js")
        self.assertNotIn("__SCRIPT__", template)
        self.assertNotIn("__STYLE__", template)

    def test_dashboard_keeps_thin_wrappers_and_expands_scope_itself(self):
        script = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("function costComputeView", script)
        self.assertIn("CostCore.compute(DATA.cost,{days,models:state.models,config:costPrices})", script)
        for name in ("costParseRate", "costSanitizeEntryRates", "costSanitizeConfig",
                     "costDefaultConfig", "costMoneyText", "costExactMoney",
                     "costModelKey", "costReferenceFor", "costEffectivePrice"):
            self.assertIn("function " + name + "(", script)
        # storage keys and memo stay in the production shell, not the core
        self.assertIn("tk-cost-v1", script)

    def test_assets_contain_no_closing_script_tag(self):
        for path in (CORE, DASHBOARD):
            self.assertNotIn("</script", path.read_text(encoding="utf-8"))

    def test_package_data_covers_core(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('"dashboard_assets/*.js"', text)


@requires_node
class CostCoreContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cases = [
            {"name": name, "cost": cost, "days": days, "identities": identities, "config": config}
            for name, cost, days, identities, config in CASES
        ]
        cls._tmp = tempfile.TemporaryDirectory()
        cases_path = Path(cls._tmp.name) / "cases.json"
        cases_path.write_text(json.dumps(cases), encoding="utf-8")
        runner_path = Path(cls._tmp.name) / "runner.js"
        runner_path.write_text(NODE_RUNNER, encoding="utf-8")
        proc = subprocess.run(
            ["node", str(runner_path), str(CORE), str(cases_path)],
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        cls.result = json.loads(proc.stdout)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_api_surface(self):
        expected = {k: "function" for k in
                    ("defaultConfig", "sanitizeConfig", "parseRate", "modelKey", "effectivePrice",
                     "moneyText", "moneyExact", "compute", "sanitizeEntryRates", "referenceFor")}
        expected.update({"parts": "object", "reference": "object"})
        self.assertEqual(expected, self.result["api"])
        self.assertEqual(1, self.result["helpers"]["version"])

    def test_view_and_entry_shape_is_pinned(self):
        self.assertEqual(VIEW_KEYS, self.result["shape"]["view"])
        self.assertEqual(ENTRY_KEYS, self.result["shape"]["entry"])

    def test_parts_and_reference_are_frozen_values(self):
        self.assertEqual(["input", "output", "cache_read", "cache_write", "thoughts"],
                         json.loads(self.result["helpers"]["parts"]))
        self.assertEqual("2026-10-12", self.result["helpers"]["referenceDate"])
        self.assertEqual("openai,deepseek,zai", self.result["helpers"]["referenceVendors"])

    def test_default_config(self):
        self.assertEqual({"v": 1, "currency": "USD", "reference": True, "prices": {}},
                         json.loads(self.result["helpers"]["defaultConfig"]))

    def test_bigint_accumulation_is_exact(self):
        view = self.result["views"]["bigint-beyond-2-53"]
        e = view["entries"][0]
        # 9007199254740991 + 9007199254740991 exceeds 2^53 and must stay exact
        self.assertEqual("BigInt:18014398509481982", e["partSums"][0])
        self.assertEqual("BigInt:9007199254740991", e["partSums"][1])
        self.assertEqual("BigInt:18014398509481982", e["tokens"])
        self.assertEqual("BigInt:5", e["calls"])
        # 18014398509481982*2e6 + 9007199254740991*1e7 (gpt-6.1-sol in $2 / out $10)
        self.assertEqual("BigInt:126100789566373874000000", e["costScaled"])
        self.assertTrue(view["fullEstimate"])
        self.assertTrue(e["fullPriced"])

    def test_uncertain_rows_counted_unknown_and_not_billed(self):
        view = self.result["views"]["uncertain-rows-never-billed"]
        self.assertEqual("BigInt:2", view["unknownCalls"])
        self.assertEqual("BigInt:2000", view["unknownTokens"])
        e = view["entries"][0]
        self.assertEqual("BigInt:1000", e["partSums"][0])
        self.assertEqual("BigInt:1000000000", e["costScaled"])
        self.assertTrue(e["fullPriced"])
        self.assertFalse(view["fullEstimate"])

    def test_zero_rates_are_priced_not_pending(self):
        view = self.result["views"]["free-zero-is-priced"]
        e = view["entries"][0]
        self.assertTrue(e["fullPriced"])
        self.assertEqual("BigInt:0", e["costScaled"])
        self.assertEqual(1, view["pricedCount"])
        self.assertEqual(0, view["pendingCount"])
        self.assertTrue(view["anyPriced"])

    def test_empty_rate_on_active_part_is_pending(self):
        view = self.result["views"]["pending-empty-rate"]
        e = view["entries"][0]
        self.assertFalse(e["fullPriced"])
        self.assertEqual("BigInt:0", e["costScaled"])
        self.assertEqual(1, view["pendingCount"])
        self.assertEqual("BigInt:200", view["pendingTokens"])
        self.assertEqual(0, view["pricedCount"])
        self.assertFalse(view["anyPriced"])
        self.assertFalse(view["fullEstimate"])

    def test_override_takes_priority_over_reference(self):
        e = self.result["views"]["override-beats-reference"]["entries"][0]
        self.assertEqual("team", e["note"])
        self.assertIsNone(e["reference"])
        self.assertEqual("BigInt:3500000", e["rates"][0])
        self.assertEqual("BigInt:3500000000000", e["costScaled"])

    def test_reference_used_for_usd(self):
        view = self.result["views"]["reference-active-usd"]
        e = view["entries"][0]
        self.assertIsNotNone(e["reference"])
        self.assertEqual("openai", e["reference"]["vendor"])
        self.assertEqual("", e["note"])
        self.assertEqual("BigInt:2000000", e["rates"][0])
        self.assertEqual("BigInt:12000000000000", e["costScaled"])
        self.assertEqual(1, view["referenceCount"])

    def test_non_usd_currency_blocks_reference(self):
        view = self.result["views"]["non-usd-blocks-reference"]
        self.assertEqual("CNY", view["currency"])
        self.assertFalse(view["entries"][0]["fullPriced"])
        self.assertEqual(0, view["referenceCount"])

    def test_hidden_model_entry_is_never_priced(self):
        e = self.result["views"]["hidden-model-never-priced"]["entries"][0]
        self.assertTrue(e["hidden"])
        self.assertFalse(e["fullPriced"])
        self.assertEqual("", e["rateTexts"][0])

    def test_unknown_schema_is_unsupported(self):
        self.assertEqual({"supported": False}, self.result["views"]["unknown-schema-unsupported"])

    def test_total_incomplete_blocks_full_estimate(self):
        view = self.result["views"]["total-incomplete-blocks-full-estimate"]
        self.assertTrue(view["totalIncomplete"])
        self.assertFalse(view["fullEstimate"])
        self.assertTrue(view["anyPriced"])

    def test_rounding_input_boundaries_stay_exact(self):
        by_name = {e["model"]["model"]: e for e in self.result["views"]["rounding-input-boundaries"]["entries"]}
        self.assertEqual("BigInt:5000000000", by_name["round-a"]["costScaled"])
        self.assertEqual("BigInt:4999999999", by_name["round-b"]["costScaled"])
        # display rounding asserted in test_helpers: 5e9 scaled = $0.005 -> $0.01 (half-up)

    def test_day_and_model_scope_filter_rows(self):
        view = self.result["views"]["day-and-model-scope"]
        self.assertEqual(1, len(view["entries"]))
        e = view["entries"][0]
        self.assertEqual("in", e["model"]["identity"])
        self.assertEqual("BigInt:2500000", e["partSums"][0])
        self.assertEqual("BigInt:5000000000000", e["costScaled"])

    def test_invalid_rows_are_counted_not_dropped(self):
        view = self.result["views"]["invalid-rows-counted-as-unknown"]
        self.assertEqual(4, view["invalidRows"])
        self.assertEqual("BigInt:4", view["unknownCalls"])
        self.assertEqual("BigInt:6", view["unknownTokens"])
        self.assertEqual("BigInt:6", view["totalCalls"])
        self.assertFalse(view["fullEstimate"])
        e = view["entries"][0]
        self.assertEqual("BigInt:1000000", e["partSums"][0])
        self.assertEqual("BigInt:2000000000000", e["costScaled"])

    def test_parse_rate(self):
        got = self.result["helpers"]["parseRate"]
        self.assertEqual('{"ok":true,"scaled":"BigInt:2500000"}', got[0])
        self.assertEqual('{"ok":false}', got[1])
        self.assertEqual('{"ok":true,"empty":true}', got[2])
        self.assertEqual('{"ok":false}', got[3])  # 7 decimals
        self.assertEqual('{"ok":false}', got[4])  # above 1e9 cap

    def test_money_text(self):
        self.assertEqual(
            ["$0.00", "$<0.0001", "$1.50", "¥0.50", "$123,456.79", "$<0.01"],
            self.result["helpers"]["moneyText"],
        )

    def test_money_exact(self):
        self.assertEqual(["0", "0.12", "0.123456789012", "0.000000000001"],
                         self.result["helpers"]["moneyExact"])

    def test_model_key(self):
        self.assertEqual('["a\\"b","c\\\\d"]', self.result["helpers"]["modelKey"])

    def test_sanitize_entry_rates(self):
        got = self.result["helpers"]["sanitizeEntryRates"]
        self.assertEqual('["1","","0.5","1","1"]', got[0])
        self.assertEqual("null", got[1])   # not an array / wrong length
        self.assertEqual("null", got[2])   # wrong length
        self.assertEqual("null", got[3])   # invalid rate string

    def test_sanitize_config(self):
        got = [json.loads(x) for x in self.result["helpers"]["sanitizeConfig"]]
        self.assertEqual([None, None, None, None], got[:4])
        cn = got[4]
        self.assertEqual(1, cn["v"])
        self.assertEqual("CNY", cn["currency"])
        self.assertEqual(False, cn["reference"])
        entry = cn["prices"]['["a","b"]']
        self.assertEqual(["1", "", "", "", ""], entry["rates"])
        self.assertEqual(120, len(entry["note"]))  # long note truncated

    def test_effective_price(self):
        got = [json.loads(x) for x in self.result["helpers"]["effectivePrice"]]
        self.assertEqual(["2", "10", "0.10", "2.50", ""], got[0]["entry"]["rates"])
        self.assertEqual("", got[0]["entry"]["note"])
        self.assertEqual("openai", got[0]["reference"]["vendor"])
        self.assertEqual({"entry": None, "reference": None}, got[1])  # hidden
        self.assertEqual({"entry": None, "reference": None}, got[2])  # unknown model
        self.assertEqual("n", got[3]["entry"]["note"])
        self.assertIsNone(got[3]["reference"])  # explicit entry beats reference


if __name__ == "__main__":
    unittest.main()
