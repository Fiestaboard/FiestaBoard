"""FastAPI router for the debug, diagnostics and log endpoints.

Twelve route-methods: the eight ``/debug/*`` board tools plus the four
siblings that are the same subsystem — ``GET /cache-status``,
``POST /clear-cache``, ``POST /force-refresh`` and ``GET /logs``.

Phase 2 Task 8. The handlers were extracted from ``src/api_server.py`` as a
pure move in the previous commit; this module now serves them under
``docs/internal/reference/API_CONVENTIONS.md``:

* every route declares a ``response_model`` and the 4xx it can raise;
* bodies are bare (no ``{"status": "success", ...}`` envelope);
* ``POST /debug/fill`` takes a Pydantic model, not ``request: dict``;
* refusals are status codes — a paused board is a **409**, a write dropped
  by the send floor is a **429**, an unreachable board is a **503** — not a
  200 carrying a word like ``"blocked"``.

Names that still live in ``api_server`` — the service getters and the board
helpers — are reached through the thin call-time proxies below rather than a
module-level import. That is the ``src/mqtt/commands.py`` pattern the other
extracted routers use: a module-level import would both create an import
cycle (``api_server`` imports this router) and detach the handlers from the
suite's ``patch("src.api_server.<name>")`` targets. They are retired in the
next commit of this same slice.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query

from src import __version__
from src.api_errors import errors
from src.board_client import board_client_from_board_dict
from src.board_send_executor import run_board_send

from .models import (
    BoardFillRequest,
    CacheStatus,
    ConnectionTestResponse,
    DebugActionResponse,
    DebugInfoResponse,
    ForceRefreshResponse,
    LogFilters,
    LogsResponse,
    NetworkDiagnosticsResponse,
    SystemInfoResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["debug"])


# ---------------------------------------------------------------------------
# Call-time seams onto api_server (retired later in this slice)
# ---------------------------------------------------------------------------


def _service_is_running() -> bool:
    """Call-time seam onto the ``src.api_server._service_running`` flag."""
    from src import api_server

    return api_server._service_running


def _get_board_client(*args, **kwargs):
    """Call-time seam onto ``src.api_server._get_board_client`` — see module docstring."""
    from src.api_server import _get_board_client as _impl

    return _impl(*args, **kwargs)


def get_settings_service(*args, **kwargs):
    """Call-time seam onto ``src.api_server.get_settings_service`` — see module docstring."""
    from src.api_server import get_settings_service as _impl

    return _impl(*args, **kwargs)


def get_service(*args, **kwargs):
    """Call-time seam onto ``src.api_server.get_service`` — see module docstring."""
    from src.api_server import get_service as _impl

    return _impl(*args, **kwargs)


def _board_is_paused(*args, **kwargs):
    """Call-time seam onto ``src.api_server._board_is_paused`` — see module docstring."""
    from src.api_server import _board_is_paused as _impl

    return _impl(*args, **kwargs)


def _get_first_board_dims(*args, **kwargs):
    """Call-time seam onto ``src.api_server._get_first_board_dims`` — see module docstring."""
    from src.api_server import _get_first_board_dims as _impl

    return _impl(*args, **kwargs)


def _note_out_of_band_write(*args, **kwargs):
    """Call-time seam onto ``src.api_server._note_out_of_band_write`` — see module docstring."""
    from src.api_server import _note_out_of_band_write as _impl

    return _impl(*args, **kwargs)


def _primary_connection_info(*args, **kwargs):
    """Call-time seam onto ``src.api_server._primary_connection_info`` — see module docstring."""
    from src.api_server import _primary_connection_info as _impl

    return _impl(*args, **kwargs)


def _primary_board_entry(*args, **kwargs):
    """Call-time seam onto ``src.api_server._primary_board_entry`` — see module docstring."""
    from src.api_server import _primary_board_entry as _impl

    return _impl(*args, **kwargs)


def _get_server_ip(*args, **kwargs):
    """Call-time seam onto ``src.api_server._get_server_ip`` — see module docstring."""
    from src.api_server import _get_server_ip as _impl

    return _impl(*args, **kwargs)


def _get_service_uptime(*args, **kwargs):
    """Call-time seam onto ``src.api_server._get_service_uptime`` — see module docstring."""
    from src.api_server import _get_service_uptime as _impl

    return _impl(*args, **kwargs)


def _format_uptime(*args, **kwargs):
    """Call-time seam onto ``src.api_server._format_uptime`` — see module docstring."""
    from src.api_server import _format_uptime as _impl

    return _impl(*args, **kwargs)


def _read_logs_from_files(*args, **kwargs):
    """Call-time seam onto ``src.api_server._read_logs_from_files`` — see module docstring."""
    from src.api_server import _read_logs_from_files as _impl

    return _impl(*args, **kwargs)


def _send_with_status(*args, **kwargs):
    """Call-time seam onto ``src.api_server._send_with_status`` — see module docstring."""
    from src.api_server import _send_with_status as _impl

    return _impl(*args, **kwargs)


# ---------------------------------------------------------------------------
# Shared guards
#
# Every out-of-band board write in this domain runs the same four checks in
# the same order: is a board configured, is the UI the only output target, is
# the board paused, and did the client-side send floor drop the write. Before
# the conventions pass each handler open-coded them, which is how the three
# senders ended up with three different answers to "did that work".
# ---------------------------------------------------------------------------

PAUSED_DETAIL = "Board is paused — sends are blocked until it is resumed."


def _require_board_client():
    """The primary board client, or a 400 saying there isn't one."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")
    return client


