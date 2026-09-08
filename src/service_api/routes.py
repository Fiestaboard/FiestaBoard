"""FastAPI router for the app's own service surface.

Eight route-methods that are not a data domain — they are *this server*:
``GET /`` (what am I), ``GET|HEAD /health`` (am I up), ``GET /status`` (what
is the display loop doing, per board), ``POST /start`` / ``POST /stop`` (make
it run or stop), ``POST /refresh`` (drive a pass now) and
``GET /silence-status`` (is the board in its quiet window).

Phase 2, Task 8 — the last untagged routes. Moved out of ``src/api_server.py``
and converted to ``docs/internal/reference/API_CONVENTIONS.md``: a declared
``response_model`` on every route, a Pydantic body on ``POST /refresh``
instead of ``payload: dict | None``, the ``{"status": "success", ...}``
envelopes replaced by bare bodies, and the failure codes each route can raise
declared in ``responses=``. ``tests/conventions_manifest.json`` lists
``service`` so a regression fails the build.

Collaborators resolve from :mod:`src.display_runtime` and
:mod:`src.board_guards` as module attributes, so this module never loads
``src.api_server`` (``tests/test_service_decoupled.py`` asserts that in a
fresh interpreter) and one patch target is the whole truth for a helper that
calls another helper.

The background-loop *state* deliberately stays in ``api_server`` — see the
:mod:`src.display_runtime` module docstring for why relocating a module global
cannot keep ``patch("src.api_server._service_running", ...)`` live. This module
reads it through ``runtime.is_service_running()`` and writes it through
``runtime.spawn_display_loop()`` / ``runtime.halt_display_loop()``.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from src import __version__
from src import display_runtime as runtime
from src.api_errors import errors
from src.board_guards import _require_board
from src.board_send_executor import run_board_send
from src.config import Config
from src.config_manager import get_config_manager

from .models import (
    ApiInfoResponse,
    BoardStatus,
    HealthResponse,
    RefreshRequest,
    RefreshResponse,
    ServiceStateResponse,
    SilenceStatusResponse,
    StatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["service"])


def _loop_is_running() -> bool:
    """True only when the flag is set *and* a service instance exists.

    Both halves matter: the flag can outlive a service that failed to
    rebuild, and a service can exist with the loop stopped.
    """
    return runtime.is_service_running() and runtime.get_service() is not None


# ---------------------------------------------------------------------------
# Identity and liveness
# ---------------------------------------------------------------------------


@router.get("/", response_model=ApiInfoResponse)
async def root():
    """Root endpoint with API information."""
    return ApiInfoResponse(name="FiestaBoard Display API", version="1.0.0", status="running")


@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(status="ok", service_running=_loop_is_running(), version=__version__)


@router.head("/health", response_model=HealthResponse)
async def health_head():
    """Health check endpoint (HEAD).

    Split from `health()` above into its own handler with a distinct name so
    each HTTP method gets its own APIRoute and its own OpenAPI operationId.
    A single @app.api_route(methods=["GET", "HEAD"]) produces one APIRoute
    whose unique_id is derived from `list(route.methods)[0]` — since
    route.methods is a set, that pick is non-deterministic, and FastAPI emits
    the same operationId for both the GET and HEAD operations (see #1572).
    """
    return await health()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/status", response_model=StatusResponse, responses=errors(503))
async def get_status():
    """Get current service status."""
    service = runtime.get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    settings_service = runtime.get_settings_service()

    status = StatusResponse(
        running=runtime.is_service_running(), initialized=service is not None, config_summary=Config.get_summary()
    )
    status.config_summary["active_page_id"] = settings_service.get_active_page_id()

    # Per-board status (issue #1244): configured/paused/active page for every
    # configured board, keyed by board id. Defensive throughout — a partial
    # boards list must never break the legacy top-level status fields.
    try:
        boards = settings_service.get_board_settings().boards or []
        # Why each board failed to get a client, when it failed (issue #1749).
        # A board skipped at startup is visible here instead of only in the log.
        init_errors = getattr(service, "board_init_errors", None)
        if not isinstance(init_errors, dict):
            init_errors = {}
        for board in boards:
            if not isinstance(board, dict) or not board.get("id"):
                continue
            bid = board["id"]
            try:
                configured = service.get_board_client(bid) is not None
            except Exception:
                configured = False
            active_page_id = settings_service.get_active_page_id(board_id=bid)
            if not isinstance(active_page_id, str):
                active_page_id = None
            init_error = init_errors.get(bid)
            if not isinstance(init_error, str):
                init_error = None
            status.boards[bid] = BoardStatus(
                configured=configured,
                paused=runtime._board_is_paused(bid),
                active_page_id=active_page_id,
                error=init_error,
            )
    except Exception as e:
        logger.debug(f"Per-board status unavailable: {e}")
    return status


# ---------------------------------------------------------------------------
# Display-loop lifecycle
# ---------------------------------------------------------------------------


@router.post("/start", response_model=ServiceStateResponse, responses=errors(500, 503))
async def start_service():
    """Start the background display loop."""
    if runtime.is_service_running():
        return ServiceStateResponse(running=True, changed=False, message="Service is already running")

    service = runtime.get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Retry initialization if it failed before, so the loop can start once the
    # configuration is fixed without restarting the container.
    if not service.vb_client:
        logger.info("Retrying service initialization...")
        if not service.initialize():
            raise HTTPException(
                status_code=503,
                detail="Service initialization failed - check board configuration (API key, host, etc.)",
            )
        logger.info("Service initialization successful on retry")

    runtime.spawn_display_loop()

    # Give it a moment to start
    await asyncio.sleep(0.5)

    if not runtime.is_service_running():
        raise HTTPException(status_code=500, detail="Service failed to start - check logs for details")
    return ServiceStateResponse(running=True, changed=True, message="Service started successfully")


@router.post("/stop", response_model=ServiceStateResponse)
async def stop_service():
    """Stop the background display loop.

    Idempotent by design and has no failure path: stopping an already-stopped
    loop is the state the caller asked for, so it answers 200 with
    ``changed: false`` rather than a 4xx. That is why ``service`` carries a
    ``declared_errors`` exception for this route in the conventions manifest.
    """
    if not runtime.is_service_running():
        return ServiceStateResponse(running=False, changed=False, message="Service is not running")

    runtime.halt_display_loop()
    return ServiceStateResponse(running=False, changed=True, message="Service stopped successfully")


# ---------------------------------------------------------------------------
# Manual refresh
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=RefreshResponse, responses=errors(404, 500, 503))
async def refresh_display(board_id: str | None = None, payload: RefreshRequest | None = None):
    """Manually trigger a display refresh.

    Args:
        board_id: Optional board to refresh (query param, or
            ``{"board_id": ...}`` in the JSON body). Omitted → legacy
            behavior: refresh every board, primary first (issue #1244).
    """
    if board_id is None and payload is not None:
        board_id = payload.board_id

    service = runtime.get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if board_id is None:
        # Every board is driven here, so a failing secondary must surface
        # too — the wrapper aggregates across the whole pass (issue #1791).
        # The pass is board network I/O, so it runs in a worker thread to
        # keep the event loop free (#1826); _send_with_status moves as one
        # call because its failure reason lives in a thread-local that is
        # set and read inside the same sync call.
        try:
            sent, error = await run_board_send(
                runtime._send_with_status,
                service,
                "check_and_send_active_page_with_status",
                "check_and_send_active_page",
            )
        except Exception as e:
            logger.error(f"Error refreshing display: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to refresh display: {e!s}") from e
        # Outside the try on purpose: inside it, this raise was caught by the
        # handler's own `except Exception` and re-raised as
        # HTTPException(500, str(e)) — and str(HTTPException) is
        # "500: <detail>", which is how the detail came to stutter.
        if error:
            raise HTTPException(status_code=500, detail=f"Failed to refresh display: {error}")
        return RefreshResponse(message="Display refreshed successfully", board_id=None, sent=sent)

    board = _require_board(board_id)
    rt = service.get_runtime(board_id)
    if rt is None:
        raise HTTPException(status_code=503, detail=f"Board client not initialized: {board_id}")
    is_primary = board_id == runtime.get_settings_service().get_primary_board_id()
    # Board network I/O — off the event loop (#1826); _send_with_status
    # moves as one call (thread-local failure reason, see above).
    try:
        sent, error = await run_board_send(
            runtime._send_with_status,
            service,
            "check_and_send_for_board_with_status",
            "check_and_send_for_board",
            board_id,
            rt,
            is_primary=is_primary,
            board=board,
        )
    except Exception as e:
        logger.error(f"Error refreshing board {board_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh display: {e!s}") from e
    if error:
        raise HTTPException(status_code=500, detail=f"Failed to refresh board {board_id}: {error}")
    return RefreshResponse(message=f"Board {board_id} refreshed successfully", board_id=board_id, sent=sent)


# ---------------------------------------------------------------------------
# Silence window
# ---------------------------------------------------------------------------


@router.get("/silence-status", response_model=SilenceStatusResponse)
async def get_silence_status(board_id: str | None = None):
    """Get current silence mode status with UTC times.

    Args:
        board_id: Optional board to read (query param). Omitted → the
            **primary** board (issue #1788), matching ``_silence_active`` and
            ``_board_is_paused``. This is a runtime status endpoint, not a
            config dump: "is silence on?" with no board means "on the board
            you drive by default". Returning the install-wide layer instead
            made the dashboard overlay, the silence-imminent banner and
            ``GET /silence-status`` all report the pre-save window on a
            single-board install, because the settings form writes the board
            layer. The install-wide layer is still readable as raw config via
            ``GET /settings/all``.

    Has no failure path — an unknown board is a *read*, and reads fall back to
    the safe answer rather than 404ing (API_CONVENTIONS.md §board_id
    validation), so ``service`` carries a ``declared_errors`` exception for
    this route in the conventions manifest.
    """
    from src.config import resolve_silence_schedule
    from src.time_service import get_time_service

    time_service = get_time_service()
    config_manager = get_config_manager()

    if board_id is None:
        try:
            primary = runtime.get_settings_service().get_primary_board_id()
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Could not resolve primary board for silence status: %s", e)
            primary = None
        # Coerce: an id that is not a string would land in the JSON response.
        board_id = str(primary) if isinstance(primary, str) and primary else None

    # No migration here: this is a read the UI polls on a timer, and the
    # migration is a config write.  It runs once at startup instead
    # (``_run_startup_migrations``) — see #1746.
    silence_config = resolve_silence_schedule(config_manager.get_feature("silence_schedule"), board_id)
    enabled = silence_config["enabled"]
    start_time = silence_config["start_time"]
    end_time = silence_config["end_time"]

    # Check if currently active
    active = time_service.is_time_in_window(start_time, end_time) if enabled else False

    current_utc = time_service.get_current_utc()

    # Determine next change time (simplified - just return start or end)
    next_change_utc = end_time if active else start_time

    # Wall-clock seconds until the next active/inactive transition. Lets the
    # frontend show a "silence starts in N min" warning without re-doing the
    # UTC + offset math the silence window uses (which has subtle edge cases
    # around midnight rollover and DST). None when silence is disabled.
    seconds_until_next_change: int | None = None
    if enabled:
        next_change_dt = time_service.parse_iso_time(next_change_utc)
        if next_change_dt is not None:
            delta_seconds = int((next_change_dt - current_utc).total_seconds())
            # next_change_dt is anchored to "today" in UTC, so a negative value
            # means the boundary already passed today and will recur tomorrow.
            if delta_seconds < 0:
                delta_seconds += 86_400
            seconds_until_next_change = delta_seconds

    return SilenceStatusResponse(
        enabled=enabled,
        active=active,
        start_time_utc=start_time,
        end_time_utc=end_time,
        current_time_utc=current_utc.strftime("%H:%M+00:00"),
        next_change_utc=next_change_utc,
        seconds_until_next_change=seconds_until_next_change,
        mode=silence_config["mode"],
        page_id=silence_config["page_id"],
        indicator_text=silence_config["indicator_text"],
        indicator_position=silence_config["indicator_position"],
        board_id=board_id,
    )
