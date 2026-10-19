# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## [Unreleased]

> 本机 0.3.0 候选（未正式发布）。This section collects the local 0.3.0 release-candidate content. It has **not been publicly released**: no public release date exists, and no verified 0.3.0 package-index release is claimed. The candidate wheel, if built, is a local offline artifact only.

### Added

- Reporting-timezone date scopes for all records, today, yesterday, the last seven calendar days, and a specified day. Core usage views and exports share the selected range; report-wide and generation-time views retain explicit scope labels. When a reporting calendar cannot be resolved reliably, relative dates use the labeled report-generation day instead of the browser's local timezone.
- Daily model usage details and a GLM comparison shortcut using only recorded identities. Token totals and logged calls remain separate from trusted billing components; missing labels, incomplete components, and dates outside recorded coverage must not be interpreted as proof of zero actual usage. The shortcut does not relabel historical records or infer absent Flash usage.
- Daily model usage CSV for the selected dates and model filters, including trusted input/output/cache components, nonzero thoughts, component coverage, and token/call precision. Missing values stay blank, partial components remain known subtotals, and unsafe source counts are explicitly marked rather than claimed as exact. Downloads stay local and use the shared CSV escaping.
- Cost ledger "restore official reference" for a single model in the price editor. The control appears only when the draft is USD with the reference layer on, the model is not hidden, the exact model name hits a built-in reference, and a saved override exists for that source/model (all-empty, an explicit zero, or a note-only entry all count as overrides). Confirming clears that entry's unit prices and note only and leaves other models untouched; cancelling changes nothing; closing the editor without saving persists nothing. Re-entering a price afterwards creates a normal override again.
- Cost ledger CSV export. A click-only local download with no fetch and no new endpoint, it reuses the current granularity, selection, model filters, currency, and effective prices, and exports every entry regardless of pagination. Rows carry row type, range, source/model, currency, pricing status, the five billing components with tokens, effective unit prices, and estimated amounts; sessions, titles, project paths, and notes are never included. Reference-priced, manually priced, pending, and hidden rows stay distinct; unknown stays blank while an explicit zero means free. Amounts are computed with the 10^12-scaled BigInt pipeline into exact decimals (at most 12 fractional digits, trailing zeros trimmed), never through Number or display rounding.
- Cost CSV summary records for what the entry table cannot show: unknown calls/tokens, invalid rows, `totalIncomplete`, the priced subtotal, and the full-estimate flag. With no priceable amount the amount stays blank instead of inventing a complete total, and a no-records state is explicit.
- Shared CSV cell escaping for quotes, commas, CR, and LF plus dangerous formula prefixes (`=`, `+`, `-`, `@`, including after leading whitespace or control characters), applied to the new cost CSV and back-ported to the existing trend CSV. Markdown export keeps its separate escaping. UTF-8 with BOM, the existing `downloadBlob`, and a fixed safe filename remain.
- Release-candidate documentation: a local 0.3.0 install path (offline wheel or source checkout) and the candidate release checklist under `docs/release-candidate-checklist.md`, plus the monthly-budget design specification under `docs/monthly-budget-design.md` (specification only; no budget code or storage key this round).
- Local model cost estimates with browser-only channel-price settings, explicit unpriced and uncertain coverage, and independent billing components without changing existing usage statistics.
- Built-in official USD reference prices for ten exact model names (OpenAI Standard short-context ≤272K, DeepSeek peak-time baseline, and Z.ai international rates, which are not the domestic Zhipu equivalent), shown by default with no local settings, overridable per source/model by manual prices, and toggled by a "Use official reference price (USD)" switch. The page never contacts providers, and private manual prices stay local under the existing `tk-cost-v1` key.
- Demo-first README paths, public share metadata, sitemap discovery, and package project metadata for the zero-install synthetic Dashboard.
- Interactive equal-length A/B trend comparison and peak-period profile using logged model and backend identities.
- `--lang en|zh` for terminal and static HTML reports; Markdown export follows Dashboard language.

### Changed

- Live log scans run in a single background worker; page and snapshot requests read published in-memory data without waiting for parsing or aggregation.
- `--interval` controls background scanning. Browser checks default to at most one minute, check sooner during preparation, and can be changed or paused independently.
- Token Flow is redesigned as Token destinations: a project/model overview beside readable session cards, with a stacked mobile layout and the existing seven-plus-`Other` palette.
- Model buttons filter the session list locally; project actions open recorded evidence without inferring project-to-session pairings.
- Sessions paginate twelve per page with exact off-page usage, an accessible full-list table, and separate replay actions.
- SVG export identifies the current page, scope, model filters, and theme instead of implying that it includes every session.
- Cost-ledger documentation limits the "not embedded in reports" statement to manually entered private prices; built-in public reference prices ship with the page assets.

### Fixed

