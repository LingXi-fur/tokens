# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## [Unreleased]

> 本机 0.3.0 候选（未正式发布）。This section collects the local 0.3.0 release-candidate content. It has **not been publicly released**: no public release date exists, and no verified 0.3.0 package-index release is claimed. The candidate wheel, if built, is a local offline artifact only.

### Added

- A lightweight date browser inside daily model usage: seven consecutive report dates, recorded-count previews, and an on-demand month picker. Previewing or browsing a month does not change statistics; choosing a date uses the existing specified-day details and exports. Missing records and unsafe counts are not presented as exact zero usage. Includes daily-model navigation and command-palette entry points, keyboard navigation, and documented design references.
- Reporting-timezone date scopes for all records, today, yesterday, the last seven calendar days, and a specified day. Core usage views and exports share the selected range; report-wide and generation-time views retain explicit scope labels. When a reporting calendar cannot be resolved reliably, relative dates use the labeled report-generation day instead of the browser's local timezone.
- Daily model usage details and a GLM comparison shortcut using only recorded identities. Token totals and logged calls remain separate from trusted billing components; missing labels, incomplete components, and dates outside recorded coverage must not be interpreted as proof of zero actual usage. The shortcut does not relabel historical records or infer absent Flash usage.
- Daily model usage CSV for the selected dates and model filters, including trusted input/output/cache components, nonzero thoughts, component coverage, and token/call precision. Missing values stay blank, partial components remain known subtotals, and unsafe source counts are explicitly marked rather than claimed as exact. Downloads stay local and use the shared CSV escaping.
- Cost ledger "restore official reference" for a single model in the price editor. The control appears only when the draft is USD with the reference layer on, the model is not hidden, the exact model name hits a built-in reference, and a saved override exists for that source/model (all-empty, an explicit zero, or a note-only entry all count as overrides). Confirming clears that entry's unit prices and note only and leaves other models untouched; cancelling changes nothing; closing the editor without saving persists nothing. Re-entering a price afterwards creates a normal override again.
- Cost ledger CSV export. A click-only local download with no fetch and no new endpoint, it reuses the current granularity, selection, model filters, currency, and effective prices, and exports every entry regardless of pagination. Rows carry row type, range, source/model, currency, pricing status, the five billing components with tokens, effective unit prices, and estimated amounts; sessions, titles, project paths, and notes are never included. Reference-priced, manually priced, pending, and hidden rows stay distinct; unknown stays blank while an explicit zero means free. Amounts are computed with the 10^12-scaled BigInt pipeline into exact decimals (at most 12 fractional digits, trailing zeros trimmed), never through Number or display rounding.
- Cost CSV summary records for what the entry table cannot show: unknown calls/tokens, invalid rows, `totalIncomplete`, the priced subtotal, and the full-estimate flag. With no priceable amount the amount stays blank instead of inventing a complete total, and a no-records state is explicit.
- Shared CSV cell escaping for quotes, commas, CR, and LF plus dangerous formula prefixes (`=`, `+`, `-`, `@`, including after leading whitespace or control characters), applied to the new cost CSV and back-ported to the existing trend CSV. Markdown export keeps its separate escaping. UTF-8 with BOM, the existing `downloadBlob`, and a fixed safe filename remain.
- Release-candidate documentation: a local 0.3.0 install path (offline wheel or source checkout) and the candidate release checklist under `docs/release-candidate-checklist.md`, plus the monthly-budget design specification under `docs/monthly-budget-design.md` (specification only; no budget code or storage key this round).
- Local model cost estimates with browser-only channel-price settings, explicit unpriced and uncertain coverage, and independent billing components without changing existing usage statistics.
- Built-in official USD reference prices for twenty-five exact model names (OpenAI Standard short-context ≤272K, DeepSeek peak-time baseline, and Z.ai international rates, which are not the domestic Zhipu equivalent), shown by default with no local settings, overridable per source/model by manual prices, and toggled by a "Use official reference price (USD)" switch. The page never contacts providers, and private manual prices stay local under the existing `tk-cost-v1` key.
- Demo-first README paths, public share metadata, sitemap discovery, and package project metadata for the zero-install synthetic Dashboard.
- Interactive equal-length A/B trend comparison and peak-period profile using logged model and backend identities.
- `--lang en|zh` for terminal and static HTML reports; Markdown export follows Dashboard language.
- Claude records keep the pre-routing request model name beside the router-resolved backend name (`request_model`). It is informational only: counting, deduplication, and cost attribution continue to use the resolved backend exactly as before, and Codex/Gemini records are untouched. The dashboard shows a request-name column in the daily model table plus a collapsed alias→backend mapping panel; anonymized exports omit request names entirely.
- A "Route map" collapsed panel in daily model usage: an SVG flow diagram of request names to resolved backends, with line width proportional to tokens. Hovering a flow highlights it; clicking a backend node filters to that model. The panel hides entirely when no alias flows exist (same-name records or anonymized exports) and is informational only, touching no statistics.
- Four more built-in reference prices verified from official pages on 2026-11-06: `gpt-6.1-terra`, `gpt-6-astra`, `gpt-5.5` (OpenAI Standard short-context), and `glm-5.3-flash` (Z.ai international), all using the same Standard short-context tier as the existing entries.
- Eleven more built-in reference prices from the local freetest proxy price list snapshot (2026-11-06, USD per million tokens, no public page): Claude 5.5/5/4.8/4.7/4.6 tiers, `gpt-6-luna`, `deepseek-v4.1-flash`, and `kimi-k3`. The price list publishes input/output only, so cached-input and cache-write components stay pending rather than guessed; the vendor renders without a source link. **Superseded the same day**: all eleven entries now use each model's official publisher rates instead — Anthropic Claude lineup (cache reads at the official multipliers, cache writes at the 5-minute tier), OpenAI `gpt-6-luna`, DeepSeek `deepseek-v4.1-flash` (served as the official `deepseek-flash` peak-hour baseline), and Moonshot `kimi-k3`; the freetest proxy vendor was removed, and two official vendors (Anthropic, Moonshot AI) with source links were added. GLM entries record Z.ai's limited-time-free cache writes as zero instead of pending, and a bare provider-prefixed record (`zhipu/glm-5.3-flash`) is priced as its own exact entry at the same backend's official rates.
- CCR hex aliases resolve to their embedded backend: the `anthropic/claude-ccr-h<hex>` request name written into Claude settings decodes to the real backend it encodes (for example `zhipu/glm-5.3-flash`) instead of overflowing into the Other bucket. The decoded backend name drops its provider prefix (`zhipu/glm-5.3-flash` is recorded as `glm-5.3-flash`) so the hex-decoded identity merges with the historical bare router name instead of splitting into two identities and overflowing the identity capacity. The encoded original is kept as the request name; decoding is deterministic and needs no router file.
- A dominant-model shift badge on the overview's top-model card: when the current period's leading model differs from the previous period's over the same comparable window used by the period-over-period delta, the card shows a small `主力换人 X → Y` pill. Informational only — statistics, filters, and exports are unchanged, and the badge hides when both periods share a leader or no comparable window exists.
- A "copy text summary" action in the current-view popover: one click copies a short readable summary of the current scope (granularity, models, range, total tokens, calls, top model, and the period-over-period delta when available) to the clipboard for pasting into notes or messages. Local only, using the existing clipboard fallback.
- The overview top-model card now shows the leading model's share of the current total token usage beside its name (e.g. `66.7%`), so the dominant model's weight reads at a glance without opening the per-model trend. The share also renders as a thin progress bar under the label.
- The overview period-over-period delta exposes the exact prior and current totals in a hover title (e.g. `上期 250 → 本期 200 tk`), complementing the percentage label; the one-line `periodDelta` forwarder was folded into `renderDelta`. The delta also flashes green/red when its value changes (rising vs falling), matching the KPI number flash and respecting reduced motion.

