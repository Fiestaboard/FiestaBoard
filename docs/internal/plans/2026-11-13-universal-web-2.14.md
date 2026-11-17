# Web 2.14 implementation plan

**Goal:** Translate Displays, Schedule, Integrations and Settings to the saved 06/07d/07e references.
**Architecture:** Preserve existing API, query and mutation wiring; compose only FiestaUI primitives. Four normal-merge stacked PRs: Displays → Schedule → Integrations → Settings.
**Spec:** program/briefs/WEB-SLICE-BRIEF.md, WEB-BATCH3-RULINGS.md, shots/web-2.14/FIGMA-REFS.md in the external program hub.
**Constraints:** v11, alpha.2 registry pin; all locales; test-first; no merges, publishing, VRT approval or comments; exact Claude commit trailer. Installed uses 06/DD-W12, not 07d. No dark or 768 references exist; derive using kit tokens and nearest breakpoint.

## Task 1: Displays

- [ ] Add failing tests for grouped health rows, problem ordering, selection and preview/quick controls; retain pause, add and settings flows.
- [ ] Replace index cards with ListRowGroup/ListRow and responsive list/detail. Reuse DisplayLivePreview, status banners and existing per-display mutations. On phones, rows navigate to the existing detail route.
- [ ] Align detail tabs/controls using existing kit parts, preserving output-specific settings. Add Playwright flow and axe assertions; capture 390/768/1280 light/dark.
- [ ] Run focused and full unit/coverage, typecheck, lint, formatting, build. Add changeset, push and create PR to v11.

## Task 2: Schedule

- [ ] Test failing responsive day/list/week selection, agenda states and entry interactions.
- [ ] Adopt AgendaRow, WeekStrip, WeekCalendar and ScheduleEntryForm where API-compatible; preserve real recurrence and sun-time storage. Wire H8 from hub, never compute its answer in web.
- [ ] Add e2e/axe, locales, coverage entries, changeset; run local gates. Merge Displays parent normally and open stacked PR.

## Task 3: Integrations

- [ ] Test failing Installed group/needs-attention actions and compact Marketplace presentation.
- [ ] Adopt ListRowGroup, ListRow, muted IconTile and brand text action; compact PluginCard results. Preserve plugin setup, OAuth, updates and output/transition plugin controls.
- [ ] Add e2e/axe, locales, coverage, changeset; run local gates and normally merge Schedule parent.

## Task 4: Settings

- [ ] Test existing section deep links and updated form layout using kit sections/rows.
- [ ] Align Network, language/time, system/backups, AI, FiestaBot, appearance and accessibility with refs, preserving supported hub settings only. Account/phone is 2.12, Notifications 2.13.
- [ ] Run all gates, e2e/axe, screenshots, changeset; normally merge Integrations parent.

## Review and finish

- [ ] Astra reviewer independently reviews each PR exact head against brief/rulings/refs (maximum three rounds). Fix important findings test-first.
- [ ] Poll hosted checks to green; record observed evidence and outstanding gaps in status/web-2.14.md and WORKTREES.md. Check WRAPUP before every step/PR and at least every 30 minutes.

## Review focus

Unknown health must not read Online; responsive list selection must not navigate on desktop; removed displays must not leave stale detail; all writes must stay scoped to the selected display; unavailable hub settings must not acquire invented controls. Tests belong to each owning section.
