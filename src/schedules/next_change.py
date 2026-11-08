"""When a display is next expected to change, from the hub's own rules (H2).

``next_change(board_id)`` answers for ``GET /v1/boards/{board}``: the
earliest instant after now at which what drives the display changes, why, and
(when the hub can know it) the page in force afterwards. It follows the
engine's precedence per display:

1. a paused board takes no updates: nothing;
2. an active H1 override beats everything else: its expiry (and the
   rotation of its own collection, if it names one);
3. while silenced, the silence treatment hides the schedule: the window's end;
4. otherwise the earliest of the next schedule boundary where the page
   changes, the silence window opening, and the rotation of the collection
   in force.

Plugin triggers can take over the primary display at any moment and are
never modelled; out-of-band writes happen when someone sends them.

Schedules are wall-clock rules in the hub's configured timezone (the clock the
engine reads). A boundary that falls in a spring-forward gap is reported at
the end of the gap, the first instant the engine's clock reaches it; a
repeated fall-back time is reported at its first occurrence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Literal

from src import board_guards, time_service
from src.config import Config

#: How far ahead the schedule is searched. A weekly schedule repeats within it.
HORIZON_DAYS = 8

Reason = Literal["override_ends", "schedule", "silence_starts", "silence_ends", "collection"]

_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class NextChange:
    """``at`` is ISO 8601 UTC with whole seconds; all three are None when nothing is known."""

    at: str | None = None
    reason: Reason | None = None
    page_id: str | None = None


_NOTHING = NextChange()


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _on_the_minute(value: datetime | None) -> datetime | None:
    """*value* rounded to the nearest minute.

    Quiet hours are configured to the minute, but ``board_guards.silence_timing``
    reports the boundary as ``now + whole seconds``, which keeps now's
    microseconds and lands up to a second either side of it. Rounding recovers
    the configured minute, the same rule panel status's ``silenced_until``
    applies (``src/panels/status.py``, ``_instant(..., to_minute=True)``).
    """
    if value is None:
        return None
    return (value + timedelta(seconds=30)).replace(second=0, microsecond=0)


def wall_to_utc(wall: datetime, zone: tzinfo) -> datetime:
    """The first UTC instant at which the wall clock in *zone* reads *wall* or later.

    For a time that exists, that is the time itself (the first one when it is
    repeated at a fall-back). For a time inside a spring-forward gap, it is the
    end of the gap.
    """
    first = wall.replace(tzinfo=zone, fold=0).astimezone(UTC)
    if first.astimezone(zone).replace(tzinfo=None) == wall:
        return first
    probe = wall.replace(tzinfo=zone, fold=1).astimezone(UTC)
    while probe.astimezone(zone).replace(tzinfo=None) < wall:
        probe += timedelta(minutes=1)
    return probe


def _settings():
    from src.settings.service import get_settings_service

    return get_settings_service()


def _schedules():
    from src.schedules.service import get_schedule_service

    return get_schedule_service()


def _page_at(board_id: str, when: datetime, zone: tzinfo) -> str | None:
    """The page (or collection) reference in force at *when*, ignoring overrides and silence."""
    settings = _settings()
    if not settings.is_schedule_enabled(board_id=board_id):
        return settings.get_active_page_id(board_id=board_id)
    local = when.astimezone(zone)
    return _schedules().get_active_page_id(
        local.time(), _DAYS[local.weekday()], board_id=board_id, on_date=local.date()
    )


def _rotation(ref: str | None, board_id: str, now: datetime) -> tuple[datetime, Reason, None] | None:
    """When the collection *ref* may next rotate, or None for a plain page or a device-driven one."""
    from src.collections.models import is_collection_id

    if not ref or not is_collection_id(ref):
        return None
    from src.display_runtime import native_page_selection

    if native_page_selection(ref, board_id) is not None:
        return None  # the device's buttons and dwell decide, not the hub's clock
    from src.collections.service import get_collection_service

    seconds = get_collection_service().seconds_until_next_check(ref, now_unix=now.timestamp())
    if seconds is None:
        return None
    return now + timedelta(seconds=seconds), "collection", None


def _schedule_boundary(board_id: str, now: datetime, zone: tzinfo, current: str | None):
    """The next instant the schedule names a different page than *current*, within the horizon."""
    wall_now = now.astimezone(zone).replace(tzinfo=None)
    horizon = wall_now + timedelta(days=HORIZON_DAYS)
    schedules = _schedules()
    for edge in schedules.window_edges(board_id, wall_now.date() - timedelta(days=1), HORIZON_DAYS + 2):
        if edge <= wall_now or edge > horizon:
            continue
        page = schedules.get_active_page_id(edge.time(), _DAYS[edge.weekday()], board_id=board_id, on_date=edge.date())
        if page != current:
            return wall_to_utc(edge, zone), "schedule", page
    return None


def _after_override(override, board_id: str, at: datetime, zone: tzinfo) -> str | None:
    if override.revert_mode == "page":
        return override.revert_page_id
    if override.revert_mode == "blank":
        return None
    return _page_at(board_id, at, zone)


def _earliest(candidates) -> NextChange:
    candidates = [c for c in candidates if c is not None]
    if not candidates:
        return _NOTHING
    at, reason, page_id = min(candidates, key=lambda c: c[0])
    return NextChange(_instant(at), reason, page_id)


def next_change(board_id: str) -> NextChange:
    """When *board_id* is next expected to change, why, and to what (see the module docstring)."""
    settings = _settings()
    if settings.is_paused(board_id=board_id) is True:
        return _NOTHING

    local_now = time_service.get_time_service().get_current_time()
    zone = local_now.tzinfo
    now = local_now.astimezone(UTC)

    override = settings.peek_temporary_override(board_id)
    if override is not None and not override.is_expired():
        ends = _parse(override.expires_at)
        ending = (ends, "override_ends", _after_override(override, board_id, ends, zone)) if ends else None
        return _earliest([ending, _rotation(override.page_id, board_id, now)])

    silence = Config.silence_config_for(board_id) or {}
    timing = board_guards.silence_timing(silence) if silence.get("enabled") else None
    boundary = _on_the_minute(_parse(timing.next_change_at)) if timing else None
    if timing is not None and timing.active:
        return (
            NextChange(_instant(boundary), "silence_ends", _page_at(board_id, boundary, zone)) if boundary else _NOTHING
        )

    current = _page_at(board_id, now, zone)
    candidates = [_rotation(current, board_id, now)]
    if boundary is not None:
        silence_page = silence.get("page_id") if silence.get("mode") == "page" else None
        candidates.append((boundary, "silence_starts", silence_page))
    if settings.is_schedule_enabled(board_id=board_id):
        candidates.append(_schedule_boundary(board_id, now, zone, current))
    return _earliest(candidates)
