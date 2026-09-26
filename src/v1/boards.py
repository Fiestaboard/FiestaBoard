"""Board addressing for the ``/v1`` surface.

The one concept v1 adds over the internal API: ``{board}`` accepts either a
board id **or** the literal ``primary``. A single-board owner never has to
learn that boards have ids, and a multi-board owner never has to guess which
one an id-less endpoint meant — the internal surface's oldest ergonomic
defect (``POST /send-message`` has no ``board_id`` at all, so board 2 is
unreachable over HTTP today).

Nothing here is new domain logic: ``primary`` resolves through
``SettingsService.get_primary_board_id()`` and every id resolves through
``src.board_guards._require_board``, which is the single place in the
codebase that makes the "unknown board" verdict.
"""

from __future__ import annotations

from fastapi import HTTPException

from src.board_guards import _board_dims, _require_board, get_settings_service

#: The alias every v1 board path accepts in place of a real board id.
PRIMARY_ALIAS = "primary"


def resolve_board_id(board: str) -> str:
    """Turn a ``{board}`` path segment into a concrete board id.

    ``primary`` resolves to the install's primary board; anything else is
    taken as a board id and validated. Raises 404 for an unknown id and 404
    for ``primary`` on an install with no board configured yet — a caller
    that cannot address any board gets the same verdict either way.
    """
    if board == PRIMARY_ALIAS:
        primary_id = get_settings_service().get_primary_board_id()
        if not primary_id:
            raise HTTPException(status_code=404, detail="No board is configured on this install.")
        return primary_id
    _require_board(board)
    return board


def resolve_board(board: str) -> tuple[str, dict]:
    """``(board_id, board_entry)`` for a ``{board}`` path segment."""
    board_id = resolve_board_id(board)
    return board_id, _require_board(board_id)


def board_dimensions(board_entry: dict):
    """Resolved ``rows``/``cols`` for a board entry (never raises)."""
    return _board_dims(board_entry)