- Record caches now bind parsed dates to the reporting timezone. Changing timezone or loading a cache without that marker reparses source records instead of reusing stale calendar dates; an unverifiable system-local timezone conservatively reparses. Historical source files and model attribution are not changed.
- `glm-5.3` and `glm-5.3-flash`, when present under those exact recorded names, retain separate filter identities even when model capacity overflows. They share the existing seven-identity capacity with the latest backend and usage-ranked models; no historical records are relabeled and no absent Flash usage is inferred.
- The full session table retains an independent replay button for every row, including sessions outside the current card page.
- Report-level source metadata retains the requested sources instead of being overwritten by the last session's sources, including when another source has records without session IDs.
- Model filters now show the names and token totals inside `Other` without requiring an expanded chart legend. These names follow the current period and share the `Other` color and group filter; they are not independent model filters. Anonymous reports do not invent or expose missing names.
- Slow local scans no longer block snapshot requests until the browser's network timeout. Initial preparation is explicit, and failed background scans preserve the last successful data with its check time instead of reporting a network disconnection.
- Dashboard overflow selects the seven major models by all-record token totals, retaining a seat for the most recently active backend, instead of letting early low-usage identities hide newer major backends in `Other`. Selected identities keep first-seen palette order and are independent of the displayed date range; colors may change when the retained identity set changes.
- Achievement previews open their details directly, and the archive lists all unlocked achievements with pagination while keeping locked secret achievements private.
- Long backend names wrap inside model legend buttons instead of overflowing narrow mobile layouts.
- Session titles wrap instead of being truncated in the visualization. Conservative local cleaning rejects continuation summaries and system boilerplate; missing titles are explicitly unnamed and accompanied by available recorded context, without AI summarization or uploads.
- Session background metadata is labeled as report-scoped context, not a precise project pairing for a locally filtered view.

## [0.2.0] - 2026-09-21

### Added

- Installable `ai-cli-tokens` package with the `tokens` command.
- Source-first launch paths for repository clones, including `./run`, `PYTHONPATH=src python -m tokens_cli`, and editable installs.
- Cross-platform `tokens doctor`, browser opening, output selection, and IANA timezone selection.
- English-first documentation with a complete Chinese entry and offline GitHub Pages site.
- Data Trail, Signal Lens, Exactness Key, hold-to-compare, Token Almanac, project analysis, session replay, Context Reuse River, and Token Flow.
- Report-scoped pseudonymization with `tokens dashboard --anonymize`.
- Cross-platform CI and tag-driven GitHub release automation; package-index publishing remains disabled until separately authorized and verified.
- Release contracts for launchers, package assets, synthetic previews, exports, model sorting, and stable Dashboard colors.

### Changed

- Public documentation treats cloning the repository as the verified first-run path instead of advertising an unverified package-index release.
- Reports default to `./out`; the derivative cache uses the platform user-cache directory.
- Dashboard assets are packaged under `src/tokens_cli/dashboard_assets`.
- Live Dashboard checks default to five minutes and can be changed or paused from the page.
- Public/default display formatting preserves logged model and Router backend names verbatim instead of applying maintainer-specific aliases.
- Terminal and Dashboard model ordering follows the current user's token totals, with model-name tie-breaking.
- Dashboard model identity uses independently validated light and dark palettes; colors stay stable across ranking, filtering, input order, and refresh, while excess categories fold into `Other`.
- Claude Code Router rules are read locally and conservatively only for plain Claude request aliases; router backends, Gemini models, and Codex models remain historical facts.

### Fixed

- Windows installs include IANA timezone data; the Dashboard export subprocess test decodes Node output as UTF-8; temporary-home checks follow Windows profile semantics.
- Unsupported Router return expressions can no longer leak pending aliases into a later rule.
- CSV and Markdown Dashboard exports preserve delimiters, quotes, pipes, and multiline values.
- Manual dark mode uses the same complete theme token set as system dark mode.
- Lazy Dashboard visualizations no longer fail as silent blank cards; Token Flow rendering exposes a retryable error state and recovers after module or renderer failures.
- Lazy Dashboard placeholders use bilingual DOM content instead of untranslated CSS-generated text.
- Token Flow preserves full node names in SVG tooltips, translates empty states and region labels, and exposes its horizontally scrollable canvas as a keyboard-focusable region.
- Lazy-render retries restore keyboard focus to the refreshed module or replacement retry control.

### Security

- Cache and generated Dashboard writes are atomic and use private file permissions where supported.
- Command-palette entries render untrusted logged model names as text instead of HTML.
- Diagnostics avoid parsing message contents and report only source metadata and counts.
- Privacy documentation states that Router files are read as local text, never executed or uploaded.
- `--anonymize` is documented as pseudonymization: model names and Router-resolved backend names remain visible and may reveal local configuration semantics.
- Documentation states that local-first reports can remain sensitive and that pseudonymization is not guaranteed anonymity.
- Public preview assets use synthetic data and contain no local identifiers.

[Unreleased]: https://github.com/LingXi-fur/tokens/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/LingXi-fur/tokens/releases/tag/v0.2.0
