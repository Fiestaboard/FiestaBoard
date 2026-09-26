"""Domain behaviour behind the ``/transitions`` endpoints.

The three Transition Lab operations — preview a plugin in-process, drive it
once on a real board, and snap the board back afterwards — used to live in
``src/transitions/routes.py``, where they were 250 lines of frame-cap loops,
grid sizing and board routing that had nothing to do with HTTP, and where
``tests/test_layering_ratchet.py``'s ``router_no_domain_logic`` rule flagged
all three.

The functions here raise :class:`TransitionError` rather than
``fastapi.HTTPException``: a domain module has to stay callable from MQTT,
MCP, the display loop and a test without a web framework's error model
(ARCHITECTURE.md, "The shape of a request"). The router translates it back
into the exact status/detail pairs the endpoints have always answered, pinned
by value in ``tests/test_transitions_contract.py``. The one exception is
``src.board_guards._require_board``, which still raises ``HTTPException`` for
the whole app; its 404 travels through untouched.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``. Tests that need to stub one patch
it where this module binds it — ``src.transitions.service.<name>``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

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
    TransitionPreviewRequest,
    TransitionPreviewResponse,
    TransitionRestoreRequest,
    TransitionRestoreResponse,
)
from .runner import unpack_frame

logger = logging.getLogger(__name__)


class TransitionError(Exception):
    """A transition operation refused, or failed, with the answer to give.

    ``status_code`` and ``detail`` are the values the router hands to
    ``HTTPException`` verbatim. They are part of this domain's recorded
    contract (``tests/test_transitions_contract.py``), not an implementation
    detail of the transport.
    """

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# Hold the from-page on the board briefly before starting a live-test
# transition so the starting state is actually visible (physical tile
# flips take a moment to settle).
LIVE_TEST_FROM_HOLD_SECONDS = 1.5


def list_installed_transition_plugins() -> list[dict[str, Any]]:
    """Every installed transition plugin, as the listing endpoint reports it.

    Installed, not enabled: unlike data plugins, transitions don't need to be
    enabled in the Marketplace to be selectable — installing one is opting in.
    Sorted by display name so the picker's order is stable.
    """
    from src.plugins.base import TransitionPluginBase

    registry = get_plugin_registry()
    out: list[dict[str, Any]] = []
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
    return out


def _resolve_preview_device(request: TransitionPreviewRequest):
    """Validate the requested geometry and build its :class:`BoardContext`."""
    from src.devices import MAX_NOTES_PER_AXIS, board_context_for

    device_type = request.device_type
    if device_type not in ("flagship", "note", "note_array"):
        raise TransitionError(400, f"Unknown device_type: {device_type}")
    try:
        notes_wide = int(request.notes_wide)
        notes_tall = int(request.notes_tall)
    except (TypeError, ValueError) as exc:
        raise TransitionError(400, "notes_wide/notes_tall must be integers") from exc
    if not (1 <= notes_wide <= MAX_NOTES_PER_AXIS and 1 <= notes_tall <= MAX_NOTES_PER_AXIS):
        raise TransitionError(400, f"notes_wide/notes_tall must be between 1 and {MAX_NOTES_PER_AXIS}")
    return board_context_for(device_type, notes_wide=notes_wide, notes_tall=notes_tall)


def _require_plugin_id(plugin_id: Any) -> None:
    """400 when the body named no plugin. Kept separate from the registry
    lookup because the live-test endpoint validates *both* ids before it
    looks anything up, and the order of those two 400s is recorded."""
    if not plugin_id or not isinstance(plugin_id, str):
        raise TransitionError(400, "plugin_id is required")


def _load_transition_plugin(plugin_id: str):
    """The loaded transition plugin for *plugin_id*, or a 404 naming it."""
    plugin = get_plugin_registry().get_transition_plugin(plugin_id)
    if plugin is None:
        raise TransitionError(404, f"Transition plugin {plugin_id!r} not loaded or not enabled")
    return plugin


def _collect_preview_frames(
    plugin,
    from_grid: list[list[int]],
    to_grid: list[list[int]],
    device,
    config: dict,
    caps: dict,
) -> tuple[list[dict[str, Any]], int, bool, str | None]:
    """Iterate the plugin's generator on a worker thread, collecting frames.

    Returns ``(frames, total_delay, capped, error)``.

    This is the preview twin of :meth:`TransitionRunner._drive_generator`, and
    deliberately **not** the same loop: the runner sends each frame to a board
    and aborts the run on a malformed one, while a preview collects frames
    into JSON and skips a malformed frame so the harness still shows the rest.
    What the two genuinely shared — coercing a yielded value into
    ``(grid, delay_ms)`` — is now :func:`src.transitions.runner.unpack_frame`,
    called by both.
    """
    max_frames = int(caps["max_frames"])
    min_interval_ms = int(caps["min_interval_ms"])
    max_runtime_s = int(caps["max_runtime_seconds"])

    frames: list[dict[str, Any]] = []
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
            grid, delay = unpack_frame(raw_frame)
            if grid is None:
                continue
            delay = max(delay, min_interval_ms)
            frames.append({"grid": grid, "delay_ms": delay})
            total_delay += delay
    except Exception as exc:
        return frames, total_delay, capped_flag, str(exc)
    return frames, total_delay, capped_flag, None


async def preview_transition(request: TransitionPreviewRequest) -> TransitionPreviewResponse:
    """Run a transition plugin once and return the resulting frame sequence.

    Frames are generated in-process and returned as JSON; nothing is sent to a
    real board. The runner's caps (``max_frames``, ``max_runtime_seconds``,
    ``min_interval_ms``) are honored; exceeding either bound truncates the
    response and sets ``capped`` so the UI can show a hint.

    Iteration happens on a worker thread (``asyncio.to_thread``) so a slow or
    runaway plugin generator cannot block FastAPI's event loop, and the thread
    itself is bounded: past the runtime cap plus a small grace period the run
    is abandoned rather than tying up a worker indefinitely.
    """
    _require_plugin_id(request.plugin_id)
    plugin = _load_transition_plugin(request.plugin_id)
    device = _resolve_preview_device(request)

    from_grid = text_to_board_array(request.from_text, rows=device.rows, cols=device.cols)
    to_grid = text_to_board_array(request.to_text, rows=device.rows, cols=device.cols)

    # Merge override config on top of the plugin's currently-bound config.
    config = dict(plugin.config or {})
    config.update(request.config or {})

    caps = plugin.transition_settings
    max_runtime_s = int(caps["max_runtime_seconds"])

    try:
        frames, total_delay, capped, error = await asyncio.wait_for(
            asyncio.to_thread(_collect_preview_frames, plugin, from_grid, to_grid, device, config, caps),
            timeout=max_runtime_s + 5,
        )
    except TimeoutError as exc:
        logger.warning("Transition preview for %s exceeded %ds; aborting", request.plugin_id, max_runtime_s)
        raise TransitionError(
            504,
            f"Plugin {request.plugin_id!r} exceeded the {max_runtime_s}s runtime cap and was aborted.",
        ) from exc

    if error is not None:
        logger.warning("Transition preview failed for %s: %s", request.plugin_id, error)
        raise TransitionError(500, f"Plugin error: {error}")

    return TransitionPreviewResponse(
        plugin_id=request.plugin_id,
        device_type=request.device_type,
        frames=[TransitionFrame(**frame) for frame in frames],
        frame_count=len(frames),
        total_delay_ms=total_delay,
        capped=capped,
        from_grid=from_grid,
        to_grid=to_grid,
    )


def _resolve_live_board_client(board_id: str | None) -> tuple[dict | None, Any]:
    """Resolve ``(board_entry, client)`` for a Transition Lab live send.

    Mirrors the routing used by ``/pages/{id}/send``: an explicit *board_id*
    targets that board's client; omitted keeps the legacy primary-client path.
    """
    service = get_service()
    if board_id is not None:
        if not service:
            raise TransitionError(503, "Service not initialized")
        board = _require_board(board_id)
        client = service.get_board_client(board_id)
        if client is None:
            raise TransitionError(503, f"Board client not initialized: {board_id}")
        return board, client
    if not service or not service.vb_client:
        raise TransitionError(503, "Service not initialized")
    return None, service.vb_client


def _render_live_page_grid(page_id: str, rows: int, cols: int) -> list[list[int]]:
    """Render *page_id* fresh and convert it to a rows×cols grid."""
    page_service = get_page_service()
    result = page_service.preview_page(page_id, force_refresh=True)
    if result is None:
        raise TransitionError(404, f"Page not found: {page_id}")
    if not result.available:
        raise TransitionError(503, result.error or f"Page rendering failed: {page_id}")
    return text_to_board_array(result.formatted, rows=rows, cols=cols)


def _require_board_is_writable(board_id: str | None, what: str) -> None:
    """409 while the target board is silenced or paused."""
    if _silence_active(board_id):
        raise TransitionError(409, f"Silence mode is active - {what} blocked")
    if _board_is_paused(board_id):
        raise TransitionError(409, f"Board is paused - {what} blocked")


async def run_live_transition_test(request: TransitionLiveTestRequest) -> TransitionLiveTestResponse:
    """Run a transition plugin once on the real board (Transition Lab).

    Respects silence mode and board pause (409 so the UI can explain why
    nothing happened). The board is left showing the to-page; ``restore`` — or
    the normal display loop — returns it to its active page.
    """
    plugin_id = request.plugin_id
    _require_plugin_id(plugin_id)
    to_page_id = request.to_page_id
    if not to_page_id or not isinstance(to_page_id, str):
        raise TransitionError(400, "to_page_id is required")
    from_page_id = request.from_page_id
    board_id = request.board_id

    plugin = _load_transition_plugin(plugin_id)
    board, board_client = _resolve_live_board_client(board_id)
    _require_board_is_writable(board_id, "live test")

    page_service = get_page_service()
    to_page = page_service.get_page(to_page_id)
    if not to_page:
        raise TransitionError(404, f"Page not found: {to_page_id}")
    if from_page_id and not page_service.get_page(from_page_id):
        raise TransitionError(404, f"Page not found: {from_page_id}")

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
    # mirroring the preview so live behavior matches what the UI showed.
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
        raise TransitionError(504, f"Plugin {plugin_id!r} exceeded the {max_runtime_s}s runtime cap.") from exc

    if not success:
        raise TransitionError(502, "Board unreachable - live test failed")

    return TransitionLiveTestResponse(
        sent=was_sent,
        plugin_id=plugin_id,
        from_page_id=from_page_id,
        to_page_id=to_page_id,
        board_id=board_id,
    )


async def restore_after_transition_test(request: TransitionRestoreRequest | None = None) -> TransitionRestoreResponse:
    """Snap the board back to its active page after a live transition test.

    Re-renders the board's active page and sends it plainly (no transition),
    cancelling any still-running plugin transition. The normal display loop
    would eventually do the same; this just lets the Lab do it on demand.
    """
    board_id = (request or TransitionRestoreRequest()).board_id

    board, board_client = _resolve_live_board_client(board_id)
    _require_board_is_writable(board_id, "restore")

    settings_service = get_settings_service()
    if board_id is not None:
        active_page_id = settings_service.get_active_page_id(board_id=board_id)
    else:
        active_page_id = settings_service.get_active_page_id()
    if not active_page_id:
        raise TransitionError(404, "No active page set")

    if is_collection_id(active_page_id):
        resolved = get_collection_service().resolve_page_id(active_page_id)
        if not resolved:
            raise TransitionError(404, "Collection could not be resolved")
        active_page_id = resolved

    page = get_page_service().get_page(active_page_id)
    if not page:
        raise TransitionError(404, "Active page not found")

    if board is not None:
        dims = _board_dims(board)
    else:
        dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
    grid = _render_live_page_grid(active_page_id, dims.rows, dims.cols)

    success, was_sent = await run_board_send(board_client.render, grid, strategy=None, force=True)
    if not success:
        raise TransitionError(502, "Board unreachable - restore failed")

    return TransitionRestoreResponse(page_id=active_page_id, sent=was_sent, board_id=board_id)
