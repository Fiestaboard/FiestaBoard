"""FastAPI router for the pages, staff-picks and page-send endpoints.

Handlers moved verbatim from ``src/api_server.py`` (issue #1756, pure move).
Names that still live in ``api_server`` — the service getters, the
board/silence/pause guards, and the utilities the test-suite monkeypatches as
``src.api_server.<name>`` — are imported *inside* each handler so they resolve
through the api_server module at call time. A module-level import would both
create an import cycle (api_server imports this router) and detach the
handlers from those patches.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.settings.service import VALID_OUTPUT_TARGETS

from .models import PageCreate, PageUpdate
from .service import find_incompatible_references
from .share import decode_page, encode_page

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])


@router.get("/pages")
async def list_pages():
    """List all saved pages."""
    from src.api_server import get_page_service  # patched-in-tests seam — see module docstring (#1756)

    page_service = get_page_service()
    pages = page_service.list_pages()

    return {"pages": [p.model_dump() for p in pages], "total": len(pages)}


@router.get("/pages/current-display")
async def get_current_display():
    """Get the template content of the currently active board display.

    Resolves collections and schedule mode to find the actual page being shown.
    For template pages, returns the raw template and line metadata so the
    caller can use it as a starting point for a new page.  For other page
    types, returns the rendered output lines.

    Returns 404 when no active page can be determined.
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        get_collection_service,
        get_page_service,
        get_schedule_service,
        get_settings_service,
        is_collection_id,
    )

    settings_service = get_settings_service()
    page_service = get_page_service()
    collection_service = get_collection_service()

    # Determine the active page ID (schedule-aware)
    if settings_service.is_schedule_enabled():
        from src.time_service import get_time_service

        time_service = get_time_service()
        now = time_service.get_current_time()
        current_time = now.time()
        current_day = now.strftime("%A").lower()
        schedule_service = get_schedule_service()
        active_page_id = schedule_service.get_active_page_id(current_time, current_day)
    else:
        active_page_id = settings_service.get_active_page_id()

    if not active_page_id:
        raise HTTPException(status_code=404, detail="No active page set")

    # Resolve collection to underlying page
    if is_collection_id(active_page_id):
        resolved = collection_service.resolve_page_id(active_page_id)
        if not resolved:
            raise HTTPException(status_code=404, detail="Collection could not be resolved")
        active_page_id = resolved

    page = page_service.get_page(active_page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Active page not found")

    response: dict = {
        "page_id": page.id,
        "page_name": page.name,
        "page_type": page.type,
        "device_type": page.device_type,
    }

    if page.type == "template" and page.template:
        # Return raw template so variables like {{weather.temp}} are preserved
        response["template"] = page.template
        response["line_metadata"] = [m.model_dump() for m in page.line_metadata] if page.line_metadata else None
    else:
        # For single/composite pages, return the rendered output as template lines
        result = page_service.preview_page(active_page_id, force_refresh=True)
        if result and result.available:
            response["template"] = result.formatted.split("\n")
            response["line_metadata"] = None
        else:
            response["template"] = []
            response["line_metadata"] = None

    return response


@router.post("/pages")
async def create_page(page_data: PageCreate):
    """
    Create a new page.

    Page types:
    - single: Display a single source (set display_type)
    - composite: Combine rows from multiple sources (set rows)
    - template: Custom templated content (set template)
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        _reject_plugin_strategy_when_beta_off,
        get_page_service,
    )

    _reject_plugin_strategy_when_beta_off(page_data.transition_strategy)
    page_service = get_page_service()

    try:
        page = page_service.create_page(page_data)
        return {"status": "success", "page": page.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/pages/{page_id}")
async def get_page(page_id: str):
    """Get a page by ID."""
    from src.api_server import get_page_service  # patched-in-tests seam — see module docstring (#1756)

    page_service = get_page_service()
    page = page_service.get_page(page_id)

    if not page:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    return page.model_dump()


@router.put("/pages/{page_id}")
async def update_page(page_id: str, page_data: PageUpdate):
    """Update an existing page.

    When the update changes the page's size (device/size retarget, issue
    #1250), the response includes ``incompatible_references``: schedule
    entries and per-board active pages that now point this page at a board
    it no longer fits. Warn-only — no reference is mutated or removed.
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        _reject_plugin_strategy_when_beta_off,
        get_page_service,
    )
    from src.devices import size_key

    _reject_plugin_strategy_when_beta_off(page_data.transition_strategy)
    page_service = get_page_service()
    existing = page_service.get_page(page_id)

    try:
        page = page_service.update_page(page_id, page_data)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

        response = {"status": "success", "page": page.model_dump()}
        if existing is not None:
            old_size = size_key(existing.device_type, existing.notes_wide, existing.notes_tall)
            new_size = size_key(page.device_type, page.notes_wide, page.notes_tall)
            if old_size != new_size:
                response["incompatible_references"] = find_incompatible_references(page)
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/pages/{page_id}")
async def delete_page(page_id: str):
    """Delete a page.

    If this is the last page, a default welcome page is automatically created
    to ensure there is always at least one page.

    If the deleted page was the active display page, the active page will be
    updated to another valid page automatically.
    """
    from src.api_server import get_page_service  # patched-in-tests seam — see module docstring (#1756)

    page_service = get_page_service()

    result = page_service.delete_page(page_id)

    if not result.deleted:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    response = {
        "status": "success",
        "message": f"Page {page_id} deleted",
        "default_page_created": result.default_page_created,
        "active_page_updated": result.active_page_updated,
    }

    if result.default_page_created:
        response["message"] = f"Page {page_id} deleted. A default welcome page was created."
        response["new_page_id"] = result.new_page_id

    if result.active_page_updated:
        response["new_active_page_id"] = result.new_active_page_id

    return response


