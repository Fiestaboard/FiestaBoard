"""H21a: a phone never sends a display's stored secret to settings it just chose.

A phone (``control`` scope) may add, change and remove displays. Changing a
saved display's *connection* (a host, port or mode, its own or a tile's)
must not carry the stored key along: the stored key would then be sent to a
host the phone picked. The browser keeps today's rule (an echoed ``"***"``
keeps the stored secret), so this check runs for phones only.

How: the write is simulated with the same pure steps ``set_boards`` uses
(restore echoed masks, merge the two shapes, normalise). A stored secret
that survives into the result under different connection fields (see
``src/auth/key_reentry.py``), and which the request did not carry itself,
refuses the write (``key_required``).
"""

from __future__ import annotations

import copy
from typing import Any


def simulate_board_write(incoming: dict[str, Any], stored: dict[str, Any]) -> dict[str, Any]:
    """The stored board *incoming* would become, without saving anything."""
    from src.devices import BoardInstance
    from src.settings.board_shape import merge_board_write
    from src.settings.service import restore_masked_board_secrets

    board = copy.deepcopy(incoming)
    restore_masked_board_secrets(board, copy.deepcopy(stored))
    return BoardInstance.from_dict(merge_board_write(board, copy.deepcopy(stored))).to_dict()


def moves_a_stored_secret(incoming: dict[str, Any], stored: dict[str, Any], sent: Any = None) -> bool:
    """True when this write sends a stored secret to a new endpoint and the request did not carry it.

    *sent* is what the phone actually sent, when *incoming* has already been
    merged onto the stored board (a saved-board action); default *incoming*.
    Only connection fields count (``src/auth/key_reentry.py``): moving tiles
    around, switching one off, or editing an output's non-connection
    settings keeps each key with its host and needs no re-entry.
    """
    from src.auth.key_reentry import moves_a_secret
    from src.settings.board_shape import board_view
    from src.settings.service import BoardSettings

    try:
        after = simulate_board_write(incoming, stored)
        masked_before = BoardSettings._mask_board(stored)
        if masked_before == BoardSettings._mask_board(after):
            return False
        return moves_a_secret(
            board_view(stored),
            board_view(after),
            masked_before,
            incoming if sent is None else sent,
            extra_keys=("output",),
        )
    except (ValueError, TypeError, KeyError):
        return False  # the real write refuses it with its own error


def first_board_needing_key(boards: list[Any], stored_boards: list[dict[str, Any]]) -> str | None:
    """The id of the first saved display in *boards* that :func:`moves_a_stored_secret`."""
    stored_by_id = {b.get("id"): b for b in stored_boards if isinstance(b, dict)}
    for board in boards:
        if not isinstance(board, dict):
            continue
        stored = stored_by_id.get(board.get("id"))
        if stored is not None and moves_a_stored_secret(board, stored):
            return str(board.get("id"))
    return None


def action_moves_a_stored_secret(edits: dict[str, Any], stored: dict[str, Any]) -> bool:
    """:func:`moves_a_stored_secret` for a saved-board action's edited ``output_config``.

    Merged onto the stored board the way ``src.outputs.actions.saved_board``
    merges it (edits over the stored ``output_config``).
    """
    stored_config = stored.get("output_config")
    merged = {**stored, "output_config": {**(stored_config if isinstance(stored_config, dict) else {}), **edits}}
    return moves_a_stored_secret(merged, stored, sent=edits)
