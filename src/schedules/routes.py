"""FastAPI router for the schedule endpoints.

Handlers moved verbatim from ``src/api_server.py`` (issue #1756, pure move).
Names that still live in ``api_server`` — the service getters and the
active-page/override resolvers shared with the settings routes — are imported
*inside* each handler so they resolve through the api_server module at call
time. The test-suite patches them as ``src.api_server.<name>``; a
module-level import would both create an import cycle (api_server imports
this router) and detach the moved handlers from those patches.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from .models import ScheduleCreate, ScheduleUpdate

router = APIRouter(tags=["schedules"])


def _enrich_schedule_with_sun_times(schedule_dict: dict) -> dict:
    """Add resolved_start_time / resolved_end_time to a schedule dict.

    For fixed-type schedules the resolved times equal the stored times.
    For sun-based schedules (sunrise/sunset) the times are computed
    dynamically for today using the configured location.
    """
    from src.api_server import get_settings_service  # patched-in-tests seam — see module docstring (#1756)

    start_type = schedule_dict.get("start_type", "fixed")
    end_type = schedule_dict.get("end_type", "fixed")

    if start_type == "fixed" and end_type == "fixed":
        schedule_dict["resolved_start_time"] = schedule_dict["start_time"]
        schedule_dict["resolved_end_time"] = schedule_dict.get("end_time")
        return schedule_dict

    from .sun_times import (
        get_effective_timezone,
        get_today_in_timezone,
        resolve_schedule_sun_times,
    )

    settings = get_settings_service()
    loc = settings.get_location_settings()
    timezone_str = get_effective_timezone()

    resolved_start, resolved_end = resolve_schedule_sun_times(
        start_type=start_type,
        start_sun_offset=schedule_dict.get("start_sun_offset", 0),
        start_time_fallback=schedule_dict["start_time"],
        end_type=end_type,
        end_sun_offset=schedule_dict.get("end_sun_offset", 0),
        end_time_fallback=schedule_dict.get("end_time"),
        latitude=loc.latitude,
        longitude=loc.longitude,
        target_date=get_today_in_timezone(timezone_str),
        timezone_str=timezone_str,
    )
    schedule_dict["resolved_start_time"] = resolved_start
    schedule_dict["resolved_end_time"] = resolved_end
    return schedule_dict


@router.get("/schedules")
async def list_schedules(board_id: str | None = None):
    """List schedule entries, optionally for one board (query: board_id=).

    Use board_id=* to get ALL schedules across all boards (useful for cleanup/admin).
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        get_schedule_service,
        get_settings_service,
    )

    schedule_service = get_schedule_service()
    settings_service = get_settings_service()
    schedules = schedule_service.list_schedules(board_id=board_id)

    # When listing all boards (board_id="*"), default_page_id and enabled don't make sense
    if board_id == "*":
        return {
            "schedules": [_enrich_schedule_with_sun_times(s.model_dump()) for s in schedules],
            "total": len(schedules),
            "default_page_id": None,
            "enabled": False,
        }

    return {
        "schedules": [_enrich_schedule_with_sun_times(s.model_dump()) for s in schedules],
        "total": len(schedules),
        "default_page_id": schedule_service.get_default_page(board_id=board_id),
        "enabled": settings_service.is_schedule_enabled(board_id=board_id),
    }


def _with_compat_warnings(response: dict, schedule) -> dict:
    """Attach non-fatal page<->board size warnings to a schedule response.

    Collections may mix page sizes; the write is allowed when at least one
    member fits the board, and the members that don't fit are surfaced as a
    ``warnings`` list (issue #1245). The key is omitted when there is nothing
    to warn about.
    """
    from src.api_server import check_ref_board_compatibility  # patched-in-tests seam — see module docstring (#1756)

    compat = check_ref_board_compatibility(schedule.page_id, schedule.board_id)
    if compat.ok and compat.warnings:
        response["warnings"] = compat.warnings
    return response


@router.post("/schedules")
async def create_schedule(schedule_data: ScheduleCreate):
    """Create a new schedule entry.

    Args:
        schedule_data: Schedule configuration

    Returns:
        Created schedule entry
    """
    from src.api_server import get_schedule_service  # patched-in-tests seam — see module docstring (#1756)

    schedule_service = get_schedule_service()

    try:
        schedule = schedule_service.create_schedule(schedule_data)
        response = _enrich_schedule_with_sun_times(schedule.model_dump())
        return _with_compat_warnings(response, schedule)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# Specific routes must come BEFORE parameterized routes
# to avoid /schedules/{schedule_id} matching everything


