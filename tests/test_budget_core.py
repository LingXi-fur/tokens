"""Synthetic contracts for the production monthly-budget core."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.test_dashboard_range import _extract_function

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src/tokens_cli/dashboard_assets"
HAVE_NODE = shutil.which("node") is not None


def harness():
    source = (ASSETS / "dashboard.js").read_text(encoding="utf-8")
    import re
    constants = "\n".join(re.search(rf"^const {name}=.*?;", source, re.M).group(0)
                          for name in ("ISO_DAY_RE", "DAILY_COST_MAX"))
    helpers = "\n".join(_extract_function(source, name)
                        for name in ("isoDayValid", "addISODays", "dailySafeInt"))
    assets = "\n;\n".join((ASSETS / name).read_text(encoding="utf-8")
                              for name in ("cost_core.js", "calendar_core.js", "budget_core.js"))
    return constants + "\n" + helpers + "\n" + assets + r"""
const calendar=CalendarCore.create({isoDayValid,addISODays,dailySafeInt});
const budget=BudgetCore.create({CostCore,calendar,isoDayValid});
const assert=require('node:assert/strict');
const S=1000000000000n;
const model={source:'synthetic',model:'m',identity:'m',hidden:false};
const prices={v:1,currency:'USD',reference:false,prices:{
  [CostCore.modelKey(model)]:{rates:['1','1','1','1','1'],note:''}
}};
const row=(day,amount=1000000)=>[day,0,[amount,0,0,0,0],amount,1,false];
const cost=(rows)=>({schema:1,components:CostCore.parts.slice(),models:[model],rows});
const input=(overrides={})=>({day:'2026-10-10',timezoneKnown:true,
  range:{since:null,until:null},cost:cost([row('2026-10-01'),row('2026-10-09'),row('2026-10-10',2000000)]),
  config:prices,amount:'100.00',...overrides});
const limited=(result,reason)=>{
  assert.ok(result.reasons.includes(reason),JSON.stringify(result.reasons));
  for(const key of ['remaining','percentTenths','scenario','threshold'])assert.equal(result[key],null,key);
};
"""


def run_node(body):
    result = subprocess.run(["node", "-e", harness() + body], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise AssertionError(result.stderr[-4000:])


class BudgetAssetTests(unittest.TestCase):
    def test_budget_core_exists(self):
        self.assertTrue((ASSETS / "budget_core.js").is_file())


@unittest.skipUnless(HAVE_NODE, "Node.js is required")
class BudgetCoreTests(unittest.TestCase):
    def test_strict_positive_amount_and_limits(self):
        run_node(r"""
for(const value of ['',0,null,'0','0.00','-1','+1',' 1','1 ','1,000','1e3','.50','1.','1.001','1000000.01','9'.repeat(1000)]){
  assert.equal(budget.parseAmount(value).ok,false,String(value));
}
for(const [text,expected] of [['0.01',S/100n],['001.20',S*12n/10n],['1000000.00',1000000n*S]]){
  const parsed=budget.parseAmount(text);assert.equal(parsed.ok,true);assert.equal(parsed.scaled,expected);
}
assert.equal(budget.parseAmount('001.20').text,'1.20');
""")

    def test_configuration_is_bounded_validated_and_does_not_mutate(self):
        run_node(r"""
const raw={v:1,budgets:{'2026-10':{USD:'001.20',CNY:'2'}}};
const before=JSON.stringify(raw),clean=budget.sanitizeConfig(raw);
assert.equal(clean.budgets['2026-10'].USD,'1.20');assert.equal(JSON.stringify(raw),before);
for(const value of [null,[],{}, {...raw,v:2},{...raw,extra:true},
  {v:1,budgets:{'0099-01':{USD:'2'}}},{v:1,budgets:{'2026-13':{USD:'2'}}},
  {v:1,budgets:{'2026-10':{EUR:'2'}}},{v:1,budgets:{'2026-10':{USD:'0'}}},
  JSON.parse('{"v":1,"budgets":{"__proto__":{"USD":"1"}}}')])assert.equal(budget.sanitizeConfig(value),null);
