"""Node-guarded contracts for the period-over-period core (dashboard_assets/period_core.js).

The core owns calendar expansion of day/week/month period keys and the choice of
comparable windows (whole / same-point / partial) used by the KPI delta, the
dominant-model shift badge, delta attribution and the copied view summary.
It is self-contained (no DOM, DATA, state, language or clock), so these tests
run it alone under Node and pin the edge cases directly.
"""

import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ASSETS = SRC / "tokens_cli" / "dashboard_assets"
CORE = ASSETS / "period_core.js"

sys.path.insert(0, str(SRC))
from tokens_cli import report_dashboard  # noqa: E402

HAVE_NODE = shutil.which("node") is not None


def run_node(body):
    script = CORE.read_text(encoding="utf-8") + "\nconst assert=require('node:assert/strict');\nconst P=PeriodCore;\n" + body
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", check=False)
    if result.returncode:
        raise AssertionError(result.stderr[-4000:])


class PeriodCoreAssemblyTests(unittest.TestCase):
    def test_core_is_embedded_once_before_dashboard(self):
        template = report_dashboard._TEMPLATE
        self.assertEqual(1, template.count("global.PeriodCore=Object.freeze("))
        self.assertLess(template.index("global.PeriodCore="), template.index("function deltaWindowInfo(rows)"))

    def test_core_stays_pure(self):
        source = re.sub(r"/\*.*?\*/|//[^\n]*", "", CORE.read_text(encoding="utf-8"), flags=re.S)
        for forbidden in ("document", "window.", "localStorage", "DATA", "state.", "Date.now", "dashboardLanguage"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, source)


