# TV sign-in beta qualification

This change targets FiestaBoard `next`, with matching Apple TV and Android TV
changes targeting their `main` branches. TV sign-in is enabled by default; an
administrator can disable it under Settings → Account. The `next`/beta release
channel is the rollout gate. Browser session tracking applies whenever sign-in
is enabled.

## Protocol and storage

The canonical shared fixture is `tests/fixtures/auth/tv-sign-in-v1.json`.
Both native repositories copy and decode this fixture, including error cases and
IPv4, IPv6, custom port and path-prefix URL examples. The internal API reference
is generated from the implementation. The approved design is in
`docs/internal/superpowers/specs/2026-10-18-revocable-sign-ins-design.md`.

`auth_sessions.sqlite3` is an auth-owned, private SQLite database. It contains
hashed browser/TV credentials, challenges, CSRF nonces, limits and the enrollment
setting. It is not included in portable settings backups. An independent server
restart must preserve this file alongside `auth.json` and `.session_key`.

On first migration, legacy cookies are invalidated once. New cookies have an
explicit version prefix that old servers reject. Managed image rollback and
Leave beta persist an account cutoff and revoke sessions before calling the
updater. A persistence failure blocks the image operation. Manual image changes
require Sign out everywhere first. A complete old data restore can restore old
revocation state; do not present it as a way to preserve revocations.

TV permissions are panel reads and six screen-presentation fields only. New
Apple TV FiestaBot functionality cannot use these credentials. Existing legacy
credentials retain their old capabilities until migration. Device sign-out
revokes only that TV; enrollment-off does not revoke existing credentials.

## Automated verification

- Server tests cover restart persistence, cookie copies after revocation,
  migration, cutoff failure, expiry, one-use concurrent redemption, poll backoff,
  approval-browser invalidation, rate/capacity limits, private hashed storage,
  CSRF/origin checks, strict PATCH fields and bearer-before-public-route handling.
- Web tests cover safe same-origin redirects, code entry and consent, errors,
  signed-in device controls, current-browser actions, all locale catalogs and
  service-worker retirement. Current `next` already retired runtime caching;
  the replacement retirement worker awaits FiestaBoard cache deletion and has
  no fetch handler. It preserves unrelated applications' caches.
- A live-server Playwright API smoke test verifies separate browser/TV sessions,
  approval, panel access, forbidden administration and immediate revocation.
- CI runs the built web app with a real auth-enabled server for browser approval,
  revocation and worker retirement at root and behind a path prefix. Local isolated
  Docker Chromium also verifies the production bundle against a real API: login,
  explicit consent, denial, revocation, consent-heading focus, and desktop plus
  390 × 844 layouts without horizontal overflow. The activation page has no axe
  WCAG 2 A/AA or 2.1 AA violations in that run. Native macOS Chromium launch
  remains sandbox-restricted; the Docker browser run provides local evidence.
- Native tests cover secure credential persistence, migration, scoped requests,
  cancellation, restart and revocation without password recovery. The Android
  emulator uses an isolated validation application ID. Apple TV simulator launch
  is locally restricted; CI owns simulator validation.

## Beta operator checks before wider rollout

Use a non-production instance on the beta release channel with a backup, and
install the matching native builds. Store publication and a 24-hour physical-device soak are
separate release activities and are not claimed by a code merge.

1. Pair Apple TV and Android TV by QR; repeat using a desktop URL and manual code.
2. Verify direct TV password sign-in creates its own device row, then restart
   each app and server without entering a password again.
3. Revoke each TV while displaying a panel. Confirm it stops authenticated polling
   and returns to sign-in. Repeat browser revocation in two separate browser profiles.
4. Deny, cancel and expire a code; disable enrollment during approval; disconnect
   and reconnect the network. Ensure retries cannot redeem a consumed code twice.
5. Check remote focus, QR readability and activation on a phone at TV viewing distance.
6. Test an HTTP LAN URL, HTTPS proxy, custom port, IPv6 address and supported prefix.
7. Run each physical TV for 24 hours, including sleep/wake and network interruption.
8. Exercise managed rollback and re-upgrade. Old cookies and revoked TV credentials
   must not regain access; sign in afresh after rollback.

To halt enrollment, turn off TV sign-in under Settings → Account. This preserves
existing access; revoke sessions in Signed-in devices to remove active access.
