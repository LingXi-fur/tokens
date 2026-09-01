"""终端表格输出。纯 ANSI，不依赖 rich。

默认只看 claude（GLM-5.2 / DeepSeek），所以趋势表按「模型」拆列，而非按来源。
"""
from . import config

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RESET = "\033[0m"

PERIOD_LABEL = {"day": "日期", "week": "周(始)", "month": "月份"}

# 趋势表里固定展示的模型列（按常见度排序）。命中即显示，无数据补 0。
PRIORITY_MODELS = ["glm-5.2", "deepseek-v4-pro", "glm-5.1"]


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


def _human(n):
    for unit, div in (("亿", 1_0000_0000), ("万", 1_0000)):
        if n >= div:
            return f"{n / div:.1f}{unit}"
    return str(n)


def _bar(ratio, width=24):
    filled = int(ratio * width)
    return "█" * filled + "░" * (width - filled)


def _top_model_columns(rows, limit=3):
    """从所有期里挑总 token 最高的 N 个模型，并叠加 PRIORITY_MODELS 顺序。"""
    totals = {}
    for _, s in rows:
        for m, v in s["by_model"]:
            totals[m] = totals.get(m, 0) + v
    ranked = [m for m, _ in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)]
    cols = []
    for m in PRIORITY_MODELS:
        if m in totals and m not in cols:
            cols.append(m)
    for m in ranked:
        if m not in cols:
            cols.append(m)
    return cols[:limit]


def print_report(mode, rows, focus_date, focus_label):
    """rows: [(period_str, summarize_dict), ...]，已排序。"""
    if not rows:
        print(f"{DIM}范围内无数据{RESET}")
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
    print(f"{BOLD}{CYAN}■ {focus_label}：{fmt_period(p, mode, rows)}{RESET}")
    print(f"  {BOLD}总 token：{fmt(s['total'])}{RESET}  {DIM}({s['calls']} 次调用){RESET}")

    # 按模型
    if s["by_model"]:
        print(f"  {DIM}按模型：{RESET}")
        top_m = max(v for _, v in s["by_model"]) or 1
        for model, v in s["by_model"]:
            ratio = v / top_m if top_m else 0
            pct = v / s["total"] * 100 if s["total"] else 0
            color = GREEN if model.startswith("deepseek") else YELLOW
            print(f"    {config.pretty_model(model):<20} {fmt(v):>14}  "
                  f"{color}{pct:5.1f}%{RESET}  {DIM}{_bar(ratio, 16)}{RESET}")
    print()

    # 趋势表 —— 按模型拆列
    label = PERIOD_LABEL.get(mode, "期")
    cols = _top_model_columns(rows)
    col_name = {m: config.pretty_model(m) for m in cols}

    print(f"{BOLD}历史趋势（{label}）{RESET}")
    max_total = max((s2["total"] for _, s2 in rows), default=1) or 1

    # 表头：日期 | 总 | 各模型列 | 趋势
    header = f"  {label:<11} {'总 token':>13}"
    sep = f"  {'-'*11} {'-'*13}"
    for m in cols:
        w = max(14, len(col_name[m]) + 2)
        header += f"  {col_name[m]:>{w}}"
        sep += f"  {'-'*w}"
    header += f"  {'趋势':<24}"
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
        mark = f" {CYAN}◀ 现在{RESET}" if p == focus_date else ""
        line += f"  {DIM}{bar}{RESET}{mark}"
        print(line)
    print()
