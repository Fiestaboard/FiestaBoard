"""FastAPI router for the out-of-band board read and the two manual senders.

Three route-methods: ``GET /board/current-message`` (the canonical "what is on
the board" read), ``POST /send-message`` and ``POST /send-welcome-message``.

Phase 2, Task 8 — the last untagged routes. Moved out of ``src/api_server.py``
and converted to ``docs/internal/reference/API_CONVENTIONS.md``.

What the conventions pass changed here
--------------------------------------
The two senders used to answer **200** for three different non-deliveries:
``{"status": "blocked", "silence_mode": true}`` for the silence window,
``{"status": "blocked", "paused": true}`` for a paused board, and
``{"status": "throttled", ...}`` for a write the client-side send floor
dropped. A client that checks only the status code read all three as "sent".
They are now **409**, **409** and **429** — the same verdicts, and the same
Retry-After arithmetic, that ``src/debug/routes.py`` adopted in the debug
slice. The three senders in this codebase now give one answer to "did that
work".

The ``except Exception`` around each send also used to swallow the handler's
own ``HTTPException`` and re-raise it as ``HTTPException(500, str(e))`` —
and ``str(HTTPException)`` is ``"500: <detail>"``, which is why a refused send
served the stuttering detail ``"500: Failed to send message"``. The guards now
raise outside that ``try``.

``GET /board/current-message`` is unchanged by value. Issue #1912 tracks
collapsing its cache-selection logic with the two other copies
(``src/mcp_server.py`` and the panel frame endpoint); that consolidation is
deliberately *not* attempted here.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from src import display_runtime as runtime
from src.api_errors import errors
from src.board_chars import characters_to_message
from src.board_client import board_client_from_board_dict
from src.board_guards import _board_dims, _require_board, _silence_active
from src.board_guards import raise_if_paused as _raise_if_paused
from src.board_guards import raise_if_throttled as _raise_if_throttled
from src.config_manager import get_config_manager
from src.devices import resolve_dimensions
from src.text_to_board import text_to_board_array

from .models import BoardCurrentMessageResponse, MessageRequest, SendResponse
from .welcome import build_welcome_template

logger = logging.getLogger(__name__)

router = APIRouter(tags=["board"])

SILENCE_DETAIL = "Manual sends are blocked during silence mode to prevent waking the board."


def _raise_if_silenced() -> None:
    """The silence window refuses every manual send (issue #1788).

    This path drives the primary board's client, so it resolves the primary
    board's window.
    """
    if _silence_active():
        logger.info("Silence mode is active - blocking manual send to prevent wake-up")
        raise HTTPException(status_code=409, detail=SILENCE_DETAIL)


def _primary_geometry(settings_service):
    """Grid size of the active (first) board, defaulting to a flagship."""
    device_type = "flagship"
    notes_wide = 1
    notes_tall = 1
    board_settings = settings_service.get_board_settings()
    boards = getattr(board_settings, "boards", None) or []
    if boards:
        first = boards[0]
        if isinstance(first, dict):
            device_type = first.get("device_type", "flagship")
            notes_wide = first.get("notes_wide", 1)
            notes_tall = first.get("notes_tall", 1)
        else:
            device_type = getattr(first, "device_type", "flagship")
            notes_wide = getattr(first, "notes_wide", 1)
            notes_tall = getattr(first, "notes_tall", 1)
    if device_type not in ("flagship", "note", "note_array"):
        device_type = "flagship"
    return device_type, notes_wide, notes_tall


# ---------------------------------------------------------------------------
# Reading the board
# ---------------------------------------------------------------------------


@router.get("/board/current-message", response_model=BoardCurrentMessageResponse, responses=errors(404, 503))
async def get_board_current_message(force: bool = False, board_id: str | None = None):
    """Return the current state of the physical board.

    Normally serves from the cached result of the background poll thread
    (updated every 30 s local / 3 min cloud) so callers don't hammer the
    Vestaboard API.  Pass ?force=true to trigger a live read instead.

    Args:
        force: Trigger a live board read instead of serving the poll cache.
            Only honored for the primary board.
        board_id: Optional board to read (issue #1247). Omitted or the
            primary board → legacy live-polled behavior. A secondary board is
            served from its runtime cache (last-sent/polled content) because
            board-state polling is primary-only by design; ``characters`` /
            ``message`` are null when nothing has been sent to it yet.
    """
    service = runtime.get_service()
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Board client not initialized")

    if board_id is not None:
        board = _require_board(board_id)
        if board_id != runtime.get_settings_service().get_primary_board_id():
            # Secondary board: serve from its runtime cache. No live read —
            # the poll thread only tracks the primary board (issue #1243).
            rt = service.get_runtime(board_id)
            rt_client = rt.client if rt is not None else None
            last_sent = getattr(rt_client, "_last_characters", None) if rt_client is not None else None
            polled = rt.polled_characters if rt is not None else None
            characters = polled if polled is not None else last_sent
            cached_at = None
            if polled is not None and rt is not None and rt.polled_at is not None:
                cached_at = datetime.fromtimestamp(rt.polled_at, tz=UTC).isoformat()
            board_api_mode = "cloud" if getattr(rt_client, "use_cloud", False) else "local"
            if characters is None:
                # Nothing sent to this board yet — return its geometry so the
                # UI can degrade gracefully (render the active page instead).
                dims = _board_dims(board)
                return BoardCurrentMessageResponse(
                    characters=None,
                    message=None,
                    rows=dims.rows,
                    cols=dims.cols,
                    expected_characters=None,
                    cached_at=None,
                    api_mode=board_api_mode,
                    board_id=board_id,
                )
            return BoardCurrentMessageResponse(
                characters=characters,
                message=characters_to_message(characters),
                rows=len(characters),
                cols=len(characters[0]) if characters else 0,
                expected_characters=last_sent,
                cached_at=cached_at,
                api_mode=board_api_mode,
                board_id=board_id,
            )

    api_mode = "cloud" if getattr(service.vb_client, "use_cloud", False) else "local"
    expected_characters = service.vb_client._last_characters

    if force or service._polled_characters is None:
        # No cached data yet (startup) or caller wants a live read — hit the board directly
        characters = await asyncio.to_thread(service.vb_client.read_current_message)
        if characters is None:
            raise HTTPException(status_code=503, detail="Failed to read current board message")
        # Prime the cache so subsequent requests are fast
        service._polled_characters = characters
        service._polled_at = time.time()
        cached_at = None
    else:
        characters = service._polled_characters
        cached_at = datetime.fromtimestamp(service._polled_at, tz=UTC).isoformat()

    return BoardCurrentMessageResponse(
        characters=characters,
        message=characters_to_message(characters),
        rows=len(characters),
        cols=len(characters[0]) if characters else 0,
        expected_characters=expected_characters,
        cached_at=cached_at,
        api_mode=api_mode,
        board_id=board_id,
    )


# ---------------------------------------------------------------------------
# Writing to the board
# ---------------------------------------------------------------------------


@router.post("/send-message", response_model=SendResponse, responses=errors(409, 429, 500, 503))
async def send_message(request: MessageRequest):
    """Send a custom message to the board."""
    service = runtime.get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    _raise_if_silenced()
    _raise_if_paused()

    if not service.vb_client:
        raise HTTPException(status_code=503, detail="Board client not initialized")

    settings_service = runtime.get_settings_service()
    transition = settings_service.get_transition_settings()
    # Size the grid to the active (first) board so a manual send to a note
    # array uses its real geometry instead of a default flagship 22×6.
    device_type, notes_wide, notes_tall = _primary_geometry(settings_service)
    dims = resolve_dimensions(device_type, notes_wide, notes_tall)
    # Word-wrap/convert/render is the shared message core (#1765): the
    # MCP send_message executor calls the same function, so the two
    # surfaces cannot render a message differently. See
    # src/displays/messages.py for the #1793 newline/backslash notes.
    from src.displays.messages import render_message

    try:
        success, was_sent = render_message(
            service.vb_client,
            request.text,
            rows=dims.rows,
            cols=dims.cols,
            strategy=transition.strategy,
            step_interval_ms=transition.step_interval_ms,
            step_size=transition.step_size,
        )
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {e!s}") from e

    # Every raise below sits OUTSIDE the try above on purpose: inside it, the
    # handler's own except caught its own HTTPException and re-raised it as
    # HTTPException(500, str(e)) — which is how the served detail came to read
    # "500: Failed to send message".
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send message")
    if not was_sent:
        # A not-sent "success" can also mean the send floor dropped the write
        # entirely (#1868 review) — that is not "unchanged".
        _raise_if_throttled(service.vb_client)
        return SendResponse(message="Message unchanged, no update needed", sent=False)

    # Flag the out-of-band write and push fresh MQTT state so HA reflects the
    # update (issues #1794/#1831). The display loop's dedupe cache is
    # deliberately left alone: invalidating it here made the message
    # self-destruct on the next engine tick (<=15s). Restoring the active page
    # is a pull — /force-refresh, MQTT Refresh Display, re-selecting a page,
    # or an actual content change (issue #1794).
    runtime._note_out_of_band_write()
    service.request_board_refresh()
    return SendResponse(message="Message sent successfully", sent=True)


@router.post("/send-welcome-message", response_model=SendResponse, responses=errors(409, 429, 500, 503))
async def send_welcome_message():
    """Send a colorful welcome message to the board.

    Used by the setup wizard to confirm the board is working.

    Note: This creates a fresh board client from the settings boards store
    so any recent credential changes (setup wizard or Settings) are used.
    """
    # Check silence mode for the board this actually writes to (the primary
    # board — the wizard has no board picker).
    _raise_if_silenced()
    _raise_if_paused()

    # Create a fresh board client from the primary settings board so recent
    # credential edits are always used. Board credentials are unified on
    # settings.json (issue #1760): the legacy config.json copy is never read.
    board = runtime._primary_board_entry()
    try:
        board_client = board_client_from_board_dict(board) if board is not None else None
    except ValueError as e:
        logger.error(f"Failed to create board client: {e}")
        raise HTTPException(status_code=503, detail=f"Board not configured: {e!s}") from e
    if board_client is None:
        raise HTTPException(status_code=503, detail="Board not configured: no board with a usable connection")
    board_client.skip_unchanged = False  # Always send the welcome message

    # Use custom welcome message if set, otherwise use the default
    custom_msg = (get_config_manager().get_general().get("welcome_message") or "").strip()

    settings_service = runtime.get_settings_service()
    transition = settings_service.get_transition_settings()

    # Determine device type and array dimensions from configured boards
    # (defaults to flagship 6×22). Note arrays use notes_wide/notes_tall
    # to compute the actual grid size.
    try:
        device_type, notes_wide, notes_tall = _primary_geometry(settings_service)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not determine device type for welcome message: %s", exc)
        device_type, notes_wide, notes_tall = "flagship", 1, 1

    welcome_template = build_welcome_template(device_type, custom_msg, notes_wide=notes_wide, notes_tall=notes_tall)

    # Convert template to board array sized for the target device
    dims = resolve_dimensions(device_type, notes_wide=notes_wide, notes_tall=notes_tall)
    board_array = text_to_board_array("\n".join(welcome_template), rows=dims.rows, cols=dims.cols)

    try:
        success, was_sent = board_client.render(
            board_array,
            strategy=transition.strategy,
            step_interval_ms=transition.step_interval_ms,
            step_size=transition.step_size,
            force=True,  # Force send even if cached
            device_type=device_type,
        )
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send welcome message: {e!s}") from e

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send welcome message")
    if not was_sent:
        # Dropped by the send floor, not unchanged (#1868 review).
        _raise_if_throttled(board_client)
        return SendResponse(message="Welcome message unchanged", sent=False)

    logger.info("Welcome message sent to board")
    return SendResponse(message="Welcome message sent to your board!", sent=True)
