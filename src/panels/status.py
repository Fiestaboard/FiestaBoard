"""The read-only status of a panel's board, for a TV viewer's status chip (H13).

Built from the same sources the display loop (``src/main.py``) acts on, so
the chip never claims a state the board is not in:

* **override** — the temporary-override store drives the *primary* board
  only today, so a panel on any other board never reports one. Per-display
  overrides are a separate ticket (H1); when they land, this is the one place
  to change.
* **silence** — :func:`src.board_guards.silence_verdict`'s own inputs:
  ``Config.is_silence_mode_active`` and the board's resolved silence schedule.
* **pause** and the **schedule switch** — the per-board settings.

Every read here is a pure read: nothing is written, nothing is consumed. In
particular an expired override is left in the store for the display loop,
which applies its revert when it finds it.

Every instant is reported as ``YYYY-MM-DDTHH:MM:SS+00:00`` (UTC, whole
seconds), so the status is identical between polls while nothing changes.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from src import board_guards
from src.config import Config
from src.settings.service import get_settings_service

from .models import PanelStatus

logger = logging.getLogger(__name__)


def _override_for(board_id: str):
    """The live override driving *board_id*, or ``None``.

    Reads through :meth:`SettingsService.peek_temporary_override`, never
    ``get_temporary_override()``: that one clears and saves an *expired*
    override, and the display loop needs to find the expired override to
    apply its ``revert_mode`` (``blank`` / ``page``). A TV polls this every
    10 s, so it would almost always get there first.
    """
    settings_service = get_settings_service()
    override = settings_service.peek_temporary_override(board_id)
    if override is None or override.is_expired():
        return None
    return override


def _instant(value: str | None, *, to_minute: bool = False) -> str | None:
    """*value* as ``YYYY-MM-DDTHH:MM:SS+00:00``: UTC, whole seconds.

    One shape for every instant in the status, which Swift's ``.iso8601``
    decoder accepts (it rejects fractional seconds), and which stays equal
    between polls. An instant that does not parse is passed through.

    ``to_minute`` is for the silence window's end. Silence boundaries are
    configured to the minute (``HH:MM``), but
    :func:`src.board_guards.silence_timing` reports the boundary as ``now +
    whole seconds``, which lands up to a second either side of it and moves
    on every call. Rounding to the nearest minute recovers the exact
    boundary.
    """
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    if to_minute:
        parsed = (parsed + timedelta(seconds=30)).replace(second=0)
    return parsed.replace(microsecond=0).isoformat()


def panel_status(board_id: str) -> PanelStatus:
    """What *board_id* is doing right now, as a viewer reports it."""
    settings_service = get_settings_service()
    override = _override_for(board_id)
    schedule_enabled = settings_service.is_schedule_enabled(board_id=board_id) is True

    silenced = Config.is_silence_mode_active(board_id) is True
    silenced_until = _instant(board_guards.silence_window_end(board_id), to_minute=True) if silenced else None
    silence_mode = None
    if silenced:
        try:
            silence_mode = Config.silence_config_for(board_id).get("mode")
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Could not resolve the silence mode for %s: %s", board_id, e)

    if override is not None:
        mode = "override"
    elif schedule_enabled:
        mode = "schedule"
    else:
        mode = "manual"

    return PanelStatus(
        mode=mode,
        schedule_enabled=schedule_enabled,
        override_active=override is not None,
        override_expires_at=_instant(override.expires_at) if override is not None else None,
        override_started_at=_instant(override.started_at) if override is not None else None,
        silenced=silenced,
        silenced_until=silenced_until,
        silence_mode=silence_mode,
        paused=settings_service.is_paused(board_id=board_id) is True,
        **_next_change(board_id),
    )


def _next_change(board_id: str) -> dict:
    """H2's next change for the board, in panel status's instant shape (H2b).

    No page id: a TV holds the tv_panels scope and cannot name a page.
    """
    from src.schedules.next_change import next_change

    change = next_change(board_id)
    return {"next_change_at": _instant(change.at), "next_change_reason": change.reason}
