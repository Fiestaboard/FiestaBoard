"""FastAPI router for the ``/oauth`` endpoints.

``GET /oauth/callback`` is where the relay page sends the browser after a
provider sign-in (``<board>/api/oauth/callback`` before nginx strips the
prefix). It is exempt from the session check in ``src/auth/middleware.py``:
the request arrives by cross-site navigation, and what authenticates it is the
signed, single-use ``state`` of a flow that an authenticated user started.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any, TypeVar
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from src.api_errors import errors

from .errors import (
    ConnectionNotConfigured,
    ConnectionNotFound,
    FlowNotSupported,
    InvalidBoardUrl,
    OAuthError,
    PastedCodeRejected,
    ProviderError,
)
from .models import (
    OAuthAuthorizationStart,
    OAuthAuthorizeRequest,
    OAuthCompleteRequest,
    OAuthConnection,
    OAuthConnectionList,
)
from .service import AI_CONNECTION_PREFIX, CallbackOutcome, get_oauth_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])

#: The single place an OAuth-domain failure becomes a status code.
_STATUS_BY_ERROR: tuple[tuple[type[OAuthError], int], ...] = (
    (ConnectionNotFound, 404),
    (ConnectionNotConfigured, 400),
    (FlowNotSupported, 400),
    (InvalidBoardUrl, 400),
    (PastedCodeRejected, 400),
    (ProviderError, 502),
)

_T = TypeVar("_T")


def oauth_errors_to_http(handler: Callable[..., Awaitable[_T]]) -> Callable[..., Awaitable[_T]]:
    """Map :class:`~src.oauth.errors.OAuthError` onto ``HTTPException``."""

    @functools.wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> _T:
        try:
            return await handler(*args, **kwargs)
        except OAuthError as exc:
            status = next((code for kind, code in _STATUS_BY_ERROR if isinstance(exc, kind)), 502)
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    return wrapper


@router.get("/oauth/connections", response_model=OAuthConnectionList)
async def list_oauth_connections() -> OAuthConnectionList:
    """Every installed plugin that signs in with OAuth, and whether it is connected."""
    service = get_oauth_service()
    return OAuthConnectionList(
        connections=[OAuthConnection.model_validate(asdict(status)) for status in service.list_connections()],
        redirect_uri=service.redirect_uri,
    )


@router.get("/oauth/connections/{connection_id}", response_model=OAuthConnection, responses=errors(404))
@oauth_errors_to_http
async def get_oauth_connection(connection_id: str) -> OAuthConnection:
    """One plugin's connection, including any device-code sign-in in progress."""
    return OAuthConnection.model_validate(asdict(get_oauth_service().get_connection(connection_id)))


@router.post(
    "/oauth/connections/{connection_id}/authorize",
    response_model=OAuthAuthorizationStart,
    responses=errors(400, 404, 502),
)
@oauth_errors_to_http
async def authorize_oauth_connection(connection_id: str, request: OAuthAuthorizeRequest) -> OAuthAuthorizationStart:
    """Start connecting a plugin to its provider.

    ``relay`` answers with the URL to send the browser to. ``device`` answers
    with the code to show the user; poll ``GET /oauth/connections/{id}`` to
    see it complete.
    """
    # The device flow calls the provider, so this cannot run on the event loop.
    start = await asyncio.to_thread(
        get_oauth_service().start, connection_id, request.flow, request.board_url, request.headless
    )
    return OAuthAuthorizationStart.model_validate(asdict(start))


@router.post(
    "/oauth/connections/{connection_id}/complete",
    response_model=OAuthConnection,
    responses=errors(400, 404, 502),
)
@oauth_errors_to_http
async def complete_oauth_connection(connection_id: str, request: OAuthCompleteRequest) -> OAuthConnection:
    """Finish a sign-in from the address or code the user pasted.

    For when the browser did not come back on its own: the relay page could
    not reach the board, or the provider shows a code instead of redirecting.
    Needs a session, unlike ``/oauth/callback``.
    """
    status = await asyncio.to_thread(get_oauth_service().complete_pasted, connection_id, request.pasted)
    return OAuthConnection.model_validate(asdict(status))


@router.delete("/oauth/connections/{connection_id}", response_model=OAuthConnection, responses=errors(404))
@oauth_errors_to_http
async def disconnect_oauth_connection(connection_id: str) -> OAuthConnection:
    """Delete the tokens stored for a plugin. Idempotent for a known plugin."""
    return OAuthConnection.model_validate(asdict(get_oauth_service().disconnect(connection_id)))


def _return_location(outcome: CallbackOutcome) -> str:
    """Where to send the browser once a callback has been handled.

    Relative on purpose. The browser is at ``<base>/api/oauth/callback``, where
    ``<base>`` is empty for a direct install and a path prefix under Home
    Assistant ingress; two levels up is the app root in both.
    """
    outcome_value = "connected" if outcome.connected else "error"
    if outcome.connection_id and outcome.connection_id.startswith(AI_CONNECTION_PREFIX):
        # FiestaBot's AI providers sign in from Settings → AI, not the
        # Integrations page. (The tab was called Integrations before 10.0;
        # the web app still maps that old id to AI.)
        ai_query = {"section": "ai","oauth": outcome_value, "connection": outcome.connection_id}
        if outcome.reason:
            ai_query["reason"] = outcome.reason
        return f"../../settings?{urlencode(ai_query)}"
    query = {"tab": "installed", "oauth": outcome_value}
    if outcome.connection_id:
        query["plugin"] = outcome.connection_id
    if outcome.reason:
        query["reason"] = outcome.reason
    return f"../../integrations?{urlencode(query)}"


@router.get(
    "/oauth/callback",
    response_class=RedirectResponse,
    status_code=302,
    responses={302: {"description": "Back to the Integrations page, with the outcome in the query string."}},
)
async def oauth_callback(
    state: str | None = None, code: str | None = None, error: str | None = None
) -> RedirectResponse:
    """Finish a relay sign-in and return the browser to the Integrations page.

    Always redirects, whatever happened: the caller is a person mid-sign-in,
    and a JSON error body would strand them on a blank page.
    """
    outcome = await asyncio.to_thread(get_oauth_service().complete_authorization, state=state, code=code, error=error)
    return RedirectResponse(
        _return_location(outcome),
        status_code=302,
        # The request URL carried an authorization code; keep it out of caches
        # and out of any Referer the next page sends.
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
