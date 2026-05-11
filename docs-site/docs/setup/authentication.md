---
sidebar_position: 9
description: "Enable a username/password login for FiestaBoard. Recommended for any deployment that is reachable from the public internet."
keywords: [FiestaBoard authentication, login, security, password, internet exposed, VPS]
---

# Authentication

FiestaBoard ships with an **opt-in** username + password login. Local-only
installs don't need it — but if your FiestaBoard is reachable from the
public internet (for example, hosted on a VPS), turn it on.

When enabled, every API endpoint and every page of the web UI requires a
valid session cookie. The login page handles first-run account creation
automatically.

## Quick start

1. **Enable auth.** Add this to your `.env` (or set the environment variable
   on the host) and restart the container:

   ```bash
   FIESTABOARD_AUTH_ENABLED=true
   ```

2. **Create the admin account.** Open the web UI. Because no user exists
   yet, you'll be redirected to `/login` and prompted to set a username
   and password.

3. **Sign in.** That's it — you'll be redirected to the dashboard with a
   session cookie that lasts 7 days. Sign out from the profile menu when
   you're done.

## How it works

- **Passwords** are hashed with `hashlib.scrypt` (N=32768, r=8, p=1) and
  stored in `data/auth.json` (mode `0600`).
- **Sessions** are stateless HMAC-signed tokens (`username.issued.expires.nonce.sig`).
  The signing key lives in `data/.session_key` (mode `0600`) and is
  generated automatically the first time auth is used.
- **Cookies** are `HttpOnly`, `SameSite=Lax`, and `Secure` when the request
  comes in over HTTPS (FiestaBoard trusts the `X-Forwarded-Proto` header
  set by its bundled nginx).
- **Brute-force protection.** After 10 failed logins from the same client
  IP in 60 seconds the endpoint returns `429 Too Many Requests`.

## Configuration reference

| Variable | Default | Description |
| --- | --- | --- |
| `FIESTABOARD_AUTH_ENABLED` | _(unset)_ | Set to `true` / `1` / `yes` / `on` to require login. |
| `FIESTABOARD_SESSION_TTL_SECONDS` | `604800` (7d) | Session cookie lifetime in seconds. |

## Public endpoints

These remain reachable without authentication so health-checks, the login
page itself, and the OpenAPI docs keep working:

- `GET /`, `GET /health`
- `GET/POST /auth/*`
- `GET /openapi.json`, `/docs`, `/redoc`

Everything else (status, config, pages, plugins, etc.) requires a valid
session cookie.

## Changing the password

Sign in, then `POST /api/auth/change-password` with `{ "current_password",
"new_password" }`. A UI for this in the profile page is a follow-up; for
now you can call the API directly.

## Recovering from a lost password

Stop the container, delete `data/auth.json`, and restart. The next visit
to the UI will walk you through creating a new admin account.

## Secret encryption at rest

Independent of the login feature, FiestaBoard now supports encrypting
sensitive values (API keys, board keys, plugin credentials) before
writing them to `data/config.json`. See
[Secret encryption](./secret-encryption.md) for details.
