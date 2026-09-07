"""FastAPI router for the debug, diagnostics and log endpoints.

Handlers moved **verbatim** from ``src/api_server.py`` (Phase 2 Task 8, the
debug slice). This commit is a pure move: no signature, status code, body or
message changes, and ``tests/golden/api_routes.json`` is byte-identical
afterwards. The conventions pass lands in the commit after it.

Names that still live in ``api_server`` — the service getters and the board
helpers — are reached through the thin call-time proxies below rather than a
module-level import. That is the ``src/mqtt/commands.py`` pattern the other
extracted routers use (``src/schedules/routes.py``, ``src/system/routes.py``):
a module-level import would both create an import cycle (``api_server``
imports this router) and detach the handlers from the suite's
``patch("src.api_server.<name>")`` targets. Retiring them is a later commit in
this same slice.

One line of the moved code changed shape rather than meaning:
``debug_get_system_info`` read the module global ``_service_running``
directly, which no proxy can stand in for, so it now calls
``_service_is_running()``. Same value, same source of truth.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query

from src import __version__
from src.board_client import board_client_from_board_dict
from src.board_send_executor import run_board_send

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


def _paused_response(*args, **kwargs):
    """Call-time seam onto ``src.api_server._paused_response`` — see module docstring."""
    from src.api_server import _paused_response as _impl

    return _impl(*args, **kwargs)


def _get_first_board_dims(*args, **kwargs):
    """Call-time seam onto ``src.api_server._get_first_board_dims`` — see module docstring."""
    from src.api_server import _get_first_board_dims as _impl

    return _impl(*args, **kwargs)


def _throttled_send_response(*args, **kwargs):
    """Call-time seam onto ``src.api_server._throttled_send_response`` — see module docstring."""
    from src.api_server import _throttled_send_response as _impl

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


@router.post("/debug/blank")
async def debug_blank_board():
    """Clear the board by filling with space characters (code 0)."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")

    settings_service = get_settings_service()
    if not settings_service.should_send_to_board():
        return {"status": "success", "message": "Board blank (output target is UI only)"}

    # Block when the (first) board is paused (issue #970).
    if _board_is_paused():
        logger.info("Board is paused - blocking debug blank send")
        return _paused_response()

    dims = _get_first_board_dims()
    try:
        # Create an array of spaces (code 0) sized for the active board
        blank_array = [[0] * dims.cols for _ in range(dims.rows)]
        success, was_sent = client.send_characters(blank_array, force=True)

        if success:
            if not was_sent:
                # Dropped by the send floor, not delivered (#1868 review).
                throttled = _throttled_send_response(client)
                if throttled is not None:
                    return throttled
            _note_out_of_band_write()
            return {"status": "success", "message": "Board blanked successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to blank board")
    except Exception as e:
        logger.error(f"Error blanking board: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/debug/fill")
async def debug_fill_board(request: dict):
    """Fill the board with a single character.

    Body: {"character_code": number} - code must be 0-71
    """
    character_code = request.get("character_code")
    if character_code is None:
        raise HTTPException(status_code=400, detail="character_code is required")

    if not isinstance(character_code, int) or character_code < 0 or character_code > 71:
        raise HTTPException(status_code=400, detail="character_code must be 0-71")

    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")

    settings_service = get_settings_service()
    if not settings_service.should_send_to_board():
        return {
            "status": "success",
            "message": f"Board filled with character {character_code} (output target is UI only)",
        }

    # Block when the (first) board is paused (issue #970).
    if _board_is_paused():
        logger.info("Board is paused - blocking debug fill send")
        return _paused_response()

    dims = _get_first_board_dims()
    try:
        # Create an array filled with the specified character, sized for the active board
        fill_array = [[character_code] * dims.cols for _ in range(dims.rows)]
        success, was_sent = client.send_characters(fill_array, force=True)

        if success:
            if not was_sent:
                # Dropped by the send floor, not delivered (#1868 review).
                throttled = _throttled_send_response(client)
                if throttled is not None:
                    return throttled
            _note_out_of_band_write()
            return {"status": "success", "message": f"Board filled with character {character_code}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to fill board")
    except Exception as e:
        logger.error(f"Error filling board: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/debug/info")
async def debug_show_info():
    """Display debug information on the board."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")

    settings_service = get_settings_service()
    send_to_board = settings_service.should_send_to_board()

    # Gather system info. Mode/IP come from the boards[] store / live client,
    # not wizard-era config.json (issue #1791).
    connection_mode, board_ip = _primary_connection_info()
    board_ip = board_ip or "not set"
    connection_mode = connection_mode.upper()
    server_ip = _get_server_ip()
    uptime = _get_service_uptime()
    uptime_str = _format_uptime(uptime)
    version = __version__

    # Get current timestamp
    from src.time_service import get_time_service

    time_service = get_time_service()
    now = time_service.get_current_time()
    timestamp = now.strftime("%H:%M")

    # Build debug info text. The per-line slice caps below are flagship-oriented
    # (~22 col); the final grid is sized to the active board's dimensions when
    # converted to a board array (see text_to_board_array call). On narrow boards
    # the converter wraps/truncates to the real width. Per-line polish for exotic
    # widths is deferred (see #1173).
    debug_text = f"""DEBUG INFO
