---
description: Session authentication, OAuth flows, and deployment paths for native clients.
---

# Native client authentication and OAuth

Native clients use the existing HTTP APIs. No additional mobile token, custom
callback scheme, or authentication bypass is required for the supported flows.
This contract covers a reachable FiestaBoard deployment; establishing access
through an external gateway remains a separate authentication step.

## Session lifecycle

Start with `GET /api/auth/status`. Respect `enabled`, `setup_required`,
`first_run`, and `authenticated`; a protected deployment without an administrator account returns
409 instead of behaving as an anonymous installation. Sign in using
`POST /api/auth/login` with `username`, `password`, and an explicit
`remember_me` choice. Retain the returned `fiestaboard_session` cookie in an
isolated cookie store associated with this deployment. Use that cookie for both
public versioned content routes and internal routes used by the web application.
Do not copy credentials or cookies into requests to OAuth providers.

`POST /api/auth/logout` revokes the session on the server as well as clearing
the cookie. Discard the local cookie too. A copied cookie cannot keep accessing
protected routes after logout or session revocation. A 401 means the client
must sign in again; it must not replay interrupted mutations automatically.

Session administration uses the existing browser-session contract. First read
`GET /api/auth/sessions/context` for a CSRF token associated with the current
cookie. Mutating session/device-management requests require that cookie, an
`Origin` equal to the deployment's scheme and authority (without its path), and
`X-CSRF-Token`. Non-DELETE mutations also require JSON content type. Explicitly
configured operator CORS origins remain supported. Missing/wrong Origin or
missing/stale-session CSRF values must remain errors, not grounds for adding an
exemption for native clients. An API/TV bearer token is not an administrative
browser session.

## Provider sign-in

Discover connections through `GET /api/oauth/connections` and individual
`GET /api/oauth/connections/{id}`. Use the connection's advertised flows,
configuration requirements, status, and `paste_expected` value. Start a flow
with `POST /api/oauth/connections/{id}/authorize` and open its returned provider
URL in an appropriate system browser session. Use the board base URL, including
any deployment prefix, as `board_url` where supported; never substitute an
invented application URL scheme for a provider's registered redirect.

| Flow | Native interaction | Completion |
| --- | --- | --- |
| `relay` | Open authorization URL | Existing board callback, or authenticated `complete` with pasted returned URL |
| `device` | Show user code and open verification URL | Server polls provider; client polls connection status |
| `key_exchange` | Open authorization URL; use advertised headless/paste behavior | Existing callback or authenticated `complete` with returned URL/code |
| `plex_pin` | Open authorization URL | Server polls PIN; client polls connection status |

`POST /api/oauth/connections/{id}/complete` accepts `{"pasted": "..."}`.
It is the existing fallback when a browser return cannot reach the board,
including loopback-only provider redirects. The client can poll connection
status after a browser handoff or manual completion. Handle pending, expiry,
denial, failed exchange, and reauthorization states explicitly. Closing the
browser is not evidence that authorization succeeded.

The exact `/api/oauth/callback` route is publicly reachable because signed,
single-use state authenticates it. Other OAuth operations require the ordinary
session when deployment authentication is enabled. A repeated callback/paste
cannot exchange a code again. Connection responses deliberately exclude access
tokens, refresh tokens, device codes, and PKCE verifiers. Disconnect using
`DELETE /api/oauth/connections/{id}`.

## Deployment paths and limits

Compose every API URL beneath the selected deployment base. For example,
`https://example/board/kitchen` produces
`https://example/board/kitchen/api/auth/login`. The deployment's proxy strips
the API prefix before forwarding to Python. Callback return redirects are
relative so they stay beneath that base.

A Home Assistant ingress URL may require an independent Home Assistant login
and ingress session. FiestaBoard credentials do not replace those credentials.
Tests that simulate prefix stripping establish URL behavior only; they do not
establish native support for Home Assistant's authentication gateway. Direct
reachable LAN/HTTPS deployments and correctly configured reverse proxies are
the supported backend boundary. Native discovery, browser UI, secure credential
storage, gateway authentication, and device acceptance remain native app work.

## Verification

`tests/test_native_auth_contract.py` exercises login, protected public/internal
reads, logout and copied-cookie rejection, session Origin/CSRF enforcement,
OAuth manual completion/status/disconnect/replay, and unauthenticated OAuth
rejection. Each sequence runs against both `/api` and a nested deployment
prefix using the real application and a test-only path-rewrite adapter.

The existing auth/OAuth suites additionally cover the four flow types, signed
state tampering/expiry/single use, device and PIN pending/expiry behavior,
provider denial, manual completion boundaries, and token redaction. All provider
responses are fixtures; tests use temporary authentication/token stores with
network access disabled. No live provider account or board is contacted.
