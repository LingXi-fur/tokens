import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "tokens_cli" / "dashboard_assets"
SCRIPT = ASSETS / "dashboard.js"
COST_CORE = ASSETS / "cost_core.js"
HAVE_NODE = shutil.which("node") is not None


def _extract_function(source, name):
    start = source.index(f"function {name}(")
    paren = source.index("(", start)
    depth = 0
    brace = None
    for index in range(paren, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                brace = source.index("{", index)
                break
    if brace is None:
        raise AssertionError(name)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(name)


def _run_node(script):
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr[-4000:])
    return result.stdout


def _range_harness(source):
    start = source.index("const RANGE_PRESETS")
    end = source.index("function compareActive", start)
    range_source = source[start:end]
    period_days = _extract_function(source, "periodDays")
    local_iso = _extract_function(source, "localISO")
    return f"""
const DATA={{
  generated:'2026-10-19T03:00:00Z',
  calendar_day:'2026-10-17',
  snapshot:{{timezone:'UTC'}},
  range:{{since:'2026-01-01',until:'2026-10-31'}},
  day:[],
}};
let dashboardLanguage='zh';
let state={{gran:'day',models:new Set(),focusPeriod:null,range:'all',rangeDate:''}};
{local_iso}
{period_days}
{range_source}
"""


class DashboardRangeTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_range_presets_use_report_timezone_and_generated_fallback(self):
        source = SCRIPT.read_text(encoding="utf-8")
        script = _range_harness(source) + r"""
const RealDate=Date;
class FakeDate extends RealDate {
  constructor(...args){ if(args.length===0) super('2026-10-19T01:30:00Z'); else super(...args); }
  static UTC(...args){ return RealDate.UTC(...args); }
}
Date=FakeDate;
function check(label, actual, expected){
  const left=JSON.stringify(actual), right=JSON.stringify(expected);
  if(left!==right)throw new Error(label+': '+left+' != '+right);
}
if(generatedDay()!=='2026-10-17')throw new Error('explicit calendar_day must win');
DATA.calendar_day=undefined;
if(generatedDay()!=='2026-10-19')throw new Error('generated fallback drift');
DATA.calendar_day='2026-10-17';

DATA.snapshot={timezone:'UTC'};
state.range='today';
check('utc today', rangeInfo(), {preset:'today',requested:'today',since:'2026-10-19',until:'2026-10-19',days:['2026-10-19'],anchor:'2026-10-19',anchored:false,timeZone:'UTC'});
state.range='yesterday';
check('utc yesterday', rangeInfo().days, ['2026-10-18']);
state.range='last7';
check('utc last7', rangeInfo().days, ['2026-10-13','2026-10-14','2026-10-15','2026-10-16','2026-10-17','2026-10-18','2026-10-19']);
state.range='custom';state.rangeDate='2026-02-29';
check('invalid custom falls back', rangeInfo().preset, 'all');
state.rangeDate='2026-03-01';
check('custom day', rangeInfo().days, ['2026-03-01']);

DATA.snapshot={timezone:'America/Los_Angeles'};
state.range='today';
check('iana boundary today', rangeInfo().anchor, '2026-10-18');
state.range='last7';
check('iana boundary last7 start', rangeInfo().since, '2026-10-12');

DATA.snapshot={timezone:'system local time'};
state.range='today';
check('system local anchored', [rangeInfo().anchor,rangeInfo().anchored,rangeInfo().days], ['2026-10-17',true,['2026-10-17']]);
state.range='last7';
check('anchored label', rangeLabel().startsWith('生成日 '), true);

DATA.snapshot={timezone:'UTC'};
state.range='all';state.rangeDate='';
const empty={preset:'all',since:null};
check('all inactive', rangeActive(), false);
if(isoDayValid('2026-02-29')||isoDayValid('2026-13-01'))throw new Error('invalid ISO day accepted');
if(addISODays('2026-12-31',1)!=='2027-01-01'||addISODays('2026-03-01',-1)!=='2026-02-28')throw new Error('UTC label arithmetic drift');
"""
        _run_node(script)

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_boundary_week_and_month_range_clipping(self):
        source = SCRIPT.read_text(encoding="utf-8")
        script = _range_harness(source) + r"""
const normalInfo=rangeInfo;
rangeInfo=()=>({preset:'custom',since:'2026-02-10',until:'2026-02-15',days:['2026-02-10','2026-02-11','2026-02-12','2026-02-13','2026-02-14','2026-02-15'],anchor:'2026-02-15',anchored:false,timeZone:'UTC'});
if(periodDays('2026-02-01','month').length!==28)throw new Error('month period length drift');
if(periodScopeDays('2026-02-01','month').join(',')!=='2026-02-10,2026-02-11,2026-02-12,2026-02-13,2026-02-14,2026-02-15')throw new Error('month clipping drift');
if(periodScopeDays('2026-01-01','month').length!==0)throw new Error('out-of-range month should be empty');
if(periodScopeDays('2026-02-09','week').join(',')!=='2026-02-10,2026-02-11,2026-02-12,2026-02-13,2026-02-14,2026-02-15')throw new Error('week clipping drift');
if(periodTouchesRange('2026-02-16','week')!==false)throw new Error('next week should not touch range');
rangeInfo=normalInfo;state.range='all';state.rangeDate='';
if(periodScopeDays('2026-02-01','month').length!==28)throw new Error('all-range month should be complete');
if(periodScopeDays('2026-02-09','week').join(',')!=='2026-02-09,2026-02-10,2026-02-11,2026-02-12,2026-02-13,2026-02-14,2026-02-15')throw new Error('all-range week drift');
"""
        _run_node(script)

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_daily_model_rows_and_cost_statuses(self):
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index("const DAILY_COST_PARTS")
        end = source.index("function mergeDailyCosts", start)
        daily_source = source[start:end] + _extract_function(source, "mergeDailyCosts")
        range_start = source.index("const RANGE_PRESETS")
        range_end = source.index("function compareActive", range_start)
        range_source = (
            _extract_function(source, "localISO")
            + "\n"
            + _extract_function(source, "periodDays")
            + "\n"
            + source[range_start:range_end]
        )
        core = COST_CORE.read_text(encoding="utf-8")
        data = {
            "generated": "2026-10-19T03:00:00Z",
            "calendar_day": "2026-10-19",
            "snapshot": {"timezone": "UTC"},
            "models": ["glm-5.3", "glm-5.3-flash", "other"],
            "pretty": {"glm-5.3": "GLM 5.3", "glm-5.3-flash": "GLM 5.3 Flash", "other": "Other"},
            "day": [
                {"period": "2026-10-10", "total": 1500000, "calls": 4,
                 "models": {"glm-5.3": 1000000, "glm-5.3-flash": 500000},
                 "model_calls": {"glm-5.3": 2, "glm-5.3-flash": 2}},
                {"period": "2026-10-11", "total": 0, "calls": 1,
                 "models": {"glm-5.3": 0}, "model_calls": {"glm-5.3": 1}},
                {"period": "2026-10-12", "total": 300, "calls": 1,
                 "models": {"glm-5.3-flash": 300}, "model_calls": {"glm-5.3-flash": 1}},
                {"period": "2026-10-13", "total": 700, "calls": 1,
                 "models": {"glm-5.3": 700}, "model_calls": {"glm-5.3": 1}},
                {"period": "2026-10-14", "total": 900, "calls": 1,
                 "models": {"other": 900}, "model_calls": {"other": 1}},
            ],
            "cost": {
                "schema": 1,
                "components": ["input", "output", "cache_read", "cache_write", "thoughts"],
                "models": [
                    {"source": "a", "model": "glm-5.3", "identity": "glm-5.3", "hidden": False},
                    {"source": "b", "model": "glm-5.3", "identity": "glm-5.3", "hidden": False},
                    {"source": "a", "model": "glm-5.3-flash", "identity": "glm-5.3-flash", "hidden": False},
                    {"source": "a", "model": "other", "identity": "other", "hidden": True},
                ],
                "rows": [
                    ["2026-10-10", 0, [400000, 0, 0, 0, 0], 400000, 1, False],
                    ["2026-10-10", 1, [600000, 0, 0, 0, 0], 600000, 1, False],
                    ["2026-10-11", 0, [0, 0, 0, 0, 0], 0, 1, False],
                    ["2026-10-12", 2, [0, 0, 0, 0, 0], 300, 1, True],
                    ["2026-10-13", 0, [700, 0, 0, 0, 9007199254740991], 700, 1, False],
                    ["2026-10-14", 3, [900, 0, 0, 0, 0], 900, 1, False],
                ],
            },
        }
        script = f"""
const fs=require('fs');
const vm=require('vm');
const coreSource=fs.readFileSync({json.dumps(str(COST_CORE))},'utf8');
const context={{console}};
vm.createContext(context);
vm.runInContext(coreSource,context);
const CostCore=context.CostCore;
const DATA={json.dumps(data)};
let dashboardLanguage='zh';
let state={{gran:'day',models:new Set(['glm-5.3','glm-5.3-flash','other']),focusPeriod:null,range:'all',rangeDate:''}};
const COST_COMPONENTS=DATA.cost.components;
const costPrices=CostCore.defaultConfig();
function esc(value){{return String(value);}}
function fmt(value){{return Number(value).toLocaleString('en-US');}}
{range_source}
{daily_source}
function assert(condition,message){{if(!condition)throw new Error(message);}}
let summary=dailyCostFor('2026-10-10','glm-5.3');
assert(summary.status==='priced','multi-source trusted rows should price');
assert(CostCore.moneyText(summary.scaled,'USD')==='$1.40','multi-row input cost drift: '+CostCore.moneyText(summary.scaled,'USD'));
assert(summary.partSums[0]===1000000n,'multi-row BigInt sum drift');
summary=dailyCostFor('2026-10-11','glm-5.3');
assert(summary.status==='priced'&&summary.scaled===0n,'trusted zero usage should be explicit zero');
summary=dailyCostFor('2026-10-12','glm-5.3-flash');
assert(summary.status==='unknown','uncertain row must not become zero');
summary=dailyCostFor('2026-10-13','glm-5.3');
assert(summary.status==='partial','unpriced active cache_write must be partial');
summary=dailyCostFor('2026-10-14','other');
assert(summary.status==='hidden','hidden Other must not be guessed');
summary=dailyCostFor('2026-10-15','glm-5.3');
assert(summary.status==='missing','missing cost rows must not become zero');
summary=dailyCostFor('2026-10-10','glm-5.3');
assert(summary.scaled===1400000000000n,'expected $1.40 in scaled units');

state.range='custom';state.rangeDate='2026-10-10';
let rows=dailyModelRows();
assert(rows.length===2&&rows.every(row=>row.day==='2026-10-10'),'range clipping drift');
assert(rows.some(row=>row.model==='glm-5.3'&&row.tokens===1000000&&row.calls===2),'day exact values drift');
state.range='custom';state.rangeDate='2026-10-11';
rows=dailyModelRows();
assert(rows.length===1&&rows[0].tokens===0&&rows[0].calls===1,'zero-token recorded call must stay visible');
state.range='all';
const before=DATA.models.slice();
const stats=glmSeatStats({{model:'glm-5.3',label:'GLM-5.3'}});
assert(stats.catalog===true&&stats.days===3&&stats.calls===4n,'GLM two-step stats drift');
assert(JSON.stringify(DATA.models)===JSON.stringify(before),'GLM compare must not mutate DATA.models');
const absent=glmSeatStats({{model:'glm-5.3-missing',label:'Missing'}});
assert(absent.catalog===false&&absent.days===0,'missing seat must stay absent');
assert(JSON.stringify(DATA.models)===JSON.stringify(before),'missing seat must not be added');
const merged=mergeDailyCosts([{{status:'priced',scaled:2n}},{{status:'unknown',scaled:0n}}]);
assert(merged.status==='partial','mixed priced/unknown merge drift');
const merged2=mergeDailyCosts([{{status:'missing',scaled:0n}},{{status:'priced',scaled:2n}}]);
assert(merged2.status==='partial'&&merged2.scaled===2n,'missing+priced merge drift');
"""
        output = _run_node(script)
        self.assertEqual("", output)

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_cost_parts_chunk_sum_uses_bigint(self):
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index("const DAILY_COST_PARTS")
        end = source.index("function mergeDailyCosts", start)
        daily_source = source[start:end]
        core = COST_CORE.read_text(encoding="utf-8")
        data = {
            "generated": "2026-10-19T03:00:00Z",
            "calendar_day": "2026-10-19",
            "snapshot": {"timezone": "UTC"},
            "models": ["glm-5.3"],
            "pretty": {"glm-5.3": "GLM 5.3"},
            "day": [],
            "cost": {
                "schema": 1,
                "components": ["input", "output", "cache_read", "cache_write", "thoughts"],
                "models": [{"source": "a", "model": "glm-5.3", "identity": "glm-5.3", "hidden": False}],
                "rows": [
                    ["2026-10-10", 0, [9007199254740991, 0, 0, 0, 0], 1, 1, False],
                    ["2026-10-10", 0, [9007199254740991, 0, 0, 0, 0], 1, 1, False],
                ],
            },
        }
        script = f"""
const fs=require('fs');
const vm=require('vm');
const context={{console}};
vm.createContext(context);
vm.runInContext(fs.readFileSync({json.dumps(str(COST_CORE))},'utf8'),context);
const CostCore=context.CostCore;
const DATA={json.dumps(data)};
let dashboardLanguage='zh';
let state={{gran:'day',models:new Set(['glm-5.3']),focusPeriod:null,range:'all',rangeDate:''}};
const COST_COMPONENTS=DATA.cost.components;
const costPrices=CostCore.defaultConfig();
function esc(value){{return String(value);}}
function fmt(value){{return String(value);}}
{daily_source}
const summary=dailyCostFor('2026-10-10','glm-5.3');
if(summary.status!=='priced')throw new Error('chunked rows should price');
if(summary.partSums[0]!==18014398509481982n)throw new Error('BigInt chunk sum drift: '+summary.partSums[0]);
if(CostCore.moneyText(summary.scaled,'USD')==='$0.00')throw new Error('large sum must not collapse to zero');
"""
        output = _run_node(script)
        self.assertEqual("", output)


    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_daily_components_csv_and_glm_filter_contract(self):
        source = SCRIPT.read_text(encoding="utf-8")
        daily = source[source.index("const DAILY_COST_PARTS"):source.index("let previousModels")]
        exports = "\n".join(_extract_function(source, name) for name in (
            "usageCSVCount", "exportDailyCSV", "csvCell",
        ))
        script = _range_harness(source) + f"""
const vm=require('vm'),fs=require('fs'),context={{}};
vm.createContext(context);
vm.runInContext(fs.readFileSync({json.dumps(str(COST_CORE))},'utf8'),context);
const CostCore=context.CostCore,costPrices=CostCore.defaultConfig();
const assert=(v,m)=>{{if(!v)throw new Error(m);}};
const esc=String,pretty=String,fmt=String;
const elements={{}};
const document={{getElementById(id){{return elements[id]||(elements[id]={{innerHTML:'',textContent:'',setAttribute(){{}}}});}}}};
let download=null;
function downloadBlob(text,type,name){{download={{text,type,name}};}}
{daily}
{exports}
DATA.models=['glm-5.3','glm-5.3-flash'];
DATA.cost={{schema:1,components:[...DAILY_COST_PARTS],models:[{{source:'a',model:'glm-5.3',identity:'glm-5.3',hidden:false}}],rows:[
 ['2026-10-18',0,[7,2,0,0,1],10,1,false],
 ['2026-10-18',0,[0,0,0,0,0],5,1,true]
]}};
DATA.day=[{{period:'2026-10-18',models:{{'glm-5.3':15}},model_calls:{{'glm-5.3':2}}}},{{period:'2026-10-17',models:{{'glm-5.3':0}},model_calls:{{'glm-5.3':0}}}}];
state.models=new Set(DATA.models);state.range='custom';state.rangeDate='2026-10-18';
let rows=dailyModelRows();
assert(rows.length===1&&rows[0].components.status==='partial','mixed trust must be partial');
assert(rows[0].components.parts[0]===7n,'known subtotal lost');
exportDailyCSV();
assert(download.name==='tokens-daily-models.csv','daily filename');
assert(download.text.includes('thoughts,component_coverage'),'nonzero thoughts column');
assert(download.text.includes('15,2,7,2,0,0,1,partial,exact,exact'),'daily precision and coverage');
assert(!download.text.includes('2026-10-17'),'CSV escaped date range');
let flash=glmSeatStats(GLM_SEATS[1]);
assert(flash.catalog&&flash.days===0,'catalog missing-day state');
renderGLMCompare();
assert(elements['glm-compare'].innerHTML.includes('无已记录用量'),'no day rows must not invent zero');
state.models=new Set(['glm-5.3-flash']);
assert(glmSeatStats(GLM_SEATS[0]).days===0,'GLM ignored model filter');
renderGLMCompare();
assert(!elements['glm-compare'].innerHTML.includes('范围查数完成'),'filtered model leaked values');
assert(!glmCompareHintText().includes('GLM-5.3（'),'GLM hint ignored model filter');
state.models=new Set(['glm-5.3']);
DATA.cost.rows[1][5]=false;
let summary=dailyCostFor('2026-10-18','glm-5.3');
assert(dailyComponents(summary,15,2).status==='complete','pricing must not control component coverage');
assert(dailyComponents(summary,16,2).status==='partial','missing reported token coverage');
DATA.cost.rows[0].pop();
summary=dailyCostFor('2026-10-18','glm-5.3');
assert(summary.invalid===1&&dailyComponents(summary,15,2).status==='partial','missing uncertainty flag trusted');
DATA.cost.rows[0][5]=false;DATA.cost.components.pop();
assert(dailyCostFor('2026-10-18','glm-5.3').trusted===0,'missing component schema fabricated zeros');
assert(usageCSVCount(9007199254740992).startsWith('not_exact:'),'unsafe CSV fake exact');
assert(usageCSVCount(18014398509481982n)==='18014398509481982','BigInt exact CSV');
state.rangeDate='2026-10-17';
assert(dailyModelRows().length===1,'explicit recorded zero row lost');
DATA.day[1].model_calls={{}};
rows=dailyModelRows();
assert(rows[0].tokens===0&&rows[0].calls===null,'missing calls fabricated exact zero');
assert(!glmSeatStats(GLM_SEATS[0]).exact,'missing calls fabricated exact GLM value');
exportDailyCSV();
assert(download.text.includes(',missing,exact,unverified,'),'missing calls CSV precision');
DATA.day[1].models={{}};DATA.day[1].model_calls={{'glm-5.3':0}};
rows=dailyModelRows();
assert(rows[0].tokens===null&&rows[0].calls===0,'missing tokens fabricated exact zero');
assert(!glmSeatStats(GLM_SEATS[0]).exact,'missing tokens fabricated exact GLM value');
exportDailyCSV();
assert(download.text.includes(',missing,unverified,exact,'),'missing tokens CSV precision');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_relative_range_same_preset_refreshes_after_midnight(self):
        source = SCRIPT.read_text(encoding="utf-8")
        functions = "\n".join(_extract_function(source, name) for name in (
            "refreshRelativeRange", "applyRange",
        ))
        script = _range_harness(source) + f"""
