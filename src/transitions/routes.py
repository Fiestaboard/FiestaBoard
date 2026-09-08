"""FastAPI router for the transition-plugin endpoints (beta).

Handlers were moved here from ``src/api_server.py`` (Phase 2 slice 8, Task 8)
into the existing ``src/transitions`` package — it already owns the runner —
and the conventions pass was applied in the same commit. The 250 lines of
frame-cap loops, grid sizing and board routing that came with them moved down
again into ``src/transitions/service.py`` when this domain opted into
``tests/test_layering_ratchet.py``; what is left here is HTTP.

Every route is gated behind ``beta.transition_plugins_enabled`` and answers
404 while it is off: the SDK is experimental and the feature is meant to be
invisible until the operator opts in. That gate stays in the router — a 404
for "this endpoint does not exist yet" is a transport verdict, not a domain
one.

The service raises :class:`~src.transitions.service.TransitionError`, which
carries the status code and detail these endpoints have always answered; the
handlers translate it into ``HTTPException`` and change nothing about it.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``
(``tests/test_small_domains_decoupled.py`` asserts that in a fresh
interpreter). Tests that need to stub a collaborator — or the
``LIVE_TEST_FROM_HOLD_SECONDS`` seam, which now lives beside the code that
sleeps on it — patch it where the *service* binds it:
``src.transitions.service.<name>``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from src.api_errors import errors
from src.settings.service import get_settings_service

from . import service
from .models import (
    TransitionLiveTestRequest,
    TransitionLiveTestResponse,
    TransitionPluginEntry,
    TransitionPluginsResponse,
    TransitionPreviewRequest,
    TransitionPreviewResponse,
    TransitionRestoreRequest,
    TransitionRestoreResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transitions"])


def _ensure_transition_plugins_beta() -> None:
    """Gate transition-plugin endpoints behind the beta flag.

    The SDK is experimental and its contract may change.  Until the
    operator opts in via Settings → Beta the endpoints respond 404 so
    the feature is fully hidden -- no plugin picker, no preview page,
    no surface area for users to start depending on something we may
    reshape.
    """
    settings_service = get_settings_service()
    beta = settings_service.get_beta_settings()
    if not beta.transition_plugins_enabled:
        raise HTTPException(
            status_code=404,
            detail=(
                "Transition plugins are an experimental beta. Enable them in Settings → Beta to use this endpoint."
            ),
        )


def _as_http(exc: service.TransitionError) -> HTTPException:
    """The domain's refusal, in the transport's vocabulary.

    Status and detail pass through untouched — ``tests/test_transitions_contract.py``
    pins every pair by value.
    """
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/transitions/plugins", response_model=TransitionPluginsResponse, responses=errors(404))
async def list_transition_plugins():
    """List installed transition plugins available for selection.

    Each entry includes the plugin id, display name, manifest metadata,
    its ``settings_schema`` (so the UI can render a config form), and the
    plugin's ``transition_settings`` caps.  Every installed transition
    plugin is listed -- unlike data plugins, transitions don't need to be
    enabled in the Marketplace to be selectable; installing one is opting
    in.

    Gated behind ``beta.transition_plugins_enabled``.
    """
    _ensure_transition_plugins_beta()
    entries = service.list_installed_transition_plugins()
    return TransitionPluginsResponse(plugins=[TransitionPluginEntry.model_validate(entry) for entry in entries])


@router.post(
    "/transitions/preview",
    response_model=TransitionPreviewResponse,
    responses=errors(400, 404, 500, 504),
)
async def preview_transition(request: TransitionPreviewRequest):
    """Drive a transition plugin once and return its frame sequence.

    Designed for the standalone /transitions test harness in the web UI.
    Frames are generated in-process and returned as JSON; nothing is sent
    to a real board.  The runner's caps (max_frames, max_runtime_seconds,
    min_interval_ms) are honored; exceeding one truncates the response and
    sets ``capped`` so the UI can display a hint.

    Gated behind ``beta.transition_plugins_enabled`` -- see
    ``_ensure_transition_plugins_beta``.
    """
    _ensure_transition_plugins_beta()
    try:
        return await service.preview_transition(request)
    except service.TransitionError as exc:
        raise _as_http(exc) from exc


@router.post(
    "/transitions/test-live",
    response_model=TransitionLiveTestResponse,
    responses=errors(400, 404, 409, 502, 503, 504),
)
async def run_live_transition_test(request: TransitionLiveTestRequest):
    """Run a transition plugin once on the real board (Transition Lab).

    Request body:
      - plugin_id (str, required): the transition plugin to drive
      - to_page_id (str, required): page the transition lands on
      - from_page_id (str, optional): page snapped to the board first so
        the transition visibly starts from it; omitted → the transition
        starts from whatever the board currently shows
      - config (dict, optional): per-run overrides merged on top of the
        plugin's currently-bound config
      - board_id (str, optional): target board; omitted → primary board

    Respects silence mode and board pause (409 so the UI can explain why
    nothing happened).  The board is left showing the to-page; use
    ``POST /transitions/restore`` — or just wait for the normal display
    loop — to return it to its active page.

    Gated behind ``beta.transition_plugins_enabled``.
    """
    _ensure_transition_plugins_beta()
    try:
        return await service.run_live_transition_test(request)
    except service.TransitionError as exc:
        raise _as_http(exc) from exc


@router.post(
    "/transitions/restore",
    response_model=TransitionRestoreResponse,
    responses=errors(404, 409, 502, 503),
)
async def restore_after_transition_test(request: TransitionRestoreRequest | None = None):
    """Snap the board back to its active page after a live transition test.

    Request body (optional):
      - board_id (str, optional): target board; omitted → primary board

    Re-renders the board's active page and sends it plainly (no
    transition), cancelling any still-running plugin transition.  The
    normal display loop would eventually do the same; this endpoint just
    lets the Transition Lab do it on demand.

    Gated behind ``beta.transition_plugins_enabled``.
    """
    _ensure_transition_plugins_beta()
    try:
        return await service.restore_after_transition_test(request)
    except service.TransitionError as exc:
        raise _as_http(exc) from exc
