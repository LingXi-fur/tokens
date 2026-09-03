# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## [Unreleased]

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
