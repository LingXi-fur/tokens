# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## [Unreleased]

### Added

- Source-first launch paths for repository clones, including `./run`, `PYTHONPATH=src python -m tokens_cli`, and editable installs.
- Release contracts for launchers, package assets, synthetic previews, exports, model sorting, and stable Dashboard colors.

### Changed

- Public documentation now treats cloning the repository as the verified first-run path instead of advertising an unverified package-index release.
- Terminal and Dashboard model ordering now follows the current user's token totals, with model-name tie-breaking.
- Dashboard model identity uses independently validated light and dark palettes; colors stay stable across ranking, filtering, input order, and refresh, while excess categories fold into `Other`.
- Claude Code Router rules are read locally and conservatively only for plain Claude request aliases; router backends, Gemini models, and Codex models remain historical facts.

### Fixed

- Unsupported Router return expressions can no longer leak pending aliases into a later rule.
- CSV and Markdown Dashboard exports preserve delimiters, quotes, pipes, and multiline values.
- Manual dark mode now uses the same complete theme token set as system dark mode.
- Lazy Dashboard visualizations no longer fail as silent blank cards; Token Flow rendering now exposes a retryable error state and recovers after module or renderer failures.
- Lazy Dashboard placeholders now use bilingual DOM content instead of untranslated CSS-generated text.
- Token Flow preserves full node names in SVG tooltips, translates empty states and region labels, and exposes its horizontally scrollable canvas as a keyboard-focusable region.
- Lazy-render retries now restore keyboard focus to the refreshed module or the replacement retry control.

### Security

- Privacy documentation now states that Router files are read as local text, never executed or uploaded.
- `--anonymize` is documented as pseudonymization: model names and Router-resolved backend names remain visible and may reveal local configuration semantics.
- Public preview assets use synthetic data and contain no local identifiers.

## [0.2.0] - 2026-09-03

### Added

- Installable `ai-cli-tokens` package with the `tokens` command.
- Cross-platform `tokens doctor`, browser opening, output selection, and IANA timezone selection.
- English-first documentation with a complete Chinese entry and offline GitHub Pages site.
- Data Trail, Signal Lens, Exactness Key, hold-to-compare, Token Almanac, project analysis, session replay, and Context Reuse River.
- Report-scoped pseudonymization with `tokens dashboard --anonymize`.
- Cross-platform CI and tag-driven PyPI/GitHub release automation.

### Changed

- Reports default to `./out`; the derivative cache uses the platform user-cache directory.
- Dashboard assets are packaged under `src/tokens_cli/dashboard_assets`.
- Cache writes are atomic and use private file permissions where supported.
- Live Dashboard checks default to five minutes and can be changed or paused from the page.
- The README and documentation provide a concise first-run path for installed and source users.

### Fixed

- Windows installs include IANA timezone data, and cross-platform permission tests respect Windows filesystem semantics.

### Security

- Diagnostics avoid parsing message contents and report only source metadata and counts.
- Documentation states that local-first reports can remain sensitive and that pseudonymization is not guaranteed anonymity.

[Unreleased]: https://github.com/LingXi-fur/tokens/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/LingXi-fur/tokens/releases/tag/v0.2.0
