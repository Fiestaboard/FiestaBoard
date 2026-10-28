<!-- cspell:words worktree transactionally Backgrounding Siri -->

# Revocable sign-ins and TV activation — beta design

Status: approved design, implemented for the next beta. See the qualification record in `docs/internal/development/TV_SIGN_IN_BETA.md` for validation and release limitations.

## Intent and confirmed scope

Let someone connect either native TV app without typing an account password with a remote. Support three equivalent TV entry points: scanning a QR code, opening a displayed URL on a phone or desktop and typing a code, and entering username/password directly on the TV. On a supporting server, every option issues the same kind of revocable TV credential; direct password entry must not leave a saved account password.

The user confirmed that **TVs and web browsers** belong in revocable sign-in management. Put it in **Settings → Account → Signed-in devices**, not in panel configuration. A sign-in belongs to one server/account/client, independent of which panel is displayed. Several devices can show one panel, and one TV can switch panels.

The portal is the selected self-hosted FiestaBoard instance. No FiestaBoard cloud account, public pairing relay, new mobile app, or subscription is required. Both the TV and approval browser must be able to reach that instance. Password sign-in remains compatible with older servers.

## Source baseline

Inspected on 2026-10-18:

| Project | Baseline | Relevant existing behavior |
| --- | --- | --- |
| FiestaBoard | local `origin/next` `bffc3ff0d`; auth source inspected in checkout `f84b1d3d3` and compared with `origin/next` | FastAPI, React Router web UI; signed cookies; 7-day ordinary and 30-day remembered sessions; no individual session revocation |
| Apple TV | `fiestaboard-appletv` `4053808` | SwiftUI; ephemeral URLSession cookies; Keychain username/password; password replay on restart/401 |
| Android TV / Google TV | `fiestaboard-androidtv` `3f811c1` | Kotlin/Compose; in-memory OkHttp cookies; Keystore-encrypted username/password; serialized password recovery |

The local worktree named `next` is stale; implementation must branch from freshly fetched `origin/next`, not that worktree. Existing checkouts contain unrelated work. This design and its plan are documentation only in the main FiestaBoard checkout.

The old Beta settings page is retired on current code. Do not add this feature to deprecated `/settings/beta`. TV sign-in is enabled by default, with its administrative control under Account. Existing `/auth/*` routes bypass middleware and must explicitly authenticate sensitive operations. Existing singular `/panel/*` reads are deliberately public; plural `/panels` management is protected.

## Experience

### TV

1. Discover or manually choose a FiestaBoard as today. Open servers continue directly; unfinished account setup directs the user to the portal.
2. On supporting, opted-in servers, offer **Sign in with a phone or computer** and **Use username and password**. The former creates a challenge and displays a QR, `http(s)://<chosen-board>[:port][/prefix]/activate`, an eight-character code such as `WDJB-MJHT`, board name/address, and a ten-minute expiry.
3. Scanning opens `/activate?user_code=...`. The manual URL opens the same page with a code-entry field. This works from desktop browsers as well as phones.
4. The user signs into that FiestaBoard if necessary. The page shows the requesting TV/platform, server, matching code, and requested permissions. **Allow this TV** / **Deny** requires an explicit action; opening or scanning the URL never authorizes it.
5. The TV checks status every five seconds. After approval it securely stores its credential, verifies access, and opens its saved default panel or panel picker.
6. Direct TV password entry verifies credentials and returns a TV credential through a separate endpoint. Keep the password only in memory for the request and clear the form after successful storage.

QR and manual code entry are two presentations of one challenge. The QR contains the public user code and portal URL, never a credential, private device code, or password. A browser session used to approve a TV remains separate from that TV's credential.

Offer **New code**, **Use username and password**, and **Back**. Handle expired, denied, cancelled, offline, server-starting, disabled, rate-limited, storage-failed, and revoked states with distinct messages. No automatic login through an old saved password after a device credential is revoked.

### Web Account management

Show a unified **Signed-in devices** list with:

