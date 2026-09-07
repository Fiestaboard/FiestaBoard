"""FastAPI router for the transition-plugin endpoints (beta).

Handlers were moved here from ``src/api_server.py`` (Phase 2 slice 8, Task 8)
into the existing ``src/transitions`` package — it already owns the runner —
and the conventions pass was applied in the same commit.

Every route is gated behind ``beta.transition_plugins_enabled`` and answers
404 while it is off: the SDK is experimental and the feature is meant to be
invisible until the operator opts in.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``
(``tests/test_small_domains_decoupled.py`` asserts that in a fresh
interpreter). Tests that need to stub a collaborator — or the module-level
``LIVE_TEST_FROM_HOLD_SECONDS`` seam — patch it where this module binds it:
``src.transitions.routes.<name>``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from src.api_errors import errors
from src.board_guards import _board_dims, _board_is_paused, _require_board, _silence_active
from src.board_send_executor import run_board_send
from src.collections.models import is_collection_id
from src.collections.service import get_collection_service
from src.devices import resolve_dimensions
from src.display_runtime import get_service
from src.pages.service import get_page_service
from src.plugins.registry import get_plugin_registry
from src.settings.service import get_settings_service
from src.text_to_board import text_to_board_array

from .models import (
    TransitionFrame,
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

    from src.plugins.base import TransitionPluginBase

    registry = get_plugin_registry()
    out = []
    # registry.plugins copies under the registry lock, so a concurrent
    # install/uninstall can't mutate the dict mid-iteration (#1828).
    for plugin_id, plugin in registry.plugins.items():
        if not isinstance(plugin, TransitionPluginBase):
            continue
        manifest = registry.get_manifest(plugin_id)
        if manifest is None:
            continue
        out.append(
            {
                "id": plugin_id,
                "name": manifest.name,
                "description": manifest.description,
                "icon": manifest.icon,
                "version": manifest.version,
                "author": manifest.author,
                "settings_schema": manifest.settings_schema,
                "transition_settings": plugin.transition_settings,
                "config": dict(plugin.config or {}),
                "strategy": f"plugin:{plugin_id}",
            }
        )
    out.sort(key=lambda e: e["name"].lower())
    return TransitionPluginsResponse(plugins=[TransitionPluginEntry.model_validate(entry) for entry in out])


@router.post(
    "/transitions/preview",
    response_model=TransitionPreviewResponse,
    responses=errors(400, 404, 500, 504),
)
async def preview_transition(request: TransitionPreviewRequest):
    """Drive a transition plugin once and return its frame sequence.

    Gated behind ``beta.transition_plugins_enabled`` -- see
    ``_ensure_transition_plugins_beta``.
    """
    _ensure_transition_plugins_beta()
    return await _preview_transition_impl(request)


async def _preview_transition_impl(request: TransitionPreviewRequest) -> TransitionPreviewResponse:
    """Run a transition plugin once and return the resulting frame sequence.

    Designed for the standalone /transitions test harness in the web UI.
    Frames are generated in-process and returned as JSON; nothing is sent
    to a real board.

    Request body:
      - plugin_id (str, required): the transition plugin to drive
      - from_text (str, optional): text to render into the from-grid
        (uses text_to_board_array).  Defaults to a blank grid.
      - to_text (str, required): text to render into the to-grid
      - config (dict, optional): per-run overrides for the plugin's
        settings_schema fields.  Merged on top of the plugin's
        currently-bound config.
      - device_type (str, optional): "flagship" (default), "note", or
        "note_array" (sized by notes_wide/notes_tall)
      - notes_wide, notes_tall (int, optional): note-array geometry
        (1-8 each; only used when device_type is "note_array")

    Response:
      ``{"frames": [{"grid": [[..]], "delay_ms": int}, ...],
         "total_delay_ms": int, "capped": bool, "plugin_id": str}``

    The runner's caps (max_frames, max_runtime_seconds, min_interval_ms)
    are honored.  If the plugin exceeds either max_frames or
    max_runtime_seconds the response is truncated and ``capped`` is set
    to true so the UI can display a hint.

    Iteration happens on a worker thread (``asyncio.to_thread``) so a
    slow / runaway plugin generator cannot block FastAPI's event loop.
    """
    from src.devices import MAX_NOTES_PER_AXIS, board_context_for

    plugin_id = request.plugin_id
    if not plugin_id or not isinstance(plugin_id, str):
        raise HTTPException(status_code=400, detail="plugin_id is required")

    registry = get_plugin_registry()
    plugin = registry.get_transition_plugin(plugin_id)
    if plugin is None:
        raise HTTPException(
            status_code=404,
            detail=f"Transition plugin {plugin_id!r} not loaded or not enabled",
        )

    device_type = request.device_type
    if device_type not in ("flagship", "note", "note_array"):
        raise HTTPException(status_code=400, detail=f"Unknown device_type: {device_type}")
    try:
        notes_wide = int(request.notes_wide)
        notes_tall = int(request.notes_tall)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="notes_wide/notes_tall must be integers") from exc
    if not (1 <= notes_wide <= MAX_NOTES_PER_AXIS and 1 <= notes_tall <= MAX_NOTES_PER_AXIS):
        raise HTTPException(
            status_code=400,
            detail=f"notes_wide/notes_tall must be between 1 and {MAX_NOTES_PER_AXIS}",
        )
    device = board_context_for(device_type, notes_wide=notes_wide, notes_tall=notes_tall)

    from_text = request.from_text
    to_text = request.to_text
    from_grid = text_to_board_array(from_text, rows=device.rows, cols=device.cols)
    to_grid = text_to_board_array(to_text, rows=device.rows, cols=device.cols)

    # Merge override config on top of the plugin's currently-bound config.
    config = dict(plugin.config or {})
    config.update(request.config or {})

    caps = plugin.transition_settings
    max_frames = int(caps["max_frames"])
    min_interval_ms = int(caps["min_interval_ms"])
    max_runtime_s = int(caps["max_runtime_seconds"])

    def _collect_frames() -> tuple[list, int, bool, str | None]:
        """Run on a worker thread; returns (frames, total_delay, capped, error)."""
        import time

        frames: list = []
        total_delay = 0
        capped_flag = False
        started = time.monotonic()
        try:
            for raw_frame in plugin.generate_frames(from_grid, to_grid, device, config):
                if len(frames) >= max_frames:
                    capped_flag = True
                    break
                if (time.monotonic() - started) >= max_runtime_s:
                    capped_flag = True
                    break
                if isinstance(raw_frame, tuple) and len(raw_frame) == 2:
                    grid, delay = raw_frame
                else:
                    grid, delay = raw_frame, 0
                try:
                    delay = int(delay or 0)
                except (TypeError, ValueError):
                    delay = 0
                delay = max(delay, min_interval_ms)
                if not isinstance(grid, list) or not grid or not isinstance(grid[0], list):
                    continue
                frames.append({"grid": grid, "delay_ms": delay})
                total_delay += delay
        except Exception as exc:
            return frames, total_delay, capped_flag, str(exc)
        return frames, total_delay, capped_flag, None

    try:
        # Bound the thread itself: if iteration takes longer than the cap +
        # a small grace period, give up rather than letting a runaway
        # plugin tie up a worker thread indefinitely.
        frames, total_delay, capped, error = await asyncio.wait_for(
            asyncio.to_thread(_collect_frames),
            timeout=max_runtime_s + 5,
        )
    except TimeoutError as exc:
        logger.warning(
            "Transition preview for %s exceeded %ds; aborting",
            plugin_id,
            max_runtime_s,
        )
        raise HTTPException(
            status_code=504,
            detail=(f"Plugin {plugin_id!r} exceeded the {max_runtime_s}s runtime cap and was aborted."),
        ) from exc

    if error is not None:
        logger.warning("Transition preview failed for %s: %s", plugin_id, error)
        raise HTTPException(status_code=500, detail=f"Plugin error: {error}")

    return TransitionPreviewResponse(
        plugin_id=plugin_id,
        device_type=device_type,
        frames=[TransitionFrame(**frame) for frame in frames],
        frame_count=len(frames),
        total_delay_ms=total_delay,
        capped=capped,
        from_grid=from_grid,
        to_grid=to_grid,
    )


# Hold the from-page on the board briefly before starting a live-test
# transition so the starting state is actually visible (physical tile
# flips take a moment to settle).
LIVE_TEST_FROM_HOLD_SECONDS = 1.5


def _resolve_live_board_client(board_id: str | None) -> tuple[dict | None, Any]:
    """Resolve ``(board_entry, client)`` for a Transition Lab live send.

    Mirrors the routing used by ``/pages/{id}/send``: an explicit
    *board_id* targets that board's client; omitted keeps the legacy
    primary-client path.  Raises :class:`HTTPException` when the service
    or client isn't available.
    """
    service = get_service()
    if board_id is not None:
        if not service:
            raise HTTPException(status_code=503, detail="Service not initialized")
        board = _require_board(board_id)
        client = service.get_board_client(board_id)
        if client is None:
            raise HTTPException(status_code=503, detail=f"Board client not initialized: {board_id}")
        return board, client
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return None, service.vb_client


def _render_live_page_grid(page_id: str, rows: int, cols: int) -> list[list[int]]:
    """Render *page_id* fresh and convert it to a rows×cols grid."""
    page_service = get_page_service()
    result = page_service.preview_page(page_id, force_refresh=True)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or f"Page rendering failed: {page_id}")
    return text_to_board_array(result.formatted, rows=rows, cols=cols)


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

    plugin_id = request.plugin_id
    if not plugin_id or not isinstance(plugin_id, str):
        raise HTTPException(status_code=400, detail="plugin_id is required")
    to_page_id = request.to_page_id
    if not to_page_id or not isinstance(to_page_id, str):
        raise HTTPException(status_code=400, detail="to_page_id is required")
    from_page_id = request.from_page_id
    board_id = request.board_id

    registry = get_plugin_registry()
    plugin = registry.get_transition_plugin(plugin_id)
    if plugin is None:
        raise HTTPException(
            status_code=404,
            detail=f"Transition plugin {plugin_id!r} not loaded or not enabled",
        )

    board, board_client = _resolve_live_board_client(board_id)

    if _silence_active(board_id):
        raise HTTPException(status_code=409, detail="Silence mode is active - live test blocked")
    if _board_is_paused(board_id):
        raise HTTPException(status_code=409, detail="Board is paused - live test blocked")

    page_service = get_page_service()
    to_page = page_service.get_page(to_page_id)
    if not to_page:
        raise HTTPException(status_code=404, detail=f"Page not found: {to_page_id}")
    if from_page_id and not page_service.get_page(from_page_id):
        raise HTTPException(status_code=404, detail=f"Page not found: {from_page_id}")

    # Size grids to the explicit target board when given (issue #1244);
    # otherwise keep the to-page's own device type, matching /pages/{id}/send.
    if board is not None:
        dims = _board_dims(board)
        device_hint = board.get("device_type") or to_page.device_type
    else:
        dims = resolve_dimensions(to_page.device_type, to_page.notes_wide, to_page.notes_tall)
        device_hint = to_page.device_type

    to_grid = _render_live_page_grid(to_page_id, dims.rows, dims.cols)
    from_grid = _render_live_page_grid(from_page_id, dims.rows, dims.cols) if from_page_id else None

    # Merge override config on top of the plugin's currently-bound config,
    # mirroring /transitions/preview so live behavior matches the preview.
    config = dict(plugin.config or {})
    config.update(request.config or {})

    max_runtime_s = int(plugin.transition_settings["max_runtime_seconds"])

    def _run_live() -> tuple[bool, bool]:
        if from_grid is not None:
            board_client.send_characters(from_grid, strategy=None, force=True)
            time.sleep(LIVE_TEST_FROM_HOLD_SECONDS)
        return board_client.render(
            to_grid,
            strategy=f"plugin:{plugin_id}",
            force=True,
            device_type=device_hint,
            transition_config=config,
        )

    try:
        # The runner enforces the plugin's runtime cap itself; the outer
        # timeout only guards against a generator that blocks inside next()
        # (the abandoned thread still snaps the board to the target).
        success, was_sent = await asyncio.wait_for(
            asyncio.to_thread(_run_live),
            timeout=max_runtime_s + LIVE_TEST_FROM_HOLD_SECONDS + 15,
        )
    except TimeoutError as exc:
        logger.warning("Live transition test for %s exceeded %ds; abandoning", plugin_id, max_runtime_s)
        raise HTTPException(
            status_code=504,
            detail=f"Plugin {plugin_id!r} exceeded the {max_runtime_s}s runtime cap.",
        ) from exc

    if not success:
        raise HTTPException(status_code=502, detail="Board unreachable - live test failed")

    return TransitionLiveTestResponse(
        sent=was_sent,
        plugin_id=plugin_id,
        from_page_id=from_page_id,
        to_page_id=to_page_id,
        board_id=board_id,
    )


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

    board_id = (request or TransitionRestoreRequest()).board_id

    board, board_client = _resolve_live_board_client(board_id)

    if _silence_active(board_id):
        raise HTTPException(status_code=409, detail="Silence mode is active - restore blocked")
    if _board_is_paused(board_id):
        raise HTTPException(status_code=409, detail="Board is paused - restore blocked")

    settings_service = get_settings_service()
    if board_id is not None:
        active_page_id = settings_service.get_active_page_id(board_id=board_id)
    else:
        active_page_id = settings_service.get_active_page_id()
    if not active_page_id:
        raise HTTPException(status_code=404, detail="No active page set")

    if is_collection_id(active_page_id):
        resolved = get_collection_service().resolve_page_id(active_page_id)
        if not resolved:
            raise HTTPException(status_code=404, detail="Collection could not be resolved")
        active_page_id = resolved

    page_service = get_page_service()
    page = page_service.get_page(active_page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Active page not found")

    if board is not None:
        dims = _board_dims(board)
    else:
        dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
    grid = _render_live_page_grid(active_page_id, dims.rows, dims.cols)

    success, was_sent = await run_board_send(board_client.render, grid, strategy=None, force=True)
    if not success:
        raise HTTPException(status_code=502, detail="Board unreachable - restore failed")

    return TransitionRestoreResponse(page_id=active_page_id, sent=was_sent, board_id=board_id)