BOARD: {board_ip[:15]}
SERVER: {server_ip[:14]}
UP: {uptime_str[:18]}
{connection_mode[:20]} API
V{version[:7]} {timestamp}"""

    if not send_to_board:
        return {
            "status": "success",
            "message": "Debug info displayed (output target is UI only)",
            "debug_info": debug_text,
        }

    # Block when the (first) board is paused (issue #970).
    if _board_is_paused():
        logger.info("Board is paused - blocking debug info send")
        return {**_paused_response(), "debug_info": debug_text}

    try:
        # Convert text to board array, sized to the active board's dimensions
        from src.text_to_board import text_to_board_array

        dims = _get_first_board_dims()
        board_array = text_to_board_array(debug_text, use_color_tiles=False, rows=dims.rows, cols=dims.cols)

        success, was_sent = client.send_characters(board_array, force=True)

        if success:
            if not was_sent:
                # Dropped by the send floor, not delivered (#1868 review).
                throttled = _throttled_send_response(client)
                if throttled is not None:
                    return throttled
            _note_out_of_band_write()
            return {"status": "success", "message": "Debug info sent to board", "debug_info": debug_text}
        else:
            raise HTTPException(status_code=500, detail="Failed to send debug info")
    except Exception as e:
        logger.error(f"Error sending debug info: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/debug/test-connection")
async def debug_test_connection():
    """Test connection to the board."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")

    try:
        start_time = time.time()
        connected = client.test_connection()
        latency = round((time.time() - start_time) * 1000)  # ms

        if connected:
            return {
                "status": "success",
                "message": f"Connection successful (latency: {latency}ms)",
                "connected": True,
                "latency_ms": latency,
            }
        # Unlike /config/board/test this endpoint has no declared verdict
        # body — no error class, no troubleshooting — so a 200 carrying
        # ``status: "error"`` was indistinguishable from a success to any
        # client that only checks the status code (#1887).
        raise HTTPException(status_code=503, detail="Could not reach the board.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing connection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Connection test failed.") from e


@router.post("/debug/clear-cache")
async def debug_clear_cache():
    """Clear the board client's message cache."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")

    try:
        client.clear_cache()
        return {"status": "success", "message": "Cache cleared - next message will be sent regardless of content"}
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/debug/cache-status")
async def debug_get_cache_status():
    """Get current cache status for debugging."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")

    try:
        cache_status = client.get_cache_status()
        return {"status": "success", "cache": cache_status}
    except Exception as e:
        logger.error(f"Error getting cache status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/debug/system-info")
async def debug_get_system_info():
    """Get system information without sending to board."""
    # Gather all system info. Connection mode and board IP come from the
    # boards[] store / live client — the values the send path actually uses —
    # not from wizard-era config.json (issue #1791).
    connection_mode, board_ip = _primary_connection_info()
    server_ip = _get_server_ip()
    uptime_seconds = _get_service_uptime()
    uptime_formatted = _format_uptime(uptime_seconds)
    version = __version__

    # Get current timestamp
    from src.time_service import get_time_service

    time_service = get_time_service()
    timestamp = time_service.create_utc_timestamp()

    # Get cache status if available
    client = _get_board_client()
    cache_status = client.get_cache_status() if client else None

    # Check if board is configured: the client factory is the authority on
    # "has a usable connection". No boards[] entry means unconfigured — the
    # legacy config.json copy is never consulted (issue #1760).
    board = _primary_board_entry()
    if board is not None:
        try:
            board_configured = board_client_from_board_dict(board) is not None
        except Exception as exc:
            logger.debug("Could not evaluate board connection config: %s", exc)
            board_configured = False
    else:
        board_configured = False

    return {
        "board_ip": board_ip,
        "server_ip": server_ip,
        "uptime_seconds": uptime_seconds,
        "uptime_formatted": uptime_formatted,
        "connection_mode": connection_mode,
        "version": version,
        "timestamp": timestamp,
        "cache_status": cache_status,
        "board_configured": board_configured,
        "service_running": _service_is_running(),
    }


@router.get("/debug/network-diagnostics")
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
        results = run_full_diagnostics(
            board_host=board_host,
            board_port=board_port,
            board_api_key=board_api_key,
            use_cloud=use_cloud,
            cloud_key=cloud_key,
        )
        return {"status": "success", "diagnostics": results}
    except Exception as e:
        logger.error(f"Error running network diagnostics: {e}")
        raise HTTPException(status_code=500, detail="Network diagnostics failed") from e


@router.get("/cache-status")
async def get_cache_status():
    """Get the current client-side cache status for the board client."""
    service = get_service()
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")

    return service.vb_client.get_cache_status()


@router.post("/clear-cache")
async def clear_cache():
    """
    Clear the client-side message cache.

    This forces the next update to be sent to the board,
    even if the message content hasn't changed.
    """
    service = get_service()
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")

    service.vb_client.clear_cache()
    return {"status": "success", "message": "Cache cleared - next update will be sent to board"}


@router.post("/force-refresh")
async def force_refresh():
    """
    Force a display refresh, ignoring the cache.

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
        if error:
            raise HTTPException(status_code=500, detail=f"Failed to force refresh: {error}")
        return {
            "status": "success",
            "message": "Display force-refreshed successfully",
            "sent": sent,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error force-refreshing display: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to force refresh: {str(e)}") from e


@router.get("/logs")
async def get_logs(
    limit: int = Query(default=50, ge=1, le=500, description="Number of log entries to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    level: str | None = Query(default=None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"),
    search: str | None = Query(default=None, description="Search in log message or logger name"),
):
    """Get application logs with pagination, filtering, and search.

    Args:
        limit: Maximum number of log entries to return (default 50, max 500)
        offset: Number of entries to skip for pagination
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        search: Search text in log message or logger name

    Returns:
        List of log entries with pagination info
    """
    # Validate level if provided
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if level and level.upper() not in valid_levels:
        raise HTTPException(status_code=400, detail=f"Invalid log level: {level}. Valid levels: {valid_levels}")

    logs, total, has_more = _read_logs_from_files(limit=limit, offset=offset, level=level, search=search)

    return {
        "logs": logs,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "filters": {"level": level.upper() if level else None, "search": search},
    }
