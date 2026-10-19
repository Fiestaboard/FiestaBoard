<!-- cspell:words worktree worktrees chromeless appletv androidtv Siri backgrounded reauthentication -->

# Revocable Sign-ins and TV Activation Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` for inline execution, or `superpowers:subagent-driven-development` if the user selects delegation. Steps use checkbox syntax for tracking. The user subsequently authorized implementation, CI fixes and merging the server into `next` and TV apps into `main`.

**Goal:** Support QR, desktop-code, and password sign-in on both TV apps, and revocable browser/TV sessions managed in FiestaBoard Account settings.

**Architecture:** A server-owned registry tracks browser sessions and scoped TV credentials. QR and desktop-code entry share an explicit browser-approval handshake; TV password entry issues the same credential directly. The web portal manages individual/bulk revocation. Native enrollment is enabled by default; the beta release channel gates testing.

**Tech stack:** FastAPI/Python/SQLite; React Router/React/TypeScript; SwiftUI/URLSession/Keychain/Core Image; Kotlin/Compose/OkHttp/Android Keystore/ZXing core.

**Spec:** [Revocable sign-ins and TV activation](../specs/2026-10-18-revocable-sign-ins-design.md). Read it before execution; endpoint bodies, error codes, permissions and lifecycle rules there are the shared contract.

**Status:** Approved implementation plan. Tasks 1–5 are implemented; automated qualification and merge evidence are tracked in `docs/internal/development/TV_SIGN_IN_BETA.md`. The checklist below preserves the original acceptance scope; physical-device and store-release work remains a separate beta qualification activity.

## Global constraints

- Backend/web PR targets freshly fetched `origin/next`, not the stale local `next` worktree. TV PRs target each app's current `main`. Create isolated worktrees at implementation time; preserve unrelated local modifications.
- TV enrollment defaults on, with an explicit disable available through Account settings. Browser session tracking is active infrastructure on the new server; disabling enrollment does not disable revocation or invalidate existing TV credentials.
- Both TV apps support QR, manually typed portal URL/code, and username/password. On supporting opted-in servers all issue a TV credential and store no account password.
- Challenge lifetime 600 seconds; initial polling interval 5 seconds; `slow_down` increases it by 5; transport backoff caps at 30 seconds. Credential lifetime 31,536,000 seconds (365 days), no refresh subsystem.
- Browser cookie name, 7-day/30-day default TTLs, environment overrides and remember-me semantics remain; versioned cookies additionally require an active registry record.
- One-time browser sign-in reset on migration; v2 cookies and TV tokens fail closed on downgrade. Auth-disabled and setup-required behavior remain supported.
- Secret material is local to the selected FiestaBoard and each client. No cloud relay, external QR generator, new camera permission, telemetry or Top Shelf secret sharing.
- TV permission `tv_panels` is the exact endpoint/method/field allowlist in the spec. Do not reuse the MCP token or give TV credentials browser-admin access.
- Existing public panel links stay public; UI/docs must not promise that revoking a TV makes such links private.
- Do not raise either app's current deployment floor for this feature. Additive capability decoding must work against old servers.

## Review focus

These failure modes require explicit tests in the owning task:

1. Revoked credentials resurrect through browser-cookie fallback, a deleted registry, an old password, or server rollback — Tasks 1, 2, 4, 5, 6.
2. Concurrent approvals/redemptions, account changes, and late responses authenticate the wrong connection — Tasks 1, 2, 4, 5.
3. Public `/auth/*` or `/panel/*` bypasses and permissive PATCH parsing give TV credentials administrator access — Task 2.
4. A proxy prefix, hostile redirect, separate desktop origin, or `.local` resolution failure strands approval or leaks a token — Tasks 2–6.
5. A failed secure-storage write or app background/restart claims success, loses the credential or keeps polling — Tasks 4–6.

## Delivery map

| Work package | Dependency | Reviewable result |
| --- | --- | --- |
| 1. Session registry and migration | None | Browser sign-ins and sign-out become revocable; legacy migration/rollback rules enforced |
| 2. TV protocol and authorization | 1 | Pairing, direct password exchange, scoped tokens, management API, contract fixtures |
| 3. Web activation and Account UI | 2 | Phone/desktop approvals and complete sign-in management |
| 4. Apple TV | 2 | All three methods, secure migration, lifecycle handling |
| 5. Android/Google TV | 2 | Same behavior and shared wire contract |
| 6. Coordinated beta qualification | 1–5 | Recorded acceptance, safe beta release and rollback procedure |

