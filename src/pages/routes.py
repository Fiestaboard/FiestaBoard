"""FastAPI router for the pages and page-send endpoints.

Handlers were moved here verbatim from ``src/api_server.py`` (issue #1756);
Phase 2 slice 3 then applied ``docs/internal/reference/API_CONVENTIONS.md`` to
them and retired the thirteen call-time ``from src.api_server import ...``
seams the move left behind.

Collaborators now resolve from their canonical homes at **module import
time**, so this module never loads ``src.api_server``
(``tests/test_pages_decoupled.py`` asserts that in a fresh interpreter, after
driving all fourteen handlers). Tests that need to stub a collaborator patch it
where this module binds it — ``src.pages.routes.<name>`` — not
``src.api_server.<name>``.

Two of those collaborators had no canonical home to move to, so they got one:
``src/board_guards.py`` (board lookup, pause and silence guards) and
``src/display_runtime.py`` (the ``DisplayService`` singleton accessor).
``src.api_server`` imports both, so its own handlers and their patch targets
are unchanged.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from src.api_deprecation import superseded_by_v1
from src.api_errors import errors
from src.board_guards import _board_dims, _board_is_paused, _require_board, _silence_active
from src.collections.models import is_collection_id
from src.collections.service import get_collection_service
from src.devices import resolve_dimensions, size_key
from src.display_runtime import get_service
from src.schedules.service import get_schedule_service
from src.settings.service import VALID_OUTPUT_TARGETS, get_settings_service
from src.text_to_board import text_to_board_array

from .models import (
    CurrentDisplayResponse,
    IncompatibleReference,
    PageCacheClearRequest,
    PageCacheClearResponse,
    PageCacheStatsResponse,
    PageCreate,
    PageDeleteResponse,
    PageImportPreview,
    PageImportRequest,
    PageListResponse,
    PagePreviewBatchRequest,
    PagePreviewBatchResponse,
    PagePreviewResponse,
    PageSendRequest,
    PageSendResponse,
    PageUpdate,
    PageUpdateResponse,
    ShareStringResponse,
)
from .models import Page as PageModel
from .service import find_incompatible_references, get_page_service
from .share import decode_page, encode_page

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])


def _reject_plugin_strategy_when_beta_off(strategy: str | None) -> None:
    """Reject ``plugin:<id>`` strategies when the transition-plugin beta
    flag is off.

    Applied to page create / update / import so a page can't persist a plugin
    strategy that the runtime won't actually honor.  Symmetric with the
    settings-service guard on ``update_transition_settings``.

    Lived in ``src/api_server.py`` until Phase 2 slice 3. Nothing else ever
    called it — these three handlers are its only callers — so it moved here
    with the routes rather than staying behind as a call-time seam.
    """
    if not isinstance(strategy, str):
        return
    from src.settings.service import TRANSITION_PLUGIN_PREFIX  # local: avoid cycle

    if not strategy.startswith(TRANSITION_PLUGIN_PREFIX):
        return
    settings_service = get_settings_service()
    if not settings_service.get_beta_settings().transition_plugins_enabled:
        raise HTTPException(
            status_code=400,
            detail=(
                "Transition plugins are an experimental beta. Enable them "
                "in Settings → Beta before assigning a 'plugin:<id>' "
                "strategy to a page."
            ),
        )


# No 4xx of its own: an empty instance is an empty list, not an error. See the
# declared_errors exception in tests/conventions_manifest.json.
@router.get(
    "/pages",
    response_model=PageListResponse,
    dependencies=[superseded_by_v1("GET /pages")],
)
async def list_pages():
    """List all saved pages."""
    page_service = get_page_service()
    pages = page_service.list_pages()

    return PageListResponse(pages=pages, total=len(pages))


@router.get(
    "/pages/current-display",
    response_model=CurrentDisplayResponse,
    responses=errors(404),
)
async def get_current_display():
    """Get the template content of the currently active board display.

    Resolves collections and schedule mode to find the actual page being shown.
    For template pages, returns the raw template and line metadata so the
    caller can use it as a starting point for a new page.  For other page
    types, returns the rendered output lines.

    Returns 404 when no active page can be determined.
    """
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

    if page.type == "template" and page.template:
        # Return raw template so variables like {{weather.temp}} are preserved
        template = page.template
        line_metadata = page.line_metadata
    else:
        # For single/composite pages, return the rendered output as template
        # lines. The forced render fans out to plugins — off the loop (#1826).
        result = await asyncio.to_thread(page_service.preview_page, active_page_id, force_refresh=True)
        template = result.formatted.split("\n") if result and result.available else []
        line_metadata = None

    return CurrentDisplayResponse(
        page_id=page.id,
        page_name=page.name,
        page_type=page.type,
        device_type=page.device_type,
        template=template,
        line_metadata=line_metadata,
    )


@router.post(
    "/pages",
    response_model=PageModel,
    status_code=201,
    responses=errors(400),
    dependencies=[superseded_by_v1("POST /pages")],
)
async def create_page(page_data: PageCreate):
    """
    Create a new page.

    Page types:
    - single: Display a single source (set display_type)
    - composite: Combine rows from multiple sources (set rows)
    - template: Custom templated content (set template)
    """
    _reject_plugin_strategy_when_beta_off(page_data.transition_strategy)
    page_service = get_page_service()

    try:
        return page_service.create_page(page_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/pages/{page_id}",
    response_model=PageModel,
    responses=errors(404),
    dependencies=[superseded_by_v1("GET /pages/{page_id}")],
)
async def get_page(page_id: str):
    """Get a page by ID."""
    page_service = get_page_service()
    page = page_service.get_page(page_id)

    if not page:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    return page


@router.put(
    "/pages/{page_id}",
    response_model=PageUpdateResponse,
    responses=errors(400, 404),
    dependencies=[superseded_by_v1("PUT /pages/{page_id}")],
)
async def update_page(page_id: str, page_data: PageUpdate):
    """Update an existing page.

    When the update changes the page's size (device/size retarget, issue
    #1250), ``incompatible_references`` lists the schedule entries and
    per-board active pages that now point this page at a board it no longer
    fits. Warn-only — no reference is mutated or removed. The list is empty
    when the size did not change, or when nothing broke.
    """
    _reject_plugin_strategy_when_beta_off(page_data.transition_strategy)
    page_service = get_page_service()
    existing = page_service.get_page(page_id)

    try:
        page = page_service.update_page(page_id, page_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not page:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    incompatible: list[IncompatibleReference] = []
    if existing is not None:
        old_size = size_key(existing.device_type, existing.notes_wide, existing.notes_tall)
        new_size = size_key(page.device_type, page.notes_wide, page.notes_tall)
        if old_size != new_size:
            incompatible = [IncompatibleReference(**ref) for ref in find_incompatible_references(page)]
    return PageUpdateResponse(page=page, incompatible_references=incompatible)


@router.delete(
    "/pages/{page_id}",
    response_model=PageDeleteResponse,
    responses=errors(404),
    dependencies=[superseded_by_v1("DELETE /pages/{page_id}")],
)
async def delete_page(page_id: str):
    """Delete a page.

    If this is the last page, a default welcome page is automatically created
    to ensure there is always at least one page.

    If the deleted page was the active display page, the active page will be
    updated to another valid page automatically.
    """
    page_service = get_page_service()

    result = page_service.delete_page(page_id)

    if not result.deleted:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    message = f"Page {page_id} deleted"
    if result.default_page_created:
        message = f"Page {page_id} deleted. A default welcome page was created."

    return PageDeleteResponse(
        id=page_id,
        message=message,
        default_page_created=result.default_page_created,
        new_page_id=result.new_page_id if result.default_page_created else None,
        active_page_updated=result.active_page_updated,
        new_active_page_id=result.new_active_page_id if result.active_page_updated else None,
    )


@router.get(
    "/pages/{page_id}/share",
    response_model=ShareStringResponse,
    responses=errors(404),
)
async def get_page_share_string(page_id: str):
    """Return a portable share string for an existing page."""
    page_service = get_page_service()
    page = page_service.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    return ShareStringResponse(share_string=encode_page(page))


@router.post(
    "/pages/import/preview",
    response_model=PageImportPreview,
    responses=errors(422),
)
async def preview_page_import(body: PageImportRequest):
    """Decode a share string and return the page data without persisting it."""
    try:
        page_data = decode_page(body.share_string)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return page_data


@router.post(
    "/pages/import",
    response_model=PageModel,
    status_code=201,
    responses=errors(400, 422),
)
async def import_page(body: PageImportRequest):
    """Create a new page from a share string.

    A share string the decoder rejects, or one whose contents do not satisfy
    ``PageCreate``, is the caller's problem: 422. A page that decodes and
    validates but that the service refuses is a 400. Anything else is a
    server fault and propagates as a 500 — this handler used to convert
    *every* unexpected exception to 422, which reported a storage failure or
    a bug in this process as "your share string is bad" (Phase 2 slice 3).
    """
    try:
        page_data = decode_page(body.share_string)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    try:
        page_create = PageCreate(**{k: v for k, v in page_data.items() if k in PageCreate.model_fields})
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid share string — {e}") from e

    _reject_plugin_strategy_when_beta_off(page_create.transition_strategy)

    page_service = get_page_service()
    try:
        return page_service.create_page(page_create)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/pages/{page_id}/preview",
    response_model=PagePreviewResponse,
    responses=errors(404, 503),
)
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
    page_service = get_page_service()
    settings_service = get_settings_service()

    # Always force refresh for the active page to ensure it's up-to-date
    active_page_id = settings_service.get_active_page_id()
    if page_id == active_page_id:
        force_refresh = True

    # Rendering fans out to plugins (network I/O) — off the event loop (#1826).
    # The preview cache write inside is a single dict item assignment, safe
    # under concurrent worker threads on CPython; store-level locking is
    # Track A2's job (#1848).
    result = await asyncio.to_thread(page_service.preview_page, page_id, force_refresh=force_refresh)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Page rendering failed")

    return PagePreviewResponse(
        page_id=page_id,
        message=result.formatted,
        lines=result.formatted.split("\n"),
        display_type=result.display_type,
        raw=result.raw,
    )


@router.post(
    "/pages/preview/batch",
    response_model=PagePreviewBatchResponse,
    responses=errors(422),
)
async def preview_pages_batch(request: PagePreviewBatchRequest):
    """
    Preview multiple pages in a single request.

    Returns a dict mapping page_id to preview data (or error).
    Uses cached previews by default for fast responses.
    Active page is always rendered fresh regardless of force_refresh setting.
    Template context (plugin data) is built once and shared across all page renders.

    A per-page render failure is reported inside ``previews`` with
    ``available: false`` — the request itself still succeeded. Only a
    malformed body (``page_ids`` that is not a list of strings) is a 422.
    """
    page_ids = request.page_ids

    page_service = get_page_service()
    settings_service = get_settings_service()
    active_page_id = settings_service.get_active_page_id()
    results: dict = {}

    # Use batch preview to build template context once for all pages. One
    # worker-thread call for the whole batch — the internal context sharing
    # per board size must be preserved, so the pages are NOT parallelized;
    # the point is only that N renders' worth of plugin fan-out stops
    # seizing the event loop (#1826).
    batch_results = await asyncio.to_thread(
        page_service.preview_pages_batch,
        page_ids,
        force_refresh=request.force_refresh,
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

    return PagePreviewBatchResponse(
        previews=results,
        total=len(page_ids),
        successful=sum(1 for r in results.values() if r.get("available", False)),
    )


# No 4xx of its own: reports in-memory cache state that always exists. See the
# declared_errors exception in tests/conventions_manifest.json.
@router.get("/pages/cache/stats", response_model=PageCacheStatsResponse)
async def get_page_cache_stats():
    """
    Get preview cache statistics.

    Returns information about the preview cache including size,
    cached page IDs, and TTL configuration.
    """
    page_service = get_page_service()
    return PageCacheStatsResponse(**page_service.get_cache_stats())


@router.post(
    "/pages/cache/clear",
    response_model=PageCacheClearResponse,
    responses=errors(422),
)
async def clear_page_cache(request: PageCacheClearRequest | None = None):
    """
    Clear preview cache.

    Request body (optional):
        {
            "page_id": "page123"  // Clear specific page, omit to clear all
        }

    Clears the preview cache, forcing fresh renders on next preview.
    Useful for testing or when data sources have been updated.
    """
    page_service = get_page_service()

    page_id = request.page_id if request else None

    # Public service method, not `_invalidate_cache` — a route must not reach
    # into another object's privates (API_CONVENTIONS.md, "Routers and
    # services").
    page_service.invalidate_preview_cache(page_id)

    if page_id:
        return PageCacheClearResponse(message=f"Cache cleared for page {page_id}", page_id=page_id)
    return PageCacheClearResponse(message="All preview caches cleared")


@router.post(
    "/pages/{page_id}/send",
    response_model=PageSendResponse,
    responses=errors(400, 404, 500, 503),
)
async def send_page(
    page_id: str,
    target: str | None = None,
    board_id: str | None = None,
    payload: PageSendRequest | None = None,
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
    if target is None and payload:
        target = payload.target
    if board_id is None and payload:
        board_id = payload.board_id
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
        board = _require_board(board_id)
        board_client = service.get_board_client(board_id)
        if board_client is None:
            raise HTTPException(status_code=503, detail=f"Board client not initialized: {board_id}")
    else:
        if not service or not service.vb_client:
            raise HTTPException(status_code=503, detail="Service not initialized")
        board_client = service.vb_client

    # The page lookup, forced fresh render (plugin fan-out), and board send
    # (network call plus an up-to-seconds transition animation) all block, so
    # they run as one worker-thread unit and the event loop keeps serving
    # requests (#1826). HTTPExceptions raised inside propagate through the
    # await unchanged.
    def _work() -> PageSendResponse:
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
                # render() serializes concurrent senders via the client's
                # per-board _send_lock, so worker threads can't interleave.
                success, was_sent = board_client.render(
                    board_array,
                    strategy=strategy,
                    step_interval_ms=interval_ms,
                    step_size=step_size,
                    device_type=(board.get("device_type") if board is not None else page.device_type),
                )
                sent_to_board = was_sent
                if not success:
                    # Board offline / unreachable. Deliberately NOT 502/503/504:
                    # nginx intercepts those on /api/ and replaces the body with
                    # its startup placeholder, so the caller would lose the
                    # reason entirely.
                    #
                    # It is now the domain's one error shape ({"detail": str}),
                    # raised rather than returned. It used to be a JSONResponse
                    # carrying a 6-key body, which (a) is not the shape every
                    # other pages route promises, and (b) sat in a nested
                    # closure, which `no_200_on_failure` explicitly ignores — so
                    # no rule saw a routine 500 that no route declared.
                    logger.error(f"Failed to send page {page_id} to board (offline or unreachable)")
                    raise HTTPException(status_code=500, detail="Failed to send to board")
                if was_sent and (board_id is None or board_id == settings_service.get_primary_board_id()):
                    # Adaptive post-send refresh polls the primary board only.
                    service.request_board_refresh()

        return PageSendResponse(
            page_id=page_id,
            message=result.formatted,
            sent_to_board=sent_to_board,
            paused=paused,
            target=target or settings_service.get_output_settings().target,
            board_id=board_id,
        )

    # Board network I/O goes on the dedicated bounded send pool, never the
    # shared default executor (#1878) — see src/board_send_executor.py.
    from src.board_send_executor import run_board_send

    return await run_board_send(_work)
