"""FastAPI router for the schedule endpoints.

Handlers were moved here verbatim from ``src/api_server.py`` (issue #1756);
Phase 2 slice 2 then applied ``docs/internal/reference/API_CONVENTIONS.md`` to
them and retired the call-time ``from src.api_server import ...`` seams the
move left behind.

Collaborators now resolve from their canonical homes at **module import time**,
so this module never loads ``src.api_server``
(``tests/test_schedules_decoupled.py`` asserts that in a fresh interpreter).
Three of them had no canonical home before this pass and were moved out of the
app module to get one: ``_require_board`` (``src/board_guards.py``),
``resolve_active_page_id`` / ``resolve_next_check_seconds``
(``src/collections/service.py``) and ``temporary_override_payload``
(``src/settings/service.py``).

``_require_board`` briefly lived in a second module, ``src/boards.py``, which
took the settings service as a parameter while ``src/board_guards.py`` resolved
it through its own module-level accessor — two seam designs for one identical
lookup, and the reason a fixture could stub ``src.board_guards`` and steer
nothing. The parameter form is gone; this router resolves the board verdict
through ``src.board_guards`` like every other domain, so one stub covers them
all.

Tests that need to stub a collaborator patch it where this module binds it —
``src.schedules.routes.<name>`` — not ``src.api_server.<name>``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api_errors import errors
from src.board_guards import _require_board
from src.collections.models import is_collection_id
from src.collections.service import (
    get_collection_service,
    resolve_active_page_id,
    resolve_next_check_seconds,
)
from src.pages.service import check_ref_board_compatibility, get_page_service
from src.settings.service import get_settings_service, temporary_override_payload
from src.time_service import get_time_service

from .models import (
    ActiveScheduleResponse,
    DefaultPageResponse,
    DefaultPageUpdate,
    ScheduleCreate,
    ScheduleDeleteResponse,
    ScheduleEnabledResponse,
    ScheduleEnabledUpdate,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleUpdate,
    ScheduleValidateRequest,
    ScheduleValidationResult,
    ScheduleWriteResponse,
)
from .service import get_schedule_service

router = APIRouter(tags=["schedules"])


def _validate_board(board_id: str | None) -> None:
    """404 when *board_id* names a board that does not exist.

    ``None`` and ``""`` mean "the default/primary board" (``DEFAULT_BOARD_ID``
    is ``""``) and are passed through untouched.

    Every schedule *write* runs this. Before #1888 all four write endpoints
    took a free-form board id: ``PUT /schedules/default-page`` stored a
    phantom default, ``PUT /schedules/enabled`` was a logged no-op that
    reported success, and ``POST``/``PUT /schedules/{id}`` persisted a
    schedule parented to a nonexistent board because
    ``check_ref_board_compatibility`` passes silently on an unknown board.
    Board-scoped *reads* deliberately still fall back — see
    ``docs/internal/reference/API_CONVENTIONS.md``.
    """
    if not board_id:
        return
    _require_board(board_id)


def _enrich_schedule_with_sun_times(schedule_dict: dict) -> dict:
    """Add resolved_start_time / resolved_end_time to a schedule dict.

    For fixed-type schedules the resolved times equal the stored times.
    For sun-based schedules (sunrise/sunset) the times are computed
    dynamically for today using the configured location.
    """
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


def _with_compat_warnings(response: dict, schedule) -> dict:
    """Attach non-fatal page<->board size warnings to a schedule response.

    Collections may mix page sizes; the write is allowed when at least one
    member fits the board, and the members that don't fit are surfaced as a
    ``warnings`` list (issue #1245). The list is empty when there is nothing
    to warn about — the key is always present so a client can tell "no
    warnings" from "no warnings reported".
    """
    compat = check_ref_board_compatibility(schedule.page_id, schedule.board_id)
    response["warnings"] = list(compat.warnings) if (compat.ok and compat.warnings) else []
    return response


@router.get("/schedules", response_model=ScheduleListResponse)
async def list_schedules(board_id: str | None = None):
    """List schedule entries, optionally for one board (query: board_id=).

    Use board_id=* to get ALL schedules across all boards (useful for cleanup/admin).
    """
    schedule_service = get_schedule_service()
    settings_service = get_settings_service()
    schedules = schedule_service.list_schedules(board_id=board_id)
    entries = [_enrich_schedule_with_sun_times(s.model_dump()) for s in schedules]

    # When listing all boards (board_id="*") the two per-board fields have no
    # answer, so both are null. `enabled` used to be hardcoded `False`, which a
    # client cannot tell apart from "schedule mode is off on every board" — it
    # said `false` even with schedule mode on for the only board. `null` is the
    # honest "not applicable to this listing", and matches what the same branch
    # has always answered for `default_page_id`.
    if board_id == "*":
        return ScheduleListResponse(schedules=entries, total=len(schedules))

    return ScheduleListResponse(
        schedules=entries,
        total=len(schedules),
        default_page_id=schedule_service.get_default_page(board_id=board_id),
        enabled=settings_service.is_schedule_enabled(board_id=board_id),
    )


@router.post(
    "/schedules",
    response_model=ScheduleWriteResponse,
    status_code=201,
    responses=errors(400, 404),
)
async def create_schedule(schedule_data: ScheduleCreate):
    """Create a new schedule entry."""
    _validate_board(schedule_data.board_id)

    schedule_service = get_schedule_service()

    try:
        schedule = schedule_service.create_schedule(schedule_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    response = _enrich_schedule_with_sun_times(schedule.model_dump())
    return _with_compat_warnings(response, schedule)


# Specific routes must come BEFORE parameterized routes
# to avoid /schedules/{schedule_id} matching everything


@router.get("/schedules/active/page", response_model=ActiveScheduleResponse)
async def get_active_schedule(board_id: str | None = None):
    """Get the currently active page based on schedule (optional query: board_id=)."""
    schedule_service = get_schedule_service()
    settings_service = get_settings_service()

    # Include temporary override status so the frontend can show the countdown badge
    # without a separate API call.
    override = settings_service.get_temporary_override()
    override_payload = temporary_override_payload(override)

    if not settings_service.is_schedule_enabled(board_id=board_id):
        manual_page_id = settings_service.get_active_page_id()
        return ActiveScheduleResponse(
            page_id=manual_page_id,
            resolved_page_id=resolve_active_page_id(manual_page_id, get_collection_service),
            resolved_next_check_seconds=resolve_next_check_seconds(manual_page_id, get_collection_service),
            source="manual",
            schedule_enabled=False,
            temporary_override=override_payload,
        )

    time_service = get_time_service()
    now = time_service.get_current_time()
    current_time = now.time()
    current_day = now.strftime("%A").lower()
    page_id = schedule_service.get_active_page_id(current_time, current_day, board_id=board_id)
    return ActiveScheduleResponse(
        page_id=page_id,
        resolved_page_id=resolve_active_page_id(page_id, get_collection_service),
        resolved_next_check_seconds=resolve_next_check_seconds(page_id, get_collection_service),
        source="schedule" if page_id else "none",
        schedule_enabled=True,
        current_time=now.strftime("%H:%M"),
        current_day=current_day,
        default_page_id=schedule_service.get_default_page(board_id=board_id),
        temporary_override=override_payload,
    )


@router.post("/schedules/validate", response_model=ScheduleValidationResult)
async def validate_schedules(request: ScheduleValidateRequest | None = None):
    """Validate schedules for overlaps and gaps. Body optional: {"board_id": "..."}.

    A ``valid: false`` verdict is a 200: the caller asked "are these schedules
    consistent?" and got the answer it asked for, in a declared response model
    — the probe-endpoint case of API_CONVENTIONS.md §status codes, not a
    failure served as a success.
    """
    schedule_service = get_schedule_service()
    board_id = request.board_id if request else None
    return schedule_service.validate_schedules(board_id=board_id)


@router.get("/schedules/default-page", response_model=DefaultPageResponse)
async def get_default_page(board_id: str | None = None):
    """Get the default page ID for schedule gaps (optional query: board_id=)."""
    schedule_service = get_schedule_service()
    return DefaultPageResponse(default_page_id=schedule_service.get_default_page(board_id=board_id))


@router.put(
    "/schedules/default-page",
    response_model=DefaultPageResponse,
    responses=errors(404),
)
async def set_default_page(request: DefaultPageUpdate):
    """Set the default page ID for schedule gaps. Body: page_id, optional board_id."""
    page_id = request.page_id
    board_id = request.board_id
    _validate_board(board_id)
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
    return DefaultPageResponse(default_page_id=page_id)


@router.get("/schedules/enabled", response_model=ScheduleEnabledResponse)
async def get_schedule_enabled(board_id: str | None = None):
    """Check if schedule mode is enabled (optional query: board_id=)."""
    settings_service = get_settings_service()
    return ScheduleEnabledResponse(enabled=settings_service.is_schedule_enabled(board_id=board_id))


@router.put(
    "/schedules/enabled",
    response_model=ScheduleEnabledResponse,
    responses=errors(404),
)
async def set_schedule_enabled(request: ScheduleEnabledUpdate):
    """Enable or disable schedule mode. Body: enabled, optional board_id."""
    _validate_board(request.board_id)
    settings_service = get_settings_service()
    settings_service.set_schedule_enabled(request.enabled, board_id=request.board_id)
    return ScheduleEnabledResponse(enabled=request.enabled)


# Parameterized routes come LAST to avoid matching specific paths


@router.get(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    responses=errors(404),
)
async def get_schedule(schedule_id: str):
    """Get a schedule entry by ID."""
    schedule_service = get_schedule_service()
    schedule = schedule_service.get_schedule(schedule_id)

    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {schedule_id}")

    return _enrich_schedule_with_sun_times(schedule.model_dump())


@router.put(
    "/schedules/{schedule_id}",
    response_model=ScheduleWriteResponse,
    responses=errors(400, 404),
)
async def update_schedule(schedule_id: str, schedule_data: ScheduleUpdate):
    """Update an existing schedule entry."""
    _validate_board(schedule_data.board_id)

    schedule_service = get_schedule_service()

    try:
        schedule = schedule_service.update_schedule(schedule_id, schedule_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {schedule_id}")
    response = _enrich_schedule_with_sun_times(schedule.model_dump())
    return _with_compat_warnings(response, schedule)


@router.delete(
    "/schedules/{schedule_id}",
    response_model=ScheduleDeleteResponse,
    responses=errors(404),
)
async def delete_schedule(schedule_id: str):
    """Delete a schedule entry."""
    schedule_service = get_schedule_service()

    deleted = schedule_service.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {schedule_id}")

    return ScheduleDeleteResponse(id=schedule_id)
