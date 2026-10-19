---
sidebar_position: 9
description: "FiestaBoard ships with a built-in username/password login. Decide on first run whether to keep it on or skip it; both options are one click."
keywords: [FiestaBoard authentication, login, security, password, internet exposed, VPS]
---

# Authentication

FiestaBoard ships with a built-in username + password login. The first time
you open the UI on a fresh install you'll be asked whether to keep it on
or skip it:

- **Enable login (recommended).** Required for any FiestaBoard reachable
  from the public internet (e.g. a VPS).
- **Continue without login.** Convenient for a private LAN-only install
  behind your home router.

Your choice is persisted to `data/auth.json` so you'll never see the
picker again on this install. You can override it later with the
`FIESTABOARD_AUTH_ENABLED` env var.

When auth is on, management endpoints require a valid session. Public health,
login and panel display endpoints are listed below.

## Quick start

1. **Open the web UI.** On a fresh install you'll land on `/login` with
   the first-run picker.

2. **Enable login.** Click *Enable login (recommended)*, then set a
   username and password.

3. **Sign in.** You'll be redirected to the dashboard with a session
   cookie. Tick **Keep me logged in** (on by default) to stay signed in
   across browser restarts; clear it on a shared or public computer so the
   session ends when you close the browser. Manage your account (rename,
   change password, sign out) from **Settings → Account**.

To skip login entirely on a LAN install, click *Continue without login*
on the first-run picker — the middleware will short-circuit on every
future request.

## How it works

- **Auth mode** is a tri-state: `enabled` / `disabled` / `undecided`.
  - `FIESTABOARD_AUTH_ENABLED=true` (or `1`/`yes`/`on`) pins it to
    `enabled`.
  - `FIESTABOARD_AUTH_ENABLED=false` (or `0`/`no`/`off`) pins it to
    `disabled`.
  - Unset → fall back to the persisted preference in `data/auth.json`.
  - No env var, no persisted preference → `undecided`, which is treated
    as *enforced* (secure by default) and surfaces the first-run picker.
- **Passwords** are hashed with `hashlib.scrypt` (N=2¹⁵, r=8, p=1) and
  stored in `data/auth.json` (mode `0600`).
- **Browser sessions** use signed, versioned cookies plus a server-side registry.
  `data/auth_sessions.sqlite3` stores only credential hashes and sign-in metadata
  (mode `0600`). The signing key remains in `data/.session_key`. Each sign-in
  can be revoked independently, including copies of its cookie.
- **Cookies** are `HttpOnly`, `SameSite=Lax`, and `Secure` when the request
  comes in over HTTPS (FiestaBoard trusts the `X-Forwarded-Proto` header
  set by its bundled nginx).
- **"Keep me logged in"** controls how long the session survives:
  - **Checked** → a *persistent* cookie with a `Max-Age` (30 days by
    default) that outlives browser restarts.
  - **Unchecked** → a *session* cookie (no `Max-Age`) that the browser
    discards when it closes. The token's signed `expires_at` still caps
    the server-side lifetime at the normal session TTL (7 days) so a
    leaked cookie can't live indefinitely on a browser that never closes.
- **Brute-force protection.** After 10 failed logins from the same client
  IP in 60 seconds the endpoint returns `429 Too Many Requests`.
- **Stolen-cookie revocation.** Every password or username change bumps
  the per-user session watermark, so any previously-issued cookies stop
  working.

## Configuration reference

