# Home banner hand-offs implementation plan

> Execution: Codex inline builder, Astra review only, autonomous per user.

**Goal:** DD-W34/35/36/38/58: one silence banner, held-message card, canon out-of-sync, last-known state and disabled sends when hub cannot answer.
**Specs:** external program/briefs/WEB-SLICE-BRIEF.md, WEB-BATCH3-RULINGS.md, shots/web-2.3b/FIGMA-REFS.md.
**Architecture:** Reuse shared useHubConnection/status poll; guard Home buttons, shortcuts, menu callbacks and already-open dialog submits. Board offline still allows sends; hub/device offline do not. Keep typed Compose content and show its connection banner.

## Task 1: Main card and sends

Files: home.tsx; active-page-display.tsx; home/home-compose.tsx; home/board-context-menu.tsx; compose-page-dialog.tsx; home/change-page-dialog.tsx; home/home-supporting-pane.tsx; new home-banner-handoffs.test.tsx and existing silence tests.

1. Tests RED: hub offline disables header Compose, Change Page, C/P/menu and already-open dialog sends; display offline dims at 0.6 and permits sends; hub loss dims 0.5 with Last known. Drop standing silence notice, retain held discard card above board on phone and first supporting card desktop. No unsupported release action.
2. Implement kit composition, guards and cache age labels. Do not claim live while hub cannot answer. Keep Edit page available (local editing remains useful). Verify relevant suites GREEN.

## Task 2: Banner semantics

Files: board-out-of-sync-banner.tsx; silence-imminent-banner.tsx; status-banner-host.tsx; all locale JSON; existing banner tests plus slice e2e.

1. Tests RED for named Home out-of-sync copy/one action, preserve kept-frame Save/Dismiss; silence-soon title with time and only Edit Silence Schedule. Held silence banner names held message with Show now spelled correctly.
2. Implement Home-specific props while preserving display-page recovery. Show Should be showing/warning state in card. Remove orphan home.boardInitError{Title,TitleUnnamed,OpenSettings} locale keys. DD rulings preserve retry15s and offline dim0.6.
3. Unit/coverage, typecheck/lint/format/build; hosted full-app e2e and axe, screenshots 390/768/1280 light/dark. Local Docker unavailable; native browser launch blocked.
4. Separate changeset and PR based on feat/universal-web-2.2b-home-pane. Astra exact-head review <=3 rounds; poll CI and fix. No merge/comments/VRT approval.

## Review focus / preflight ledger

Task1's connection state must guard Task2 recovery and held discard as well as visible send buttons. Mid-dialog hub failure must preserve text. Unknown health stays unknown; explicit H12 unreachable only marks Offline. Existing cached data persists from shared queries. No silent queue. Held author/release API absent: omit author and hide early-release action. All tablet/dark states without references derive existing kit tokens/layout. Remote simultaneous mutation revision guarantees remain a hub API gap inherited from 2.2b.

## Final review continuation (2026-11-17)

- Retire Cancel override Undo when Home unmounts, including a pending read or a late Cancel response. Three regressions observed RED before the guard; all 70 tests across the five affected Home/override files pass afterward.
- Ruling: preserve Undo's captured original display while Home remains mounted. The existing 2.2 plan and pending-DELETE regression require it; selection changes alone do not freeze the shared connectivity ref. Jev `home_lifetime` p=0.95, confidence=0.94. Retiring on every selection change would remove that established behavior. Each mount owns its emitted toast IDs and dismisses them on cleanup.
- The d6 hosted run was green with one retry: a banner capture axe scan reported pale foreground colors across the animated main region. The common route entrance fades opacity over 0.4 s; visibility alone does not establish settled contrast. Jev `wait_fade` p=0.78, confidence=0.74 selected waiting for computed ancestor opacity before the unchanged axe scan. Failure-time opacity was not captured, so the cause remains a supported hypothesis rather than a reproduced diagnosis. No palette, contrast threshold or axe exclusion changed.
- Live read-only Figma comparison of held desktop/phone confirms a brand mono eyebrow and semibold message. Adopt existing kit typography/color utilities; preserve all recorded API and layout deltas.
