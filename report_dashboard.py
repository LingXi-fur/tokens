"""交互式自包含 HTML dashboard。

单个 HTML：数据内嵌为 `const DATA = {...}`，vanilla JS 渲染内联 SVG。
零依赖、无 CDN、双击即开、可邮件分发；亮/暗双色自动跟随系统。

设计原则（见 frontend-ui-engineering skill）：
- 统一间距/圆角刻度，单一阴影层级；不堆砌渐变与圆角。
- 微交互有目的：KPI 数字 count-up、总量迷你折线、柱子生长动画、悬停/聚焦反馈。
- 按日/周/月均为堆叠柱状图（带数值标签与背景轨道）。
"""
import json
import os
from datetime import datetime, timedelta

import config
import readers
import aggregate
import report_term

# 协调分类色：同明度/饱和，主色锁定品牌蓝，其余仅在多模型时出现。
PALETTE = ["#5b8def", "#14b8a6", "#f59e0b", "#a78bfa",
           "#f472b6", "#38bdf8", "#fb923c", "#94a3b8"]


def _global_models(recs):
    totals = {}
    for r in recs:
        totals[r["model"]] = totals.get(r["model"], 0) + r["total"]
    cols = []
    for m in report_term.PRIORITY_MODELS:
        if m in totals:
            cols.append(m)
    for m, _ in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
        if m not in cols:
            cols.append(m)
    pretty = {m: config.pretty_model(m) for m in cols}
    return cols, pretty


def _pack(rows):
    return [{"period": p, "total": s["total"], "calls": s["calls"], "models": dict(s["by_model"])}
            for p, s in rows]


def _short_cwd(p):
    parts = str(p).replace("\\", "/").rstrip("/").split("/")
    return "/".join(parts[-2:]) or str(p)


def _top_with_models(records, key, limit=6):
    """Rank entities with total and per-model token amounts."""
    buckets = {}
    for r in records:
        ident = r.get(key)
        if not ident:
            continue
        item = buckets.setdefault(ident, {"total": 0, "models": {}})
        total = r.get("total", 0) or 0
        model = r.get("model") or "unknown"
        item["total"] += total
        item["models"][model] = item["models"].get(model, 0) + total
    ranked = sorted(buckets.items(), key=lambda kv: kv[1]["total"], reverse=True)
    return [(ident, stats["total"], dict(stats["models"]))
            for ident, stats in ranked[:limit]]


def _flow_data(records, summaries):
    """Aggregate real project→model and model→session token flows."""
    project_model = {}
    model_session = {}
    session_ids = set()
    for r in records:
        total = r.get("total", 0) or 0
        model = r.get("model") or "unknown"
        cwd = r.get("cwd")
        sid = r.get("session")
        if cwd:
            key = (cwd, model)
            project_model[key] = project_model.get(key, 0) + total
        if sid:
            key = (model, sid)
            model_session[key] = model_session.get(key, 0) + total
            session_ids.add(sid)
    labels = {
        sid: summaries.get(sid) or readers.session_title(sid) or str(sid)[:8]
        for sid in session_ids
    }
    return {
        "project_model": [
            [_short_cwd(cwd), cwd, model, total]
            for (cwd, model), total in sorted(
                project_model.items(), key=lambda item: item[1], reverse=True
            )
        ],
        "model_session": [
            [model, labels[sid], sid, total]
            for (model, sid), total in sorted(
                model_session.items(), key=lambda item: item[1], reverse=True
            )
        ],
    }


def build_payload(records, since=None, until=None, sources=None):
    recs = aggregate.filter_range(records, since=since, until=until)
    models, pretty = _global_models(recs)
    colors = {m: PALETTE[i % len(PALETTE)] for i, m in enumerate(models)}
    cache_read = sum(r.get("cache_read", 0) or 0 for r in recs)
    # 24 小时活动分布（本地时区），用于径向作息时钟
    hourly = [0] * 24
    for r in recs:
        h = readers.local_hour(r.get("ts"))
        if h is not None:
            hourly[h] += r["total"]
    # 近 5 小时（6 个小时桶，生成时刻往前）——「计费窗口」快照
    gen = datetime.now(config.TZ)
    dh = {}
    for r in recs:
        dt = readers.parse_local_dt(r.get("ts"))
        if dt:
            dh[(dt.date().isoformat(), dt.hour)] = dh.get((dt.date().isoformat(), dt.hour), 0) + r["total"]
    buckets = []
    for i in range(5, -1, -1):
        t = gen - timedelta(hours=i)
        buckets.append({"h": t.hour, "total": dh.get((t.date().isoformat(), t.hour), 0)})
    summaries = readers.load_session_summaries()
    # 每日细节：供「时光探针」聚焦后重算作息、缓存与 Top 榜。
    # 只嵌入聚合值，不暴露会话正文；仍保持单文件、纯离线。
    by_day_records = {}
    for r in recs:
        by_day_records.setdefault(r["date"], []).append(r)
    day_details = {}
    for day, day_recs in by_day_records.items():
        day_hourly = [0] * 24
        day_hourly_models = {}
        for r in day_recs:
            h = readers.local_hour(r.get("ts"))
            if h is not None:
                day_hourly[h] += r["total"]
                mh = day_hourly_models.setdefault(r["model"], [0] * 24)
                mh[h] += r["total"]
        day_top_sessions = []
        for sid, total, model_totals in _top_with_models(day_recs, "session", 6):
            label = summaries.get(sid) or readers.session_title(sid) or str(sid)[:8]
            day_top_sessions.append([label, total, sid, model_totals])
        day_details[day] = {
            "hourly": day_hourly,
            "hourly_models": day_hourly_models,
            "cache_read": sum(r.get("cache_read", 0) or 0 for r in day_recs),
            "top_cwds": [[_short_cwd(p), t, p, model_totals]
                         for p, t, model_totals in _top_with_models(day_recs, "cwd", 6)],
            "top_sessions": day_top_sessions,
            "flow": _flow_data(day_recs, summaries),
        }
    top_cwds = [[_short_cwd(p), t, p, model_totals]
                for p, t, model_totals in _top_with_models(recs, "cwd", 6)]
    top_sessions = []
    for sid, t, model_totals in _top_with_models(recs, "session", 6):
        label = summaries.get(sid) or readers.session_title(sid) or str(sid)[:8]
        top_sessions.append([label, t, sid, model_totals])
    # 流光图中的任意会话都可点击回放；逐轮序列最多保留最近 200 轮。
    by_sess = {}
    for r in recs:
        sid = r.get("session")
        if sid:
            by_sess.setdefault(sid, []).append(r)
    session_series = {}
    for sid, records_for_session in by_sess.items():
        arr = sorted(records_for_session, key=lambda r: r.get("ts") or "")
        session_series[sid] = [r["total"] for r in arr][-200:]
    # 徽章用的全局计数
    n_cwds = len({r.get("cwd") for r in recs if r.get("cwd")})
    n_sessions = len({sid for sid in by_sess})
    max_turns = max((len(v) for v in by_sess.values()), default=0)
    # 成就图鉴用的细粒度数字聚合；不嵌入会话正文。
    session_totals = {sid: sum(r["total"] for r in rs) for sid, rs in by_sess.items()}
    cwd_totals = {}
    source_totals = {}
    model_stats = {}
    for r in recs:
        cwd = r.get("cwd")
        source = r.get("source") or "unknown"
        model = r.get("model") or "unknown"
        if cwd:
            cwd_totals[cwd] = cwd_totals.get(cwd, 0) + r["total"]
        source_totals[source] = source_totals.get(source, 0) + r["total"]
        ms = model_stats.setdefault(model, {"input": 0, "output": 0, "cache_read": 0,
                                            "cache_write": 0, "calls": 0})
        ms["input"] += r.get("input", 0) or 0
        ms["output"] += r.get("output", 0) or 0
        ms["cache_read"] += r.get("cache_read", 0) or 0
        ms["cache_write"] += r.get("cache_write", 0) or 0
        ms["calls"] += 1
    achievement_stats = {
        "input": sum(r.get("input", 0) or 0 for r in recs),
        "output": sum(r.get("output", 0) or 0 for r in recs),
        "cache_write": sum(r.get("cache_write", 0) or 0 for r in recs),
        "session_totals": sorted(session_totals.values(), reverse=True),
        "cwd_totals": sorted(cwd_totals.values(), reverse=True),
        "source_totals": source_totals,
        "model_stats": model_stats,
        "first_day": min((r["date"] for r in recs), default=None),
        "last_day": max((r["date"] for r in recs), default=None),
    }
    return {
        "generated": datetime.now(config.TZ).strftime("%Y-%m-%d %H:%M"),
        "source": sources or [],
        "range": {"since": since, "until": until},
        "models": models,
        "pretty": pretty,
        "colors": colors,
        "cache_read": cache_read,
        "hourly": hourly,
        "day_details": day_details,
        "block": {"total": sum(b["total"] for b in buckets), "buckets": buckets},
        "top_cwds": top_cwds,
        "top_sessions": top_sessions,
        "session_series": session_series,
        "flow": _flow_data(recs, summaries),
        "n_cwds": n_cwds,
        "n_sessions": n_sessions,
        "max_turns": max_turns,
        "achievement_stats": achievement_stats,
        "day": _pack(aggregate.by_day(recs)),
        "week": _pack(aggregate.by_week(recs)),
        "month": _pack(aggregate.by_month(recs)),
    }


