"""Node-guarded contracts for the insight core (dashboard_assets/insight_core.js).

The core owns the math behind three overview insights: today-vs-yesterday at the
same time of day, the per-day model share stream, and the activity calendar with
streak statistics. It is self-contained (no DOM, DATA, state, language or clock),
so these tests run it alone under Node and pin the edge cases directly.
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
CORE = ASSETS / "insight_core.js"

sys.path.insert(0, str(SRC))
from tokens_cli import report_dashboard  # noqa: E402

HAVE_NODE = shutil.which("node") is not None


def run_node(body):
    script = (CORE.read_text(encoding="utf-8")
              + "\nconst assert=require('node:assert/strict');\nconst I=InsightCore;\n"
              + "const close=(a,b,msg)=>assert.ok(Math.abs(a-b)<1e-9,(msg||'')+' '+a+' != '+b);\n"
              + body)
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", check=False)
    if result.returncode:
        raise AssertionError(result.stderr[-4000:])


class InsightCoreAssemblyTests(unittest.TestCase):
    def test_core_is_embedded_once_before_dashboard(self):
        template = report_dashboard._TEMPLATE
        self.assertEqual(1, template.count("global.InsightCore=Object.freeze("))
        self.assertLess(template.index("global.InsightCore="), template.index("function renderPaceRace()"))
        self.assertLess(template.index("global.PeriodCore="), template.index("global.InsightCore="))

    def test_core_stays_pure(self):
        source = re.sub(r"/\*.*?\*/|//[^\n]*", "", CORE.read_text(encoding="utf-8"), flags=re.S)
        for forbidden in ("document", "window.", "localStorage", "DATA", "state.", "Date.now",
                          "new Date()", "dashboardLanguage", "fetch(", "XMLHttpRequest"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, source)


@unittest.skipUnless(HAVE_NODE, "Node.js is required for insight core contract tests")
class InsightCoreTests(unittest.TestCase):
    def test_dates_and_continuous_days(self):
        run_node(r"""
assert.ok(Object.isFrozen(I));
assert.equal(I.weekdayMonday('2026-11-09'),0,'Monday');
assert.equal(I.weekdayMonday('2026-11-15'),6,'Sunday');
assert.equal(I.addDays('2026-12-31',1),'2027-01-01');
const feb=I.continuousDays('2024-02-27','2024-03-01');
assert.deepEqual(feb,['2024-02-27','2024-02-28','2024-02-29','2024-03-01']);
// DST transitions must not skip or duplicate days (pure UTC arithmetic).
assert.equal(new Set(I.continuousDays('2026-03-01','2026-03-31')).size,31);
assert.deepEqual(I.continuousDays('2026-03-02','2026-03-01'),[],'reversed');
assert.deepEqual(I.continuousDays('2026-02-30','2026-03-01'),[],'invalid');
assert.equal(I.continuousDays('2000-01-01','2026-01-01').length,1500,'capped');
""")

    def test_pace_race_prorates_the_cutoff_hour(self):
        run_node(r"""
const zero=()=>new Array(24).fill(0);
const today=zero(),yesterday=zero();
today[9]=100;today[10]=50;         // hour 10 is the in-progress hour
yesterday[9]=60;yesterday[10]=120;yesterday[20]=300;
const r=I.paceRace({today,yesterday,hour:10,minute:30});
assert.equal(r.today.total,150);
close(r.yesterday.atCutoff,60+120*30/60,'half of the cutoff hour');
assert.equal(r.yesterday.total,480);
close(r.delta,(150-120)/120*100);
assert.equal(r.lead,'ahead');
close(r.projection,150*480/120);
assert.equal(r.cutoff,10.5);
assert.equal(r.today.cum.length,12,'cum through the cutoff hour');
assert.equal(r.today.cum[10],100);
assert.equal(r.today.cum[11],150);
assert.equal(r.yesterday.cum.length,25);
assert.equal(r.baseline,null);
// At minute 0 yesterday's cutoff hour contributes nothing.
close(I.paceRace({today,yesterday,hour:10,minute:0}).yesterday.atCutoff,60);
""")

    def test_pace_race_lead_states_and_crossover(self):
        run_node(r"""