| Variable | Default | Description |
| --- | --- | --- |
| `FIESTABOARD_AUTH_ENABLED` | *(unset, first-run picker)* | `true`/`1`/`yes`/`on` force-enables, `false`/`0`/`no`/`off` force-disables. Unset = use stored preference; if none, show the first-run picker. |
| `FIESTABOARD_SESSION_TTL_SECONDS` | `604800` (7d) | Lifetime for a normal sign-in (without "Keep me logged in"), in seconds. Caps the session-cookie token. |
| `FIESTABOARD_REMEMBER_ME_TTL_SECONDS` | `2592000` (30d) | Lifetime when "Keep me logged in" is checked, in seconds. Sets both the persistent cookie's `Max-Age` and the token expiry. |
| `FIESTABOARD_MCP_TOKEN` | *(unset)* | Pre-shared bearer token for `/api/mcp/`. Takes precedence over a token stored from **Settings → AI**, and disables the UI's rotate/revoke buttons. See [MCP clients and the bearer token](#mcp-clients-and-the-bearer-token). |
| `FIESTABOARD_CORS_ORIGINS` | *(unset, no credentialed cross-origin access)* | Comma-separated list of exact origins allowed to send credentials on cross-origin browser requests. See [Cross-origin browser access](#cross-origin-browser-access-cors). |

## Public endpoints

These remain reachable without authentication so health-checks, the login
page itself, and the OpenAPI docs keep working:

- `GET /`, `GET /health`
- Login, setup and status under `/auth/*`; device approval and session management
  explicitly require browser authentication.
- `GET /openapi.json`, `/internal/openapi.json`, `/docs`, `/redoc`
- `GET /panel/{panel}` and `GET /panel/{panel}/frame`, the read-only [frame endpoints](/docs/development/output-stream-api) a FiestaPanel TV reads

Everything else (status, config, pages, plugins, etc.) requires a valid
session cookie.

## MCP clients and the bearer token

External MCP clients — Claude Desktop, Claude Code — can't drive a
cookie-based login, so they authenticate to `/api/mcp/` with a pre-shared
bearer token instead of a session cookie. Configure one in
**Settings → AI**, or by setting `FIESTABOARD_MCP_TOKEN`.

:::warning Behaviour change: a configured token is now enforced in every auth mode

If a token is configured, `/api/mcp/` **requires** it — including when you
chose *Continue without login*. Previously the token was ignored whenever
auth was disabled, so a client could reach `/api/mcp/` without sending it.

If an MCP client that used to work starts returning `401`, put the token in
its config so it sends `Authorization: Bearer <your-token>`. Alternatively,
clear the token in **Settings → AI** if you want `/api/mcp/` to
stay open.

**Installs with no token configured are unaffected** — they behave exactly
as before.
:::

On an install where you chose *Continue without login* there is no session
for the token-management routes (`GET` / `POST` / `DELETE
/auth/mcp-token`) to check, so possession of the current token stands in
for one: once a token exists, managing it requires sending that token as an
`Authorization: Bearer` header, and requests without it get a `401`. Only
the first mint is open — until a token exists the whole API is open anyway,
so gating it would protect nothing. (Earlier releases left these routes
fully open on such installs, so anyone who could reach the port could
rotate or revoke a Settings-stored token — fixed in
Fiestaboard/FiestaBoard#1825.) The stored token also guards the one way
around that gate. With the login disabled by preference, re-enabling it
(`POST /auth/preference` with `enabled: true`) and registering the first
admin (`POST /auth/setup`) would each hand out a session that can rotate or
revoke the token — so while a stored token exists, both of those requests
must present it as an `Authorization: Bearer` header too, and are refused
with a `403` otherwise (Fiestaboard/FiestaBoard#1880). Turning the login
*off* is never gated; it cannot take anything over. If you chose *Continue
without login* and later want to add one, send the token with the request
or clear it in **Settings → AI** first. A token pinned by
`FIESTABOARD_MCP_TOKEN` is not gated this way because there is nothing to
hijack: while it is set, both mutating routes refuse with `409` and the
token cannot be changed over the network at all.

## Cross-origin browser access (CORS)

The web UI and the API are served from the same origin (nginx fronts both),
so CORS only affects third-party callers — for example a dashboard of your
own, on a different host or port, calling the FiestaBoard API from a
browser.

:::warning Behaviour change: credentialed cross-origin requests need an allowlist

Any origin may still make **anonymous** cross-origin requests, exactly as
before. What changed is that **no** origin may send credentials (cookies,
TLS client certificates) unless you list it. Previously every origin on the
internet held a credentialed grant to the whole API, so any page you
visited could drive your board.

If your own page calls the API with `credentials: "include"`, list its
origin in `FIESTABOARD_CORS_ORIGINS`:

```bash
FIESTABOARD_CORS_ORIGINS=https://dashboard.example,http://192.0.2.10:8080
```

Origins must match exactly — scheme, host, and port. A `*` in the list is
accepted, but drops credentials again: the wildcard and credentials cannot
be combined.
:::

MCP clients such as Claude Desktop and Claude Code are not browsers, so
CORS never applies to them.

## Managing your account

**Settings → Account** is available when auth is enabled and you are signed in:

- **Change username** — requires your current password.
- **Change password** — requires your current password, plus the new one
  twice for confirmation.
- **Sign out** — revokes this browser session, clears its cookie, and opens `/login`.
- **Signed-in devices** — lists browsers and TVs, including approximate last-active
  and expiry times. Revoke one, sign out other devices, or sign out everywhere.
  Device names are descriptive labels, not verified hardware identities.

The corresponding API endpoints are also available:

| Method | Path | Body |
| --- | --- | --- |
| `POST` | `/api/auth/change-username` | `{ "current_password", "new_username" }` |
| `POST` | `/api/auth/change-password` | `{ "current_password", "new_password" }` |
| `POST` | `/api/auth/logout` | *(none)* |

## TV sign-in (Beta)

Enable **TV sign-in (Beta)** in **Settings → Account**. It is off by default
and requires a configured username and password. On a compatible Apple TV or
Android TV app, choose **Sign in with a phone or computer**:

1. Scan the QR code, or open the displayed `/activate` URL on a desktop or phone
   and enter the eight-character code.
2. Sign into that same FiestaBoard instance. Both devices need network access to it.
3. Check the displayed TV and matching code, then explicitly allow or deny access.
   Scanning alone never approves a TV. Codes expire after ten minutes.

**Use username and password** remains available on the TV. With this beta enabled,
it creates the same individually revocable TV credential and does not retain the
account password after secure storage succeeds. Compatible apps migrate previously
saved passwords once. Older servers keep their existing password flow.

TV credentials expire after one year and permit panel display and screen presentation
settings only. They cannot manage accounts, edit content, or access AI/MCP. Revoke a
TV from **Signed-in devices**; its next authenticated request is rejected. A revoked
TV asks you to sign in again rather than replaying a saved password.

Turning the beta switch off stops new TV sign-ins and cancels pending codes. Existing
TV credentials remain valid until revoked or expired. Use the device list to remove
existing access. Password or username changes revoke all existing browser and TV
sessions. Public panel URLs remain public even after revoking a TV credential.

### Upgrade and rollback

The first upgrade to the session registry signs existing browsers out once. Sign in
again to create tracked sessions. Ordinary restarts retain valid sessions. A legacy
client that still stores the password can create a new session after revocation;
update that client, or change the password if it should lose future access.

Managed image rollback and **Leave beta** invalidate sessions before switching images.
Before a manual image downgrade, use **Sign out everywhere** and then stop the
container. Back up authentication data securely; restoring an older copy of the data
can restore credentials and their earlier revocation state. Never copy the registry
or signing key into public diagnostics.

## Recovering from a lost password

Stop the container, delete `data/auth.json`, and restart. The next visit
to the UI will walk you through the first-run picker again.
