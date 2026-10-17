"""``/v1/install`` — the settings that describe the install rather than a board.

``schedule_enabled`` and ``default_page_id`` are readable and writable with
*no board at all* on the internal API (``GET/PUT /schedules/enabled`` and
``GET/PUT /schedules/default-page`` with ``board_id`` omitted). Every other
``/v1`` path is scoped under ``/boards/{board}``, so without this resource
those four routes could not be retired (#2073, blocking #1941).

The resource is a thin adapter: it calls the same setters with
``board_id=None``, so it answers exactly what the board-less internal routes
answer today. Per-board values stay on ``PATCH /v1/boards/{board}``; this is
the install-level fallback, not a second copy of them.

Shape: a singleton read with ``GET`` and changed with a partial ``PATCH`` —
the same verbs and the same "only the fields you send are applied" rule as
``/v1/boards/{board}`` and ``/v1/plugins/{plugin_id}``.
"""

from __future__ import annotations

from src.api_errors import errors

from .models import InstallSettings, InstallUpdate
from .router import router
from .routes_boards import _require_page_ref, _schedule_service, _settings_service


def _read() -> InstallSettings:
    return InstallSettings(
        schedule_enabled=bool(_settings_service().is_schedule_enabled(board_id=None)),
        default_page_id=_schedule_service().get_default_page(board_id=None),
    )


@router.get(
    "/install",
    response_model=InstallSettings,
    responses=errors(503),
    summary="Read the install's own settings",
    description=(
        "Settings that belong to the install rather than to one board: whether the schedule is on and the "
        "install-wide page shown when the schedule has a gap. A board's own values are on "
        "`GET /v1/boards/{board}`."
    ),
)
async def get_install() -> InstallSettings:
    return _read()


@router.patch(
    "/install",
    response_model=InstallSettings,
    responses=errors(404, 503),
    summary="Change the install's own settings",
    description=(
        "Turn the install's schedule on or off, or set the install-wide page shown when the schedule has a gap. "
        "Only the fields you send are applied; omit the rest. Send `default_page_id: null` to clear it. To change "
        "one board, use `PATCH /v1/boards/{board}`."
    ),
)
async def update_install(request: InstallUpdate) -> InstallSettings:
    provided = request.model_dump(exclude_unset=True)

    if provided.get("schedule_enabled") is not None:
        _settings_service().set_schedule_enabled(provided["schedule_enabled"], board_id=None)

    if "default_page_id" in provided:
        page_id = provided["default_page_id"]
        if page_id is not None:
            _require_page_ref(page_id)
        _schedule_service().set_default_page(page_id, board_id=None)

    return _read()