### Changed

- Dashboard visual redesign: neutral zinc surfaces with a single blue accent, hairline borders, 12px radii, and a system font stack with tabular numerals replace the glass panels, ambient color blobs, gradient headings, and breathing KPI gradient. The section dock is a full-width translucent bar pinned to the top; buttons, pills, and the granularity/date-range switches share one quiet 28px style, with date presets as a segmented control. KPI tiles sit on a 7-column grid so the top-model tile shows full model names; trend bars drop the grey track and peak glow, narrow to 40px, and separate stacked segments with a surface-colored hairline. Decorative card gradients (almanac, achievements, provenance, work modes, reuse, data trail, lazy placeholders) are now flat; semantic fills (badge tiers, calendar no-record hatching, share cards) are unchanged. Light-theme faint text darkened to `#6b6b74` so it clears WCAG AA on both light surfaces. 仪表盘视觉重构：中性表面、单一强调色、细线边框，去除玻璃、光斑与渐变装饰；导航条吸顶全宽，控件统一，KPI 7 栏网格不再截断模型名，趋势柱更细并以表面色细线分隔堆叠段。
- Period-over-period comparison math moved into a new pure `period_core.js` (`PeriodCore`), inlined before `dashboard.js` like the cost, calendar, and budget cores. It owns day/week/month expansion, the whole / same-point / partial window choice, percent change, delta attribution ordering, and the dominant-model shift; the KPI delta, shift badge, attribution panel, and copied view summary now share one implementation instead of repeating the percent math. 环比计算抽成纯核心 `period_core.js`，KPI 环比、主力换人徽章、归因面板与视图摘要共用同一实现。
- KPI headline numbers flash on change — rising values glow green and falling values glow red for a moment — so a refresh reads at a glance without consulting the delta text. Respects the reduced-motion and low-motion settings.
- A fixed scroll-progress bar at the very top fills with the theme gradient as the page scrolls, giving a persistent sense of position across the long dashboard; it is pointer-transparent and sits above the ambient canvas but below modals.
- The cost ledger and price-editor pagers now show the total entry count beside the page position (e.g. `1 / 2 · 共 14 条` / `1 / 2 · 14 entries`), matching the session pager idiom.
- The GLM daily-comparison table starts collapsed inside a `<details>` with a live row count in the summary, like the daily-model and trend tables; opening it still shows the per-day rows.
- Removed the `displayNumber` one-line forwarder so the KPI path calls `human` directly.
- The section dock no longer carries a hard-coded `SECTION_LINKS` list duplicated from the template; its scroll-spy observers are generated from the dock buttons' own `data-target` attributes, so adding or removing a section only means editing the template (this also restores scroll highlighting for the previously-missing scope section).
- Dashboard visual polish: the primary card gains a 1px inner top highlight for a more tactile glass feel, light-theme shadows deepen for clearer layering, the dark-theme secondary surface lightens for stronger inset separation, and table zebra stripes strengthen for longer-table readability. A stray extra `}` in the `.kpi:hover` rule is removed. Pure styling — no markup, interaction, or statistics change.
- Dark-theme depth pass: the background darkens for a calmer canvas, the card surface and glass lift away from it for clearer layering, and the ambient mesh blobs brighten for a deeper, more dimensional feel. Light-theme tokens are unchanged.
- Collapsed-table summaries now carry live counts everywhere: the cost ledger detail table shows `N 行 · 待定价 M` (omitting the pending segment entirely when nothing is pending, instead of noise like `待定价 0`), and the daily model table adds the total token figure (`N 行 · 总 X Token`), matching the trend summary idiom so every collapsed `<details>` tells the reader what is inside before opening it.
- The trend "Exact details" table and the daily model usage table start collapsed (`<details>`) so the page opens shorter; picking a date expands the daily table automatically. Both summaries show row counts, and the trend summary adds the period total.
- Record cache schema version bumps to 19 and then 20 (Claude records gain the informational `request_model` field; CCR hex aliases decode to their embedded backend name; and the decoded name drops its provider prefix to merge with historical bare router names), so the first scan after each change re-parses source logs once and rewrites the cache in place; counting semantics and all prior ledger rules are unchanged.
- Record cache format is now v7 (`records-v7.json`). Older incompatible caches are treated as misses and left in place; source logs are not modified. Warm entries must pass strict record, billing-component, deduplication-state, and capacity validation before reuse.
- Live log scans run in a single background worker; page and snapshot requests read published in-memory data without waiting for parsing or aggregation.
- `--interval` controls background scanning. Browser checks default to at most one minute, check sooner during preparation, and can be changed or paused independently.
- Token Flow is redesigned as Token destinations: a project/model overview beside readable session cards, with a stacked mobile layout and the existing seven-plus-`Other` palette.
- Model buttons filter the session list locally; project actions open recorded evidence without inferring project-to-session pairings.
- Sessions paginate twelve per page with exact off-page usage, an accessible full-list table, and separate replay actions.
- SVG export identifies the current page, scope, model filters, and theme instead of implying that it includes every session.
- Cost-ledger documentation limits the "not embedded in reports" statement to manually entered private prices; built-in public reference prices ship with the page assets.