def _raise_if_paused() -> None:
    """A paused board refuses writes (issue #970).

    Answered 200 with ``{"status": "blocked"}`` before the conventions pass —
    a refusal dressed as a success, which any client checking only the status
    code read as "sent".
    """
    if _board_is_paused():
        logger.info("Board is paused - blocking debug send")
        raise HTTPException(status_code=409, detail=PAUSED_DETAIL)


def _raise_if_throttled(client) -> None:
    """A write dropped by the client-side send floor is a 429 (#1868, #1754).

    Cloud boards and note arrays enforce a minimum interval between sends; a
    send inside that window returns ``(True, False)`` with
    ``last_send_throttled`` set — the content was DROPPED, not delivered, and
    unlike the engine tick these manual endpoints never retry.

    The ``is True`` guard keeps Mock clients, whose attributes are all truthy,
    on the delivered path unless a test opts in.
    """
    if getattr(client, "last_send_throttled", False) is not True:
        return
    try:
        floor_ms = int(getattr(client, "min_send_interval_ms", 0))
    except (TypeError, ValueError):
        floor_ms = 0
    retry_after = max(1, -(-floor_ms // 1000)) if floor_ms else 15
    raise HTTPException(
        status_code=429,
        detail=(f"Send skipped: the board accepts at most one message every {retry_after}s. Retry shortly."),
        headers={"Retry-After": str(retry_after)},
    )


def _send_out_of_band(client, grid: list[list[int]], *, failure: str) -> None:
    """Push ``grid`` to the board, turning every outcome into a status code.

    The ``raise`` for a refused send deliberately sits *outside* the ``try``.
    Before this pass it sat inside, so the handler's own ``except Exception``
    caught it and re-raised ``HTTPException(500, str(e))`` — and
    ``str(HTTPException)`` is ``"500: <detail>"``, which is why the served
    detail used to read "500: Failed to blank board".
    """
    try:
        success, was_sent = client.send_characters(grid, force=True)
    except Exception as exc:
        logger.error(f"Out-of-band board write failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not success:
        raise HTTPException(status_code=500, detail=failure)
    if not was_sent:
        _raise_if_throttled(client)
    _note_out_of_band_write()


def _sends_to_board() -> bool:
    return bool(get_settings_service().should_send_to_board())


# ---------------------------------------------------------------------------
# Board actions
# ---------------------------------------------------------------------------


@router.post(
    "/debug/blank",
    response_model=DebugActionResponse,
    responses=errors(400, 409, 429),
)
async def debug_blank_board():
    """Clear the board by filling with space characters (code 0)."""
    client = _require_board_client()

    if not _sends_to_board():
        return DebugActionResponse(message="Board blank (output target is UI only)")

    _raise_if_paused()

    dims = _get_first_board_dims()
    _send_out_of_band(
        client,
        [[0] * dims.cols for _ in range(dims.rows)],
        failure="Failed to blank board",
    )
    return DebugActionResponse(message="Board blanked successfully")


@router.post(
    "/debug/fill",
    response_model=DebugActionResponse,
    responses=errors(400, 409, 422, 429),
)
async def debug_fill_board(request: BoardFillRequest):
    """Fill the board with a single character (code 0-71)."""
    character_code = request.character_code
    client = _require_board_client()

    if not _sends_to_board():
        return DebugActionResponse(message=f"Board filled with character {character_code} (output target is UI only)")

    _raise_if_paused()

    dims = _get_first_board_dims()
    _send_out_of_band(
        client,
        [[character_code] * dims.cols for _ in range(dims.rows)],
        failure="Failed to fill board",
    )
    return DebugActionResponse(message=f"Board filled with character {character_code}")


def _build_debug_text() -> str:
    """The six-line support card.

    The per-line slice caps below are flagship-oriented (~22 col); the final
    grid is sized to the active board's dimensions when converted to a board
    array. On narrow boards the converter wraps/truncates to the real width.
    Per-line polish for exotic widths is deferred (see #1173).

    Mode and IP come from the boards[] store / live client, not wizard-era
    config.json (issue #1791).
    """
    from src.time_service import get_time_service

    connection_mode, board_ip = _primary_connection_info()
    board_ip = board_ip or "not set"
    connection_mode = connection_mode.upper()
    server_ip = _get_server_ip()
    uptime_str = _format_uptime(_get_service_uptime())
    timestamp = get_time_service().get_current_time().strftime("%H:%M")

    return f"""DEBUG INFO
BOARD: {board_ip[:15]}
SERVER: {server_ip[:14]}
UP: {uptime_str[:18]}
{connection_mode[:20]} API
V{__version__[:7]} {timestamp}"""


@router.post(
    "/debug/info",
    response_model=DebugInfoResponse,
    responses=errors(400, 409, 429),
)
async def debug_show_info():
    """Display debug information on the board."""
    client = _require_board_client()
    debug_text = _build_debug_text()

    if not _sends_to_board():
        return DebugInfoResponse(
            message="Debug info displayed (output target is UI only)",
            debug_info=debug_text,
        )

    _raise_if_paused()

    from src.text_to_board import text_to_board_array

    dims = _get_first_board_dims()
    board_array = text_to_board_array(debug_text, use_color_tiles=False, rows=dims.rows, cols=dims.cols)
    _send_out_of_band(client, board_array, failure="Failed to send debug info")
    return DebugInfoResponse(message="Debug info sent to board", debug_info=debug_text)


@router.post(
    "/debug/test-connection",
    response_model=ConnectionTestResponse,
    responses=errors(400, 503),
)
async def debug_test_connection():
    """Test connection to the board."""
    client = _require_board_client()

    try:
        start_time = time.time()
        connected = client.test_connection()
        latency = round((time.time() - start_time) * 1000)  # ms
    except Exception as e:
        logger.error(f"Error testing connection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Connection test failed.") from e

    if not connected:
        # Unlike /config/board/test this endpoint has no declared verdict
        # body — no error class, no troubleshooting — so a 200 carrying
        # ``status: "error"`` was indistinguishable from a success to any
        # client that only checks the status code (#1887).
        raise HTTPException(status_code=503, detail="Could not reach the board.")

    return ConnectionTestResponse(
        message=f"Connection successful (latency: {latency}ms)",
        connected=True,
        latency_ms=latency,
    )


# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------


@router.post(
    "/debug/clear-cache",
    response_model=DebugActionResponse,
    responses=errors(400),
)
async def debug_clear_cache():
    """Clear the board client's message cache."""
    client = _require_board_client()
    try:
        client.clear_cache()
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return DebugActionResponse(message="Cache cleared - next message will be sent regardless of content")


@router.get(
    "/debug/cache-status",
    response_model=CacheStatus,
    responses=errors(400),
)
async def debug_get_cache_status():
    """Get the board client's current cache status."""
    client = _require_board_client()
    try:
        return client.get_cache_status()
    except Exception as e:
        logger.error(f"Error getting cache status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/cache-status", response_model=CacheStatus, responses=errors(503))
async def get_cache_status():
    """Get the current client-side cache status for the board client.

    Duplicate of ``GET /debug/cache-status`` in everything but which
    collaborator it reads through and which code it answers when the board is
    unavailable. Collapsing the pair behind one canonical route plus a
    deprecation shim is API_CONVENTIONS.md's "Deprecation, never deletion"
    work, not this slice's — see the PR.
    """
    service = get_service()
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")

    return service.vb_client.get_cache_status()


@router.post("/clear-cache", response_model=DebugActionResponse, responses=errors(503))
async def clear_cache():
    """Clear the client-side message cache.

    Forces the next update to be sent to the board even if the message
    content hasn't changed.
    """
    service = get_service()
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")

    service.vb_client.clear_cache()
    return DebugActionResponse(message="Cache cleared - next update will be sent to board")


@router.post("/force-refresh", response_model=ForceRefreshResponse, responses=errors(503))
async def force_refresh():
    """Force a display refresh, ignoring the cache.

    Unlike /refresh, this will send to the board even if the message
    content hasn't changed. Useful when you want to resync the board.
    """
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # The cache clearing plus a full forced send pass is all blocking work,
    # so it runs in one worker thread and the event loop keeps serving
    # requests (#1826); _send_with_status moves as one call because its
    # failure reason lives in a thread-local set and read inside the same
    # sync call.
    def _work() -> tuple[bool, str | None]:
        # Clear caches to force send even if content unchanged — every board,
        # not just the primary (secondary boards have their own clients).
        if service.vb_client:
            service.vb_client.clear_cache()
        for client in service.board_clients.values():
            client.clear_cache()
        # The board clients are only half of it: the display loop skips at its
        # own per-runtime content-dedupe guard, so clearing the client caches
        # alone left "Resend to board" doing nothing (issue #1794).
        try:
            service.invalidate_all_board_content()
        except Exception as e:
            logger.debug(f"Board content invalidation failed: {e}")

        return _send_with_status(service, "check_and_send_active_page_with_status", "check_and_send_active_page")

    try:
        sent, error = await run_board_send(_work)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error force-refreshing display: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to force refresh: {e}") from e

    if error:
        raise HTTPException(status_code=500, detail=f"Failed to force refresh: {error}")
    return ForceRefreshResponse(message="Display force-refreshed successfully", sent=sent)


# ---------------------------------------------------------------------------
# System info and diagnostics
# ---------------------------------------------------------------------------


@router.get("/debug/system-info", response_model=SystemInfoResponse)
async def debug_get_system_info():
    """Get system information without sending it to the board."""
    from src.time_service import get_time_service

    # Connection mode and board IP come from the boards[] store / live client
    # — the values the send path actually uses — not from wizard-era
    # config.json (issue #1791).
    connection_mode, board_ip = _primary_connection_info()
    uptime_seconds = _get_service_uptime()

    client = _get_board_client()
    cache_status = client.get_cache_status() if client else None

    # Check if board is configured: the client factory is the authority on
    # "has a usable connection". No boards[] entry means unconfigured — the
    # legacy config.json copy is never consulted (issue #1760).
    board = _primary_board_entry()
    board_configured = False
    if board is not None:
        try:
            board_configured = board_client_from_board_dict(board) is not None
        except Exception as exc:
            logger.debug("Could not evaluate board connection config: %s", exc)

    return SystemInfoResponse(
        board_ip=board_ip,
        server_ip=_get_server_ip(),
        uptime_seconds=uptime_seconds,
        uptime_formatted=_format_uptime(uptime_seconds),
        connection_mode=connection_mode,
        version=__version__,
        timestamp=get_time_service().create_utc_timestamp(),
        cache_status=cache_status,
        board_configured=board_configured,
        service_running=_service_is_running(),
    )


@router.get("/debug/network-diagnostics", response_model=NetworkDiagnosticsResponse)
async def debug_network_diagnostics():
    """Run network diagnostics to troubleshoot connectivity issues.

    Checks DNS resolution, internet connectivity, and Vestaboard reachability.
    """
    from src.network_diagnostics import run_full_diagnostics

    # Diagnose the connection the send path actually uses: the boards[]
    # store. The legacy config.json copy is never consulted (issue #1760) —
    # with no boards entry the diagnostics run without board credentials.
    board = _primary_board_entry() or {}
    board_host = board.get("host") or None
    board_port = board.get("port") or 7000
    board_api_key = board.get("local_api_key") or None
    use_cloud = (board.get("api_mode") or "local").lower() == "cloud"
    cloud_key = board.get("cloud_key") or None

    try:
        return run_full_diagnostics(
            board_host=board_host,
            board_port=board_port,
            board_api_key=board_api_key,
            use_cloud=use_cloud,
            cloud_key=cloud_key,
        )
    except Exception as e:
        logger.error(f"Error running network diagnostics: {e}")
        raise HTTPException(status_code=500, detail="Network diagnostics failed") from e


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


@router.get("/logs", response_model=LogsResponse, responses=errors(400))
async def get_logs(
    limit: int = Query(default=50, ge=1, le=500, description="Number of log entries to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    level: str | None = Query(default=None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"),
    search: str | None = Query(default=None, description="Search in log message or logger name"),
):
    """Get application logs with pagination, filtering, and search."""
    if level and level.upper() not in VALID_LOG_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid log level: {level}. Valid levels: {list(VALID_LOG_LEVELS)}",
        )

    logs, total, has_more = _read_logs_from_files(limit=limit, offset=offset, level=level, search=search)

    return LogsResponse(
        logs=logs,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
        filters=LogFilters(level=level.upper() if level else None, search=search),
    )
