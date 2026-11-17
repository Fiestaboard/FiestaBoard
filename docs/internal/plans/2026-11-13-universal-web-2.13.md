# Web 2.13 push and Badging implementation plan

> Execute test-first; independent SW helper in an isolated worktree; one Astra whole-PR reviewer, at most three rounds. Owner has explicitly requested autonomous execution without questions.

**Goal:** Enroll a signed-in account and this browser for push, truthfully report permission and transport state, show notifications through the existing worker, route clicks within the hub scope, and feature-detect app badging.

**Architecture:** A browser-only push API uses the existing session CSRF context and base-path helpers. A browser controller manages permission/subscription; a FiestaUI notification settings section renders server/browser state. Extend the 2.8 classic SW through a separate imported push handler. Sign-out clears subscriptions and badges without trapping logout.

**Tech stack:** React, TypeScript, React Query, FiestaUI 8.17.0-alpha.2 (current base pin), Vitest, Playwright. Classic JavaScript SW.
**Spec:** program/briefs/WEB-SLICE-BRIEF.md, task web213, docs/development/web-push.md; live Figma working file ZQ8RMELCO6qEOFZUnQu36e nodes 59:13890, 329:48335, 337:60272, 337:61267.

## Constraints and decisions

- v11 only; no publishing, merges, PR comments, VRT approval or Figma writes. Minor changeset; prescribed Claude trailer/footer.
- Reuse shared containers only; one heavy process at a time, Vitest <=2 workers and Playwright 1 worker/spec. Check program/codex/WRAPUP before each step.
- Both account and browser consent start off. Request permission only during explicit browser-enable activation; HTTPS/localhost, iOS installation, iframe/HA ingress and unsupported browsers need truthful states.
- H15 event_sources is empty: keep drawn categories disabled with unavailable copy (Jev disabled_categories p=0.75), never fake delivery or category persistence. Test counts distinguish sent/failed/skipped/expired; sent is provider acceptance only.
- Scope all APIs, SW lookup and notification click URLs to the runtime app base. No subscription secrets in localStorage/logs.

## Review focus

Permission dismissed/denied or changed externally; stale/key-rotated subscription and failed enrollment; tests accepted but not sent; HA ingress/out-of-scope click URL; sign-out with unavailable browser storage/network.

## Task 1 — API and browser enrollment

Files: new web/src/lib/api/push.ts, web/src/lib/pwa/push.ts and focused tests; web/src/lib/pwa/sign-out.ts.

- [x] RED: real API requests enforce CSRF/no-store/same-origin/base prefix; browser cases cover unsupported/insecure/denied, gesture request, failed enrollment cleanup, unsubscribe and bounded cleanup.
- [x] Implement typed H15 API status/preferences/subscription/delete/test. Controller uses app-scope registration, decodes VAPID, reuses only matching subscriptions, rolls back new browser subscriptions if server registration fails.
- [x] GREEN: focused Vitest tests. Extend existing post-logout local cleanup; server logout already invalidates enrollment.

## Task 2 — SW notifications and Badging (independent helper)

Files: web/public/sw-push.js, additive import in web/public/sw.js, web/src/**tests**/sw-push.test.ts.

- [x] RED: execute real worker code at browser seams; validate payload, showNotification, waitUntil, same-origin scope routing, focus/open, CLEAR_PUSH notification cleanup and CLEAR_BADGE message.
- [x] Implement imported worker module. Payload title/body/url/tag matches H15; push never changes badges: the app drives a dot from More attention, never an unread count. Reject external/traversing URLs and fall back to scope root; preserve HA prefixes. No app-shell caching change.
- [x] GREEN: helper focused tests, parent integrates and inspects diff.

## Task 3 — Notification settings and lifecycle

Files: web/src/components/settings/notification-settings.tsx and tests; additive settings.tsx/settings-sections.ts; messages/*.json notification namespace; pwa-lifecycle.tsx.

- [x] RED: enrollment is explicit and separate from account preference; no auto permission prompt; error and recovery states; count-based test results; disabled category rows; server auth unavailable.
- [x] Compose FiestaUI ListRowGroup/NotificationRow/Alert/Button/Text. Keep permission text separate from device consent. Use existing Settings list-detail shell, add notifications legacy query mapping.
- [x] Drive the attention dot from More update/setup state and clear it when More opens (live Figma59:15823); all new copy translated in every locale. Add new coverage entries.
- [ ] GREEN: focused component/integration tests and static checks.

## Task 4 — browser flow, parity and delivery

Files: web/tests/layout/notifications.spec.ts (mock H15 and browser push seam), changeset, status/refs/screenshots.

- [x] Playwright one worker covers default/allowed/denied/HTTP/unsupported/ingress/test-count/error/unsubscribe states with axe, 390/768/1280 light/dark captures plus drawn viewport slots.
- [ ] Full Vitest coverage, typecheck, lint, format, production build sequentially in shared containers; actual browser worker coverage where feasible.
- [ ] Independent Astra review including live Figma parity; repair findings with regressions, maximum three rounds.
- [ ] Commit/push normally; PR into v11; observe CI; update hub status and WORKTREES with exact results and remaining follow-ups. Never merge.
