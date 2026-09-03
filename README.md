<div align="center">
  <img src="https://raw.githubusercontent.com/LingXi-fur/tokens/main/docs/favicon.svg" width="76" height="76" alt="tokens logo">

# tokens

**See where your AI coding tokens go — without sending your logs anywhere.**

Turn the Claude Code, Gemini CLI, and Codex logs already on your computer into a terminal report, a live local dashboard, or one self-contained offline HTML file.

[![PyPI](https://img.shields.io/pypi/v/ai-cli-tokens?color=5b8def)](https://pypi.org/project/ai-cli-tokens/)
[![Python](https://img.shields.io/pypi/pyversions/ai-cli-tokens)](https://pypi.org/project/ai-cli-tokens/)
[![CI](https://github.com/LingXi-fur/tokens/actions/workflows/ci.yml/badge.svg)](https://github.com/LingXi-fur/tokens/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-f59e0b)](https://github.com/LingXi-fur/tokens/blob/main/LICENSE)
[![Privacy](https://img.shields.io/badge/privacy-local--first-a78bfa)](#privacy)

[Install](#install) · [Documentation](https://lingxi-fur.github.io/tokens/) · [Dashboard guide](https://lingxi-fur.github.io/tokens/dashboard.html) · [中文说明](https://github.com/LingXi-fur/tokens/blob/main/README.zh-CN.md)

</div>

![Synthetic tokens dashboard preview](https://raw.githubusercontent.com/LingXi-fur/tokens/main/docs/assets/readme-preview.svg)

> This preview uses synthetic data. `tokens` never uploads your logs, but a generated report can contain sensitive local metadata. Read [Privacy](#privacy) before sharing one.

## Why use tokens?

AI coding tools keep useful usage records locally, but each tool stores and counts them differently. `tokens` gives you one inspectable view across them:

- **One dashboard for Claude Code, Gemini CLI, and Codex**
- **Daily, weekly, and monthly trends** by model and source
- **Projects, sessions, context composition, and replay** where the source logs support them
- **Live local mode** that updates the page without a full reload
- **Portable offline snapshots** with data, CSS, and JavaScript in one HTML file
- **No account, telemetry, hosted backend, database, CDN, or log upload**

The core pipeline and loopback server use the Python standard library. Windows installs also include the data-only `tzdata` package so IANA timezones work consistently.

## Install

### Recommended: pipx

[`pipx`](https://pipx.pypa.io/) installs the command in an isolated environment and makes it available globally:

```bash
pipx install ai-cli-tokens
tokens doctor
tokens serve --open
```

The package is named `ai-cli-tokens`; the installed command is simply `tokens`.

<details>
<summary>Other installation options</summary>

With pip:

```bash
python -m pip install --user ai-cli-tokens
tokens --version
```

From source:

```bash
git clone https://github.com/LingXi-fur/tokens.git
cd tokens
./run doctor
./run serve --open
```

On Windows, the source entry can be run with:

```powershell
python -m tokens_cli doctor
```

Set `PYTHONPATH=src` first when running directly from a source checkout without installing it.

</details>

Requirements: Python 3.9 or newer on macOS, Linux, or Windows, plus local logs from at least one supported AI coding CLI.

## Start in 30 seconds

```bash
# 1. Safely check which local logs are available
tokens doctor

# 2. Open the live, loopback-only dashboard
tokens serve --open

# 3. Or create one offline file you can archive
tokens dashboard --open
```

`tokens doctor` checks paths, candidate file counts, timezone, output, and cache permissions. It does not parse message contents or print project and session identifiers.

The live dashboard binds only to `127.0.0.1`. It checks for local log changes every five minutes by default; the page can switch between 1, 5, 15, or 30 minutes, or pause refresh. Unchanged files are not reparsed or retransmitted.

## Live dashboard or offline snapshot?

| Goal | Command | Behavior |
|---|---|---|
| Quick terminal summary | `tokens day` | Last 14 days in the terminal |
| Keep a dashboard open | `tokens serve --open` | Loopback-only service with in-page updates |
| Save an offline archive | `tokens dashboard --open` | Self-contained generation-time snapshot |
| Prepare a safer sharing copy | `tokens dashboard --anonymize --open` | Pseudonymizes selected identifiers |

Reports are written to `./out` by default. Use `--output DIR` to choose another location.

## What can I explore?

Start with total usage, trends, model mix, sources, projects, and sessions. When you want more detail, the dashboard includes:

- **Data Trail** to move from a selected period toward project, session, or context evidence without silently changing global filters
- **Signal Lens** and **Exactness Key** for temporary inspection and exact values
- **Context Reuse River** for Fresh Input, Output, Cache Read, Cache Write, and Other
- **Project Lens** and session replay, retaining at most the most recent 200 turns per session
- **Token Almanac**, achievements, activity rhythm, and a local Furry Token companion

Data Trail state remains in page memory and is not written to the URL or `localStorage`. Projects and sessions remain parallel aggregates rather than being automatically paired. A fixed period comparison may appear in the URL as `compare=1`; project/session IDs and exact token details do not.

Token change describes usage, not productivity or code quality. Cache Read is cached-token volume, not guaranteed monetary savings.

## Supported sources

| Source | Default local path | Project data | Session data | Accounting note |
|---|---|---:|---:|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | Yes | Yes | Total is input + output + cache read + cache write. |
| Gemini CLI | `~/.gemini/tmp/*/chats/session-*.json` | Usually no | Yes | Uses the source `tokens.total` when available. |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | Usually no | Usually no | Cached input is already included in input and is not added twice. |

Claude is the default source. Repeat `--source` to combine tools:

```bash
tokens serve \
  --source claude \
  --source gemini \
  --source codex \
  --open
```

Different tools do not expose identical token semantics. `tokens` preserves each source's reported total instead of pretending the values are perfectly interchangeable.

## CLI essentials

```text
tokens [day|week|month|all|dashboard|serve|doctor] [options]
```

| Option | Purpose |
|---|---|
| `--source claude\|gemini\|codex` | Select a source; repeat to combine sources. |
| `--since YYYY-MM-DD` / `--until YYYY-MM-DD` | Limit the inclusive report range. |
| `--timezone AREA/CITY` | Override the detected system timezone. |
| `--output DIR` | Choose the report directory; default is `./out`. |
| `--html` | Add a static HTML report to terminal modes. |
| `--anonymize` | Pseudonymize identifiers in dashboard or live mode. |
| `--interval SECONDS` | Set the initial live check interval; minimum 1, default 300. |
| `--port PORT` | Set the loopback port; default 8765, or 0 for an available port. |
| `--open` | Open the generated file or local URL in the default browser. |
| `--no-cache` | Re-read all selected log files. |

See the [complete CLI reference](https://lingxi-fur.github.io/tokens/cli.html).

## Privacy

`tokens` reads local files and performs its analysis locally. Offline snapshots make no network requests. Live mode talks only to its same-origin service on `127.0.0.1` and does not provide a LAN binding option.

A normal dashboard may still contain:

- project paths and working directories
- session identifiers and locally derived titles
- exact dates, models, token values, and per-turn token sequences
- behavioral patterns that could identify a person or organization

`--anonymize` replaces project paths, session identifiers, and natural-language titles with report-scoped aliases. Exact dates, models, token values, relationships, and replay sequences remain. This is **pseudonymization, not guaranteed anonymity**.

Before sharing a report:

1. use `tokens dashboard --anonymize`
2. restrict the date range
3. inspect the generated file or screenshot
4. search for usernames, customer names, repository names, and custom model labels
5. never attach raw logs to a public issue

Read the full [data and privacy guide](https://lingxi-fur.github.io/tokens/data-and-privacy.html).

## Troubleshooting

**No logs found?** Run `tokens doctor`. If Claude is not the tool you use, try `tokens day --source gemini` or `tokens day --source codex`.

**Dashboard numbers do not change?** `tokens dashboard` creates an offline snapshot. Use `tokens serve --open` for live updates.

**The browser did not open?** The command still prints the generated path or local URL. Open it manually.

**Command not found after pip install?** Prefer `pipx`, or ensure your Python user scripts directory is on `PATH`.

More answers are in the [FAQ](https://lingxi-fur.github.io/tokens/faq.html).

## Update or uninstall

```bash
pipx upgrade ai-cli-tokens
pipx uninstall ai-cli-tokens
```

Generated reports in `./out` and the platform user cache are local files and are not removed automatically by package uninstall.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall -q src tests
node --check src/tokens_cli/dashboard_assets/dashboard.js
```

The suite covers readers, caching, packaging, CLI validation, pseudonymization, dashboard contracts, documentation links, accessibility, privacy assertions, and loopback live updates.

## Contributing and security

Bug reports and focused pull requests are welcome. Start with [CONTRIBUTING.md](https://github.com/LingXi-fur/tokens/blob/main/CONTRIBUTING.md), and use synthetic records when reproducing a problem.

For vulnerabilities or privacy issues, follow [SECURITY.md](https://github.com/LingXi-fur/tokens/blob/main/SECURITY.md) rather than opening a public issue. Never include raw logs or an unreviewed generated dashboard.

If `tokens` is useful to you, a star helps other local-first AI tool users find it. Real bug reports and platform feedback are even more valuable.

## License

[MIT](https://github.com/LingXi-fur/tokens/blob/main/LICENSE)
