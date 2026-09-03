# Contributing to tokens

Thanks for helping improve tokens.

## Before opening a change

- Search existing issues and pull requests.
- Keep changes focused; avoid unrelated refactors.
- Never include real CLI logs, generated dashboards, local paths, session IDs, credentials, or the local `out/` directory.
- Use synthetic records in tests and screenshots.

## Local setup

Python 3.9 or newer is required. The core runtime uses the Python standard library; Windows installs the data-only `tzdata` package for IANA timezone support.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests
```

Check the JavaScript assets when changing either interface:

```bash
node --check src/tokens_cli/dashboard_assets/dashboard.js
node --check docs/assets/site.js
```

## Pull requests

Describe the user-facing reason for the change and include a short test plan. For dashboard changes, verify desktop and mobile layouts, keyboard operation, reduced motion, empty states, and both themes. Keep privacy claims precise: `--anonymize` pseudonymizes identifiers but does not guarantee anonymity.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
