"""ASGI middleware that gates the API behind a session cookie.

Activated only when ``FIESTABOARD_AUTH_ENABLED`` is truthy — otherwise it
short-circuits to a no-op so existing local-only installs are unaffected.

Public paths (no auth required):
    * ``/`` and ``/health`` — liveness probes / nginx upstream checks
    * ``/auth/*`` — login / setup / status itself
    * ``/openapi.json``, ``/docs``, ``/redoc`` — API docs (still useful)
    * ``/internal/openapi.json`` — the full schema, public for the same
      reason ``/openapi.json`` is and because it is exactly what
      ``/openapi.json`` published before the internal surface was hidden.
      Gating it now would be a new restriction dressed up as a refactor.
    * CORS preflight (``OPTIONS``) requests

Bearer-token paths (``/mcp/*`` and ``/v1/*``):
    If an API token is configured (``FIESTABOARD_MCP_TOKEN`` or the value
    stored via Settings), the MCP endpoint requires an
    ``Authorization: Bearer <token>`` header instead of the session
    cookie. This lets external MCP clients (Claude Desktop, Claude Code)
    connect — and lets any script drive ``/v1`` — without needing to
    drive a browser login flow. A 401 from the MCP endpoint includes
    ``WWW-Authenticate: Bearer`` so the client knows to send a pre-shared
    token rather than attempting OAuth. On ``/v1`` a request with no
    Authorization header falls through to the ordinary session-cookie
    check instead, so a token does not lock the browser out.

    That check runs in **every** auth mode, ``disabled`` included — a
    configured token is a credential the operator asked for, not a
    formality that the UI login toggle can switch off. With no token
    configured, nothing changes for anyone.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .service import (
    SESSION_COOKIE_NAME,
    auth_mode,
    get_auth_service,
    mcp_token,
    verify_mcp_bearer,
)

logger = logging.getLogger(__name__)

# Path prefixes that never require authentication.
_PUBLIC_PREFIXES: tuple = (
    "/auth/",
    "/health",
    "/openapi.json",
    "/internal/openapi.json",
    "/docs",
    "/redoc",
)

# Exact paths that never require authentication.
_PUBLIC_EXACT: frozenset = frozenset({"/", "/auth", "/health"})


def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def _is_mcp_path(path: str) -> bool:
    """True for any path that lands on the MCP sub-app.

    The MCP server is mounted at ``/mcp`` inside FastAPI. Behind nginx we
    have two regimes:

    * Most ``/api/*`` traffic is rewritten to drop the prefix, so the
      middleware sees ``/mcp/...`` here.
    * ``/api/mcp/*`` is proxied WITHOUT the rewrite (otherwise Starlette
      can't compute Mount root_path correctly against FastAPI's
      ``root_path="/api"``) — so for that path we see ``/api/mcp/...``.

    Both forms point at the same endpoint and should accept the same
    bearer token.
    """
    return path == "/mcp" or path.startswith(("/mcp/", "/api/mcp/")) or path == "/api/mcp"


def _is_v1_path(path: str) -> bool:
    """True for the consumer-facing ``/v1`` surface.

    The same nginx double-regime as MCP: usually the ``/api`` prefix is
    stripped before we see it, but a path arriving with the prefix intact
    must resolve identically.
    """
    return path == "/v1" or path.startswith(("/v1/", "/api/v1/")) or path == "/api/v1"


def _accepts_bearer(path: str) -> bool:
    """Paths on which an ``Authorization: Bearer`` token is a valid credential.

    Bearer acceptance used to stop at ``/mcp*``, which is the mechanical
    reason a script could not authenticate against the REST API at all: the
    token existed, ``verify_mcp_bearer`` existed, and no HTTP path would take
    it. ``/v1`` is the surface a script is meant to use, so it takes it too.
    """
    return _is_mcp_path(path) or _is_v1_path(path)


def _bearer_from(request: Request) -> str | None:
    """Pull the token from an ``Authorization: Bearer <token>`` header."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    return None


def _mcp_unauthorized() -> JSONResponse:
    """401 with a plain Bearer challenge.

    The ``WWW-Authenticate: Bearer`` header signals to MCP clients that
    this endpoint takes a pre-shared token, not an OAuth flow. We
    deliberately omit a ``resource_metadata=`` parameter so spec-compliant
    clients don't attempt OAuth 2.1 dynamic client registration here.
    """
    return JSONResponse(
        {"detail": "Not authenticated"},
        status_code=401,
        headers={"WWW-Authenticate": 'Bearer realm="FiestaBoard MCP"'},
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Enforce a valid session cookie on non-public requests."""

    def __init__(self, app, extra_public_paths: Iterable[str] = ()) -> None:
        super().__init__(app)
        # Allow callers to extend the allow-list (e.g. for embedded board
        # image endpoints that must work without a cookie).
        self._extra_public = tuple(extra_public_paths)

    async def dispatch(self, request: Request, call_next):
        mode = auth_mode()

        # Always allow CORS preflight (browsers never attach credentials
        # to it, so there is nothing to check).
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        # MCP endpoint: a *configured* bearer token is enforced in every
        # auth mode, including "disabled". Auth mode governs the browser
        # login flow; setting FIESTABOARD_MCP_TOKEN (or storing one via
        # Settings) is a separate, deliberate act that must not be undone
        # by opting out of the UI login. Without this, every mutating MCP
        # tool is open to anything that can reach the port.
        #
        # When no token is configured there is nothing to enforce, so we
        # fall through: auth-disabled installs stay open and cookie-auth
        # installs keep using the session cookie.
        if _accepts_bearer(path) and mcp_token() is not None:
            supplied = _bearer_from(request)
            if supplied is not None:
                if not verify_mcp_bearer(supplied):
                    return _mcp_unauthorized()
                request.scope["auth_user"] = "mcp-client" if _is_mcp_path(path) else "api-token"
                return await call_next(request)
            # A bearer path with no Authorization header. On /mcp that is a
            # challenge — Claude/etc. will never have a cookie, and a 401
            # with WWW-Authenticate is exactly the signal such a client
            # needs. On /v1 it falls through to the ordinary cookie check
            # instead, because the browser is a legitimate v1 caller once
            # the web UI migrates onto it (Wave 2), and refusing a valid
            # session there would be a regression the token merely enables.
            if _is_mcp_path(path):
                return _mcp_unauthorized()

        if mode == "disabled":
            return await call_next(request)

        if _is_public_path(path):
            return await call_next(request)
        for extra in self._extra_public:
            if path == extra or path.startswith(extra.rstrip("/") + "/"):
                return await call_next(request)

        svc = get_auth_service()

        # If no user has been provisioned, every protected endpoint should
        # nudge the client toward /auth/setup rather than silently 401ing.
        # ``first_run`` distinguishes "we haven't asked the admin yet" from
        # "the admin has explicitly enabled auth but not finished setup".
        if not svc.has_user():
            return JSONResponse(
                {
                    "detail": "Setup required",
                    "setup_required": True,
                    "first_run": mode == "undecided",
                },
                status_code=409,
            )

        cookie = request.cookies.get(SESSION_COOKIE_NAME)
        username = svc.verify_session(cookie) if cookie else None
        if not username:
            return JSONResponse(
                {"detail": "Not authenticated"},
                status_code=401,
            )

        # Stash the authenticated user on the request scope for downstream
        # handlers that want to know who's calling.
        request.scope["auth_user"] = username
        return await call_next(request)
