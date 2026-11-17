# Collection editor follow-ups implementation plan

> Execute test-first with an isolated locale builder and a separate Astra reviewer (maximum two rounds).

**Goal:** Correct rule-count plural forms in all 14 locales and put the medium preview immediately after mode chips.

**Architecture:** Keep the existing translation hook and ICU message format; select plural categories using the active locale where required. Render the non-phone preview after the chips while retaining its desktop absolute position and the phone's independent collapsible preview.

**Spec:** Program `reviews/FABLE-2500-2508.md`, task web26bf, Figma 07c `312:76483` / `316:98955`.

**Constraints:** v11 base; kit primitives only; patch changeset; no Figma edits, merge, VRT approval or PR comments. Shared containers only; one heavy process at a time, Vitest maxWorkers=2, Playwright workers=1. Preserve existing accepted design deltas.

**Review focus:** Locale-specific zero/one/few/many and exact ICU selectors; language switching; medium DOM/visual order; desktop sidebar geometry; phone preview independent of settings and dirty-state propagation.

- [ ] Add failing layout-order and independent phone-preview tests; add browser geometry assertions to the existing 24-state parity matrix.
- [ ] Add failing real translation-hook tests for all locales and relevant plural categories.
- [ ] Run and observe RED before production edits, then implement minimal fixes and observe GREEN.
- [ ] Run full web coverage, typecheck, lint, format, build, collection e2e and axe; capture 390/768/900/1280 light/dark.
- [ ] Recheck live Figma (initial calls rate-limited), independent Astra review, fix any findings within two rounds.
- [ ] Commit, push normal, PR into v11, observe CI and record evidence/status/ownership.

Decision: Jev selected conditional preview placement (p=0.80), retaining one mounted preview at each breakpoint and independent phone disclosures, instead of splitting settings or CSS ordering.