Keep backend Tasks 1–3 in a coordinated feature branch/PR targeting `next`; they need not land separately while Account UI is missing. App work can proceed independently once the contract fixtures in Task 2 are fixed. No shared runtime SDK is required across Swift/Kotlin/Python.

## Task 1: Persistent browser session registry

**Files — FiestaBoard:**

- Create `src/auth/session_store.py`, `src/auth/session_models.py`.
- Modify `src/auth/service.py`, `src/auth/routes.py`, `src/api_server.py` for registry lifecycle, v2 cookies, logout and invalidation.
- Verify `src/backup/service.py` continues to exclude auth state. Modify `src/system/update_service.py` to invalidate all sessions and advance the auth cutoff before managed image rollback/leave-beta transitions.
- Create `tests/test_auth_sessions.py`, `tests/test_auth_session_migration.py`.
- Extend `tests/test_auth_service.py`, `tests/test_auth_routes.py`, `tests/test_auth_contract.py`, `tests/test_backup_restore_rollback.py`.

**Interfaces:**

- `SessionStore(path: Path, clock_ms: Callable[[], int])` owns SQLite schema, transactions and expiry cleanup. All time-dependent tests use an injected clock.
- `SessionRecord`: opaque ID, credential digest, username, account generation, kind (`browser`, `tv`, `legacy`), name, method, client ID/version, creation/expiry/revocation/last-active milliseconds. Never expose digest through response models.
- `create_session(record: SessionRecord) -> None`; `find_active(digest: str, account_generation: int) -> SessionRecord | None`; `revoke_session(username: str, session_id: str) -> None`; `revoke_sessions(username: str, except_id: str | None) -> None`; `list_sessions(username: str) -> list[SessionRecord]`. Bulk revocation and challenge cancellation are one transaction once Task 2 adds challenges.
- Preserve `AuthService.authenticate(username, password, *, remember=False) -> str` and `verify_session(raw) -> str | None` externally. Add a password-verification helper that returns the verified account/generation without minting a cookie; Task 2 uses it.
- `resolve_browser_session(raw: str | None) -> SessionRecord | None` supplies current session ID to cookie-only management handlers. New cookies must have both a valid v2 signature and an active record.
- `AuthService.invalidate_all_sessions(username: str) -> None` durably advances the account cutoff first, then revokes registry rows/challenges. The cutoff makes partial database failure safe. Bulk sign-out including current and managed downgrades call this method; sign-out-others uses the registry operation to preserve the current browser.

- [ ] Write failing tests for `test_revoked_cookie_fails_even_with_valid_signature`, `test_missing_registry_row_fails_closed`, `test_logout_invalidates_copied_cookie`, `test_revoke_other_sessions_preserves_current`, `test_password_change_invalidates_all_prior_kinds`, and `test_last_active_writes_at_most_every_300_seconds`.
- [ ] Write migration tests asserting: a v1 token valid before migration is invalid afterward; the cutoff survives restart; repeated migration does not sign out new v2 sessions; old verifier rejects v2 payload; database failure never returns protected-request success; ordinary settings rollback leaves auth cutoff intact. Test account disable/recreation and username changes in the same clock tick. Rehearse two upgrade/downgrade cycles with cookies minted during the intervening old-server run; verify every managed downgrade advances the cutoff and refuses to proceed on failed persistence.
- [ ] Run `python -m pytest tests/test_auth_sessions.py tests/test_auth_session_migration.py -q`; confirm failures reflect missing new behavior.
- [ ] Implement registry and lifecycle, versioned issuance, lookup/revocation, 200-active-session limit, and one-time auth cutoff marker. Register cookies issued by setup, login, password change and username change, not just the login route. Revoke before clearing logout cookie. Record bounded client metadata at HTTP boundary; missing/unknown client metadata uses `legacy` or browser classification without treating it as trusted identity.
- [ ] Run `python -m pytest tests/test_auth_sessions.py tests/test_auth_session_migration.py tests/test_auth_service.py tests/test_auth_routes.py tests/test_auth_contract.py tests/test_backup_restore_rollback.py -q`; require all passed. Run `python -m ruff check src/auth tests/test_auth_sessions.py tests/test_auth_session_migration.py`.
- [ ] Commit the tested session foundation and migration together with message `feat(auth): track and revoke browser sessions`.

