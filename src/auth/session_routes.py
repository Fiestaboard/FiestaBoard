"""Manage signed-in browsers and TVs from a real browser session."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response

from src.api_errors import errors

from .browser_routes import require_browser_mutation, require_browser_session
from .device_models import CSRFContext, RevokeSessions, SessionList, Success
from .routes import _clear_session_cookie
from .service import get_auth_service

router = APIRouter(prefix="/auth/sessions", tags=["auth"])
RESPONSES = errors(400, 401, 403, 422, 503)


@router.get("/context", response_model=CSRFContext, responses=RESPONSES)
def context(request: Request):
    return CSRFContext(csrf_token=get_auth_service().sessions.issue_csrf(require_browser_session(request).id))


def _instant(ms: int) -> str:
    return datetime.fromtimestamp(ms // 1000, UTC).isoformat()


def _shown(views: list[tuple[str, int]], panels: set[str]) -> dict:
    # A deleted panel is no longer "shown on" anything.
    shown = [{"panel_id": p, "last_shown_at": _instant(ms)} for p, ms in views if p in panels]
    return {"shown_panels": shown, "last_shown_at": shown[0]["last_shown_at"] if shown else None}


@router.get("", response_model=SessionList, responses=RESPONSES)
def sessions(request: Request):
    from src.panels.service import get_panel_service

    current = require_browser_session(request)
    auth = get_auth_service()
    rows = auth.sessions.list_sessions(current.username)
    views = auth.sessions.panel_views(current.username)
    panels = {p.id for p in get_panel_service().list_panels()} if views else set()
    return SessionList(
        sessions=[
            {**r.summary(), **_shown(views.get(r.id, []), panels)}
            for r in rows
            if r.account_generation == current.account_generation
        ],
        current_session_id=current.id,
    )


@router.delete("/{session_id}", response_model=Success, responses=RESPONSES)
def revoke(session_id: str, request: Request, response: Response):
    current = require_browser_mutation(request)
    get_auth_service().sessions.revoke_session(current.username, session_id)
    if session_id == current.id:
        _clear_session_cookie(response)
    return Success()


@router.post("/revoke", response_model=Success, responses=RESPONSES)
def revoke_many(payload: RevokeSessions, request: Request, response: Response):
    current = require_browser_mutation(request)
    auth = get_auth_service()
    if payload.include_current:
        auth.invalidate_all_sessions(current.username)
        _clear_session_cookie(response)
    else:
        auth.sessions.revoke_sessions(current.username, except_id=current.id)
    return Success()