@router.get("/schedules/active/page")
async def get_active_schedule(board_id: str | None = None):
    """Get the currently active page based on schedule (optional query: board_id=)."""
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        _resolve_active_page_id,
        _resolve_next_check_seconds,
        _temporary_override_payload,
        get_schedule_service,
        get_settings_service,
    )

    schedule_service = get_schedule_service()
    settings_service = get_settings_service()

    # Include temporary override status so the frontend can show the countdown badge
    # without a separate API call.
    override = settings_service.get_temporary_override()
    temporary_override_payload = _temporary_override_payload(override)

    if not settings_service.is_schedule_enabled(board_id=board_id):
        manual_page_id = settings_service.get_active_page_id()
        return {
            "page_id": manual_page_id,
            "resolved_page_id": _resolve_active_page_id(manual_page_id),
            "resolved_next_check_seconds": _resolve_next_check_seconds(manual_page_id),
            "source": "manual",
            "schedule_enabled": False,
            "temporary_override": temporary_override_payload,
        }
    from src.time_service import get_time_service

    time_service = get_time_service()
    now = time_service.get_current_time()
    current_time = now.time()
    current_day = now.strftime("%A").lower()
    page_id = schedule_service.get_active_page_id(current_time, current_day, board_id=board_id)
    return {
        "page_id": page_id,
        "resolved_page_id": _resolve_active_page_id(page_id),
        "resolved_next_check_seconds": _resolve_next_check_seconds(page_id),
        "source": "schedule" if page_id else "none",
        "schedule_enabled": True,
        "current_time": now.strftime("%H:%M"),
        "current_day": current_day,
        "default_page_id": schedule_service.get_default_page(board_id=board_id),
        "temporary_override": temporary_override_payload,
    }


@router.post("/schedules/validate")
async def validate_schedules(request: dict | None = Body(None)):
    """Validate schedules for overlaps and gaps. Body optional: {"board_id": "..."}."""
    from src.api_server import get_schedule_service  # patched-in-tests seam — see module docstring (#1756)

    schedule_service = get_schedule_service()
    board_id = request.get("board_id") if request else None
    result = schedule_service.validate_schedules(board_id=board_id)
    return result.model_dump()


@router.get("/schedules/default-page")
async def get_default_page(board_id: str | None = None):
    """Get the default page ID for schedule gaps (optional query: board_id=)."""
    from src.api_server import get_schedule_service  # patched-in-tests seam — see module docstring (#1756)

    schedule_service = get_schedule_service()
    return {"default_page_id": schedule_service.get_default_page(board_id=board_id)}


@router.put("/schedules/default-page")
async def set_default_page(request: dict):
    """Set the default page ID for schedule gaps. Body: page_id, optional board_id."""
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        get_collection_service,
        get_page_service,
        get_schedule_service,
        is_collection_id,
    )

    if "page_id" not in request:
        raise HTTPException(status_code=400, detail="page_id parameter required")
    page_id = request["page_id"]
    board_id = request.get("board_id")
    if page_id is not None:
        if is_collection_id(page_id):
            collection_service = get_collection_service()
            if not collection_service.get_collection(page_id):
                raise HTTPException(status_code=404, detail=f"Collection not found: {page_id}")
        else:
            page_service = get_page_service()
            if not page_service.get_page(page_id):
                raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    schedule_service = get_schedule_service()
    schedule_service.set_default_page(page_id, board_id=board_id)
    return {"status": "success", "default_page_id": page_id}


@router.get("/schedules/enabled")
async def get_schedule_enabled(board_id: str | None = None):
    """Check if schedule mode is enabled (optional query: board_id=)."""
    from src.api_server import get_settings_service  # patched-in-tests seam — see module docstring (#1756)

    settings_service = get_settings_service()
    return {"enabled": settings_service.is_schedule_enabled(board_id=board_id)}


@router.put("/schedules/enabled")
async def set_schedule_enabled(request: dict):
    """Enable or disable schedule mode. Body: enabled, optional board_id."""
    from src.api_server import get_settings_service  # patched-in-tests seam — see module docstring (#1756)

    if "enabled" not in request:
        raise HTTPException(status_code=400, detail="enabled parameter required")
    enabled = request["enabled"]
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="enabled must be boolean")
    board_id = request.get("board_id")
    settings_service = get_settings_service()
    settings_service.set_schedule_enabled(enabled, board_id=board_id)
    return {
        "status": "success",
        "enabled": enabled,
        "message": f"Schedule mode {'enabled' if enabled else 'disabled'}",
    }


# Parameterized routes come LAST to avoid matching specific paths


@router.get("/schedules/{schedule_id}")
async def get_schedule(schedule_id: str):
    """Get a schedule entry by ID.

    Args:
        schedule_id: Schedule ID

    Returns:
        Schedule entry
    """
    from src.api_server import get_schedule_service  # patched-in-tests seam — see module docstring (#1756)

    schedule_service = get_schedule_service()
    schedule = schedule_service.get_schedule(schedule_id)

    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {schedule_id}")

    return _enrich_schedule_with_sun_times(schedule.model_dump())


@router.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, schedule_data: ScheduleUpdate):
    """Update an existing schedule entry.

    Args:
        schedule_id: Schedule ID
        schedule_data: Fields to update

    Returns:
        Updated schedule entry
    """
    from src.api_server import get_schedule_service  # patched-in-tests seam — see module docstring (#1756)

    schedule_service = get_schedule_service()

    try:
        schedule = schedule_service.update_schedule(schedule_id, schedule_data)
        if not schedule:
            raise HTTPException(status_code=404, detail=f"Schedule not found: {schedule_id}")
        response = _enrich_schedule_with_sun_times(schedule.model_dump())
        return _with_compat_warnings(response, schedule)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a schedule entry.

    Args:
        schedule_id: Schedule ID

    Returns:
        Success status
    """
    from src.api_server import get_schedule_service  # patched-in-tests seam — see module docstring (#1756)

    schedule_service = get_schedule_service()

    deleted = schedule_service.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {schedule_id}")

    return {"status": "success", "message": f"Schedule {schedule_id} deleted"}