## Task 2: TV grants, management endpoints, and permission enforcement

**Files — FiestaBoard:**

- Create `src/auth/device_service.py`, `src/auth/device_routes.py`, `src/auth/device_models.py`, `src/auth/session_routes.py`, `src/auth/browser_routes.py`, `src/auth/origins.py`.
- Extend `src/auth/session_store.py`, `src/auth/routes.py`, `src/auth/middleware.py`, `src/panels/routes.py`, `src/api_server.py`.
- Create `tests/test_auth_device_service.py`, `tests/test_auth_device_routes.py`, `tests/test_auth_tv_permissions.py`, `tests/test_auth_session_routes.py`.
- Create `tests/fixtures/auth/tv-sign-in-v1.json` and `docs/api/tv-sign-in.md` as the canonical wire examples and API contract.

**Interfaces:**

- `DeviceService.authorize(client_id: str, device_name: str, app_version: str, source: str) -> DeviceChallenge`.
- `inspect(user_code: str, browser_session: SessionRecord) -> PendingDevice`; `decide(user_code: str, browser_session: SessionRecord, approve: bool) -> None`.
- `exchange(device_code: str, client_id: str) -> DeviceTokenResult`; `cancel(device_code: str) -> None`.
- `login(username: str, password: str, client_id: str, device_name: str, app_version: str) -> DeviceTokenResult` uses Task 1's verification helper and shared login lockout, not a browser-cookie exchange.
- `authenticate_tv(token: str) -> SessionRecord | None`; authorization middleware sets `request.scope["auth_kind"]`, `auth_user`, and `auth_session_id` only after validation.
- `DeviceChallenge` and `DeviceTokenResult` use the exact JSON fields/values in the spec. API fields are snake_case. New endpoint failures preserve stable `error` plus `detail`; clients must parse this independently from legacy HTTP error mapping.
- `require_browser_session(request) -> SessionRecord` never accepts a TV/MCP bearer; `require_browser_mutation(request) -> SessionRecord` additionally checks exact trusted origin, JSON and session-bound CSRF.

- [ ] Write service tests with fake clock/randomness: expiry at 600 seconds, collision retry, 5-second polling, persistent slow-down, denied/cancelled/replayed challenge, duplicate approval, concurrent exchange with exactly one token, account change between approval and exchange, and enrollment disable races. Record approving browser session ID and require it still active at redemption.
- [ ] Write route tests for all three methods (QR and manual code use identical approve/exchange endpoints), password lockout shared across both password endpoints, CSRF/origin rejection, anonymous admin rejection, auth off/setup required, `no-store`, rate limits, lost exchange response, and secret-free list/log responses.
- [ ] Write permission tests: TV can perform exactly the six allowed operations plus self-revoke; cannot alter name/backdrop or unknown PATCH fields; mixed allowed/forbidden PATCH changes nothing; cannot use `/v1`, MCP, session APIs, plugins or account mutations; invalid TV bearer plus valid cookie fails; revoked bearer on public frame endpoint fails while anonymous frame requests retain current behavior.
- [ ] Run `python -m pytest tests/test_auth_device_service.py tests/test_auth_device_routes.py tests/test_auth_tv_permissions.py tests/test_auth_session_routes.py -q`; confirm intended failures.
- [ ] Implement new endpoints, transactional challenges/limits/CSRF storage and default-on enrollment setting. Retain revoked/consumed tombstones through their original expiry; clean bounded expired records. Bound strings/body sizes, use constant-time secret comparisons where applicable, redact bodies/authorization in errors. Limit active sessions and challenges before issuing credentials.
- [ ] Extend `/auth/status` and enforce TV identity before public-path bypasses. Validate raw PATCH field keys before existing Pydantic parsing. Browser auth remains admin; no downgrade/fallback when a TV token is presented.
- [ ] Capture fixtures for enabled, disabled, old-server capability absence, setup required, challenge, every polling outcome, successful token, revoked token and session summary. Include custom port, IPv6 and proxy-prefix URL examples without real secrets. Document all wire status codes, including 429/Retry-After and invalid credential behavior.
- [ ] Run the four new suites plus `tests/test_auth_mcp_bearer.py`, `tests/test_auth_mcp_token_routes.py`, `tests/test_auth_contract.py`, `tests/test_panels_api.py`, `tests/test_panels_public_access.py`, and `tests/test_panels_contract.py`. Require all passed. Run Ruff on changed Python files.
- [ ] Commit with message `feat(auth): add scoped TV sign-in and session management`.