const full={v:1,budgets:{}};
for(let n=0;n<budget.maxMonths;n++)full.budgets[String(2000+Math.floor(n/12))+'-'+String(n%12+1).padStart(2,'0')]={USD:'1000000.00',CNY:'0.01'};
const fullBefore=JSON.stringify(full),accepted=budget.sanitizeConfig(full);
assert.equal(Object.keys(accepted.budgets).length,120);
assert.equal(accepted.budgets['2000-01'].USD,'1000000.00');
accepted.budgets['2000-01'].USD='2.00';
assert.equal(JSON.stringify(full),fullBefore);
const huge={v:1,budgets:{}};
for(let n=0;n<=budget.maxMonths;n++)huge.budgets[String(2000+Math.floor(n/12))+'-'+String(n%12+1).padStart(2,'0')]={USD:'1'};
assert.equal(budget.sanitizeConfig(huge),null);
""")

    def test_saved_entries_sort_and_conditional_removal_are_immutable(self):
        run_node(r"""
assert.equal(typeof budget.savedEntries,'function');
assert.equal(typeof budget.removeEntry,'function');
const raw={v:1,budgets:{'2026-09':{CNY:'2.00'},'2026-10':{CNY:'3.00',USD:'1.00'}}};
const before=JSON.stringify(raw);
assert.deepEqual(budget.savedEntries(raw),[
 {month:'2026-10',currency:'USD',amount:'1.00'},
 {month:'2026-10',currency:'CNY',amount:'3.00'},
 {month:'2026-09',currency:'CNY',amount:'2.00'}]);
const target={month:'2026-10',currency:'USD',amount:'1.00'};
const removed=budget.removeEntry(raw,target);
assert.equal(removed.ok,true);assert.deepEqual(removed.config.budgets['2026-10'],{CNY:'3.00'});
assert.equal(JSON.stringify(raw),before);
const last=budget.removeEntry(removed.config,{month:'2026-10',currency:'CNY',amount:'3.00'});
assert.equal(last.ok,true);assert.equal(Object.hasOwn(last.config.budgets,'2026-10'),false);
assert.deepEqual(last.config.budgets['2026-09'],{CNY:'2.00'});
for(const bad of [null,{}, {...target,amount:'9.00'},{...target,currency:'EUR'},{...target,month:'__proto__'},{...target,month:'2025-01',amount:undefined}]){
 assert.equal(budget.removeEntry(raw,bad).ok,false);assert.equal(JSON.stringify(raw),before);
}
assert.equal(budget.removeEntry(removed.config,target).ok,false);
assert.deepEqual(budget.savedEntries(null),[]);
""")

    def test_scenario_excludes_today_and_uses_natural_day_denominator(self):
        run_node(r"""
const result=budget.compute(input());
assert.deepEqual(result.reasons,[]);assert.equal(result.subtotal,4n*S);
assert.equal(result.todayLoaded,2n*S);assert.equal(result.closedSubtotal,2n*S);
assert.equal(result.windowDays,7);assert.equal(result.futureDays,22);
assert.equal(result.scenario.numerator,36n*S);assert.equal(result.scenario.denominator,7n);
assert.equal(result.remaining,96n*S);assert.equal(result.threshold,'normal');
assert.equal(budget.scenarioMoney(result.scenario,'USD'),'$5.14');
const changed=budget.compute(input({cost:cost([row('2026-10-01'),row('2026-10-09'),row('2026-10-10',9000000)])}));
assert.deepEqual(changed.scenario,result.scenario);assert.equal(changed.todayLoaded,9n*S);
""")

    def test_exact_thresholds_signed_remaining_and_large_sums(self):
        run_node(r"""
for(const [amount,threshold] of [[79999999,'normal'],[80000000,'warning'],[100000000,'over'],[100000001,'over']]){
 const r=budget.compute(input({cost:cost([row('2026-10-09',amount)])}));
 assert.equal(r.threshold,threshold);assert.equal(r.remaining,100n*S-BigInt(amount)*1000000n);
}
const r=budget.compute(input({cost:cost([row('2026-10-09',Number.MAX_SAFE_INTEGER),row('2026-10-09',Number.MAX_SAFE_INTEGER)])}));
assert.equal(r.subtotal,18014398509481982n*1000000n);
assert.equal(r.threshold,'over');assert.ok(r.remaining<0n);
// Round the exact rational once, not the scaled quotient before currency formatting.
assert.equal(budget.scenarioMoney({numerator:1004999999999n,denominator:1n},'USD'),'$1.00');
assert.equal(budget.scenarioMoney({numerator:1005000000000n,denominator:1n},'USD'),'$1.01');
""")

    def test_each_reliability_limit_hides_all_comparisons(self):
        run_node(r"""
