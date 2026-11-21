# Dashboard design iterations

Small iterations should improve an existing question-to-answer path, not add another panel for an answer the dashboard already provides. Each iteration needs synthetic correctness checks, keyboard and narrow-screen checks, a visual review, and an independent review before delivery.

## Lightweight date browser

**Question:** How do I find a recorded day quickly and open its per-model details without a permanently expanded calendar?

The browser lives inside daily model usage. Seven consecutive report dates provide a compact default view; an inline month picker opens on demand. A date preview follows the selected models but may include days outside the reporting range. Choosing a day uses the existing specified-day range: usage views, daily details, and exports then share that range. Browsing, folding, and unfolding alone change none of them. Existing GLM comparison cards are reused, not duplicated or relabeled as a preview day's statistics.

The first always-expanded month prototype did not receive visual acceptance. This revision uses a small synthetic preview before full regression sign-off; passing its predecessor's tests is not evidence that this design is accepted.

### References and reusable principles

- [GitHub contribution calendar](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-github-profile/managing-contribution-settings-on-your-profile/viewing-contributions-on-your-profile): a recognizable day grid provides a direct route to a particular date. This iteration does not implement its multi-day selection.
- [Linear Insights](https://linear.app/docs/insights): shared filters and chart-to-detail drill-down keep related views coherent. The browser reuses the dashboard's existing filter and detail pipeline instead of creating another one.
- [shadcn Date Picker](https://ui.shadcn.com/docs/components/date-picker): a trigger and an on-demand calendar separate frequent reading from date selection. This native implementation adapts that layering with inline disclosure; it does not install React components or copy a popover implementation.

The references above were reviewed as official written documentation, not as a claim of external-product visual or browser testing. Their interaction principles are adapted; brand assets and product skins are not copied.

### Data and interaction boundaries

- The date window and preview month are transient UI state, not new URL or persistent settings. Explicit reporting-range changes reposition both; theme, language, model changes, and live data refreshes update values without jumping to newer dates. Month navigation does not move the seven-day window.
- A gap is not proof of zero actual usage. No day record, no selected-model record, an explicit recorded zero, and an unknown or unsafe count remain distinguishable. Snapshot endpoints do not prove that the intervening logs are complete. Essential warnings remain visible when explanatory details are folded.
- Selected-model token and logged-call counts remain independent. Safe source integers can be summed exactly with BigInt; missing or unsafe token counts are not assigned a precise intensity. Intensity is relative to the visible seven-day window or the expanded month, respectively, not an absolute comparison between the two.
- Date arithmetic follows the report's calendar helpers and UTC calendar operations, not the viewer's local midnight. Generation-day fallback is labeled. The usual seven dates are truncated at the supported lower year boundary rather than filled with invalid dates.
- The strip uses real buttons, a single roving tabstop, and pressed state only for the exact specified day. The optional month grid has at most 42 positions, starts on Monday, and retains its keyboard navigation. Native disclosure state survives repainting. Choosing a day moves focus to existing daily details; repainting must not steal focus from other controls.
- Each render reuses the existing monthly aggregation through a local month-keyed map. The strip needs at most two months; a different expanded month adds at most one. There is no per-day rescan, fee scan, or cross-render cache, and no unmeasured performance claim.
- No new network requests, telemetry, external fonts, pricing rules, model aliases, or record-attribution inference are introduced.

### Acceptance gates

1. Synthetic logic covers sparse records, explicit zeros, missing fields, unsafe values, exact large sums, leap years, month boundaries, and range transitions.
2. Review a focused synthetic prototype before full regression sign-off: inspect the default date strip and expanded month at desktop and narrow widths in both languages and themes. DOM dimensions and generated screenshots do not substitute for pixel-level visual acceptance. If the image viewer is unavailable, keep the gate open and request local user review.
3. After the direction is accepted, synthetic Chromium checks keyboard focus, native disclosure, shared view/export scope, navigation entry points, and live updates. The full affected regressions, static review, and exact-change sensitive-content review must pass before a file-whitelisted commit and push. Test evidence is per iteration, not inherited from earlier work.
4. Code delivery and running-site deployment are reported separately. This design revision does not deploy, inspect private usage records, or delete historical artifacts.

## Candidate queue

Candidates are not approval for a batch redesign. Select one primary question for the next iteration, inspect existing behavior, add a relevant public reference, and repeat the acceptance gates.

1. **Explain a change:** make the existing change-attribution explanation and its evidence easier to follow, without adding a second attribution engine.
2. **Read the first screen:** improve hierarchy and progressive disclosure of existing modules, without hiding essential scope or data-quality warnings.
3. **Reach a frequent query:** refine the existing command palette and common lookup paths, rather than add another shortcut system.

Year-wide heatmaps, streak rewards, companions, World, multi-day drag selection, and new arbitrary-range presets are outside this iteration.
