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
node --check src/tokens_cli/dashboard_assets/dashboard.js
node --check docs/assets/site.js
```

## Local artifacts and cleanup

- Keep generated reports in ignored output directories and use only synthetic data for previews, tests, and screenshots. Keep temporary test evidence outside the checkout; never include private output in a package or site build.
- Python bytecode, `build/`, and packaging metadata are rebuildable, but check that no running service or editable installation depends on a target before removing it. Set `PYTHONDONTWRITEBYTECODE=1` for maintenance checks that should not recreate bytecode.
- Remove registered Git worktrees only after checking tracked and untracked changes, commit ancestry, locks, and active ownership. Use `git worktree remove` without `--force`; keep branches and uncertain worktrees.
- Do not delete real `out/` reports, backups, or historical evidence based on age or filenames. Use a reviewed, exact cleanup list and stop when permissions or ownership are unclear.

## Pull requests

Describe the user-facing reason for the change and include a short test plan. For dashboard changes, verify desktop and mobile layouts, keyboard operation, reduced motion, empty states, and both themes. Keep privacy claims precise: `--anonymize` pseudonymizes identifiers but does not guarantee anonymity.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
