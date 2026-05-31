"""ASGI middleware that gates the API behind a session cookie.

Activated only when ``FIESTABOARD_AUTH_ENABLED`` is truthy — otherwise it
short-circuits to a no-op so existing local-only installs are unaffected.

Public paths (no auth required):
    * ``/`` and ``/health`` — liveness probes / nginx upstream checks
    * ``/auth/*`` — login / setup / status itself
    * ``/openapi.json``, ``/docs``, ``/redoc`` — API docs (still useful)
    * CORS preflight (``OPTIONS``) requests

MCP endpoint (``/mcp/*``):
    If ``FIESTABOARD_MCP_TOKEN`` is set, the MCP endpoint accepts an
    ``Authorization: Bearer <token>`` header instead of (or in addition to)
    the session cookie. This lets external MCP clients (Claude Desktop,
    Claude Code) connect without needing to drive a browser login flow.
    A 401 from this endpoint includes ``WWW-Authenticate: Bearer`` so the
    client knows to send a pre-shared token rather than attempting OAuth.
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
    "/docs",
    "/redoc",
)

# Exact paths that never require authentication.
_PUBLIC_EXACT: frozenset = frozenset({"/", "/auth", "/health"})


def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return True
    return False


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
    return (
        path == "/mcp"
        or path.startswith("/mcp/")
        or path == "/api/mcp"
        or path.startswith("/api/mcp/")
    )


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
        if mode == "disabled":
            return await call_next(request)

        # Always allow CORS preflight.
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if _is_public_path(path):
            return await call_next(request)
        for extra in self._extra_public:
            if path == extra or path.startswith(extra.rstrip("/") + "/"):
                return await call_next(request)

        # MCP endpoint: accept a Bearer token if one is configured. Falls
        # through to cookie auth when no token env var is set so the UI's
        # own MCP usage (and existing installs) keep working.
        if _is_mcp_path(path) and mcp_token() is not None:
            supplied = _bearer_from(request)
            if supplied is not None:
                if verify_mcp_bearer(supplied):
                    request.scope["auth_user"] = "mcp-client"
                    return await call_next(request)
                return _mcp_unauthorized()
            # No Authorization header — challenge the client. We skip the
            # session-cookie fallback here because Claude/etc. will never
            # have a cookie, and emitting a 401 with WWW-Authenticate is
            # exactly the signal it needs.
            return _mcp_unauthorized()

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