limited(budget.compute(input({day:null})),'date');
limited(budget.compute(input({day:'2026-02-30'})),'date');
limited(budget.compute(input({timezoneKnown:false})),'timezone');
limited(budget.compute(input({range:{since:'2026-10-02',until:null}})),'range');
limited(budget.compute(input({range:{since:null,until:'2026-10-09'}})),'range');
limited(budget.compute(input({range:{}})),'range');
limited(budget.compute(input({cost:null})),'unsupported');
limited(budget.compute(input({cost:{...cost([]),total_incomplete:true}})),'incomplete');
limited(budget.compute(input({cost:cost([])})),'no-records');
limited(budget.compute(input({cost:cost([['bad']])})),'invalid');
limited(budget.compute(input({cost:cost([row('2026-10-09'),['2025-01-01']])})),'invalid');
limited(budget.compute(input({cost:cost([row('2026-10-09'),row('2026-02-30')])})),'invalid');
limited(budget.compute(input({cost:cost([['2026-10-09',0,[0,0,0,0,0],100,1,false]])})),'incomplete');
limited(budget.compute(input({cost:cost([['2026-10-09',0,[0,0,0,0,0],0,0,true]])})),'uncertain');
limited(budget.compute(input({cost:cost([row('2026-10-09')]),config:{...prices,prices:{}}})),'pricing');
for(const day of ['2026-10-01','2026-10-03'])limited(budget.compute(input({day,cost:cost([row(day)])})),'sample');
const unset=budget.compute(input({amount:null}));
assert.equal(unset.status,'unset');for(const key of ['remaining','percentTenths','scenario','threshold'])assert.equal(unset[key],null);
""")

    def test_zero_records_hidden_models_and_other_are_not_confused(self):
        run_node(r"""
const zero=budget.compute(input({cost:cost([row('2026-10-09',0)])}));
assert.deepEqual(zero.reasons,[]);assert.equal(zero.subtotal,0n);assert.equal(zero.remaining,100n*S);
const free=budget.compute(input({config:{...prices,prices:{[CostCore.modelKey(model)]:{rates:['0','0','0','0','0'],note:''}}}}));
assert.deepEqual(free.reasons,[]);assert.equal(free.subtotal,0n);
const hidden={...model,identity:'not-in-dashboard-filter',hidden:true};
limited(budget.compute(input({cost:{...cost([row('2026-10-09')]),models:[hidden]}})),'pricing');
const other={...model,model:'other-raw',identity:'other-identity'};
const all=budget.compute(input({cost:{...cost([row('2026-10-09'),['2026-10-09',1,[2000000,0,0,0,0],2000000,1,false]]),models:[model,other]},
 config:{...prices,prices:{...prices.prices,[CostCore.modelKey(other)]:{rates:['1','','','',''],note:''}}}}));
assert.equal(all.subtotal,3n*S);
""")

    def test_month_boundaries_leap_year_and_input_immutability(self):
        run_node(r"""
for(const [day,days,future] of [['2028-02-29',29,1],['2026-03-08',31,24],['0100-01-04',31,28],['9999-12-31',31,1]]){
 const source=input({day,cost:cost([row(day)])}),before=JSON.stringify(source);
 const r=budget.compute(source);assert.deepEqual(r.reasons,[]);assert.equal(r.daysInMonth,days);assert.equal(r.futureDays,future);
 assert.equal(JSON.stringify(source),before);
}
const r=budget.compute(input({cost:cost([row('2026-09-30',9000000),row('2026-10-09'),row('2026-10-11',9000000)])}));
assert.equal(r.subtotal,S);assert.equal(r.todayLoaded,0n);
""")


if __name__ == '__main__':
    unittest.main()
