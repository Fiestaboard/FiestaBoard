"""What a display's schedule says at a given instant (H8).

``GET /schedules/active/page?at=`` and the collection dry run answer for an
instant other than now. Everything here is a pure read of today's
configuration evaluated at that instant: the schedule and the manual pin as
they are set now, the H1 override as it runs now, the quiet-hours window,
and a collection's own selection logic with the formula clock pinned to the
instant. Nothing is stored and no board is touched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from src import time_service

#: How far from now an instant may be asked about: a dated schedule entry
#: repeats within a year.
MAX_AT_DAYS = 366


def instant(at: datetime) -> tuple[datetime, datetime]:
    """*at* as ``(hub-local, UTC)``. Naive means the hub's timezone.

    Raises ``ValueError`` when it is more than :data:`MAX_AT_DAYS` from now.
    """
    from src.templates.preview import hub_instant

    local = hub_instant(at)
    if local.tzinfo is None:  # a hub without a configured zone
        local = local.astimezone()
    as_utc = local.astimezone(UTC)
    if abs(as_utc - datetime.now(UTC)) > timedelta(days=MAX_AT_DAYS):
        raise ValueError(f"at must be within {MAX_AT_DAYS} days of now")
    return local, as_utc


def stamp(value: datetime) -> str:
    """UTC, whole seconds: the shape of every instant the hub reports."""
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def silenced_at(board_id: str | None, at_utc: datetime) -> bool:
    """Whether *board_id*'s quiet hours cover *at_utc*: the window arithmetic
    of :func:`src.board_guards.silence_timing`, at that instant."""
    from src.config import Config

    config = Config.silence_config_for(board_id) or {}
    if not config.get("enabled"):
        return False
    service = time_service.get_time_service()
    start = service.parse_iso_time(config.get("start_time") or "")
    end = service.parse_iso_time(config.get("end_time") or "")
    if start is None or end is None:
        return False
    now, start_t, end_t = at_utc.astimezone(UTC).time(), start.time(), end.time()
    if start_t > end_t:  # spans midnight
        return now >= start_t or now <= end_t
    return start_t <= now <= end_t


def override_at(override: Any, at_utc: datetime) -> Any:
    """*override* if it will (still) be running at *at_utc*, else ``None``.

    One that started after *at_utc*, or will have expired by then, is not in
    force; one with no expiry runs until cancelled.
    """
    if override is None:
        return None
    started = _parse(getattr(override, "started_at", None))
    if started is not None and started > at_utc:
        return None
    ends = _parse(getattr(override, "expires_at", None))
    if ends is not None and ends <= at_utc:
        return None
    return override


def remaining_at(override: Any, at_utc: datetime) -> int | None:
    """Seconds *override* has left at *at_utc*; ``None`` without an expiry."""
    ends = _parse(getattr(override, "expires_at", None))
    return None if ends is None else max(0, int((ends - at_utc).total_seconds()))


def resolve_at(
    ref: str | None, board_id: str | None, local: datetime, collections: Any = None
) -> tuple[str | None, int | None]:
    """``(resolved page, seconds until it may change)`` for *ref* at *local*.

    A plain page is itself. A collection runs its own logic at that instant:
    time and random modes are functions of the clock; variable mode evaluates
    its rules with the formula clock pinned to *local* against the hub's
    current data. A device-driven (native) collection is ``(None, None)``:
    the device's buttons decide, not the hub's clock.
    """
    from src.collections.models import is_collection_id
    from src.display_runtime import native_page_selection
    from src.templates.expressions import RENDER_CLOCK_KEY

    if not is_collection_id(ref):
        return ref, None
    if native_page_selection(ref, board_id) is not None:
        return None, None
    if collections is None:
        from src.collections.service import get_collection_service as collections
    service = collections()
    stamp_unix = local.timestamp()
    resolved = service.resolve_page_id(
        ref,
        now_unix=stamp_unix,
        context_factory=lambda: {**service._build_variable_context(), RENDER_CLOCK_KEY: local},
    )
    return resolved, service.seconds_until_next_check(ref, now_unix=stamp_unix)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def active_page(
    board_id: str | None, at: datetime | None, *, settings: Any, schedules: Any, clock: Any, collections: Any
) -> dict[str, Any]:
    """``GET /schedules/active/page``'s answer for now, or for *at* (see its docstring).

    The services come from the router (its import-time seams); *collections*
    is the collection-service accessor. Raises ``ValueError`` for an *at* more
    than :data:`MAX_AT_DAYS` from now.
    """
    from src.settings.service import temporary_override_payload

    local, at_utc = instant(at) if at is not None else (clock.get_current_time(), None)

    # Only a real board's override: an unknown id (including the store's
    # internal "__primary__" key) has none, rather than reaching the primary's.
    known = not board_id or any(b.get("id") == board_id for b in settings.get_board_settings().boards or [])
    override = settings.get_temporary_override(board_id) if known else None
    if at_utc is not None:
        override = override_at(override, at_utc)
    payload = temporary_override_payload(override, board_id or settings.get_primary_board_id())
    if at_utc is not None and override is not None:
        payload["remaining_seconds"] = remaining_at(override, at_utc)
    answer: dict[str, Any] = {
        "temporary_override": payload,
        "at": stamp(at_utc) if at_utc is not None else None,
        "silenced": silenced_at(board_id, at_utc if at_utc is not None else datetime.now(UTC)),
    }

    if not settings.is_schedule_enabled(board_id=board_id):
        ref = settings.get_active_page_id(board_id=board_id)
        resolved, next_check = _resolved(ref, board_id, local if at_utc is not None else None, collections)
        return {
            **answer,
            "page_id": ref,
            "resolved_page_id": resolved,
            "resolved_next_check_seconds": next_check,
            "source": "manual",
            "schedule_enabled": False,
        }

    day = local.strftime("%A").lower()
    dated = {"on_date": local.date()} if at_utc is not None else {}
    ref = schedules.get_active_page_id(local.time(), day, board_id=board_id, **dated)
    resolved, next_check = _resolved(ref, board_id, local if at_utc is not None else None, collections)
    return {
        **answer,
        "page_id": ref,
        "resolved_page_id": resolved,
        "resolved_next_check_seconds": next_check,
        "source": "schedule" if ref else "none",
        "schedule_enabled": True,
        "current_time": local.strftime("%H:%M"),
        "current_day": day,
        "default_page_id": schedules.get_default_page(board_id=board_id),
    }


def _resolved(
    ref: str | None, board_id: str | None, local: datetime | None, collections: Any
) -> tuple[str | None, int | None]:
    """*ref* resolved now (``local`` None: the live path, unchanged) or at *local*."""
    if local is not None:
        return resolve_at(ref, board_id, local, collections)
    from src.collections.service import resolve_active_page_id, resolve_next_check_seconds

    return (
        resolve_active_page_id(ref, collections, board_id=board_id),
        resolve_next_check_seconds(ref, collections, board_id=board_id),
    )