@router.get("/pages/{page_id}/share")
async def get_page_share_string(page_id: str):
    """Return a portable share string for an existing page."""
    from src.api_server import get_page_service  # patched-in-tests seam — see module docstring (#1756)

    page_service = get_page_service()
    page = page_service.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    return {"share_string": encode_page(page)}


class PageImportRequest(BaseModel):
    share_string: str


@router.post("/pages/import/preview")
async def preview_page_import(body: PageImportRequest):
    """Decode a share string and return the page data without persisting it."""
    try:
        page_data = decode_page(body.share_string)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return page_data


@router.post("/pages/import")
async def import_page(body: PageImportRequest):
    """Create a new page from a share string."""
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        _reject_plugin_strategy_when_beta_off,
        get_page_service,
    )

    try:
        page_data = decode_page(body.share_string)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    page_service = get_page_service()
    try:
        page_create = PageCreate(**{k: v for k, v in page_data.items() if k in PageCreate.model_fields})
        _reject_plugin_strategy_when_beta_off(page_create.transition_strategy)
        page = page_service.create_page(page_create)
        return {"status": "success", "page": page.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Staff Picks
# ---------------------------------------------------------------------------

# NOTE: one more .parent than api_server.py had — this file is a level deeper.
_STAFF_PICKS_PATH = Path(__file__).parent.parent.parent / "staff-picks" / "picks.json"


def _load_staff_picks() -> list:
    try:
        with open(_STAFF_PICKS_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


@router.get("/staff-picks")
async def list_staff_picks():
    """Return all staff picks (without share strings)."""
    picks = _load_staff_picks()
    return [{k: v for k, v in pick.items() if k != "share_string"} for pick in picks]


@router.get("/staff-picks/{pick_id}/share")
async def get_staff_pick_share(pick_id: str):
    """Return the share string for a specific staff pick."""
    picks = _load_staff_picks()
    pick = next((p for p in picks if p["id"] == pick_id), None)
    if not pick:
        raise HTTPException(status_code=404, detail=f"Staff pick not found: {pick_id}")
    return {"share_string": pick["share_string"]}


@router.post("/pages/{page_id}/preview")
async def preview_page(
    page_id: str, force_refresh: bool = Query(default=False, description="Force fresh render, bypass cache")
):
    """
    Preview a page's rendered output.

    Uses cached preview by default for fast responses. Set force_refresh=true
    to always render fresh (useful when editing or displaying active page).

    Args:
        page_id: The page ID to preview
        force_refresh: If true, bypass cache and always render fresh

    Returns:
        The formatted text that would be displayed.
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        get_page_service,
        get_settings_service,
    )

    page_service = get_page_service()
    settings_service = get_settings_service()

    # Always force refresh for the active page to ensure it's up-to-date
    active_page_id = settings_service.get_active_page_id()
    if page_id == active_page_id:
        force_refresh = True

    result = page_service.preview_page(page_id, force_refresh=force_refresh)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Page rendering failed")

    return {
        "page_id": page_id,
        "message": result.formatted,
        "lines": result.formatted.split("\n"),
        "display_type": result.display_type,
        "raw": result.raw,
    }


@router.post("/pages/preview/batch")
async def preview_pages_batch(request: dict):
    """
    Preview multiple pages in a single request.

    Request body:
        {
            "page_ids": ["page1", "page2", ...],
            "force_refresh": false  // Optional, defaults to false
        }

    Returns a dict mapping page_id to preview data (or error).
    Uses cached previews by default for fast responses.
    Active page is always rendered fresh regardless of force_refresh setting.
    Template context (plugin data) is built once and shared across all page renders.
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        get_page_service,
        get_settings_service,
    )

    page_ids = request.get("page_ids", [])
    force_refresh = request.get("force_refresh", False)

    if not isinstance(page_ids, list):
        raise HTTPException(status_code=400, detail="page_ids must be a list")

    page_service = get_page_service()
    settings_service = get_settings_service()
    active_page_id = settings_service.get_active_page_id()
    results = {}

    # Use batch preview to build template context once for all pages
    batch_results = page_service.preview_pages_batch(
        page_ids,
        force_refresh=force_refresh,
        active_page_id=active_page_id,
    )

    for page_id in page_ids:
        result = batch_results.get(page_id)
        if result is None:
            results[page_id] = {"error": "Page not found", "available": False}
        elif not result.available:
            results[page_id] = {"error": result.error or "Page rendering failed", "available": False}
        else:
            results[page_id] = {
                "page_id": page_id,
                "message": result.formatted,
                "lines": result.formatted.split("\n"),
                "display_type": result.display_type,
                "raw": result.raw,
                "available": True,
            }

    return {
        "previews": results,
        "total": len(page_ids),
        "successful": sum(1 for r in results.values() if r.get("available", False)),
    }


@router.get("/pages/cache/stats")
async def get_page_cache_stats():
    """
    Get preview cache statistics.

    Returns information about the preview cache including size,
    cached page IDs, and TTL configuration.
    """
    from src.api_server import get_page_service  # patched-in-tests seam — see module docstring (#1756)

    page_service = get_page_service()
    return page_service.get_cache_stats()


@router.post("/pages/cache/clear")
async def clear_page_cache(request: dict = None):
    """
    Clear preview cache.

    Request body (optional):
        {
            "page_id": "page123"  // Clear specific page, omit to clear all
        }

    Clears the preview cache, forcing fresh renders on next preview.
    Useful for testing or when data sources have been updated.
    """
    from src.api_server import get_page_service  # patched-in-tests seam — see module docstring (#1756)

    page_service = get_page_service()

    page_id = None
    if request:
        page_id = request.get("page_id")

    page_service._invalidate_cache(page_id)

    if page_id:
        return {"status": "success", "message": f"Cache cleared for page {page_id}"}
    else:
        return {"status": "success", "message": "All preview caches cleared"}


@router.post("/pages/{page_id}/send")
async def send_page(
    page_id: str, target: str | None = None, board_id: str | None = None, payload: dict | None = Body(None)
):
    """
    Send a page to the configured target.

    Args:
        page_id: The page ID
        target: Override output target (ui, board, both) — query param,
            or ``{"target": ...}`` in the JSON body
        board_id: Optional board to send to (query param, or
            ``{"board_id": ...}`` in the JSON body). Omitted → primary
            board, legacy behavior (issue #1244).
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        _board_dims,
        _board_is_paused,
        _find_board,
        _silence_active,
        get_page_service,
        get_service,
        get_settings_service,
        resolve_dimensions,
        text_to_board_array,
    )

    if target is None and payload:
        target = payload.get("target")
    if board_id is None and payload:
        board_id = payload.get("board_id")
    if target is not None and target not in VALID_OUTPUT_TARGETS:
        raise HTTPException(status_code=400, detail=f"Invalid target: {target}. Valid targets: {VALID_OUTPUT_TARGETS}")

    page_service = get_page_service()
    settings_service = get_settings_service()
    service = get_service()

    # Resolve the target board's client: explicit board_id routes to that
    # board's client; omitted keeps the legacy primary-client path.
    board = None
    if board_id is not None:
        if not service:
            raise HTTPException(status_code=503, detail="Service not initialized")
        board = _find_board(board_id)
        if board is None:
            raise HTTPException(status_code=404, detail=f"Board not found: {board_id}")
        board_client = service.get_board_client(board_id)
        if board_client is None:
            raise HTTPException(status_code=503, detail=f"Board client not initialized: {board_id}")
    else:
        if not service or not service.vb_client:
            raise HTTPException(status_code=503, detail="Service not initialized")
        board_client = service.vb_client

    # Get the page for transition settings
    page = page_service.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    # Render the page - always force fresh render when sending to board
    result = page_service.preview_page(page_id, force_refresh=True)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Page rendering failed")

    # Determine target
    if target is None:
        send_to_board = settings_service.should_send_to_board()
    else:
        send_to_board = target in ["board", "both"]

    sent_to_board = False
    paused = False
    if send_to_board:
        # CRITICAL: Block ALL manual sends during silence mode to prevent
        # wake-ups — for the board this send targets (issue #1788).
        if _silence_active(board_id):
            logger.info("Silence mode is active - blocking manual page send to prevent wake-up")
            sent_to_board = False
            # Don't raise error, just skip sending
        elif _board_is_paused(board_id):
            # Block when the target (or first) board is paused (issue #970).
            logger.info("Board is paused - blocking manual page send")
            paused = True
        else:
            # Use page-level transitions if set, otherwise fall back to system defaults
            system_transition = settings_service.get_transition_settings()
            strategy = page.transition_strategy if page.transition_strategy else system_transition.strategy
            interval_ms = (
                page.transition_interval_ms
                if page.transition_interval_ms is not None
                else system_transition.step_interval_ms
            )
            step_size = (
                page.transition_step_size if page.transition_step_size is not None else system_transition.step_size
            )

            # Size the grid to the explicit target board when given (issue
            # #1244); otherwise keep sizing to the page's device type.
            if board is not None:
                dims = _board_dims(board)
            else:
                dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
            board_array = text_to_board_array(result.formatted, rows=dims.rows, cols=dims.cols)
            success, was_sent = board_client.render(
                board_array,
                strategy=strategy,
                step_interval_ms=interval_ms,
                step_size=step_size,
                device_type=(board.get("device_type") if board is not None else page.device_type),
            )
            sent_to_board = was_sent
            if not success:
                # Board offline / unreachable — degrade gracefully with a
                # structured error instead of a bare 500 detail string so
                # callers can distinguish "board unreachable" from a server
                # fault. Must not be 502/503/504: nginx intercepts those on
                # /api/ and replaces the body with its startup placeholder.
                logger.error(f"Failed to send page {page_id} to board (offline or unreachable)")
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "detail": "Failed to send to board",
                        "page_id": page_id,
                        "sent_to_board": False,
                        "paused": False,
                        "target": target or settings_service.get_output_settings().target,
                        "board_id": board_id,
                    },
                )
            if was_sent and (board_id is None or board_id == settings_service.get_primary_board_id()):
                # Adaptive post-send refresh polls the primary board only.
                service.request_board_refresh()

    return {
        "status": "success",
        "page_id": page_id,
        "message": result.formatted,
        "sent_to_board": sent_to_board,
        "paused": paused,
        "target": target or settings_service.get_output_settings().target,
        "board_id": board_id,
    }
