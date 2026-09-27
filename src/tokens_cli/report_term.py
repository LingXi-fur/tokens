"""终端表格输出。纯 ANSI，不依赖 rich。

趋势表按「模型」拆列，而非按来源。
文案随 lang 参数切换（en/zh），默认沿用中文。
"""
from . import config

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RESET = "\033[0m"

TEXT = {
    "zh": {
        "period": {"day": "日期", "week": "周(始)", "month": "月份"},
        "period_fallback": "期",
        "empty": "范围内无数据",
        "total": "总 token",
        "focus_sep": "：",
        "calls": "{c} 次调用",
        "by_model": "按模型：",
        "history": "历史趋势（{label}）",
        "trend": "趋势",
        "now": "◀ 现在",
        "units": (("亿", 1_0000_0000), ("万", 1_0000)),
    },
    "en": {
        "period": {"day": "Date", "week": "Week (start)", "month": "Month"},
        "period_fallback": "Period",
        "empty": "No data in range",
        "total": "Total tokens",
        "focus_sep": ": ",
        "calls": "{c} calls",
        "by_model": "By model:",
        "history": "Trend history ({label})",
        "trend": "Trend",
        "now": "◀ now",
        "units": (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)),
    },
}


def fmt(n):
    return f"{n:,}"


def fmt_period(period, mode, rows):
    """期间标签美化：月期去 '-01'；日/周单年压成 MM-DD（与 dashboard/html 一致）。"""
    p = str(period).split("-")
    if mode == "month":
        return p[0] + "-" + (p[1] if len(p) > 1 else "")
    if mode in ("day", "week"):
        years = {(pp or "")[:4] for pp, _ in rows}
        if len(years) > 1:
            return period
        return (p[1] if len(p) > 1 else "") + "-" + (p[2] if len(p) > 2 else "")
    return period


def _human(n, units):
    for unit, div in units:
        if n >= div:
            return f"{n / div:.1f}{unit}"
    return str(n)


def _bar(ratio, width=24):
    filled = int(ratio * width)
    return "█" * filled + "░" * (width - filled)


def _top_model_columns(rows, limit=3):
    """从所有期里挑总 token 最高的 N 个模型。"""
    totals = {}
    for _, s in rows:
        for m, v in s["by_model"]:
            totals[m] = totals.get(m, 0) + v
    return [
        model
        for model, _ in sorted(
            totals.items(),
            key=lambda item: (-item[1], item[0]),
        )[:limit]
    ]


def print_report(mode, rows, focus_date, focus_label, lang="zh"):
    """rows: [(period_str, summarize_dict), ...]，已排序。"""
    t = TEXT.get(lang, TEXT["zh"])
    if not rows:
        print(f"{DIM}{t['empty']}{RESET}")
        return

    # 头条：关注期
    focus = None
    for p, s in rows:
        if p == focus_date:
            focus = (p, s)
            break
    if focus is None:
        focus = rows[-1]

    p, s = focus
    print()
    print(f"{BOLD}{CYAN}■ {focus_label}{t['focus_sep']}{fmt_period(p, mode, rows)}{RESET}")
    print(f"  {BOLD}{t['total']}{t['focus_sep']}{fmt(s['total'])}{RESET}  "
          f"{DIM}({t['calls'].format(c=s['calls'])}){RESET}")

    # 按模型
    if s["by_model"]:
        print(f"  {DIM}{t['by_model']}{RESET}")
        top_m = max(v for _, v in s["by_model"]) or 1
        for model, v in s["by_model"]:
            ratio = v / top_m if top_m else 0
            pct = v / s["total"] * 100 if s["total"] else 0
            color = GREEN if model.startswith("deepseek") else YELLOW
            print(f"    {config.pretty_model(model):<20} {fmt(v):>14}  "
                  f"{color}{pct:5.1f}%{RESET}  {DIM}{_bar(ratio, 16)}{RESET}")
    print()

    # 趋势表 —— 按模型拆列
    label = t["period"].get(mode, t["period_fallback"])
    cols = _top_model_columns(rows)
    col_name = {m: config.pretty_model(m) for m in cols}

    print(f"{BOLD}{t['history'].format(label=label)}{RESET}")
    max_total = max((s2["total"] for _, s2 in rows), default=1) or 1

    # 表头：日期 | 总 | 各模型列 | 趋势
    header = f"  {label:<11} {t['total']:>13}"
    sep = f"  {'-'*11} {'-'*13}"
    for m in cols:
        w = max(14, len(col_name[m]) + 2)
        header += f"  {col_name[m]:>{w}}"
        sep += f"  {'-'*w}"
    header += f"  {t['trend']:<24}"
    sep += f"  {'-'*24}"
    print(header)
    print(sep)

    for p, s2 in rows:
        mmap = dict(s2["by_model"])
        plab = fmt_period(p, mode, rows)
        line = f"  {plab:<11} {fmt(s2['total']):>13}"
        for m in cols:
            w = max(14, len(col_name[m]) + 2)
            v = mmap.get(m, 0)
            cell = fmt(v) if v else f"{DIM}·{RESET}"
            # · 占 1 视觉位，但带 ANSI；对齐用空格补到宽度（粗略）
            if v:
                line += f"  {cell:>{w}}"
            else:
                line += f"  {' ':>{w-1}}{DIM}·{RESET}"
        bar = _bar(s2["total"] / max_total if max_total else 0, 24)
        mark = f" {CYAN}{t['now']}{RESET}" if p == focus_date else ""
        line += f"  {DIM}{bar}{RESET}{mark}"
        print(line)
    print()