## Task 3: Phone/desktop activation and Signed-in devices

**Files — FiestaBoard:**

- Create `web/app/routes/activate.tsx`, `web/src/components/settings/signed-in-devices.tsx`, `web/src/lib/api/sessions.ts`, `web/src/lib/safe-redirect.ts`.
- Modify `web/app/routes.ts`, `web/app/routes/login.tsx`, `web/src/lib/chromeless.ts`, `web/src/components/account-section.tsx`, `web/src/lib/api/auth.ts`, `web/src/lib/api.ts`, `web/messages/en.json`, `web/vite.config.ts`.
- Create `web/public/sw-auth-cache-cleanup.js` for awaited activation-time removal of old FiestaBoard caches, imported by the retiring worker. Current `next` already removed runtime caching.
- Extend locale files according to existing translation policy; keep new strings in translation resources.
- Create `web/src/__tests__/activate.test.tsx`, `web/src/__tests__/signed-in-devices.test.tsx`, `web/src/__tests__/safe-redirect.test.ts`, `web/tests/device-sign-in.spec.ts`.
- Extend `web/src/__tests__/account-section.test.tsx`, `web/src/__tests__/api-auth.test.ts` and existing base-path/ingress tests.

**Interfaces:**

- Typed `sessionsApi` mirrors Task 2 endpoints: `getContext`, `inspectDevice`, `approveDevice`, `denyDevice`, `listSessions`, `revokeSession`, `revokeSessions`, `getDeviceSettings`, `updateDeviceSettings`.
- `safeRedirect(value: string | null) -> string` accepts only app-relative paths within the current installation, rejects schemes/authorities/protocol-relative paths, backslashes/control characters and encoded bypasses; fallback `/`.
- `SignedInDevices` loads the browser-only list and current session marker. The activation route owns authentication/loading/error states without wizard takeover.

- [ ] Write UI tests asserting scan/direct visit renders no approval side effect, anonymous login preserves the code, already authenticated browsers reach consent, manual code normalization works, denied/expired/used code cannot approve, disabled enrollment is explained, current browser is identified, revoke affects only chosen row, bulk confirmation is required and enrollment disable retains management.
- [ ] Test `safeRedirect` with `/activate?user_code=WDJB-MJHT`, `https://attacker.invalid`, `//attacker.invalid`, backslashes, encoded delimiters, and ingress-prefixed paths. Test that code/credentials never appear in external links or analytics.
- [ ] Run from `web`: `npm run test:run -- src/__tests__/activate.test.tsx src/__tests__/signed-in-devices.test.tsx src/__tests__/safe-redirect.test.ts`; confirm intended failures.
- [ ] Implement `/activate` as a chromeless route, using existing `apiUrl`/`appUrl` and router basename rules. Preserve code through `/login?redirect=...`; sanitize existing login redirect usage. Display server address, device metadata, matching code and the explicit permission explanation before Allow/Deny. Add a no-referrer policy to the activation surface.
- [x] Preserve service-worker retirement on current `next`: await removal of the previous `offlineCache` and owned static caches, then unregister without a fetch handler. Production Playwright tests seed the old runtime cache, activate the retiring worker, revoke a browser, go offline, and assert stale authenticated status/device lists cannot be served; repeat beneath a proxy prefix.
- [ ] Add the Account card with names, category, method, timestamps/expiry, This browser, per-session revoke and bulk actions. Display the legacy-password limitation for legacy clients. Do not imply last active means online. Update logout to use registered-session revocation.
- [ ] Add Playwright coverage with separate approval-browser and TV HTTP contexts: approve through fresh login, verify TV reads, revoke TV, and assert next TV request is 401 while approval browser remains signed in; revoke a second browser while the current browser keeps working.
- [ ] Run the focused Vitest tests plus existing Account/auth/base-path suites, `npm run typecheck`, `npm run lint`, `npm run build`, and `npm run test:integration -- tests/device-sign-in.spec.ts` against the paired test backend. Require successful exits and passing assertions.
- [ ] Commit with message `feat(web): add TV activation and signed-in device controls`.