const zero=()=>new Array(24).fill(0);
const y=zero();y[2]=100;
const behind=zero();behind[2]=40;
assert.equal(I.paceRace({today:behind,yesterday:y,hour:5,minute:0}).lead,'behind');
const even=zero();even[2]=100.2;
assert.equal(I.paceRace({today:even,yesterday:y,hour:5,minute:0}).lead,'even','within 0.5%');
const fresh=zero();fresh[1]=10;
const n=I.paceRace({today:fresh,yesterday:zero(),hour:5,minute:0});
assert.equal(n.lead,'new');assert.equal(n.delta,null);assert.equal(n.projection,null);
const idle=I.paceRace({today:zero(),yesterday:y,hour:1,minute:0});
assert.equal(idle.lead,'idle');
// Today overtakes yesterday at the 4 o'clock boundary.
const slow=zero();slow[3]=150;
assert.equal(I.paceRace({today:slow,yesterday:y,hour:6,minute:0}).crossover,4);
assert.equal(I.paceRace({today:behind,yesterday:y,hour:6,minute:0}).crossover,null);
// Invalid clocks and sanitised inputs.
assert.equal(I.paceRace({today:y,yesterday:y,hour:24,minute:0}),null);
assert.equal(I.paceRace({today:y,yesterday:y,hour:-1,minute:0}),null);
const dirty=I.paceRace({today:[NaN,-5,'7',Infinity],yesterday:null,hour:3,minute:99});
assert.equal(dirty.today.total,7);assert.equal(dirty.minute,0);assert.equal(dirty.yesterday.total,0);
""")

    def test_pace_race_baseline_is_the_hourly_average(self):
        run_node(r"""
const day=v=>{const a=new Array(24).fill(0);a[8]=v;return a;};
const r=I.paceRace({today:day(300),yesterday:day(100),baseline:[day(100),day(200),day(300)],hour:12,minute:0});
assert.equal(r.baseline.days,3);
close(r.baseline.atCutoff,200);
close(r.baseline.total,200);
close(r.baseline.delta,50);
assert.equal(r.baseline.cum.length,25);
""")

    def test_share_stream_shares_sum_to_one(self):
        run_node(r"""
const days=['2026-01-01','2026-01-02','2026-01-03'];
const rows={'2026-01-01':{a:30,b:10},'2026-01-03':{a:5,b:15,c:0}};
const s=I.shareStream({days,rows,models:['b','a','c','a'],mode:'share',smooth:1});
assert.equal(s.mode,'share');
assert.deepEqual(s.layers.map(l=>l.model),['b','a'],'catalog order, absent models dropped, duplicates ignored');
assert.deepEqual(s.totals,[40,0,20]);
assert.deepEqual(s.raw[1],{b:0,a:0,c:0},'gap day keeps zero raw values');
close(s.layers[0].y0[0],0);close(s.layers[0].y1[0],.25);
close(s.layers[1].y0[0],.25);close(s.layers[1].y1[0],1);
assert.deepEqual([s.layers[0].y1[1],s.layers[1].y1[1]],[0,0],'empty day collapses to zero');
close(s.layers[1].y1[2],1);
assert.deepEqual(s.domain,[0,1]);
assert.equal(s.layers[0].peak.day,'2026-01-03');
close(s.layers[0].peak.share,.75);
""")

    def test_share_stream_centered_smoothing_and_volume_baseline(self):
        run_node(r"""
const days=I.continuousDays('2026-01-01','2026-01-05');
const rows={};days.forEach((d,i)=>rows[d]={a:i===2?100:0,b:10});
const s=I.shareStream({days,rows,models:['a','b'],mode:'volume',smooth:3});
assert.equal(s.smooth,3);
// Centred window: day 0 averages days 0..1, day 2 averages days 1..3.
const a=s.layers.find(l=>l.model==='a'),b=s.layers.find(l=>l.model==='b');
close(a.y1[0]-a.y0[0],0,'day 0 sees only days 0..1');
close(a.y1[1]-a.y0[1],100/3);
close(a.y1[2]-a.y0[2],100/3);
close(a.y1[4]-a.y0[4],0);
// Silhouette baseline: each day is centred on zero.
days.forEach((_,i)=>close(a.y0[i]+b.y1[i],0,'symmetric day '+i));
close(s.max,100/3+10);
assert.deepEqual(s.domain,[-s.max/2,s.max/2]);
// Raw values are never smoothed.
assert.equal(s.raw[2].a,100);assert.equal(s.totals[2],110);
// Window clamps and unknown modes fall back to share.
const t=I.shareStream({days,rows,models:['a'],mode:'nope',smooth:99});
assert.equal(t.mode,'share');assert.equal(t.smooth,30);
assert.equal(I.shareStream({days:[],rows,models:['a']}).layers.length,0);
""")

    def test_activity_calendar_grid_shape(self):
        run_node(r"""