@unittest.skipUnless(HAVE_NODE, "Node.js is required for period core contract tests")
class PeriodCoreTests(unittest.TestCase):
    def test_period_days_expansion(self):
        run_node(r"""
assert.deepEqual(P.periodDays('2026-08-03','day'),['2026-08-03']);
assert.equal(P.periodDays('2026-02-01','month').length,28);
assert.equal(P.periodDays('2024-02-01','month').length,29,'leap year');
assert.equal(P.periodDays('2026-07-01','month').at(-1),'2026-07-31');
assert.deepEqual(P.periodDays('2026-12-28','week'),
  ['2026-12-28','2026-12-29','2026-12-30','2026-12-31','2027-01-01','2027-01-02','2027-01-03']);
// DST transitions must not skip or duplicate days (pure UTC arithmetic).
assert.equal(new Set(P.periodDays('2026-03-01','month')).size,31);
assert.equal(new Set(P.periodDays('2026-11-01','month')).size,30);
assert.deepEqual(P.periodDays('2026-07','month'),[],'month keys are first-of-month ISO days');
assert.deepEqual(P.periodDays('2026-02-30','week'),[]);
assert.ok(Object.isFrozen(P));
""")

    def test_whole_window_without_range_uses_row_totals(self):
        run_node(r"""
const w=P.comparisonWindow({gran:'month',currentPeriod:'2026-07-01',previousPeriod:'2026-06-01',generated:'2026-08-26',coverageUntil:null});
assert.deepEqual(w,{mode:'whole',currentDays:null,previousDays:null});
""")

    def test_open_period_aligns_same_point(self):
        run_node(r"""
const w=P.comparisonWindow({gran:'month',currentPeriod:'2026-08-01',previousPeriod:'2026-07-01',generated:'2026-08-26'});
assert.equal(w.mode,'same-point');
assert.equal(w.currentDays.length,25);
assert.equal(w.currentDays.at(-1),'2026-08-25');
assert.equal(w.previousDays.at(-1),'2026-07-25');
// Generated day on the first day of the period: nothing elapsed yet.
assert.equal(P.comparisonWindow({gran:'week',currentPeriod:'2026-08-24',previousPeriod:'2026-08-17',generated:'2026-08-24'}),null);
// An open day is never compared.
assert.equal(P.comparisonWindow({gran:'day',currentPeriod:'2026-08-26',previousPeriod:'2026-08-25',generated:'2026-08-26'}),null);
// Coverage ending before the generated day closes the period.
assert.equal(P.comparisonWindow({gran:'month',currentPeriod:'2026-08-01',previousPeriod:'2026-07-01',generated:'2026-08-26',coverageUntil:'2026-08-20'}).mode,'whole');
""")

    def test_open_long_month_against_short_previous_month(self):
        run_node(r"""
const w=P.comparisonWindow({gran:'month',currentPeriod:'2026-03-01',previousPeriod:'2026-02-01',generated:'2026-03-31'});
assert.equal(w.currentDays.length,30);
assert.equal(w.previousDays.length,28,'offsets past the shorter month are dropped');
assert.equal(w.previousDays.at(-1),'2026-02-28');
""")

    def test_range_clipped_period_is_partial_same_calendar_offset(self):
        run_node(r"""
const scope=['2026-08-10','2026-08-11','2026-08-12'];
const w=P.comparisonWindow({gran:'month',currentPeriod:'2026-08-01',previousPeriod:'2026-07-01',generated:'2026-10-01',scopeDays:scope});
assert.deepEqual(w,{mode:'partial',currentDays:scope,previousDays:['2026-07-10','2026-07-11','2026-07-12']});
assert.equal(P.comparisonWindow({gran:'month',currentPeriod:'2026-08-01',previousPeriod:'2026-07-01',scopeDays:[]}),null);
// Open + clipped: same-point wins and drops the generated day itself.
const open=P.comparisonWindow({gran:'week',currentPeriod:'2026-08-24',previousPeriod:'2026-08-17',generated:'2026-08-27',
  scopeDays:['2026-08-25','2026-08-26','2026-08-27']});
assert.deepEqual(open,{mode:'same-point',currentDays:['2026-08-25','2026-08-26'],previousDays:['2026-08-18','2026-08-19']});
""")

    def test_range_whole_period_keeps_full_previous_days(self):
        run_node(r"""
// Regression: the whole-period range path once mapped previous days by offset,
// so a 28-day February dropped January 29-31 from the per-model split while
// the headline total still summed all of January.
const feb=P.periodDays('2026-02-01','month');
const w=P.comparisonWindow({gran:'month',currentPeriod:'2026-02-01',previousPeriod:'2026-01-01',generated:'2026-05-01',scopeDays:feb});
assert.equal(w.mode,'whole');
assert.equal(w.currentDays.length,28);
assert.equal(w.previousDays.length,31);
assert.equal(w.previousDays.at(-1),'2026-01-31');
""")

    def test_percent_attribution_and_dominant_shift(self):
        run_node(r"""
assert.equal(P.percentChange(150,100),50);
assert.equal(P.percentChange(50,100),-50);
assert.equal(P.percentChange(10,0),null);
assert.equal(P.percentChange(10,undefined),null);
const parts=P.attributionParts({a:90,b:55},{a:80,b:20,c:5},['a','b','c']);
assert.deepEqual(parts.map(p=>p.model),['b','a','c']);
assert.equal(parts.reduce((s,p)=>s+p.delta,0),(90+55)-(80+20+5));
// Equal magnitude ties break by model name.
assert.deepEqual(P.attributionParts({x:5,y:0},{x:0,y:5},['y','x']).map(p=>p.model),['x','y']);
assert.deepEqual(P.dominantShift({a:30,b:70},{a:80,b:20}),{from:'a',to:'b'});
assert.equal(P.dominantShift({a:90,b:10},{a:80,b:20}),null);
assert.equal(P.dominantShift({},{a:1}),null);
// Ties keep insertion order, matching dashboard topModelOf(models,false).
assert.deepEqual(P.topModel({b:5,a:5}),['b',5]);
""")


if __name__ == "__main__":
    unittest.main()
