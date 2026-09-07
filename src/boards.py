"""The board directory: the one place a board id is resolved, or refused.

Boards live in ``settings.boards``. Every router needs to answer two questions
about a ``board_id`` a client sent — "which board is this?" and "does it exist
at all?" — and before #1888 nine handlers open-coded the second one while four
schedule write endpoints simply skipped it and persisted state bound to a board
that does not exist.

Both functions lived in ``src/api_server.py``, which meant a domain router could
only reach them by importing the 10k-line app module *at call time* — the seam
Phase 2 §2.3 retires. They are platform helpers, not app-factory internals, so
they live here.

**The settings service is a parameter, not a global.** Every caller already
holds one, and passing it keeps the lookup resolving through whichever
``get_settings_service`` the *calling module* binds — which is what lets a test
stub one router's settings without reaching into this module. A hidden
``get_settings_service()`` here would silently detach the board lookup from
every existing per-module stub.

``require_board`` raises ``HTTPException`` rather than a domain error on
purpose: it exists to make the HTTP "unknown board" verdict in exactly one
place, and every caller is a request handler.

**Writes 404, reads fall back** — see the "board_id validation" note in
``docs/internal/reference/API_CONVENTIONS.md``. Call ``require_board`` on any
path that persists something scoped to a board; board-scoped reads answer their
safe default instead.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def find_board(board_id: str | None, settings_service: Any) -> dict | None:
    """Return the ``settings.boards`` entry for *board_id*, or None (issue #1244)."""
    try:
        boards = settings_service.get_board_settings().boards or []
    except Exception as exc:
        logger.debug("Could not read boards list: %s", exc)
        return None
    for board in boards:
        if isinstance(board, dict) and board.get("id") == board_id:
            return board
    return None


def require_board(board_id: str, settings_service: Any) -> dict:
    """Return the ``settings.boards`` entry for *board_id*, or raise 404.

    The single place the "unknown board" verdict is made. The pattern was
    open-coded in nine handlers and simply missing from four schedule write
    endpoints, which persisted state bound to a board that does not exist and
    reported success (#1888).
    """
    board = find_board(board_id, settings_service)
    if board is None:
        raise HTTPException(status_code=404, detail=f"Board not found: {board_id}")
    return board