_TEMPLATE = r"""<!doctype html>
<html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Token 用量 Dashboard</title>
<style>
:root{
  --bg:#f6f8fa; --surface:#ffffff; --surface-2:#f0f3f7;
  --ink:#1c2128; --muted:#5a6573; --faint:#8b95a4;
  --border:#e3e8ee; --border-2:#d2dae3;
  --accent:#2f6fd6; --accent-2:#5b8def; --accent-soft:rgba(47,111,214,.12);
  --track:#eef1f5; --good:#14b8a6;
  --shadow:0 1px 2px rgba(16,24,40,.04),0 6px 20px rgba(16,24,40,.06);
  --r-card:18px; --r-tile:14px; --r-bar:4px;
  --glass:rgba(255,255,255,.72); --glass-2:rgba(255,255,255,.55); --glass-brd:rgba(255,255,255,.7);
  --blob-a:rgba(91,141,239,.34); --blob-b:rgba(167,139,250,.28); --blob-c:rgba(20,184,166,.22);
  --hero-grad:linear-gradient(120deg,var(--accent),#a78bfa 60%,#f472b6);
  color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme=light]){
    --bg:#0b0e14; --surface:#141a24; --surface-2:#1c2330;
    --ink:#e6edf3; --muted:#8b949e; --faint:#6e7681;
    --border:#222932; --border-2:#30363d;
    --accent:#5b8def; --accent-2:#7aa2f7; --accent-soft:rgba(91,141,239,.16);
    --track:#1a212b; --good:#2dd4bf;
    --shadow:0 1px 0 rgba(255,255,255,.03) inset,0 10px 30px rgba(0,0,0,.45);
    --glass:rgba(22,27,36,.74); --glass-2:rgba(28,35,48,.62); --glass-brd:rgba(255,255,255,.08);
    --blob-a:rgba(91,141,239,.46); --blob-b:rgba(167,139,250,.34); --blob-c:rgba(45,212,191,.24);
    --hero-grad:linear-gradient(120deg,#7aa2f7,#a78bfa 60%,#f472b6);
    color-scheme:dark;
  }
}
/* 手动强制暗色（覆盖系统） */
:root[data-theme=dark]{
  --bg:#0b0e14; --surface:#141a24; --surface-2:#1c2330;
  --ink:#e6edf3; --muted:#8b949e; --faint:#6e7681;
  --border:#222932; --border-2:#30363d;
  --accent:#5b8def; --accent-2:#7aa2f7; --accent-soft:rgba(91,141,239,.16);
  --track:#1a212b; --good:#2dd4bf;
  --shadow:0 1px 0 rgba(255,255,255,.03) inset,0 10px 30px rgba(0,0,0,.45);
  color-scheme:dark;
}

*{box-sizing:border-box}
html,body{margin:0}
body{
  color:var(--ink);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  padding:32px 24px 64px; -webkit-font-smoothing:antialiased;
  position:relative; min-height:100vh; overflow-x:hidden;
}
/* 动态渐变光晕底（mesh）——给页面「活」感 */
body::before{
  content:""; position:fixed; inset:-20vmax; z-index:-2; background:var(--bg);
}
body::after{
  content:""; position:fixed; inset:0; z-index:-1; pointer-events:none;
  background:
    radial-gradient(40vmax 40vmax at 12% 8%, var(--blob-a), transparent 60%),
    radial-gradient(38vmax 38vmax at 88% 12%, var(--blob-b), transparent 60%),
    radial-gradient(42vmax 42vmax at 70% 95%, var(--blob-c), transparent 60%);
  filter:blur(6px); opacity:1; animation:drift 44s ease-in-out infinite alternate;
}
@keyframes drift{ 0%{transform:translate3d(0,0,0) scale(1)} 50%{transform:translate3d(2vmax,-2vmax,0) scale(1.06)} 100%{transform:translate3d(-2vmax,1vmax,0) scale(1.02)} }
/* 注：drift 动画在 .clock 外层 body::after 上，周期见下 */
.wrap{max-width:1160px;margin:0 auto;position:relative;perspective:1600px}

/* header */
header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:24px}
.brand{display:flex;align-items:center;gap:12px;min-width:0}
.logo{width:36px;height:36px;border-radius:10px;flex:none;background:var(--accent);
  display:grid;place-items:center;color:#fff;font-weight:700;font-size:14px;letter-spacing:.3px;
  box-shadow:0 4px 12px var(--accent-soft)}
h1{font-size:20px;margin:0;font-weight:700;letter-spacing:.1px}
.sub{color:var(--muted);font-size:12.5px;margin-top:2px}
.seg{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;color:var(--muted);
  background:var(--surface);border:1px solid var(--border);padding:6px 12px;border-radius:999px}
.seg .led{width:7px;height:7px;border-radius:50%;background:var(--accent-2);box-shadow:0 0 0 3px var(--accent-soft)}
.status-pulse{cursor:pointer;transition:border-color .15s,background .15s}.status-pulse:hover{border-color:var(--border-2);background:var(--glass-2)}.status-pulse .led{animation:statusBeat 2.4s ease-in-out infinite}.status-pulse.warming .led{background:#a78bfa}.status-pulse.steady .led{background:#7b8797}.status-pulse.cooling .led{background:#5b8def}@keyframes statusBeat{50%{transform:scale(1.3);box-shadow:0 0 0 5px var(--accent-soft)}}

.head-tools{display:inline-flex;align-items:center;gap:8px}
.section-dock{position:sticky;top:8px;z-index:44;display:flex;align-items:center;gap:6px;overflow:visible;margin:0 0 16px;padding:6px;background:var(--glass);border:1px solid var(--glass-brd);border-radius:12px;box-shadow:var(--shadow);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}.section-links{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}.section-links::-webkit-scrollbar{display:none}.section-dock button{flex:none;border:0;background:transparent;color:var(--muted);border-radius:8px;padding:6px 12px;font:600 12px/1.2 inherit;cursor:pointer;white-space:nowrap}.section-dock button:hover{color:var(--ink);background:var(--surface-2)}.section-dock button.on{color:var(--accent-2);background:var(--accent-soft)}
.view-wrap{position:relative;margin-left:auto;flex:none}.view-capsule{display:inline-flex!important;align-items:center;gap:7px;background:var(--surface-2)!important;border:1px solid var(--border)!important;color:var(--ink)!important}.view-capsule::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--accent-2);box-shadow:0 0 0 3px var(--accent-soft)}.view-capsule.dirty::before{background:#a78bfa}.view-pop{position:absolute;right:0;top:42px;width:min(330px,calc(100vw - 48px));padding:14px;background:var(--glass);border:1px solid var(--glass-brd);border-radius:14px;box-shadow:var(--shadow);backdrop-filter:blur(20px);display:none}.view-pop.open{display:block;animation:rise .18s ease both}.view-pop h3{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:0 0 8px}.view-summary{font-size:12.5px;color:var(--muted);line-height:1.7}.view-summary b{color:var(--ink)}.view-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.view-actions .ghostbtn{padding:8px 10px}
[id^=section-]{scroll-margin-top:112px}
.themebtn{width:34px;height:34px;border-radius:9px;border:1px solid var(--border);
  background:var(--surface);color:var(--ink);cursor:pointer;font-size:15px;line-height:1;
  display:grid;place-items:center;transition:border-color .15s,transform .12s}
.themebtn:hover{border-color:var(--border-2);transform:translateY(-1px)}
.themebtn:active{transform:translateY(0)}

/* 数据天气 + 时光探针：让统计页拥有自己的「气候」与时间轴 */
.weather{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:16px;padding:18px 22px;overflow:hidden;position:relative}
.discovery{position:relative;overflow:hidden;padding:20px 22px;background:linear-gradient(115deg,var(--glass),var(--glass-2));cursor:pointer}.discovery::after{content:"✦";position:absolute;right:20px;top:3px;font-size:74px;color:var(--accent-soft);transform:rotate(12deg)}.disc-kicker{font-size:9.5px;letter-spacing:.17em;color:var(--accent-2);font-weight:800}.disc-text{font-size:17px;line-height:1.55;font-weight:700;max-width:830px;margin-top:6px}.disc-sub{font-size:11.5px;color:var(--faint);margin-top:5px}.disc-actions{position:absolute;right:18px;bottom:15px;z-index:1;display:flex;align-items:center;gap:7px}.disc-pos{font-size:11px;color:var(--faint);font-variant-numeric:tabular-nums}.disc-pin.on{color:var(--accent-2);border-color:var(--accent-2);background:var(--accent-soft)}.discovery.pinned{cursor:default}.discovery.pinned .disc-kicker::after{content:" · 已固定";color:var(--muted)}
.weather::after{content:"";position:absolute;right:-40px;top:-70px;width:190px;height:190px;border-radius:50%;background:radial-gradient(circle,var(--weather-glow,var(--blob-a)),transparent 67%);pointer-events:none}
.w-icon{font-size:38px;line-height:1;filter:drop-shadow(0 5px 12px var(--accent-soft));animation:wfloat 4s ease-in-out infinite}
@keyframes wfloat{50%{transform:translateY(-4px) rotate(2deg)}}
.w-title{font-size:16px;font-weight:800;letter-spacing:.01em}.w-title small{font-size:10px;color:var(--faint);font-weight:700;letter-spacing:.12em;margin-left:8px}
.w-copy{font-size:12.5px;color:var(--muted);margin-top:3px;max-width:720px}
.w-metric{text-align:right;font-variant-numeric:tabular-nums;color:var(--muted);font-size:11px;z-index:1}.w-metric b{display:block;color:var(--ink);font-size:19px}
.probe{position:sticky;top:64px;z-index:40;display:none;align-items:center;gap:12px;margin:0 0 16px;padding:10px 14px;border-radius:12px;background:rgba(20,26,36,.88);color:#edf4ff;border:1px solid rgba(122,162,247,.35);box-shadow:0 10px 30px rgba(0,0,0,.2);backdrop-filter:blur(18px)}
.probe.on{display:flex;animation:rise .2s ease both}.probe-orb{width:9px;height:9px;border-radius:50%;background:#7aa2f7;box-shadow:0 0 0 5px rgba(122,162,247,.13),0 0 18px #7aa2f7}.probe-copy{flex:1;font-size:12.5px}.probe-copy b{font-size:13px}.probe button{border:0;background:rgba(255,255,255,.1);color:#fff;width:27px;height:27px;border-radius:8px;cursor:pointer}
@media(max-width:640px){.weather{grid-template-columns:auto 1fr}.w-metric{grid-column:1/-1;text-align:left;display:flex;gap:8px;align-items:baseline}.w-metric b{display:inline}.w-icon{font-size:30px}}

/* card */
.card{background:var(--glass);backdrop-filter:blur(18px) saturate(1.25);-webkit-backdrop-filter:blur(18px) saturate(1.25);
  border:1px solid var(--glass-brd);border-radius:var(--r-card);padding:22px;margin-bottom:16px;
  box-shadow:var(--shadow);animation:rise .5s cubic-bezier(.2,.75,.2,1) both;transition:transform .28s ease;transform-style:preserve-3d}
.card:nth-child(2){animation-delay:.04s}.card:nth-child(3){animation-delay:.08s}
.card:nth-child(4){animation-delay:.12s}.card:nth-child(5){animation-delay:.16s}
@keyframes rise{from{opacity:0;transform:translateY(12px)}}
.grad{background:var(--hero-grad);-webkit-background-clip:text;background-clip:text;
  -webkit-text-fill-color:transparent;color:transparent;filter:drop-shadow(0 3px 14px var(--accent-soft))}
.card h2{font-size:11px;color:var(--muted);margin:0 0 14px;font-weight:600;
  letter-spacing:.08em;text-transform:uppercase}
.row-between{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}

/* kpi */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:16px}
.kpi{position:relative;background:var(--glass-2);border:1px solid var(--glass-brd);border-radius:var(--r-tile);padding:16px 18px;overflow:hidden;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}
.kpi .v{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.05;letter-spacing:-.5px;white-space:nowrap}
.kpi.is-primary .v{font-size:34px}
.kpi.is-primary{box-shadow:var(--shadow),0 0 40px -8px var(--blob-a)}
.kpi.is-primary::after{content:"";position:absolute;right:-30px;top:-30px;width:120px;height:120px;border-radius:50%;background:radial-gradient(circle,var(--blob-a),transparent 70%);pointer-events:none}
.kpi .v small{font-size:13px;color:var(--faint);font-weight:600;margin-left:5px}
.kpi .l{color:var(--muted);font-size:12.5px;margin-top:10px;letter-spacing:.01em}
.kpi .spark{position:absolute;right:14px;bottom:14px;width:96px;height:30px;opacity:.9}
.kpi.is-primary::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent)}
@media(max-width:720px){.kpis{grid-template-columns:repeat(2,1fr)} .kpi .spark{display:none}}

/* 环比 Δ、缓存燃料条、均值 μ、峰值旗、Top 排行榜 —— 标新立异的小巧思 */
.delta{display:inline-block;margin-left:8px;font-size:11px;font-weight:700;padding:2px 8px;border-radius:99px;vertical-align:3px;letter-spacing:.02em}
.delta.up{color:var(--accent-2);background:var(--accent-soft)}
.delta.down{color:var(--muted);background:var(--track)}
.gauge{margin-top:10px;height:8px;background:var(--track);border-radius:99px;overflow:hidden;position:relative}
.gauge i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent-2));border-radius:99px;transition:width .9s cubic-bezier(.2,.75,.2,1);box-shadow:0 0 8px var(--accent-soft)}
.mean-line{stroke:var(--accent-2);stroke-width:1;stroke-dasharray:3 4;opacity:.55}
.mean-lab{fill:var(--accent-2);font-size:11px;font-style:italic;font-weight:700}
.barstack.peak{filter:drop-shadow(0 0 5px var(--accent-2))}
.barstack.focused{filter:drop-shadow(0 0 9px var(--accent));opacity:1}
.barstack.muted{opacity:.25}
.barstack{cursor:crosshair}.barstack:focus{outline:none}.barstack:focus .seg{filter:brightness(1.12);stroke:var(--ink);stroke-width:.8}.barstack:focus .bar-focus{stroke:var(--accent-2);stroke-width:2;stroke-dasharray:5 3}.bar-hit{fill:transparent;pointer-events:all}.bar-focus{fill:transparent;pointer-events:none}
.ghostbar{fill:none;stroke:var(--faint);stroke-width:1.2;stroke-dasharray:4 3;opacity:.65;pointer-events:none}
.delta-tag{fill:var(--muted);font-size:8.5px;font-weight:700}
.comparebtn.on{color:var(--accent-2);border-color:var(--accent-2);background:var(--accent-soft)}
.peak-flag{fill:var(--accent);font-size:9px;font-weight:700;letter-spacing:.05em}
.lb-row{display:grid;grid-template-columns:30px 1fr 80px 50px;align-items:center;gap:10px;padding:7px 0}.lb-row[role=button]{border-radius:9px}.lb-row[role=button]:focus{outline:2px solid var(--accent-2);outline-offset:2px}.lb-comp{grid-column:2/5;display:flex;height:3px;border-radius:99px;overflow:hidden;background:var(--track);margin-top:-4px}.lb-comp i{height:100%}.lb-dom{grid-column:2/5;font-size:9.5px;color:var(--faint);margin-top:-5px}
.rk{font:700 13px/1 ui-monospace,"SF Mono",Menlo,monospace;color:var(--accent-2);font-variant-numeric:tabular-nums}
.lb-row:first-child .rk{color:var(--accent);text-shadow:0 0 10px var(--accent-soft)}
.lb-name{font-size:12px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:ui-monospace,"SF Mono",Menlo,monospace}
.lb-bar{position:relative;height:8px;background:var(--track);border-radius:99px;overflow:hidden}
.lb-bar i{position:absolute;inset:0 auto 0 0;background:linear-gradient(90deg,var(--accent),var(--accent-2));border-radius:99px;transform-origin:left;animation:groww .7s cubic-bezier(.2,.75,.2,1) both}
.lb-val{font-size:11.5px;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
@keyframes groww{from{transform:scaleX(0)}}
.top2{display:grid;grid-template-columns:1fr 1fr;gap:28px}
@media(max-width:760px){.top2{grid-template-columns:1fr}}

/* 作息时钟（径向 24h）、CSV 按钮、预测行 */
.clock{width:100%;max-width:260px;height:auto;display:block;margin:0 auto}
.clk-tick{stroke:var(--border-2);stroke-width:1}
.clk-h{fill:var(--faint);font-size:9px;font-variant-numeric:tabular-nums}
.clk-spoke{stroke:var(--accent-2);stroke-linecap:round;transition:stroke .12s}
.clk-spoke.peak{stroke:var(--accent);filter:drop-shadow(0 0 4px var(--accent-2))}
.clk-core{fill:var(--surface);stroke:var(--border)}
.clk-center{fill:var(--ink);font-size:15px;font-weight:700;font-variant-numeric:tabular-nums}
.clk-sub{fill:var(--faint);font-size:8.5px;letter-spacing:.12em}
.fc{display:block;font-size:11px;color:var(--faint);margin-top:3px}
.ghostbtn{background:var(--surface-2);border:1px solid var(--border);color:var(--muted);
  font-size:12px;font-weight:600;padding:6px 12px;border-radius:8px;cursor:pointer;transition:.15s}
.ghostbtn:hover{color:var(--accent-2);border-color:var(--accent-2);box-shadow:0 0 0 3px var(--accent-soft)}
.share-actions{display:flex;gap:8px;flex-wrap:wrap}.share-modal{position:fixed;inset:0;z-index:97;background:rgba(0,0,0,.62);backdrop-filter:blur(8px);display:none;align-items:center;justify-content:center;padding:20px}.share-modal.open{display:flex}.share-sheet{position:relative;max-width:94vw;max-height:92vh;overflow:auto}.share-close{position:absolute;right:-12px;top:-12px;z-index:3;width:32px;height:32px;border-radius:50%;border:1px solid rgba(255,255,255,.25);background:#151a24;color:white;font-size:20px;cursor:pointer}.passport{width:720px;min-height:430px;border-radius:24px;padding:34px;color:#ecf4ff;background:radial-gradient(circle at 85% 15%,rgba(167,139,250,.35),transparent 30%),linear-gradient(135deg,#0b1220,#172b4e 60%,#102237);border:1px solid rgba(255,255,255,.16);box-shadow:0 30px 80px rgba(0,0,0,.5);font-family:ui-monospace,"SF Mono",Menlo,monospace;position:relative;overflow:hidden}.passport::after{content:"";position:absolute;inset:0;background:repeating-linear-gradient(120deg,transparent 0 18px,rgba(255,255,255,.018) 18px 20px);pointer-events:none}.pass-head{display:flex;justify-content:space-between;align-items:flex-start}.pass-head h3{font-size:25px;margin:4px 0;letter-spacing:.08em}.pass-k{font-size:10px;letter-spacing:.22em;color:#8faed1}.pass-id{font-size:11px;color:#8faed1;text-align:right}.pass-grid{display:grid;grid-template-columns:1.2fr 1fr;gap:28px;margin-top:30px}.pass-hero{font-size:40px;font-weight:900;line-height:1.05;letter-spacing:-.04em}.pass-sub{color:#94a9c4;margin-top:8px}.pass-fields{display:grid;grid-template-columns:1fr 1fr;gap:14px}.pass-field span{display:block;font-size:9px;color:#7890ad;letter-spacing:.12em}.pass-field b{display:block;font-size:15px;margin-top:3px}.pass-foot{display:flex;justify-content:space-between;align-items:flex-end;margin-top:30px;padding-top:18px;border-top:1px dashed rgba(255,255,255,.2);font-size:10px;color:#8198b5}.barcode{font:28px/1 monospace;letter-spacing:-4px;color:#cfe0f8}.receipt{width:390px;min-height:570px;padding:30px 25px;background:#f3efe4;color:#1f2328;box-shadow:0 25px 70px rgba(0,0,0,.45);font:13px/1.55 ui-monospace,"SF Mono",Menlo,monospace;position:relative}.receipt::before,.receipt::after{content:"";position:absolute;left:0;right:0;height:12px;background:radial-gradient(circle at 6px 0,transparent 5px,#f3efe4 5.5px) repeat-x;background-size:12px 12px}.receipt::before{top:-11px;transform:rotate(180deg)}.receipt::after{bottom:-11px}.receipt h3{text-align:center;font-size:19px;letter-spacing:.15em;margin:0}.receipt-center{text-align:center}.receipt hr{border:0;border-top:1px dashed #555;margin:16px 0}.receipt-row{display:flex;justify-content:space-between;gap:14px}.receipt-row b{text-align:right}.receipt-total{font-size:18px;font-weight:900}.receipt-code{text-align:center;font-size:25px;letter-spacing:-5px;margin:18px 0 8px}.receipt-note{text-align:center;font-size:10px;color:#5d6268}

/* 趣味交互：toast、confetti 彩蛋、趣味换算、hero 跟手光斑 */
#toast{position:fixed;left:50%;bottom:28px;transform:translate(-50%,24px);z-index:99;
  background:var(--glass);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  border:1px solid var(--glass-brd);color:var(--ink);padding:11px 18px;border-radius:999px;
  font-size:13px;font-weight:600;box-shadow:var(--shadow);opacity:0;pointer-events:none;transition:.28s}
#toast.show{opacity:1;transform:translate(-50%,0)}
.confetti{position:fixed;top:-16px;width:9px;height:14px;border-radius:2px;z-index:98;opacity:.92;
  animation:fall 2.1s cubic-bezier(.3,.6,.5,1) forwards}
@keyframes fall{to{transform:translateY(108vh) rotate(560deg);opacity:0}}
.ff{display:flex;align-items:baseline;gap:12px;padding:9px 0;border-bottom:1px dashed var(--border)}
.ff:last-child{border-bottom:0}
.ff-n{font-size:23px;font-weight:800;font-variant-numeric:tabular-nums;background:var(--hero-grad);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.ff-l{color:var(--muted);font-size:13.5px}
.kpi.is-primary{cursor:pointer;grid-column:span 2;background:radial-gradient(150px circle at var(--mx,30%) var(--my,25%),var(--accent-soft),var(--glass-2) 72%)}
@media(max-width:720px){.kpi.is-primary{grid-column:span 2}}
.logo{cursor:pointer;transition:transform .35s cubic-bezier(.2,.75,.2,1)}
.logo:hover{transform:rotate(-8deg) scale(1.06)}
.logo.spin{transform:rotate(360deg) scale(1.08)}

/* 模块开关 popover */
.popover{position:absolute;top:46px;right:0;z-index:50;background:var(--glass);backdrop-filter:blur(18px);
  -webkit-backdrop-filter:blur(18px);border:1px solid var(--glass-brd);border-radius:14px;padding:14px 16px;
  box-shadow:var(--shadow);min-width:230px;display:none}
.popover.open{display:block;animation:rise .18s ease both}
.popover h3{font-size:11px;color:var(--muted);margin:0 0 8px;text-transform:uppercase;letter-spacing:.07em}
.mrow{display:flex;align-items:center;justify-content:space-between;padding:7px 0;font-size:13px;color:var(--ink)}
.mrow label{display:flex;align-items:center;gap:9px;cursor:pointer}
.switch{position:relative;width:34px;height:20px;background:var(--track);border-radius:99px;transition:.2s;flex:none}
.switch::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#fff;transition:.2s;box-shadow:0 1px 3px rgba(0,0,0,.3)}
.switch.on{background:var(--accent)}.switch.on::after{left:16px}
.mrow input{display:none}

/* 命令面板 Cmd+K */
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.45);backdrop-filter:blur(3px);z-index:90;display:none;align-items:flex-start;justify-content:center;padding-top:12vh}
.scrim.open{display:flex;animation:fade .15s ease}
@keyframes fade{from{opacity:0}}
.palette{width:min(560px,92vw);background:var(--glass);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);
  border:1px solid var(--glass-brd);border-radius:16px;box-shadow:var(--shadow);overflow:hidden;animation:rise .2s ease both}
.palette input{width:100%;border:0;background:transparent;color:var(--ink);font-size:16px;padding:16px 18px;outline:none;border-bottom:1px solid var(--border)}
.palette ul{list-style:none;margin:0;padding:8px;max-height:52vh;overflow:auto}
.palette li{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:10px;font-size:14px;cursor:pointer;color:var(--ink)}
.palette li.active,.palette li:hover{background:var(--accent-soft)}
.palette li .ic{width:20px;text-align:center;color:var(--accent-2)}
.palette li .k{margin-left:auto;font-size:11px;color:var(--faint);font-family:ui-monospace,Menlo,monospace}
.palette .empty{padding:20px;text-align:center;color:var(--faint);font-size:13px}

/* 快捷键帮助 */
.help-modal{position:fixed;inset:0;z-index:94;background:rgba(0,0,0,.5);backdrop-filter:blur(5px);display:none;align-items:center;justify-content:center;padding:20px}.help-modal.open{display:flex;animation:fade .15s ease}.help-sheet{width:min(620px,94vw);max-height:86vh;overflow:auto;background:var(--glass);border:1px solid var(--glass-brd);border-radius:18px;box-shadow:var(--shadow);backdrop-filter:blur(22px);padding:20px}.help-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.help-head h3{margin:0;font-size:17px}.help-close{width:32px;height:32px;border:0;border-radius:9px;background:var(--surface-2);color:var(--muted);font-size:20px;cursor:pointer}.help-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px 18px;margin-top:16px}.help-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid var(--border);font-size:12.5px;color:var(--muted)}.help-row kbd{flex:none;font:700 11px/1 ui-monospace,Menlo,monospace;color:var(--ink);background:var(--surface-2);border:1px solid var(--border);border-bottom-color:var(--border-2);border-radius:6px;padding:5px 7px;box-shadow:0 1px 0 var(--border-2)}

/* 5h 计费块 */
.block-bars{display:flex;align-items:flex-end;gap:8px;height:60px;margin-top:10px}
.bb{flex:1;background:linear-gradient(var(--accent-2),var(--accent));border-radius:5px 5px 0 0;min-height:3px;transition:height .6s cubic-bezier(.2,.75,.2,1);position:relative}
.bb span{position:absolute;bottom:-17px;left:0;right:0;text-align:center;font-size:9.5px;color:var(--faint)}
.block-now{font-size:13px;color:var(--muted);margin-top:22px}

/* 作息织锦：14 日 × 24 小时的时间纹理 */
.rhythm{overflow-x:auto;padding-bottom:4px}
.rhythm-grid{display:grid;grid-template-columns:38px repeat(14,minmax(34px,1fr));gap:4px;min-width:650px;align-items:center}
.rh-day{font-size:9.5px;color:var(--faint);text-align:center;font-variant-numeric:tabular-nums}.rh-hour{font-size:9px;color:var(--faint);text-align:right;padding-right:5px;font-variant-numeric:tabular-nums}
.rh-cell{height:8px;border-radius:3px;background:var(--track);transition:transform .12s,filter .12s,opacity .12s;cursor:crosshair}
.rh-cell:hover{transform:scale(1.65);filter:brightness(1.15);z-index:2;box-shadow:0 0 8px var(--accent-soft)}
.rh-tip{position:fixed;z-index:120;pointer-events:none;min-width:174px;padding:10px 12px;border-radius:11px;background:rgba(15,20,29,.94);color:#edf4ff;border:1px solid rgba(122,162,247,.3);box-shadow:0 12px 36px rgba(0,0,0,.34);backdrop-filter:blur(16px);opacity:0;transform:translate(12px,12px) scale(.96);transition:opacity .1s,transform .1s;font-size:11.5px;font-variant-numeric:tabular-nums}
.rh-tip.on{opacity:1;transform:translate(12px,12px) scale(1)}.rh-tip b{display:block;font-size:13px;margin-bottom:3px}.rh-tip span{color:#9ba9bc}.rh-tip .rh-v{color:#9dbaff;font-weight:800;font-size:15px;margin-right:4px}
.rh-cell.l1{background:color-mix(in srgb,var(--accent) 24%,var(--track))}.rh-cell.l2{background:color-mix(in srgb,var(--accent) 45%,var(--track))}.rh-cell.l3{background:color-mix(in srgb,var(--accent) 68%,var(--track))}.rh-cell.l4{background:var(--accent)}
.rh-foot{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-top:14px;flex-wrap:wrap}.persona{font-size:13px;color:var(--muted)}.persona b{color:var(--ink);font-size:15px}.rh-legend{display:flex;align-items:center;gap:5px;color:var(--faint);font-size:10px}.rh-legend i{width:12px;height:8px;border-radius:3px;background:var(--track)}
.model-mark,.slice,.mp{transition:opacity .18s,transform .18s,filter .18s;transform-origin:center}.model-dim{opacity:.12!important;filter:saturate(.2)}.model-hot{filter:brightness(1.12) drop-shadow(0 0 5px var(--accent-soft));transform:translateY(-2px)}

/* 每模型迷你趋势 */
.mp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.mp{background:var(--glass-2);border:1px solid var(--glass-brd);border-radius:12px;padding:10px 12px}
.mp .nm{font-size:11.5px;color:var(--muted);display:flex;align-items:center;gap:6px;overflow:hidden;white-space:nowrap}
.mp .nm i{width:8px;height:8px;border-radius:2px;flex:none}
.mp .vt{font-size:16px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:3px}
.mp svg{width:100%;height:32px;display:block;margin-top:4px}

/* Token 生物：数据驱动的数字生命 */
.creature-stage{display:flex;align-items:center;justify-content:center;min-height:270px;position:relative;background:radial-gradient(circle at 50% 48%,var(--accent-soft),transparent 50%);border-radius:14px;overflow:hidden}.creature-stage::before{content:"";position:absolute;inset:0;background-image:radial-gradient(circle,rgba(255,255,255,.4) 0 1px,transparent 1.5px);background-size:43px 37px;opacity:.18}.creature{width:260px;height:260px;filter:drop-shadow(0 18px 20px rgba(0,0,0,.22));animation:creatureFloat 5s ease-in-out infinite}.creature-eye{animation:blink 5s infinite;transform-origin:center}@keyframes creatureFloat{50%{transform:translateY(-7px) rotate(1deg)}}@keyframes blink{0%,45%,49%,100%{transform:scaleY(1)}47%{transform:scaleY(.08)}}.creature-info{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}.creature-info div{background:var(--glass-2);border:1px solid var(--glass-brd);border-radius:10px;padding:9px;text-align:center;font-size:10px;color:var(--faint)}.creature-info b{display:block;color:var(--ink);font-size:12px;margin-bottom:2px}.creature-name{text-align:center;font-size:17px;font-weight:800;margin-top:12px}.creature-desc{text-align:center;color:var(--muted);font-size:11.5px;margin-top:3px}

/* Token 流光图：项目→模型→会话的真实流向 */
.flow-shell{position:relative;min-height:470px;border-radius:14px;overflow-x:auto;overflow-y:hidden;background:radial-gradient(circle at 50% 50%,rgba(91,141,239,.13),transparent 30%),linear-gradient(160deg,rgba(8,13,27,.96),rgba(17,26,48,.96));border:1px solid rgba(122,162,247,.14)}.flow-shell::before{content:"";position:absolute;inset:0;background-image:radial-gradient(circle,rgba(226,237,255,.45) 0 .7px,transparent 1px);background-size:31px 29px;opacity:.14;pointer-events:none}.flow-map{position:relative;width:100%;height:auto;display:block;z-index:1;min-width:900px}.flow-col{fill:#8fa3c0;font-size:10px;font-weight:800;letter-spacing:.14em}.flow-link{fill:none;stroke-linecap:round;opacity:.32;transition:opacity .16s,filter .16s}.flow-link.hot{opacity:.92;filter:drop-shadow(0 0 5px currentColor)}.flow-link.dim{opacity:.045}.flow-node{cursor:pointer;transition:opacity .16s,filter .16s,transform .16s;transform-box:fill-box;transform-origin:center}.flow-node:hover,.flow-node:focus,.flow-node.locked{filter:brightness(1.16) drop-shadow(0 0 7px currentColor);transform:scale(1.04);outline:none}.flow-node.dim{opacity:.18;filter:saturate(.25)}.flow-hit{fill:transparent;stroke:transparent;pointer-events:all}.flow-box{stroke:rgba(255,255,255,.7);stroke-width:1}.flow-node text{fill:#e1ecfb;font-size:10px;font-weight:700;pointer-events:none}.flow-node .flow-value{fill:#9badc7;font-size:8.5px;font-weight:600}.flow-panel{position:absolute;left:16px;bottom:16px;z-index:3;max-width:min(420px,calc(100% - 32px));background:rgba(8,12,22,.86);color:#dce9ff;border:1px solid rgba(122,162,247,.25);border-radius:12px;padding:11px 13px;backdrop-filter:blur(15px);font-size:11px;box-shadow:0 10px 28px rgba(0,0,0,.28)}.flow-panel b{display:block;font-size:13px;color:#fff;margin-bottom:2px}.flow-panel span{color:#9badc7}.flow-stats{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.flow-stats span{font-size:10px;color:var(--faint);background:var(--glass-2);border:1px solid var(--glass-brd);border-radius:999px;padding:4px 8px}.flow-link.motion{stroke-dasharray:5 9;animation:flowDash 8s linear infinite}@keyframes flowDash{to{stroke-dashoffset:-70}}

/* 柱图竞赛 */
.race{display:flex;flex-direction:column;gap:7px;margin-top:10px}
.race-row{display:grid;grid-template-columns:96px 1fr 56px;align-items:center;gap:10px;font-size:12.5px}
.race-name{display:flex;align-items:center;gap:6px;overflow:hidden;white-space:nowrap}
.race-name i{width:8px;height:8px;border-radius:2px;flex:none}
.race-bar{height:18px;background:var(--track);border-radius:6px;overflow:hidden;position:relative}
.race-bar i{position:absolute;left:0;top:0;bottom:0;border-radius:6px;transition:width .45s cubic-bezier(.2,.75,.2,1)}
.race-val{font-size:11.5px;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
.race-ctrl{display:flex;align-items:center;gap:12px;margin-top:10px;font-size:12px;color:var(--faint)}
.rbtn{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:6px 14px;font-size:12px;font-weight:600;cursor:pointer}
.rbtn:hover{filter:brightness(1.08)}
.rscrub{flex:1;accent-color:var(--accent);min-width:120px}

/* 成就徽章 */
.badges{display:flex;flex-wrap:wrap;gap:16px;margin-top:8px}
.badge{display:flex;flex-direction:column;align-items:center;width:74px;text-align:center}
.badge .ring{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;font-size:23px;
  background:var(--glass-2);border:1px solid var(--glass-brd);position:relative;transition:.2s}
.badge.on .ring{background:radial-gradient(circle,var(--accent-soft),var(--glass-2));border-color:var(--accent-2);
  box-shadow:0 0 18px -3px var(--accent-2);animation:pop .5s cubic-bezier(.2,1.5,.4,1) both}
@keyframes pop{0%{transform:scale(.3);opacity:0}}
.badge .nm{font-size:11px;color:var(--ink);margin-top:7px;font-weight:700}
.badge .dc{font-size:9.5px;color:var(--faint);line-height:1.25;margin-top:1px}
.badge.off .ring{filter:grayscale(1) opacity(.45)}
.badge.off .ring::after{content:"🔒";position:absolute;font-size:10px;right:-3px;bottom:-3px}
.badge-count{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums}
.badge-count b{font-size:19px;color:var(--accent-2)}
.tier{margin-bottom:16px}.tier:last-child{margin-bottom:0}
.tier-h{display:flex;align-items:center;justify-content:space-between;font-size:11px;color:var(--faint);margin-bottom:9px;letter-spacing:.06em;text-transform:uppercase}
.tier-h b{color:var(--ink)}
.tier-c{font-variant-numeric:tabular-nums;color:var(--muted)}
.badge.tier-bronze.on .ring{border-color:#c08457;background:radial-gradient(circle,rgba(192,132,87,.30),var(--glass-2));box-shadow:0 0 14px -4px #c08457}
.badge.tier-silver.on .ring{border-color:#b8c0cc;background:radial-gradient(circle,rgba(184,192,204,.32),var(--glass-2));box-shadow:0 0 16px -4px #b8c0cc}
.badge.tier-gold.on .ring{border-color:#f0b429;background:radial-gradient(circle,rgba(240,180,41,.34),var(--glass-2));box-shadow:0 0 20px -3px #f0b429}
.badge.tier-prismatic.on .ring{border-color:transparent;background:conic-gradient(from 0deg,#5b8def,#a78bfa,#f472b6,#14b8a6,#5b8def);box-shadow:0 0 26px -2px rgba(167,139,250,.7)}
.badge.secret .ring{background:repeating-linear-gradient(45deg,var(--glass-2),var(--glass-2) 4px,var(--track) 4px,var(--track) 8px)}
.badge{width:62px}
.badge .ring{width:46px;height:46px;font-size:20px}
.cat{margin-bottom:2px}
.cat-h{display:flex;align-items:center;gap:9px;font-size:12.5px;font-weight:700;color:var(--ink);cursor:pointer;padding:9px 0;border-top:1px solid var(--border);user-select:none}
.cat-h .ce{font-size:15px}
.cat-h .cc{margin-left:auto;font-size:11.5px;color:var(--faint);font-variant-numeric:tabular-nums}
.cat-h .cc b{color:var(--accent-2)}
.cat-h .chev{color:var(--faint);transition:transform .2s;font-size:10px;margin-left:4px}
.cat.collapsed .cat-grid{display:none}
.cat.collapsed .chev{transform:rotate(-90deg)}
.cat-grid{display:flex;flex-wrap:wrap;gap:14px 12px;padding:10px 0 14px}
/* 成就：主页紧凑卡 + 进度环 + 随机滚动条 */
.ach-compact{display:flex;align-items:center;gap:22px;margin-top:8px}
.ach-ring{display:flex;flex-direction:column;align-items:center;gap:10px;flex:none;width:108px}
.ach-ring-disc{position:relative;width:104px;height:104px}
.ach-ring .pct{position:absolute;inset:0;display:grid;place-items:center;font-size:24px;font-weight:800;font-variant-numeric:tabular-nums;background:var(--hero-grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.ach-ringlab{font-size:11px;color:var(--faint);text-align:center;line-height:1.5}
.ach-ringlab b{color:var(--ink);font-size:12.5px}
.ach-tiers{display:flex;flex-direction:column;gap:9px;margin-top:18px}
.trow{display:grid;grid-template-columns:54px 1fr 50px;align-items:center;gap:12px;font-size:11.5px}
.tl{color:var(--muted);font-weight:600;display:flex;align-items:center;gap:6px}
.tl i{width:9px;height:9px;border-radius:2px;flex:none}
.tbar{height:8px;background:var(--track);border-radius:99px;overflow:hidden}
.tbar j{display:block;height:100%;border-radius:99px;transition:width .9s cubic-bezier(.2,.75,.2,1)}
.tv{font-variant-numeric:tabular-nums;color:var(--faint);text-align:right;font-size:11px}
.ach-info{flex:1;min-width:0}
.ach-meta2{font-size:12.5px;color:var(--muted);margin-bottom:10px}
.ach-meta2 b{color:var(--accent-2);font-size:15px}
.ach-strip{display:flex;gap:12px;overflow:hidden;min-height:78px;mask-image:linear-gradient(90deg,transparent,#000 6%,#000 94%,transparent);-webkit-mask-image:linear-gradient(90deg,transparent,#000 6%,#000 94%,transparent)}
.ach-strip .badge{flex:none;animation:slideIn .45s cubic-bezier(.2,.75,.2,1) both}
@keyframes slideIn{from{opacity:0;transform:translateY(10px) scale(.9)}}
.ach-open{margin-top:14px}
/* 全屏成就页 */
.ach-modal{position:fixed;inset:0;z-index:96;background:rgba(0,0,0,.55);backdrop-filter:blur(6px);display:none;align-items:center;justify-content:center;padding:24px}
.ach-modal.open{display:flex;animation:fade .15s ease}
.ach-sheet{width:min(920px,96vw);max-height:88vh;display:flex;flex-direction:column;background:var(--glass);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);border:1px solid var(--glass-brd);border-radius:18px;box-shadow:var(--shadow);animation:rise .25s ease both;overflow:hidden}
.ach-top{padding:20px 22px 14px;border-bottom:1px solid var(--border);position:relative}
.ach-top h3{margin:0;font-size:18px;padding-right:30px}
.ach-top .x{position:absolute;top:16px;right:18px;background:none;border:0;color:var(--muted);font-size:24px;cursor:pointer;line-height:1}
.ach-top .x:hover{color:var(--ink)}
.ach-bar{display:flex;align-items:center;gap:12px;margin-top:12px}
.ach-search{flex:1;background:var(--surface-2);border:1px solid var(--border);color:var(--ink);border-radius:10px;padding:9px 13px;font-size:13px;outline:none}
.ach-search:focus{border-color:var(--accent-2)}
.ach-filter{background:var(--surface-2);border:1px solid var(--border);color:var(--ink);border-radius:10px;padding:8px 10px;font-size:12px;outline:none}
.ach-filter:focus{border-color:var(--accent-2)}
.ach-stats{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px;font-size:11px;color:var(--faint)}.ach-stats b{color:var(--ink)}
.ach-body{padding:6px 22px 22px;overflow:auto}
.ach-body .cat-h{position:sticky;top:0;background:var(--glass);z-index:2;padding-left:0;padding-right:0}
/* 解锁正反馈：金辉 / 彩钻流光 */
.badge.tier-prismatic.on .ring{animation:pop .5s cubic-bezier(.2,1.5,.4,1) both,hue 6s linear infinite .6s}
.badge.tier-gold.on .ring{animation:pop .5s cubic-bezier(.2,1.5,.4,1) both,goldpulse 2.6s ease-in-out infinite .6s}
@keyframes hue{to{filter:hue-rotate(360deg)}}
@keyframes goldpulse{0%,100%{filter:brightness(1)}50%{filter:brightness(1.22) saturate(1.18)}}

/* Token 星云：用量分布生成的彩色数据深空 */
.dna-wrap{display:flex;flex-direction:column;align-items:center;gap:12px;margin-top:6px}
.dna{width:300px;height:300px;max-width:100%;overflow:visible;filter:drop-shadow(0 16px 30px rgba(31,41,78,.22))}
.nebula-stage{width:100%;min-height:330px;display:grid;place-items:center;position:relative;border-radius:14px;overflow:hidden;background:radial-gradient(circle at 50% 45%,rgba(91,141,239,.15),transparent 34%),radial-gradient(circle at 30% 70%,rgba(244,114,182,.08),transparent 28%),linear-gradient(160deg,rgba(8,13,27,.96),rgba(17,26,48,.96));border:1px solid rgba(122,162,247,.13)}
.nebula-stage::before{content:"";position:absolute;inset:0;background-image:radial-gradient(circle,rgba(226,237,255,.55) 0 .7px,transparent 1px);background-size:29px 31px;opacity:.22;animation:starDrift 35s linear infinite}
@keyframes starDrift{to{background-position:58px 62px}}
.nebula-core{animation:corePulse 3.8s ease-in-out infinite;transform-origin:center}@keyframes corePulse{50%{transform:scale(1.08);opacity:.86}}
.nebula-arm{transform-origin:150px 150px;animation:nebulaTurn 90s linear infinite}.nebula-arm:nth-of-type(2n){animation-direction:reverse;animation-duration:120s}@keyframes nebulaTurn{to{transform:rotate(360deg)}}
.nebula-particle{transition:r .18s,opacity .18s;cursor:crosshair}.nebula-particle:hover{r:6;opacity:1;filter:drop-shadow(0 0 5px currentColor)}
.nebula-meta{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;width:100%}.nebula-meta div{border:1px solid var(--glass-brd);background:var(--glass-2);border-radius:9px;padding:7px;text-align:center;font-size:9.5px;color:var(--faint)}.nebula-meta b{display:block;color:var(--ink);font-size:11.5px}.dna-tip{font-size:11px;color:var(--faint);text-align:center}.dnadl{background:var(--surface-2);border:1px solid var(--border);color:var(--muted);font-size:12px;font-weight:600;padding:6px 12px;border-radius:8px;cursor:pointer}.dnadl:hover{color:var(--accent-2);border-color:var(--accent-2)}

/* 会话回放弹层 */
.modal{position:fixed;inset:0;background:rgba(0,0,0,.5);backdrop-filter:blur(4px);z-index:95;display:none;align-items:center;justify-content:center;padding:20px}
.modal.open{display:flex;animation:fade .15s ease}
.sheet{position:relative;width:min(720px,94vw);background:var(--glass);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);
  border:1px solid var(--glass-brd);border-radius:18px;box-shadow:var(--shadow);padding:22px;animation:rise .22s ease both}
.sheet h3{margin:0;font-size:16px;padding-right:30px}
.sheet .ecg{width:100%;height:160px;display:block;margin-top:14px}
.sheet .x{position:absolute;top:14px;right:16px;background:none;border:0;color:var(--muted);font-size:20px;cursor:pointer;line-height:1}
.sheet .x:hover{color:var(--ink)}
.rp-ctrl{display:flex;align-items:center;gap:12px;margin-top:14px;font-size:12px;color:var(--faint)}
.rp-scrub{flex:1}.replay-stats{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.replay-stats span{font-size:10.5px;color:var(--muted);padding:4px 8px;border-radius:999px;background:var(--surface-2);border:1px solid var(--border)}

/* 今日运势 */
.fortune{display:flex;flex-direction:column;gap:11px;margin-top:8px}
.f-head{display:flex;align-items:baseline;gap:14px}
.f-grade{font-size:36px;font-weight:800;background:var(--hero-grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;line-height:1}
.f-score{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums}
.f-bar{height:8px;background:var(--track);border-radius:99px;overflow:hidden}
.f-bar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent-2));border-radius:99px;transition:width .8s cubic-bezier(.2,.75,.2,1)}
.f-yj{display:flex;gap:22px;font-size:14.5px;color:var(--ink);flex-wrap:wrap}
.f-yj b{font-size:13px;margin-right:7px}
.f-yi b{color:var(--good)}.f-ji b{color:#ef6f6f}
.f-poem{font-size:13px;color:var(--faint);font-style:italic;border-left:2px solid var(--accent-2);padding-left:11px}

/* tabs + chips */
.tabs{display:inline-flex;gap:2px;background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:3px}
.tabs button{background:transparent;border:0;color:var(--muted);padding:7px 18px;border-radius:8px;
  cursor:pointer;font-size:13px;font-weight:600;transition:color .15s,background .15s}
.tabs button:hover{color:var(--ink)}
.tabs button.on{background:var(--accent);color:#fff}
:focus-visible{outline:2px solid var(--accent-2);outline-offset:2px;border-radius:8px}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.filter-ledger{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:11px;padding-top:11px;border-top:1px dashed var(--border)}.filter-ledger .summary{font-size:11.5px;color:var(--muted);margin-right:auto}.filter-ledger .summary b{color:var(--ink)}.filter-ledger button{padding:5px 9px}.filter-ledger button:disabled{opacity:.4;cursor:not-allowed;box-shadow:none}
.chip{display:inline-flex;align-items:center;gap:7px;background:var(--surface-2);
  border:1px solid var(--border);padding:5px 11px;border-radius:999px;font-size:12px;cursor:pointer;
  user-select:none;transition:border-color .15s,opacity .15s}
.chip:hover{border-color:var(--border-2)}
.chip input{display:none}
.chip .cdot{width:9px;height:9px;border-radius:3px}
.chip.off{opacity:.4}

/* chart */
.chart{width:100%;height:auto;display:block}
.bar-track{fill:var(--track);pointer-events:none}
.barstack{transform-box:fill-box;transform-origin:center bottom;animation:grow .6s cubic-bezier(.2,.75,.2,1) both}
.barstack:hover .seg{opacity:.999}
.seg{transition:filter .12s}
.barstack:hover .seg{filter:brightness(1.06)}
.grid-l{stroke:var(--border)} .axis{stroke:var(--border-2)}
.tick{fill:var(--faint);font-size:10px}
.xlabel{fill:var(--muted);font-size:10.5px}
.vlabel{fill:var(--muted);font-size:10px;font-weight:600;font-variant-numeric:tabular-nums}
.slice{stroke:var(--surface);stroke-width:2}
.pie-hole{fill:var(--surface)}
.pie{width:100%;height:auto;display:block;max-width:220px;margin:0 auto}
.pie-center{fill:var(--ink);font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.pie-sub{fill:var(--faint);font-size:9.5px;letter-spacing:.12em}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}

/* legend + table */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.grid2{grid-template-columns:1fr}}
.legend{list-style:none;padding:0;margin:14px 0 0;display:grid;grid-template-columns:1fr 1fr;gap:6px 14px}
.legend li{font-size:12.5px;color:var(--ink);display:flex;align-items:center}
.legend em{color:var(--faint);font-style:normal;margin-left:auto;padding-left:8px;font-variant-numeric:tabular-nums}
.ldot{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:7px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-weight:600;font-size:11.5px;letter-spacing:.02em}
tbody tr{transition:background .12s}
tbody tr:hover{background:var(--surface-2)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.dim{color:var(--faint)}
.hint{color:var(--muted);font-size:12.5px;text-align:center;padding:28px}
footer{color:var(--faint);font-size:11.5px;text-align:center;margin-top:20px}
footer b{color:var(--muted);font-weight:600}
#rocket{position:fixed;right:24px;bottom:22px;z-index:80;width:44px;height:44px;border-radius:50%;border:1px solid var(--glass-brd);background:var(--glass);backdrop-filter:blur(12px);display:grid;place-items:center;font-size:21px;cursor:pointer;box-shadow:var(--shadow);opacity:0;transform:translateY(18px) scale(.8);pointer-events:none;transition:.25s}#rocket.on{opacity:1;transform:none;pointer-events:auto}#rocket:hover{transform:translateY(-3px) rotate(-8deg)}#rocket.launch{animation:launch .7s ease forwards}@keyframes launch{50%{transform:translateY(-28px) rotate(-12deg) scale(1.15);opacity:1}100%{transform:translateY(-90px) rotate(-18deg) scale(.5);opacity:0}}
.comet{position:fixed;z-index:109;pointer-events:none;border-radius:50%;will-change:transform,opacity;animation:cometFade .72s ease-out forwards}@keyframes cometFade{to{transform:translate(var(--dx),var(--dy)) scale(.08);opacity:0}}
@media(prefers-reduced-motion:reduce){#rocket,.comet{display:none!important}}
@media(prefers-reduced-motion:reduce){.barstack,.status-pulse .led,.flow-link{animation:none}*{transition:none!important}}
@media(max-width:640px){body{padding:18px 12px 48px}.section-dock{top:4px}.section-links{min-width:0}.view-capsule{padding:7px 9px!important}.view-pop{position:fixed;left:12px;right:12px;top:auto;bottom:12px;width:auto}.help-modal{align-items:flex-end;padding:12px}.help-sheet{width:100%;max-height:82vh;border-radius:18px 18px 12px 12px}.help-grid{grid-template-columns:1fr}.probe{top:58px}[id^=section-]{scroll-margin-top:106px}.flow-shell{min-height:410px}.flow-map{width:900px;min-width:900px}.flow-node text{font-size:11px}.flow-panel{position:sticky;left:12px;bottom:12px;margin:0 12px 12px;max-width:calc(100vw - 72px)}.disc-actions{position:relative;right:auto;bottom:auto;margin-top:12px;justify-content:flex-end}.discovery{padding-bottom:16px}}
</style>
<script>/* 防 FOUC：渲染前先套用手动主题 */
try{var t=localStorage.getItem('tk-theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);}catch(e){}
</script></head><body>
<div class=wrap>

<header>
  <div class=brand>
    <div class=logo id=logo role=button tabindex=0 aria-label="点我有惊喜" title="点我">Tk</div>
    <div>
      <h1>Token 用量</h1>
      <div class=sub id=meta></div>
    </div>
  </div>
  <div class=head-tools>
    <button class="seg status-pulse" id=status-pulse type=button title="用量状态计算中"><span class=led></span><span id=status-text>状态 —</span></button>
    <div class=seg id=source-pill><span class=led></span><span id=source-txt>—</span></div>
    <button class=themebtn id=theme-btn aria-label="切换主题" title="主题：自动"></button>
    <div class=pop style=position:relative>
      <button class=themebtn id=mods-btn aria-label="模块开关" title="模块开关">⚙</button>
      <div class=popover id=mods-pop>
        <h3>显示模块</h3>
        <div class=mrow><label><input type=checkbox data-mod=clock checked>作息时钟</label><span class="switch on" data-sw=clock></span></div>
        <div class=mrow><label><input type=checkbox data-mod=fun checked>趣味换算</label><span class="switch on" data-sw=fun></span></div>
        <div class=mrow><label><input type=checkbox data-mod=block checked>5h 计费块</label><span class="switch on" data-sw=block></span></div>
        <div class=mrow><label><input type=checkbox data-mod=daily checked>每天趋势</label><span class="switch on" data-sw=daily></span></div>
        <div class=mrow><label><input type=checkbox data-mod=rhythm checked>作息织锦</label><span class="switch on" data-sw=rhythm></span></div>
        <div class=mrow><label><input type=checkbox data-mod=multiples checked>每模型趋势</label><span class="switch on" data-sw=multiples></span></div>
        <div class=mrow><label><input type=checkbox data-mod=flow checked>Token 流光图</label><span class="switch on" data-sw=flow></span></div>
        <div class=mrow><label><input type=checkbox data-mod=creature checked>Token 生物</label><span class="switch on" data-sw=creature></span></div>
        <div class=mrow><label><input type=checkbox data-mod=race checked>柱图竞赛</label><span class="switch on" data-sw=race></span></div>
        <div class=mrow><label><input type=checkbox data-mod=fortune checked>今日运势</label><span class="switch on" data-sw=fortune></span></div>
        <div class=mrow><label><input type=checkbox data-mod=badges checked>成就徽章</label><span class="switch on" data-sw=badges></span></div>
        <div class=mrow><label><input type=checkbox data-mod=dna checked>Token 星云</label><span class="switch on" data-sw=dna></span></div>
        <div class=mrow><label><input type=checkbox data-mod=top checked>Top 榜</label><span class="switch on" data-sw=top></span></div>
      </div>
    </div>
  </div>
</header>

<nav class=section-dock id=section-dock aria-label="Dashboard 区域导航">
 <div class=section-links><button data-target=section-overview class=on>总览</button><button data-target=section-trend>趋势</button><button data-target=section-rhythm>节奏</button><button data-target=section-flow>流光</button><button data-target=section-achievements>成就</button><button data-target=section-top>Top</button></div>
 <div class=view-wrap><button class=view-capsule id=view-capsule type=button aria-controls=view-pop aria-expanded=false title="查看当前视图状态"><span id=view-label>月 · 全部模型 · 全景</span></button><div class=view-pop id=view-pop><h3>Current View · 当前视图</h3><div class=view-summary id=view-summary></div><div class=view-actions><button class=ghostbtn id=view-copy type=button>⧉ 复制视图链接</button><button class=ghostbtn id=view-reset type=button>↺ 恢复全景</button></div></div></div>
</nav>

<section class="card weather" id=weather-card>
  <div class=w-icon id=w-icon>◌</div>
  <div><div class=w-title><span id=w-title>数据气候计算中</span><small>LOCAL FORECAST</small></div><div class=w-copy id=w-copy>正在读取你的本地 Token 气压、活跃时段与缓存云层。</div></div>
  <div class=w-metric><b id=w-metric>—</b><span id=w-metric-label>相对近况</span></div>
</section>

<section class="card discovery" id=discovery-card tabindex=0 aria-label="数据侦探，点击切换洞察">
 <div class=disc-kicker>YOU MAY NOT HAVE NOTICED · 数据侦探</div>
 <div class=disc-text id=discovery-text>正在寻找藏在数字之间的线索……</div>
 <div class=disc-sub id=discovery-sub>所有发现均由本地数据计算，不调用 AI。</div>
 <div class=disc-actions><span class=disc-pos id=discovery-pos>1/1</span><button class="ghostbtn disc-pin" id=discovery-pin title="固定当前洞察" aria-pressed=false>◇ 固定</button><button class="ghostbtn disc-next" id=discovery-next title="换一条发现">↻ 换一条</button></div>
</section>

<div class=probe id=time-probe>
  <span class=probe-orb></span>
  <span class=probe-copy id=probe-copy></span>
  <button id=probe-close title="退出回看（Esc）">×</button>
</div>

<section class=card id=section-overview>
 <div class=kpis>
   <div class="kpi is-primary">
     <div class=v><span class=grad id=k-total></span> <small id=k-total-u></small></div>
     <div class=l>总 token<span class=delta id=k-delta></span><span class=fc id=k-forecast></span></div>
     <svg class=spark id=spark aria-hidden=true></svg>
   </div>
   <div class=kpi>
     <div class=v><span id=k-cache-pct></span><small>%</small></div>
     <div class=l>缓存命中 · 省 <span id=k-saved></span></div>
     <div class=gauge aria-hidden=true><i id=gauge-fill style="width:0"></i></div>
   </div>
   <div class=kpi><div class=v><span id=k-calls></span></div><div class=l>调用次数</div></div>
   <div class=kpi><div class=v><span id=k-models></span></div><div class=l>命中模型数</div></div>
   <div class=kpi><div class=v><span id=k-dom></span></div><div class=l>主力模型</div></div>
 </div>
</section>

<section class=card>
 <div class=row-between>
   <h2 style=margin:0>粒度与筛选</h2>
   <div class=tabs id=tabs role=tablist>
     <button data-gran=day role=tab>按日</button>
     <button data-gran=week role=tab>按周</button>
     <button data-gran=month role=tab class=on>按月</button>
   </div>
 </div>
 <div class=filters id=filters aria-label="模型筛选"></div>
 <div class=filter-ledger id=filter-ledger><span class=summary id=filter-summary aria-live=polite></span><button class=ghostbtn id=filter-all type=button>全选</button><button class=ghostbtn id=filter-none type=button>清空</button><button class=ghostbtn id=filter-undo type=button disabled>撤销</button></div>
</section>

<section class=card id=section-trend>
 <div class=row-between>
   <h2 style=margin:0 id=bar-title>每期 token（按模型堆叠）</h2>
   <div style="display:flex;align-items:center;gap:9px"><button class="ghostbtn comparebtn" id=compare-btn title="叠加上一期轮廓">◫ 幻影对比</button><span class=sub id=bar-hint style=margin:0;color:var(--faint)></span></div>
 </div>
 <div id=bar style=margin-top:14px></div>
</section>

<section class=card data-module=fun>
 <div class=row-between>
   <h2 style=margin:0>趣味换算 · 你的 token 约等于</h2>
   <button class=ghostbtn id=fun-shuffle title="换一组">🎲 换一组</button>
 </div>
 <div id=funfacts style=margin-top:12px></div>
</section>

<section class=card data-module=block>
 <div class=row-between>
   <h2 style=margin:0>5h 计费窗口 · 近 5 小时</h2>
   <span class=sub id=block-total style=margin:0;color:var(--faint)></span>
 </div>
 <div class=block-bars id=block-bars></div>
 <div class=block-now id=block-now></div>
</section>

<section class=card data-module=daily>
 <div class=row-between>
   <h2 style=margin:0>每天 · 近 14 天</h2>
   <span class=sub id=daily-total style=margin:0;color:var(--faint)></span>
 </div>
 <div class=block-bars id=daily-bars style=margin-top:22px></div>
</section>

<section class=card data-module=rhythm id=section-rhythm>
 <div class=row-between>
   <h2 style=margin:0>作息织锦 · 14 天 × 24 小时</h2>
   <span class=sub style="margin:0;color:var(--faint)">每一个方格，都是一小时留下的算力纹理</span>
 </div>
 <div class=rhythm id=rhythm style=margin-top:16px></div>
 <div class=rh-foot><div class=persona id=rhythm-persona></div><div class=rh-legend>静 <i></i><i class=l1></i><i class=l2></i><i class=l3></i><i class=l4></i> 沸</div></div>
</section>

<section class=card data-module=fortune>
 <div class=row-between>
   <h2 style=margin:0>今日 token 运势</h2>
   <span class=sub id=f-date style=margin:0;color:var(--faint)></span>
 </div>
 <div class=fortune id=fortune></div>
</section>

<div class=grid2>
 <section class=card data-module=clock>
   <h2>作息时钟 · 什么时段最肝</h2>
   <div id=clock></div>
   <p class=sub style="text-align:center;margin:10px 0 0;color:var(--faint)">每根辐条 = 一小时的 token 量 · 高亮为峰值</p>
 </section>
 <section class=card>
   <h2>模型占比</h2>
   <div id=donut></div>
   <ul class=legend id=donut-legend></ul>
 </section>
</div>

<section class=card data-module=flow id=section-flow>
 <div class=row-between><h2 style=margin:0>Token 流光图 · 项目 → 模型 → 会话</h2><div style="display:flex;align-items:center;gap:9px;flex-wrap:wrap"><span class=sub style="margin:0;color:var(--faint)">光带宽度对应真实 Token 流量；点击项目或模型锁定链路，点击会话回放</span><button class=ghostbtn id=flow-save type=button title="保存当前流光图为 SVG">保存 SVG</button></div></div>
 <div class=flow-shell style=margin-top:14px><svg class=flow-map id=flow-map viewBox="0 0 1120 470" preserveAspectRatio="xMidYMid meet" role=img aria-label="项目到模型再到会话的 Token 流光图"></svg><div class=flow-panel id=flow-panel aria-live=polite><b>Token 流光图</b><span>悬停或聚焦节点查看真实流向，点击项目或模型可锁定链路。</span></div></div>
 <div class=flow-stats id=flow-stats></div>
</section>

<section class=card data-module=creature>
 <div class=row-between><h2 style=margin:0>Token 生物 · 你的数字生命</h2><button class=ghostbtn id=creature-save>保存 SVG</button></div>
 <div class=creature-stage id=creature-stage><svg class=creature id=creature viewBox="0 0 260 260"></svg></div>
 <div class=creature-name id=creature-name></div><div class=creature-desc id=creature-desc></div>
 <div class=creature-info id=creature-info></div>
</section>

<div class=grid2>
 <section class=card data-module=multiples>
   <h2>每模型趋势 · 日</h2>
   <div class=mp-grid id=multiples></div>
 </section>
 <section class=card data-module=race>
   <div class=row-between>
     <h2 style=margin:0>柱图竞赛 · 累计 token</h2>
     <span class=sub id=race-day style=margin:0;color:var(--faint)></span>
   </div>
   <div class=race id=race></div>
   <div class=race-ctrl>
     <button class=rbtn id=race-play>▶ 播放</button>
     <input class=rscrub id=race-scrub type=range min=0 max=0 value=0 aria-label="柱图竞赛日期位置">
     <span id=race-pos></span>
   </div>
 </section>
</div>

<section class=card>
 <div class=row-between>
   <h2 style=margin:0>明细</h2>
   <div style="display:flex;gap:8px"><button class=ghostbtn id=md-btn title="下载当前明细为 Markdown">◇ 导出 MD</button><button class=ghostbtn id=csv-btn title="下载当前明细为 CSV">⤓ 导出 CSV</button></div>
 </div>
 <table style=margin-top:12px><thead id=thead></thead><tbody id=tbody></tbody></table>
</section>

<div class=grid2>
 <section class=card data-module=badges id=section-achievements>
   <div class=row-between>
     <h2 style=margin:0>🏆 成就徽章</h2>
     <span class=ach-meta id=ach-meta></span>
   </div>
   <div class=ach-compact>
     <div class=ach-ring aria-hidden=true>
       <div class=ach-ring-disc>
         <svg viewBox="0 0 100 100" width=104 height=104>
           <circle cx=50 cy=50 r=42 fill=none style="stroke:var(--track)" stroke-width=9/>
           <circle id=ach-arc cx=50 cy=50 r=42 fill=none stroke=url(#achg) stroke-width=9 stroke-linecap=round stroke-dasharray="263.9" stroke-dashoffset=263.9 style="transition:stroke-dashoffset 1s cubic-bezier(.2,.75,.2,1)"/>
           <defs><linearGradient id=achg x1=0 y1=0 x2=1 y2=1><stop offset=0 style="stop-color:var(--accent)"/><stop offset=.5 style="stop-color:#a78bfa"/><stop offset=1 style="stop-color:#f472b6"/></linearGradient></defs>
         </svg>
         <div class=pct id=ach-pct>0%</div>
       </div>
       <div class=ach-ringlab id=ach-ringlab></div>
     </div>
     <div class=ach-info>
       <div class=ach-meta2 id=ach-meta2></div>
       <div class=ach-strip id=ach-strip></div>
       <button class=ghostbtn ach-open id=ach-open>📜 查看全部成就 · 图鉴 →</button>
     </div>
   </div>
   <div class=ach-tiers id=ach-tiers></div>
 </section>
 <section class=card data-module=dna>
   <h2>Token 星云 · 你的数据深空</h2>
   <div class=dna-wrap>
     <div class=nebula-stage><svg class=dna id=dna viewBox="0 0 300 300"></svg></div>
     <div class=dna-tip>24 小时形成星云旋臂 · 模型化作彩色星团 · 缓存点亮中央星核</div>
     <div class=nebula-meta id=nebula-meta></div>
     <button class=dnadl id=dna-dl>📥 收藏这片星云</button>
   </div>
 </section>
</div>

<section class=card data-module=top id=section-top>
 <div class=row-between>
   <h2 style=margin:0>Top 项目 / 会话</h2>
   <span class=sub id=top-hint style=margin:0;color:var(--faint)></span>
 </div>
 <div class=top2 style="margin-top:14px">
   <div><h2 style=margin:0>烧 token 的项目（cwd）</h2><div id=top-cwd style=margin-top:8px></div></div>
   <div><h2 style=margin:0>烧 token 的会话</h2><div id=top-sess style=margin-top:8px></div></div>
 </div>
</section>

<footer id=dynamic-footer>by <b>LingXi</b> · 自包含 HTML，离线可用 · 亮/暗随系统 · 按 <b>⌘K</b> 唤起命令面板</footer>
<div class=share-actions style="justify-content:center;margin-top:12px"><button class=ghostbtn id=passport-btn>✦ 生成 Token 护照</button><button class=ghostbtn id=receipt-btn>▤ 打印 Token 收据</button></div>
</div>

<button id=rocket title="返回数据宇宙顶部" aria-label="返回顶部">🚀</button>
<div class=share-modal id=share-modal><div class=share-sheet><button class=share-close id=share-close>×</button><div id=share-content></div><div class=share-actions style="justify-content:center;margin-top:18px"><button class=ghostbtn id=share-save>保存为 HTML</button></div></div></div>

<div class=rh-tip id=rhythm-tip role=tooltip></div>
<div class=scrim id=scrim aria-hidden=true>
 <div class=palette role=dialog aria-label="命令面板">
  <input id=palette-q placeholder="输入命令或搜索…（例如：月、暗、导出）" autocomplete=off>
  <ul id=palette-list></ul>
 </div>
</div>

<div class=ach-modal id=ach-modal aria-hidden=true>
 <div class=ach-sheet>
  <div class=ach-top>
   <button class=x id=ach-x aria-label=关闭>×</button>
   <h3>🏆 成就图鉴</h3>
   <div class=ach-bar>
     <span class=ach-meta id=ach-modal-meta></span>
     <input class=ach-search id=ach-search placeholder="搜索 2000+ 成就（名称/描述/分类）…" autocomplete=off>
     <select class=ach-filter id=ach-filter aria-label="筛选成就"><option value=all>全部</option><option value=on>已解锁</option><option value=off>未解锁</option><option value=secret>隐藏</option><option value=bronze>青铜</option><option value=silver>白银</option><option value=gold>黄金</option><option value=prismatic>彩钻</option></select>
     <button class=ghostbtn id=ach-confetti>🎉</button>
   </div>
  </div>
  <div class=ach-body id=ach-body></div>
 </div>
</div>

<div class=help-modal id=help-modal aria-hidden=true>
 <div class=help-sheet role=dialog aria-modal=true aria-labelledby=help-title>
  <div class=help-head><div><h3 id=help-title>快捷键与隐藏操作</h3><div class=sub>按 <b>?</b> 随时打开 · 所有操作都在本地完成</div></div><button class=help-close id=help-close type=button aria-label="关闭快捷键帮助">×</button></div>
  <div class=help-grid>
   <div class=help-row><span>切换日 / 周 / 月</span><kbd>1 / 2 / 3</kbd></div><div class=help-row><span>打开命令面板</span><kbd>⌘/Ctrl K</kbd></div>
   <div class=help-row><span>切换主题</span><kbd>T</kbd></div><div class=help-row><span>导出当前 CSV</span><kbd>E</kbd></div>
   <div class=help-row><span>退出时光探针 / 关闭弹层</span><kbd>Esc</kbd></div><div class=help-row><span>打开本帮助</span><kbd>?</kbd></div>
   <div class=help-row><span>数据侦探前后切换</span><kbd>← / →</kbd></div><div class=help-row><span>流光节点锁定 / 回放</span><kbd>Enter / Space</kbd></div>
   <div class=help-row><span>模型独看</span><kbd>双击模型</kbd></div><div class=help-row><span>全选 / 清空模型</span><kbd>Alt + 点击</kbd></div>
   <div class=help-row><span>反选单个模型</span><kbd>右键模型</kbd></div><div class=help-row><span>总量表达切换 / 复制</span><kbd>单击 / 双击</kbd></div>
  </div>
 </div>
</div>

<div class=modal id=replay-modal aria-hidden=true>
 <div class=sheet role=dialog aria-modal=true aria-labelledby=replay-title>
  <button class=x id=replay-x aria-label=关闭>×</button>
  <h3 id=replay-title>会话回放</h3>
  <div class=sub id=replay-sub style=margin:2px 0 0;color:var(--faint)></div>
  <svg class=ecg id=replay-ecg viewBox="0 0 700 160" preserveAspectRatio="none"></svg>
  <div class=rp-ctrl>
   <button class=rbtn id=replay-play>▶ 播放</button>
   <input class=rp-scrub id=replay-scrub type=range min=0 max=0 step=1 value=0 aria-label="会话回放轮次">
   <span id=replay-pos></span>
  </div>
  <div class=replay-stats id=replay-stats aria-live=polite></div>
 </div>
</div>

<script>
const DATA = __DATA__;
const state = { gran: 'month', models: new Set(DATA.models), focusPeriod:null, compare:false, numberMode:0 };
let lastTotal = 0;
const LABEL = {day:'日期', week:'周(始)', month:'月份'};

const fmt = n => Number(n||0).toLocaleString('en-US');
function human(n){ if(n>=1e8) return (n/1e8).toFixed(1)+'亿'; if(n>=1e4) return (n/1e4).toFixed(1)+'万'; return String(Math.round(n)); }
function metric(n){ if(n>=1e9)return (n/1e9).toFixed(2)+'B'; if(n>=1e6)return (n/1e6).toFixed(2)+'M'; if(n>=1e3)return (n/1e3).toFixed(1)+'K'; return String(Math.round(n)); }
function displayNumber(n){ return state.numberMode===1?human(n):state.numberMode===2?metric(n):fmt(n); }
const pretty = m => DATA.pretty[m] || m;
const pct = (a,b) => b? ((a/b*100).toFixed(1)+'%') : '0%';
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function periodDays(period, gran){
  if(gran==='day') return [period];
  const start=new Date(period+'T00:00:00'), out=[];
  if(Number.isNaN(start.getTime())) return out;
  if(gran==='week'){ for(let i=0;i<7;i++){const d=new Date(start);d.setDate(start.getDate()+i);out.push(localISO(d));} }
  else { const y=start.getFullYear(),m=start.getMonth(); for(let d=1;d<=new Date(y,m+1,0).getDate();d++) out.push(localISO(new Date(y,m,d))); }
  return out;
}
function localISO(d){ return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); }
function focusDays(){ return state.focusPeriod?new Set(periodDays(state.focusPeriod,state.gran)):null; }
function filteredHourly(){
  const fd=focusDays(); if(!fd) return DATA.hourly||[];
  const out=Array(24).fill(0);
  fd.forEach(day=>{ const det=DATA.day_details[day]; if(!det)return; Object.entries(det.hourly_models||{}).forEach(([m,h])=>{ if(state.models.has(m)) h.forEach((v,i)=>out[i]+=v||0); }); });
  return out;
}
function focusDetail(){
  const fd=focusDays(); if(!fd)return null;
  const d={cache_read:0,top_cwds:{},top_sessions:{}};
  fd.forEach(day=>{const x=DATA.day_details[day];if(!x)return;d.cache_read+=x.cache_read||0;(x.top_cwds||[]).forEach(it=>{const k=it[2]||it[0],cur=d.top_cwds[k]||[it[0],0,it[2],{}];cur[1]+=it[1]||0;Object.entries(it[3]||{}).forEach(([m,v])=>cur[3][m]=(cur[3][m]||0)+v);d.top_cwds[k]=cur;});(x.top_sessions||[]).forEach(it=>{const k=it[2]||it[0],cur=d.top_sessions[k]||[it[0],0,it[2],{}];cur[1]+=it[1]||0;Object.entries(it[3]||{}).forEach(([m,v])=>cur[3][m]=(cur[3][m]||0)+v);d.top_sessions[k]=cur;});});
  d.top_cwds=Object.values(d.top_cwds).sort((a,b)=>b[1]-a[1]).slice(0,6);d.top_sessions=Object.values(d.top_sessions).sort((a,b)=>b[1]-a[1]).slice(0,6);return d;
}

function spanYears(gran){ const ys=[...new Set(DATA[gran].map(r=>(r.period||'').slice(0,4)))]; return ys.length>1; }
function fmtLabel(period, gran){
  const p=(period||'').split('-');
  if(gran==='month') return p[0]+'-'+(p[1]||'');
  if(gran==='day'||gran==='week'){ return spanYears(gran)?period:(p[1]||'')+'-'+(p[2]||''); }
  return period;
}
function selectedRows(all=false){
  let src=DATA[state.gran];
  if(state.focusPeriod&&!all) src=src.filter(r=>r.period===state.focusPeriod);
  return src.map(r=>{
    const models={}; let total=0;
    state.models.forEach(m=>{ const v=r.models[m]||0; if(v){ models[m]=v; total+=v; } });
    return {period:r.period, calls:r.calls, models, total};
  });
}

/* count-up 数字动画 */
function animateNum(el, to, dur, formatter=fmt){
  if(!el) return;
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){ el.textContent=formatter(to); return; }
  const start=performance.now();
  function tick(t){ const k=Math.min(1,(t-start)/dur), e=1-Math.pow(1-k,3);
    el.textContent=formatter(Math.round(to*e)); if(k<1) requestAnimationFrame(tick); }
  requestAnimationFrame(tick);
}

function renderKPI(){
  const rows=selectedRows();
  const total=rows.reduce((a,r)=>a+r.total,0); lastTotal=total;
  const calls=rows.reduce((a,r)=>a+r.calls,0);
  const mtot={};
  rows.forEach(r=>Object.entries(r.models).forEach(([m,v])=>mtot[m]=(mtot[m]||0)+v));
  let dom='—', domv=-1;
  Object.entries(mtot).forEach(([m,v])=>{ if(v>domv){domv=v;dom=m;} });
  animateNum(document.getElementById('k-total'), total, 600, displayNumber);
  document.getElementById('k-total-u').textContent = human(total)+' tk';
  animateNum(document.getElementById('k-calls'), calls, 500);
  animateNum(document.getElementById('k-models'), Object.keys(mtot).length, 400);
  document.getElementById('k-dom').textContent = dom!=='—' ? pretty(dom) : '—';
  // 环比 Δ：最末一期 vs 上一期（多 token 不代表好坏，故中性配色，非红绿）
  const dEl=document.getElementById('k-delta');
  if(rows.length>=2 && rows[rows.length-2].total>0){
    const last=rows[rows.length-1].total, prev=rows[rows.length-2].total, d=(last-prev)/prev*100;
    dEl.style.display=''; dEl.className='delta '+(d>=0?'up':'down');
    dEl.textContent=(d>=0?'▲ ':'▼ ')+Math.abs(d).toFixed(1)+'% 环比';
  } else dEl.style.display='none';
  // 缓存命中：cache_read 占比；省下 = cache_read（无需重算的 token）
  const detail=focusDetail();
  const cr=detail?detail.cache_read:(DATA.cache_read||0), hit=total?(cr/total*100):0;
  animateNum(document.getElementById('k-cache-pct'), Math.round(hit), 500);
  document.getElementById('k-saved').textContent = human(cr)+' tk';
  setTimeout(()=>{ document.getElementById('gauge-fill').style.width=Math.min(100,hit).toFixed(1)+'%'; }, 60);
  // 本月预测：按已过天数速率推算月末
  const fEl=document.getElementById('k-forecast');
  if(state.gran==='month' && rows.length && !state.focusPeriod){
    const last=rows[rows.length-1], [yy,mm]=last.period.split('-').map(Number);
    const dim=new Date(yy,mm,0).getDate(), dom=Math.max(1,Math.min(dim,new Date().getDate()));
    if(dom<dim){ fEl.style.display=''; fEl.textContent='预计月末 '+human(Math.round(last.total/dom*dim))+' tk · '+Math.round(dom/dim*100)+'%进度'; }
    else fEl.style.display='none';
  } else fEl.style.display='none';
  renderSpark(rows);
}

/* 总量 KPI 里的迷你折线（最近若干期） */
function renderSpark(rows){
  const svg=document.getElementById('spark');
  const vals=rows.slice(-16).map(r=>r.total);
  if(vals.length<2){ svg.innerHTML=''; return; }
  const W=96,H=30,max=Math.max(...vals),min=Math.min(...vals),sp=(max-min)||1;
  const pts=vals.map((v,i)=>[ (i/(vals.length-1))*W, H-3-((v-min)/sp)*(H-6) ]);
  const line='M'+pts.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join('L');
  const area=line+` L ${W} ${H} L 0 ${H} Z`;
  const last=pts[pts.length-1];
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  svg.innerHTML=`<path d="${area}" fill="var(--accent-soft)"/><path d="${line}" fill="none" stroke="var(--accent-2)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2" fill="var(--accent)"/>`;
}

let barCursor=0;
function describeBar(el,focus=true){
  const rows=selectedRows(true),i=Number(el.dataset.index||0),r=rows[i];if(!r)return;
  barCursor=i;document.querySelectorAll('#bar .barstack').forEach((x,j)=>x.setAttribute('tabindex',j===i?'0':'-1'));
  const dom=Object.entries(r.models||{}).sort((a,b)=>b[1]-a[1])[0],hint=fmtLabel(r.period,state.gran)+' · '+fmt(r.total)+' Token'+(dom?' · 主力 '+pretty(dom[0])+' '+pct(dom[1],r.total):'')+' · Enter 回看';
  document.getElementById('bar-hint').textContent=hint;if(focus)el.focus();
}
function renderBar(){
  const rows=selectedRows(true);
  const W=1040,H=340,padL=56,padR=18,padT=18;
  const plotW=W-padL-padR;
  const n=Math.max(1,rows.length), step=plotW/n;
  // 每根柱都标日期：少→横排，中→斜排(-45)，密→竖排(-90)，永不抽稀、不重叠
  const ang = n<=10 ? 0 : step>=26 ? -45 : -90;
  const padB = ang===0 ? 40 : ang===-90 ? 48 : 56;
  const plotH=H-padT-padB;
  const compared=state.compare?rows.map((r,i)=>i?rows[i-1].total:0):[];
  const vmax=Math.max(1, ...rows.map(r=>r.total), ...compared);
  // 整图锁定单一单位，避免 y 轴/标签 万与亿混用造成「629→7.5」歧义
  const U = vmax>=1e8?['亿',1e8]:vmax>=1e4?['万',1e4]:['',1];
  const vfmt = nn => { const v=nn/U[1]; return U[0] ? (v<10?v.toFixed(1):String(Math.round(v)))+U[0] : String(Math.round(nn)); };
  const bw=Math.max(3,Math.min(54,step*0.6));
  const showVal = n<=12;
  const p=['<svg viewBox="0 0 '+W+' '+H+'" class="chart" preserveAspectRatio="xMidYMid meet">'];
  for(let i=0;i<=4;i++){
    const frac=i/4, y=padT+plotH*(1-frac), val=Math.round(vmax*frac);
    p.push('<line class="grid-l" x1="'+padL+'" y1="'+y.toFixed(1)+'" x2="'+(W-padR)+'" y2="'+y.toFixed(1)+'"/>');
    if(i>0) p.push('<text x="'+(padL-8)+'" y="'+(y+3.5).toFixed(1)+'" text-anchor="end" class="tick">'+vfmt(val)+'</text>');
  }
  p.push('<line class="axis" x1="'+padL+'" y1="'+(padT+plotH).toFixed(1)+'" x2="'+(W-padR)+'" y2="'+(padT+plotH).toFixed(1)+'"/>');
  if(rows.length===0){ p.push('<text x="'+(W/2)+'" y="'+(H/2)+'" text-anchor="middle" class="tick">无数据</text></svg>'); document.getElementById('bar').innerHTML=p.join(''); return; }
  const _vals=rows.map(r=>r.total);
  const mean=_vals.reduce((a,b)=>a+b,0)/_vals.length;
  let peakI=0; for(let i=1;i<rows.length;i++){ if(rows[i].total>rows[peakI].total) peakI=i; }
  rows.forEach((r,i)=>{
    const x=padL+step*i+(step-bw)/2;
    p.push('<rect class="bar-track" x="'+x.toFixed(1)+'" y="'+padT.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+plotH.toFixed(1)+'" rx="4"/>');
    if(state.compare&&i>0){
      const pv=rows[i-1].total, gh=(pv/vmax)*plotH, gy=padT+plotH-gh;
      p.push('<rect class="ghostbar" x="'+(x-3).toFixed(1)+'" y="'+gy.toFixed(1)+'" width="'+(bw+6).toFixed(1)+'" height="'+gh.toFixed(1)+'" rx="5"><title>上一期 '+esc(rows[i-1].period)+' · '+fmt(pv)+' tk</title></rect>');
    }
    let segs=''; let y0=padT+plotH;
    state.models.forEach(m=>{ const v=r.models[m]||0; if(v<=0) return;
      const h=(v/vmax)*plotH, y=y0-h;
      segs+='<rect class="seg model-mark" data-model="'+esc(m)+'" x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+h.toFixed(1)+'" rx="2" fill="'+DATA.colors[m]+'"><title>'+esc(r.period)+' · '+esc(pretty(m))+': '+fmt(v)+' ('+pct(v,r.total)+')</title></rect>';
      y0-=h;
    });
    const isPeak = rows.length>1 && i===peakI;
    const isFocus=state.focusPeriod===r.period;
    const aria=fmtLabel(r.period,state.gran)+'，'+fmt(r.total)+' Token'+(isPeak?'，峰值':'')+(isFocus?'，当前时光探针':'')+'，按 Enter 回看';
    p.push('<g class="barstack'+(isPeak?' peak':'')+(isFocus?' focused':'')+(state.focusPeriod&&!isFocus?' muted':'')+'" data-period="'+esc(r.period)+'" data-index="'+i+'" tabindex="'+(i===Math.min(barCursor,rows.length-1)?'0':'-1')+'" role="button" aria-label="'+esc(aria)+'"><rect class="bar-focus" x="'+(padL+step*i+2).toFixed(1)+'" y="'+(padT+1).toFixed(1)+'" width="'+Math.max(1,step-4).toFixed(1)+'" height="'+(plotH+padB-2).toFixed(1)+'" rx="6"/>'+segs+'</g>');
    if(isPeak&&!state.focusPeriod){
      p.push('<text class="peak-flag" x="'+(x+bw/2).toFixed(1)+'" y="'+(padT+plotH-r.total/vmax*plotH-7).toFixed(1)+'" text-anchor="middle">▲峰值 '+vfmt(r.total)+'</text>');
    } else if(showVal){
      p.push('<text class="vlabel" x="'+(x+bw/2).toFixed(1)+'" y="'+(padT+plotH-r.total/vmax*plotH-6).toFixed(1)+'" text-anchor="middle">'+vfmt(r.total)+'</text>');
    }
    if(state.compare&&i>0&&rows[i-1].total>0&&n<=18){
      const d=(r.total-rows[i-1].total)/rows[i-1].total*100;
      p.push('<text class="delta-tag" x="'+(x+bw/2).toFixed(1)+'" y="'+Math.max(11,padT+plotH-Math.max(r.total,rows[i-1].total)/vmax*plotH-18).toFixed(1)+'" text-anchor="middle">'+(d>=0?'+':'')+d.toFixed(0)+'%</text>');
    }
    const lx=padL+step*i+step/2;
    let ly, anchor, tr;
    if(ang===0){ ly=H-padB+18; anchor='middle'; tr=''; }
    else if(ang===-45){ ly=H-padB+30; anchor='end'; tr='transform="rotate(-45 '+lx.toFixed(1)+' '+ly.toFixed(1)+')"'; }
    else { ly=H-8; anchor='start'; tr='transform="rotate(-90 '+lx.toFixed(1)+' '+ly.toFixed(1)+')"'; }
    p.push('<text x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'" text-anchor="'+anchor+'" class="xlabel" '+tr+'>'+esc(fmtLabel(r.period,state.gran))+'</text>');
    p.push('<rect class="bar-hit" data-period="'+esc(r.period)+'" x="'+(padL+step*i).toFixed(1)+'" y="'+padT+'" width="'+step.toFixed(1)+'" height="'+(plotH+padB).toFixed(1)+'"><title>点击回看 '+esc(r.period)+'</title></rect>');
  });
  if(rows.length>1 && mean>0){
    const my=padT+plotH-(mean/vmax)*plotH;
    p.push('<line class="mean-line" x1="'+padL+'" y1="'+my.toFixed(1)+'" x2="'+(W-padR)+'" y2="'+my.toFixed(1)+'"/>');
    p.push('<text class="mean-lab" x="'+(W-padR-2)+'" y="'+(my-4).toFixed(1)+'" text-anchor="end">μ '+vfmt(mean)+'</text>');
  }
  p.push('</svg>');
  const box=document.getElementById('bar'); box.innerHTML=p.join('');
  const stacks=[...box.querySelectorAll('.barstack')];
  stacks.forEach(el=>{
    el.addEventListener('click',()=>toggleFocus(el.dataset.period));
    el.addEventListener('focus',()=>describeBar(el,false));
    el.addEventListener('keydown',e=>{const i=Number(el.dataset.index||0);if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();const next=Math.max(0,Math.min(stacks.length-1,i+(e.key==='ArrowRight'?1:-1)));describeBar(stacks[next]);}else if(e.key==='Home'||e.key==='End'){e.preventDefault();describeBar(stacks[e.key==='Home'?0:stacks.length-1]);}else if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleFocus(el.dataset.period,true);}});
  });
  box.querySelectorAll('.bar-hit').forEach(el=>el.addEventListener('click',()=>toggleFocus(el.dataset.period)));
  box.querySelectorAll('.model-mark').forEach(el=>{el.addEventListener('mouseenter',e=>{modelHover(el.dataset.model,true);e.stopPropagation();});el.addEventListener('mouseleave',e=>{modelHover(el.dataset.model,false);e.stopPropagation();});});
}

function renderDonut(){
  const rows=selectedRows();
  const mtot={};
  rows.forEach(r=>Object.entries(r.models).forEach(([m,v])=>mtot[m]=(mtot[m]||0)+v));
  const entries=Object.entries(mtot).sort((a,b)=>b[1]-a[1]);
  const total=entries.reduce((a,[,v])=>a+v,0);
  const box=document.getElementById('donut');
  if(total===0){ box.innerHTML='<div class="hint">所选区间无数据</div>'; document.getElementById('donut-legend').innerHTML=''; return; }
  const size=220, cx=size/2, cy=size/2, r=size/2-8;
  let angle=-Math.PI/2; const p=['<svg viewBox="0 0 '+size+' '+size+'" class="pie">'];
  entries.forEach(([m,v])=>{
    const frac=v/total, a0=angle, a1=angle+frac*2*Math.PI;
    if(frac>=0.999){
      p.push('<circle class="slice model-mark" data-model="'+esc(m)+'" cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="'+DATA.colors[m]+'"><title>'+esc(pretty(m))+' '+pct(v,total)+'</title></circle>');
    }else{
      const large=frac>0.5?1:0;
      const x0=cx+r*Math.cos(a0), y0=cy+r*Math.sin(a0), x1=cx+r*Math.cos(a1), y1=cy+r*Math.sin(a1);
      p.push('<path class="slice model-mark" data-model="'+esc(m)+'" d="M '+cx+' '+cy+' L '+x0.toFixed(2)+' '+y0.toFixed(2)+' A '+r+' '+r+' 0 '+large+' 1 '+x1.toFixed(2)+' '+y1.toFixed(2)+' Z" fill="'+DATA.colors[m]+'"><title>'+esc(pretty(m))+' '+pct(v,total)+'</title></path>');
    }
    angle=a1;
  });
  p.push('<circle class="pie-hole" cx="'+cx+'" cy="'+cy+'" r="'+(r*0.58).toFixed(1)+'"/>');
  p.push('<text x="'+cx+'" y="'+(cy-2)+'" text-anchor="middle" class="pie-center">'+human(total)+'</text>');
  p.push('<text x="'+cx+'" y="'+(cy+14)+'" text-anchor="middle" class="pie-sub">TOKENS</text></svg>');
  box.innerHTML=p.join('');
  document.getElementById('donut-legend').innerHTML=entries.map(([m,v])=>
    '<li class="model-mark" data-model="'+esc(m)+'"><span class="ldot" style="background:'+DATA.colors[m]+'"></span>'+esc(pretty(m))+' <em>'+pct(v,total)+'</em></li>').join('');
}

function renderTable(){
  const rows=selectedRows();
  const cols=DATA.models.filter(m=>state.models.has(m));
  const th=cols.map(m=>'<th class=num>'+esc(pretty(m))+'</th>').join('');
  const body=rows.map(r=>{
    const tds=cols.map(m=> r.models[m]?'<td class=num>'+fmt(r.models[m])+'</td>':'<td class=num><span class=dim>·</span></td>').join('');
    return '<tr><td>'+esc(fmtLabel(r.period,state.gran))+'</td><td class=num>'+fmt(r.total)+'</td>'+tds+'<td class=num>'+fmt(r.calls)+'</td></tr>';
  }).join('');
  document.getElementById('thead').innerHTML='<tr><th>'+LABEL[state.gran]+'</th><th class=num>总 token</th>'+th+'<th class=num>调用</th></tr>';
  document.getElementById('tbody').innerHTML=body || '<tr><td colspan="' +(cols.length+3)+ '" class="hint">无数据</td></tr>';
}

let previousModels=null;
function setModels(next,label){previousModels=new Set(state.models);state.models=new Set(next);renderFilters();render();if(label)toast(label);}
function renderFilterLedger(){
  const rows=DATA[state.gran]||[],all=rows.reduce((a,r)=>a+(r.total||0),0),selected=rows.reduce((a,r)=>a+Object.entries(r.models||{}).reduce((s,[m,v])=>s+(state.models.has(m)?v:0),0),0);
  document.getElementById('filter-summary').innerHTML='已选 <b>'+state.models.size+'/'+DATA.models.length+'</b> 个模型 · 覆盖 <b>'+pct(selected,all)+'</b> Token';document.getElementById('filter-undo').disabled=!previousModels;
}
function renderFilters(){
  const box=document.getElementById('filters');
  if(DATA.models.length===0){ box.innerHTML='<span class=hint>无模型数据</span>'; return; }
  box.innerHTML=DATA.models.map(m=>{
    const on=state.models.has(m);
    return '<label class="chip'+(on?'':' off')+'"><input type=checkbox value="'+esc(m)+'" '+(on?'checked':'')+'><span class=cdot style="background:'+DATA.colors[m]+'"></span>'+esc(pretty(m))+'</label>';
  }).join('');
  box.querySelectorAll('input').forEach(cb=>{
    cb.addEventListener('change',e=>{const next=new Set(state.models);e.target.checked?next.add(e.target.value):next.delete(e.target.value);setModels(next);});
    const chip=cb.closest('.chip');
    chip.title='点击切换 · 双击独看 · Alt 点击全选/清空 · 右键反选';
    chip.addEventListener('dblclick',e=>{e.preventDefault();setModels([cb.value],'Solo · '+pretty(cb.value));});
    chip.addEventListener('click',e=>{if(!e.altKey)return;e.preventDefault();setModels(state.models.size===DATA.models.length?[]:DATA.models);});
    chip.addEventListener('contextmenu',e=>{e.preventDefault();const next=new Set(state.models);next.has(cb.value)?next.delete(cb.value):next.add(cb.value);setModels(next);});
  });
  renderFilterLedger();
}
document.getElementById('filter-all').addEventListener('click',()=>setModels(DATA.models,'已选择全部模型'));
document.getElementById('filter-none').addEventListener('click',()=>setModels([],'已清空模型筛选'));
document.getElementById('filter-undo').addEventListener('click',()=>{if(!previousModels)return;state.models=new Set(previousModels);previousModels=null;renderFilters();render();toast('已撤销上一次模型筛选');});

function lbRows(items,sessionRows=false){
  if(!items || !items.length) return '<div class="hint">无数据</div>';
  const filtered=items.map(it=>{const models=it[3]||{},parts=Object.entries(models).filter(([m])=>state.models.has(m)).sort((a,b)=>b[1]-a[1]),total=parts.reduce((a,[,v])=>a+v,0);return {it,parts,total};});
  const max=Math.max(1,...filtered.map(x=>x.total));
  return filtered.map(({it,parts,total},i)=>{
    const w=total/max*100,full=it[2]||it[0],dom=parts[0],comp=total?parts.map(([m,v])=>'<i style="width:'+(v/total*100).toFixed(1)+'%;background:'+DATA.colors[m]+'" title="'+esc(pretty(m))+' '+pct(v,total)+'"></i>').join(''):'';
    const attrs=sessionRows?' role="button" tabindex="0" aria-label="会话 '+esc(it[0])+'，'+fmt(total)+' Token，按 Enter 回放"':'';
    return '<div class=lb-row'+attrs+'><span class=rk>'+String(i+1).padStart(2,'0')+'</span>'
      +'<span class=lb-name title="'+esc(full)+'">'+esc(it[0])+'</span>'
      +'<span class=lb-bar><i style="width:'+w.toFixed(1)+'%"></i></span>'
      +'<span class=lb-val>'+human(total)+'</span><span class=lb-comp>'+comp+'</span><span class=lb-dom>'+(dom?'主力 '+esc(pretty(dom[0]))+' · 当前模型筛选构成':'当前模型筛选下无 Token')+'</span></div>';
  }).join('');
}
function renderTop(){
  const detail=focusDetail(), cwds=detail?detail.top_cwds:DATA.top_cwds, sessions=detail?detail.top_sessions:DATA.top_sessions;
  document.getElementById('top-cwd').innerHTML = lbRows(cwds);
  document.getElementById('top-sess').innerHTML = lbRows(sessions,true);
  document.getElementById('top-hint').textContent=(state.focusPeriod?'当前回看期 · ':'')+'保持原 Top 顺序 · 数值和色条按当前模型筛选 · 会话可回放';
  Array.from(document.getElementById('top-sess').querySelectorAll('.lb-row')).forEach((row,i)=>{
    const it=sessions[i]; if(!it) return;
    row.style.cursor='pointer';row.title='点击或按 Enter 回放逐轮 token';
    const activate=()=>openReplay(it[2],it[0]);row.addEventListener('click',activate);row.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}});
  });
}

function renderClock(){
  const h=filteredHourly(), box=document.getElementById('clock');
  const total=h.reduce((a,b)=>a+(b||0),0);
  if(!total){ box.innerHTML='<div class="hint">无数据</div>'; return; }
  const max=Math.max.apply(null,h);
  let peak=0; for(let i=1;i<24;i++) if((h[i]||0)>(h[peak]||0)) peak=i;
  const size=270, cx=size/2, cy=size/2, rmax=size/2-28, rmin=34;
  const sw=Math.max(3, 2*Math.PI*rmin/24-3);
  const p=['<svg viewBox="0 0 '+size+' '+size+'" class="clock" aria-label="每小时 token 分布">'];
  p.push('<circle cx="'+cx+'" cy="'+cy+'" r="'+rmax+'" fill="none" stroke="var(--border)" stroke-dasharray="2 5"/>');
  for(let i=0;i<24;i++){
    const ang=(i/24)*2*Math.PI - Math.PI/2;
    if(i%3===0){
      const r2=rmax+5;
      p.push('<line x1="'+(cx+Math.cos(ang)*rmax).toFixed(1)+'" y1="'+(cy+Math.sin(ang)*rmax).toFixed(1)+'" x2="'+(cx+Math.cos(ang)*r2).toFixed(1)+'" y2="'+(cy+Math.sin(ang)*r2).toFixed(1)+'" class="clk-tick"/>');
      p.push('<text x="'+(cx+Math.cos(ang)*(r2+10)).toFixed(1)+'" y="'+(cy+Math.sin(ang)*(r2+10)+3).toFixed(1)+'" text-anchor="middle" class="clk-h">'+String(i).padStart(2,'0')+'</text>');
    }
  }
  for(let i=0;i<24;i++){
    const v=h[i]||0; if(v<=0) continue;
    const frac=v/max, ang=(i/24)*2*Math.PI - Math.PI/2;
    const ri=rmin, ro=rmin+frac*(rmax-rmin), isPeak=i===peak;
    p.push('<line class="clk-spoke'+(isPeak?' peak':'')+'" x1="'+(cx+Math.cos(ang)*ri).toFixed(1)+'" y1="'+(cy+Math.sin(ang)*ri).toFixed(1)+'" x2="'+(cx+Math.cos(ang)*ro).toFixed(1)+'" y2="'+(cy+Math.sin(ang)*ro).toFixed(1)+'" stroke-width="'+sw.toFixed(1)+'"><title>'+String(i).padStart(2,'0')+':00 · '+human(v)+' tk</title></line>');
  }
  p.push('<circle class="clk-core" cx="'+cx+'" cy="'+cy+'" r="'+rmin+'"/>');
  p.push('<text x="'+cx+'" y="'+(cy-2)+'" text-anchor="middle" class="clk-center">'+String(peak).padStart(2,'0')+':00</text>');
  p.push('<text x="'+cx+'" y="'+(cy+14)+'" text-anchor="middle" class="clk-sub">峰值时段</text></svg>');
  box.innerHTML=p.join('');
}

function buildDiscoveries(){
  const days=DATA.day||[], vals=days.map(d=>d.total||0), total=vals.reduce((a,b)=>a+b,0), avg=vals.length?total/vals.length:0;
  if(!days.length)return [{t:'数据还在沉睡，等第一批 Token 落下后，故事会从这里开始。',s:'暂无足够数据'}];
  const top=[...days].sort((a,b)=>b.total-a.total), h=DATA.hourly||[], ht=h.reduce((a,b)=>a+b,0), peak=h.indexOf(Math.max(...h));
  const mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const me=Object.entries(mt).sort((a,b)=>b[1]-a[1]);
  const wd=Array(7).fill(0);days.forEach(d=>{const p=d.period.split('-'),x=new Date(Date.UTC(+p[0],+p[1]-1,+p[2]));wd[(x.getUTCDay()+6)%7]+=d.total;});
  const out=[];
  if(top[0])out.push({t:'你最猛烈的一天是 '+fmtLabel(top[0].period,'day')+'，单日燃烧 '+human(top[0].total)+' Token。',s:avg?'相当于日均值的 '+(top[0].total/avg).toFixed(1)+' 倍':''});
  if(top.length>=3){const v=top.slice(0,3).reduce((a,d)=>a+d.total,0);out.push({t:'仅仅三个最高峰日，就贡献了全部 Token 的 '+(v/total*100).toFixed(1)+'%。',s:'少数时刻塑造了大部分数据地貌'});}
  if(peak>=0)out.push({t:'你的算力生物最喜欢在 '+String(peak).padStart(2,'0')+':00 出没。',s:'这个小时累计 '+human(h[peak]||0)+' Token'});
  const night=(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))/(ht||1);if(night>.25)out.push({t:'夜色承载了你 '+(night*100).toFixed(1)+'% 的 Token，屏幕熄灭得比城市更晚。',s:'统计范围：22:00–06:00'});
  if(me[0])out.push({t:pretty(me[0][0])+' 是你的主力引擎，独自承载 '+(me[0][1]/total*100).toFixed(1)+'% 的算力。',s:me[1]?'是第二名的 '+(me[0][1]/me[1][1]).toFixed(1)+' 倍':'目前没有第二名'});
  if(me.length>=3)out.push({t:'你使用过 '+me.length+' 种模型，数据光谱已经不再是单色。',s:'每种模型都在 Token 星云中凝聚成不同颜色的星团'});
  const best=wd.indexOf(Math.max(...wd));out.push({t:['周一','周二','周三','周四','周五','周六','周日'][best]+'是你一周里算力气压最高的一天。',s:'累计 '+human(wd[best])+' Token'});
  const cr=DATA.cache_read||0;if(total&&cr/total>.5)out.push({t:'超过一半的 Token 曾被缓存记住，你的上下文很少真正从零开始。',s:'缓存占比 '+(cr/total*100).toFixed(1)+'%'});
  if(DATA.top_cwds&&DATA.top_cwds[0])out.push({t:'「'+DATA.top_cwds[0][0]+'」是这座数据宇宙里质量最大的项目。',s:'累计 '+human(DATA.top_cwds[0][1])+' Token'});
  const recent=vals.slice(-7),old=vals.slice(-14,-7),ra=recent.reduce((a,b)=>a+b,0)/(recent.length||1),oa=old.reduce((a,b)=>a+b,0)/(old.length||1);if(oa)out.push({t:'最近七天的日均 Token 比此前七天 '+(ra>=oa?'高':'低')+' '+Math.abs((ra/oa-1)*100).toFixed(1)+'%。',s:ra>=oa?'数据天气正在升温':'算力气压正在回落'});
  out.push({t:'你的 '+fmt(DATA.n_sessions||0)+' 个会话，正在共同组成一份无法复制的开发者轨迹。',s:'它只存在于这份本地生成的 HTML 中'});
  return out;
}
let discoveryIndex=0, discoveryPinned=false;
const DISCOVERY_KEY='tk-discovery';
function loadDiscovery(){try{const v=JSON.parse(localStorage.getItem(DISCOVERY_KEY)||'{}');discoveryIndex=Math.max(0,Number(v.index)||0);discoveryPinned=!!v.pinned;}catch(e){}}
function saveDiscovery(){try{localStorage.setItem(DISCOVERY_KEY,JSON.stringify({index:discoveryIndex,pinned:discoveryPinned}));}catch(e){}}
function renderDiscovery(step=0,force=false){const a=buildDiscoveries();if(step&&(!discoveryPinned||force))discoveryIndex=(discoveryIndex+step+a.length)%a.length;discoveryIndex%=a.length;document.getElementById('discovery-text').textContent=a[discoveryIndex].t;document.getElementById('discovery-sub').textContent=(a[discoveryIndex].s||'所有发现均由本地数据计算。')+(discoveryPinned?' · 当前洞察已固定':'');document.getElementById('discovery-pos').textContent=(discoveryIndex+1)+'/'+a.length;const pin=document.getElementById('discovery-pin'),card=document.getElementById('discovery-card');pin.classList.toggle('on',discoveryPinned);pin.setAttribute('aria-pressed',String(discoveryPinned));pin.textContent=discoveryPinned?'◆ 已固定':'◇ 固定';card.classList.toggle('pinned',discoveryPinned);saveDiscovery();}
function stepDiscovery(step){if(discoveryPinned){toast('当前洞察已固定，取消固定后可切换');return;}renderDiscovery(step,true);}
loadDiscovery();
document.getElementById('discovery-next').addEventListener('click',e=>{e.stopPropagation();stepDiscovery(1);});
document.getElementById('discovery-pin').addEventListener('click',e=>{e.stopPropagation();discoveryPinned=!discoveryPinned;renderDiscovery();});
document.getElementById('discovery-card').addEventListener('click',e=>{if(e.target.closest('button'))return;stepDiscovery(1);});
document.getElementById('discovery-card').addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();stepDiscovery(e.key==='ArrowRight'?1:-1);}else if((e.key==='Enter'||e.key===' ')&&!e.target.closest('button')){e.preventDefault();stepDiscovery(1);}});
function renderFooter(){
  const a=_ach||getBadgeData(), h=DATA.hourly||[], peak=h.indexOf(Math.max(...h)), lines=[
    'by <b>LingXi</b> · 本页装载了 <b>'+human(DATA.day.reduce((s,d)=>s+d.total,0))+'</b> Token 的痕迹。',
    '你的缓存替你记住了 <b>'+human(DATA.cache_read||0)+'</b> Token。',
    '<b>'+fmt(a.all.length-a.got)+'</b> 枚成就仍在数据深处沉睡。',
    '算力最常在 <b>'+String(Math.max(0,peak)).padStart(2,'0')+':00</b> 亮起。',
    '纯本地生成 · 没有任何数据离开这台电脑。'
  ];document.getElementById('dynamic-footer').innerHTML=lines[(new Date().getDate()+DATA.day.length)%lines.length];
}

function shareStats(){
  const days=DATA.day||[],total=days.reduce((a,d)=>a+d.total,0),calls=days.reduce((a,d)=>a+d.calls,0),h=DATA.hourly||[],peak=h.indexOf(Math.max(...h)),mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const dom=Object.entries(mt).sort((a,b)=>b[1]-a[1])[0];
  return {total,calls,peak,dom:dom?pretty(dom[0]):'—',cache:total?(DATA.cache_read||0)/total:0,ach:_ach||getBadgeData(),creature:document.getElementById('creature-name').textContent||'Token 生物'};
}
function openShare(type){
  const x=shareStats(), content=document.getElementById('share-content');
  if(type==='passport')content.innerHTML='<div class=passport id=share-card><div class=pass-head><div><div class=pass-k>LOCAL DEVELOPER IDENTITY</div><h3>TOKEN PASSPORT</h3></div><div class=pass-id>ISSUED '+esc(DATA.generated)+'<br>NO DATA UPLOADED</div></div><div class=pass-grid><div><div class=pass-k>DEVELOPER TYPE</div><div class=pass-hero>'+(x.peak<6||x.peak>=22?'MIDNIGHT<br>NAVIGATOR':'DAYLIGHT<br>BUILDER')+'</div><div class=pass-sub>'+esc(x.creature)+' · 本地数据宇宙居民</div></div><div class=pass-fields><div class=pass-field><span>TOTAL TOKENS</span><b>'+fmt(x.total)+'</b></div><div class=pass-field><span>PRIMARY MODEL</span><b>'+esc(x.dom)+'</b></div><div class=pass-field><span>PEAK GATE</span><b>'+String(Math.max(0,x.peak)).padStart(2,'0')+':00</b></div><div class=pass-field><span>CACHE</span><b>'+Math.round(x.cache*100)+'%</b></div><div class=pass-field><span>CALLS</span><b>'+fmt(x.calls)+'</b></div><div class=pass-field><span>ACHIEVEMENTS</span><b>'+fmt(x.ach.got)+' / '+fmt(x.ach.all.length)+'</b></div></div></div><div class=pass-foot><span>VALID IN ALL LOCAL TERMINALS<br>PRIVACY CLASS: OFFLINE</span><span class=barcode>||| || ||| | |||| || |</span></div></div>';
  else content.innerHTML='<div class=receipt id=share-card><h3>TOKEN STORE</h3><div class=receipt-center>LOCAL TERMINAL · '+esc(DATA.generated.slice(0,10))+'<br>ORDER #'+String(x.total%100000).padStart(5,'0')+'</div><hr>'+(DATA.models||[]).map(m=>{const v=(DATA.day||[]).reduce((a,d)=>a+(d.models[m]||0),0);return '<div class=receipt-row><span>'+esc(pretty(m)).slice(0,18)+'</span><b>'+fmt(v)+'</b></div>';}).join('')+'<hr><div class=receipt-row><span>CALLS</span><b>'+fmt(x.calls)+'</b></div><div class=receipt-row><span>CACHE SAVED</span><b>'+fmt(DATA.cache_read||0)+'</b></div><div class=receipt-row><span>ACHIEVEMENTS</span><b>'+fmt(x.ach.got)+'</b></div><hr><div class="receipt-row receipt-total"><span>TOTAL</span><b>'+fmt(x.total)+' TK</b></div><div class=receipt-code>|||| || ||||| | ||| ||</div><div class=receipt-note>THANK YOU FOR CODING<br>OPEN 24 HOURS · NO DATA UPLOADED</div></div>';
  document.getElementById('share-modal').classList.add('open');document.getElementById('share-modal').dataset.type=type;
}
function closeShare(){document.getElementById('share-modal').classList.remove('open');}
document.getElementById('passport-btn').addEventListener('click',()=>openShare('passport'));document.getElementById('receipt-btn').addEventListener('click',()=>openShare('receipt'));document.getElementById('share-close').addEventListener('click',closeShare);document.getElementById('share-modal').addEventListener('click',e=>{if(e.target.id==='share-modal')closeShare();});
document.getElementById('share-save').addEventListener('click',()=>{const card=document.getElementById('share-card'),style=[...document.querySelectorAll('style')].map(x=>x.textContent).join('\n'),html='<!doctype html><meta charset=utf-8><style>'+style+'body{display:grid;place-items:center;min-height:100vh;background:#080b12;padding:30px}</style>'+card.outerHTML;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'}));a.download='token-'+document.getElementById('share-modal').dataset.type+'.html';a.click();toast('分享卡已保存为 HTML');});

function renderWeather(){
  const days=(DATA.day||[]).slice(-14), recent=days.slice(-7), prev=days.slice(-14,-7);
  const rt=recent.reduce((a,d)=>a+d.total,0), pt=prev.reduce((a,d)=>a+d.total,0), ratio=pt?rt/pt:1;
  const h=filteredHourly(), ht=h.reduce((a,b)=>a+b,0), night=ht?(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))/ht:0;
  const total=selectedRows().reduce((a,r)=>a+r.total,0), detail=focusDetail(), cr=detail?detail.cache_read:(DATA.cache_read||0), cache=total?cr/total:0;
  let w={i:'☀️',t:'Token 晴朗',c:'用量平稳，算力气压舒适。今天适合把注意力留给代码本身。',m:'稳定',g:'rgba(245,158,11,.28)'};
  if(cache>=.72) w={i:'🌈',t:'缓存彩虹',c:'大量上下文被成功复用，重复算力正在悄悄变成你的隐形红利。',m:Math.round(cache*100)+'%',g:'rgba(167,139,250,.34)'};
  if(ratio>=1.35) w={i:'🌧️',t:'局部 Token 暴雨',c:'最近七期明显高于此前节奏，算力云层正在快速增厚。',m:'+'+Math.round((ratio-1)*100)+'%',g:'rgba(91,141,239,.42)'};
  if(ratio>=1.8) w={i:'⛈️',t:'模型风暴',c:'Token 气压出现强烈跃升。建议点开柱状图，定位是哪一期掀起了风暴。',m:'×'+ratio.toFixed(1),g:'rgba(244,114,182,.38)'};
  if(night>=.42) w={i:'🌙',t:'深夜低压',c:'大量算力聚集在夜间，屏幕亮着的时候，城市可能已经睡了。',m:Math.round(night*100)+'%',g:'rgba(99,102,241,.38)'};
  if(state.focusPeriod) w.c='时光探针已锁定 '+fmtLabel(state.focusPeriod,state.gran)+'。此刻的天气只属于这一段时间。';
  document.getElementById('w-icon').textContent=w.i; document.getElementById('w-title').textContent=w.t; document.getElementById('w-copy').textContent=w.c; document.getElementById('w-metric').textContent=w.m; document.getElementById('w-metric-label').textContent=state.focusPeriod?'局部气候':'相对近况'; document.getElementById('weather-card').style.setProperty('--weather-glow',w.g);
}
function renderProbe(){
  const el=document.getElementById('time-probe');
  if(!state.focusPeriod){el.classList.remove('on');return;}
  const row=selectedRows()[0], dom=row?Object.entries(row.models).sort((a,b)=>b[1]-a[1])[0]:null;
  document.getElementById('probe-copy').innerHTML='<b>正在回看 '+esc(fmtLabel(state.focusPeriod,state.gran))+'</b> · '+human(row?row.total:0)+' tk'+(dom?' · 主力 '+esc(pretty(dom[0])):'')+' · Esc 返回全景';
  el.classList.add('on');
}
function toggleFocus(period,restoreBar=false){ state.focusPeriod=state.focusPeriod===period?null:period; render();if(restoreBar){const el=[...document.querySelectorAll('#bar .barstack')].find(x=>x.dataset.period===period);if(el){barCursor=Number(el.dataset.index||0);el.focus();}} }
function clearFocus(restoreBar=false){ if(!state.focusPeriod)return;const period=state.focusPeriod;state.focusPeriod=null;render();if(restoreBar){const el=[...document.querySelectorAll('#bar .barstack')].find(x=>x.dataset.period===period);if(el){barCursor=Number(el.dataset.index||0);el.focus();}} }

document.getElementById('probe-close').addEventListener('click',clearFocus);

const THEMES=[['auto','🌗','自动'],['light','☀️','亮色'],['dark','🌙','暗色']];
let restoringView=true;
function currentTheme(){return document.documentElement.getAttribute('data-theme')||'auto';}
function validFocus(period,gran){return !!period&&DATA[gran].some(r=>r.period===period);}
function viewParams(){
  const p=new URLSearchParams();p.set('gran',state.gran);
  if(state.models.size!==DATA.models.length)p.set('models',DATA.models.filter(m=>state.models.has(m)).join(','));
  if(state.focusPeriod)p.set('focus',state.focusPeriod);
  if(state.compare)p.set('compare','1');
  const theme=currentTheme();if(theme!=='auto')p.set('t',theme);
  return p;
}
function viewURL(){const u=new URL(location.href);u.search=viewParams().toString();u.hash='';return u.toString();}
function syncViewURL(replace=true){if(restoringView||!history.replaceState)return;const u=viewURL();history[replace?'replaceState':'pushState'](null,'',u);}
function restoreViewFromURL(){
  const p=new URLSearchParams(location.search),g=p.get('gran')||((location.hash||'').replace('#',''));
  if(['day','week','month'].includes(g))state.gran=g;
  const requested=p.get('models');if(requested!==null){const allowed=new Set(DATA.models),models=requested?requested.split(',').filter(m=>allowed.has(m)):[];state.models=new Set(models);}else state.models=new Set(DATA.models);previousModels=null;
  const focus=p.get('focus');state.focusPeriod=validFocus(focus,state.gran)?focus:null;state.compare=p.get('compare')==='1';
  const theme=(p.get('t')||'').toLowerCase();if(['auto','light','dark'].includes(theme))applyTheme(theme);
}
function viewDescription(){const gran={day:'按日',week:'按周',month:'按月'}[state.gran],modelCount=state.models.size,focus=state.focusPeriod?fmtLabel(state.focusPeriod,state.gran):'全景',compare=state.compare?'已开启':'关闭';return {gran,modelCount,focus,compare};}
function renderViewCapsule(){
  const d=viewDescription(),label=document.getElementById('view-label'),capsule=document.getElementById('view-capsule');
  label.textContent=d.gran.replace('按','')+' · '+(d.modelCount===DATA.models.length?'全部模型':d.modelCount+'/'+DATA.models.length+' 模型')+' · '+d.focus;
  capsule.classList.toggle('dirty',!!state.focusPeriod||state.models.size!==DATA.models.length||state.compare);
  document.getElementById('view-summary').innerHTML='<b>'+d.gran+'</b> · '+d.modelCount+' / '+DATA.models.length+' 个模型<br><b>'+(state.focusPeriod?'时光探针':'时间范围')+'</b> · '+esc(d.focus)+'<br><b>幻影对比</b> · '+d.compare;
  document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x.dataset.gran===state.gran));document.getElementById('compare-btn').classList.toggle('on',state.compare);
}
function resetView(){state.gran='month';state.models=new Set(DATA.models);state.focusPeriod=null;state.compare=false;previousModels=null;renderFilters();render();toast('已恢复月度全景');}
async function copyText(text){try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);return true;}}catch(e){}const ta=document.createElement('textarea');ta.value=text;ta.style.cssText='position:fixed;left:-9999px;top:0';document.body.appendChild(ta);ta.select();let ok=false;try{ok=document.execCommand('copy');}catch(e){}ta.remove();return ok;}
function copyViewLink(){copyText(viewURL()).then(ok=>toast(ok?'当前视图链接已复制':'复制失败，请从地址栏复制'));}
document.getElementById('view-capsule').addEventListener('click',e=>{e.stopPropagation();const pop=document.getElementById('view-pop'),open=!pop.classList.contains('open');pop.classList.toggle('open',open);e.currentTarget.setAttribute('aria-expanded',String(open));});
document.getElementById('view-copy').addEventListener('click',copyViewLink);document.getElementById('view-reset').addEventListener('click',resetView);document.addEventListener('click',e=>{if(!e.target.closest('.view-wrap')){document.getElementById('view-pop').classList.remove('open');document.getElementById('view-capsule').setAttribute('aria-expanded','false');}});
window.addEventListener('popstate',()=>{restoringView=true;restoreViewFromURL();renderFilters();render();restoringView=false;});

document.getElementById('compare-btn').addEventListener('click',()=>{ state.compare=!state.compare; renderBar();renderViewCapsule();syncViewURL(); });

function render(){
  renderKPI();
  const n=DATA[state.gran].length;
  document.getElementById('bar-hint').textContent = n+' 期 · 点击柱子进入时光探针';
  renderBar(); renderDonut(); renderTable(); renderTop(); renderClock(); renderFunFacts(); renderWeather(); renderProbe(); renderRhythm();
  renderBlock(); renderDaily(); renderMultiples(); renderFlow(); renderCreature(); renderRace();
  renderBadges(); renderDNA(); renderFortune(); renderDiscovery(); renderFooter(); renderStatusPulse(); renderViewCapsule(); bindModelLinks();
  syncViewURL();
}

document.getElementById('tabs').addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b) return;
  setGran(b.dataset.gran);
});
function setGran(g){
  if(!['day','week','month'].includes(g))return;
  state.gran=g; state.focusPeriod=null;
  render();
}

document.getElementById('meta').textContent =
  '生成于 '+DATA.generated+' · '+(DATA.range.since||'起始')+' ~ '+(DATA.range.until||'至今');
document.getElementById('source-txt').textContent = '来源 '+(DATA.source.join(' / ')||'无');

/* 主题：自动 / 亮 / 暗 三态，localStorage 记忆，覆盖系统 */
function applyTheme(t){
  if(t==='light'||t==='dark') document.documentElement.setAttribute('data-theme',t);
  else document.documentElement.removeAttribute('data-theme');
  const c=THEMES.find(x=>x[0]===t)||THEMES[0];
  const b=document.getElementById('theme-btn');
  b.textContent=c[1]; b.title='主题：'+c[2]+'（点击切换）';
  try{localStorage.setItem('tk-theme',t);}catch(e){}
  if(typeof restoringView!=='undefined')syncViewURL();
}
document.getElementById('theme-btn').addEventListener('click',()=>{
  const order=['auto','light','dark'], cur=localStorage.getItem('tk-theme')||'auto';
  applyTheme(order[(order.indexOf(cur)+1)%order.length]);
});
// 初始主题：URL ?t=light|dark 优先（可分享/截图），否则 localStorage，否则跟随系统
(function(){
  const q=(new URLSearchParams(location.search).get('t')||'').toLowerCase();
  applyTheme(['light','dark'].includes(q)?q:(localStorage.getItem('tk-theme')||'auto'));
})();

// CSV 导出（当前粒度 + 所选模型）
function exportCSV(){
  const rows=selectedRows(), cols=DATA.models.filter(m=>state.models.has(m));
  const head=['period','total_tokens',...cols.map(pretty),'calls'];
  const body=rows.map(r=>[r.period,r.total,...cols.map(m=>r.models[m]||0),r.calls]);
  const csv=[head,...body].map(r=>r.map(x=>/[,\"\n]/.test(String(x))?'"'+String(x).replace(/"/g,'""')+'"':x).join(',')).join('\n');
  const blob=new Blob(['﻿'+csv],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='tokens-'+state.gran+'.csv'; a.click();
}
document.getElementById('csv-btn').addEventListener('click', exportCSV);
function exportMarkdown(){
  const rows=selectedRows(), cols=DATA.models.filter(m=>state.models.has(m));
  const head=[LABEL[state.gran],'总 token',...cols.map(pretty),'调用'];
  const body=rows.map(r=>[r.period,fmt(r.total),...cols.map(m=>fmt(r.models[m]||0)),fmt(r.calls)]);
  const line=a=>'| '+a.join(' | ')+' |';
  const md=['# Token 用量报告','',line(head),line(head.map((_,i)=>i?'---:':'---')),...body.map(line),'','> 本地生成于 '+DATA.generated+'，未上传任何数据。'].join('\n');
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([md],{type:'text/markdown;charset=utf-8'}));a.download='tokens-'+state.gran+'.md';a.click();toast('Markdown 报告已生成');
}
document.getElementById('md-btn').addEventListener('click',exportMarkdown);
function openHelp(){document.getElementById('help-modal').classList.add('open');document.getElementById('help-modal').setAttribute('aria-hidden','false');document.getElementById('help-close').focus();}
function closeHelp(){const el=document.getElementById('help-modal');el.classList.remove('open');el.setAttribute('aria-hidden','true');}
document.getElementById('help-close').addEventListener('click',closeHelp);document.getElementById('help-modal').addEventListener('click',e=>{if(e.target.id==='help-modal')closeHelp();});
// 键盘：1/2/3 切粒度，T 切主题，E 导出 CSV，? 查看帮助
document.addEventListener('keydown',e=>{
  const tag=(e.target.tagName||'').toUpperCase();
  if(tag==='INPUT'||tag==='TEXTAREA') return;
  if(e.key==='1') setGran('day');
  else if(e.key==='2') setGran('week');
  else if(e.key==='3') setGran('month');
  else if(e.key==='t'||e.key==='T'){ const o=['auto','light','dark'],c=localStorage.getItem('tk-theme')||'auto'; applyTheme(o[(o.indexOf(c)+1)%3]); }
  else if(e.key==='e'||e.key==='E') exportCSV();
  else if(e.key==='?') openHelp();
});

/* ---- 趣味 / 意想不到的交互 ---- */
function toast(msg, ms=2600){
  let t=document.getElementById('toast');
  if(!t){t=document.createElement('div');t.id='toast';document.body.appendChild(t);}
  t.textContent=msg;t.classList.add('show');clearTimeout(t._t);
  t._t=setTimeout(()=>t.classList.remove('show'),ms);
}
function confetti(){
  const cs=['#5b8def','#a78bfa','#f472b6','#14b8a6','#f59e0b','#7aa2f7'];
  for(let i=0;i<90;i++){
    const d=document.createElement('div');d.className='confetti';
    d.style.left=(Math.random()*100)+'vw';d.style.background=cs[i%cs.length];
    d.style.animationDelay=(Math.random()*.5)+'s';d.style.animationDuration=(1.6+Math.random()*1)+'s';
    document.body.appendChild(d);setTimeout(()=>d.remove(),2700);
  }
}
// Konami ↑↑↓↓←→←→BA
(function(){
  const SEQ=['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a'];
  let i=0;
  document.addEventListener('keydown',e=>{
    const k=e.key.length===1?e.key.toLowerCase():e.key;
    if(k===SEQ[i]){i++;if(i===SEQ.length){i=0;confetti();toast('🎉 Konami 触发！真·肝帝已觉醒');}}
    else i=(k===SEQ[0])?1:0;
  });
})();
// 点 Logo：随机吐槽/夸奖
document.getElementById('logo').addEventListener('click',()=>{
  const lg=document.getElementById('logo');lg.classList.remove('spin');void lg.offsetWidth;lg.classList.add('spin');
  const h=DATA.hourly||[];let ph=-1,pi=-1;for(let i=0;i<24;i++)if((h[i]||0)>ph){ph=h[i]||0;pi=i;}
  const top=(DATA.top_cwds&&DATA.top_cwds[0])?DATA.top_cwds[0][0]:'—';
  const calls=(DATA.day||[]).reduce((a,r)=>a+r.calls,0);
  const F=[
    '缓存帮你省了 '+human(DATA.cache_read||0)+' token，钱包松了口气',
    '峰值在 '+(pi>=0?String(pi).padStart(2,'0')+':00':'?')+'，夜猫子实锤',
    human(lastTotal)+' token ≈ '+fmt(Math.max(0,Math.round(lastTotal/27000)))+' 篇毕业论文',
    '最肝的项目：'+top,
    '别肝了，站起来活动活动 🧘',
    '已累计 '+fmt(calls)+' 次调用，键盘冒烟了',
    '今日份的算力已燃烧 ✨'
  ];
  toast(F[Math.floor(Math.random()*F.length)]);
});
// 点 Hero 数字：短按切换表达方式；双击复制精确值
const heroValue=document.querySelector('.kpi.is-primary .v');
heroValue.addEventListener('click',()=>{
  state.numberMode=(state.numberMode+1)%3;
  document.getElementById('k-total').textContent=displayNumber(lastTotal);
  toast(['精确数字','中文数量级','国际缩写'][state.numberMode]);
});
heroValue.addEventListener('dblclick',()=>{
  try{navigator.clipboard.writeText(String(lastTotal));}catch(e){}
  toast('已复制 '+fmt(lastTotal)+' token');
});
// Hero 跟手光斑
(function(){
  const el=document.querySelector('.kpi.is-primary');
  if(!el)return;
  el.addEventListener('mousemove',e=>{const r=el.getBoundingClientRect();el.style.setProperty('--mx',(e.clientX-r.left)+'px');el.style.setProperty('--my',(e.clientY-r.top)+'px');});
})();
// 趣味换算
const FUN=[
  ['一本《红楼梦》全文',1000000],['一部《三体》三部曲',1200000],['整部《哈利波特》',1300000],
  ['一部《指环王》三部曲',1700000],['一集美剧字幕',10000],['一首流行歌词',400],
  ['一篇本科毕业论文',27000],['一次深度对话',5000],['一行代码',8],['一条推文',30],
  ['小时人类高速打字',18000],['杯程序员续命美式',250000],['次完整阅读技术文档',45000],
  ['小时键盘持续敲击',12000],['个中型函数的代码量',1800]
];
function renderFunFacts(){
  const box=document.getElementById('funfacts'), t=lastTotal||0;
  if(t<=0){box.innerHTML='<div class="hint">无数据</div>';return;}
  let cands=FUN.map(([l,p])=>({l,p,n:t/p})).filter(x=>x.n>=0.3&&x.n<1e7).sort((a,b)=>b.n-a.n);
  for(let i=cands.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[cands[i],cands[j]]=[cands[j],cands[i]];}
  box.innerHTML=cands.slice(0,3).map(x=>{
    const num=x.n>=100?fmt(Math.round(x.n)):(x.n>=10?x.n.toFixed(1):x.n.toFixed(2));
    return '<div class=ff><span class=ff-n>'+num+'</span><span class=ff-l>'+x.l+'</span></div>';
  }).join('') || '<div class="hint">数据太少，肝得还不够</div>';
}
document.getElementById('fun-shuffle').addEventListener('click',renderFunFacts);

/* ---- 模块开关（附加功能可勾选 + 记忆）---- */
const MODS_KEY='tk-mods', MOD_DEFAULT={clock:true,fun:true,block:true,daily:true,rhythm:true,fortune:true,multiples:true,flow:true,creature:true,race:true,badges:true,dna:true,top:true};
function loadMods(){ try{ const m=Object.assign({},JSON.parse(localStorage.getItem(MODS_KEY)||'{}'));let legacy;if(Object.prototype.hasOwnProperty.call(m,'orbit'))legacy=m.orbit;else if(Object.prototype.hasOwnProperty.call(m,'city'))legacy=m.city;if(!Object.prototype.hasOwnProperty.call(m,'flow')&&legacy!==undefined)m.flow=legacy;delete m.orbit;delete m.city;localStorage.setItem(MODS_KEY,JSON.stringify(m));return m; }catch(e){ return {}; } }
function applyMods(){
  const m=Object.assign({},MOD_DEFAULT,loadMods());
  document.querySelectorAll('[data-module]').forEach(el=>{ el.style.display = m[el.dataset.module]===false ? 'none' : ''; });
  document.querySelectorAll('[data-sw]').forEach(sw=>{
    const on=m[sw.dataset.sw]!==false; sw.classList.toggle('on',on);
    const cb=document.querySelector('input[data-mod="'+sw.dataset.sw+'"]'); if(cb) cb.checked=on;
  });
}
document.getElementById('mods-btn').addEventListener('click',e=>{ e.stopPropagation(); document.getElementById('mods-pop').classList.toggle('open'); });
document.addEventListener('click',e=>{ if(!e.target.closest('#mods-pop')&&!e.target.closest('#mods-btn')) document.getElementById('mods-pop').classList.remove('open'); });
document.querySelectorAll('#mods-pop .mrow').forEach(row=>{
  row.addEventListener('click',()=>{
    const sw=row.querySelector('[data-sw]'); if(!sw) return;
    const k=sw.dataset.sw, m=Object.assign({},MOD_DEFAULT,loadMods());
    m[k]=m[k]===false; try{localStorage.setItem(MODS_KEY,JSON.stringify(m));}catch(e){}
    applyMods();
  });
});

/* ---- 5h 计费窗口 ---- */
function renderBlock(){
  const b=DATA.block||{total:0,buckets:[]}, bars=document.getElementById('block-bars');
  document.getElementById('block-total').textContent=human(b.total)+' tk';
  const bk=b.buckets||[], max=Math.max(1,...bk.map(x=>x.total));
  bars.innerHTML=bk.map(x=>'<div class=bb style="height:'+Math.max(3,x.total/max*100).toFixed(1)+'%" title="'+String(x.h).padStart(2,'0')+':00 · '+human(x.total)+' tk"><span>'+String(x.h).padStart(2,'0')+'</span></div>').join('');
  document.getElementById('block-now').textContent='近 6 个小时桶（按生成时刻往前）';
}

/* ---- 每天（近 14 天）迷你柱条 ---- */
function renderDaily(){
  const box=document.getElementById('daily-bars'), days=(DATA.day||[]).slice(-14);
  if(!days.length){ box.innerHTML='<div class="hint" style="width:100%">无数据</div>'; document.getElementById('daily-total').textContent=''; return; }
  const max=Math.max(1,...days.map(d=>d.total)), tot=days.reduce((a,d)=>a+d.total,0);
  document.getElementById('daily-total').textContent=human(tot)+' tk · '+days.length+' 天';
  box.innerHTML=days.map(d=>{
    const h=Math.max(3,d.total/max*100), dd=(d.period||'').split('-')[2]||'?';
    return '<div class=bb style="height:'+h.toFixed(1)+'%" title="'+esc(d.period)+' · '+human(d.total)+' tk（'+d.calls+' 次）"><span>'+dd+'</span></div>';
  }).join('');
}

function showRhythmTip(cell,e){
  const tip=document.getElementById('rhythm-tip'), v=Number(cell.dataset.value||0), share=cell.dataset.share||'0.0', h=Number(cell.dataset.hour||0);
  const part=h<5?'深夜':h<9?'清晨':h<12?'上午':h<14?'午间':h<18?'下午':h<22?'夜晚':'深夜';
  tip.innerHTML='<b>'+esc(cell.dataset.day)+' · '+String(h).padStart(2,'0')+':00–'+String((h+1)%24).padStart(2,'0')+':00</b><div><span class="rh-v">'+fmt(v)+'</span> Token</div><span>'+part+'时段 · 占当天 '+share+'% · 点击回看这一天</span>';
  tip.classList.add('on'); moveRhythmTip(e);
}
function moveRhythmTip(e){
  const tip=document.getElementById('rhythm-tip'), gap=14, w=tip.offsetWidth||190, h=tip.offsetHeight||70;
  let x=e.clientX+gap,y=e.clientY+gap;if(x+w>innerWidth-8)x=e.clientX-w-gap;if(y+h>innerHeight-8)y=e.clientY-h-gap;
  tip.style.left=x+'px';tip.style.top=y+'px';
}
function hideRhythmTip(){document.getElementById('rhythm-tip').classList.remove('on');}

function renderRhythm(){
  const box=document.getElementById('rhythm'), days=(DATA.day||[]).slice(-14), det=DATA.day_details||{};
  if(!days.length){box.innerHTML='<div class="hint">无数据</div>';document.getElementById('rhythm-persona').textContent='';return;}
  const matrix=days.map(d=>{ const x=det[d.period], out=Array(24).fill(0); if(x) Object.entries(x.hourly_models||{}).forEach(([m,h])=>{if(state.models.has(m))h.forEach((v,i)=>out[i]+=v||0);}); return out; });
  const vals=matrix.flat().filter(Boolean).sort((a,b)=>a-b), max=Math.max(1,...vals), q=p=>vals.length?vals[Math.min(vals.length-1,Math.floor(vals.length*p))]:1;
  const cuts=[q(.25),q(.5),q(.75),max]; let html='<div class="rhythm-grid"><div></div>'+days.map(d=>'<div class="rh-day">'+esc((d.period||'').slice(5).replace('-','/'))+'</div>').join('');
  const dayTotals=matrix.map(a=>a.reduce((x,y)=>x+y,0));
  for(let h=0;h<24;h++){html+='<div class="rh-hour">'+(h%3===0?String(h).padStart(2,'0'):'')+'</div>';for(let d=0;d<days.length;d++){const v=matrix[d][h],lv=!v?0:v<=cuts[0]?1:v<=cuts[1]?2:v<=cuts[2]?3:4,share=dayTotals[d]?v/dayTotals[d]*100:0;html+='<div class="rh-cell l'+lv+'" data-day="'+esc(days[d].period)+'" data-hour="'+h+'" data-value="'+v+'" data-share="'+share.toFixed(1)+'" aria-label="'+esc(days[d].period)+' '+String(h).padStart(2,'0')+':00，'+fmt(v)+' token"></div>';}}
  box.innerHTML=html+'</div>';
  box.querySelectorAll('.rh-cell').forEach(c=>{
    c.addEventListener('click',()=>{state.gran='day';document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x.dataset.gran==='day'));state.focusPeriod=c.dataset.day;hideRhythmTip();render();});
    c.addEventListener('mouseenter',e=>showRhythmTip(c,e));
    c.addEventListener('mousemove',moveRhythmTip);
    c.addEventListener('mouseleave',hideRhythmTip);
  });
  const hs=Array(24).fill(0);matrix.forEach(a=>a.forEach((v,i)=>hs[i]+=v));const total=hs.reduce((a,b)=>a+b,0),sum=(a,b)=>hs.slice(a,b).reduce((x,y)=>x+y,0);
  let p=['☀️','日间稳定型','算力主要沿着白昼平稳展开。'];
  if(total&&sum(0,6)+sum(22,24)>total*.42)p=['🌙','午夜航行型','你的高密度思考更常发生在城市熄灯以后。'];
  else if(total&&sum(5,10)>total*.38)p=['🌅','晨光启动型','大部分算力在清晨苏醒，像一台提前预热的机器。'];
  else if(total&&sum(17,22)>total*.4)p=['🌆','黄昏冲刺型','越接近夜幕，Token 越开始加速。'];
  else if(hs.filter(v=>v>0).length>=20)p=['🌐','全时域高能体','一天几乎没有真正的静默区。'];
  document.getElementById('rhythm-persona').innerHTML=p[0]+' <b>'+p[1]+'</b> · '+p[2];
}

function modelHover(model,on){
  document.querySelectorAll('[data-model]').forEach(el=>{const same=el.dataset.model===model;el.classList.toggle('model-hot',on&&same);el.classList.toggle('model-dim',on&&!same);});
}
function bindModelLinks(){
  document.querySelectorAll('[data-model]').forEach(el=>{el.addEventListener('mouseenter',()=>modelHover(el.dataset.model,true));el.addEventListener('mouseleave',()=>modelHover(el.dataset.model,false));});
}

function currentFlow(){
  if(!state.focusPeriod)return DATA.flow||{project_model:[],model_session:[]};
  const fd=focusDays(),pm={},ms={};
  (fd||[]).forEach(day=>{const f=DATA.day_details[day]?.flow;if(!f)return;(f.project_model||[]).forEach(x=>{const k=x[1]+'::'+x[2],v=pm[k]||[x[0],x[1],x[2],0];v[3]+=x[3]||0;pm[k]=v;});(f.model_session||[]).forEach(x=>{const k=x[0]+'::'+x[2],v=ms[k]||[x[0],x[1],x[2],0];v[3]+=x[3]||0;ms[k]=v;});});
  return {project_model:Object.values(pm),model_session:Object.values(ms)};
}
let flowLocked=null;
function renderFlow(){
  const svg=document.getElementById('flow-map'),raw=currentFlow(),selectedTotal=selectedRows().reduce((a,r)=>a+r.total,0);
  const pm=(raw.project_model||[]).filter(x=>state.models.has(x[2])&&x[3]>0),ms=(raw.model_session||[]).filter(x=>state.models.has(x[0])&&x[3]>0);
  const sumBy=(arr,key,val)=>{const o={};arr.forEach(x=>o[x[key]]=(o[x[key]]||0)+(x[val]||0));return o;};
  const pmModels=sumBy(pm,2,3),msModels=sumBy(ms,0,3),allModels=new Set([...Object.keys(pmModels),...Object.keys(msModels)]),mt={};allModels.forEach(m=>mt[m]=Math.max(pmModels[m]||0,msModels[m]||0));
  const modelIds=Object.keys(mt).filter(m=>state.models.has(m)).sort((a,b)=>(mt[b]||0)-(mt[a]||0)).slice(0,7),modelSet=new Set(modelIds),modelPM=pm.filter(x=>modelSet.has(x[2])),modelMS=ms.filter(x=>modelSet.has(x[0])),pt=sumBy(modelPM,1,3),st=sumBy(modelMS,2,3);
  const projectIds=Object.keys(pt).sort((a,b)=>pt[b]-pt[a]).slice(0,7),sessionIds=Object.keys(st).sort((a,b)=>st[b]-st[a]).slice(0,8),projectSet=new Set(projectIds),sessionSet=new Set(sessionIds),linksPM=modelPM.filter(x=>projectSet.has(x[1])),linksMS=modelMS.filter(x=>sessionSet.has(x[2]));
  if(!linksPM.length&&!linksMS.length){svg.innerHTML='<text x="560" y="220" text-anchor="middle" class="flow-col">暂无所选模型的流向数据</text>';document.getElementById('flow-stats').innerHTML='<span>0 条流光链路</span>';showFlowPanel(null);return;}
  const W=1120,H=470,xpos={project:130,model:560,session:990},layout=(ids,totals,type)=>{const gap=(H-90)/Math.max(1,ids.length),out={};ids.forEach((id,i)=>out[id]={x:xpos[type],y:55+gap*(i+.5),total:totals[id]||0});return out;},P=layout(projectIds,pt,'project'),M=layout(modelIds,mt,'model'),S=layout(sessionIds,st,'session'),maxLink=Math.max(1,...linksPM.map(x=>x[3]),...linksMS.map(x=>x[3]));
  const sessionLabels={};ms.forEach(x=>sessionLabels[x[2]]=x[1]);const projectLabels={};pm.forEach(x=>projectLabels[x[1]]=x[0]);
  let p=['<defs>'];modelIds.forEach((m,i)=>{const c=DATA.colors[m]||'#7aa2f7';p.push('<linearGradient id="flow-g-'+i+'" x1="0" x2="1"><stop stop-color="'+c+'" stop-opacity=".25"/><stop offset=".5" stop-color="'+c+'"/><stop offset="1" stop-color="'+c+'" stop-opacity=".35"/></linearGradient>');});p.push('</defs><text class="flow-col" x="55" y="28">PROJECT</text><text class="flow-col" x="520" y="28">MODEL</text><text class="flow-col" x="942" y="28">SESSION</text>');
  const path=(a,b)=>'M '+a.x+' '+a.y+' C '+(a.x+150)+' '+a.y+' '+(b.x-150)+' '+b.y+' '+b.x+' '+b.y;
  linksPM.forEach(x=>{const mi=modelIds.indexOf(x[2]),w=2+Math.sqrt(x[3]/maxLink)*17;p.push('<path class="flow-link motion" data-flow-from="project:'+esc(x[1])+'" data-flow-model="'+esc(x[2])+'" d="'+path(P[x[1]],M[x[2]])+'" stroke="url(#flow-g-'+mi+')" stroke-width="'+w.toFixed(1)+'"><title>'+esc(x[0])+' → '+esc(pretty(x[2]))+' · '+fmt(x[3])+' Token</title></path>');});
  linksMS.forEach(x=>{const mi=modelIds.indexOf(x[0]),w=2+Math.sqrt(x[3]/maxLink)*17;p.push('<path class="flow-link motion" data-flow-model="'+esc(x[0])+'" data-flow-to="session:'+esc(x[2])+'" d="'+path(M[x[0]],S[x[2]])+'" stroke="url(#flow-g-'+mi+')" stroke-width="'+w.toFixed(1)+'"><title>'+esc(pretty(x[0]))+' → '+esc(x[1])+' · '+fmt(x[3])+' Token</title></path>');});
  const node=(type,id,pos,label,total,color)=>{const share=Math.min(100,selectedTotal?total/selectedTotal*100:0),boxX=pos.x-80,boxY=pos.y-20,canLock=type!=='session';return '<g class="flow-node '+type+'" data-flow-type="'+type+'" data-flow-id="'+esc(id)+'" data-flow-name="'+esc(label)+'" data-flow-total="'+total+'" data-flow-share="'+share.toFixed(2)+'" tabindex="0" role="button" aria-label="'+(type==='project'?'项目 ':type==='model'?'模型 ':'会话 ')+esc(label)+'，'+fmt(total)+' Token，占比 '+share.toFixed(1)+'%"><rect class="flow-hit" x="'+(boxX-6)+'" y="'+(boxY-4)+'" width="172" height="48" rx="12"/><rect class="flow-box" x="'+boxX+'" y="'+boxY+'" width="160" height="40" rx="10" fill="'+color+'" fill-opacity=".22"/><text x="'+pos.x+'" y="'+(pos.y-2)+'" text-anchor="middle">'+esc(label.length>20?label.slice(0,19)+'…':label)+'</text><text class="flow-value" x="'+pos.x+'" y="'+(pos.y+13)+'" text-anchor="middle">'+human(total)+' tk</text><title>'+(canLock?'点击锁定链路':'点击回放会话')+'</title></g>';};
  projectIds.forEach((id,i)=>p.push(node('project',id,P[id],projectLabels[id]||id,pt[id],['#5b8def','#14b8a6','#a78bfa','#38bdf8'][i%4])));modelIds.forEach(m=>p.push(node('model',m,M[m],pretty(m),mt[m],DATA.colors[m]||'#7aa2f7')));sessionIds.forEach((id,i)=>p.push(node('session',id,S[id],sessionLabels[id]||id,st[id],['#f472b6','#f59e0b','#a78bfa','#38bdf8'][i%4])));
  svg.innerHTML=p.join('');document.getElementById('flow-stats').innerHTML='<span>'+projectIds.length+' 个项目</span><span>'+modelIds.length+' 个模型</span><span>'+sessionIds.length+' 个会话</span><span>'+(linksPM.length+linksMS.length)+' 条真实流向</span>';
  const nodes=[...svg.querySelectorAll('.flow-node')],links=[...svg.querySelectorAll('.flow-link')],keyFor=n=>n.dataset.flowType+':'+n.dataset.flowId,dataFor=n=>({type:n.dataset.flowType,id:n.dataset.flowId,name:n.dataset.flowName,total:Number(n.dataset.flowTotal),share:Number(n.dataset.flowShare)});
  const illuminate=n=>{const key=keyFor(n),type=n.dataset.flowType,id=n.dataset.flowId,models=new Set();if(type==='model')models.add(id);if(type==='project')links.filter(l=>l.dataset.flowFrom===key).forEach(l=>models.add(l.dataset.flowModel));if(type==='session')links.filter(l=>l.dataset.flowTo===key).forEach(l=>models.add(l.dataset.flowModel));links.forEach(l=>{const hot=type==='model'?l.dataset.flowModel===id:type==='project'?(l.dataset.flowFrom===key||models.has(l.dataset.flowModel)):type==='session'?(l.dataset.flowTo===key||models.has(l.dataset.flowModel)):false;l.classList.toggle('hot',hot);l.classList.toggle('dim',!hot);});const active=new Set([key]);links.filter(l=>l.classList.contains('hot')).forEach(l=>{if(l.dataset.flowFrom)active.add(l.dataset.flowFrom);if(l.dataset.flowTo)active.add(l.dataset.flowTo);if(l.dataset.flowModel)active.add('model:'+l.dataset.flowModel);});nodes.forEach(x=>x.classList.toggle('dim',!active.has(keyFor(x))));};
  const clear=()=>{links.forEach(l=>l.classList.remove('hot','dim'));nodes.forEach(n=>n.classList.remove('dim'));};
  nodes.forEach(n=>{n.addEventListener('mouseenter',()=>{illuminate(n);showFlowPanel(dataFor(n));});n.addEventListener('focus',()=>{illuminate(n);showFlowPanel(dataFor(n));});n.addEventListener('mouseleave',()=>{if(!flowLocked){clear();showFlowPanel(null);}});n.addEventListener('blur',()=>{if(!flowLocked){clear();showFlowPanel(null);}});const activate=()=>{const d=dataFor(n);if(d.type==='session'){openReplay(d.id,d.name);return;}const k=keyFor(n);flowLocked=flowLocked===k?null:k;nodes.forEach(x=>x.classList.toggle('locked',keyFor(x)===flowLocked));if(flowLocked){illuminate(n);showFlowPanel(d,true);}else{clear();showFlowPanel(null);}};n.addEventListener('click',activate);n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}});});
  if(flowLocked){const locked=nodes.find(n=>keyFor(n)===flowLocked);if(locked){locked.classList.add('locked');illuminate(locked);showFlowPanel(dataFor(locked),true);}else flowLocked=null;}else showFlowPanel(null);
}
function showFlowPanel(d,locked=false){const panel=document.getElementById('flow-panel');if(!d){panel.innerHTML='<b>Token 流光图</b><span>① 悬停追踪链路　② 点击项目或模型锁定　③ 点击会话回放</span>';return;}const type=d.type==='project'?'项目':d.type==='model'?'模型':'会话';panel.innerHTML='<b>'+type+' · '+esc(d.name)+'</b><span>'+fmt(d.total)+' Token · 占当前筛选总量 '+d.share.toFixed(1)+'%'+(locked?' · 已锁定，再点取消':d.type==='session'?' · 点击回放':' · 点击锁定链路')+'</span>';}
function saveFlowSVG(){const source=document.getElementById('flow-map');if(!source.querySelector('.flow-node')){toast('当前筛选没有可导出的流向');return;}const svg=source.cloneNode(true);svg.setAttribute('xmlns','http://www.w3.org/2000/svg');svg.setAttribute('width','1120');svg.setAttribute('height','470');const bg=document.createElementNS('http://www.w3.org/2000/svg','rect');bg.setAttribute('width','1120');bg.setAttribute('height','470');bg.setAttribute('fill','#0b1120');svg.insertBefore(bg,svg.firstChild);const style=document.createElementNS('http://www.w3.org/2000/svg','style');style.textContent='.flow-col{fill:#8fa3c0;font:800 10px sans-serif;letter-spacing:.14em}.flow-link{fill:none;stroke-linecap:round;opacity:.58}.flow-box{stroke:rgba(255,255,255,.7);stroke-width:1}.flow-node text{fill:#e1ecfb;font:700 10px sans-serif}.flow-node .flow-value{fill:#9badc7;font:600 8.5px sans-serif}.flow-hit{display:none}';svg.insertBefore(style,bg.nextSibling);const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['<?xml version="1.0"?>\n'+svg.outerHTML],{type:'image/svg+xml'}));a.download='token-flow-'+state.gran+(state.focusPeriod?'-'+state.focusPeriod:'')+'.svg';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);toast('当前流光图已保存为 SVG');}
document.getElementById('flow-save').addEventListener('click',saveFlowSVG);

function renderCreature(){
  const svg=document.getElementById('creature'),days=DATA.day||[],total=days.reduce((a,d)=>a+d.total,0),h=DATA.hourly||[],ht=h.reduce((a,b)=>a+b,0),night=(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))/(ht||1);
  const cr=DATA.cache_read||0,cache=total?cr/total:0,models=Math.max(1,DATA.models.length),projects=Math.max(1,DATA.n_cwds||1),streak=Math.min(40,days.length),stage=total>=1e9?5:total>=1e8?4:total>=1e7?3:total>=1e6?2:1;
  const names=['微光幼体','上下文游鱼','缓存水母','算力星灵','Token 远古体'],prefix=night>.42?'午夜':cache>.7?'晶核':models>=5?'虹彩':projects>=20?'漫游':'静默';
  const size=48+stage*8, tent=3+Math.min(7,models), spots=Math.min(18,Math.ceil(projects/2)), hue=(total%240)+80;
  let p=['<defs><radialGradient id="cg" cx="38%" cy="30%"><stop offset="0" stop-color="hsl('+hue+' 90% 82%)"/><stop offset=".55" stop-color="hsl('+hue+' 76% 61%)"/><stop offset="1" stop-color="hsl('+(hue+45)+' 70% 38%)"/></radialGradient><filter id="gl"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'];
  p.push('<ellipse cx="130" cy="223" rx="'+(36+stage*4)+'" ry="7" fill="rgba(0,0,0,.16)"/>');
  for(let i=0;i<tent;i++){const x=92+i*(76/Math.max(1,tent-1)),len=25+((i*13+total)%25);p.push('<path d="M '+x+' 169 Q '+(x-12+(i%3)*10)+' '+(190+len/3)+' '+(x+(i%2?8:-8))+' '+(180+len)+'" fill="none" stroke="hsl('+(hue+i*8)+' 72% 58%)" stroke-width="'+(4+(i%3))+'" stroke-linecap="round" opacity=".65"/>');}
  p.push('<path d="M '+(130-size)+' 145 Q '+(130-size+4)+' '+(80-stage*3)+' 130 '+(71-stage*4)+' Q '+(130+size-4)+' '+(80-stage*3)+' '+(130+size)+' 145 Q '+(130+size-5)+' 174 130 178 Q '+(130-size+5)+' 174 '+(130-size)+' 145Z" fill="url(#cg)" stroke="rgba(255,255,255,.5)" stroke-width="1.5" filter="url(#gl)"/>');
  for(let i=0;i<spots;i++){const a=(i*2.399)+(total%11),r=size*.62*Math.sqrt((i+1)/(spots+1)),x=130+Math.cos(a)*r,y=126+Math.sin(a)*r*.55;p.push('<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+(1.8+(i%3))+'" fill="rgba(255,255,255,'+(cache*.55+.18).toFixed(2)+')"/>');}
  const eyeY=132,eyeGap=18+stage*2;p.push('<g class="creature-eye"><ellipse cx="'+(130-eyeGap)+'" cy="'+eyeY+'" rx="7" ry="'+(night>.4?9:7)+'" fill="#111827"/><circle cx="'+(128-eyeGap)+'" cy="'+(eyeY-2)+'" r="2" fill="white"/><ellipse cx="'+(130+eyeGap)+'" cy="'+eyeY+'" rx="7" ry="'+(night>.4?9:7)+'" fill="#111827"/><circle cx="'+(128+eyeGap)+'" cy="'+(eyeY-2)+'" r="2" fill="white"/></g>');
  p.push('<path d="M 119 153 Q 130 '+(158+stage)+' 141 153" fill="none" stroke="rgba(17,24,39,.75)" stroke-width="2.3" stroke-linecap="round"/>');
  if(cache>.65)p.push('<path d="M 104 105 Q 130 75 156 105" fill="none" stroke="rgba(255,255,255,.72)" stroke-width="3" stroke-linecap="round"/><circle cx="130" cy="86" r="6" fill="hsl('+(hue+90)+' 90% 73%)" filter="url(#gl)"/>');
  svg.innerHTML=p.join('');document.getElementById('creature-name').textContent=prefix+'·'+names[stage-1];document.getElementById('creature-desc').textContent='由总量、模型、项目、缓存与作息共同塑形 · 每份数据只会诞生这一只';
  document.getElementById('creature-info').innerHTML='<div><b>形态 '+stage+'/5</b>进化阶段</div><div><b>'+tent+' 条</b>模型触须</div><div><b>'+spots+' 枚</b>项目星斑</div><div><b>'+Math.round(cache*100)+'%</b>晶核纯度</div><div><b>'+Math.round(night*100)+'%</b>夜行倾向</div><div><b>'+streak+'</b>生命年轮</div>';
}
document.getElementById('creature-save').addEventListener('click',()=>{const s=document.getElementById('creature').cloneNode(true);s.setAttribute('xmlns','http://www.w3.org/2000/svg');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([s.outerHTML],{type:'image/svg+xml'}));a.download='token-creature.svg';a.click();toast('Token 生物已保存');});

/* ---- 每模型迷你趋势（small multiples）---- */
function renderMultiples(){
  const box=document.getElementById('multiples'), days=DATA.day||[];
  if(!days.length||!DATA.models.length){ box.innerHTML='<div class="hint">无数据</div>'; return; }
  box.innerHTML=DATA.models.map(m=>{
    const s=days.map(d=>d.models[m]||0), total=s.reduce((a,b)=>a+b,0), max=Math.max(1,...s), W=120,H=32,c=DATA.colors[m];
    let path=''; s.forEach((v,i)=>{ const x=i/Math.max(1,s.length-1)*W, y=H-3-(v/max)*(H-6); path+=(i?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)+' '; });
    const area=path+'L '+W+' '+H+' L 0 '+H+' Z';
    return '<div class=mp data-model="'+esc(m)+'"><div class=nm><i style="background:'+c+'"></i>'+esc(pretty(m))+'</div><div class=vt>'+human(total)+'</div>'
      +'<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none"><path d="'+area+'" fill="'+c+'" fill-opacity="0.16"/><path d="'+path+'" fill="none" stroke="'+c+'" stroke-width="1.5" stroke-linejoin="round"/></svg></div>';
  }).join('');
}

/* ---- 柱图竞赛（累计 token 随日演变）---- */
let raceTimer=null, raceIdx=0;
function raceData(){
  const days=DATA.day||[], cum={}, out=[];
  days.forEach(d=>{ Object.keys(d.models).forEach(m=>cum[m]=(cum[m]||0)+d.models[m]); out.push({day:d.period,cum:Object.assign({},cum)}); });
  return out;
}
function renderRace(){
  const data=raceData(), box=document.getElementById('race');
  if(data.length<2){ box.innerHTML='<div class="hint">数据不足</div>'; document.getElementById('race-day').textContent='';const scrub=document.getElementById('race-scrub');scrub.disabled=true;scrub.max='0';scrub.value='0';scrub.removeAttribute('aria-valuetext'); return; }
  document.getElementById('race-scrub').disabled=false;
  raceIdx=Math.min(raceIdx,data.length-1);
  const cur=data[raceIdx], entries=Object.entries(cur.cum).sort((a,b)=>b[1]-a[1]).slice(0,6), max=Math.max(1,...entries.map(e=>e[1]));
  box.innerHTML=entries.map(([m,v])=>{
    const w=v/max*100;
    return '<div class=race-row><span class=race-name><i style="background:'+DATA.colors[m]+'"></i>'+esc(pretty(m))+'</span>'
      +'<span class=race-bar><i style="width:'+w.toFixed(1)+'%;background:'+DATA.colors[m]+'"></i></span><span class=race-val>'+human(v)+'</span></div>';
  }).join('');
  document.getElementById('race-day').textContent='截至 '+fmtLabel(cur.day,'day');
  document.getElementById('race-pos').textContent=(raceIdx+1)+'/'+data.length;
  const scrub=document.getElementById('race-scrub');scrub.max=String(data.length-1);scrub.value=String(raceIdx);scrub.setAttribute('aria-valuetext','截至 '+fmtLabel(cur.day,'day')+'，第 '+(raceIdx+1)+' / '+data.length+' 期');
}
document.getElementById('race-scrub').addEventListener('input',e=>{if(raceTimer){clearInterval(raceTimer);raceTimer=null;document.getElementById('race-play').textContent='▶ 播放';}raceIdx=Number(e.target.value||0);renderRace();});

document.getElementById('race-play').addEventListener('click',function(){
  const data=raceData();
  if(raceTimer){ clearInterval(raceTimer); raceTimer=null; this.textContent='▶ 播放'; return; }
  if(data.length<2) return;
  raceIdx=0; renderRace(); this.textContent='⏸ 暂停';
  raceTimer=setInterval(()=>{ raceIdx++; if(raceIdx>=data.length){ clearInterval(raceTimer); raceTimer=null; this.textContent='▶ 播放'; raceIdx=data.length-1; } renderRace(); },700);
});

function dataCommands(){
  const days=DATA.day||[],top=[...days].sort((a,b)=>b.total-a.total)[0],h=DATA.hourly||[],peak=h.indexOf(Math.max(...h)),mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));
  const out=[];if(top)out.push({ic:'🔍',t:'最高 Token 日 · '+top.period+' · '+human(top.total),k:'数据',run:()=>{setGran('day');setTimeout(()=>toggleFocus(top.period),30);}});if(peak>=0)out.push({ic:'🌙',t:'最活跃时刻 · '+String(peak).padStart(2,'0')+':00 · '+human(h[peak]),k:'数据',run:()=>document.querySelector('[data-module=clock]').scrollIntoView({behavior:'smooth'})});Object.entries(mt).sort((a,b)=>b[1]-a[1]).forEach(([m,v])=>out.push({ic:'🤖',t:pretty(m)+' · '+human(v)+' · '+(v/Object.values(mt).reduce((a,b)=>a+b,0)*100).toFixed(1)+'%',k:'模型',run:()=>setModels([m],'Solo · '+pretty(m))}));return out;
}
function secretCommand(q){
  q=q.trim().toLowerCase();
  const secrets={
    'whoami':()=>{const x=shareStats();toast((x.peak<6||x.peak>=22?'午夜航行型':'日光构筑型')+'开发者 · '+x.dom+' · '+Math.round(x.cache*100)+'% 缓存',4200);},
    '42':()=>toast('宇宙终极答案是 42，但你的答案是 '+human(lastTotal)+' Token。',4200),
    'coffee':()=>toast('你的 Token 大约够续命 '+fmt(Math.round(lastTotal/250000))+' 杯程序员美式 ☕',4200),
    'sudo':()=>toast('权限不足：算力宇宙拒绝 root 接管。'),
    'rm -rf':()=>toast('操作已拦截。你的 '+fmt((_ach||getBadgeData()).got)+' 枚成就松了一口气。',4200),
    'matrix':()=>{document.body.style.filter='hue-rotate(75deg) saturate(1.5)';toast('Wake up, developer…');setTimeout(()=>document.body.style.filter='',2600);},
    'midnight':()=>{const h=DATA.hourly||[];toast('深夜共留下 '+human(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))+' Token。',4200);},
    'receipt':()=>openShare('receipt'),'passport':()=>openShare('passport'),'flow':()=>scrollToSection('section-flow'),'orbit':()=>scrollToSection('section-flow'),'city':()=>scrollToSection('section-flow'),'creature':()=>document.querySelector('[data-module=creature]').scrollIntoView({behavior:'smooth'})
  };if(secrets[q]){closePalette();setTimeout(secrets[q],80);return true;}return false;
}

function scrollToSection(id){const el=document.getElementById(id);if(!el)return;el.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});}
const SECTION_LINKS=[['section-overview','总览'],['section-trend','趋势'],['section-rhythm','节奏'],['section-flow','流光'],['section-achievements','成就'],['section-top','Top']];
function initSectionDock(){
  const dock=document.getElementById('section-dock');dock.addEventListener('click',e=>{const b=e.target.closest('button[data-target]');if(b)scrollToSection(b.dataset.target);});
  const mark=id=>dock.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.target===id));
  if('IntersectionObserver'in window){const obs=new IntersectionObserver(entries=>{const hit=entries.filter(x=>x.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];if(hit)mark(hit.target.id);},{rootMargin:'-18% 0px -65% 0px',threshold:[0,.15,.4]});SECTION_LINKS.forEach(([id])=>{const el=document.getElementById(id);if(el)obs.observe(el);});}
}
initSectionDock();
document.getElementById('status-pulse').addEventListener('click',()=>scrollToSection('section-trend'));
function usageStatus(rows){if(rows.length<2)return {label:'—',cls:'',last:rows.length?rows[rows.length-1].total:0,avg:null,delta:null,detail:'至少需要两期数据才能计算状态'};const last=rows[rows.length-1].total,prior=rows.slice(Math.max(0,rows.length-5),-1),avg=prior.reduce((a,r)=>a+r.total,0)/Math.max(1,prior.length);if(avg===0){if(last>0)return {label:'升温',cls:'warming',last,avg,delta:null,detail:'此前均值为 0，本期出现新活动'};return {label:'平稳',cls:'steady',last,avg,delta:0,detail:'本期与此前均值均为 0'};}const delta=last/avg-1,label=delta>.12?'升温':delta<-.12?'降温':'平稳',cls=delta>.12?'warming':delta<-.12?'cooling':'steady';return {label,cls,last,avg,delta,detail:'变化 '+(delta>=0?'+':'')+(delta*100).toFixed(1)+'%'};}
function renderStatusPulse(){const el=document.getElementById('status-pulse'),text=document.getElementById('status-text'),s=usageStatus(selectedRows(true));el.classList.remove('warming','steady','cooling');if(s.cls)el.classList.add(s.cls);text.textContent='状态 '+s.label;el.title=s.avg===null?s.detail+' · 点击查看趋势':'最后一期 '+fmt(s.last)+' Token；此前均值 '+fmt(s.avg)+'；'+s.detail+' · 点击查看趋势';}

/* ---- 命令面板 Cmd+K ---- */
function cmdActions(){ return [
  {ic:'◎',t:'跳转 · 总览',k:'',run:()=>scrollToSection('section-overview')},
  {ic:'↗',t:'跳转 · 趋势',k:'',run:()=>scrollToSection('section-trend')},
  {ic:'◫',t:'跳转 · 节奏',k:'',run:()=>scrollToSection('section-rhythm')},
  {ic:'≋',t:'跳转 · Token 流光图',k:'',run:()=>scrollToSection('section-flow')},
  {ic:'◇',t:'跳转 · 成就',k:'',run:()=>scrollToSection('section-achievements')},
  {ic:'№',t:'跳转 · Top',k:'',run:()=>scrollToSection('section-top')},
  {ic:'📅',t:'按日',k:'1',run:()=>setGran('day')},
  {ic:'📆',t:'按周',k:'2',run:()=>setGran('week')},
  {ic:'🗓️',t:'按月',k:'3',run:()=>setGran('month')},
  {ic:'☀️',t:'亮色主题',k:'',run:()=>applyTheme('light')},
  {ic:'🌙',t:'暗色主题',k:'',run:()=>applyTheme('dark')},
  {ic:'🌗',t:'跟随系统主题',k:'T',run:()=>applyTheme('auto')},
  {ic:'⤓',t:'导出 CSV',k:'E',run:exportCSV},
  {ic:'◇',t:'导出 Markdown',k:'',run:exportMarkdown},
  {ic:'◫',t:'切换幻影对比',k:'',run:()=>document.getElementById('compare-btn').click()},
  {ic:'⧉',t:'复制当前视图链接',k:'',run:copyViewLink},
  {ic:'?',t:'查看快捷键与隐藏操作',k:'?',run:openHelp},
  {ic:'🎲',t:'换一组趣味换算',k:'',run:renderFunFacts},
  {ic:'▶',t:'播放柱图竞赛',k:'',run:()=>{ if(!document.getElementById('race').closest('[data-module]')||document.getElementById('race').closest('[data-module]').style.display!=='none') document.getElementById('race-play').click(); }},
  {ic:'⚙️',t:'打开模块开关',k:'',run:()=>document.getElementById('mods-btn').click()},
  {ic:'🎉',t:'撒花彩蛋',k:'',run:()=>{confetti();toast('🎉');}}
]; }
let pal={items:[],i:0};
function openPalette(){ renderPalette(''); document.getElementById('scrim').classList.add('open'); setTimeout(()=>document.getElementById('palette-q').focus(),10); }
function closePalette(){ document.getElementById('scrim').classList.remove('open'); document.getElementById('palette-q').value=''; }
function renderPalette(q){
  const ul=document.getElementById('palette-list'), base=[...cmdActions(),...dataCommands()];
  pal.items=base.filter(a=>!q||(a.t+a.ic+a.k).toLowerCase().includes(q.toLowerCase())); pal.i=0;
  ul.innerHTML = pal.items.length ? pal.items.map((a,i)=>'<li data-i="'+i+'"><span class=ic>'+a.ic+'</span>'+a.t+(a.k?'<span class=k>'+a.k+'</span>':'')+'</li>').join('') : '<div class="empty">无匹配结果 · 试试 whoami、42、matrix、coffee</div>';
  const f=ul.querySelector('li'); if(f) f.classList.add('active');
}
function runPalette(i){ const a=pal.items[i]; if(!a) return; closePalette(); setTimeout(a.run,30); }
document.getElementById('palette-q').addEventListener('input',e=>renderPalette(e.target.value));
document.getElementById('palette-q').addEventListener('keydown',e=>{if(e.key==='Enter'&&secretCommand(e.target.value)){e.preventDefault();e.stopImmediatePropagation();}});
document.getElementById('palette-list').addEventListener('click',e=>{ const li=e.target.closest('li'); if(li) runPalette(+li.dataset.i); });
document.getElementById('scrim').addEventListener('click',e=>{ if(e.target.id==='scrim') closePalette(); });
function syncPal(){ document.querySelectorAll('#palette-list li').forEach((li,i)=>li.classList.toggle('active',i===pal.i)); }
document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&(e.key==='k'||e.key==='K')){ e.preventDefault(); document.getElementById('scrim').classList.contains('open')?closePalette():openPalette(); return; }
  if(e.key==='Escape' && document.getElementById('help-modal').classList.contains('open')){ e.preventDefault(); closeHelp(); return; }
  if(e.key==='Escape' && document.getElementById('replay-modal').classList.contains('open')){ e.preventDefault(); closeReplay(); return; }
  if(e.key==='Escape' && state.focusPeriod){ e.preventDefault(); clearFocus(true); return; }
  if(e.key==='Escape' && document.getElementById('ach-modal').classList.contains('open')){ e.preventDefault(); document.getElementById('ach-modal').classList.remove('open'); return; }
  if(!document.getElementById('scrim').classList.contains('open')) return;
  if(e.key==='Escape'){ e.preventDefault(); closePalette(); }
  else if(e.key==='ArrowDown'){ e.preventDefault(); pal.i=(pal.i+1)%Math.max(1,pal.items.length); syncPal(); }
  else if(e.key==='ArrowUp'){ e.preventDefault(); pal.i=(pal.i-1+Math.max(1,pal.items.length))%Math.max(1,pal.items.length); syncPal(); }
  else if(e.key==='Enter'){ e.preventDefault(); runPalette(pal.i); }
});

/* ---- 成就徽章（生成器：3000+ 枚，四等 + 隐藏 + 分类折叠）---- */
function tierFor(i,n){ const r=n<=1?1:i/Math.max(1,n-1); return r>=.85?'prismatic':r>=.6?'gold':r>=.35?'silver':'bronze'; }
function mk(emoji, value, thresholds, unit, fmt, pool, secret){
  // 阶梯名称带序号，确保大图鉴中每枚都有独立身份。
  return thresholds.map((v,i)=>({e:emoji,n:pool[i%pool.length]+' · '+String(i+1).padStart(2,'0'),d:fmt(v)+unit,tier:tierFor(i,thresholds.length),ok:value>=v,secret:!!secret}));
}
const POOL_BIG=['初窥门径','初出茅庐','渐入佳境','小试牛刀','初露锋芒','小有所成','炉火纯青','驾轻就熟','游刃有余','登堂入室','十万火急','名声大噪','百万富翁','声名鹊起','日进斗金','富甲一方','千万大咖','名震江湖','亿万身家','一方霸主','登峰造极','富可敌国','名扬四海','威震天下','通天代','权倾朝野','宇宙级','神话','超凡入圣','不可名状','超脱','永恒','无尽','太初','混沌','虚无','归零','重启','飞升','涅槃'];
const POOL_STREAK=['初心','坚持','小成','连胜','热身','入门','上进','勤奋','刻苦','钻研','精通','大成','宗师','泰斗','传奇','不朽','一鼓作气','再接再厉','持之以恒','锲而不舍','水滴石穿','铁杵磨针','日复一日','年复一年','春秋不辍','冬夏无休','雷打不动','风雨无阻','马不停蹄','日夜兼程'];
const POOL_DAYS=['启程','起步','摸鱼','上手','入坑','沉迷','习惯','日常','本能','呼吸','熔铸','刻入DNA','老用户','熟客','常客','元老','资深','骨灰','活化石','传说玩家'];
const POOL_RATIO=['入门','及格','顺手','熟练','老练','精通','大成','化境','登顶','极限','极致','圆满'];
const WD=['周一','周二','周三','周四','周五','周六','周日'];
const WD_PERSONA=['Monday Blue','周二综合征','周三墙','小周末','TGIF','周末战士','周日恐慌'];
function getBadgeData(){
  const h=DATA.hourly||[]; let peak=-1; for(let i=0;i<24;i++)if((h[i]||0)>(h[peak]||0))peak=i;
  const hoursActive=(h||[]).filter(x=>x>0).length;
  const days=DATA.day||[], total=days.reduce((a,d)=>a+(d.total||0),0), cr=DATA.cache_read||0, cRatio=total?cr/total:0, models=DATA.models.length;
  const dayCount=days.length, maxDay=Math.max(0,...days.map(d=>d.total));
  const calls=days.reduce((a,d)=>a+(d.calls||0),0);
  let streak=0; for(let i=days.length-1;i>=0;i--){ if(days[i].total>0) streak++; else break; }
  const nCwds=DATA.n_cwds||0, nSess=DATA.n_sessions||0, maxTurns=DATA.max_turns||0;
  const avgPerDay=dayCount?total/dayCount:0;
  const AS=DATA.achievement_stats||{}, inputTotal=AS.input||0, outputTotal=AS.output||0, cacheWrite=AS.cache_write||0;
  const sessTotals=AS.session_totals||[], cwdTotals=AS.cwd_totals||[], sourceTotals=AS.source_totals||{}, modelStats=AS.model_stats||{};
  const sortedDays=days.map(d=>d.total||0), sumA=a=>a.reduce((x,y)=>x+y,0), avgA=a=>a.length?sumA(a)/a.length:0;
  const median=a=>{if(!a.length)return 0;const s=[...a].sort((x,y)=>x-y),i=Math.floor(s.length/2);return s.length%2?s[i]:(s[i-1]+s[i])/2;};
  const variance=a=>{const av=avgA(a);return a.length?avgA(a.map(x=>(x-av)*(x-av))):0;};
  const avgSession=nSess?total/nSess:0, avgProject=nCwds?total/nCwds:0, maxSession=sessTotals[0]||0, medSession=median(sessTotals), maxProject=cwdTotals[0]||0;
  const tokensPerCall=calls?total/calls:0, callsPerDay=dayCount?calls/dayCount:0, sessionsPerDay=dayCount?nSess/dayCount:0;
  const dailyCV=avgPerDay?Math.sqrt(variance(sortedDays))/avgPerDay:0;
  const recent7=sortedDays.slice(-7), prior7=sortedDays.slice(-14,-7), avg7=avgA(recent7), avg30=avgA(sortedDays.slice(-30));
  const momentum=avgA(prior7)?avg7/avgA(prior7)-1:0;
  let growthStreak=0, declineStreak=0; for(let i=sortedDays.length-1;i>0;i--){if(sortedDays[i]>sortedDays[i-1]&&!declineStreak)growthStreak++;else if(sortedDays[i]<sortedDays[i-1]&&!growthStreak)declineStreak++;else break;}
  const hTotal=sumA(h), hRatio=(a,b)=>hTotal?sumA(h.slice(a,b))/hTotal:0;
  const nightRatio=(sumA(h.slice(0,6))+sumA(h.slice(22)))/(hTotal||1), morningRatio=hRatio(6,11), workRatio=hRatio(9,18), eveningRatio=hRatio(18,22);
  const activeHours=h.filter(v=>v>0), hourlySpan=activeHours.length, maxHour=Math.max(0,...h), avgActiveHour=avgA(activeHours);
  const modelTotals={}; days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>modelTotals[m]=(modelTotals[m]||0)+v));
  const modelVals=Object.values(modelTotals), topModelShare=total&&modelVals.length?Math.max(...modelVals)/total:0;
  const modelHHI=total?modelVals.reduce((a,v)=>a+(v/total)*(v/total),0):0;
  const denseLog=(lo,hi,n)=>Array.from({length:n},(_,i)=>Math.round(lo*Math.pow(hi/lo,i/Math.max(1,n-1))));
  const denseLinear=(lo,hi,n)=>Array.from({length:n},(_,i)=>lo+(hi-lo)*i/Math.max(1,n-1));
  const pushLadder=(name,e,value,thresholds,unit,formatter,pool=POOL_BIG,secret=false)=>cats.push({name,e,items:mk(e,value,[...new Set(thresholds)],unit,formatter,pool,secret)});

  const wd=[0,0,0,0,0,0,0], mo=[0,0,0,0,0,0,0,0,0,0,0,0];
  days.forEach(d=>{ const p=d.period.split('-'); const dt=new Date(Date.UTC(+p[0],+p[1]-1,+p[2])); wd[(dt.getUTCDay()+6)%7]+=d.total; mo[(+p[1]-1)]+=d.total; });
  const fmtT=v=>human(v);
  const tok=denseLog(1e3,1e14,72);
  const dayTok=denseLog(1e3,1e12,48);
  const streaks=[...Array.from({length:30},(_,i)=>i+1),...Array.from({length:35},(_,i)=>(i+7)*5),365,400,500,600,666,730,888,1000];
  const daysList=[...Array.from({length:30},(_,i)=>i+1),...Array.from({length:40},(_,i)=>(i+7)*5),250,300,365,500,666,730,888,1000,1500,2000];
  const hours=Array.from({length:24},(_,i)=>i+1);
  const modelsList=[...Array.from({length:20},(_,i)=>i+1),25,30,40,50,60,75,100,150,200];
  const cwdsList=[...Array.from({length:20},(_,i)=>i+1),25,30,40,50,75,100,150,200,300,500];
  const sessList=denseLog(1,10000,48);
  const callList=denseLog(10,1e8,52);
  const ratioList=[...Array.from({length:20},(_,i)=>(i+1)*.025),...Array.from({length:19},(_,i)=>.5+(i+1)*.025),.98,.99,.995,.999];
  const turnsList=denseLog(5,50000,42);
  const cacheAbs=denseLog(1e3,1e14,52);
  const avgList=denseLog(1e3,1e11,44);

  let cats=[];
  cats.push({name:'累计 token',e:'📈',items:mk('📈',total,tok,' tk',fmtT,POOL_BIG)});
  cats.push({name:'单日峰值',e:'📅',items:mk('📅',maxDay,dayTok,' /日',fmtT,POOL_BIG)});
  cats.push({name:'连续天数',e:'⚡',items:mk('⚡',streak,streaks,' 天',v=>v,POOL_STREAK)});
  cats.push({name:'累计活跃天',e:'🗓️',items:mk('🗓️',dayCount,daysList,' 天',v=>v,POOL_DAYS)});
  cats.push({name:'活跃小时数',e:'🕐',items:mk('🕐',hoursActive,hours,' 小时',v=>v,POOL_RATIO)});
  cats.push({name:'模型种类',e:'🎲',items:mk('🎲',models,modelsList,' 模型',v=>v,POOL_RATIO)});
  cats.push({name:'项目足迹',e:'📁',items:mk('📁',nCwds,cwdsList,' 项目',v=>v,POOL_DAYS)});
  cats.push({name:'会话数量',e:'💬',items:mk('💬',nSess,sessList,' 会话',v=>v,POOL_DAYS)});
  cats.push({name:'调用次数',e:'🔔',items:mk('🔔',calls,callList,' 次',fmtT,POOL_BIG)});
  cats.push({name:'缓存命中',e:'💎',items:mk('💎',cRatio,ratioList,'% 量',v=>(v*100).toFixed(0),POOL_RATIO)});
  cats.push({name:'缓存省量',e:'🧊',items:mk('🧊',cr,cacheAbs,' tk',fmtT,POOL_BIG)});
  cats.push({name:'单会话轮数',e:'🦠',items:mk('🦠',maxTurns,turnsList,' 轮',v=>v,POOL_STREAK)});
  cats.push({name:'日均 token',e:'⚖️',items:mk('⚖️',avgPerDay,avgList,' /日均',fmtT,POOL_BIG)});
  pushLadder('累计输入','📥',inputTotal,denseLog(1e3,1e14,54),' 输入',fmtT);
  pushLadder('累计输出','📤',outputTotal,denseLog(1e3,1e13,50),' 输出',fmtT);
  pushLadder('缓存写入','🧬',cacheWrite,denseLog(1e3,1e13,46),' 写缓存',fmtT);
  pushLadder('每次调用密度','🧱',tokensPerCall,denseLog(10,1e8,42),' tk/次',fmtT);
  pushLadder('每日调用密度','🔔',callsPerDay,denseLog(1,1e5,38),' 次/日',v=>Number(v).toFixed(v<10?1:0),POOL_STREAK);
  pushLadder('平均会话体量','💬',avgSession,denseLog(100,1e10,46),' tk/会话',fmtT);
  pushLadder('会话中位数','🪨',medSession,denseLog(100,1e10,42),' tk 中位',fmtT);
  pushLadder('最大会话','🐋',maxSession,denseLog(1e3,1e12,48),' tk/会话',fmtT);
  pushLadder('每日会话密度','🫧',sessionsPerDay,denseLog(.1,1e3,34),' 会话/日',v=>Number(v).toFixed(v<10?1:0),POOL_RATIO);
  pushLadder('平均项目体量','🏗️',avgProject,denseLog(1e3,1e12,42),' tk/项目',fmtT);
  pushLadder('最大项目','🏰',maxProject,denseLog(1e3,1e13,44),' tk/项目',fmtT);
  // 趋势、节奏与集中度阶梯
  pushLadder('夜猫指数','🌙',nightRatio,denseLinear(.025,1,40),' 夜间',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('晨光指数','🌅',morningRatio,denseLinear(.025,1,36),' 清晨',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('工时集中度','💼',workRatio,denseLinear(.025,1,36),' 日间',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('黄昏指数','🌆',eveningRatio,denseLinear(.025,1,34),' 晚间',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('波动指数','🌊',dailyCV,denseLinear(.05,3,36),' CV',v=>Number(v).toFixed(2),POOL_RATIO);
  pushLadder('增长连击','📶',growthStreak,Array.from({length:30},(_,i)=>i+1),' 天连涨',v=>v,POOL_STREAK);
  pushLadder('回落连击','📉',declineStreak,Array.from({length:30},(_,i)=>i+1),' 天连降',v=>v,POOL_STREAK);
  pushLadder('近期加速度','🚀',Math.max(0,momentum),denseLinear(.025,5,40),' 增速',v=>'+'+(v*100).toFixed(1)+'%',POOL_BIG);
  pushLadder('七日均值','7️⃣',avg7,denseLog(1e3,1e11,42),' /近7日',fmtT);
  pushLadder('三十日均值','🗓️',avg30,denseLog(1e3,1e11,42),' /近30日',fmtT);
  pushLadder('活跃小时跨度','🧭',hourlySpan,Array.from({length:24},(_,i)=>i+1),' 个时段',v=>v,POOL_DAYS);
  pushLadder('单小时峰值','⚡',maxHour,denseLog(100,1e11,44),' /小时',fmtT);
  pushLadder('活跃小时均值','⌛',avgActiveHour,denseLog(100,1e10,40),' /活跃小时',fmtT);
  pushLadder('主力模型占比','👑',topModelShare,denseLinear(.05,1,38),' 占比',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('模型专注指数','🎯',modelHHI,denseLinear(.05,1,38),' HHI',v=>Number(v).toFixed(2),POOL_RATIO);

  // 星期 × 小时：每一个星期时刻都是独立可收集坐标
  const wdHour=Array.from({length:7},()=>Array(24).fill(0));
  days.forEach(d=>{const x=DATA.day_details[d.period],p=d.period.split('-'),dt=new Date(Date.UTC(+p[0],+p[1]-1,+p[2])),w=(dt.getUTCDay()+6)%7;if(x)(x.hourly||[]).forEach((v,hour)=>wdHour[w][hour]+=v||0);});
  const wdHourItems=[]; const WHT=[1e2,1e3,1e4,1e5];
  WD.forEach((day,w)=>{for(let hour=0;hour<24;hour++)WHT.forEach((v,i)=>wdHourItems.push({e:['·','▪','◆','✦'][i],n:day+' '+String(hour).padStart(2,'0')+'点·'+['微光','点亮','炽热','恒星'][i],d:day+' '+String(hour).padStart(2,'0')+':00 累计 '+fmtT(v)+' tk',tier:tierFor(i,WHT.length),ok:wdHour[w][hour]>=v,secret:i>=3}));});
  cats.push({name:'星期时空坐标',e:'🧿',items:wdHourItems});

  // 月份 × 四时段
  const moBand=Array.from({length:12},()=>Array(4).fill(0)), bands=[[0,6,'深夜'],[6,12,'晨午'],[12,18,'午后'],[18,24,'晚间']];
  days.forEach(d=>{const x=DATA.day_details[d.period],mon=Number(d.period.slice(5,7))-1;if(x)bands.forEach(([a,b],bi)=>moBand[mon][bi]+=sumA((x.hourly||[]).slice(a,b)));});
  const moBandItems=[];for(let m=0;m<12;m++)bands.forEach((band,bi)=>[1e3,1e5,1e7,1e9].forEach((v,i)=>moBandItems.push({e:['🌑','🌓','🌕','☀️'][i],n:(m+1)+'月·'+band[2]+'·'+['初响','回声','盛放','传说'][i],d:(m+1)+'月 '+band[2]+'累计 '+fmtT(v)+' tk',tier:tierFor(i,4),ok:moBand[m][bi]>=v,secret:i===3})));
  cats.push({name:'月份四时',e:'🌗',items:moBandItems});

  // 模型 × 时段人格
  const modelBandItems=[];Object.entries(modelStats).forEach(([m,ms],mi)=>{const mh=Array(24).fill(0);Object.values(DATA.day_details||{}).forEach(x=>{const a=(x.hourly_models||{})[m]||[];a.forEach((v,i)=>mh[i]+=v||0);});bands.forEach(([a,b,nm],bi)=>{const v=sumA(mh.slice(a,b));[1e3,1e5,1e7].forEach((th,i)=>modelBandItems.push({e:'🤖',n:pretty(m)+'·'+nm+'·'+['邂逅','搭档','灵魂'][i],d:pretty(m)+' 在'+nm+'累计 '+fmtT(th)+' tk',tier:tierFor(i,3),ok:v>=th,secret:i===2}));});});
  cats.push({name:'模型时段羁绊',e:'🪢',items:modelBandItems});

  // 来源阶梯
  Object.entries(sourceTotals).forEach(([src,v])=>pushLadder('来源 · '+src,'📡',v,denseLog(1e3,1e13,36),' tk',fmtT,POOL_BIG));

  // 组合成就：总量、缓存、连续、模型、会话彼此交叉
  const combo=[];
  const totalBands=[1e5,1e6,1e7,1e8,1e9,1e10], cacheBands=[.1,.3,.5,.7,.9];
  totalBands.forEach((tv,ti)=>cacheBands.forEach((cv,ci)=>combo.push({e:'⚗️',n:'算力炼金·'+(ti+1)+'-'+(ci+1),d:'累计 '+fmtT(tv)+' 且缓存率 '+Math.round(cv*100)+'%',tier:tierFor(ti+ci,totalBands.length+cacheBands.length),ok:total>=tv&&cRatio>=cv,secret:ci>=3})));
  [3,7,14,30,60,100].forEach((sv,si)=>[1e5,1e6,1e7,1e8,1e9].forEach((tv,ti)=>combo.push({e:'🔥',n:'长燃引擎·'+sv+'×'+(ti+1),d:'连续 '+sv+' 天且累计 '+fmtT(tv),tier:tierFor(si+ti,10),ok:streak>=sv&&total>=tv,secret:si>=4})));
  [1,2,3,5,8,12].forEach((mv,mi)=>[10,50,100,500,1000].forEach((sv,si)=>combo.push({e:'🧩',n:'多元宇宙·'+mv+'×'+sv,d:'使用 '+mv+' 模型且拥有 '+sv+' 会话',tier:tierFor(mi+si,10),ok:models>=mv&&nSess>=sv,secret:mi>=4})));
  cats.push({name:'复合炼金术',e:'⚗️',items:combo});

  // 24 时刻 × 量级矩阵
  const hourItems=[]; const htok=[1e2,1e3,1e4,1e5,1e6];
  for(let hr=0;hr<24;hr++){ htok.forEach((v,i)=>{ const name=['夜巡','更夫','守夜','夜神','夜之王'][i]; hourItems.push({e:'🕒',n:String(hr).padStart(2,'0')+'点·'+name,d:String(hr).padStart(2,'0')+':00 烧 '+fmtT(v)+' tk',tier:tierFor(i,htok.length),ok:(h[hr]||0)>=v,secret:i>=3}); }); }
  cats.push({name:'时刻战士',e:'🕒',items:hourItems});
  // 星期矩阵
  const wdItems=[]; const wdt=[1e4,1e6,1e8,1e10]; WD.forEach((nm,w)=> wdt.forEach((v,i)=> wdItems.push({e:'▮',n:nm+['·学徒','·常客','·狂魔','·化身'][i],d:nm+'累计 '+fmtT(v)+' tk',tier:tierFor(i,wdt.length),ok:wd[w]>=v})) );
  cats.push({name:'星期人格',e:'📆',items:wdItems});
  // 月份矩阵
  const moItems=[]; const mot=[1e5,1e7,1e9]; for(let m=0;m<12;m++) mot.forEach((v,i)=> moItems.push({e:'🌙',n:(m+1)+'月'+['·起势','·丰收','·封神'][i],d:(m+1)+'月累计 '+fmtT(v)+' tk',tier:tierFor(i,mot.length),ok:mo[m]>=v}));
  cats.push({name:'月份里程碑',e:'🌙',items:moItems});
  // 每个用过模型一枚
  const modelItems=(DATA.models||[]).map((m,i)=>{const tot=days.reduce((a,d)=>a+((d.models[m])||0),0);return {e:'🤖',n:pretty(m)+'用户',d:'用过 '+pretty(m),tier:tierFor(i,Math.max(1,DATA.models.length)),ok:tot>0};});
  cats.push({name:'模型图鉴',e:'🤖',items:modelItems});

  // ---- 奇思妙想 / 隐藏彩蛋 ----
  const SE=[];
  const has=v=>total>=v;
  // 数字彩蛋
  const eggs=[
    [42,'宇宙答案'],[64,'六十四位'],[128,'半字节军团'],[256,'像素方阵'],[404,'成就未找到'],[418,'我是茶壶'],[451,'不可用'],[500,'服务器冒烟'],[520,'我爱你'],[666,'恶魔契约'],[777,'幸运七'],[888,'发发发'],[999,'长长久久'],[1024,'一千零二十四'],[1314,'一生一世'],[1337,'Leet'],[2048,'合成玩家'],[4096,'页大小'],[5200,'我爱你加长版'],[7777,'老虎机'],[8192,'八千字节'],[9000,'Over 9000'],[10000,'万事开头'],[16384,'十六K'],[23333,'笑出声'],[32768,'有符号边界'],[65535,'端口之王'],[65536,'无符号飞升'],[66666,'六六大顺'],[88888,'暴富预兆'],[99999,'九九归一'],[111111,'全一教'],[123456,'顺子'],[161803,'黄金比'],[271828,'自然底'],[314159,'圆周率'],[524288,'半兆'],[654321,'倒顺子'],[666666,'六道轮回'],[777777,'七星连珠'],[888888,'一路发'],[999999,'无限逼近'],[1048576,'一兆门槛'],[1234567,'连续升级'],[16777216,'真彩色'],[5201314,'真爱粉'],[10000000,'千万俱乐部'],[16777215,'RGB 白'],[33554432,'三十二兆'],[100000000,'亿万先生'],[1073741824,'一吉字节'],[2147483647,'整数之巅'],[4294967295,'无符号边界']
  ];
  eggs.forEach(([v,nm])=>SE.push({e:'🎰',n:nm,d:'token 含 / 达到 '+fmtT(v),tier:'gold',ok:has(v)||String(total).includes(String(v)),secret:true}));
  // 单日数字蛋
  [[666666,'单日六六六'],[888888,'单日发发发'],[50000000,'单日五千万'],[100000000,'单日破亿']].forEach(([v,nm])=>SE.push({e:'🥚',n:nm,d:'单日达到 '+fmtT(v),tier:'gold',ok:maxDay>=v,secret:true}));
  // 时段人格（按峰值）
  const persona=[['🌅','破晓行者',5,8],['☕','早C战士',8,11],['🍱','午间摸鱼',11,14],['🍵','下午茶王',14,18],['🌆','黄昏斗士',18,21],['🌙','夜行者',21,24],['🦉','修仙党',0,5]];
  persona.forEach(([e,nm,a,b])=>SE.push({e,n:nm,d:'峰值在 '+a+'-'+b+' 点',tier:'silver',ok:peak>=a&&peak<b}));
  SE.push({e:'🕛',n:'子夜战神',d:'峰值恰在 0 点',tier:'gold',ok:peak===0,secret:true});
  SE.push({e:'🐓',n:'晨型人',d:'峰值在 6 点',tier:'silver',ok:peak===6,secret:true});
  // 星期人格
  WD_PERSONA.forEach((nm,w)=>SE.push({e:'📆',n:nm,d:'用量最高的是 '+WD[w],tier:'silver',ok: wd[w]===Math.max(...wd)&&Math.max(...wd)>0,secret:w<5}));
  // 周末战士
  const wkend=wd[5]+wd[6], wkdayAvg=(wd[0]+wd[1]+wd[2]+wd[3]+wd[4])/(5||1);
  SE.push({e:'🏄',n:'周末战士',d:'周末日均 > 工作日',tier:'gold',ok:wkend/2>wkdayAvg,secret:true});
  SE.push({e:'💼',n:'打工人',d:'工作日 > 周末',tier:'silver',ok:wkdayAvg>wkend/2,secret:true});
  // 全天候 / 极端
  SE.push({e:'🌍',n:'全天候',d:'24 小时都有用量',tier:'gold',ok:hoursActive>=24});
  SE.push({e:'🎯',n:'专一',d:'只用 1 个模型',tier:'bronze',ok:models===1});
  SE.push({e:'🌈',n:'万花筒',d:'用过 ≥5 模型',tier:'gold',ok:models>=5});
  SE.push({e:'🦠',n:'话痨',d:'单会话 ≥500 轮',tier:'gold',ok:maxTurns>=500,secret:true});
  SE.push({e:'🗂️',n:'多面手',d:'≥5 个项目',tier:'silver',ok:nCwds>=5});
  SE.push({e:'🐢',n:'龟速',d:'日均 <1 万',tier:'bronze',ok:avgPerDay<1e4&&dayCount>5,secret:true});
  SE.push({e:'🚀',n:'爆发',d:'单日占总量 ≥40%',tier:'gold',ok:maxDay>=total*0.4&&total>0,secret:true});
  // 编程梗（接真实条件）
  const TR=[
    ['👋','Hello World', total>=1e4],['🐛','捉虫能手', calls>=1000],['🧹','洁癖', cRatio>=0.9],['💀','rm -rf 幸存者', total>=1e8],
    ['🌀','无限循环', streak>=30],['📦','囤积狂', nCwds>=30],['🤡','摸鱼王', streak<3 && dayCount>10],['🎲','随机种子', models>=4],
    ['🧊','冷启动', cRatio<0.1 && total>1e5],['🔥','热加载', cRatio>=0.99],['🪦','坟墓', nSess>=100],['⚙️','CRUD 战神', calls>=1e4],
    ['🧪','实验狂', nCwds>=10],['🪄','魔法师', maxTurns>=1000],['🦆','鸭子调试', peak>=0&&peak<4],['🎈','内存泄漏', nSess>=500],
    ['🧭','导航员', nCwds>=20],['🍄','蘑菇', peak>=0&&peak<4],['🛷','滑坡', streak<dayCount-5 && dayCount>20],['🎨','调色板', models>=6],
    ['🧩','拼图', nCwds>=15],['🔭','观星者', hoursActive>=20],['🦾','钢铁肝', total>=5e7],['🧠','脑力劳动者', calls>=5000],
    ['🍔','外卖续命', peak>=22||peak<2],['💤','失眠', hoursActive>=22],['🪞','照镜子', models===1],['🎵','单曲循环', models===1 && total>1e6],
    ['🧶','乱麻', nCwds>=40],['🏹','神射手', cRatio>=0.85],
    ['🌃','赛博夜行人',nightRatio>=.5],['🌄','朝九之前',morningRatio>=.5],['🏢','标准工时',workRatio>=.65],['🌆','下班才上班',eveningRatio>=.5],
    ['🎢','过山车',dailyCV>=1.5],['🧘','稳定发挥',dailyCV<=.15&&dayCount>=7],['📈','牛市',growthStreak>=7],['📉','熊市',declineStreak>=7],
    ['🚄','高速迭代',momentum>=1],['🪶','轻量会话',avgSession>0&&avgSession<1e4],['🐘','重量级会话',avgSession>=1e7],['🐋','利维坦会话',maxSession>=1e9],
    ['🏙️','项目都市',nCwds>=100],['🌌','项目星系',nCwds>=500],['💬','群聊现场',sessionsPerDay>=20],['🔕','静默少言',sessionsPerDay<1&&dayCount>=7],
    ['🥇','一枝独秀',topModelShare>=.9],['🤹','左右开弓',models>=2&&topModelShare<.65],['🌈','模型联合国',models>=8],['🎯','极致专注',modelHHI>=.95],
    ['🫧','均匀分布',modelHHI<=.3&&models>=4],['📥','海纳百川',inputTotal>=1e9],['📤','滔滔不绝',outputTotal>=1e8],['🧬','缓存播种者',cacheWrite>=1e8],
    ['🧱','上下文长城',tokensPerCall>=1e6],['⚡','闪电问答',tokensPerCall<1e3&&calls>=100],['🧺','批处理大师',callsPerDay>=1000],['🕰️','长线主义',dayCount>=365],
    ['🪄','Prompt 巫师',outputTotal>inputTotal],['📚','上下文图书馆',inputTotal>=outputTotal*20&&outputTotal>0],['♻️','循环利用',cr>inputTotal],['🧯','缓存灭火器',cRatio>=.95&&total>=1e7],
    ['🧑‍🚀','全栈宇航员',nCwds>=20&&models>=5&&hoursActive>=18],['🧑‍💻','真正的程序员',nightRatio>=.4&&calls>=10000],['☕','咖啡编译器',h[9]>0&&h[14]>0&&h[21]>0],['🍜','泡面时区',h[0]+h[1]+h[2]>=hTotal*.25],
    ['🧿','零点观测站',h[0]>=maxHour*.8&&maxHour>0],['🐓','早起提交',h[6]>=maxHour*.8&&maxHour>0],['🥪','午休提交',h[12]+h[13]>=hTotal*.2],['🌇','晚高峰提交',h[18]+h[19]>=hTotal*.25],
    ['📆','周一启动器',wd[0]===Math.max(...wd)],['🎉','周五释放',wd[4]===Math.max(...wd)],['🏖️','双休日构建',wd[5]+wd[6]>(sumA(wd.slice(0,5))/5)*2],['🛠️','工作日机器',sumA(wd.slice(0,5))>=sumA(wd.slice(5))*4],
    ['🔬','微服务人格',avgProject<1e6&&nCwds>=10],['🗿','单体巨石',maxProject>=total*.8&&nCwds>0],['🪐','多项目轨道',nCwds>=50&&maxProject<total*.3],['🧳','项目旅行家',nCwds>=dayCount&&dayCount>10],
    ['🎛️','参数调优师',models>=3&&cRatio>=.7],['🔋','满电运行',streak>=100&&hoursActive>=18],['🕳️','Token 黑洞',maxDay>=1e9],['🌋','单日喷发',maxDay>=avgPerDay*8&&dayCount>=7],
    ['🧊','绝对零度',total===0],['🌱','第一粒 Token',total>0],['🛤️','万里长征',dayCount>=1000],['🏛️','数字文明',total>=1e12]
  ];
  TR.forEach(([e,nm,ok])=>SE.push({e,n:nm,d:nm,tier:'silver',ok,secret:true}));
  // 星座/生肖（按生成日期，必解锁其一）
  const ZODIAC=[['♈','白羊'],['♉','金牛'],['♊','双子'],['♋','巨蟹'],['♌','狮子'],['♍','处女'],['♎','天秤'],['♏','天蝎'],['♐','射手'],['♑','摩羯'],['♒','水瓶'],['♓','双鱼']];
  const gd=new Date(), gm=gd.getMonth()+1, gday=gd.getDate();
  const zidx=(gm===12&&gday>=22)||gm<=1&&gday<20?9:gm<=2?10:gm<=3?11:gm<=4?0:gm<=5?1:gm<=6?2:gm<=7?3:gm<=8?4:gm<=9?5:gm<=10?6:gm<=11?7:8;
  ZODIAC.forEach((z,i)=>SE.push({e:z[0],n:'星座·'+z[1],d:'今日星座 '+z[1],tier:'bronze',ok:i===zidx}));
  const SX=['🐀鼠','🐂牛','🐅虎','🐇兔','🐉龙','🐍蛇','🐎马','🐐羊','🐒猴','🐓鸡','🐕狗','🐖猪'];
  const sxIdx=(gd.getFullYear()-4)%12;
  SX.forEach((s,i)=>SE.push({e:'🔮',n:'生肖·'+s,d:'今年生肖 '+s,tier:'bronze',ok:i===sxIdx}));
  // 节日（按 mm-dd）
  const fest=[['01-01','元旦'],['02-14','情人节'],['03-08','妇女节'],['03-14','圆周率日'],['04-01','愚人节'],['04-22','地球日'],['05-01','劳动节'],['05-04','青年节'],['05-17','电信日'],['06-01','儿童节'],['07-01','建党节'],['07-17','世界 Emoji 日'],['08-15','抗战胜利'],['09-10','教师节'],['09-13','程序员节'],['10-01','国庆'],['10-24','程序员节 1024'],['10-31','万圣节'],['11-11','双十一'],['12-24','平安夜'],['12-25','圣诞节']];
  const today=String(gm).padStart(2,'0')+'-'+String(gday).padStart(2,'0');
  fest.forEach(([d,nm])=>SE.push({e:'🎉',n:'节日·'+nm,d:'在 '+nm+' 跑了统计',tier:'silver',ok:d===today,secret:true}));
  const solar=['小寒','大寒','立春','雨水','惊蛰','春分','清明','谷雨','立夏','小满','芒种','夏至','小暑','大暑','立秋','处暑','白露','秋分','寒露','霜降','立冬','小雪','大雪','冬至'];
  solar.forEach((nm,i)=>{const target=Math.round(i*365/24),now=Math.floor((gd-new Date(gd.getFullYear(),0,1))/86400000);SE.push({e:'🌿',n:'节气·'+nm,d:'在'+nm+'附近生成报告',tier:i%6===0?'gold':'bronze',ok:Math.abs(now-target)<=2,secret:true});});
  const dateEggs=[['镜像日期',today.split('-').join('')===today.split('-').join('').split('').reverse().join('')],['双数之日',/[02468]{4}/.test(today.replace('-',''))],['幸运七日',today.includes('07')],['六六之日',today.includes('06')],['八八之日',today.includes('08')],['连续日期',/123|234|345|456|567|678|789/.test(today.replace('-',''))],['月日相同',gm===gday],['月末守望',gday===new Date(gd.getFullYear(),gm,0).getDate()]];
  dateEggs.forEach(([nm,ok])=>SE.push({e:'📟',n:nm,d:'生成日期触发：'+nm,tier:'silver',ok,secret:true}));
  cats.push({name:'奇思妙想 · 隐藏',e:'✨',items:SE});

  const ALL=[].concat(...cats.map(c=>c.items));
  const got=ALL.filter(b=>b.ok).length;
  return {cats, all:ALL, got, pct: ALL.length? got/ALL.length:0};
}
function badgeCell(b){
  const masked=b.secret&&!b.ok;
  const cls='badge '+(b.ok?('on tier-'+b.tier):'off')+(b.secret?' secret':'');
  return '<div class="'+cls+'" title="'+(masked?'隐藏成就，达成自动揭晓':esc(b.d))+'">'
    +'<div class=ring>'+(masked?'❓':(b.ok?b.e:'🔒'))+'</div>'
    +'<div class=nm>'+(masked?'???':esc(b.n))+'</div>'
    +'<div class=dc>'+(masked?'隐藏':esc(b.d))+'</div></div>';
}
let _ach=null, _stripT=null;
function renderBadges(){
  _ach=getBadgeData(); const a=_ach;
  document.getElementById('ach-meta').innerHTML='已解锁 <b>'+a.got+'</b> / '+a.all.length;
  document.getElementById('ach-meta2').innerHTML='收集进度 <b>'+a.got+'</b> / '+a.all.length+' 枚';
  const C=2*Math.PI*42, arc=document.getElementById('ach-arc');
  arc.style.strokeDasharray=C.toFixed(1);
  arc.style.strokeDashoffset=C.toFixed(1);
  setTimeout(()=>{ arc.style.strokeDashoffset=(C*(1-a.pct)).toFixed(1); document.getElementById('ach-pct').textContent=Math.round(a.pct*100)+'%'; }, 60);
  document.getElementById('ach-pct').textContent=Math.round(a.pct*100)+'%';
  if(_stripT) clearInterval(_stripT);
  const roll=()=>{ const src=a.all.filter(b=>b.ok); const pool=src.length?src:a.all; const pick=[];
    for(let i=0;i<6;i++) pick.push(pool[Math.floor(Math.random()*pool.length)]);
    document.getElementById('ach-strip').innerHTML=pick.map(badgeCell).join('');
  };
  roll(); _stripT=setInterval(roll,3500);
  // 等级分布条 + 最高等级
  const TCOL={bronze:'#c08457',silver:'#b8c0cc',gold:'#f0b429',prismatic:'linear-gradient(90deg,#5b8def,#a78bfa,#f472b6,#14b8a6)'};
  const TLB={bronze:'青铜',silver:'白银',gold:'黄金',prismatic:'彩钻'};
  const TORD=['prismatic','gold','silver','bronze'];
  const trows=TORD.map(t=>{ const bs=a.all.filter(b=>b.tier===t); const g=bs.filter(b=>b.ok).length; return {t,g,n:bs.length,pct:bs.length?g/bs.length:0}; });
  document.getElementById('ach-tiers').innerHTML=trows.map(r=>{
    const bg=TCOL[r.t];
    return '<div class=trow><span class=tl><i style="background:'+(r.t==='prismatic'?'#a78bfa':bg)+'"></i>'+TLB[r.t]+'</span>'
      +'<span class=tbar><j style="width:'+(r.pct*100).toFixed(1)+'%;background:'+bg+'"></j></span>'
      +'<span class=tv>'+r.g+'/'+r.n+'</span></div>';
  }).join('');
  const top=TORD.find(t=>trows.find(r=>r.t===t&&r.g>0))||'bronze';
  const tr=trows.find(r=>r.t===top);
  document.getElementById('ach-ringlab').innerHTML='最高 <b>'+TLB[top]+'</b><br>'+tr.g+' 枚已集齐';
}
function achievementCategory(c,items,open){
  const g=items.filter(b=>b.ok).length, collapsed=open?'':' collapsed';
  return '<div class="cat'+collapsed+'" data-ach-cat="'+esc(c.name)+'"><div class=cat-h><span class=ce>'+c.e+'</span><span>'+c.name+'</span><span class=cc><b>'+g+'</b> / '+items.length+'</span><span class=chev>▼</span></div><div class=cat-grid>'+(open?items.map(badgeCell).join(''):'')+'</div></div>';
}
function renderAchievements(q){
  if(!_ach) _ach=getBadgeData(); const a=_ach; q=(q||'').trim().toLowerCase();
  const filter=document.getElementById('ach-filter').value;
  const okFilter=b=>filter==='all'||(filter==='on'&&b.ok)||(filter==='off'&&!b.ok)||(filter==='secret'&&b.secret)||b.tier===filter;
  document.getElementById('ach-modal-meta').innerHTML='已解锁 <b>'+a.got+'</b> / '+a.all.length+' · '+Math.round(a.pct*100)+'%';
  let shown=0, visibleCats=0; const forceOpen=!!q||filter!=='all';
  const body=a.cats.map(c=>{
    let items=c.items.filter(okFilter);
    if(q) items=items.filter(b=>(c.name+' '+b.n+' '+b.d).toLowerCase().includes(q));
    if(!items.length) return '';
    shown+=items.length; visibleCats++;
    return achievementCategory(c,items,forceOpen);
  }).join('');
  document.getElementById('ach-body').innerHTML='<div class=ach-stats><span>当前显示 <b>'+shown+'</b> 枚</span><span><b>'+visibleCats+'</b> 个分类</span><span>总图鉴 <b>'+a.all.length+'</b> 枚</span><span>展开分类时按需渲染</span></div>'+body;
  document.querySelectorAll('#ach-body .cat-h').forEach(h=>h.addEventListener('click',()=>{
    const cat=h.parentElement, grid=cat.querySelector('.cat-grid');
    if(cat.classList.contains('collapsed')){
      const c=a.cats.find(x=>x.name===cat.dataset.achCat); if(!c)return;
      let items=c.items.filter(okFilter);if(q)items=items.filter(b=>(c.name+' '+b.n+' '+b.d).toLowerCase().includes(q));
      if(!grid.childElementCount)grid.innerHTML=items.map(badgeCell).join('');cat.classList.remove('collapsed');
    }else cat.classList.add('collapsed');
  }));
}
document.getElementById('ach-open').addEventListener('click',()=>{ renderAchievements(document.getElementById('ach-search').value); document.getElementById('ach-modal').classList.add('open'); });
document.getElementById('ach-x').addEventListener('click',()=>document.getElementById('ach-modal').classList.remove('open'));
document.getElementById('ach-modal').addEventListener('click',e=>{ if(e.target.id==='ach-modal') e.currentTarget.classList.remove('open'); });
document.getElementById('ach-search').addEventListener('input',e=>renderAchievements(e.target.value));
document.getElementById('ach-filter').addEventListener('change',()=>renderAchievements(document.getElementById('ach-search').value));
document.getElementById('ach-confetti').addEventListener('click',()=>{ confetti(); toast('🎉 庆祝 '+Math.round((_ach?_ach.pct:0)*100)+'% 进度'); });

/* ---- Token 星云：数据生成的彩色深空 ---- */
function renderDNA(){
  const svg=document.getElementById('dna'), h=filteredHourly(), days=selectedRows(), total=days.reduce((a,d)=>a+d.total,0), cr=focusDetail()?.cache_read??(DATA.cache_read||0), cache=total?cr/total:0;
  const mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const models=Object.entries(mt).sort((a,b)=>b[1]-a[1]),ht=h.reduce((a,b)=>a+b,0),hmax=Math.max(1,...h),cx=150,cy=150;
  let p=['<defs><radialGradient id="ng" cx="50%" cy="50%"><stop offset="0" stop-color="#ffffff"/><stop offset=".18" stop-color="#d8e7ff"/><stop offset=".52" stop-color="#8daeff" stop-opacity=".9"/><stop offset="1" stop-color="#5b8def" stop-opacity="0"/></radialGradient><filter id="nb"><feGaussianBlur stdDeviation="5"/></filter><filter id="nbl"><feGaussianBlur stdDeviation="11"/></filter></defs>'];
  // 背景恒星：确定性分布，避免每次渲染跳动
  for(let i=0;i<72;i++){const seed=(i*7919+(total%104729))%100003,a=seed*.017,r=35+(seed%110),x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.86,rr=.35+(seed%7)/10;p.push('<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+rr.toFixed(1)+'" fill="#dbe9ff" opacity="'+(.18+(seed%5)*.1)+'"/>');}
  // 每个模型形成一条独立旋臂，模型颜色清晰可辨
  const arms=models.length?models:[[null,total]];
  arms.slice(0,8).forEach(([m,mv],mi)=>{
    const color=m?DATA.colors[m]:'#7aa2f7',frac=total?mv/total:1,count=Math.max(18,Math.round(24+frac*74)),phase=mi/Math.max(1,arms.length)*Math.PI*2+(total%97)/31;
    let haze='';for(let j=0;j<count;j++){const t=(j+1)/count,a=phase+t*Math.PI*(3.2+arms.length*.12),hour=Math.floor(t*24)%24,energy=(h[hour]||0)/hmax,rad=18+t*112+(energy-.5)*16,wob=Math.sin(j*1.73+mi)*9*(1-t*.45),x=cx+Math.cos(a)*rad+Math.cos(a+Math.PI/2)*wob,y=cy+Math.sin(a)*rad*.72+Math.sin(a+Math.PI/2)*wob*.72,rr=1.1+energy*2.9+(j%9===0?1.5:0),op=.25+energy*.58;haze+='<circle class="nebula-particle" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+rr.toFixed(1)+'" fill="'+color+'" opacity="'+op.toFixed(2)+'"><title>'+esc(m?pretty(m):'Token')+' · '+String(hour).padStart(2,'0')+':00 · '+human(h[hour]||0)+' tk</title></circle>';if(j%4===0)haze+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+(rr*3.4).toFixed(1)+'" fill="'+color+'" opacity="'+(.035+energy*.055).toFixed(3)+'" filter="url(#nb)"/>';}
    p.push('<g class="nebula-arm" style="animation-delay:-'+(mi*11)+'s">'+haze+'</g>');
  });
  // 24 个小时轨道信标
  for(let hour=0;hour<24;hour++){const v=h[hour]||0,energy=v/hmax,a=hour/24*Math.PI*2-Math.PI/2,r=126+energy*13,x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.72;if(v>0)p.push('<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+(1.4+energy*3).toFixed(1)+'" fill="#fff" opacity="'+(.28+energy*.7).toFixed(2)+'"><title>'+String(hour).padStart(2,'0')+':00 · '+fmt(v)+' Token</title></circle>');}
  // 缓存率越高，中央星核越明亮并出现更多光环
  p.push('<circle cx="150" cy="150" r="'+(24+cache*19).toFixed(1)+'" fill="url(#ng)" opacity=".32" filter="url(#nbl)"/><g class="nebula-core"><circle cx="150" cy="150" r="'+(10+cache*6).toFixed(1)+'" fill="url(#ng)"/><circle cx="150" cy="150" r="3.2" fill="#fff"/></g>');
  if(models.length){const dom=models[0];p.push('<text x="150" y="282" text-anchor="middle" fill="#91a6c8" font-size="8.5" letter-spacing="1.5">DOMINANT · '+esc(pretty(dom[0]).toUpperCase())+'</text>');}
  svg.innerHTML=p.join('');
  let peak=0;for(let i=1;i<24;i++)if((h[i]||0)>(h[peak]||0))peak=i;
  document.getElementById('nebula-meta').innerHTML='<div><b>'+models.length+' 个星团</b>模型光谱</div><div><b>'+String(peak).padStart(2,'0')+':00</b>最亮轨道</div><div><b>'+Math.round(cache*100)+'%</b>星核亮度</div>';
}
document.getElementById('dna-dl').addEventListener('click',()=>{
  const svg=document.getElementById('dna').cloneNode(true); svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
  svg.setAttribute('style','background:#0b1120');
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob(['<?xml version="1.0"?>\n'+svg.outerHTML],{type:'image/svg+xml'})); a.download='token-nebula.svg'; a.click(); toast('Token 星云已收藏为 SVG');
});

/* ---- 会话时间轴回放 ---- */
let rp={series:[],i:0,timer:null,returnFocus:null};
function openReplay(sid,label){
  const s=DATA.session_series[sid]||[];
  if(!s.length){ toast('该会话无逐轮数据'); return; }
  rp.series=s; rp.i=0;rp.returnFocus=document.activeElement;
  document.getElementById('replay-title').textContent=label||'会话回放';
  document.getElementById('replay-sub').textContent=s.length+' 轮'+(s.length>=200?'（最近 200 轮）':'')+' · 共 '+human(s.reduce((a,b)=>a+b,0))+' token · 横轴为轮次，不代表真实耗时';
  const modal=document.getElementById('replay-modal');modal.classList.add('open');modal.setAttribute('aria-hidden','false');
  const scrub=document.getElementById('replay-scrub');scrub.max=String(s.length-1);scrub.value='0';
  drawECG(0);document.getElementById('replay-x').focus();
}
function closeReplay(){ if(rp.timer){clearInterval(rp.timer);rp.timer=null;} document.getElementById('replay-play').textContent='▶ 播放';const modal=document.getElementById('replay-modal');modal.classList.remove('open');modal.setAttribute('aria-hidden','true');if(rp.returnFocus&&document.contains(rp.returnFocus))rp.returnFocus.focus(); }
function trapReplayFocus(e){if(e.key!=='Tab')return;const modal=document.getElementById('replay-modal');if(!modal.classList.contains('open'))return;const items=[...modal.querySelectorAll('button,input,[tabindex]:not([tabindex="-1"])')].filter(x=>!x.disabled),first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
function drawECG(index){
  const s=rp.series, W=700,H=160, max=Math.max(1,...s), n=s.length;
  let line=''; s.forEach((v,i)=>{ const x=i/Math.max(1,n-1)*W, y=H-6-(v/max)*(H-12); line+=(i?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)+' '; });
  const cur=Math.max(0,Math.min(n-1,Math.round(index))),cx=cur/Math.max(1,n-1)*W,cy=H-6-(s[cur]||0)/max*(H-12),total=s.reduce((a,b)=>a+b,0),cum=s.slice(0,cur+1).reduce((a,b)=>a+b,0);rp.i=cur;
  document.getElementById('replay-ecg').innerHTML='<path d="'+line+'L '+W+' '+H+' L 0 '+H+' Z" fill=var(--accent-soft)/><path d="'+line+'" fill=none stroke=var(--accent-2) stroke-width=1.5/>'
    +'<line x1="'+cx.toFixed(1)+'" y1=0 x2="'+cx.toFixed(1)+'" y2='+H+' stroke=var(--accent)/><circle cx="'+cx.toFixed(1)+'" cy="'+cy.toFixed(1)+'" r=3.5 fill=var(--accent)/>';
  document.getElementById('replay-pos').textContent=(cur+1)+'/'+n;
  const scrub=document.getElementById('replay-scrub');scrub.value=String(cur);scrub.setAttribute('aria-valuetext','第 '+(cur+1)+' 轮，'+fmt(s[cur]||0)+' Token，累计 '+(total?cum/total*100:0).toFixed(1)+'%');
  document.getElementById('replay-stats').innerHTML='<span>当前轮 '+fmt(s[cur]||0)+' tk</span><span>累计 '+fmt(cum)+' tk</span><span>累计占比 '+(total?cum/total*100:0).toFixed(1)+'%</span>';
}
document.getElementById('replay-x').addEventListener('click',closeReplay);
document.getElementById('replay-modal').addEventListener('keydown',trapReplayFocus);
document.getElementById('replay-modal').addEventListener('click',e=>{ if(e.target.id==='replay-modal') closeReplay(); });
function stopReplay(){if(rp.timer){clearInterval(rp.timer);rp.timer=null;document.getElementById('replay-play').textContent='▶ 播放';}}
document.getElementById('replay-scrub').addEventListener('input',e=>{stopReplay();drawECG(Number(e.target.value||0));});
document.getElementById('replay-ecg').addEventListener('pointerdown',e=>{stopReplay();const r=e.currentTarget.getBoundingClientRect(),index=(e.clientX-r.left)/Math.max(1,r.width)*Math.max(0,rp.series.length-1);drawECG(index);});
document.getElementById('replay-play').addEventListener('click',function(){
  if(rp.timer){ clearInterval(rp.timer); rp.timer=null; this.textContent='▶ 播放'; return; }
  if(rp.series.length<2) return; let index=rp.i;if(index>=rp.series.length-1)index=-1;this.textContent='⏸ 暂停';
  rp.timer=setInterval(()=>{ index++; if(index>=rp.series.length-1){index=rp.series.length-1;clearInterval(rp.timer);rp.timer=null;this.textContent='▶ 播放';}drawECG(index); },120);
});

/* ---- 今日 token 运势 ---- */
function daySeed(){ const d=new Date(); return d.getFullYear()*10000+(d.getMonth()+1)*100+d.getDate(); }
function uhash(n){ n=Math.imul(n^(n>>>15),0x27d4eb2d); n=n^(n>>>13); return (n>>>0)/4294967296; }
function renderFortune(){
  const seed=daySeed(), r=k=>uhash(seed*(k+7));
  const yi=['宜重构','宜写测试','宜删废代码','宜提交','宜读文档','宜改名','宜早睡','宜喝口水','宜拆函数','宜加注释'];
  const ji=['忌 rm -rf','忌深夜上线','忌动数据库','忌裸奔 main','忌盲信 AI','忌硬编码','忌跳过测试','忌复制粘贴','忌不留缓存'];
  const poem=['token 如流水，缓存尚可留。','一日肝到夜，bug 自然来。','代码千行，缓存一响，黄金万两。','commit 之前，三思而后行。','算力烧不尽，春风吹又生。','多喝热水，少写 any。','重构像减肥，明天再说。'];
  const total=lastTotal||0, cr=DATA.cache_read||0, cRatio=total?cr/total:0;
  const score=Math.max(12,Math.min(99,Math.round(45+cRatio*40+r(3)*20-10)));
  const grade=score>=88?'大吉':score>=72?'中吉':score>=58?'吉':score>=44?'末吉':'凶';
  const pick=(arr,k)=>arr[Math.floor(r(k)*arr.length)];
  document.getElementById('f-date').textContent=new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'});
  document.getElementById('fortune').innerHTML=
    '<div class=f-head><div class=f-grade>'+grade+'</div><div class=f-score>运势 <b style="color:var(--ink);font-size:16px">'+score+'</b> / 100</div></div>'
    +'<div class=f-bar><i style="width:'+score+'%"></i></div>'
    +'<div class=f-yj><span class=f-yi><b>宜</b>'+pick(yi,1)+'</span><span class=f-ji><b>忌</b>'+pick(ji,2)+'</span></div>'
    +'<div class=f-poem>'+pick(poem,4)+'</div>';
}

/* ---- 3D 鼠标倾斜卡（全局 parallax tilt）---- */
(function(){
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  let raf=0,mx=0,my=0;
  document.addEventListener('mousemove',e=>{ mx=e.clientX; my=e.clientY; if(!raf) raf=requestAnimationFrame(tick); },{passive:true});
  function tick(){
    raf=0;
    document.querySelectorAll('.card').forEach(c=>{
      const r=c.getBoundingClientRect();
      const near=my>r.top-300&&my<r.bottom+300&&mx>r.left-300&&mx<r.right+300;
      if(!near){ if(c.style.transform) c.style.transform=''; return; }
      const dx=(mx-(r.left+r.width/2))/(r.width/2), dy=(my-(r.top+r.height/2))/(r.height/2);
      c.style.transform='rotateX('+Math.max(-1.6,Math.min(1.6,-dy*1.6)).toFixed(2)+'deg) rotateY('+Math.max(-1.6,Math.min(1.6,dx*1.6)).toFixed(2)+'deg)';
    });
  }
})();

// 双击页面空白：模型色数据尘埃
(function(){
  document.addEventListener('dblclick',e=>{
    if(e.target.closest('button,input,label,a,.card,svg'))return;
    const cs=Object.values(DATA.colors||{});for(let i=0;i<38;i++){const d=document.createElement('i');d.style.cssText='position:fixed;z-index:110;pointer-events:none;left:'+e.clientX+'px;top:'+e.clientY+'px;width:'+(3+i%4)+'px;height:'+(3+i%4)+'px;border-radius:50%;background:'+(cs[i%Math.max(1,cs.length)]||'#7aa2f7')+';transition:transform .85s cubic-bezier(.15,.7,.2,1),opacity .85s';document.body.appendChild(d);requestAnimationFrame(()=>{const a=i/38*Math.PI*2,r=40+(i%9)*9;d.style.transform='translate('+Math.cos(a)*r+'px,'+Math.sin(a)*r+'px) scale(.2)';d.style.opacity='0';});setTimeout(()=>d.remove(),900);}
  });
})();

// 光标彗星：每颗粒子继承真实模型配色
(function(){
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  let last=0,i=0;const colors=Object.values(DATA.colors||{});
  document.addEventListener('mousemove',e=>{const now=performance.now();if(now-last<42)return;last=now;const d=document.createElement('i'),sz=3+(i%4),c=colors.length?colors[i++%colors.length]:'#7aa2f7';d.className='comet';d.style.left=(e.clientX-sz/2)+'px';d.style.top=(e.clientY-sz/2)+'px';d.style.width=sz+'px';d.style.height=sz+'px';d.style.background=c;d.style.boxShadow='0 0 '+(sz*3)+'px '+c;d.style.setProperty('--dx',(-8+(i%5)*4)+'px');d.style.setProperty('--dy',(12+(i%7)*3)+'px');document.body.appendChild(d);setTimeout(()=>d.remove(),760);},{passive:true});
})();
// 滚到深处出现返航火箭
(function(){const r=document.getElementById('rocket');window.addEventListener('scroll',()=>r.classList.toggle('on',scrollY>innerHeight*.9),{passive:true});r.addEventListener('click',()=>{r.classList.remove('launch');void r.offsetWidth;r.classList.add('launch');setTimeout(()=>{scrollTo({top:0,behavior:'smooth'});r.classList.remove('launch');},360);});})();

/* URL 可恢复当前视图；旧版 #day/#week/#month 仍兼容 */
applyMods();
restoringView=true;restoreViewFromURL();renderFilters();render();restoringView=false;syncViewURL();
</script>
</body></html>
"""


def _embed_json(payload):
    """JSON → 可安全嵌进 <script> 的 JS 字面量（防 </script> 与 U+2028/2029）。"""
    s = json.dumps(payload, ensure_ascii=False)
    return (s.replace("<", "\\u003c")
             .replace(">", "\\u003e")
             .replace(chr(0x2028), "\\u2028")
             .replace(chr(0x2029), "\\u2029"))


def write_dashboard(records, since=None, until=None, sources=None):
    payload = build_payload(records, since=since, until=until, sources=sources)
    html_doc = _TEMPLATE.replace("__DATA__", _embed_json(payload))
    os.makedirs(config.OUT_DIR, exist_ok=True)
    path = os.path.join(config.OUT_DIR, "dashboard.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_doc)
    return path


def open_path(path):
    import subprocess
    subprocess.Popen(["open", path])
