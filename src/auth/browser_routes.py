"""Browser-only management gates. Native/MCP tokens never become admin sessions."""

from __future__ import annotations

import os

from fastapi import Request

from .device_models import AuthFlowError
from .origins import normalized_origin
from .service import SESSION_COOKIE_NAME, get_auth_service
from .session_models import SessionRecord


def require_browser_session(request: Request) -> SessionRecord:
    # Even a valid cookie must not widen the privileges of a presented token.
    if request.headers.get("authorization"):
        raise AuthFlowError("unauthorized", "Sign in through the web portal to manage devices.", 401)
    session = get_auth_service().resolve_browser_session(request.cookies.get(SESSION_COOKIE_NAME))
    if not session:
        raise AuthFlowError("unauthorized", "Sign in through the web portal.", 401)
    return session


def _require_portal_origin(request: Request) -> None:
    # request.url uses the ASGI scheme set by Uvicorn's trusted proxy handling;
    # never read arbitrary X-Forwarded-* headers here. Explicit operator CORS
    # origins support an upstream TLS terminator without guessing its authority.
    expected = normalized_origin(f"{request.url.scheme}://{request.url.netloc}")
    allowed = {expected} if expected else set()
    allowed.update(
        filter(None, (normalized_origin(x.strip()) for x in os.environ.get("FIESTABOARD_CORS_ORIGINS", "").split(",")))
    )
    supplied = normalized_origin(request.headers.get("origin", ""))
    if not supplied or supplied not in allowed:
        raise AuthFlowError("forbidden", "This request must come from the FiestaBoard web portal.", 403)


def require_browser_mutation(request: Request) -> SessionRecord:
    session = require_browser_session(request)
    _require_portal_origin(request)
    if (
        request.method != "DELETE"
        and request.headers.get("content-type", "").split(";")[0].lower() != "application/json"
    ):
        raise AuthFlowError("forbidden", "A JSON request is required.", 403)
    if not get_auth_service().sessions.verify_csrf(session.id, request.headers.get("x-csrf-token", "")):
        raise AuthFlowError("forbidden", "Refresh this page and try again.", 403)
    return session
