import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "tokens_cli" / "dashboard_assets"
SCRIPT = ASSETS / "dashboard.js"
COST_CORE = ASSETS / "cost_core.js"
CALENDAR_CORE = ASSETS / "calendar_core.js"
PERIOD_CORE = ASSETS / "period_core.js"
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


def _daily_source(source, end_marker):
    """Keep daily derivations independent of the dashboard's calendar wiring."""
    start = source.index("const DAILY_COST_PARTS")
    end = source.index(end_marker, start)
    calendar_start = source.index("const {calendarMonthParse,", start, end)
    daily_start = source.index("function dailyModelRows(", calendar_start, end)
    return source[start:calendar_start] + source[daily_start:end]


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
    period_days = PERIOD_CORE.read_text(encoding="utf-8") + "\n" + _extract_function(source, "periodDays")
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
        daily_source = _daily_source(source, "function mergeDailyCosts") + _extract_function(
            source, "mergeDailyCosts"
        )
        range_start = source.index("const RANGE_PRESETS")
        range_end = source.index("function compareActive", range_start)
        range_source = (
            _extract_function(source, "localISO")
            + "\n"
            + PERIOD_CORE.read_text(encoding="utf-8")
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
        daily_source = _daily_source(source, "function mergeDailyCosts")
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
        daily = _daily_source(source, "let previousModels")
        # The calendar interaction binding needs a real DOM; the daily harness
        # only extracts pure derivations, so keep its IIFE out of the test realm.
        daily = re.sub(
            r"^\(function bindDailyCalendar\(\)\{.*?^\}\)\(\);$",
            "",
            daily,
            flags=re.MULTILINE | re.DOTALL,
        )
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
        self.assertRegex(source, r"if\(hasSnapshot\)refreshRelativeRange\(\);\s*statusFromBody\(payload\)")


def _calendar_harness(source):
    """Load the production calendar core with its existing shared dependencies."""
    shared = "\n".join(
        _extract_function(source, name)
        for name in ("isoDayValid", "addISODays", "dailySafeInt")
    )
    constants = "\n".join(
        re.search(rf"^const {name}=.*?;", source, re.MULTILINE).group(0)
        for name in ("ISO_DAY_RE", "DAILY_COST_MAX")
    )
    core = CALENDAR_CORE.read_text(encoding="utf-8")
    return f"""
{constants}
{shared}
{core}
const {{calendarMonthParse,calendarWeekdayMonday,calendarMonthShift,calendarBase,
  calendarRangeKey,calendarMonthData,calendarStripDays,calendarPreviewData}}=
  CalendarCore.create({{isoDayValid,addISODays,dailySafeInt}});
const eq=(actual,expected,label)=>{{
  const left=JSON.stringify(actual), right=JSON.stringify(expected);
  if(left!==right)throw new Error(label+': '+left+' != '+right);
}};
const ok=(value,label)=>{{if(!value)throw new Error(label);}};
const cell=(data,day)=>{{
  const found=(data.cells||[]).find(item=>item.day===day);
  if(!found)throw new Error('missing cell '+day);
  return found;
}};
"""


class CalendarCoreContractsTests(unittest.TestCase):
    def test_calendar_core_is_separate_and_old_entry_points_are_removed(self):
        self.assertTrue(CALENDAR_CORE.is_file(), "Calendar derivations need a production asset")
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?m)^function calendar\w+\(")
        for name in ("rangeDaySet", "setSignalPreview", "clearSignalPreview"):
            with self.subTest(name=name):
                self.assertNotRegex(source, rf"\b{re.escape(name)}\b")

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_core_exports_only_the_factory_and_public_derivations(self):
        self.assertTrue(CALENDAR_CORE.is_file(), "Calendar core asset is missing")
        source = SCRIPT.read_text(encoding="utf-8")
        script = _calendar_harness(source) + """
eq(Object.keys(CalendarCore),['create'],'core namespace');
const api=CalendarCore.create({isoDayValid,addISODays,dailySafeInt});
eq(Object.keys(api).sort(),[
  'calendarMonthParse','calendarWeekdayMonday','calendarMonthShift','calendarBase',
  'calendarRangeKey','calendarMonthData','calendarStripDays','calendarPreviewData'
].sort(),'public API');
ok(!('calendarIsLeapYear' in api),'leap helper remains private');
ok(!('calendarDaysInMonth' in api),'month helper remains private');
ok(!('calendarIntensityLevel' in api),'intensity helper remains private');
"""
        self.assertEqual("", _run_node(script))


class CalendarLogicTests(unittest.TestCase):
    """Pure month-calendar derivations.

    The calendar is a preview locator, never a second data pipeline: it reads
    the same recorded day rows, keeps unknown/missing distinct from zero and
    only reports values it can prove.
    """

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_month_shift_utc_and_year_bounds(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
eq(calendarMonthShift('2026-01',-1),'2025-12','previous year');
eq(calendarMonthShift('2026-12',1),'2027-01','next year');
eq(calendarMonthShift('2024-02',1),'2024-03','leap February shift');
eq(calendarMonthShift('2026-06',-12),'2025-06','minus twelve months');
eq(calendarMonthShift('2026-06',12),'2027-06','plus twelve months');
eq(calendarMonthShift('0100-01',0),'0100-01','minimum supported year');
eq(calendarMonthShift('9999-12',0),'9999-12','maximum supported year');
eq(calendarMonthShift('0100-01',-1),null,'underflow must be unavailable');
eq(calendarMonthShift('9999-12',1),null,'overflow must be unavailable');
eq(calendarMonthShift('2026-13',1),null,'month 13 is invalid');
eq(calendarMonthShift('2026-00',1),null,'month 0 is invalid');
eq(calendarMonthShift('2026-1',1),null,'single-digit month is invalid');
eq(calendarMonthShift('26-01',1),null,'short year is invalid');
eq(calendarMonthShift('',1),null,'empty month is invalid');
eq(calendarMonthShift(null,1),null,'null month is invalid');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_base_precedence_and_fallbacks(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const ranged=calendarBase(
  {preset:'custom',since:'2026-02-01',until:'2026-02-28',anchor:'2026-10-19'},
  [{period:'2026-03-31'}],'2026-04-01');
eq(ranged.day,'2026-02-28','valid range until must win over later rows');
eq(ranged.month,'2026-02','range month');
eq(ranged.basis,'range','range basis');

const rows=[
  {period:'2026-01-15'},{period:'2026-03-31'},{period:'2026-02-30'},
  {period:'2026-02-29'},{period:''},{},
];
const records=calendarBase(
  {preset:'all',since:null,until:null,anchor:'2026-10-19'},rows,'2026-04-01');
eq(records.day,'2026-03-31','latest valid recorded period wins');
eq(records.month,'2026-03','records month');
eq(records.basis,'records','records basis');

const invalidUntil=calendarBase(
  {preset:'all',since:null,until:'2026-02-30'},[{period:'2025-12-31'}],'2026-04-01');
eq(invalidUntil.day,'2025-12-31','invalid range until falls back to records');
eq(invalidUntil.month,'2025-12','invalid until month');
eq(invalidUntil.basis,'records','invalid until basis');

const generated=calendarBase(
  {preset:'all'},[{period:'2026-02-30'},{period:'bad'}],'2026-04-01');
eq(generated.day,'2026-04-01','generated day fallback');
eq(generated.month,'2026-04','generated month');
eq(generated.basis,'generated','generated basis');

const unavailable=calendarBase({preset:'all'},[{period:'bad'}],'not-a-day');
eq(unavailable.day,null,'unavailable day');
eq(unavailable.month,null,'unavailable month');
eq(unavailable.basis,'unavailable','unavailable basis');
eq(calendarBase(null,null,null).basis,'unavailable','null inputs stay unavailable');
eq(calendarBase({preset:'all'},null,undefined).basis,'unavailable','missing inputs stay unavailable');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_range_key_excludes_anchor_and_tracks_scope(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const base={preset:'custom',since:'2026-02-10',until:'2026-02-15',anchor:'2026-10-19'};
const shiftedAnchor={...base,anchor:'2026-03-01'};
eq(calendarRangeKey(base),calendarRangeKey(shiftedAnchor),'anchor must not move the key');
ok(typeof calendarRangeKey(base)==='string','range key must be a string');
ok(calendarRangeKey(base).includes('2026-02-10'),'range key carries since');
ok(calendarRangeKey(base).includes('2026-02-15'),'range key carries until');
ok(!calendarRangeKey(base).includes('2026-10-19'),'range key must exclude anchor');
ok(calendarRangeKey({...base,preset:'all'})!==calendarRangeKey(base),'preset change must move the key');
ok(calendarRangeKey({...base,since:'2026-02-11'})!==calendarRangeKey(base),'since change must move the key');
ok(calendarRangeKey({...base,until:'2026-02-16'})!==calendarRangeKey(base),'until change must move the key');
ok(calendarRangeKey({preset:'all',since:null,until:null,anchor:'2026-10-19'})===calendarRangeKey({preset:'all',since:null,until:null,anchor:'2026-10-20'}),'null scope ignores anchor');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_month_grid_utc_leap_and_42_cell_bound(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
function checkMonth(month,days,firstOffset,coverage){
  const data=calendarMonthData([],['m1'],month,coverage,null);
  eq(data.valid,true,'valid '+month);
  eq(data.month,month,'month echo '+month);
  eq(data.year,Number(month.slice(0,4)),'year '+month);
  eq(data.monthIndex,Number(month.slice(5,7))-1,'month index '+month);
  eq(data.daysInMonth,days,'days in month '+month);
  eq(data.cells.length,days,'one cell per real day '+month);
  eq(data.cells[0].day,month+'-01','first cell '+month);
  eq(data.cells[days-1].day,month+'-'+String(days).padStart(2,'0'),'last cell '+month);
  ok(data.weeks.every(week=>week.length===7),'seven columns '+month);
  const flat=data.weeks.flat();
  ok(flat.length%7===0,'whole weeks '+month);
  ok(flat.length<=42,'at most 42 slots '+month);
  eq(flat.filter(Boolean).length,days,'placeholders are not days '+month);
  eq(flat[firstOffset].day,month+'-01','Monday-first offset '+month);
  flat.forEach((slot,index)=>{
    if(!slot)return;
    const column=index%7;
    const utcColumn=(new Date(slot.day+'T00:00:00Z').getUTCDay()+6)%7;
    eq(column,utcColumn,'UTC weekday column '+slot.day);
  });
  return data;
}
checkMonth('2024-02',29,3,{first_day:'2024-02-01',last_day:'2024-02-29'});
checkMonth('2023-02',28,2,{first_day:'2023-02-01',last_day:'2023-02-28'});
const august=checkMonth('2026-08',31,5,{first_day:'2026-08-01',last_day:'2026-08-31'});
eq(august.weeks.length,6,'six-week month');
eq(august.weeks.flat().length,42,'six-week grid uses 42 slots');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_month_data_no_selection_no_record_and_zero(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const coverage={first_day:'2026-04-01',last_day:'2026-04-30'};
const row={period:'2026-04-02',models:{m1:5},model_calls:{m1:1}};
const none=calendarMonthData([row],[],'2026-04',coverage,null);
eq(none.modelCount,0,'no model selection count');
eq(none.selectedModels,[],'no model selection echo');
const blank=cell(none,'2026-04-02');
eq(blank.selectedPresent,0,'no-selection present count');
eq(blank.hasRecord,false,'no-selection has no own-key record');
eq(blank.hasAnyDayRow,true,'day row still exists');
eq(blank.tokenStatus,'no-selection','token status without a filter');
eq(blank.callsStatus,'no-selection','calls status without a filter');
eq(blank.tokens,null,'no-selection must not paint a value');
eq(blank.calls,null,'no-selection must not paint calls');
eq(blank.tokensExact,false,'no-selection cannot be exact');
eq(blank.callsExact,false,'no-selection calls cannot be exact');
eq(blank.zeroRecorded,false,'no-selection is not a recorded zero');
eq(blank.intensity,null,'no-selection stays out of the scale');
eq(none.recordedDays,0,'no-selection records no days');
eq(none.anyDayRows,1,'unfiltered day rows are still counted');
eq(none.exactTokenDays,0,'no-selection exact days');
eq(none.maxTokens,null,'no-selection maximum');

const empty=calendarMonthData([],['m1'],'2026-04',coverage,null);
const missingDay=cell(empty,'2026-04-01');
eq(missingDay.hasRecord,false,'empty month has no record');
eq(missingDay.hasAnyDayRow,false,'empty month has no day row');
eq(missingDay.tokenStatus,'no-record','absent record is no-record');
eq(missingDay.callsStatus,'no-record','absent calls are no-record');
eq(missingDay.tokens,null,'no record is not zero tokens');
eq(missingDay.calls,null,'no record is not zero calls');
eq(empty.recordedDays,0,'empty month recorded days');
eq(empty.anyDayRows,0,'empty month any-day rows');
eq(empty.maxTokens,null,'empty month maximum');

const otherOnly=calendarMonthData(
  [{period:'2026-04-03',models:{other:9},model_calls:{other:1}}],
  ['m1'],'2026-04',coverage,null);
const otherCell=cell(otherOnly,'2026-04-03');
eq(otherCell.hasAnyDayRow,true,'unselected identity still proves a day row');
eq(otherCell.hasRecord,false,'unselected identity is not an own-key record');
eq(otherCell.tokenStatus,'no-record','unselected identity stays no-record');
eq(otherOnly.recordedDays,0,'unselected identity records no selected day');

const selectedOther=calendarMonthData(
  [{period:'2026-04-03',models:{other:9},model_calls:{other:1}}],
  ['other'],'2026-04',coverage,null);
const selectedOtherCell=cell(selectedOther,'2026-04-03');
eq(selectedOtherCell.hasRecord,true,'selected Other is a real own key');
eq(selectedOtherCell.tokenStatus,'known','selected Other tokens are known');
eq(selectedOtherCell.tokens,'9','selected Other token value');
eq(selectedOtherCell.calls,'1','selected Other call value');

const zero=calendarMonthData(
  [{period:'2026-04-04',models:{m1:0},model_calls:{m1:0}}],
  ['m1'],'2026-04',coverage,null);
const zeroCell=cell(zero,'2026-04-04');
eq(zeroCell.hasRecord,true,'explicit zero is a record');
eq(zeroCell.zeroRecorded,true,'explicit zero flag');
eq(zeroCell.tokenStatus,'zero','explicit token zero');
eq(zeroCell.callsStatus,'zero','explicit call zero');
eq(zeroCell.tokens,'0','explicit zero tokens are printed');
eq(zeroCell.calls,'0','explicit zero calls are printed');
eq(zeroCell.tokensExact,true,'explicit token zero is exact');
eq(zeroCell.callsExact,true,'explicit call zero is exact');
eq(zeroCell.intensity,0,'explicit zero sits at the scale floor');
eq(zero.maxTokens,'0','zero is still an exact maximum');
eq(zero.exactTokenDays,1,'explicit zero is an exact token day');
eq(zero.recordedDays,1,'explicit zero is recorded');

for(const [calls,expected] of [[{m1:3},'known'],[{},'missing']]){
  const data=calendarMonthData(
    [{period:'2026-04-05',models:{m1:0},model_calls:calls}],
    ['m1'],'2026-04',coverage,null);
  const day=cell(data,'2026-04-05');
  eq(day.tokens,'0','explicit token zero remains visible');
  eq(day.tokensExact,true,'token zero precision is independent');
  eq(day.tokenStatus,'zero','token zero status is independent');
  eq(day.callsStatus,expected,'call status remains independent');
  eq(day.zeroRecorded,false,'combined zero still requires both sides');
  eq(day.intensity,0,'exact zero tokens occupy the scale floor');
}
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_month_data_missing_sides_stay_independent(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const coverage={first_day:'2026-05-01',last_day:'2026-05-31'};
const tokensOnly=calendarMonthData(
  [{period:'2026-05-02',models:{m1:5},model_calls:{}}],
  ['m1','m2'],'2026-05',coverage,null);
const tokensCell=cell(tokensOnly,'2026-05-02');
eq(tokensCell.selectedPresent,1,'only the identity with an own key is present');
eq(tokensCell.tokenStatus,'known','token side is known');
eq(tokensCell.tokens,'5','known token value');
eq(tokensCell.tokensExact,true,'known tokens exact');
eq(tokensCell.missingToken,0,'no missing token side');
eq(tokensCell.unsafeToken,0,'no unsafe token side');
eq(tokensCell.callsStatus,'missing','absent calls side is missing');
eq(tokensCell.calls,null,'missing calls must not become zero');
eq(tokensCell.callsExact,false,'missing calls cannot be exact');
eq(tokensCell.missingCalls,1,'one present identity misses calls');
eq(tokensCell.unsafeCalls,0,'no unsafe calls side');
ok(tokensCell.intensity>=1&&tokensCell.intensity<=4,'exact positive tokens enter the scale');
eq(tokensOnly.recordedDays,1,'one recorded day');
eq(tokensOnly.exactTokenDays,1,'one exact token day');

const callsOnly=calendarMonthData(
  [{period:'2026-05-03',models:{},model_calls:{m1:3}}],
  ['m1','m2'],'2026-05',coverage,null);
const callsCell=cell(callsOnly,'2026-05-03');
eq(callsCell.tokenStatus,'missing','absent tokens side is missing');
eq(callsCell.tokens,null,'missing tokens must not become zero');
eq(callsCell.missingToken,1,'one present identity misses tokens');
eq(callsCell.callsStatus,'known','calls side is known');
eq(callsCell.calls,'3','known calls value');
eq(callsCell.callsExact,true,'known calls exact');
eq(callsCell.missingCalls,0,'no missing calls side');
eq(callsCell.intensity,null,'missing tokens stay out of the token scale');

const mixed=calendarMonthData(
  [{period:'2026-05-04',models:{m1:5,m2:7},model_calls:{m1:1}}],
  ['m1','m2'],'2026-05',coverage,null);
const mixedCell=cell(mixed,'2026-05-04');
eq(mixedCell.selectedPresent,2,'both identities have an own key');
eq(mixedCell.tokens,'12','known token subtotal');
eq(mixedCell.tokenStatus,'known','known tokens remain known');
eq(mixedCell.callsExact,false,'partially missing calls are not exact');
eq(mixedCell.missingCalls,1,'one identity misses calls');
eq(mixedCell.callsStatus,'partial','known plus missing calls are partial');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_month_data_unsafe_and_bigint_accumulation(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const safe=9007199254740991;
const coverage={first_day:'2026-07-01',last_day:'2026-07-31'};
const rows=[
  {period:'2026-07-02',models:{m1:safe},model_calls:{m1:1}},
  {period:'2026-07-02',models:{m1:safe},model_calls:{m1:1}},
  {period:'2026-07-03',models:{m1:safe+1},model_calls:{m1:2}},
  {period:'2026-07-04',models:{m1:5},model_calls:{m1:safe+1}},
];
const data=calendarMonthData(rows,['m1'],'2026-07',coverage,null);
const accumulated=cell(data,'2026-07-02');
eq(typeof accumulated.tokens,'string','BigInt accumulation is serialized as a string');
eq(accumulated.tokens,'18014398509481982','safe rows sum exactly beyond 2^53');
eq(accumulated.tokensExact,true,'BigInt sum stays exact');
eq(accumulated.tokenStatus,'known','BigInt sum is known');
eq(accumulated.calls,'2','safe calls accumulate');
eq(accumulated.callsExact,true,'safe calls stay exact');
ok(accumulated.intensity>=1&&accumulated.intensity<=4,'largest exact day enters the scale');
eq(data.maxTokens,'18014398509481982','maximum is a BigInt-exact string');

const unsafeTokens=cell(data,'2026-07-03');
eq(unsafeTokens.tokens,null,'unsafe token integer is not printed as exact');
eq(unsafeTokens.tokensExact,false,'unsafe token integer is not exact');
eq(unsafeTokens.tokenStatus,'unsafe','unsafe token status');
eq(unsafeTokens.unsafeToken,1,'one unsafe token identity');
eq(unsafeTokens.missingToken,0,'unsafe is not missing');
eq(unsafeTokens.intensity,null,'unsafe tokens stay out of the scale');
eq(unsafeTokens.calls,'2','calls side remains known');
eq(unsafeTokens.callsStatus,'known','unsafe tokens do not poison calls');

const unsafeCalls=cell(data,'2026-07-04');
eq(unsafeCalls.tokens,'5','tokens side remains known');
eq(unsafeCalls.tokenStatus,'known','unsafe calls do not poison tokens');
eq(unsafeCalls.calls,null,'unsafe calls are not printed as exact');
eq(unsafeCalls.callsExact,false,'unsafe calls are not exact');
eq(unsafeCalls.callsStatus,'unsafe','unsafe calls status');
eq(unsafeCalls.unsafeCalls,1,'one unsafe calls identity');
eq(unsafeCalls.missingCalls,0,'unsafe calls are not missing');
ok(unsafeCalls.intensity>=1,'exact tokens still enter the scale');

eq(data.exactTokenDays,2,'two exact token days');
eq(data.recordedDays,3,'three recorded days');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_month_data_coverage_range_and_boundary_mismatch(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const coverage={first_day:'2026-03-10',last_day:'2026-03-20'};
const range={preset:'custom',since:'2026-03-08',until:'2026-03-18'};
const rows=[
  {period:'2026-03-05',models:{m1:5},model_calls:{m1:1}},
  {period:'2026-03-12',models:{m1:7},model_calls:{m1:1}},
  {period:'2026-03-12',models:{other:100},model_calls:{other:1}},
  {period:'2026-03-25',models:{m1:9},model_calls:{m1:1}},
];
const data=calendarMonthData(rows,['m1'],'2026-03',coverage,range);
eq(data.coverage.first,'2026-03-10','coverage first');
eq(data.coverage.last,'2026-03-20','coverage last');
eq(data.coverage.hasCoverage,true,'ordered coverage is known');

const before=cell(data,'2026-03-05');
eq(before.inCoverage,false,'record before coverage is outside');
eq(before.outsideCoverageRecord,true,'outside record is flagged');
eq(before.inRange,false,'day before the statistical range');
eq(before.tokens,'5','outside coverage still keeps the real record');
eq(before.tokenStatus,'known','outside coverage record stays exact');

const inside=cell(data,'2026-03-12');
eq(inside.inCoverage,true,'day inside coverage');
eq(inside.outsideCoverageRecord,false,'inside record is not a mismatch');
eq(inside.inRange,true,'day inside the statistical range');
eq(inside.tokens,'7','inside value is the selected identity only');

const after=cell(data,'2026-03-25');
eq(after.inCoverage,false,'record after coverage is outside');
eq(after.outsideCoverageRecord,true,'after record is flagged');
eq(after.inRange,false,'day after the statistical range');
eq(after.tokens,'9','after coverage still keeps the real record');
ok(data.boundaryMismatch,'records outside coverage must flag a boundary mismatch');
eq(data.recordedDays,3,'all three recorded days survive');
eq(data.anyDayRows,3,'all three day rows are counted');

const orphan=cell(data,'2026-03-15');
eq(orphan.hasRecord,false,'coverage alone does not invent a record');
eq(orphan.hasAnyDayRow,false,'coverage alone does not invent a day row');
eq(orphan.tokens,null,'coverage alone does not invent tokens');
eq(orphan.tokenStatus,'no-record','coverage alone is still no-record');

const invalid=calendarMonthData(
  rows,['m1'],'2026-03',{first_day:'2026-03-20',last_day:'2026-03-10'},range);
eq(invalid.coverage.first,null,'reversed coverage has no first day');
eq(invalid.coverage.last,null,'reversed coverage has no last day');
eq(invalid.coverage.hasCoverage,false,'reversed coverage is unknown');
invalid.cells.forEach(item=>{
  eq(item.inCoverage,null,'unknown coverage '+item.day);
  eq(item.outsideCoverageRecord,false,'unknown coverage invents no mismatch '+item.day);
});
ok(!invalid.boundaryMismatch,'unknown coverage must not claim a mismatch');
eq(cell(invalid,'2026-03-05').tokens,'5','unknown coverage keeps real records');

const absent=calendarMonthData(rows,['m1'],'2026-03',null,range);
eq(absent.coverage.first,null,'absent coverage first');
eq(absent.coverage.last,null,'absent coverage last');
eq(absent.coverage.hasCoverage,false,'absent coverage is unknown');
eq(cell(absent,'2026-03-12').inCoverage,null,'absent coverage leaves cells unknown');
eq(cell(absent,'2026-03-12').tokens,'7','absent coverage keeps the record');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_month_data_sparse_rows_and_unknown_coverage(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const rows=[
  {period:'2026-04-20',models:{m1:3,m2:4},model_calls:{m1:1,m2:1}},
  {period:'2026-04-02',models:{m1:1},model_calls:{m1:1}},
  {period:'2026-04-10',models:{m2:2},model_calls:{m2:1}},
  {period:'2026-04-12',models:{other:5},model_calls:{other:1}},
];
const before=JSON.stringify(rows);
const data=calendarMonthData(rows,['m2','m1'],'2026-04',null,null);
eq(data.valid,true,'April 2026 is valid');
eq(data.month,'2026-04','month echo');
eq(data.year,2026,'year echo');
eq(data.monthIndex,3,'month index');
eq(data.daysInMonth,30,'April length');
eq(data.cells.length,30,'April cells');
eq(data.selectedModels.slice().sort(),['m1','m2'],'selected model identities');
eq(data.modelCount,2,'selected model count');
eq(data.coverage.first,null,'unknown coverage first');
eq(data.coverage.last,null,'unknown coverage last');
eq(data.coverage.hasCoverage,false,'unknown coverage flag');
eq(data.recordedDays,3,'three selected recorded days');
eq(data.anyDayRows,4,'four days carry rows regardless of selection');
eq(data.maxTokens,'7','largest exact day sum');
eq(data.exactTokenDays,3,'three exact token days');
eq(cell(data,'2026-04-20').tokens,'7','two selected identities accumulate');
eq(cell(data,'2026-04-10').tokens,'2','sparse single-identity day');
const unselected=cell(data,'2026-04-12');
eq(unselected.hasAnyDayRow,true,'unselected day row exists');
eq(unselected.hasRecord,false,'unselected identity is not recorded');
eq(unselected.tokenStatus,'no-record','unselected identity stays no-record');
eq(unselected.tokens,null,'unselected identity has no value');
data.cells.forEach(item=>eq(item.inCoverage,null,'unknown coverage '+item.day));
eq(JSON.stringify(rows),before,'calendar derivation must not mutate day rows');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_month_data_scans_rows_once(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const raw=[];
for(let index=0;index<120;index++){
  const day='2026-04-'+String(1+(index%30)).padStart(2,'0');
  raw.push({period:day,models:{m1:1},model_calls:{m1:1}});
}
let touches=0;
const rows=new Proxy(raw,{get(target,property,receiver){
  if(typeof property==='string'&&/^\d+$/.test(property))touches++;
  return Reflect.get(target,property,receiver);
}});
const data=calendarMonthData(rows,['m1'],'2026-04',{first_day:'2026-04-01',last_day:'2026-04-30'},null);
eq(data.recordedDays,30,'every day aggregates');
eq(cell(data,'2026-04-01').tokens,'4','four rows per day');
/* Numeric gets are row iteration, not row fields; +8 tolerates a few
   repeated gets inside one pass but a second full scan doubles the count. */
ok(touches<=raw.length+8,'calendarMonthData must not rescan rows per cell: '+touches+' touches');
"""
        self.assertEqual("", _run_node(script))


    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_token_zero_marker_preserves_call_warning(self):
        source = SCRIPT.read_text(encoding="utf-8")
        script = _calendar_harness(source) + "\n" + _extract_function(
            source, "calCellButton"
        ) + r"""
const state={range:'all',rangeDate:''};
const esc=String;
function calCellAria(){return 'synthetic recorded counts';}
for(const [calls,unknown] of [[{m1:3},false],[{},true]]){
  const data=calendarMonthData(
    [{period:'2026-04-05',models:{m1:0},model_calls:calls}],
    ['m1'],'2026-04',{},null);
  const html=calCellButton(cell(data,'2026-04-05'),false,'2026-04-05');
  ok(/\bis-zero\b/.test(html),'explicit zero tokens need a zero state');
  ok(/\bintensity-0\b/.test(html),'explicit zero tokens use scale floor');
  eq(/\bis-unknown\b/.test(html),unknown,'missing calls warning stays separate');
  ok(html.includes(unknown?'>0!</span>':'>0</span>'),'visible zero and warning mark');
}
"""
        self.assertEqual("", _run_node(script))


class CalendarStripLogicTests(unittest.TestCase):
    """Seven-day projections retain the trusted monthly Cell semantics."""

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_strip_days_utc_leap_year_crossings_and_bounds(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const cases=[
  ['2024-03-03',['2024-02-26','2024-02-27','2024-02-28','2024-02-29','2024-03-01','2024-03-02','2024-03-03']],
  ['2026-03-03',['2026-02-25','2026-02-26','2026-02-27','2026-02-28','2026-03-01','2026-03-02','2026-03-03']],
  ['2026-01-03',['2025-12-28','2025-12-29','2025-12-30','2025-12-31','2026-01-01','2026-01-02','2026-01-03']],
  ['2026-03-10',['2026-03-04','2026-03-05','2026-03-06','2026-03-07','2026-03-08','2026-03-09','2026-03-10']],
  ['2000-02-29',['2000-02-23','2000-02-24','2000-02-25','2000-02-26','2000-02-27','2000-02-28','2000-02-29']],
  ['0100-01-01',['0100-01-01']],
  ['0100-01-03',['0100-01-01','0100-01-02','0100-01-03']],
  ['0100-01-07',['0100-01-01','0100-01-02','0100-01-03','0100-01-04','0100-01-05','0100-01-06','0100-01-07']],
  ['9999-12-31',['9999-12-25','9999-12-26','9999-12-27','9999-12-28','9999-12-29','9999-12-30','9999-12-31']],
];
for(const [end,expected] of cases)eq(calendarStripDays(end),expected,'UTC strip ending '+end);
for(const end of [undefined,null,'',0,20260303,{},[],'bad','2026-3-03','2026-03-3',
  '2026-02-29','1900-02-29','2026-04-31','2026-13-01','2026-00-01','2026-01-00',
  '2026-01-32','0099-12-31','0000-01-01','10000-01-01','2026-03-03T00:00:00Z',
  ' 2026-03-03','2026-03-03 ']){
  eq(calendarStripDays(end),[],'invalid strip anchor '+String(end));
}
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_strip_keeps_contiguous_days_with_sparse_same_and_cross_month_rows(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const cases=[
  {end:'2026-04-12',days:['2026-04-06','2026-04-07','2026-04-08','2026-04-09','2026-04-10','2026-04-11','2026-04-12'],
   rows:['2026-04-01','2026-04-06','2026-04-09','2026-04-12'],values:['2',null,null,'3',null,null,'4']},
  {end:'2026-05-03',days:['2026-04-27','2026-04-28','2026-04-29','2026-04-30','2026-05-01','2026-05-02','2026-05-03'],
   rows:['2026-04-01','2026-04-30','2026-05-02'],values:[null,null,null,'2',null,'3',null]},
];
for(const item of cases){
  const rows=item.rows.map((period,index)=>({period,models:{m1:index+1},model_calls:{m1:1}}));
  const before=JSON.stringify(rows);
  const data=calendarPreviewData(rows,['m1'],item.end,item.end.slice(0,7),null);
  eq(data.days.map(day=>day.day),item.days,'consecutive dates ending '+item.end);
  eq(data.days.map(day=>day.tokens),item.values,'missing dates are not skipped '+item.end);
  eq(data.days.map(day=>day.tokenStatus),item.values.map(value=>value===null?'no-record':'known'),'record status '+item.end);
  eq(data.days.map(day=>day.hasAnyDayRow),item.values.map(value=>value!==null),'day-row presence '+item.end);
  for(const day of data.days.filter(day=>!day.hasRecord)){
    eq(day.calls,null,'absent day is not zero calls '+day.day);
    eq(day.intensity,null,'absent day is not a zero marker '+day.day);
  }
  eq(data.monthData,null,'default preview stays collapsed');
  eq(JSON.stringify(rows),before,'projection does not mutate rows');
}
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_strip_preserves_no_selection_no_record_and_independent_zero_warnings(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const safe=9007199254740991;
const rows=[
  {period:'2026-04-01',models:Object.create({m1:9}),model_calls:Object.create({m1:1})},
  {period:'2026-04-02',models:{m1:0},model_calls:{m1:0}},
  {period:'2026-04-03',models:{m1:0},model_calls:{m1:3}},
  {period:'2026-04-04',models:{m1:0},model_calls:{}},
  {period:'2026-04-05',models:{m1:0},model_calls:{m1:safe+1}},
  {period:'2026-04-06',models:{},model_calls:{m1:0}},
];
const end='2026-04-07',month='2026-04';
const none=calendarPreviewData(rows,[],end,month,null);
for(const day of none.days){
  eq(day.tokenStatus,'no-selection','no selected token model '+day.day);
  eq(day.callsStatus,'no-selection','no selected call model '+day.day);
  eq(day.hasRecord,false,'selection is needed for a record '+day.day);
  eq(day.tokens,null,'no selection is not zero tokens '+day.day);
  eq(day.calls,null,'no selection is not zero calls '+day.day);
  eq(day.intensity,null,'no selection has no intensity '+day.day);
}
eq(none.days[1].hasAnyDayRow,true,'no selection retains day-row evidence');
const empty=calendarPreviewData([],['m1'],end,month,null);
for(const day of empty.days){
  eq(day.tokenStatus,'no-record','empty input has no token record '+day.day);
  eq(day.callsStatus,'no-record','empty input has no call record '+day.day);
  eq(day.hasAnyDayRow,false,'empty input has no row '+day.day);
  eq(day.tokens,null,'empty input is not recorded zero '+day.day);
  eq(day.calls,null,'empty input is not zero calls '+day.day);
}
const data=calendarPreviewData(rows,['m1'],end,month,null);
const at=day=>data.days.find(item=>item.day==='2026-04-0'+day);
eq(at(1).hasAnyDayRow,true,'inherited-key row still exists');
eq(at(1).hasRecord,false,'inherited model keys are not records');
eq(at(1).tokenStatus,'no-record','inherited token value stays absent');
eq(at(1).callsStatus,'no-record','inherited call value stays absent');
for(const day of [2,3,4,5]){
  eq(at(day).tokens,'0','explicit zero tokens survive '+day);
  eq(at(day).tokensExact,true,'token zero stays exact '+day);
  eq(at(day).tokenStatus,'zero','zero token status '+day);
  eq(at(day).intensity,0,'zero token scale floor '+day);
}
eq(at(2).calls,'0','explicit zero calls');
eq(at(2).callsExact,true,'explicit zero calls are exact');
eq(at(2).callsStatus,'zero','explicit call zero status');
eq(at(2).zeroRecorded,true,'only both exact zeros are combined zero');
eq(at(3).calls,'3','positive calls survive zero tokens');
eq(at(3).callsStatus,'known','positive calls are known');
eq(at(4).calls,null,'missing calls cannot become zero');
eq(at(4).callsStatus,'missing','missing call warning');
eq(at(4).missingCalls,1,'one missing call side');
eq(at(5).calls,null,'unsafe calls cannot become zero');
eq(at(5).callsStatus,'unsafe','unsafe call warning');
eq(at(5).unsafeCalls,1,'one unsafe call side');
for(const day of [3,4,5])eq(at(day).zeroRecorded,false,'zero tokens alone are not combined zero '+day);
eq(at(4).callsExact,false,'missing calls are not exact');
eq(at(5).callsExact,false,'unsafe calls are not exact');
eq(at(6).tokenStatus,'missing','zero calls do not invent token zero');
eq(at(6).tokens,null,'missing tokens remain null');
eq(at(6).calls,'0','independent exact call zero');
eq(at(6).callsStatus,'zero','independent call zero status');
eq(at(6).intensity,null,'missing tokens do not enter scale');
eq(at(7).tokenStatus,'no-record','unrecorded final day stays in strip');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_strip_preserves_bigint_unsafe_partial_and_other_identity(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const safe=9007199254740991;
const rows=[
  {period:'2026-07-01',models:{m1:safe},model_calls:{m1:safe}},
  {period:'2026-07-01',models:{m1:safe},model_calls:{m1:safe}},
  {period:'2026-07-02',models:{m1:safe+1},model_calls:{m1:2}},
  {period:'2026-07-03',models:{m1:5},model_calls:{m1:safe+1}},
  {period:'2026-07-04',models:{m1:4,m2:safe+1},model_calls:{m1:1,m2:1}},
  {period:'2026-07-05',models:{m1:7},model_calls:{m1:1,m2:2}},
  {period:'2026-07-06',models:{other:9},model_calls:{other:1}},
];
const data=calendarPreviewData(rows,['m1','m2'],'2026-07-07','2026-07',null);
const at=day=>data.days.find(item=>item.day==='2026-07-0'+day);
eq(at(1).tokens,'18014398509481982','safe input rows sum beyond 2^53 exactly');
eq(at(1).calls,'18014398509481982','safe call rows sum beyond 2^53 exactly');
eq(at(1).tokensExact,true,'BigInt token sum remains exact');
eq(at(1).callsExact,true,'BigInt call sum remains exact');
eq(at(1).tokenStatus,'known','BigInt tokens are known');
eq(at(1).callsStatus,'known','BigInt calls are known');
eq(at(1).intensity,4,'largest trusted strip value uses top level');
eq(at(2).tokens,null,'unsafe token number is not printed exact');
eq(at(2).tokenStatus,'unsafe','unsafe token status survives');
eq(at(2).tokensExact,false,'unsafe tokens are not exact');
eq(at(2).unsafeToken,1,'unsafe token counter survives');
eq(at(2).calls,'2','unsafe tokens leave safe calls intact');
eq(at(3).tokens,'5','unsafe calls leave safe tokens intact');
eq(at(3).calls,null,'unsafe calls are not printed exact');
eq(at(3).callsStatus,'unsafe','unsafe calls remain flagged');
eq(at(3).unsafeCalls,1,'unsafe call counter survives');
eq(at(4).tokens,'4','known subtotal survives unsafe second model');
eq(at(4).tokenStatus,'unsafe','subtotal is not a trusted total');
eq(at(4).tokensExact,false,'unsafe subtotal cannot be exact');
eq(at(4).calls,'2','safe independent call total');
eq(at(4).selectedPresent,2,'both own-key identities are present');
eq(at(5).tokens,'7','known subtotal survives missing second token side');
eq(at(5).tokenStatus,'partial','missing model token side remains partial');
eq(at(5).missingToken,1,'missing token counter survives');
eq(at(5).calls,'3','independent complete call total');
for(const day of [2,4,5])eq(at(day).intensity,null,'untrusted token total stays outside scale '+day);
eq(at(6).hasAnyDayRow,true,'Other row remains evidence');
eq(at(6).hasRecord,false,'unselected Other is not another selected identity');
eq(at(6).tokenStatus,'no-record','unselected Other does not leak tokens');
const other=calendarPreviewData(rows,['other'],'2026-07-07','2026-07',null).days[5];
eq(other.hasRecord,true,'explicit Other selection retains own-key identity');
eq(other.tokens,'9','Other tokens survive projection');
eq(other.calls,'1','Other calls survive projection');
eq(other.tokenStatus,'known','Other is not treated as missing');
eq(other.intensity,4,'selected Other participates in its own strip scale');
"""
        self.assertEqual("", _run_node(script))


    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_strip_scale_is_window_relative_without_mutating_month_cells(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const safe=9007199254740991;
const rows=[
  {period:'2026-07-01',models:{m1:400},model_calls:{m1:1}},
  {period:'2026-07-10',models:{m1:25},model_calls:{m1:1}},
  {period:'2026-07-11',models:{m1:100},model_calls:{m1:1}},
  {period:'2026-07-12',models:{m1:safe+1},model_calls:{m1:1}},
  {period:'2026-07-13',models:{m1:0},model_calls:{}},
  {period:'2026-07-14',models:{m1:50},model_calls:{m1:1}},
  {period:'2026-07-15',models:{m1:75},model_calls:{m1:1}},
];
const expectedMonth=calendarMonthData(rows,['m1'],'2026-07',null);
const expectedMonthJSON=JSON.stringify(expectedMonth);
const data=calendarPreviewData(rows,['m1'],'2026-07-16','2026-07',null,null,true);
const strip=day=>data.days.find(item=>item.day==='2026-07-'+day);
eq(data.monthData.maxTokens,'400','monthly scale sees the whole month');
eq(strip('11').intensity,4,'strip maximum ignores large trusted day outside window');
eq(cell(data.monthData,'2026-07-11').intensity,1,'monthly cell keeps its own maximum');
eq(data.days.map(day=>day.intensity),[1,4,null,0,2,3,null],'strip scale excludes unsafe and absent token totals');
for(const day of data.days){
  const monthCell=cell(data.monthData,day.day);
  ok(day!==monthCell,'strip Cell is a shallow copy, not the monthly object '+day.day);
  for(const key of Object.keys(monthCell).filter(key=>key!=='intensity')){
    eq(day[key],monthCell[key],'all non-intensity Cell semantics survive '+day.day+' '+key);
  }
}
eq(JSON.stringify(data.monthData),expectedMonthJSON,'strip projection does not mutate monthly cells or weeks');
strip('11').intensity=0;
eq(cell(data.monthData,'2026-07-11').intensity,1,'consumer changes cannot alter monthly Cell intensity');
eq(JSON.stringify(data.monthData),expectedMonthJSON,'month stays unchanged after strip mutation');

const crossRows=[
  {period:'2026-06-01',models:{m1:1000},model_calls:{m1:1}},
  {period:'2026-06-30',models:{m1:25},model_calls:{m1:1}},
  {period:'2026-07-01',models:{m1:100},model_calls:{m1:1}},
  {period:'2026-07-02',models:{m1:safe+1},model_calls:{m1:1}},
  {period:'2026-07-20',models:{m1:400},model_calls:{m1:1}},
];
const cross=calendarPreviewData(crossRows,['m1'],'2026-07-03','2026-06',null,null,true);
eq(cross.days.find(day=>day.day==='2026-06-30').intensity,1,'cross-month strip uses one shared seven-day scale');
eq(cross.days.find(day=>day.day==='2026-07-01').intensity,4,'cross-month maximum is shared across both source months');
eq(cross.days.find(day=>day.day==='2026-07-02').intensity,null,'cross-month unsafe value is excluded');
eq(cross.monthData.maxTokens,'1000','expanded June retains its full-month maximum');
eq(JSON.stringify(cross.monthData),JSON.stringify(calendarMonthData(crossRows,['m1'],'2026-06',null)),
  'cross-month projection does not contaminate expanded month');
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_strip_retains_out_of_range_records_and_coverage_conflicts(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const rows=[
  {period:'2026-04-27',models:{m1:7},model_calls:{m1:1}},
  {period:'2026-04-30',models:{m1:11},model_calls:{m1:2}},
  {period:'2026-05-03',models:{m1:13},model_calls:{m1:3}},
];
const coverage={first_day:'2026-04-29',last_day:'2026-05-01'};
const range={preset:'custom',since:'2026-04-30',until:'2026-04-30'};
const data=calendarPreviewData(rows,['m1'],'2026-05-03','2026-05',coverage,range,true);
eq(data.days.map(day=>day.day),['2026-04-27','2026-04-28','2026-04-29','2026-04-30','2026-05-01','2026-05-02','2026-05-03'],
  'statistical range must not clip the date strip');
eq(data.days.map(day=>day.inRange),[false,false,false,true,false,false,false],
  'only true range membership is marked');
for(const [day,tokens,calls] of [['2026-04-27','7','1'],['2026-05-03','13','3']]){
  const item=data.days.find(item=>item.day===day);
  eq(item.tokens,tokens,'out-of-range record keeps tokens '+day);
  eq(item.calls,calls,'out-of-range record keeps calls '+day);
  eq(item.tokenStatus,'known','coverage mismatch does not erase precision '+day);
  eq(item.inCoverage,false,'outside coverage is explicit '+day);
  eq(item.outsideCoverageRecord,true,'outside coverage record remains flagged '+day);
}
const inside=data.days[3];
eq(inside.inCoverage,true,'record inside declared coverage');
eq(inside.outsideCoverageRecord,false,'inside record is not a mismatch');
eq(inside.tokens,'11','selected range day keeps recorded tokens');
eq(data.days[2].inCoverage,true,'coverage can include an unrecorded date');
eq(data.days[2].tokens,null,'coverage does not invent recorded tokens');
eq(data.monthData.boundaryMismatch,true,'expanded month retains coverage conflict');
for(const item of data.days){
  const month=calendarMonthData(rows,['m1'],item.day.slice(0,7),coverage,range);
  const original=cell(month,item.day);
  for(const key of Object.keys(original).filter(key=>key!=='intensity')){
    eq(item[key],original[key],'cross-month coverage and range semantics '+item.day+' '+key);
  }
}
for(const unknown of [null,{first_day:'2026-05-01',last_day:'2026-04-29'}]){
  const preview=calendarPreviewData(rows,['m1'],'2026-05-03','2026-05',unknown,range);
  for(const item of preview.days){
    eq(item.inCoverage,null,'absent or reversed coverage stays unknown '+item.day);
    eq(item.outsideCoverageRecord,false,'unknown coverage does not invent a conflict '+item.day);
  }
  eq(preview.days[0].tokens,'7','unknown coverage retains out-of-range record');
  eq(preview.days[6].tokens,'13','unknown coverage retains later record');
}
"""
        self.assertEqual("", _run_node(script))

    @unittest.skipUnless(HAVE_NODE, "Node.js is required")
    def test_calendar_preview_derives_each_needed_month_once_and_skips_collapsed_browse_month(self):
        script = _calendar_harness(SCRIPT.read_text(encoding="utf-8")) + r"""
const raw=[],modelReads=new Map();
for(const month of ['2026-04','2026-05','2026-06']){
  for(let index=0;index<40;index++){
    raw.push({period:month+'-'+String(index%28+1).padStart(2,'0'),models:{
      get m1(){modelReads.set(month,(modelReads.get(month)||0)+1);return 1;}
    },model_calls:{m1:1}});
  }
}
let touches=0;
const rows=new Proxy(raw,{get(target,property,receiver){
  if(typeof property==='string'&&/^\d+$/.test(property))touches++;
  return Reflect.get(target,property,receiver);
}});
function measure(end,month,expanded,expectedMonths){
  touches=0;modelReads.clear();
  const data=calendarPreviewData(rows,['m1'],end,month,null,null,expanded);
  eq(Array.from(modelReads).sort(),expectedMonths.map(key=>[key,40]).sort(),
    'each required month reads every matching token once '+end+' '+month+' '+expanded);
  eq(data.monthCount,expectedMonths.length,'reported distinct-month derivation count');
  ok(touches>=raw.length*expectedMonths.length,'every needed month scans all source rows');
  ok(touches<=raw.length*expectedMonths.length+8,
    'one row scan per distinct month, never per strip/grid Cell: '+touches+' touches');
  if(expanded){
    ok(data.monthData!==null,'expanded valid month has a grid even without a valid end');
    eq(data.monthData.valid,true,'expanded month is valid');
    eq(data.monthData.month,month,'expanded grid is the requested browse month');
  }else eq(data.monthData,null,'collapsed preview does not return a monthly grid');
  return data;
}
measure('2026-05-14','2026-05',false,['2026-05']);
measure('2026-05-14','2026-05',true,['2026-05']);
measure('2026-05-03','2026-05',false,['2026-04','2026-05']);
measure('2026-05-03','2026-04',true,['2026-04','2026-05']);
measure('2026-05-03','2026-05',true,['2026-04','2026-05']);
measure('2026-05-03','2026-06',true,['2026-04','2026-05','2026-06']);
measure('2026-05-03','2026-06',false,['2026-04','2026-05']);
measure('2026-05-14','2026-06',false,['2026-05']);
measure('2026-05-14','2026-06',true,['2026-05','2026-06']);
const collapsed=measure('not-a-day','2026-06',false,[]);
eq(collapsed.days,[],'invalid anchor has no strip days');
const expanded=measure('not-a-day','2026-06',true,['2026-06']);
eq(expanded.days,[],'expanded valid browse month does not invent strip anchor');
eq(cell(expanded.monthData,'2026-06-01').tokens,'2','invalid strip end still permits valid expanded-month data');
/* Every call above starts from raw rows: no cross-render month cache. */
"""
        self.assertEqual("", _run_node(script))


if __name__ == "__main__":
    unittest.main()
