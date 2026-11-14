# Universal web slice 2.2: Canonical Home (WEB-08/11/18)

**Goal:** Home matches 07a: one "Compose a message" entry in the PageHeader; the Now showing card with Change Page as the in-content secondary action; both verbs (Compose a message, Change Page) end in the one DurationChipGroup step and "Show now"; `ForceSetDialog` is gone, rebuilt as the Change Page dialog; the Override badge and Countdown with the outcome line; the board context menu (right-click / Shift+F10 / long-press / ⋯).

**Design source (Figma `ZQ8RMELCO6qEOFZUnQu36e`):** 03 `33:10` (Home canon); 07a Home · Override `303:22566`, phone `306:53082`, Manual Mode `305:25799`, 900 `307:61752`; Change Page `310:27278`, Desk Pixoo `314:42080`, phone step 1 `318:42097`, step 2 `310:30774`; Compose `310:20283`, phone `310:25527`; Board context menu `302:2333`, frames `310:31650` (D), `310:33398` (S); Duration chip `302:1954`, DurationChipGroup `302:2051`.

**FiestaUI (local tarball until alpha.1):** DurationChipGroup / OutcomeLine / Countdown / NowShowingCard (1.7b #393), ListRow + `DropdownMenu trigger="context"` (1.8a #389), PagePreviewCard (1.8c #392), DisplayTypeChip (1.5c #394).

**Hub (in the v11 stack under #2471):**

- H1: `POST|GET|DELETE /settings/temporary-override` take `board_id` (one override per display). The active-schedule read already returns the selected board's override.
- H2: `GET /v1/boards/{board}` returns `next_change_at`, `next_change_reason` (`override_ends|schedule|silence_starts|silence_ends|collection`), `next_page_id`, `override_expires_at`, `override_started_at`.
- Triggers are primary-only and beat an override (`GET /triggers/active`). STATUS LOG carry: while a trigger shows, status reads `override_active: true`; the UI must not claim the override is on screen.

## Decisions

1. **Change Page in Manual Mode** (Jev `jev_decide`, `same_dialog_cancel_pins`, p = 0.81): the same dialog and chips everywhere. Timed chips set a timed Override that reverts to the manual page; "Until I cancel" in Manual Mode pins the page as the new manual page (no Override badge). In Schedule Mode "Until I cancel" is an indefinite Override.
2. **The "Until <time>" chip** is shown only when H2's `next_change_reason` is `schedule` and the change is ≤ 8 h away (the override store's 480 min cap). Its outcome names `next_page_id`. While an override is active H2 reports `override_ends`, so the chip is left out (hub gap, recorded).
3. **Chip → request:** `15m` → 15, `1h` → 60, `next-change` → whole minutes until `next_change_at` (rounded up, clamped 1–480), `until-cancel` → no `duration_minutes`.
4. **Countdown `onEnd`** invalidates the active-schedule, board-detail and current-message queries once per `endsAt`.
5. **Trigger over an override:** when `/triggers/active` returns a trigger on the primary display while it has an override, the card names the alert, drops the Override badge claim and says the Override returns after it.
6. **Home keys:** C (Compose), P (Change Page), E (Edit page) are bound on Home only, outside text inputs, because 07a draws their hints there. 2.7 owns the editor's registry.
7. **Layout code** lives in `web/src/components/home/**`; `app/routes/home.tsx` only composes it. No shell, nav or route-config edits (2.1). The two banner lines stay as they are for 2.3's swap.

## Tasks (test-first, one commit per sub-feature)

1. **Data layer** (`lib/api/{boards,schedules,triggers}.ts`, `components/home/home-status.ts`, `use-home-status.ts`): H1/H2 types, `getBoardDetail`, `board_id` on the override calls, `getActiveTrigger`; pure helpers for chip → minutes, outcome copy, and "override on screen". RED: `home-status.test.ts`.
2. **Duration step** (`components/home/duration-step.tsx`): DurationChipGroup + outcome copy from H2, shared by both verbs. RED: `duration-step.test.tsx`.
3. **Change Page dialog** (`components/home/change-page-dialog.tsx`), replacing `ForceSetDialog`, the page sheet and the change-mode dialog: search, Pages / Collections, ListRow rows, the bare Preview row (DD-W15), DurationChipGroup, Cancel · Show now. Below 640 px a bottom sheet in two steps (pick → how long). RED: `change-page-dialog.test.tsx`.
4. **Compose a message** gets "Show on" (any display, H1) and the duration step; the only entry is the PageHeader button. RED: compose tests updated.
5. **Now showing + Override** (`components/home/now-showing.tsx`): NowShowingCard hero with mode badge, Countdown, outcome, actions (Change Page secondary · Cancel override outline · Edit page ghost / View Schedule), key hints. RED: `now-showing.test.tsx` and the existing Home tests updated.
6. **Board context menu** (`components/home/board-context-menu.tsx`): Change Page… · Compose a message… · Edit page · Copy as text · Refresh board · Pause <display>, on right-click, Shift+F10, long-press and a ⋯ button. RED: `board-context-menu.test.tsx`.
7. Messages in all 14 locales, Playwright `tests/e2e/home-canonical.spec.ts` (+ axe), screenshots at 390 / 768 / 1280 light and dark, changeset.

## Codex handoff completion — 2026-11-13

Retain the committed review fixes and verify against `program/reviews/pr-2481-review.md`. Finish in this order:

1. Pin published FiestaUI 8.17.0-alpha.1 and clean-install in an isolated container. Existing merge `10aa98959` includes origin/feat/universal-web-2.1-ia-nav; retarget #2481 to that branch.
2. Regression tests first for the remaining S2 gaps: per-display Undo toast dismissal after either verb, capture original display/content during a pending Cancel, and recheck expiry after Undo's GET.
3. Verify M1/M2 regression sensitivity, then full unit coverage, typecheck, lint, format, build; one-worker, one-spec-at-a-time Playwright including canonical Home and axe.
4. Re-capture 390/768/1280 light/dark with reduced motion and seeded started_at; compare saved Figma references.
5. Program records: 2.2b owns DD-W50; existing 2.3b owns banner hand-offs; H22 owns expired-override read/consume race. DD-W70 records phone PageHeader action alignment (FiestaUI owner, adoption by 2.2b; Jev kit_delta p=0.99). DD-W72 records the missing Page provenance field for the saved-from-Compose annotation. S8 shortcut registry remains assigned to 2.7 integration.
6. Push normally; update only this PR body, status and worktree row with observed local/CI results. No merge, VRT approval, or GitHub comments.
