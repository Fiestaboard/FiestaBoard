"""Put one board inside its silence window for a test (issues #1943, #1944).

``silenced()`` patches the three things a silence decision reads — whether the
window is active, the board's resolved schedule (for ``show_queued_on_exit``)
and when the window ends — so a route test can drive the REAL
``src.board_guards.silence_verdict`` instead of stubbing it.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest import mock

ENDS_AT = "2026-10-18T07:00:00+00:00"


@contextmanager
def silenced(*, holds: bool = False, board: str | None = None, ends_at: str | None = ENDS_AT):
    """Silence *board* (every board when ``None``); ``holds`` = show_queued_on_exit."""
    from src.config import Config

    real_config_for = Config.silence_config_for.__func__

    def active(board_id=None):
        return board is None or board_id == board

    def config_for(cls, board_id=None):
        resolved = real_config_for(cls, board_id)
        if active(board_id):
            resolved = {**resolved, "enabled": True, "show_queued_on_exit": holds}
        return resolved

    with (
        mock.patch.object(Config, "is_silence_mode_active", side_effect=active),
        mock.patch.object(Config, "silence_config_for", classmethod(config_for)),
        mock.patch("src.board_guards.silence_window_end", return_value=ends_at),
    ):
        yield
