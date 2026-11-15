# Universal web 2.3: status banners and the BoardSelector host line

WEB-10 / WEB-09. MASTER-PLAN Phase 2 row 2.3 (deps 1.7a, 1.4c, H12).

## Goal

One persistent `StatusBanner` (FiestaUI 1.7a) under the Home PageHeader, picked from real hub
state, with one recovery action each; and the BoardSelector hub line ("host · State" + status
dot, FiestaUI 1.4c).

## Sources

- 07a `Web / Banner` `298:2280` (copy, tones, actions); frames `310:36022` (out of sync, D),
  `310:37770` (hub unreachable, S), `310:38645` (display offline, S), `306:6748` (silenced, D).
- 07 `59:69165` (PWA, hub unreachable), 03 `33:126` (row D, one fix each), 02 `20:6147` and
  `149:28542` (no viewer; web keeps the 07a recipe per the Fable ruling).
- 07a `302:2146` and 07 `53:143037` (hub line).

## Data (no invented fields)

| Kind | Source | Action |
|---|---|---|
| `device-offline` | `navigator.onLine` false | Try again (refetch) |
| `hub-unreachable` | the shared `GET /v1/status` poll failed with no answer from the hub (network error, timeout, 502/504) | Try again; Connection help |
| `init-error` | `boards[id].error` (#1749) | Display settings |
| `display-offline` | H12 `boards[id].health.reachable === false` (`last_connected_at`, `breaker_open`) | Diagnostics → `/displays/{id}` |
| `paused` | `boards[id].paused` | Resume (`setBoardPaused(false)`) |
| `silenced` | `GET /silence-status` `active` + `until` | none (UX ruling, 07a `306:6748`) |
| `no-viewer` | FiestaPanel board; H13b `GET /auth/sessions` TV sessions' `shown_panels[].last_shown_at` for its panel, none in the last 5 min | Check again |
| `silence-soon` | existing SilenceImminentBanner logic | unchanged (restyled) |
| `out-of-sync` | existing BoardOutOfSyncBanner (#1945) | Restore / Save as page (restyled) |

Priority, one banner: device-offline > hub-unreachable > init-error (current board) >
display-offline > paused > silenced > no-viewer > silence-soon. Out-of-sync stays where
BoardOutOfSyncBanner is mounted (Jev: restyle in place, p 0.72); 2.2 owns the Home card.

Hub line: host = `location.hostname`; state = `unreachable` when the hub is unreachable or the
device is offline, else `online` for a LAN host (`.local`, private IPv4, `localhost`, single
label) and `remote` otherwise.

## Steps (test first)

1. `lib/hub-identity.ts` + tests: host classification, hub status.
2. `lib/status-banners.ts` + tests: `pickStatusBanner` priority, pure.
3. `hooks/use-hub-connection.ts` + tests: online store, reachability from the status query.
4. `components/status-banners/status-banner-host.tsx` + tests: copy, actions, kinds.
5. Restyle init-error, silence-soon, out-of-sync onto StatusBanner; keep their tests green.
6. Mount: home.tsx (one line, 2.2 file), displays.$boardId.tsx (one line), navigation-sidebar
   (BoardSelector props, 2.1 file).
7. i18n `statusBanners.*` in 14 locales; e2e spec; axe; screenshots 390/768/1280 × light/dark.
