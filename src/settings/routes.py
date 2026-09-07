"""FastAPI router for the ``/settings`` endpoints.

Handlers were moved here verbatim from ``src/api_server.py`` (Phase 2, Task 8).
The move is deliberately behaviour-preserving: the only edits to a handler body
are the ones the relocation forces (``@app`` → ``@router``, relative imports
re-anchored from ``src`` to ``src.settings``, and the two module globals that
must now be read back out of ``api_server`` at call time).

**Collaborator resolution.** ``/settings`` is the widest domain in the app and
its handlers reach 25 collaborators that still live in ``src/api_server.py``
(``get_service``, ``_require_board``, ``_reinitialize_board_clients``, the
updater-sidecar probes, ...) or that other, not-yet-converted routers still
resolve through ``api_server`` (``get_settings_service`` alone is patched at
160 sites). Per ``docs/internal/reference/API_CONVENTIONS.md`` ("during
extraction, moved handlers resolve api_server-patched names at call time") and
the Phase 2 plan's addendum 3 ("a shared accessor cannot be deleted until its
last consumer converts"), those names are resolved through :func:`_api` on
every call. The thin shims below keep the moved handler bodies byte-identical
to what they were in ``api_server``; they are the seam to retire once the
remaining domains convert.

Collaborators that already have a canonical home *and* are not patched through
``src.api_server`` anywhere in the suite (``classify_dimensions``,
``run_board_send``, ``VALID_STRATEGIES``, ``VALID_OUTPUT_TARGETS``) are
imported normally at module import time.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.board_send_executor import run_board_send
from src.devices import classify_dimensions

from .models import (
    ERROR_400,
    DisplaySettingsResponse,
    DisplaySettingsUpdate,
    LocationSettingsResponse,
    LocationSettingsUpdate,
    OutputSettings,
    OutputSettingsResponse,
    OutputSettingsUpdate,
    PluginSettingsResponse,
    PluginSettingsUpdate,
    PollingSettings,
    PollingSettingsResponse,
    PollingSettingsUpdate,
    SunTimesResponse,
    SunTimesWeekResponse,
    TransitionSettings,
    TransitionSettingsResponse,
    TransitionSettingsUpdate,
)
from .service import VALID_OUTPUT_TARGETS, VALID_STRATEGIES
from .service import temporary_override_payload as _temporary_override_payload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


def _api(name: str):
    """Resolve *name* from ``src.api_server`` at call time.

    Import-time resolution would both create a cycle (``api_server`` imports
    this module to mount the router) and freeze the binding, breaking the
    ``patch("src.api_server.<name>")`` seams the existing suite relies on.
    """
    import src.api_server as api_server

    return getattr(api_server, name)


def _seam(name: str):
    """Build a call-time passthrough to ``src.api_server.<name>``."""

    def _call(*args, **kwargs):
        return _api(name)(*args, **kwargs)

    _call.__name__ = name
    _call.__qualname__ = name
    _call.__doc__ = f"Call-time seam for ``src.api_server.{name}`` (see module docstring)."
    return _call


# Service accessors other routers still resolve through ``api_server``.
get_settings_service = _seam("get_settings_service")
get_config_manager = _seam("get_config_manager")
get_page_service = _seam("get_page_service")
get_collection_service = _seam("get_collection_service")
get_panel_service = _seam("get_panel_service")
get_service = _seam("get_service")

# Helpers whose only home is ``api_server`` today.
_require_board = _seam("_require_board")
_board_is_paused = _seam("_board_is_paused")
_board_dims = _seam("_board_dims")
_apply_mqtt_config = _seam("_apply_mqtt_config")
_reinitialize_board_clients = _seam("_reinitialize_board_clients")
_validate_board_host = _seam("_validate_board_host")
_validate_board_host_is_local_network = _seam("_validate_board_host_is_local_network")

# Shared with ``src/schedules/routes.py``; cannot move until that domain owns
# a copy or a common module exists (addendum 3).
_resolve_active_page_id = _seam("_resolve_active_page_id")
_resolve_next_check_seconds = _seam("_resolve_next_check_seconds")

# fiestaupdater sidecar probes (canonical home ``src/system/update_service.py``,
# but the suite patches the ``api_server`` re-export).
_updater_url = _seam("_updater_url")
_updater_token = _seam("_updater_token")
_updater_probe = _seam("_updater_probe")
_fiestaboard_profile = _seam("_fiestaboard_profile")

# Domain helpers with canonical homes that the suite still patches on
# ``api_server``.
check_ref_board_compatibility = _seam("check_ref_board_compatibility")
is_collection_id = _seam("is_collection_id")
resolve_dimensions = _seam("resolve_dimensions")
text_to_board_array = _seam("text_to_board_array")
board_client_from_board_dict = _seam("board_client_from_board_dict")


@router.get("/settings/mqtt")
async def get_mqtt_settings():
    """Return current MQTT integration settings (password masked)."""
    from .service import get_settings_service

    s = get_settings_service().get_mqtt_settings()
    return s.to_dict(mask_secrets=True)


@router.put("/settings/mqtt")
async def update_mqtt_settings(request: Request):
    """Save MQTT settings and immediately apply them.

    Enables or disables the live MQTT client based on the *enabled* flag.
    Supply only the fields you want to change; omitted fields keep their current
    values.  Password is only updated when a non-empty, non-masked value is sent.
    """
    body = await request.json()
    from .service import get_settings_service

    svc = get_settings_service()
    updated = svc.set_mqtt_settings(body)
    _apply_mqtt_config(updated)
    return updated.to_dict(mask_secrets=True)


@router.get("/settings/ai")
async def get_ai_settings():
    """Return AI provider configuration with each provider's api_key masked."""
    cm = get_config_manager()
    return cm.get_ai_providers_masked()


@router.put("/settings/ai")
async def update_ai_settings(request: Request):
    """Update AI provider configuration.

    Body may include any of:
    - ``enabled`` (bool)
    - ``providers`` (list of provider objects: ``id``, ``name``,
      ``base_url``, ``api_key``, ``models``, ``default_model``,
      ``headers``)
    - ``default_provider_id``

    Providers whose ``api_key`` field is the mask placeholder (``"***"``)
    keep their existing key on update, matching the rest of FiestaBoard's
    masked-secret pattern.
    """
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")
    cm = get_config_manager()
    return cm.set_ai_providers(body)


