# Contributing to tokens

Thanks for helping improve tokens.

## Before opening a change

- Search existing issues and pull requests.
- Keep changes focused; avoid unrelated refactors.
- Never include real CLI logs, generated dashboards, local paths, session IDs, credentials, or the local `out/` directory.
- Use synthetic records in tests and screenshots.

## Local setup

Python 3.9 or newer is required. The core runtime uses the Python standard library; Windows installs the data-only `tzdata` package for IANA timezone support. Running the full test suite and dashboard JavaScript checks requires Node.js 22 or newer.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests
```

Check the JavaScript assets when changing either interface (requires Node.js 22 or newer):

```bash
node --check src/tokens_cli/dashboard_assets/cost_core.js
node --check src/tokens_cli/dashboard_assets/calendar_core.js
node --check src/tokens_cli/dashboard_assets/budget_core.js
node --check src/tokens_cli/dashboard_assets/dashboard.js
node --check docs/assets/site.js
```

The calendar core contains pure derivations only. It receives the dashboard's shared date and safe-integer helpers; keep DOM, storage, current time, and view state in the dashboard. Tests load the production core instead of copying its functions.

The budget core reuses CostCore pricing and CalendarCore dates. Keep budget settings in browser-local `tk-budget-v1` storage, separate by month and currency; loading must not write or repair stored values. Never add budget amounts to snapshot payloads, URLs, exports, or share cards. Synthetic browser tests cover these boundaries; a passing layout check is not visual approval.

## Local usage collection checks

Run `python3 scripts/verify_dashboard.py logic` and `python3 scripts/verify_dashboard.py browser` for isolated synthetic maintenance checks. The runner isolates HOME, cache, cwd and temporary files, blocks protected Python reads, and verifies temporary Chromium profiles and mock-keychain flags. It is an application guard, not an OS sandbox. A skipped check leaves the strict result failed.

Codex regressions live in `tests/test_codex_usage.py`. Keep new/legacy mirror checks, distinct equal-usage responses, archive duplicates, safe-file changes, large discarded content, and budget failures covered. Archive integration tests use an already installed `zstd`; do not download tools or inspect real user logs during tests. Claude's default projection profile must remain unchanged. Preserve legacy display-value compatibility while marking invalid billing evidence uncertain.

Dashboard coverage text must distinguish locally recorded Claude Code / Claude App Code and Codex usage from unknown ordinary Claude chat / Cowork usage. Do not replace unknown tokens with zero, convert subscription utilization into tokens, or claim account-wide completeness. Do not embed event IDs or application-session indexes in exports.

## Local artifacts and cleanup

- Keep generated reports in ignored output directories and use only synthetic data for previews, tests, and screenshots. Keep temporary test evidence outside the checkout; never include private output in a package or site build.
- Python bytecode, `build/`, and packaging metadata are rebuildable, but check that no running service or editable installation depends on a target before removing it. Set `PYTHONDONTWRITEBYTECODE=1` for maintenance checks that should not recreate bytecode.
- Remove registered Git worktrees only after checking tracked and untracked changes, commit ancestry, locks, and active ownership. Use `git worktree remove` without `--force`; keep branches and uncertain worktrees.
- Do not delete real `out/` reports, backups, or historical evidence based on age or filenames. Use a reviewed, exact cleanup list and stop when permissions or ownership are unclear.

## Pull requests

Describe the user-facing reason for the change and include a short test plan. For dashboard changes, verify desktop and mobile layouts, keyboard operation, reduced motion, empty states, and both themes. Keep privacy claims precise: `--anonymize` pseudonymizes identifiers but does not guarantee anonymity.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