## Task 4: Apple TV sign-in and credential migration

**Files — fiestaboard-appletv:**

- Modify `Sources/Core/Models.swift`, `Sources/Core/FiestaClient.swift`, `Sources/Core/Credentials.swift`, `Sources/Core/ConnectionStore.swift`.
- Create `Sources/Core/DeviceAuthorization.swift`, `Sources/UI/DeviceSignInModel.swift`, `Sources/UI/DeviceSignInScreen.swift`, `Sources/UI/QRCodeView.swift`.
- Modify `Sources/UI/SignInScreen.swift`, `Sources/UI/AppModel.swift`, `Sources/UI/SettingsScreen.swift` for routing, lifecycle, sign-out and accurate privacy copy.
- Create `Tests/DeviceAuthorizationTests.swift`, `Tests/DeviceSignInModelTests.swift`, `Tests/QRCodeTests.swift`, `UITests/DeviceSignInUITests.swift`, `Tests/Fixtures/tv-sign-in-v1.json` copied with provenance from Task 2.
- Extend `Tests/FiestaClientTests.swift`, `Tests/CredentialsTests.swift`, `Tests/ConnectionStoreTests.swift`, `UITests/FixtureHTTPServer.swift`; update `docs/PUBLISHING.md` and coupled privacy artifacts specified there.

**Interfaces:**

- Wire types: `TVSignInCapability`, `DeviceChallenge`, `DeviceTokenResult`, `DevicePollError`. Missing capability is unsupported; new response errors do not use the existing blanket 409 → setup-required mapping.
- `FiestaClient.beginDeviceSignIn(deviceName: String, appVersion: String) async throws -> DeviceChallenge`; `pollDeviceSignIn(deviceCode: String) async throws -> DeviceTokenResult`; `cancelDeviceSignIn(deviceCode: String) async throws`; `loginDevice(username: String, password: String, deviceName: String, appVersion: String) async throws -> DeviceTokenResult`; `revokeDeviceSession() async throws`.
- Tagged credential cases: legacy username/password and device token/session ID/expiry. Keep the existing credential-store protocol and old decoding compatibility.
- `ConnectionStore.adoptDeviceCredential(_ result: DeviceTokenResult, expectedGeneration: UUID) async throws` stores successfully, validates access, then marks signed in. Factor generation-safe adoption without making generation publicly mutable. A persistence failure cannot show success.
- `DeviceSignInModel` owns one cancellable polling task, expiry, retry/slow-down and activation state; inject time/sleep/client interfaces for deterministic tests.

- [ ] Write tests for capability fallback, QR/manual URL identical challenge, success → secure token only, direct password → same token kind, one-time migration deletes password only after replacement is saved, token 401 never invokes password login, revoke/sign-out across restart, and Keychain write failure.
- [ ] Test old-host completion after host switch, sign-out during redemption, foreground/background polling, server restart, concurrent requests, expiry, 429/slow-down, transport backoff and discarded challenge secrets on cold restart. Reject cross-origin/HTTPS-downgrade redirect forwarding, including copied cookie/token cases.
- [ ] Run `./build-and-run.sh --test`; confirm new tests fail for missing behavior before implementation.
- [ ] Implement the client/state machine and tagged credential storage. Keep legacy re-login only for legacy credentials on unsupported or enrollment-disabled servers. On opted-in servers, migrate a stored password at most once into a device credential; distinguish failed-password/transport conditions from unsupported capability rather than silently downgrading.
- [ ] Build the activation screen using local Core Image QR encoding, four-module quiet zone and integer scaling. Show URL/code as text; retain direct password entry and Back/New code. Wire app lifecycle cancellation and accessible focus/status updates. Adopt new enrollment only when capability says enabled.
- [ ] Implement best-effort server self-revocation on Sign out/Forget plus immediate local cancellation and secure deletion. If offline, do not claim server revocation succeeded; Account remains the reliable remote-revoke path. Preserve host/default-panel semantics and Top Shelf exclusions.
- [ ] Run `./build-and-run.sh --test` and required repository guards/unsigned release archive through the existing CI workflow. Require passing unit, renderer and remote-navigation checks; exercise QR physically during Task 6.
- [ ] Commit with message `feat(tvos): support revocable QR code and password sign-in`; prepare PR against `main`, referencing the server contract/version and beta-channel rollout.

