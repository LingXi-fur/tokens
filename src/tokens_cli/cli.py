#!/usr/bin/env python3
"""Command-line interface for local AI CLI token analytics."""
import argparse
import json
import sys
from datetime import date, datetime, timedelta

from . import (__version__, aggregate, config, demo, doctor, lang as lang_module, live_dashboard,
               quota, readers, report_dashboard, report_html, report_term, sources as source_registry)
from .opener import open_url

RANGES = ["day", "week", "month", "all", "dashboard", "demo", "serve", "doctor", "quota"]


def compute_window(mode, now, days, weeks, months):
    if mode == "day":
        since = (now - timedelta(days=days - 1)).isoformat()
        focus = now.isoformat()
        label = "Today"
    elif mode == "week":
        ws = aggregate.week_start(now)
        since = (ws - timedelta(weeks=weeks - 1)).isoformat()
        focus = ws.isoformat()
        label = "This week"
    elif mode == "month":
        ms = aggregate.month_start(now)
        since = aggregate.add_months(ms, -(months - 1)).isoformat()
        focus = ms.isoformat()
        label = "This month"
    else:
        since = None
        focus = now.isoformat()
        label = "Today"
    return since, focus, label


def build_parser():
    parser = argparse.ArgumentParser(
        prog="tokens",
        description="Local-first token usage analytics for Claude Code, Gemini CLI, Codex, OpenCode, and Antigravity.",
    )
    parser.add_argument("range", nargs="?", default="day", choices=RANGES,
                        help="report range or command (default: day)")
    parser.add_argument("--since", help="start date in YYYY-MM-DD")
    parser.add_argument("--until", help="end date in YYYY-MM-DD")
    parser.add_argument("--days", type=_positive_int, default=14, help="days shown in day mode")
    parser.add_argument("--weeks", type=_positive_int, default=8, help="weeks shown in week mode")
    parser.add_argument("--months", type=_positive_int, default=6, help="months shown in month mode")
    parser.add_argument("--source", action="append",
                        choices=sorted(source_registry.NAMES) + ["auto"],
                        help="log source; repeat to combine sources (default: auto)")
    parser.add_argument("--html", action="store_true", help="write a static HTML report")
    parser.add_argument("--dashboard", action="store_true", help="write the interactive offline dashboard")
    parser.add_argument("--anonymize", action="store_true",
                        help="pseudonymize identifiers in an offline or live dashboard")
    parser.add_argument("--open", action="store_true", help="open generated HTML in the default browser")
    parser.add_argument("--output", metavar="DIR", help="output directory (default: ./out)")
    parser.add_argument("--timezone", metavar="ZONE", help="IANA timezone, for example Europe/Berlin")
    parser.add_argument("--lang", choices=lang_module.SUPPORTED,
                        help="terminal and static HTML language (en or zh; default: system locale)")
    parser.add_argument("--no-cache", action="store_true", help="ignore the file cache and re-read logs")
    parser.add_argument("--models", action="store_true",
                        help="with doctor, show how Claude request names map to models")
    parser.add_argument("--json", action="store_true",
                        help="with doctor --models or quota, print machine-readable JSON")
    parser.add_argument("--interval", type=_positive_float, default=300.0,
                        help="live Dashboard check interval in seconds (default: 300)")
    parser.add_argument("--port", type=_port, default=8765,
                        help="live Dashboard loopback port; 0 chooses a free port (default: 8765)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _positive_float(value):
    number = float(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _port(value):
    number = int(value)
    if number < 0 or number > 65535:
        raise argparse.ArgumentTypeError("must be between 0 and 65535")
    return number


def _date(value, flag, parser):
    if value is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        parser.error(f"{flag} must use YYYY-MM-DD")


def _configure(args, parser):
    if args.output:
        config.set_output_dir(args.output)
    if args.timezone:
        try:
            config.set_timezone(args.timezone)
        except ValueError as exc:
            parser.error(str(exc))
    args.since = _date(args.since, "--since", parser)
    args.until = _date(args.until, "--until", parser)
    try:
        args.lang = lang_module.resolve_lang(args.lang)
    except ValueError as exc:
        parser.error(str(exc))
    if args.since and args.until and args.since > args.until:
        parser.error("--since must not be after --until")
    if args.anonymize and not (
        args.dashboard or args.range in ("dashboard", "demo", "serve")
    ):
        parser.error("--anonymize requires dashboard, demo, or serve mode")
    if args.models and args.range != "doctor":
        parser.error("--models requires doctor mode")
    if args.json and not ((args.range == "doctor" and args.models)
                          or args.range == "quota"):
        parser.error("--json requires doctor --models or quota")


def _open_generated(path):
    try:
        opened = report_dashboard.open_path(path)
    except OSError as exc:
        print(f"Could not open the browser: {exc}", file=sys.stderr)
        return
    if opened is False:
        print(f"Could not open the browser automatically. Open this file: {path}", file=sys.stderr)


def _no_records_message(sources):
    print("No supported token logs were found.", file=sys.stderr)
    for source in sources:
        registered = source_registry.BY_NAME.get(source)
        print(f"  {source}: {registered.root() if registered else 'unknown source'}",
              file=sys.stderr)
    print(
        "Run `tokens doctor` (or `./run doctor` in a source checkout) "
        "for a source-by-source check.",
        file=sys.stderr,
    )
    print(
        "Try the private synthetic demo with `tokens demo --open` "
        "(or `./run demo --open`).",
        file=sys.stderr,
    )


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure(args, parser)
    selected_sources, detected, skipped, auto_used = source_registry.resolve(
        args.source or config.DEFAULT_SOURCES)
    discovery_text = (source_registry.format_detection(detected, skipped, args.lang)
                      if auto_used else None)
    if discovery_text and not args.json and args.range != "demo":
        print(discovery_text, flush=True)

    if args.range == "doctor":
        if not args.models:
            doctor.print_report(doctor.collect(sources=selected_sources))
            return 0
        try:
            report = doctor.collect_models(
                sources=selected_sources,
                since=args.since,
                until=args.until,
                use_cache=not args.no_cache,
            )
        except readers.CollectionIncompleteError:
            print(
                "Local log collection is incomplete; no model attribution was produced. "
                "Check log readability and collection limits, then retry.",
                file=sys.stderr,
            )
            return 1
        if auto_used:
            report["sources_detected"] = [source.name for source in detected]
            report["sources_skipped"] = skipped
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            doctor.print_models(report, lang=args.lang)
        return 0

    if args.range == "quota":
        if not selected_sources:
            _no_records_message(selected_sources)
            return 1
        try:
            report = quota.collect(
                sources=selected_sources,
                use_cache=not args.no_cache,
            )
        except readers.CollectionIncompleteError:
            print(
                "Local log collection is incomplete; no quota report was produced. "
                "Check log readability and collection limits, then retry.",
                file=sys.stderr,
            )
            return 1
        if auto_used:
            report["sources_detected"] = [source.name for source in detected]
            report["sources_skipped"] = skipped
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            quota.print_report(report, lang=args.lang)
        return 0

    if args.range == "serve":
        if not selected_sources:
            _no_records_message(selected_sources)
            return 1
        try:
            server = live_dashboard.create_server(
                args.port,
                selected_sources,
                since=args.since,
                until=args.until,
                anonymize=args.anonymize,
                use_cache=not args.no_cache,
                interval=args.interval,
            )
        except OSError as exc:
            print(f"Could not start the live Dashboard: {exc}", file=sys.stderr)
            return 1
        host, port = server.server_address
        url = f"http://{host}:{port}/"
        print(f"Live Dashboard: {url}", flush=True)
        print(f"Checking local logs every {args.interval:g} seconds. Press Ctrl+C to stop.",
              flush=True)
        if args.open:
            try:
                opened = open_url(url)
            except OSError as exc:
                print(f"Could not open the browser: {exc}", file=sys.stderr)
            else:
                if opened is False:
                    print(f"Could not open the browser automatically. Open this URL: {url}", file=sys.stderr)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            print("\nLive Dashboard stopped.")
        finally:
            server.server_close()
        return 0

    if args.range == "demo":
        today = datetime.now(config.TZ).date()
        demo_sources = ([name for name in (args.source or []) if name != "auto"]
                        or list(demo.DEMO_SOURCES))
        bundle = demo.build_demo(today=today, sources=demo_sources)
        path = report_dashboard.write_dashboard(
            bundle["records"],
            since=args.since or bundle["since"],
            until=args.until or bundle["until"],
            sources=bundle["sources"],
            anonymize=args.anonymize,
            filename="dashboard-demo.html",
            generated_at=bundle["generated_at"],
            session_titles=bundle["session_titles"],
            demo=True,
        )
        print(f"Synthetic demo Dashboard: {path}")
        print("Uses generated sample data only; no local AI CLI logs were read.")
        if args.open:
            _open_generated(path)
        return 0

    now = datetime.now(config.TZ).date()
    mode = args.range
    if not selected_sources:
        _no_records_message(selected_sources)
        return 1
    collection_report = {}
    try:
        records = readers.read_all(sources=selected_sources,
                                   use_cache=not args.no_cache,
                                   collection_report=collection_report)
    except readers.CollectionIncompleteError:
        print(
            "Local log collection is incomplete; no report was written. "
            "Check log readability and collection limits, then retry.",
            file=sys.stderr,
        )
        return 1
    if not records:
        # A skipped file is not "no logs": keep the dashboard so data health
        # can explain what was omitted. Other modes still point to doctor.
        if not ((args.dashboard or mode == "dashboard")
                and collection_report.get("skipped")):
            _no_records_message(selected_sources)
            return 1

    if args.dashboard or mode == "dashboard":
        path = report_dashboard.write_dashboard(
            records,
            since=args.since,
            until=args.until,
            sources=selected_sources,
            anonymize=args.anonymize,
            collection_report=collection_report,
        )
        print(f"Dashboard: {path}")
        if args.open:
            _open_generated(path)
        return 0

    since = args.since or compute_window(mode, now, args.days, args.weeks, args.months)[0]
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
    if args.lang == "zh":
        label = {"Today": "今天", "This week": "本周", "This month": "本月"}.get(label, label)
    all_sources = sorted({record["source"] for record in recs}) or sorted({record["source"] for record in records})
    report_term.print_report(mode, rows, focus, label, lang=args.lang)

    if args.html:
        path = report_html.write_report(mode, rows, focus, label, all_sources,
                                        lang=args.lang, discovery=discovery_text)
        print(f"HTML report: {path}")
        if args.open:
            _open_generated(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
