# Universal web 2.8: PWA honesty

WEB-15 / WEB-12 / WEB-16. MASTER-PLAN Phase 2 row 2.8 (deps 1.10; H16 for the HTTPS parts).

## Goal

The web app tells the truth about what it can do as an installed app:

- a manifest and head tags that work under HA Ingress (relative URLs);
- an install offer that appears only after a real success, never on load, with a 30-day snooze;
- an app-shell service worker that keeps the app openable offline, never caches API responses
  and never strands a tab on a stale shell;
- the last-known board in IndexedDB, shown when the hub can't be reached, cleared on sign-out;
- `/offline` rewritten as the WEB-16 split ("You're offline" vs "Can't reach your hub");
- HTTPS detection, with a "needs HTTPS" state that draws no fake Install button.

## Sources

- 07 `58:33496` / `58:34360` (install card), `58:34465` / `58:35303` (Safari sheet), notes
  `58:34443` ("ask after value, never on load", "HTTPS or nothing, said plainly") and `58:35364`
  ("done honestly on iOS"); `59:69165` (PWA desktop, hub unreachable, last known).
- 07e §8 Global states: `329:47360` You're offline, `329:48320` Can't reach your hub,
  `329:49323` Requires HTTPS (07a HTTPS banner on Settings).
- FiestaUI 1.10a (#396): `InstallCard` (`state: available | installing | needs-https`),
  `InstallSteps` (host `steps`, DD-W29), `PrivacyNote`; 1.7a `StatusBanner kind="https"`.

## H16 (hub TLS) is not in the v11 stack

Jev `jev_decide` (p 0.77, `ship_gated_on_secure_context`; defer-everything 0.21): ship the
service worker, the real Install button and the offline shell **gated on `window.isSecureContext`**.
They work today wherever the page already is secure (localhost, HA over HTTPS, a TLS reverse
proxy). On plain http the app shows the honest needs-HTTPS state and registers nothing.
Named follow-up **2.8-H16**: when H16 lands, point the HTTPS copy and the "How to set up HTTPS"
link at the hub's own TLS setting instead of the reverse-proxy docs.

## Design

| Piece | Where | Notes |
|---|---|---|
| Secure-context / standalone / iOS detection | `src/lib/pwa/environment.ts` | pure, injectable `window` |
| Install trigger (3rd send or a saved page; shown once; Not now = 30 days; Don't show again = never) | `src/lib/pwa/install-trigger.ts` | localStorage, versioned key |
| API success events | `src/lib/api/success-events.ts`, one emit in `fetchApi` | no edits to Home/editor files |
| Install offer | `src/components/install-prompt.tsx` (rewrite) | InstallCard in the page flow after the Outlet; Safari sheet (Sheet + InstallSteps); `needs-https` card on http |
| SW registration | `src/lib/pwa/register-service-worker.ts`, `PwaLifecycle` in root | secure only, `appUrl("/sw.js")`, scope `appUrl("/")`, `updateViaCache: "none"` |
| Service worker | `public/sw.js` + `public/sw-shell-policy.js` | page loads network-first (cached shell only on network failure); `assets/` + `icons/` cache-first; **`api/` never touched**; non-GET, cross-origin, `Authorization`, `no-store`/`private` never cached; legacy caches deleted on activate; `skipWaiting` + `clients.claim` |
| Last-known board | `src/lib/pwa/last-known-board.ts` (IndexedDB) + recorder in `PwaLifecycle` | records `board-current-message` results from the query cache with the owner's username; wiped on sign-out, on `/login`, and when a different user is signed in |
| `/offline` and the offline boot | `src/components/pwa/offline-screen.tsx`, `app/routes/offline.tsx`, BootGate offline branch | StatusScreen pattern; last-known board card |
| HTTPS banner | `src/components/pwa/https-required-banner.tsx` on Settings › Network | `StatusBanner kind="https"` |
| Manifest | `public/manifest.json` | relative `start_url`/`scope`/icons, `id`, split `any`/`maskable` |

## Tests

- vitest: environment, install trigger, success events, SW policy + worker (vm), last-known board
  (an IndexedDB test adapter), recorder, install offer (timing, snooze, needs-https, iOS sheet), offline
  screen, BootGate offline branch, sign-out clears.
- Playwright `tests/pwa-offline.spec.ts` (SW registers; offline reload shows the shell and
  "You're offline"; no `api/` entry in any cache; network-first shell refresh) and
  `tests/pwa-install-prompt.spec.ts` (nothing on load even with `beforeinstallprompt`; card after
  the 3rd send; Not now snoozes across reloads), axe on each new state.

## Codex handoff review (2026-11-13)

The inherited implementation had no slice status file or PR. Preserve its good work,
then verify the entire slice before reporting readiness. The security review found
that arbitrary navigation HTML could enter the shell cache and a second tab could
repopulate IndexedDB after sign-out.

- Jev chose an anonymously fetched canonical shell (probability 0.67), rather than
  trusting cache-control on arbitrary credentialed navigation HTML (0.01). Keep
  navigation network-first; refresh the canonical shell separately. Cookie-gated
  ingress may have no offline shell: fail closed rather than cache an account page.
- IndexedDB uses scope-specific databases, transactional session generations, and a
  synchronous revocation marker. Late board or auth responses from the old session
  must not reopen it; a fresh auth verification can establish the next owner.
- Registry pin is alpha.1. The draft cannot be ready until an alpha with #396 ships.
  Local validation builds origin/alpha plus #396 without committing the tarball.
- Saved references and inherited screenshots remain in program/shots/web-2.8;
  DD-W62–69 record the integration gaps. A fresh Fable gate remains unavailable.

## PR #2484 review corrections (fix2484)

- M1: deliver original authenticated asset requests; populate caches with independent
  anonymous URL requests in `waitUntil`. Jev selected this over precache-only storage
  with probability 0.96 (confidence 0.95).
- M2: cache open/read/write failures must preserve online delivery.
- S1: namespace shell/assets by registration scope; trim only that scope, clean up
  only proven-owned versions, and leave unscoped legacy caches unread/untouched.
- Verify cookie-gated page reload and lazy modules using a real HTTP server and
  Chromium, plus worker VM regressions and the full existing local checks.
- S2/S3/S4 remain release/integration gates. Shared StatusScreen follow-up includes
  the phone retry action's full-width reference. No UI parity claim from worker edits.