- Name, category (Apple TV, Android/Google TV, browser, or legacy/unknown client), app version when supplied, and sign-in method (QR/code approval or password).
- Created, last active, and expiry timestamps; a **This browser** indicator.
- **Revoke** per row, **Sign out other devices** retaining the current browser, and **Sign out everywhere** including the current browser. Confirm bulk actions.
- A **TV sign-in** switch controlling the new native TV credential endpoints and pairing. Enabled by default on upgraded and fresh installations; preserve an explicit administrative disable. The beta release channel gates testing, with no separate opt-in. Session tracking for web sign-ins is server infrastructure on `next`, independent of this setting.

Disabling TV sign-in cancels outstanding challenges and prevents new TV credentials; existing credentials remain valid until individually/bulk revoked or expired. Explain that beside the switch and keep management visible when off. This separates stopping enrollment from removing access.

Names, platform, and User-Agent are descriptive client input, not attestation. Bound and escape them. Last-active is approximate, updated at most once per five minutes; do not describe it as an online-presence indicator. No IP geolocation or device fingerprinting. Do not add panel association/telemetry in this beta.

## Architecture decision

Use a device-authorization-style handshake with an opaque per-TV bearer credential, plus a persistent registry for browser sessions. The secondary-browser approval and polling pattern is described by [RFC 8628](https://www.rfc-editor.org/rfc/rfc8628.html). This is a FiestaBoard JSON protocol inspired by that flow, **not a claim of full OAuth conformance**: it uses custom endpoints and supports the project's existing trusted-network HTTP deployments.

Alternatives considered:

| Approach | Tradeoff |
| --- | --- |
| Hand the TV a normal remembered cookie | Smallest change, but current 30-day expiry would require another scan and lacks device-specific revocation |
| Opaque, scoped TV credential plus registry — recommended | Durable across restarts; immediate individual revocation; straightforward clients; a stolen credential remains useful until revoked/expired |
| Short-lived access tokens plus rotating refresh tokens | Shorter access-token lifetime, but adds refresh rotation, replay detection, concurrency and crash-recovery machinery to both apps |

Jev weakly preferred the opaque credential option for the initial TV-only comparison. That advisory result is not proof, and predates the confirmed browser-session scope. The recommendation is based on explicit server-side revocation checks, limited TV permissions, and avoiding a refresh subsystem in the beta.

## Credentials and persistence

Use a new `src/auth/session_store.py` backed by standard-library SQLite at `get_data_dir()/auth_sessions.sqlite3`. Keep session, challenge, CSRF, and enrollment configuration tables there. Use transactional mutations, a schema version, foreign keys as applicable, busy timeout, and restrictive file permissions including journal/sidecar files. This provides atomic single-use redemption across requests without introducing Redis. An unavailable/corrupt store fails closed; never silently turn authentication off or fall back to stateless acceptance.

Persist only SHA-256 digests of high-entropy credentials/challenge secrets, not plaintext. Store opaque session ID, username, account invalidation generation, kind, display name, client metadata, method, created/expiry/revocation times, and bounded last-active. IDs used in management URLs are not credentials. Do not store passwords in this database. Bound total active sessions to 200 per account; refuse excess with an actionable message rather than silently evicting another device.

TV credentials: `fb_tv_` plus 32 cryptographically random bytes encoded base64url. Fixed lifetime **365 days**, no sliding renewal or refresh token in beta. Store in Keychain on tvOS and existing Keystore-backed encryption on Android, keyed by normalized scheme/host/port/base-path. Every use checks registry state and the account invalidation generation. Prompt for any of the three sign-in methods after expiry/revocation. Keep tokens out of URLs, browser storage, logs, analytics, Top Shelf manifests, and discovery probes.

Browser sessions: retain cookie name `fiestaboard_session`, current HttpOnly/SameSite/Secure behavior, remember-me behavior, TTL defaults and environment overrides. Issue a versioned signed payload `v2.<encoded-user>.<issued-ms>.<expires-ms>.<nonce>.<signature>` and register its full-token digest before returning it. `verify_session` must validate both signature/account watermark and an active registry row. No registry row means no access. Older servers reject the v2 shape rather than accepting it without revocation checks.

`POST /auth/logout` revokes the current row before clearing the cookie; clearing a cookie alone is insufficient. Password/username changes revoke all prior sessions/challenges and preserve the existing behavior of issuing a fresh browser session to the person making the change. Disabling authentication deletes/revokes the account's credentials and pending challenges before opening the instance. Account recreation must not revive them.

### Migration and rollback

- On first startup of the new auth implementation, advance `sessions_valid_after_ms` in `auth.json` once, beyond all previously issued legacy cookies. Record an idempotent migration marker there. Crash after cutoff but before marker may cause an extra logout, never unauthorized access.
- Reject v1 cookies on the new server. Existing browsers sign in once again and enter the registry. Avoid lazy adoption, which makes revoked legacy cookies difficult to distinguish from unobserved cookies.
- Existing TV builds still work against `/auth/login`; their cookies become registered legacy-client sessions. Those builds retain account passwords and can create a new session after revocation. Label this limitation in management and release notes; password rotation is necessary to exclude such a client permanently.
- Updated TV apps migrate to device credentials through the device-password endpoint on an opted-in server, using an existing stored password at most once. Delete the old password only after the replacement is stored and verified. Never silently revert from device-token mode to password replay.
- A server rollback rejects v2 browser cookies and `fb_tv_` tokens. Before every managed image rollback or leave-beta transition, advance the account cutoff and revoke all sessions/challenges; abort the image change if that write fails. This also prevents cookies created during an earlier rollback from resurrecting across repeated upgrade/downgrade cycles. For a manual image downgrade, first use Sign out everywhere. Users sign in again; updated TV apps explicitly offer legacy password sign-in on older servers. Do not restore an old `auth.json` as part of normal release rollback.
- Ordinary settings backups must not export active session/challenge credentials. Verify existing backup and updater behavior and document that a full filesystem/auth snapshot restore changes the security state; an intentional restore must invalidate credentials before exposing the instance. Loss of the registry must not turn formerly signed cookies back into valid sessions.

## API contract, version 1

Paths below are FastAPI paths. The public HTTP route prepends `/api` beneath the existing installation base path. JSON error bodies use `{ "error": "stable_code", "detail": "safe message" }` on new endpoints. All auth responses use `Cache-Control: no-store`.

Extend `GET /auth/status` additively with `session_management_supported: true`, `auth_kind: "browser" | "tv" | null`, and `tv_sign_in: { supported: true, enabled: boolean, protocol_version: 1 }`. Older apps ignore fields; newer apps treat missing capability as unsupported. Existing `enabled`, `setup_required`, `authenticated`, `username`, `mode`, and `first_run` semantics remain compatible. A valid TV bearer can report authenticated here without authorizing browser-only operations.

| Endpoint | Caller and behavior |
| --- | --- |
| `POST /auth/device/authorize` | Anonymous, enabled/provisioned instance and TV beta on. Body: `client_id` (`fiestaboard-tvos` or `fiestaboard-androidtv`), bounded `device_name`, `app_version`. Returns `device_code`, `user_code`, `verification_path: "/activate"`, `verification_path_complete`, `expires_in: 600`, `interval: 5` |
| `POST /auth/device/token` | TV sends private `device_code` and matching `client_id`; atomically consumes approved challenge and returns `access_token`, `token_type: "Bearer"`, `expires_in: 31536000`, `session_id`, `scope: "tv_panels"` |
| `POST /auth/device/cancel` | Possession of private `device_code` cancels an unconsumed challenge; idempotent |
| `POST /auth/device/login` | Username/password plus the same client metadata; same existing password verification and IP lockout as normal login; returns the same token result, creates no administrator cookie |
| `GET /auth/sessions/context` | Valid browser cookie only; returns session-bound CSRF nonce valid for 600 seconds, stored hashed in registry |
| `POST /auth/device/inspect` | Valid browser cookie, same-origin/CSRF checks, `user_code`; returns bounded TV metadata, code, remaining lifetime, and allowed operations; no private code or token |
| `POST /auth/device/approve`, `/deny` | Valid browser cookie, same-origin/CSRF checks, `user_code`; transitions a pending challenge once |
| `GET /auth/sessions` | Valid browser cookie only; returns session summaries and current session ID, never credential hashes or raw secrets |
| `DELETE /auth/sessions/{id}` | Valid browser cookie plus same-origin/CSRF checks; revoke one session belonging to the account, idempotent |
| `POST /auth/sessions/revoke` | Valid browser cookie plus same-origin/CSRF checks; `{ "include_current": false }` signs out others; true also advances the persisted account cutoff, signs out everyone and clears current cookie; cancels pending challenges in both cases |
| `DELETE /auth/device/session` | Valid TV bearer only; revoke itself, never another device |
| `GET`, `PUT /auth/device/settings` | Valid browser cookie; PUT also same-origin/CSRF; reads/writes `{ "enabled": boolean }`; cancellation on disable is transactional |

Use returned **paths**, combined with the TV's selected normalized base URL, to build approval URLs. Do not trust a supplied Host/forwarded header or let a response select a different authority. Preserve custom ports, IPv6 brackets, HTTPS and reverse-proxy prefixes. Client ID is an identifier, not a secret or proof of platform identity.

### Challenge lifecycle and abuse controls

- Generate 32 random bytes for the private device code. User codes are eight independent characters from `BCDFGHJKLMNPQRSTVWXYZ23456789`, displayed as `XXXX-XXXX`; uppercase and remove hyphens/spaces for comparison. Enforce active-code uniqueness with transactional retry on collision. Store a digest for lookup.
- States: pending → approved → consumed, or pending → denied/cancelled/expired. Approved challenges may also expire or be cancelled before consumption. Approval does not extend the original 600-second deadline. Bind approval to the approving account's current invalidation generation and browser session ID; recheck both at redemption so browser logout/revocation cannot leave a usable approval behind.
- Token polling: HTTP 400 `authorization_pending`; 400 `slow_down` increases all future intervals by five seconds; 400 `access_denied`; 400 `expired_token`; 400 `invalid_grant` for unknown/consumed/cancelled; 403 `feature_disabled`. Too-frequent polling never issues a token. HTTP 429 carries `Retry-After`; transport errors back off up to 30 seconds within the original expiry.
- Exactly one redemption succeeds under concurrent polls. Never replay the token response. If the success response is lost, the TV needs a new code; its orphan session is visible/revocable in Account and expires normally. Do not log a secret to make recovery easier.
- Separate limiter from password lockout: five starts/minute/source address, ten code inspections or decisions/minute/account/source address, maximum 100 live challenges per instance. Return 429 on limit. Store limiter state transactionally with bounded expiry cleanup; trust forwarded IPs only through existing trusted-proxy configuration.
- GET, link previews, prefetch, QR scan, and browser login never approve anything. Browser management and approval require a real browser session, JSON, exact allowed origin, and a session-bound CSRF nonce; missing/foreign origin or nonce fails closed. Behind supported proxies, derive effective origin only from trusted configuration. MCP/TV bearers cannot substitute for that cookie.
- New code/back/host switch/sign-out invalidate local work and best-effort cancel the old challenge. Generation guards stop late responses from storing a token in a replacement connection. Backgrounding stops polling; foregrounding resumes only a still-valid challenge. Challenge secrets remain in memory only.

## TV authorization boundary

`tv_panels` permits only `GET /auth/status`, `GET /panels`, `GET /panel/{ref}`, `GET /panel/{ref}/frame`, and `PATCH /panels/{id}` for these fields: `screen_diagonal_inches`, `screen_aspect_w`, `screen_aspect_h`, `calibration_scale`, `animations_enabled`, `render_style`. Self-revocation is separately permitted. Deny every other endpoint/method, including session management, account mutations, MCP, `/v1`, plugins, AI, panel creation/deletion and unrelated settings.

For PATCH, reject the **entire** request if any unrecognized or forbidden field is supplied, including fields Pydantic would normally ignore. Validate raw field names before parsing the existing update model. Browser sessions retain existing administrator permissions. Future TV functionality must extend this explicit permission contract and consent text deliberately.

Identify a presented TV bearer before public-path bypasses, validate it, and do not fall back to a browser cookie if it is invalid. Thus a revoked native app gets 401 on its next frame poll and stops displaying cached/live content. No header still follows the existing public `/panel/*` behavior. Revocation is not a new privacy boundary for existing anonymous panel URLs, nor does it erase content someone already saw. Preserve this distinction in UI/docs.

## Platform details

tvOS: extend `StoredCredential` with a tagged legacy-password/device-token representation, preserving old JSON and pre-JSON decoding. Use Keychain's existing device-only access policy. Change `ConnectionStore` recovery by credential kind and preserve generation checks. Render QR locally with [Core Image's QR generator](https://developer.apple.com/documentation/coreimage/cifilter-swift.class/qrcodegenerator()). Add a dedicated activation model/view and explicit cancellation. Prevent cross-origin or HTTPS-downgrade redirect credential forwarding. Keep credentials out of Top Shelf.

Android: use the same tagged credential model in `ConnectionPersistence` and current AES-GCM/Keystore persistence; preserve existing AAD host binding and old-record decoding. Keep OkHttp redirects disabled. Add core activation state/polling and Compose UI controlled by lifecycle. Generate locally with [ZXing QRCodeWriter](https://github.com/zxing/zxing/blob/master/core/src/main/java/com/google/zxing/qrcode/QRCodeWriter.java); only core encoding dependency, no scanner, camera permission or network QR service. Pin a reviewed dependency version during implementation.

Both: high-contrast QR, integer module scaling, four-module quiet zone, no decorative logo. Show readable URL and code independent of the image; support D-pad/Siri Remote focus and VoiceOver/TalkBack. Core Image rendering must add a quiet zone if absent. Verify scanning with actual iOS and Android camera apps at 1080p and 4K.

Existing LAN HTTP remains supported with the same trust boundary: QR avoids placing the account password on the TV, but does not encrypt phone login or bearer traffic. Explain trusted-network usage in existing connection/privacy copy; prefer configured HTTPS and never bypass certificate validation. The phone may need the same Wi-Fi/VPN. `.local` resolution can differ across phones; the manually typed reachable portal URL plus code is the fallback. Home Assistant ingress with separate HA login is not automatically a native-TV-accessible endpoint; use a server endpoint both participants can reach.

Fresh `origin/next` already retires the service worker. Preserve retirement: an owned activation handler awaits removal of FiestaBoard caches and unregisters, with no fetch handler. Do not restore offline runtime caching or allow cached authentication/session data to authorize access. Test retirement with the production bundle, including a proxy prefix.

## Success and release criteria

Every new sign-in is recorded and individually revocable; both TV apps support all three methods on opted-in servers, survive app/server restart with no password saved, and keep existing rendering/default-panel behavior. A revoked native app stops on its next request; a revoked browser cannot perform another protected operation. Outstanding responses already authorized before revocation can complete; future requests fail.

Release backend/web changes to FiestaBoard `next`, Apple TV through TestFlight, and Android/Google TV through internal testing, followed by closed testing as appropriate. Native enrollment is enabled by default; the beta channel is the testing gate. Ship server first, then compatible apps; require automated contract/security tests and real TV/phone/desktop acceptance before expanding the cohort. Beta exit includes a 24-hour signage soak, migration/downgrade rehearsal, and no unresolved authentication-boundary failures.

Implementation tasks and exact validation commands are in [the coordinated plan](../plans/2026-10-18-revocable-sign-ins.md).