## Task 5: Android TV / Google TV sign-in and credential migration

**Files — fiestaboard-androidtv:**

- Modify `core/src/main/kotlin/com/fiestaboard/core/FiestaClient.kt`, `core/src/main/kotlin/com/fiestaboard/core/ConnectionRepository.kt`.
- Create `core/src/main/kotlin/com/fiestaboard/core/DeviceAuthorization.kt` and `app/src/main/java/com/fiestaboard/androidtv/ui/DeviceSignInScreen.kt`.
- Modify `app/src/main/java/com/fiestaboard/androidtv/data/AndroidPersistence.kt`, `app/src/main/java/com/fiestaboard/androidtv/AppModel.kt`, `app/src/main/java/com/fiestaboard/androidtv/ui/ConnectScreen.kt`, `app/src/main/java/com/fiestaboard/androidtv/ui/SettingsScreen.kt`, `app/build.gradle.kts`.
- Create `core/src/test/kotlin/com/fiestaboard/core/DeviceAuthorizationTest.kt`, `app/src/test/java/com/fiestaboard/androidtv/DeviceSignInTest.kt`, `app/src/androidTest/java/com/fiestaboard/androidtv/DeviceSignInFlowTest.kt`, `core/src/test/resources/tv-sign-in-v1.json` copied with provenance from Task 2.
- Extend existing `FiestaClientTest`, `ConnectionRepositoryTest`, `AppModelTest`, `TvFlowTest`, `scripts/fixture-server.py`, `docs/PARITY.md`, `docs/VALIDATION.md`, `docs/PUBLISHING.md`.

**Interfaces:**

- Mirror Task 4 wire type/method names in idiomatic Kotlin: `suspend fun beginDeviceSignIn(deviceName: String, appVersion: String): DeviceChallenge`, `pollDeviceSignIn(deviceCode: String): DeviceTokenResult`, `cancelDeviceSignIn(deviceCode: String)`, `loginDevice(...)`, `revokeDeviceSession()`.
- Replace `Credential` with a sealed tagged legacy/device representation, preserving current JSON reads and host-bound Keystore encryption. Repository adoption checks its captured generation, persists before announcing success, and never falls back from a rejected device credential to a legacy password.
- Core polling state machine emits state to `AppModel`; lifecycle owns the coroutine job. Keep UI/Android types out of `core`.

- [ ] Write the same contract/error/migration tests as Task 4 using the shared fixture and MockWebServer. Add process-recreation, encrypted-store write failure, AES-GCM authentication failure, concurrent 401, delayed response after `cancelPending`, and Home/Back cancellation assertions.
- [ ] Run `./gradlew :core:test :app:testDebugUnitTest`; confirm missing new behavior causes the expected failures.
- [ ] Implement capability decoding, scoped bearer requests, distinct polling errors and credential-kind recovery. Retain disabled redirects and same-origin restrictions. Persist only the new device token after successful migration.
- [ ] Implement the Compose activation screen, manual desktop URL/code, QR using a pinned/reviewed ZXing core dependency, and retained password option. No camera/scanner integration. Preserve D-pad focus, TalkBack, retry/back actions, and lifecycle stop/resume. Implement local sign-out/Forget and best-effort server self-revoke with the same offline semantics as tvOS.
- [ ] Run `./gradlew :core:test :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest :app:assembleRelease :app:bundleRelease` and `python3 scripts/check-artifacts.py`. On this Mac the repository's `scripts/gradle-local.sh` can supply the required local JDK/SDK setup.
- [ ] On a dedicated emulator/TV, run `./gradlew :app:connectedDebugAndroidTest`; do not reset a customer's configured app. Require all tests/lint/builds passed, and record physical testing in Task 6.
- [ ] Commit with message `feat(androidtv): support revocable QR code and password sign-in`; prepare PR against `main` with server contract/version and beta instructions.