const RealDate=Date;let now='2026-10-18T23:59:00Z';
Date=class extends RealDate{{constructor(...args){{super(...(args.length?args:[now]));}}}};
let renders=0,invalidations=0;const peakState={{}};
function renderRangeUI(){{state.renderedRangeStateKey=computedRangeStateKey();}}
function renderDataViews(){{renders++;}}
function invalidateDerived(){{invalidations++;}}
function resetInterval(){{}}function clearScrub(){{}}function reconcileSignalState(){{}}
function renderFilterLedger(){{}}function toast(){{}}function announceViewChange(){{}}
{functions}
state.range='today';renderRangeUI();const old=state.renderedRangeStateKey;
now='2026-10-19T00:01:00Z';applyRange('today');
if(renders!==1||invalidations!==1||state.renderedRangeStateKey===old)throw new Error('same-preset midnight stale');
if(refreshRelativeRange()||renders!==1)throw new Error('unchanged range rerendered');
now='2026-10-20T00:01:00Z';
if(!refreshRelativeRange()||renders!==2)throw new Error('same snapshot midnight stale');
"""
        self.assertEqual("", _run_node(script))
        self.assertIn("if(hasSnapshot)refreshRelativeRange();statusFromBody(lastBody)", source)
        self.assertIn("if(hasSnapshot)refreshRelativeRange();statusFromBody(payload)", source)


if __name__ == "__main__":
    unittest.main()
