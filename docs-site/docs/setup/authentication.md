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

## Public endpoints

These remain reachable without authentication so health-checks, the login
page itself, and the OpenAPI docs keep working:

- `GET /`, `GET /health`
- `GET/POST /auth/*`
- `GET /openapi.json`, `/docs`, `/redoc`

Everything else (status, config, pages, plugins, etc.) requires a valid
session cookie.

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
