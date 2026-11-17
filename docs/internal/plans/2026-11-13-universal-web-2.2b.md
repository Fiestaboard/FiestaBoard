# Home supporting pane implementation plan

> Execution: Codex builder inline, independent contract audit and Astra final review. User authorized autonomous execution.

**Goal:** Restore DD-W50 Home proportions and authoritative Up next, Other displays and Manual Mode supporting cards.
**Spec:** program/briefs/WEB-SLICE-BRIEF.md, WEB-BATCH3-RULINGS.md, shots/web-2.2b/FIGMA-REFS.md in the external program hub.
**Architecture:** Keep current Home data and main card. Add HomeSupportingPane consuming board, schedule state, names and H2 detail already read by ActivePageDisplay. OtherDisplayRow reads existing scoped APIs. Only kit Card, Text, Button, Switch, StatusDot and existing DevicePreview/ScaledBoardDisplay thumbnail wrappers.
**Stack:** React Router, TanStack Query, FiestaUI alpha.2, vitest, Playwright.

## Decisions and review focus

Jev one_authoritative_row p=1.0: H2 supplies one event only. /schedules contains recurrence rules, not ordered events; H2b is panel-status parity. Never compute future schedule in the client. Show one valid future hub event and localized empty state, with View Schedule. Record parity gap for rows 2–3.
Use 274 px pane at >=1024; tablet panes side by side at >=768, stacked below main. Phone shows only Up next or Manual Mode. Dark uses kit tokens. Missing drawn states derive nearest card, documented in DD.
Review board scoping, stale/invalid dates, unknown page names, failures/Undo, unknown health versus offline, no nested thumbnail controls. No backend changes.

## Task 1: Supporting pane

Files: new web/src/components/home/home-supporting-pane.tsx; new web/src/**tests**/home-supporting-pane.test.tsx; active-page-display.tsx; web/messages/*.json; existing home/** coverage glob includes new file.

1. Write tests: only future H2 next event; override_ends says Schedule resumes; invalid/missing/past events show empty; unknown page honest; no events from CRUD recurrence. Manual mode checked false Switch changes selected board and Undo restores false, error has no success; unknown state has no switch. Other displays excludes selected, uses display-specific content and mode and selects clicked board.
2. Run focused vitest to observe missing feature failure.
3. Build kit cards and integrate grid around main card; banners remain above grid pending 2.3b. Schedule enable captured board ID; await setting then refresh and per-display nudge; Undo disabled if state changed since.
4. Run focused and relevant Home tests, full coverage, typecheck/lint/format/build. Add e2e responsive pane/switch/selection plus axe; screenshot 390/768/1280 light/dark.
5. Changeset, commit with required trailer, push and PR into v11. Astra review at exact head max 3 rounds; CI green before completion or the wrap-up stop flag.

## Task 2: Banner stack

After Task 1 review/CI, create 2.3b on its branch in this same worktree. Separate plan and changeset; follow DD-W34/35/36/38/58 and rulings. New PR targets first branch.

## Preflight ledger

Supporting pane consumes current data without owning schedule calculation. Banner placement remains outside grid so Task 2 can keep pane aligned with card. H2b reference conflict resolved by Jev as above. User forbids questions and grants execution, so no approval pause.
