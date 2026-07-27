#!/usr/bin/env python3
"""入口：统计 Claude / Gemini / Codex token 用量。

用法：
  python3 cli.py                 # 今天（默认）
  python3 cli.py week            # 本周 + 最近 N 周
  python3 cli.py month           # 本月 + 最近 N 月
  python3 cli.py month --html    # 本月 + 生成 HTML 报告
  python3 cli.py --since 2026-07-01 --until 2026-07-24
  python3 cli.py day --source claude --source gemini
  python3 cli.py --no-cache      # 强制重读日志
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta

import config
import readers
import aggregate
import report_term
import report_html
import report_dashboard


def compute_window(mode, now, days, weeks, months):
    """返回 (since_iso, focus_iso, focus_label)。"""
    if mode == "day":
        since = (now - timedelta(days=days - 1)).isoformat()
        focus = now.isoformat()
        label = "今天"
    elif mode == "week":
        ws = aggregate.week_start(now)
        since = (ws - timedelta(weeks=weeks - 1)).isoformat()
        focus = ws.isoformat()
        label = "本周"
    elif mode == "month":
        ms = aggregate.month_start(now)
        since = aggregate.add_months(ms, -(months - 1)).isoformat()
        focus = ms.isoformat()
        label = "本月"
    else:  # all
        since = None
        focus = now.isoformat()
        label = "今天"
    return since, focus, label


def main(argv=None):
    p = argparse.ArgumentParser(description="统计 Claude/Gemini/Codex token 用量")
    p.add_argument("range", nargs="?", default="day",
                   choices=["day", "week", "month", "all", "dashboard"],
                   help="统计粒度：day(默认) / week / month / all / dashboard")
    p.add_argument("--since", help="起始日期 YYYY-MM-DD")
    p.add_argument("--until", help="结束日期 YYYY-MM-DD")
    p.add_argument("--days", type=int, default=14, help="day 模式回看天数")
    p.add_argument("--weeks", type=int, default=8, help="week 模式回看周数")
    p.add_argument("--months", type=int, default=6, help="month 模式回看月数")
    p.add_argument("--source", action="append",
                   choices=["claude", "gemini", "codex"],
                   help="限定来源，可多次；默认仅 claude")
    p.add_argument("--html", action="store_true", help="生成静态 HTML 报告")
    p.add_argument("--dashboard", action="store_true",
                   help="生成交互式 dashboard（内含日/周/月，离线可用）")
    p.add_argument("--anonymize", action="store_true",
                   help="生成脱敏 Dashboard（替换项目路径、会话标识与标题）")
    p.add_argument("--open", action="store_true", help="生成 HTML 后自动打开")
    p.add_argument("--no-cache", action="store_true", help="强制重读日志")
    args = p.parse_args(argv)

    if args.anonymize and not (args.dashboard or args.range == "dashboard"):
        p.error("--anonymize 只能与 dashboard 模式或 --dashboard 一起使用")

    now = datetime.now(config.TZ).date()
    mode = args.range

    sources = args.source or config.DEFAULT_SOURCES
    records = readers.read_all(sources=sources, use_cache=not args.no_cache)
    if not records:
        print("未找到任何日志。检查 ~/.claude / ~/.gemini / ~/.codex 是否存在。")
        return 1

    # 交互式 dashboard：内含日/周/月，忽略 range 粒度，遵守 since/until/source
    if args.dashboard or mode == "dashboard":
        path = report_dashboard.write_dashboard(
            records,
            since=args.since,
            until=args.until,
            sources=sources,
            anonymize=args.anonymize,
        )
        print(f"Dashboard：{path}")
        if args.open:
            report_dashboard.open_path(path)
        return 0

    # 确定窗口
    if args.since:
        since = args.since
    else:
        since, _, _ = compute_window(mode, now, args.days, args.weeks, args.months)
    until = args.until or now.isoformat()
    recs = aggregate.filter_range(records, since=since, until=until)

    if mode == "day":
        rows = aggregate.by_day(recs)
    elif mode == "week":
        rows = aggregate.by_week(recs)
    elif mode == "month":
        rows = aggregate.by_month(recs)
    else:
        rows = aggregate.by_day(recs)

    _, focus, label = compute_window(mode, now, args.days, args.weeks, args.months)

    # 命中的来源
    all_sources = sorted({r["source"] for r in recs}) or sorted({r["source"] for r in records})

    report_term.print_report(mode, rows, focus, label)

    if args.html:
        path = report_html.write_report(mode, rows, focus, label, all_sources)
        print(f"HTML 报告：{path}")
        if args.open:
            report_html.open_path(path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
