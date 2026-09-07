"""FastAPI router for the display-source endpoints.

Handlers were moved here verbatim from ``src/api_server.py`` (Phase 2 slice 8,
Task 8); the conventions pass in the next commit applies
``docs/internal/reference/API_CONVENTIONS.md`` to them and retires the seams
the move leaves behind.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``
(``tests/test_displays_decoupled.py`` asserts that in a fresh interpreter).
Tests that need to stub a collaborator patch it where this module binds it —
``src.displays.routes.<name>`` — not ``src.api_server.<name>``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response

from src.api_errors import errors
from src.board_guards import _board_is_paused
from src.devices import resolve_dimensions
from src.display_runtime import get_service
from src.settings.service import VALID_OUTPUT_TARGETS, get_settings_service
from src.text_to_board import text_to_board_array

from .models import (
    DisplayEntry,
    DisplayListResponse,
    DisplayRawBatchEntry,
    DisplayRawBatchRequest,
    DisplayRawBatchResponse,
    DisplayRawResponse,
    DisplayResponse,
    DisplaySendResponse,
)
from .service import get_display_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["displays"])


# No 4xx of its own: an instance with no plugins installed answers an empty
# list, not an error. See the declared_errors exception in
# tests/conventions_manifest.json.
@router.get("/displays", response_model=DisplayListResponse)
async def list_displays():
    """
    List all available display types and their status.

    Returns information about each display source including whether
    it's currently available/configured.
    """
    display_service = get_display_service()
    displays = display_service.get_available_displays()
    return DisplayListResponse(
        displays=[DisplayEntry(**entry) for entry in displays],
        total=len(displays),
        available_count=sum(1 for d in displays if d["available"]),
    )


@router.get("/displays/{display_type}", response_model=DisplayResponse, responses=errors(400, 503))
async def get_display(display_type: str):
    """
    Get formatted output for a specific display type.

    Args:
        display_type: One of: weather, datetime, weather_datetime,
                      home_assistant, star_trek, guest_wifi

    Returns:
        Formatted message text ready for display on board.
    """
    display_service = get_display_service()
    result = display_service.get_display(display_type)

    # Check for invalid display type (will have error message about valid types)
    if not result.available and result.error and "Unknown display type" in result.error:
        raise HTTPException(status_code=400, detail=result.error)

    if not result.available and result.error:
        raise HTTPException(status_code=503, detail=result.error)

    lines = result.formatted.split("\n") if result.formatted else []
    return DisplayResponse(
        display_type=result.display_type,
        message=result.formatted,
        lines=lines,
        line_count=len(lines),
        available=result.available,
    )


# One of the four endpoints that answer "what does this source hold", found by
# the 2026-09 audit. It was superseded by GET /plugins/{plugin_id}/data, which
# serves the same raw payload with the plugin system's own error contract, and
# has advertised that with a Deprecation/Link header pair since then. Marking
# it deprecated in the OpenAPI schema too costs nothing and makes the intent
# visible to generated clients; the endpoint keeps answering exactly as before.
# Removal is tracked in #1911 — do not delete it in this PR.
@router.get(
    "/displays/{display_type}/raw",
    response_model=DisplayRawResponse,
    responses=errors(503),
    deprecated=True,
)
async def get_display_raw(display_type: str, response: Response):
    """
    Deprecated: Use /plugins/{plugin_id}/data instead.

    Get raw data from a display source (before formatting).

    This is useful for debugging or building custom displays.

    Args:
        display_type: Plugin ID (e.g., weather, datetime, stocks)

    Returns:
        Raw data dictionary from the source.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'</plugins/{display_type}/data>; rel="successor-version"'

    display_service = get_display_service()
    result = display_service.get_display(display_type)

    if not result.available and result.error:
        raise HTTPException(status_code=503, detail=result.error)

    return DisplayRawResponse(
        display_type=result.display_type,
        data=result.raw,
        available=result.available,
        error=result.error,
    )


