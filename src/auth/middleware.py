"""ASGI middleware that gates the API behind a session cookie.

Activated only when ``FIESTABOARD_AUTH_ENABLED`` is truthy — otherwise it
short-circuits to a no-op so existing local-only installs are unaffected.

Public paths (no auth required):
    * ``/`` and ``/health`` — liveness probes / nginx upstream checks
    * ``/auth/*`` — login / setup / status itself
    * ``/openapi.json``, ``/docs``, ``/redoc`` — API docs (still useful)
    * CORS preflight (``OPTIONS``) requests
"""

from __future__ import annotations

import logging
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .service import SESSION_COOKIE_NAME, get_auth_service, is_auth_enabled

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


class AuthMiddleware(BaseHTTPMiddleware):
    """Enforce a valid session cookie on non-public requests."""

    def __init__(self, app, extra_public_paths: Iterable[str] = ()) -> None:
        super().__init__(app)
        # Allow callers to extend the allow-list (e.g. for embedded board
        # image endpoints that must work without a cookie).
        self._extra_public = tuple(extra_public_paths)

    async def dispatch(self, request: Request, call_next):
        if not is_auth_enabled():
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

        svc = get_auth_service()

        # If no user has been provisioned, every protected endpoint should
        # nudge the client toward /auth/setup rather than silently 401ing.
        if not svc.has_user():
            return JSONResponse(
                {"detail": "Setup required", "setup_required": True},
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