// 2026-11-10 is a Tuesday: the last column holds Monday and Tuesday only.
const totals={'2026-11-10':50,'2026-11-09':10,'2026-11-01':5,'2026-08-01':999};
const c=I.activityCalendar({totals,endDay:'2026-11-10',weeks:3,first:'2026-10-30'});
assert.equal(c.weeks,3);
assert.equal(c.start,'2026-10-26');
assert.equal(c.cells.length,7*2+2);
assert.equal(c.cells.at(-1).day,'2026-11-10');
assert.equal(c.cells.at(-1).col,2);assert.equal(c.cells.at(-1).row,1);
assert.ok(c.cells.every(cell=>cell.day<='2026-11-10'),'no future cells');
assert.equal(c.cells[0].row,0);assert.equal(I.weekdayMonday(c.cells[0].day),0);
assert.ok(c.cells.find(cell=>cell.day==='2026-10-29').outside,'before report start');
assert.ok(!c.cells.find(cell=>cell.day==='2026-10-30').outside);
// Nov 1 is the Sunday of the first column, so November labels column 0 and October is not repeated.
assert.deepEqual(c.months.map(m=>[m.col,m.month]),[[0,'2026-11']]);
// When the first month start is far from column 0, the starting month is labelled too.
const long=I.activityCalendar({totals,endDay:'2026-11-10',weeks:10});
assert.deepEqual(long.months.map(m=>[m.col,m.month]),[[0,'2026-09'],[3,'2026-10'],[7,'2026-11']]);
assert.equal(I.activityCalendar({totals,endDay:'bad',weeks:3}),null);
assert.equal(I.activityCalendar({totals,endDay:'2026-11-10',weeks:500}).weeks,60);
""")

    def test_activity_levels_use_quartiles_of_active_days(self):
        run_node(r"""
const totals={};
['2026-03-02','2026-03-03','2026-03-04','2026-03-05','2026-03-06'].forEach((d,i)=>totals[d]=[1,2,3,4,1000][i]);
const c=I.activityCalendar({totals,endDay:'2026-03-08',weeks:2});
const level=d=>c.cells.find(cell=>cell.day===d).level;
assert.equal(level('2026-03-01'),0,'empty day');
assert.equal(level('2026-03-02'),1);
assert.equal(level('2026-03-04'),2);
assert.equal(level('2026-03-05'),3);
assert.equal(level('2026-03-06'),4,'a single spike does not flatten the rest');
assert.deepEqual(c.cuts,[2,3,4]);
""")

    def test_streaks_busiest_day_and_weekday(self):
        run_node(r"""
const totals={'2026-05-01':5,'2026-05-02':5,'2026-05-03':5,'2026-05-05':40,'2026-05-06':1,'2026-05-07':0,'2026-05-08':2,'2026-05-09':3};
const s=I.streakStats(totals,'2026-05-10','2026-05-01');
assert.equal(s.activeDays,7);
assert.equal(s.spanDays,10);
assert.deepEqual(s.longest,{length:3,start:'2026-05-01',end:'2026-05-03'},'earliest longest run wins ties');
// endDay has no usage yet: the current run counts from the day before.
assert.deepEqual(s.current,{length:2,start:'2026-05-08',end:'2026-05-09',pendingToday:true});
assert.deepEqual(s.busiest,{day:'2026-05-05',total:40});
assert.equal(s.topWeekday,1,'2026-05-05 is a Tuesday');
const t=I.streakStats(totals,'2026-05-09','2026-05-01');
assert.equal(t.current.pendingToday,false);assert.equal(t.current.length,2);
const none=I.streakStats({'2026-05-01':0},'2026-05-03',null);
assert.equal(none.activeDays,0);assert.equal(none.current.length,0);assert.equal(none.current.start,null);
assert.equal(none.busiest,null);assert.equal(none.topWeekday,null);assert.equal(none.spanDays,null);
// Days after endDay never count.
assert.equal(I.streakStats({'2026-05-04':9},'2026-05-03',null).activeDays,0);
""")


if __name__ == "__main__":
    unittest.main()