@router.post("/settings/ai/test")
async def test_ai_provider(request: Request):
    """Send a tiny smoke-test request to a configured provider.

    Body: ``{provider_id?: str, model?: str, provider?: dict}``. When
    ``provider`` is supplied, its fields override the persisted config so
    unsaved drafts in the settings UI can be tested without saving first.
    A masked ``api_key`` (``"***"``) is resolved to the stored key by
    ``provider_id``. Otherwise the persisted provider is loaded by id.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    provider_id = body.get("provider_id") if isinstance(body, dict) else None
    model = body.get("model") if isinstance(body, dict) else None
    draft = body.get("provider") if isinstance(body, dict) else None

    cm = get_config_manager()

    if isinstance(draft, dict):
        provider = dict(draft)
        if provider.get("api_key") == "***":
            stored_id = provider.get("id") or provider_id
            stored = cm.get_ai_provider(stored_id) if stored_id else None
            provider["api_key"] = (stored or {}).get("api_key", "")
    else:
        block = cm.get_ai_providers()
        if not block.get("providers"):
            raise HTTPException(
                status_code=400,
                detail="No AI providers are configured.",
            )
        if provider_id:
            provider = cm.get_ai_provider(provider_id)
            if provider is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"AI provider {provider_id!r} not found.",
                )
        else:
            default_id = block.get("default_provider_id")
            provider = (cm.get_ai_provider(default_id) if default_id else None) or block["providers"][0]

    from src.ai.generator import test_provider as ai_test_provider

    result = await ai_test_provider(provider, model=model)
    return result


class SilenceScheduleRequest(BaseModel):
    """Request body for updating the silence schedule feature."""

    enabled: bool
    start_time: str
    end_time: str
    mode: str | None = None  # "freeze" (default), "indicator", or "page"
    page_id: str | None = None  # Page id to display when mode == "page"
    indicator_text: str | None = None  # Custom text to display when mode == "indicator"
    indicator_position: str | None = None  # Position: center, top-left, top-right, bottom-left, bottom-right
    # Board to target (issue #1788). Omitted → the install-wide schedule.
    # Deliberately in the BODY, not the URL, so the endpoint path is unchanged.
    board_id: str | None = None


@router.put("/settings/silence-schedule")
async def update_silence_schedule(request: SilenceScheduleRequest):
    """
    Update the silence schedule configuration.

    `silence_schedule` is a system feature (not a plugin). Times must be in
    UTC ISO format (e.g. "04:00+00:00"); the UI converts local time to UTC
    before calling this endpoint.

    `mode` selects what happens while silence is active:
      - "indicator" (default) - show a clean "SNOOZING" message sized to the device
      - "freeze" - leave whatever is on the board, stop sending updates
      - "page" - display the page identified by `page_id` and freeze it

    `board_id` (optional, issue #1788) targets one board: the write lands in
    `features.silence_schedule.by_board[board_id]` and the install-wide layer
    is left alone. Omitted → the install-wide layer is written, which is what
    every board without its own override resolves to.
    """
    config_manager = get_config_manager()

    board_id = request.board_id
    if board_id is not None:
        _require_board(board_id)

    # Validate mode and page_id together
    mode = request.mode if request.mode in ("indicator", "freeze", "page") else "freeze"
    page_id: str | None = None
    if mode == "page":
        if not request.page_id:
            raise HTTPException(
                status_code=400,
                detail="page_id is required when mode is 'page'",
            )
        page_id = request.page_id
    elif request.page_id:
        # Preserve a previously selected page even when mode is not "page",
        # so the user can toggle back without losing their choice.
        page_id = request.page_id

    # Normalize indicator_text: uppercase, strip, fallback to "SNOOZING"
    indicator_text_raw = request.indicator_text
    if isinstance(indicator_text_raw, str) and indicator_text_raw.strip():
        indicator_text = indicator_text_raw.strip().upper()
    else:
        indicator_text = "SNOOZING"

    # Normalize indicator_position
    _valid_positions = ("center", "top-left", "top-right", "bottom-left", "bottom-right")
    indicator_position = request.indicator_position if request.indicator_position in _valid_positions else "center"

    # Enforce page<->board size compatibility (issue #1788, mirroring #1245's
    # rule on PUT /settings/active-page). Without this a 22x6 Flagship page
    # could be selected as the silence page of a 15x3 Note board. There is no
    # board to validate against on an install-wide write.
    if board_id is not None and page_id:
        compat = check_ref_board_compatibility(page_id, board_id)
        if not compat.ok:
            raise HTTPException(status_code=400, detail=compat.error)

    updated = {
        "enabled": request.enabled,
        "start_time": request.start_time,
        "end_time": request.end_time,
        "mode": mode,
        "page_id": page_id,
        "indicator_text": indicator_text,
        "indicator_position": indicator_position,
    }

    if board_id is not None:
        success = config_manager.set_silence_schedule_for_board(board_id, updated)
    else:
        success = config_manager.set_feature("silence_schedule", updated)
        # The engine resolves silence per board on every install
        # (``check_and_send_for_board(primary_id, ...)``), so an install-wide
        # write that leaves a board-scoped copy in place is shadowed key by
        # key: the user turns silence off, the API says 200, and the board
        # keeps snoozing at the old time. On a single-board install there is
        # no meaningful difference between "the install default" and "this
        # board", so drop the override rather than let it win (issue #1788
        # review). Multi-board installs are untouched — there the overrides
        # are the whole point.
        if success:
            try:
                boards = get_settings_service().get_board_settings().boards or []
            except Exception:  # pragma: no cover - defensive: never fail the save
                boards = []
            if len(boards) == 1 and isinstance(boards[0], dict) and boards[0].get("id"):
                config_manager.prune_silence_schedule_for_board(str(boards[0]["id"]))
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to persist silence schedule configuration",
        )

    logger.info(
        "Silence schedule updated for board=%s: enabled=%s, start=%s, end=%s, mode=%s, page_id=%s, "
        "indicator_text=%s, indicator_position=%s",
        board_id or "(install-wide)",
        request.enabled,
        request.start_time,
        request.end_time,
        mode,
        page_id,
        indicator_text,
        indicator_position,
    )

    if board_id is not None:
        from src.config import resolve_silence_schedule

        config = resolve_silence_schedule(config_manager.get_feature("silence_schedule"), board_id)
    else:
        config = config_manager.get_feature("silence_schedule") or updated

    return {
        "status": "success",
        "config": config,
        "board_id": board_id,
    }


@router.get("/settings/transitions", response_model=TransitionSettingsResponse)
async def get_transition_settings():
    """Get current transition animation settings."""
    settings_service = get_settings_service()
    transition = settings_service.get_transition_settings()
    return {
        "strategy": transition.strategy,
        "step_interval_ms": transition.step_interval_ms,
        "step_size": transition.step_size,
        "available_strategies": VALID_STRATEGIES,
    }


@router.put("/settings/transitions", response_model=TransitionSettings, responses={**ERROR_400})
async def update_transition_settings(request: TransitionSettingsUpdate):
    """
    Update transition animation settings.

    Body can include:
    - strategy: One of column, reverse-column, edges-to-center, row, diagonal, random,
                "plugin:<id>" to drive a transition plugin, or null to disable.
    - step_interval_ms: Delay between animation steps (ms), or null for default
    - step_size: How many columns/rows animate at once, or null for default

    An explicit ``null`` clears a field; an omitted key leaves it alone.
    """
    settings_service = get_settings_service()

    # ... is the service's "not provided" sentinel; exclude_unset is what
    # keeps "omitted" distinguishable from an explicit null.
    provided = request.model_dump(exclude_unset=True)

    try:
        transition = settings_service.update_transition_settings(
            strategy=provided.get("strategy", ...),
            step_interval_ms=provided.get("step_interval_ms", ...),
            step_size=provided.get("step_size", ...),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return transition.to_dict()


@router.get("/settings/output", response_model=OutputSettingsResponse)
async def get_output_settings():
    """Get current output target settings."""
    settings_service = get_settings_service()
    output = settings_service.get_output_settings()
    return {"target": output.target, "effective_target": output.target, "available_targets": VALID_OUTPUT_TARGETS}


@router.put("/settings/output", response_model=OutputSettings, responses={**ERROR_400})
async def update_output_settings(request: OutputSettingsUpdate):
    """
    Update output target settings.

    Body should include:
    - target: One of "ui", "board", or "both"
    """
    settings_service = get_settings_service()

    try:
        output = settings_service.set_output_target(request.target)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Switching away from "ui" must resync the hardware (issue #1748). While
    # target was "ui" the display loop short-circuited before rendering, so
    # every board's content cache still holds whatever was last actually sent.
    # Without this the next poll sees "content unchanged, skipping send" and
    # the board stays stale until the content happens to change. The target is
    # a global setting, so every board is invalidated, not just the primary.
    svc = get_service()
    runtimes = getattr(svc, "runtimes", None) if svc else None
    # Only a real mapping is iterated (a Mock from an older fixture is not).
    if isinstance(runtimes, dict):
        for board_id in list(runtimes):
            try:
                svc.invalidate_board_content(board_id)
            except Exception as e:  # never fail the settings write on a cache reset
                logger.debug("Could not invalidate board %s after output-target change: %s", board_id, e)

    return output.to_dict()


@router.get("/settings/active-page")
async def get_active_page(board_id: str | None = None):
    """Get the currently active page ID.

    Args:
        board_id: Optional board to read (query param). Omitted → primary
            board, legacy behavior (issue #1244).
    """
    settings_service = get_settings_service()
    if board_id is not None:
        page_id = settings_service.get_active_page_id(board_id=board_id)
    else:
        page_id = settings_service.get_active_page_id()
    return {
        "page_id": page_id,
        "resolved_page_id": _resolve_active_page_id(page_id),
        "resolved_next_check_seconds": _resolve_next_check_seconds(page_id),
        "board_id": board_id,
    }


@router.put("/settings/active-page")
async def set_active_page(request: dict):
    """
    Set the active page ID.

    Body should include:
    - page_id: Page ID to set as active, or null to clear
    - board_id: Optional board to target. Omitted → primary board,
      legacy behavior (issue #1244).

    When a page is set, it will be immediately rendered and sent to the board.

    Response: ``sent_to_board`` reports whether content actually reached the
    board, and ``error`` carries the render/send failure reason (null when the
    send succeeded or was skipped benignly — paused board, UI-only output,
    unchanged content). The page selection itself is persisted either way.
    """
    settings_service = get_settings_service()
    page_service = get_page_service()
    service = get_service()

    page_id = request.get("page_id")
    board_id = request.get("board_id")
    board = None
    if board_id is not None:
        board = _require_board(board_id)
    collection_service = get_collection_service()

    # Validate page or collection exists if not clearing
    page = None
    render_page_id = page_id
    if page_id is not None:
        if is_collection_id(page_id):
            collection = collection_service.get_collection(page_id)
            if not collection:
                raise HTTPException(status_code=404, detail=f"Collection not found: {page_id}")
            render_page_id = collection_service.resolve_page_id(page_id)
            if render_page_id:
                page = page_service.get_page(render_page_id)
        else:
            page = page_service.get_page(page_id)
            if not page:
                raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    # Enforce page<->board size compatibility (issue #1245). Collections are
    # allowed when at least one member fits (non-fitting members become
    # warnings); plain pages must match the board size exactly.
    compat_warnings: list[str] = []
    if page_id is not None:
        compat = check_ref_board_compatibility(page_id, request.get("board_id"))
        if not compat.ok:
            raise HTTPException(status_code=400, detail=compat.error)
        compat_warnings = compat.warnings

    # Everything from the trigger dismissal through the board send blocks:
    # disk writes, a plugin-fan-out render, then the board network call plus
    # an up-to-seconds transition animation. It runs as one worker-thread
    # unit so the event loop keeps serving requests (#1826). The settings
    # write itself is not internally locked yet — per-store locking is
    # Track A2's job (#1848).
    def _work() -> tuple[bool, bool, str | None]:
        # Dismiss any active plugin triggers so the user's explicit page change
        # actually sticks. Without this, a plugin re-emitting the same trigger
        # every display loop tick (e.g. calendar_sub during a countdown window)
        # would silently overwrite the user's selection. See issue #856.
        if _api("PLUGIN_SYSTEM_AVAILABLE"):
            from src.triggers.service import get_trigger_service

            get_trigger_service().dismiss_active_for_user_override()

        # Set the active page (stores the collection ID or page ID as-is).
        # An explicit board_id targets that board's slot; omitted keeps the
        # legacy primary-board call (issue #1244).
        if board_id is not None:
            settings_service.set_active_page_id(page_id, board_id=board_id)
        else:
            settings_service.set_active_page_id(page_id)

        # Resolve the client for the immediate send: explicit board_id routes to
        # that board's client, omitted keeps the legacy primary-client path.
        send_client = None
        if service:
            send_client = service.get_board_client(board_id) if board_id is not None else service.vb_client

        # Immediately send to board if a page is set. The page selection is
        # persisted either way; a failed render/send is a partial failure that
        # must be reported, not silently swallowed (issue #1791).
        sent_to_board = False
        paused = False
        send_error: str | None = None
        if render_page_id and page and send_client and settings_service.should_send_to_board():
            # Skip immediate send when the board is paused (issue #970). The
            # active-page selection is still persisted so it takes effect when
            # the user later resumes the board.
            if _board_is_paused(board_id):
                logger.info("Board is paused - skipping immediate active-page send")
                paused = True
            else:
                result = page_service.preview_page(render_page_id, force_refresh=True)
                if result and result.available:
                    system_transition = settings_service.get_transition_settings()
                    strategy = page.transition_strategy if page.transition_strategy else system_transition.strategy
                    interval_ms = (
                        page.transition_interval_ms
                        if page.transition_interval_ms is not None
                        else system_transition.step_interval_ms
                    )
                    step_size = (
                        page.transition_step_size
                        if page.transition_step_size is not None
                        else system_transition.step_size
                    )

                    # Size the grid to the explicit target board when given
                    # (issue #1244); otherwise keep the page's device type.
                    if board is not None:
                        dims = _board_dims(board)
                    else:
                        dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
                    board_array = text_to_board_array(result.formatted, rows=dims.rows, cols=dims.cols)
                    # render() serializes concurrent senders via the client's
                    # per-board _send_lock, so worker threads can't interleave.
                    success, was_sent = send_client.render(
                        board_array,
                        strategy=strategy,
                        step_interval_ms=interval_ms,
                        step_size=step_size,
                        device_type=(board.get("device_type") if board is not None else page.device_type),
                    )
                    sent_to_board = was_sent
                    if not success:
                        send_error = f"Failed to send page to board: {page_id}"
                        logger.warning(f"Failed to send active page to board: {page_id}")
                    elif was_sent and (board_id is None or board_id == settings_service.get_primary_board_id()):
                        # Adaptive post-send refresh polls the primary board only.
                        service.request_board_refresh()
                else:
                    # A network/plugin failure surfaces here as an unavailable
                    # render — report it instead of skipping silently (#1791).
                    render_error = getattr(result, "error", None) if result else None
                    send_error = render_error or f"Failed to render page: {render_page_id}"
                    logger.warning(f"Active page set but render unavailable, not sent: {render_page_id}")
        return sent_to_board, paused, send_error

    sent_to_board, paused, send_error = await run_board_send(_work)

    # status stays "success" (the page selection itself was persisted); a
    # render/send problem is reported via error + sent_to_board=False, the
    # same partial-failure contract page-builder already consumes.
    response = {
        "status": "success",
        "page_id": page_id,
        "sent_to_board": sent_to_board,
        "paused": paused,
        "board_id": board_id,
        "error": send_error,
    }
    if compat_warnings:
        response["warnings"] = compat_warnings
    return response


@router.get("/settings/temporary-override")
async def get_temporary_override():
    """Get the current temporary override status."""
    settings_service = get_settings_service()
    return _temporary_override_payload(settings_service.get_temporary_override())


@router.post("/settings/temporary-override")
async def set_temporary_override(request: dict):
    """
    Activate a temporary override, from a saved page or from inline content.

    Exactly one of ``page_id`` or ``template`` must be supplied.

    Body:
      - page_id (str): Page (or collection) to show during the override
      - template (list[str]): Inline one-off board content, never persisted as
        a Page (issue #1787)
      - line_metadata (list[dict], optional): Per-line alignment/wrap for the
        inline form
      - device_type (str, optional): Geometry the inline content was composed
        for ("flagship" | "note" | "note_array"); defaults to flagship
      - notes_wide / notes_tall (int, optional): note_array geometry
      - duration_minutes (int, optional): How long to show it (1–480). Omit for
        an indefinite override that lasts until the user cancels it.
      - revert_mode (str, optional): "schedule" | "blank" | "page" (default: "schedule")
      - revert_page_id (str, optional): Required when revert_mode is "page"

    Deliberately not guarded by silence or pause: a user-initiated override is
    meant to beat the silence schedule (issue #949).
    """
    from datetime import datetime, timedelta

    from src.devices import DEFAULT_DEVICE_TYPE, DEVICE_TYPES, MAX_NOTES_PER_AXIS

    from .service import (
        TEMPORARY_OVERRIDE_DURATION_MAX,
        TEMPORARY_OVERRIDE_DURATION_MIN,
        VALID_REVERT_MODES,
        TemporaryOverride,
    )

    settings_service = get_settings_service()
    page_service = get_page_service()

    page_id = request.get("page_id")
    template = request.get("template")

    if page_id and template is not None:
        raise HTTPException(status_code=422, detail="Supply either page_id or template, not both")
    if not page_id and template is None:
        raise HTTPException(status_code=422, detail="Either page_id or template is required")

    device_type = None
    line_metadata = None
    notes_wide = None
    notes_tall = None

    if template is not None:
        # --- Inline (one-off) form ---
        if not isinstance(template, list) or not template:
            raise HTTPException(status_code=422, detail="template must be a non-empty list of strings")
        if not all(isinstance(line, str) for line in template):
            raise HTTPException(status_code=422, detail="template must contain only strings")

        device_type = request.get("device_type") or DEFAULT_DEVICE_TYPE
        if device_type not in DEVICE_TYPES:
            raise HTTPException(status_code=422, detail=f"device_type must be one of {list(DEVICE_TYPES)}")

        line_metadata = request.get("line_metadata")
        if line_metadata is not None and (
            not isinstance(line_metadata, list) or not all(isinstance(m, dict) for m in line_metadata)
        ):
            raise HTTPException(status_code=422, detail="line_metadata must be a list of objects")

        for key, raw in (("notes_wide", request.get("notes_wide")), ("notes_tall", request.get("notes_tall"))):
            if raw is None:
                continue
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"{key} must be an integer") from None
            if not (1 <= value <= MAX_NOTES_PER_AXIS):
                raise HTTPException(status_code=422, detail=f"{key} must be between 1 and {MAX_NOTES_PER_AXIS}")
            if key == "notes_wide":
                notes_wide = value
            else:
                notes_tall = value

        dims = resolve_dimensions(device_type, notes_wide or 1, notes_tall or 1)
        if len(template) > dims.rows:
            raise HTTPException(
                status_code=422,
                detail=f"template has {len(template)} lines but this board fits {dims.rows}",
            )
    else:
        # --- Saved page form (unchanged; collections are also valid) ---
        if not is_collection_id(page_id):
            if not page_service.get_page(page_id):
                raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
        else:
            collection_service = get_collection_service()
            if not collection_service.get_collection(page_id):
                raise HTTPException(status_code=404, detail=f"Collection not found: {page_id}")

    duration_minutes = request.get("duration_minutes")
    expires_at = None
    if duration_minutes is not None:
        try:
            duration_minutes = int(duration_minutes)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="duration_minutes must be an integer") from None
        if not (TEMPORARY_OVERRIDE_DURATION_MIN <= duration_minutes <= TEMPORARY_OVERRIDE_DURATION_MAX):
            raise HTTPException(
                status_code=422,
                detail=f"duration_minutes must be between {TEMPORARY_OVERRIDE_DURATION_MIN} and {TEMPORARY_OVERRIDE_DURATION_MAX}",
            )
        expires_at = (datetime.now(UTC) + timedelta(minutes=duration_minutes)).isoformat()

    revert_mode = request.get("revert_mode", "schedule")
    if revert_mode not in VALID_REVERT_MODES:
        raise HTTPException(status_code=422, detail=f"revert_mode must be one of {VALID_REVERT_MODES}")

    revert_page_id = request.get("revert_page_id")
    if revert_mode == "page":
        if not revert_page_id:
            raise HTTPException(status_code=422, detail="revert_page_id is required when revert_mode is 'page'")
        if not is_collection_id(revert_page_id):
            if not page_service.get_page(revert_page_id):
                raise HTTPException(status_code=404, detail=f"Revert page not found: {revert_page_id}")

    override = TemporaryOverride(
        page_id=page_id or None,
        expires_at=expires_at,
        revert_mode=revert_mode,
        revert_page_id=revert_page_id,
        template=template,
        line_metadata=line_metadata,
        device_type=device_type,
        notes_wide=notes_wide,
        notes_tall=notes_tall,
    )
    settings_service.set_temporary_override(override)

    # Clear the display cache so the next poll sends the override immediately
    svc = get_service()
    if svc:
        svc._last_active_page_content = None

    return _temporary_override_payload(override)


@router.delete("/settings/temporary-override")
async def clear_temporary_override():
    """Cancel the active temporary override and trigger an immediate board refresh."""
    settings_service = get_settings_service()
    override = settings_service.get_temporary_override()
    revert_mode = override.revert_mode if override else None
    settings_service.clear_temporary_override()

    # Apply revert side-effects server-side (same logic as expiry in the display loop)
    if override and override.revert_mode == "page" and override.revert_page_id:
        settings_service.set_active_page_id(override.revert_page_id)

    # Force an immediate re-render so the board shows the reverted state
    svc = get_service()
    if svc:
        svc._last_active_page_content = None

    return {"status": "cleared", "revert_mode": revert_mode}


@router.get("/settings/polling", response_model=PollingSettings)
async def get_polling_settings():
    """Get current polling interval settings."""
    settings_service = get_settings_service()
    polling = settings_service.get_polling_settings()
    return polling.to_dict()


@router.put("/settings/polling", response_model=PollingSettingsResponse, responses={**ERROR_400})
async def update_polling_settings(request: PollingSettingsUpdate):
    """
    Update polling interval settings.

    Accepted body fields:
    - interval_seconds: How often FiestaBoard checks active page (min 10, requires restart)
    - board_read_interval_local: How often to read board state in local mode (min 20)
    - board_read_interval_cloud: How often to read board state in cloud mode (min 20)

    Only the intervals present in the body are changed.
    """
    settings_service = get_settings_service()
    provided = request.model_dump(exclude_unset=True)
    requires_restart = False

    try:
        if "interval_seconds" in provided:
            settings_service.set_polling_interval(int(provided["interval_seconds"]))
            requires_restart = True

        if "board_read_interval_local" in provided or "board_read_interval_cloud" in provided:
            local = provided.get("board_read_interval_local")
            cloud = provided.get("board_read_interval_cloud")
            settings_service.set_board_read_intervals(
                local_seconds=int(local) if local is not None else None,
                cloud_seconds=int(cloud) if cloud is not None else None,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    polling = settings_service.get_polling_settings()
    return {**polling.to_dict(), "requires_restart": requires_restart}


@router.get("/settings/board")
async def get_board_settings():
    """Get current board settings (display type, boards array, devices)."""
    settings_service = get_settings_service()
    board = settings_service.get_board_settings()
    return board.to_dict()


@router.put("/settings/board")
async def update_board_settings(request: dict):
    """
    Update board settings.

    Body may include:
    - board_type: "black", "white", or null for default
    - devices: list of device types (e.g. ["flagship", "note"]) for backward compatibility
    - boards: full list of board instance dicts
    """
    settings_service = get_settings_service()

    try:
        if "devices" in request:
            devices = request["devices"]
            if not isinstance(devices, list):
                raise HTTPException(status_code=400, detail="devices must be a list")
            board = settings_service.set_devices(devices)
            _reinitialize_board_clients()
            return {"status": "success", "settings": board.to_dict()}
        if "boards" in request:
            boards = request["boards"]
            if not isinstance(boards, list):
                raise HTTPException(status_code=400, detail="boards must be a list")
            board = settings_service.set_boards(boards)
            _reinitialize_board_clients()
            return {"status": "success", "settings": board.to_dict()}
        if "board_type" in request:
            board_type = request["board_type"]
            board = settings_service.set_board_type(board_type)
            return {"status": "success", "settings": board.to_dict()}
        raise HTTPException(
            status_code=400,
            detail="One of board_type, devices, or boards is required",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/settings/board/add")
async def add_board_instance(request: dict):
    """Add a new board instance. Body: device_type, optional name and other board fields."""
    if "device_type" not in request:
        raise HTTPException(status_code=400, detail="device_type is required")
    settings_service = get_settings_service()
    try:
        board = settings_service.add_board(request)
        _reinitialize_board_clients()
        return {"status": "success", "settings": board.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/settings/board/{board_id}")
async def remove_board_instance(board_id: str):
    """Remove a board instance by ID.

    A board still referenced by a FiestaPanel is removed by deleting the
    panel — pulling it out from under a live panel blanks the TV and
    orphans the panel, so that request is refused with a 409.
    """
    referencing_panel = next(
        (p for p in get_panel_service().list_panels() if p.board_id == board_id),
        None,
    )
    if referencing_panel is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Board is in use by FiestaPanel '{referencing_panel.name}'. "
                "Delete the panel in Settings → FiestaPanel instead."
            ),
        )
    settings_service = get_settings_service()
    try:
        board = settings_service.remove_board(board_id)
        _reinitialize_board_clients()
        return {"status": "success", "settings": board.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/settings/board/{board_id}/pause")
async def set_board_paused(board_id: str, request: dict):
    """Pause or resume a board (issue #970).

    Body: ``{"paused": bool}``. When paused, FiestaBoard will not push
    anything to this board from any code path (polling loop, schedule,
    manual sends, plugin triggers, MQTT, debug, welcome, etc) until the
    board is resumed.
    """
    if "paused" not in request:
        raise HTTPException(status_code=400, detail="paused is required")
    if not isinstance(request["paused"], bool):
        raise HTTPException(status_code=400, detail="paused must be a boolean")
    _require_board(board_id)
    settings_service = get_settings_service()
    paused = settings_service.set_paused(request["paused"], board_id=board_id)
    return {
        "status": "success",
        "board_id": board_id,
        "paused": paused,
        "settings": settings_service.get_board_settings().to_dict(),
    }


@router.post("/settings/board/{board_id}/detect-size")
async def detect_board_size(board_id: str):
    """Auto-detect a board's device type and dimensions from its live layout.

    Reads the board's current message over its own transport (local / cloud /
    note-array, via ``board_client_from_board_dict``) and classifies the grid
    shape with :func:`classify_dimensions`.

    Returns ``device_type``, ``rows``, ``cols`` and — for note arrays —
    ``notes_wide``, ``notes_tall`` and ``matched_preset``.

    Errors: 404 (unknown board), 400 (board not configured), 422 (board
    returned no layout, or an unclassifiable grid).
    """
    settings_service = get_settings_service()
    boards = settings_service.get_board_settings().boards or []

    board_dict = next((b for b in boards if b.get("id") == board_id), None)
    if board_dict is None:
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")

    from src.devices import BoardInstance

    # A local-mode array's shape is DEFINED by its tile assignments — a local
    # read can only re-stitch the configured W×H (or fail on a partial array),
    # so "detection" would be a tautology. Only the Cloud API knows an array's
    # real shape; reject clearly instead of echoing the configuration back.
    if BoardInstance.from_dict(board_dict).uses_local_tiles:
        raise HTTPException(
            status_code=400,
            detail="Auto-detect is not available for local-mode note arrays — "
            "the array's size is defined by its tile assignments",
        )

    client = board_client_from_board_dict(board_dict)
    if client is None:
        raise HTTPException(
            status_code=400,
            detail=f"Board {board_id} is not configured (missing credentials)",
        )

    grid = client.read_current_message()
    if grid is None:
        raise HTTPException(
            status_code=422,
            detail=f"Board {board_id} returned no layout — board may be blank or unreachable",
        )

    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    try:
        return classify_dimensions(rows, cols)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Board {board_id} returned an unclassifiable grid ({rows}×{cols}): {exc}",
        ) from exc


class BoardIdentifyRequest(BaseModel):
    """Request body for the local note-array identify flash.

    ``target: "tile"`` identifies one slot (``row``/``col`` required unless
    the credential override is supplied); ``target: "all"`` flashes every
    configured tile at once. The optional ``host``/``port``/``local_api_key``
    override lets the assign dialog identify a board BEFORE its tile is
    saved — in that case ``row``/``col`` name the slot being assigned.
    """

    target: str = "tile"
    row: int | None = None
    col: int | None = None
    host: str | None = None
    port: int | None = None
    local_api_key: str | None = None


@router.post("/settings/board/{board_id}/identify")
async def identify_board_tiles(board_id: str, request: BoardIdentifyRequest):
    """Flash slot positions onto local note-array tiles (monitor-arrangement style).

    Sends each targeted tile a 3×15 pattern labeling its slot so the user
    can see which physical board answers for which grid position. The real
    frame is restored automatically on the next display-loop cycle (the
    board's content dedupe and client caches are invalidated here); on a
    paused board the pattern persists until the board is resumed.

    Errors: 404 (unknown board), 400 (not a note array in local mode, bad
    target, or missing/unknown tile).
    """
    from src.devices import BoardInstance, identify_pattern, is_note_array

    settings_service = get_settings_service()
    boards = settings_service.get_board_settings().boards or []
    board_dict = next((b for b in boards if b.get("id") == board_id), None)
    if board_dict is None:
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")

    instance = BoardInstance.from_dict(board_dict)
    if not is_note_array(instance.device_type) or instance.api_mode != "local":
        raise HTTPException(
            status_code=400,
            detail="Identify is only available for note arrays in local API mode",
        )

    if request.target not in ("tile", "all"):
        raise HTTPException(status_code=400, detail='target must be "tile" or "all"')

    # Resolve the set of (row, col, host, port, key) endpoints to flash
    targets: list[dict] = []
    if request.host is not None or request.local_api_key is not None:
        # Unsaved-tile override from the assign dialog
        if request.target != "tile" or request.row is None or request.col is None:
            raise HTTPException(
                status_code=400,
                detail="Credential override requires target='tile' with row and col",
            )
        if not request.host or not request.local_api_key:
            raise HTTPException(status_code=400, detail="host and local_api_key are both required")
        _validate_board_host(request.host)
        _validate_board_host_is_local_network(request.host)
        targets.append(
            {
                "row": request.row,
                "col": request.col,
                "host": request.host,
                "port": request.port or 7000,
                "local_api_key": request.local_api_key,
            }
        )
    else:
        configured = instance.configured_tiles()
        if request.target == "all":
            targets = configured
        else:
            if request.row is None or request.col is None:
                raise HTTPException(status_code=400, detail="row and col are required for target='tile'")
            tile = next(
                (t for t in configured if t["row"] == request.row and t["col"] == request.col),
                None,
            )
            if tile is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"No configured tile at row={request.row}, col={request.col}",
                )
            targets = [tile]
        if not targets:
            raise HTTPException(status_code=400, detail="Board has no configured tiles to identify")

    def flash_tile(tile: dict) -> dict:
        from src.board_client import BoardClient

        pattern = identify_pattern(tile["row"], tile["col"], instance.notes_wide)
        try:
            client = BoardClient(
                api_key=tile["local_api_key"],
                host=tile["host"],
                use_cloud=False,
                skip_unchanged=False,
                port=tile.get("port") or None,
            )
            success, _ = client.send_characters(pattern, force=True)
        except Exception as exc:  # noqa: BLE001 — per-tile failure must not abort the rest
            logger.error(f"Identify failed for tile ({tile['row']},{tile['col']}): {exc}")
            success = False
        return {"row": tile["row"], "col": tile["col"], "success": success}

    results = await asyncio.gather(*(asyncio.to_thread(flash_tile, t) for t in targets))

    # Restore: invalidate the display loop's dedupe + client caches so the
    # next cycle re-sends the real frame over the identify pattern.
    service = get_service()
    if service is not None:
        service.invalidate_board_content(board_id)

    return {"status": "success", "board_id": board_id, "results": list(results)}


@router.get("/settings/display", response_model=DisplaySettingsResponse)
async def get_display_settings():
    """Get current web UI display settings."""
    settings_service = get_settings_service()
    return settings_service.get_display_settings().to_dict()


@router.put("/settings/display", response_model=DisplaySettingsResponse, responses={**ERROR_400})
async def update_display_settings(request: DisplaySettingsUpdate):
    """
    Update web UI display settings.

    Body may include:
    - reduce_motion: bool — force reduced-motion CSS behaviour in the UI
    - board_animations: "on" | "desktop" | "off" — control split-flap board
      animation. "desktop" disables it on mobile screens only.
    - site_animations: "on" | "off" — control general UI transitions/hovers.
    - board_flap_speed: "hardware" | "quick" | "standard" | "relaxed", or a
      raw millisecond count clamped to [8, 2000] — how fast a tile flips one
      character in the ON-SCREEN board preview. Default "standard" (80ms).
      This is not the physical board: pacing for the hardware lives in
      /settings/transitions (step_interval_ms / step_size).
    """
    settings_service = get_settings_service()
    display = settings_service.update_display_settings(request.model_dump(exclude_unset=True))
    return display.to_dict()


@router.get("/settings/location", response_model=LocationSettingsResponse)
async def get_location_settings():
    """Get current location settings for sun-based schedules (sunrise/sunset)."""
    settings_service = get_settings_service()
    return settings_service.get_location_settings().to_dict()


@router.put("/settings/location", response_model=LocationSettingsResponse, responses={**ERROR_400})
async def update_location_settings(request: LocationSettingsUpdate):
    """
    Update location settings for sun-based schedules.

    Body may include:
    - latitude: float | null — Location latitude (-90 to 90)
    - longitude: float | null — Location longitude (-180 to 180)
    """
    settings_service = get_settings_service()
    location = settings_service.update_location_settings(request.model_dump(exclude_unset=True))
    return location.to_dict()


@router.get("/settings/location/sun-times", response_model=SunTimesResponse, responses={**ERROR_400})
async def get_location_sun_times(date: str | None = None):
    """
    Get sunrise and sunset times for the configured location on a given date.

    Query params:
    - date: ISO date string (YYYY-MM-DD); defaults to today in the configured timezone.

    Returns sunrise and sunset as HH:MM strings, or null values if location is not
    configured or sun times cannot be computed (e.g. polar day/night).
    """
    from datetime import date as date_cls

    from src.schedules.sun_times import (
        get_effective_timezone,
        get_sun_times,
        get_today_in_timezone,
    )

    settings_service = get_settings_service()
    location = settings_service.get_location_settings()

    if location.latitude is None or location.longitude is None:
        return {"sunrise": None, "sunset": None, "location_configured": False}

    timezone_str = get_effective_timezone()

    if date:
        try:
            target_date = date_cls.fromisoformat(date)
        except ValueError:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.") from None
    else:
        target_date = get_today_in_timezone(timezone_str)

    times = get_sun_times(location.latitude, location.longitude, target_date, timezone_str)
    if times is None:
        return {"sunrise": None, "sunset": None, "location_configured": True}

    return {
        "sunrise": times["sunrise"].strftime("%H:%M"),
        "sunset": times["sunset"].strftime("%H:%M"),
        "location_configured": True,
    }


@router.get(
    "/settings/location/sun-times-week",
    response_model=SunTimesWeekResponse,
    responses={**ERROR_400},
)
async def get_location_sun_times_week(week_start: str):
    """
    Get sunrise and sunset times for each day of a 7-day week.

    Query params:
    - week_start: ISO date string (YYYY-MM-DD) for the first day of the week.

    Returns a map of date strings to { sunrise, sunset } HH:MM values.
    """
    from datetime import date as date_cls
    from datetime import timedelta

    from src.schedules.sun_times import get_effective_timezone, get_sun_times

    settings_service = get_settings_service()
    location = settings_service.get_location_settings()

    if location.latitude is None or location.longitude is None:
        return {"location_configured": False, "dates": {}}

    timezone_str = get_effective_timezone()

    try:
        start = date_cls.fromisoformat(week_start)
    except ValueError:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Invalid week_start format. Use YYYY-MM-DD.") from None

    result: dict = {}
    for i in range(7):
        day = start + timedelta(days=i)
        times = get_sun_times(location.latitude, location.longitude, day, timezone_str)
        if times:
            result[day.isoformat()] = {
                "sunrise": times["sunrise"].strftime("%H:%M"),
                "sunset": times["sunset"].strftime("%H:%M"),
            }

    return {"location_configured": True, "dates": result}


def _beta_https_status() -> dict[str, Any]:
    """Return the runtime status of the HTTPS beta feature.

    Reports whether the cert files currently exist on disk and whether
    the fiestaupdater sidecar is reachable for one-click restarts.
    """
    from src.system import https_certs

    cert_path, key_path = https_certs.cert_paths()
    return {
        "cert_present": https_certs.cert_exists(),
        "cert_path": str(cert_path),
        "key_path": str(key_path),
        "updater_available": bool(_updater_token()) and _updater_probe(),
    }


@router.get("/settings/beta")
async def get_beta_settings():
    """Get opt-in beta-feature settings + runtime status."""
    settings_service = get_settings_service()
    settings = settings_service.get_beta_settings()
    status = await asyncio.to_thread(_beta_https_status)
    return {
        "settings": settings.to_dict(),
        "https": status,
    }


@router.put("/settings/beta")
async def update_beta_settings(request: dict):
    """Update beta-feature settings.

    Body may include:
    - https_enabled: bool — enable/disable the HTTPS (Beta) feature.
    - transition_plugins_enabled: bool — enable/disable the experimental
      transition-plugin system (frame-by-frame board animations). Takes
      effect immediately; no restart required.

    Side effects:
    - When https_enabled flips to ``true``, a self-signed certificate is
      generated under ``data/certs/`` (if not already present). nginx
      will switch to HTTPS the next time the container starts.
    - When https_enabled flips to ``false``, the cert files are removed
      so the next container start reverts to HTTP.

    Returns the updated settings, the cert status, and a hint about
    whether a restart is required for the change to take effect.
    """
    from src.system import https_certs

    settings_service = get_settings_service()
    previous = settings_service.get_beta_settings().https_enabled
    requested = request.get("https_enabled", previous) if isinstance(request, dict) else previous

    cert_error: str | None = None
    if "https_enabled" in (request or {}):
        if requested and not previous:
            # User just turned HTTPS on -> generate cert eagerly so nginx
            # finds it on the next restart. Failure here shouldn't block
            # persisting the user's preference, but we surface the error.
            try:
                await asyncio.to_thread(https_certs.generate_cert)
            except Exception:  # noqa: BLE001 - report to caller
                # Full detail stays in the server log; the raw exception can
                # carry paths/config internals (CodeQL py/stack-trace-exposure).
                logger.exception("Failed to generate HTTPS certificate")
                cert_error = "Certificate generation failed — check the server logs for details."
        elif previous and not requested:
            # User just turned HTTPS off -> remove the cert so nginx
            # falls back to HTTP on next restart.
            try:
                await asyncio.to_thread(https_certs.remove_cert)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to remove HTTPS certificate: %s", e)

    updated = settings_service.update_beta_settings(request or {})
    status = await asyncio.to_thread(_beta_https_status)

    # A restart is required whenever the on/off state changed, since
    # nginx only re-reads its config on container start.
    restart_required = updated.https_enabled != previous

    response: dict[str, Any] = {
        "status": "success",
        "settings": updated.to_dict(),
        "https": status,
        "restart_required": restart_required,
    }
    if cert_error:
        response["status"] = "warning"
        response["cert_error"] = cert_error
    return response


@router.get("/settings/plugins", response_model=PluginSettingsResponse)
async def get_plugin_settings():
    """Get plugin system settings."""
    settings_service = get_settings_service()
    return settings_service.get_plugin_settings().to_dict()


@router.put("/settings/plugins", response_model=PluginSettingsResponse, responses={**ERROR_400})
async def update_plugin_settings(request: PluginSettingsUpdate):
    """Update plugin system settings.

    Body may include:
    - auto_update: bool — when true, plugins are updated automatically in the background.

    ``auto_update`` is a ``StrictBool``: ``"yes"`` is a 422, not a silent
    opt-in to background plugin updates.
    """
    settings_service = get_settings_service()
    updated = settings_service.update_plugin_settings(request.model_dump(exclude_unset=True))
    return updated.to_dict()


@router.get("/settings/all")
async def get_all_settings():
    """
    Get all settings in a single request.

    Returns consolidated settings for the settings page including:
    - general config (timezone, etc.)
    - silence_schedule plugin config
    - polling interval settings
    - transitions settings
    - output settings
    - board settings
    - mqtt integration settings
    - display settings
    - service status (running)
    """
    settings_service = get_settings_service()
    config_manager = get_config_manager()

    # Get silence schedule config (stored under features, not plugins)
    silence_feature = config_manager.get_feature("silence_schedule") or {}

    # Get all other settings
    general = config_manager.get_general()
    polling = settings_service.get_polling_settings()
    transitions = settings_service.get_transition_settings()
    output = settings_service.get_output_settings()
    board = settings_service.get_board_settings()
    mqtt = settings_service.get_mqtt_settings()
    display = settings_service.get_display_settings()
    location = settings_service.get_location_settings()
    beta = settings_service.get_beta_settings()
    plugins = settings_service.get_plugin_settings()

    return {
        "general": general,
        "silence_schedule": {"config": silence_feature},
        "polling": polling.to_dict(),
        "transitions": {**transitions.to_dict(), "available_strategies": VALID_STRATEGIES},
        "output": output.to_dict(),
        "board": board.to_dict(),
        "mqtt": mqtt.to_dict(mask_secrets=True),
        "display": display.to_dict(),
        "location": location.to_dict(),
        "beta": beta.to_dict(),
        "plugins": plugins.to_dict(),
        "status": {
            "running": _api("_service_running"),
        },
    }


def _hdmi_kiosk_supported() -> bool:
    """The in-app HDMI kiosk controls exist only on FiestaPi installs with a
    reachable fiestaupdater sidecar — the sidecar is the sole component that
    can mutate the host OS (via its Docker socket)."""
    return _fiestaboard_profile() == "pi" and _updater_probe()


@router.get("/settings/hdmi-kiosk")
async def get_hdmi_kiosk_status():
    """Status of the FiestaPi HDMI kiosk (Settings → FiestaPanel UI)."""
    if not _hdmi_kiosk_supported():
        return {"supported": False, "status": "unsupported"}
    status: dict = {"status": "unknown"}
    try:
        resp = requests.get(f"{_updater_url()}/hdmi/status", timeout=3)
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, dict):
                status = body
    except Exception as e:
        logger.debug("fiestaupdater /hdmi/status fetch failed: %s", e)
    return {"supported": True, **status}


@router.post("/settings/hdmi-kiosk")
async def set_hdmi_kiosk(request: dict):
    """Enable or disable the HDMI kiosk on this FiestaPi.

    Proxies to the sidecar's fixed /hdmi/enable | /hdmi/disable verbs; the
    sidecar performs the host-side install through its Docker socket. Body:
    ``{"enabled": bool}``.
    """
    if "enabled" not in request or not isinstance(request["enabled"], bool):
        raise HTTPException(status_code=400, detail="enabled (boolean) is required")
    if not _hdmi_kiosk_supported():
        raise HTTPException(
            status_code=400,
            detail="HDMI kiosk controls are only available on FiestaPi installs with the updater sidecar",
        )
    verb = "enable" if request["enabled"] else "disable"
    try:
        resp = requests.post(
            f"{_updater_url()}/hdmi/{verb}",
            headers={"Authorization": f"Bearer {_updater_token()}"},
            timeout=10,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach the updater sidecar: {e}") from e
    if resp.status_code == 404:
        # Fleet sidecar predates the hdmi verbs. The Pi's boot service pulls
        # the newest sidecar image on every boot, so a reboot upgrades it.
        raise HTTPException(
            status_code=409,
            detail="The updater sidecar on this Pi is too old for HDMI controls — reboot the Pi to update it, then try again",
        )
    if resp.status_code not in (200, 202):
        raise HTTPException(status_code=502, detail=f"Updater sidecar error: {resp.status_code}")
    try:
        return resp.json()
    except Exception:
        return {"status": "queued", "action": f"hdmi_{verb}"}
