#!/usr/bin/env python3
"""Command-line interface for local AI CLI token analytics."""
import argparse
import sys
from datetime import date, datetime, timedelta

from . import (__version__, aggregate, config, doctor, live_dashboard, readers,
               report_dashboard, report_html, report_term)
from .opener import open_url

RANGES = ["day", "week", "month", "all", "dashboard", "serve", "doctor"]


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
        description="Local-first token usage analytics for Claude Code, Gemini CLI, and Codex.",
    )
    parser.add_argument("range", nargs="?", default="day", choices=RANGES,
                        help="report range or command (default: day)")
    parser.add_argument("--since", help="start date in YYYY-MM-DD")
    parser.add_argument("--until", help="end date in YYYY-MM-DD")
    parser.add_argument("--days", type=_positive_int, default=14, help="days shown in day mode")
    parser.add_argument("--weeks", type=_positive_int, default=8, help="weeks shown in week mode")
    parser.add_argument("--months", type=_positive_int, default=6, help="months shown in month mode")
    parser.add_argument("--source", action="append", choices=sorted(readers.SOURCES),
                        help="log source; repeat to combine sources (default: claude)")
    parser.add_argument("--html", action="store_true", help="write a static HTML report")
    parser.add_argument("--dashboard", action="store_true", help="write the interactive offline dashboard")
    parser.add_argument("--anonymize", action="store_true",
                        help="pseudonymize identifiers in an offline or live dashboard")
    parser.add_argument("--open", action="store_true", help="open generated HTML in the default browser")
    parser.add_argument("--output", metavar="DIR", help="output directory (default: ./out)")
    parser.add_argument("--timezone", metavar="ZONE", help="IANA timezone, for example Europe/Berlin")
    parser.add_argument("--no-cache", action="store_true", help="ignore the file cache and re-read logs")
    parser.add_argument("--interval", type=_positive_float, default=5.0,
                        help="live Dashboard check interval in seconds (default: 5)")
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
    if args.since and args.until and args.since > args.until:
        parser.error("--since must not be after --until")
    if args.anonymize and not (args.dashboard or args.range in ("dashboard", "serve")):
        parser.error("--anonymize requires dashboard or serve mode")


def _open_generated(path):
    try:
        opened = report_dashboard.open_path(path)
    except OSError as exc:
        print(f"Could not open the browser: {exc}", file=sys.stderr)
        return
    if opened is False:
        print(f"Could not open the browser automatically. Open this file: {path}", file=sys.stderr)


def _no_records_message(sources):
    roots = {
        "claude": config.CLAUDE_PROJECTS,
        "gemini": config.GEMINI_TMP,
        "codex": config.CODEX_SESSIONS,
    }
    print("No supported token logs were found.", file=sys.stderr)
    for source in sources:
        print(f"  {source}: {roots[source]}", file=sys.stderr)
    print("Run `tokens doctor` for a source-by-source check.", file=sys.stderr)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure(args, parser)
    sources = args.source or config.DEFAULT_SOURCES

    if args.range == "doctor":
        doctor.print_report(doctor.collect(sources=args.source))
        return 0

    if args.range == "serve":
        try:
            server = live_dashboard.create_server(
                args.port,
                sources,
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
        print(f"Live Dashboard: {url}")
        print(f"Checking local logs every {args.interval:g} seconds. Press Ctrl+C to stop.")
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

    now = datetime.now(config.TZ).date()
    mode = args.range
    records = readers.read_all(sources=sources, use_cache=not args.no_cache)
    if not records:
        _no_records_message(sources)
        return 1

    if args.dashboard or mode == "dashboard":
        path = report_dashboard.write_dashboard(
            records,
            since=args.since,
            until=args.until,
            sources=sources,
            anonymize=args.anonymize,
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
    all_sources = sorted({record["source"] for record in recs}) or sorted({record["source"] for record in records})
    report_term.print_report(mode, rows, focus, label)

    if args.html:
        path = report_html.write_report(mode, rows, focus, label, all_sources)
        print(f"HTML report: {path}")
        if args.open:
            _open_generated(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