@router.post("/displays/raw/batch", response_model=DisplayRawBatchResponse, responses=errors(400))
async def get_displays_raw_batch(request: DisplayRawBatchRequest):
    """
    Get raw data from multiple display sources in one request.

    This is useful for efficiently fetching data for multiple plugins
    without making individual requests.

    Request body:
        {
            "display_types": ["baywheels", "muni", "weather", "stocks"],
            "enabled_only": true  // Optional, only fetch enabled plugins
        }

    Returns:
        {
            "displays": {
                "baywheels": {
                    "data": {...},
                    "available": true,
                    "error": null
                },
                ...
            },
            "total": 4,
            "successful": 3
        }
    """
    display_types = request.display_types
    enabled_only = request.enabled_only

    if not display_types:
        raise HTTPException(status_code=400, detail="display_types parameter required")

    display_service = get_display_service()
    results: dict[str, DisplayRawBatchEntry] = {}

    for display_type in display_types:
        try:
            result = display_service.get_display(display_type)

            # Skip if enabled_only is true and plugin is not available
            if enabled_only and not result.available:
                continue

            results[display_type] = DisplayRawBatchEntry(
                data=result.raw or {}, available=result.available, error=result.error
            )
        except Exception as e:
            # Per-source failure, not a request failure: the caller asked for
            # N sources and gets N verdicts. The 200 carries `available: false`
            # plus the reason, which is the answer, not a masked error.
            logger.error(f"Error fetching display {display_type}: {e}", exc_info=True)
            results[display_type] = DisplayRawBatchEntry(data={}, available=False, error=str(e))

    return DisplayRawBatchResponse(
        displays=results,
        total=len(display_types),
        successful=sum(1 for r in results.values() if r.available),
    )


@router.post("/displays/{display_type}/send", response_model=DisplaySendResponse, responses=errors(400, 500, 503))
async def send_display(display_type: str, target: str | None = None):
    """
    Send a display to the configured target (ui, board, or both).

    Args:
        display_type: The display type to send
        target: Override output target (ui, board, both). If not provided,
                uses the configured default.

    Returns:
        Result of the send operation.
    """
    if target is not None and target not in VALID_OUTPUT_TARGETS:
        raise HTTPException(status_code=400, detail=f"Invalid target: {target}. Valid targets: {VALID_OUTPUT_TARGETS}")

    display_service = get_display_service()
    settings_service = get_settings_service()
    service = get_service()

    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Get the display content (validates display_type against plugin registry)
    result = display_service.get_display(display_type)

    # Check for invalid display type
    if not result.available and result.error and "Unknown display type" in result.error:
        raise HTTPException(status_code=400, detail=result.error)

    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Display not available")

    # Determine target
    if target is None:
        send_to_board = settings_service.should_send_to_board()
    else:
        send_to_board = target in ["board", "both"]

    sent_to_board = False
    paused = False
    if send_to_board:
        # Skip when the (first) board is paused (issue #970).
        if _board_is_paused():
            logger.info("Board is paused - skipping display send to board")
            paused = True
        else:
            transition = settings_service.get_transition_settings()
            # Size to the first board's device type/dimensions (flagship, note,
            # or a note array's notes_wide×notes_tall geometry).
            board_settings = settings_service.get_board_settings()
            device_type = "flagship"
            notes_wide = 1
            notes_tall = 1
            if board_settings.boards:
                primary_board = board_settings.boards[0]
                device_type = primary_board.get("device_type", "flagship")
                notes_wide = primary_board.get("notes_wide", 1)
                notes_tall = primary_board.get("notes_tall", 1)
            dims = resolve_dimensions(device_type, notes_wide, notes_tall)
            board_array = text_to_board_array(result.formatted, rows=dims.rows, cols=dims.cols)
            success, was_sent = service.vb_client.render(
                board_array,
                strategy=transition.strategy,
                step_interval_ms=transition.step_interval_ms,
                step_size=transition.step_size,
                device_type=device_type,
            )
            sent_to_board = was_sent
            if not success:
                raise HTTPException(status_code=500, detail="Failed to send to board")

    return DisplaySendResponse(
        display_type=display_type,
        message=result.formatted,
        sent_to_board=sent_to_board,
        paused=paused,
        target=target or settings_service.get_output_settings().target,
    )
