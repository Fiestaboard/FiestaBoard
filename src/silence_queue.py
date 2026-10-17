"""Last message blocked by the silence window, per board (issue #1944).

When a board's silence schedule has ``show_queued_on_exit`` enabled, a manual
send refused during the window is remembered here (the most recent one wins)
and delivered by the display engine the moment the window ends.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_queued: dict[str, str] = {}


def _key(board_id: str | None) -> str:
    return board_id or ""


def queue_message(board_id: str | None, text: str) -> None:
    """Remember ``text`` as the latest blocked send for ``board_id``."""
    with _lock:
        _queued[_key(board_id)] = text


def pop_message(board_id: str | None) -> str | None:
    """Take (and forget) the queued text for ``board_id``, if any."""
    with _lock:
        return _queued.pop(_key(board_id), None)


def clear() -> None:
    """Drop every queued message (tests)."""
    with _lock:
        _queued.clear()