### Fixed

- With a date range active and a whole current period, delta attribution and the dominant-model shift now use the full previous period, matching the headline total. Previously previous-period days were mapped by calendar offset, so a 28-day February dropped January 29–31 from the per-model split while the total still counted them. 日期范围下完整本期的归因与主力对比改用完整上期，与总量同口径（此前 2 月对 1 月会漏掉 29–31 日）。
- Two dashboard logic tests still extracted the removed `periodDelta` helper and used `YYYY-MM` month keys that never occur in real payloads (months are `YYYY-MM-01`); they now exercise `deltaWindowInfo`/`deltaPercent` with real keys. 两个仍引用已删除 `periodDelta` 的逻辑测试改用真实月键与新接口。
- Collection-wide resource ceilings were raised to match real local history: total retained data 256 MiB to 1 GiB, total records 500,000 to 1,000,000, and the record-cache file ceiling 64 MiB to 512 MiB. Counting semantics, record format, per-file limits, and the cache version are unchanged; this is a capacity adjustment, not a statistics change. Actual local history previously exceeded the old ceiling, so every scan failed with `total_retained_bytes_limit` before any snapshot could be published.
- Cache permission setup now checks `os.fchmod` availability instead of raising `AttributeError` on older Windows Python versions. Supported descriptor permissions, bounded writes, atomic replacement, and preservation of an existing cache on save failure remain in place; Windows permissions are not claimed to provide POSIX `0600` or a user-only ACL.
- Synthetic safety tests gate only FIFO-specific cases on `os.mkfifo` capability. Node contract tests decode stdout as UTF-8, and title-cleaning examples use non-home synthetic paths without weakening release-content scanning.
- Added a bounded, synthetic-only Windows stat diagnostic to identify cross-API field differences before changing safe-read comparisons. Windows stat compatibility and Firefox/WebKit CI failures remain unresolved at this diagnostic stage; this is not a claim of fully passing CI.
- Added a separate bounded Windows safe-read probe for the closed-writer/read-only-open lifecycle. It records actual API snapshots and comparison pairs; synthetic helper tests cover output limits and transparent forwarding. Production stat checks remain unchanged, and this diagnostic does not establish Windows compatibility or a real usage correction.
- Claude JSONL files no longer disappear from collection merely because the file grows past 64 MiB. Safe, bounded reads stop at the initially observed file length; truncation, replacement, early EOF, or read failures stop collection instead of returning partial results.
- Claude physical lines over 4 MiB use the same streaming JSON validator and exact usage projection as smaller lines, rather than failing solely on line length. Discarded fields and trailing syntax are validated before an event is accepted; explicit depth, token, projection, numeric, file, and collection limits remain in force. Per-file first-wins deduplication and billing semantics are preserved, including shared NaN identity and exception-path buffer cleanup.
- Incomplete collection does not overwrite a report or a valid cache with partial data. Live scans preserve the last successful snapshot, leave the first snapshot absent on failure, and retry failed scans even when the source signature is unchanged. Optional Claude title discovery failures no longer block reports that selected only Gemini or Codex.
- Added synthetic differential, long-line, resource-boundary, cache, CLI, and live-refresh regressions. These validate collection behavior, not the missing amount in any real usage history; this change does not claim a real-data recount, a service deployment, or a package release.
- Record caches now bind parsed dates to the reporting timezone. Changing timezone or loading a cache without that marker reparses source records instead of reusing stale calendar dates; an unverifiable system-local timezone conservatively reparses. Historical source files and model attribution are not changed.
- `glm-5.3` and `glm-5.3-flash`, when present under those exact recorded names, retain separate filter identities even when model capacity overflows. They share the existing seven-identity capacity with the latest backend and usage-ranked models; no historical records are relabeled and no absent Flash usage is inferred.
- The lazy-section error glyph ("!") uses a lighter amber in the dark theme so its contrast against the error panel clears the 3:1 non-text threshold; the light theme keeps the darker amber.
- The period-over-period delta label (`环比` / `较上期同期` / `部分范围 · 同历日对比`) now follows the selected language instead of staying Chinese in English mode; the same label is reused by the change-attribution panel and the top-model shift badge.
- The change-attribution empty states (`需要连续两期且上期 Token 大于 0` / `暂无可比窗口` / `没有足够的同期数据可拆解` / `各模型与上一比较窗口持平`) now follow the selected language instead of staying Chinese in English mode.
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
