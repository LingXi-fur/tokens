<div align="center">
  <img src="https://raw.githubusercontent.com/LingXi-fur/tokens/v0.2.0/docs/favicon.svg" width="76" height="76" alt="tokens logo">

# tokens

**A local-first usage dashboard for Claude Code, Gemini CLI, and Codex.**

Turn the token logs already on your machine into terminal reports, a live local dashboard, or a self-contained offline snapshot. No account, database, telemetry, or third-party runtime dependencies.

[![CI](https://github.com/LingXi-fur/tokens/actions/workflows/ci.yml/badge.svg)](https://github.com/LingXi-fur/tokens/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-f59e0b)](https://github.com/LingXi-fur/tokens/blob/v0.2.0/LICENSE)
[![Privacy](https://img.shields.io/badge/privacy-local--first-a78bfa)](#privacy)

[Get started](#quick-start) · [Documentation](https://lingxi-fur.github.io/tokens/) · [Dashboard guide](https://lingxi-fur.github.io/tokens/dashboard.html) · [中文说明](https://github.com/LingXi-fur/tokens/blob/v0.2.0/README.zh-CN.md)

</div>

![Synthetic tokens dashboard preview](https://raw.githubusercontent.com/LingXi-fur/tokens/v0.2.0/docs/assets/readme-preview.svg)

> The preview uses synthetic data. `tokens` does not upload your logs, but a generated dashboard can contain local project and session metadata. Read [Privacy](#privacy) before sharing one.

## Why tokens?

AI coding tools already record useful usage data locally, but each tool uses a different log format and token accounting model. `tokens` gives you one offline view across them:

- **Claude Code, Gemini CLI, and Codex** log readers;
- daily, weekly, and monthly trends by model and source;
- project and session exploration where the source logs support it;
- terminal output, a loopback-only live dashboard, and self-contained offline HTML;
- a pseudonymized mode for safer local viewing and export;
- Python standard-library-only runtime with no external network requests.

## Quick start

### Install with pipx

```bash
pipx install ai-cli-tokens
tokens doctor
tokens serve --open
```

`tokens doctor` checks log locations, timezone, output, and cache permissions without reading message content.

### Run from source

```bash
git clone https://github.com/LingXi-fur/tokens.git
cd tokens
./run doctor
./run serve --open
```

Reports are written to `./out` by default. Use `--output DIR` to choose another location.

## Four useful commands

```bash
# A compact terminal report for the last 14 days
tokens day

# Keep a live dashboard open; it checks local logs every 5 seconds
tokens serve \
  --source claude \
  --source gemini \
  --source codex \
  --open

# Export one self-contained offline snapshot
tokens dashboard --open

# Export a pseudonymized snapshot for a limited date range
tokens dashboard --anonymize \
  --since 2026-08-01 \
  --until 2026-08-31
```

## What the dashboard answers

The default path focuses on practical questions:

- How is usage changing over days, weeks, or months?
- Which models and sources account for the total?
- Which projects and sessions are visible in the available logs?
- How much of the standardized composition is fresh input, output, cache read, cache write, or unclassified remainder?
- What changed in a selected period, and which underlying view supports that observation?

The dashboard also includes optional exploration modules such as Data Trail, Signal Lens, session replay, context reuse, activity rhythm, achievements, Token Almanac, and synthetic visual artifacts. They use local aggregates and can be hidden when you only want the core report.

## Supported sources

| Source | Default local path | Project data | Session data | Important accounting note |
|---|---|---:|---:|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | Yes | Yes | Total is input + output + cache read + cache write. |
| Gemini CLI | `~/.gemini/tmp/*/chats/session-*.json` | Usually no | Yes | Uses the source `tokens.total` value when available. |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | Usually no | Usually no | Cached input is already included in input and is not added twice. |

Different tools do not expose identical token semantics. `tokens` preserves each source's reported total; cross-source comparisons should be interpreted accordingly.

## CLI essentials

```text
tokens [day|week|month|all|dashboard|serve|doctor] [options]
```

| Option | Purpose |
|---|---|
| `--source claude|gemini|codex` | Select a source; repeat to combine sources. |
| `--since YYYY-MM-DD` / `--until YYYY-MM-DD` | Limit the report range. |
| `--timezone AREA/CITY` | Override the detected system timezone. |
| `--output DIR` | Choose the report directory; default is `./out`. |
| `--html` | Add a static HTML report to terminal modes. |
| `--anonymize` | Pseudonymize identifiers in dashboard or live mode. |
| `--interval SECONDS` | Live log check interval; minimum 1, default 5. |
| `--port PORT` | Live loopback port; default 8765, or 0 for an available port. |
| `--open` | Open generated HTML or the live local URL in the default browser. |
| `--no-cache` | Re-read all selected log files. |

See the [complete CLI reference](https://lingxi-fur.github.io/tokens/cli.html).

## Privacy

`tokens` runs locally. Offline snapshots make no network requests; live mode talks only to its loopback service on `127.0.0.1` and does not upload logs. That does **not** mean every generated file is safe to publish.

A regular dashboard may contain:

- project paths and working directories;
- session identifiers and locally derived titles;
- exact dates, models, token values, and per-turn token sequences;
- behavioral patterns that can identify a person or organization.

`--anonymize` replaces project paths, session identifiers, and natural-language titles with report-scoped aliases. It still retains exact dates, models, token values, relationships, and replay sequences. This is **pseudonymization, not guaranteed anonymity**.

Before sharing a report:

1. prefer `tokens dashboard --anonymize`;
2. restrict the date range;
3. inspect the generated file or screenshot;
4. search for usernames, customer names, repository names, and custom model labels;
5. never attach raw logs to a public issue.

Read the full [data and privacy guide](https://lingxi-fur.github.io/tokens/data-and-privacy.html).

## Design principles

- **Local-first:** no account, hosted backend, telemetry, LAN binding, or external runtime network access.
- **Inspectable:** plain Python data processing, a loopback-only standard-library server, and a self-contained vanilla JavaScript dashboard.
- **Portable:** Python 3.9+ on macOS, Linux, and Windows.
- **Progressive detail:** core usage questions first; optional labs stay out of the primary path.
- **Explicit semantics:** cache reads are not claimed as confirmed monetary savings, and local achievements are not global rankings.
- **Accessible interaction:** keyboard paths, visible focus, reduced-motion support, and semantic controls.

## Development

```bash
# Run the full test suite
PYTHONPATH=src python3 -m unittest discover -s tests -v

# Syntax checks
python3 -m compileall -q src tests
node --check src/tokens_cli/dashboard_assets/dashboard.js

# Synthetic benchmark
PYTHONPATH=src python3 benchmarks/bench_pipeline.py --sizes 50000
```

The current suite covers readers, caching, packaging paths, CLI validation, pseudonymization, dashboard contracts, documentation links, accessibility, and privacy assertions.

## Contributing and security

Bug reports and focused pull requests are welcome. Start with [CONTRIBUTING.md](https://github.com/LingXi-fur/tokens/blob/v0.2.0/CONTRIBUTING.md), and do not include raw logs or generated dashboards that contain private data.

For vulnerabilities or privacy issues, follow [SECURITY.md](https://github.com/LingXi-fur/tokens/blob/v0.2.0/SECURITY.md) rather than opening a public issue.

## License

[MIT](https://github.com/LingXi-fur/tokens/blob/v0.2.0/LICENSE)
