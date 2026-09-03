"""生成独立 HTML 报告：日=日历热力图，周/月=内联 SVG 柱状图 + 饼图 + 明细表。

无 CDN/JS 依赖，双击即开。亮/暗双色自动跟随系统（prefers-color-scheme）。
"""
import os
import html
import math
from datetime import datetime

from . import config, report_term
from .opener import open_path

PERIOD_TITLE = {"day": "每日", "week": "每周", "month": "每月"}

# 系列配色（亮/暗通用）。热力图色阶由 CSS 变量按主题切换。
SERIES = ["#5b8def", "#f0a84b", "#56c596", "#ef6f6d",
          "#9b8cf2", "#4ec9d6", "#e08a6a", "#7ec1e8"]


def _esc(s):
    return html.escape(str(s))


def _fmt(n):
    return f"{n:,}"


def _human(n):
    for unit, div in (("亿", 1_0000_0000), ("万", 1_0000)):
        if n >= div:
            return f"{n / div:.1f}{unit}"
    return str(n)


def _pct(frac):
    return f"{frac * 100:.1f}%"


def _fmt_label(period, mode, rows):
    """与 dashboard fmtLabel 一致：月期去 '-01'；日/周单年压成 MM-DD。"""
    p = str(period).split("-")
    if mode == "month":
        return p[0] + "-" + (p[1] if len(p) > 1 else "")
    if mode in ("day", "week"):
        years = {(pp or "")[:4] for pp, _ in rows}
        if len(years) > 1:
            return period
        return (p[1] if len(p) > 1 else "") + "-" + (p[2] if len(p) > 2 else "")
    return period


# ---------- 柱状图（周/月）----------

