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

Every read here is a pure read: nothing is written, nothing is consumed.
"""

from __future__ import annotations

import logging

from src import board_guards
from src.config import Config
from src.settings.service import get_settings_service

from .models import PanelStatus

logger = logging.getLogger(__name__)


def _override_for(board_id: str):
    """The live override driving *board_id*, or ``None``."""
    settings_service = get_settings_service()
    if settings_service.get_primary_board_id() != board_id:
        return None
    return settings_service.get_temporary_override()


def panel_status(board_id: str) -> PanelStatus:
    """What *board_id* is doing right now, as a viewer reports it."""
    settings_service = get_settings_service()
    override = _override_for(board_id)
    schedule_enabled = settings_service.is_schedule_enabled(board_id=board_id) is True

    silenced = Config.is_silence_mode_active(board_id) is True
    silenced_until = board_guards.silence_window_end(board_id) if silenced else None
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
        override_expires_at=override.expires_at if override is not None else None,
        silenced=silenced,
        silenced_until=silenced_until,
        silence_mode=silence_mode,
        paused=settings_service.is_paused(board_id=board_id) is True,
    )
