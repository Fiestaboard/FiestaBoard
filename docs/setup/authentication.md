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

When auth is on, every API endpoint and every page of the web UI requires
a valid session cookie.

## Quick start

1. **Open the web UI.** On a fresh install you'll land on `/login` with
   the first-run picker.

2. **Enable login.** Click *Enable login (recommended)*, then set a
   username and password.

3. **Sign in.** You'll be redirected to the dashboard with a session
   cookie. Tick **Keep me logged in** (on by default) to stay signed in
   across browser restarts; clear it on a shared or public computer so the
   session ends when you close the browser. Manage your account (rename,
   change password, sign out) from the **Profile** page.

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
- **Sessions** are stateless HMAC-signed tokens (`username.issued.expires.nonce.sig`).
  The signing key lives in `data/.session_key` (mode `0600`) and is
  generated automatically the first time auth is used.
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
| `FIESTABOARD_MCP_TOKEN` | *(unset)* | Pre-shared bearer token for `/api/mcp/`. Takes precedence over a token stored from **Settings → Integrations**, and disables the UI's rotate/revoke buttons. See [MCP clients and the bearer token](#mcp-clients-and-the-bearer-token). |
| `FIESTABOARD_CORS_ORIGINS` | *(unset, no credentialed cross-origin access)* | Comma-separated list of exact origins allowed to send credentials on cross-origin browser requests. See [Cross-origin browser access](#cross-origin-browser-access-cors). |

## Public endpoints

These remain reachable without authentication so health-checks, the login
page itself, and the OpenAPI docs keep working:

- `GET /`, `GET /health`
- `GET/POST /auth/*`
- `GET /openapi.json`, `/docs`, `/redoc`

Everything else (status, config, pages, plugins, etc.) requires a valid
session cookie.

## MCP clients and the bearer token

External MCP clients — Claude Desktop, Claude Code — can't drive a
cookie-based login, so they authenticate to `/api/mcp/` with a pre-shared
bearer token instead of a session cookie. Configure one in
**Settings → Integrations**, or by setting `FIESTABOARD_MCP_TOKEN`.

:::warning Behaviour change: a configured token is now enforced in every auth mode

If a token is configured, `/api/mcp/` **requires** it — including when you
chose *Continue without login*. Previously the token was ignored whenever
auth was disabled, so a client could reach `/api/mcp/` without sending it.

If an MCP client that used to work starts returning `401`, put the token in
its config so it sends `Authorization: Bearer <your-token>`. Alternatively,
clear the token in **Settings → Integrations** if you want `/api/mcp/` to
stay open.

**Installs with no token configured are unaffected** — they behave exactly
as before.
:::

On an install where you chose *Continue without login*, prefer
`FIESTABOARD_MCP_TOKEN` over a token generated on the Settings page. Token
management is part of the API (`POST` / `DELETE /auth/mcp-token`), and with
the login disabled there is no session for those routes to check — so
anyone who can reach the port can rotate or revoke a Settings-stored token
and re-open `/api/mcp/`. A Settings-stored token protects against accidents
there, not against an attacker who can already reach FiestaBoard. While
`FIESTABOARD_MCP_TOKEN` is set, both routes refuse with `409` and the token
cannot be changed over the network.

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

The **Profile** page has an *Account* card (visible only when auth is
enabled and you're signed in) with three things:

- **Change username** — requires your current password.
- **Change password** — requires your current password, plus the new one
  twice for confirmation.
- **Sign out** — clears the session cookie and bounces you back to
  `/login`.

The corresponding API endpoints are also available:

| Method | Path | Body |
| --- | --- | --- |
| `POST` | `/api/auth/change-username` | `{ "current_password", "new_username" }` |
| `POST` | `/api/auth/change-password` | `{ "current_password", "new_password" }` |
| `POST` | `/api/auth/logout` | *(none)* |

## Recovering from a lost password

Stop the container, delete `data/auth.json`, and restart. The next visit
to the UI will walk you through the first-run picker again.

## Secret encryption at rest

Independent of the login feature, FiestaBoard supports encrypting
sensitive values (API keys, board keys, plugin credentials) before
writing them to `data/config.json`. See
[Secret encryption](./secret-encryption.md) for details.