def _svg_bar_chart(rows, mode, width=820, height=300):
    """rows: [(period, value)]。标签按 mode 美化；过密则倾斜 + 抽稀。描边/填色走 CSS 类，自动随主题。"""
    bars = [(l, v) for l, v in rows]
    if not bars:
        return '<p class="hint">无数据</p>'
    vmax = max(v for _, v in bars) or 1
    # 整图锁定单一单位，避免 y 轴 万与亿混用造成歧义
    if vmax >= 1_0000_0000:
        ulabel, udiv = "亿", 1_0000_0000
    elif vmax >= 1_0000:
        ulabel, udiv = "万", 1_0000
    else:
        ulabel, udiv = "", 1

    def _vf(n):
        if not ulabel:
            return str(round(n))
        v = n / udiv
        return (f"{v:.1f}" if v < 10 else str(round(v))) + ulabel

    n = len(bars)
    pad_l, pad_t, pad_r = 58, 16, 20
    plot_w = width - pad_l - pad_r
    step = plot_w / n
    # 每根柱都标日期：少→横排，中→斜(-45)，密→竖(-90)，永不抽稀
    ang = 0 if n <= 10 else (-45 if step >= 26 else -90)
    pad_b = 40 if ang == 0 else (56 if ang == -45 else 48)
    plot_h = height - pad_b - pad_t
    bw = min(46, step * 0.62)

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" preserveAspectRatio="xMidYMid meet">']
    for i in range(5):
        frac = i / 4
        y = pad_t + plot_h * (1 - frac)
        val = int(vmax * frac)
        parts.append(f'<line class="grid-line" x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" />')
        if i > 0:
            parts.append(f'<text x="{pad_l-9}" y="{y+3.5:.1f}" text-anchor="end" class="tick">{_vf(val)}</text>')
    parts.append(f'<line class="axis" x1="{pad_l}" y1="{pad_t+plot_h:.1f}" x2="{width-pad_r}" y2="{pad_t+plot_h:.1f}" />')
    for i, (label, v) in enumerate(bars):
        x = pad_l + step * i + (step - bw) / 2
        h = (v / vmax) * plot_h if vmax else 0
        y = pad_t + plot_h - h
        parts.append(f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2"><title>{_esc(label)}: {_fmt(v)}</title></rect>')
        lab = _fmt_label(label, mode, rows)
        lx = pad_l + step * i + step / 2
        if ang == 0:
            ly = height - pad_b + 18; anchor = "middle"; tr = ""
        elif ang == -45:
            ly = height - pad_b + 30; anchor = "end"; tr = f'transform="rotate(-45 {lx:.1f} {ly})"'
        else:
            ly = height - 8; anchor = "start"; tr = f'transform="rotate(-90 {lx:.1f} {ly})"'
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" class="xlabel" {tr}>{_esc(lab)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# ---------- 饼图 ----------

def _svg_pie(slices, size=240):
    """slices: [(label, value)]。分片描边 / 中心孔走 CSS 类，随主题。"""
    total = sum(v for _, v in slices) or 1
    cx, cy, r = size / 2, size / 2, size / 2 - 8
    angle = -math.pi / 2
    parts = [f'<svg viewBox="0 0 {size} {size}" class="pie" role="img">']
    for i, (label, v) in enumerate(slices):
        frac = v / total
        a0 = angle
        a1 = angle + frac * 2 * math.pi
        color = SERIES[i % len(SERIES)]
        if frac >= 0.999:
            parts.append(f'<circle class="slice" cx="{cx}" cy="{cy}" r="{r}" fill="{color}"><title>{_esc(label)} {_pct(frac)}</title></circle>')
        else:
            large = 1 if frac > 0.5 else 0
            x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
            x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
            d = f"M {cx} {cy} L {x0:.2f} {y0:.2f} A {r} {r} 0 {large} 1 {x1:.2f} {y1:.2f} Z"
            parts.append(f'<path class="slice" d="{d}" fill="{color}"><title>{_esc(label)} {_pct(frac)}</title></path>')
        angle = a1
    parts.append(f'<circle class="pie-hole" cx="{cx}" cy="{cy}" r="{r*0.56:.1f}" />')
    parts.append(f'<text x="{cx}" y="{cy-2}" text-anchor="middle" class="pie-center">{_human(total)}</text>')
    parts.append(f'<text x="{cx}" y="{cy+15}" text-anchor="middle" class="pie-sub">TOKENS</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# ---------- 组装 ----------

_STYLE = """
:root{
  --bg:#f5f7fa; --panel:#ffffff; --panel-2:#eef1f6;
  --ink:#1c2128; --dim:#5a6573; --faint:#8b95a4;
  --line:#e2e7ee; --line-2:#cfd6e0;
  --accent:#2f6fd6; --accent-2:#5b8def;
  --shadow:0 1px 2px rgba(20,30,50,.05),0 10px 30px rgba(20,30,50,.07);
  --l0:#ebedf2; --l1:#cfe0ff; --l2:#8db4ff; --l3:#5b8def; --l4:#2f6fd6;
  --hm-num:#9aa3b2; color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#0b0e14; --panel:#131822; --panel-2:#1b212d;
    --ink:#e6edf3; --dim:#8b949e; --faint:#6e7681;
    --line:#21262d; --line-2:#30363d;
    --accent:#5b8def; --accent-2:#7aa2f7;
    --shadow:0 1px 0 rgba(255,255,255,.04) inset,0 12px 34px rgba(0,0,0,.5);
    --l0:#1d242e; --l1:#243b5e; --l2:#2f5b9f; --l3:#5b8def; --l4:#9abcff;
    --hm-num:#5b6573; color-scheme:dark;
  }
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1100px 560px at 82% -12%,rgba(91,141,239,.14),transparent 62%),var(--bg);
  color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;
  padding:30px 24px 56px;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:23px;margin:0;font-weight:700;letter-spacing:.1px}
.sub{color:var(--dim);font-size:12.5px;margin-top:4px;margin-bottom:22px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:16px;box-shadow:var(--shadow)}
.card h2{font-size:11.5px;color:var(--dim);margin:0 0 14px;font-weight:600;letter-spacing:.7px;text-transform:uppercase}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.kpi{background:var(--panel-2);border:1px solid var(--line);border-radius:12px;padding:15px 16px;position:relative;overflow:hidden}
.kpi::after{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(var(--accent-2),transparent)}
.kpi .v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.1;letter-spacing:-.3px}
.kpi .l{color:var(--dim);font-size:11.5px;margin-top:6px}
.chart,.pie{width:100%;height:auto;display:block}
.pie{max-width:230px;margin:0 auto}
.grid-line{stroke:var(--line)}.axis{stroke:var(--line-2)}
.bar{fill:var(--accent-2)}
.tick{fill:var(--faint);font-size:10px}
.xlabel{fill:var(--dim);font-size:10.5px}
.slice{stroke:var(--panel);stroke-width:2}
.pie-hole{fill:var(--panel)}
.pie-center{fill:var(--ink);font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}
.pie-sub{fill:var(--dim);font-size:10px;letter-spacing:.5px}
.hm-wrap{display:flex;flex-direction:column;gap:20px}
.hm-head{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:9px}
.hm-month{font-size:13.5px;font-weight:700}.hm-sub{font-size:11.5px;color:var(--faint);font-variant-numeric:tabular-nums}
.hm-grid{display:grid;grid-template-columns:repeat(7,30px);gap:4px}
.hm-wd{font-size:10px;color:var(--faint);text-align:center;padding-bottom:3px}
.hm-cell{width:30px;height:27px;border-radius:6px;display:grid;place-items:center;font-size:10px;color:var(--hm-num);background:var(--l0)}
.hm-cell.l1{background:var(--l1);color:rgba(255,255,255,.7)}
.hm-cell.l2{background:var(--l2);color:#fff}
.hm-cell.l3{background:var(--l3);color:#fff}
.hm-cell.l4{background:var(--l4);color:#fff;box-shadow:0 0 0 1.5px var(--accent-2) inset}
.hm-legend{display:flex;align-items:center;gap:6px;margin-top:14px;font-size:11px;color:var(--dim)}
.hm-legend .sw{width:14px;height:14px;border-radius:4px}
.legend{list-style:none;padding:0;margin:14px 0 0;display:grid;grid-template-columns:1fr 1fr;gap:6px 14px}
.legend li{font-size:12.5px;color:var(--ink);display:flex;align-items:center}
.legend em{color:var(--faint);font-style:normal;margin-left:auto;padding-left:8px;font-variant-numeric:tabular-nums}
.dot{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:7px;vertical-align:middle}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:600;font-size:11.5px;letter-spacing:.3px}
tbody tr{transition:background .12s}tbody tr:hover{background:var(--panel-2)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr.now td{color:var(--accent);font-weight:600}
.hint{color:var(--dim);font-size:12.5px;text-align:center;padding:28px}
footer{color:var(--faint);font-size:11.5px;text-align:center;margin-top:20px}
footer b{color:var(--dim);font-weight:600}
a{color:var(--accent)}
"""


def write_report(mode, rows, focus_date, focus_label, all_sources):
    """rows: [(period, summarize)]; all_sources: 本次扫描命中的 source 列表。"""
    focus = None
    for p, s in rows:
        if p == focus_date:
            focus = s
            break
    if focus is None:
        focus = rows[-1][1] if rows else {"total": 0, "by_model": [], "by_source": [], "calls": 0}

    bar_rows = [(p, s2["total"]) for p, s2 in rows]
    model_slices = focus["by_model"][:8]
    src_slices = focus["by_source"]

    cols = report_term._top_model_columns(rows)
    col_name = {m: config.pretty_model(m) for m in cols}
    model_th = "".join(f"<th class=num>{_esc(col_name[m])}</th>" for m in cols)

    table_rows = []
    for p, s2 in rows:
        mmap = dict(s2["by_model"])
        mark = " ◀" if p == focus_date else ""
        cells = "".join(f"<td class=num>{_fmt(mmap.get(m, 0))}</td>" for m in cols)
        table_rows.append(
            f"<tr{' class=now' if p==focus_date else ''}>"
            f"<td>{_esc(_fmt_label(p, mode, rows))}{mark}</td>"
            f"<td class=num>{_fmt(s2['total'])}</td>"
            f"{cells}"
            f"<td class=num>{s2['calls']}</td></tr>"
        )

    legend_models = "".join(
        f'<li><span class=dot style="background:{col}"></span>{_esc(config.pretty_model(m))} <em>{_fmt(v)}</em></li>'
        for (m, v), col in zip(model_slices, SERIES)
    )
    legend_sources = "".join(
        f'<li><span class=dot style="background:{col}"></span>{_esc(src)} <em>{_fmt(v)}</em></li>'
        for (src, v), col in zip(src_slices, SERIES)
    )

    trend_title = f"{PERIOD_TITLE.get(mode, '')}总 token 趋势"
    trend_body = _svg_bar_chart(bar_rows, mode)

    focus_disp = _fmt_label(focus_date, mode, rows)
    title = f"Token 用量报告 · {PERIOD_TITLE.get(mode, '')} · {focus_label} {focus_disp}"
    now_str = datetime.now(config.TZ).strftime("%Y-%m-%d %H:%M")

    html_doc = f"""<!doctype html>
<html lang=zh><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>{_STYLE}</style></head><body>
<div class=wrap>
<h1>{_esc(title)}</h1>
<div class=sub>生成于 {_esc(now_str)} · 来源：{', '.join(all_sources) or '无'} · 本地日志解析</div>

<div class=card>
 <div class=kpis>
   <div class=kpi><div class=v>{_fmt(focus['total'])}</div><div class=l>{_esc(focus_label)} 总 token</div></div>
   <div class=kpi><div class=v>{_fmt(focus['calls'])}</div><div class=l>调用次数</div></div>
   <div class=kpi><div class=v>{len(focus['by_model'])}</div><div class=l>模型数</div></div>
 </div>
</div>

<div class=card>
 <h2>{_esc(trend_title)}</h2>
 {trend_body}
</div>

<div class=grid>
 <div class=card>
  <h2>本期模型分布</h2>
  {_svg_pie(model_slices)}
  <ul class=legend>{legend_models}</ul>
 </div>
 <div class=card>
  <h2>本期来源分布</h2>
  {_svg_pie(src_slices)}
  <ul class=legend>{legend_sources}</ul>
 </div>
</div>

<div class=card>
 <h2>明细</h2>
 <table><thead><tr><th>{_esc(PERIOD_TITLE.get(mode,''))+'期'}</th><th class=num>总 token</th>{model_th}<th class=num>调用</th></tr></thead>
 <tbody>{''.join(table_rows)}</tbody></table>
</div>

<footer>by <b>tokens</b> · 数据来自 ~/.claude / ~/.gemini / ~/.codex · 亮/暗随系统</footer>
</div>
</body></html>"""

    os.makedirs(config.OUT_DIR, exist_ok=True)
    fname = f"report-{mode}-{focus_date}.html"
    path = os.path.join(config.OUT_DIR, fname)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_doc)
    return path