## Task 6: Cross-platform acceptance and staged beta

**Files:** Add `docs/testing/revocable-sign-ins-beta.md` in FiestaBoard; update both TV `docs/VALIDATION.md` where present and `docs/PUBLISHING.md`, plus FiestaBoard `docs/api/tv-sign-in.md` and `docs/features/fiestapanel.md`.

**Interfaces:** Builds identify server commit, app version/build, fixture version and device/OS. Evidence records synthetic test accounts only; no live QR, code, password, token or cookie in published artifacts.

- [ ] Run browser/TV contract suites against the same built `next` server. Test each TV app with QR approval on iPhone and Android, manual URL/code on desktop, and direct TV password entry. Test both fresh and already-signed-in approval browsers.
- [ ] Confirm all resulting sign-ins appear independently in Account with correct method/current-browser marker. Revoke TV A while TV B and desktop keep working; revoke desktop B while desktop A stays; exercise Sign out others and everywhere. Verify password/username changes and auth disable/re-enable invalidate old credentials and pending approval.
- [ ] Test clean install, auth disabled, incomplete setup, enrollment disabled, old server/new app, new server/old app, saved-password migration, reboot, offline startup, session expiry using controlled time, revoked default-panel launch, storage failure and server outage. Verify no automatic password retry after token revocation.
- [ ] Test simultaneous requests, double approval, double redemption, stale QR, cancelled/replaced challenge, approval after browser logout/revoke, invalid code guessing and mixed forbidden PATCH fields. Match the behavior to the documented errors, not a generic spinner.
- [ ] Use custom port, IPv4, IPv6, `.local`, a reachable HTTPS reverse proxy and a base-path deployment. Test that a phone on cellular cannot reach a LAN-only server and that the manual reachable-portal/code route explains the remedy. Reject certificate errors and hostile redirects without exposing credentials.
- [ ] Physically scan at 1080p/4K from normal viewing distance; exercise Siri Remote/D-pad and VoiceOver/TalkBack. Run a 24-hour signage soak with app background/resume, server restart and mid-soak revocation; record requests stop when backgrounded/revoked and credentials survive normal restarts.
- [ ] Rehearse upgrade from current sessions and rollback to the prior server build with the same data volume. Require one-time login reset, legacy cookie cutoff preserved, old server rejecting new credentials, and explicit fallback sign-in on TVs. Inspect backup/restore handling for registry omission and auth rollback; fail release if a revoked credential resurrects.
- [ ] Land coordinated server/web PR to `next` after required checks; publish the approved server beta using the existing release workflow. Ship TV builds through TestFlight and Play internal testing, then wider testing after qualification. Existing signing/account access requirements in each publishing document apply; this plan does not upload builds.
- [ ] Pilot with a small opt-in group. Document **Settings → Account → TV sign-in**, the migration logout, all three sign-in methods, revocation, public-panel and legacy-app limitations. Expand only after the test matrix/soak/rollback pass with no unresolved auth bypass, credential leak or lost-sign-in defect.

## Rollout and rollback decisions

Server first, apps second. Updated apps can be released before universal server adoption because they negotiate capabilities and preserve older-server password login. New enrollment stays off until the administrator opts in. Do not treat the feature switch as an access kill switch: use per-device/bulk revocation to remove access. Disable enrollment to stop new grants during an incident while preserving session management.

If server rollback is necessary, expect a fresh browser sign-in and explicit TV reauthentication. The managed downgrade path must first advance the auth cutoff and revoke all sessions; a manual image switch requires Sign out everywhere first. Retain current auth cutoff and registry files; older code must ignore the new database and reject the new credential format. Do not restore old auth state to make sessions appear to work.

## Plan verification and handoff

The plan is reviewed against the design for endpoint consistency, migration, lifetime values, both native platforms, three entry methods, web session management, permissions, rollout and rollback. Proposed tests/commands above are implementation gates, **not test results from this planning session**.

Review the design and this plan before starting product implementation. The first execution step is isolated branches from fresh bases and Task 1; the final feature deliverable is the recorded matrix in Task 6, not merely a QR image on a sign-in screen.
