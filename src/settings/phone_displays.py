"""H21a: a phone never sends a display's stored secret to settings it just chose.

A phone (``control`` scope) may add, change and remove displays. Changing a
saved display's *connection* (its host, mode, tiles or ``output_config``)
must not carry the stored key along: the stored key would then be sent to a
host the phone picked. The browser keeps today's rule (an echoed ``"***"``
keeps the stored secret), so this check runs for phones only.

How: the write is simulated with the same pure steps ``set_boards`` uses
(restore echoed masks, merge the two shapes, normalise). When the masked
connection view changes, every stored secret must have been re-entered: a
secret whose stored value survives into the result, and which the request
did not carry itself, refuses the write (``key_required``).
"""

from __future__ import annotations

import copy
import json
from typing import Any

from src.auth.phone_policy import MASK


def _leaves(value: Any, path: tuple = ()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, (*path, index))
    else:
        yield path, value


def _at(value: Any, path: tuple) -> Any:
    for step in path:
        if (isinstance(value, dict) and step in value) or (
            isinstance(value, list) and isinstance(step, int) and 0 <= step < len(value)
        ):
            value = value[step]
        else:
            return None
    return value


def _connection(view: dict[str, Any]) -> dict[str, Any]:
    from src.devices import LEGACY_CONNECTION_FIELDS

    return {key: view.get(key) for key in (*LEGACY_CONNECTION_FIELDS, "output", "output_config")}


def simulate_board_write(incoming: dict[str, Any], stored: dict[str, Any]) -> dict[str, Any]:
    """The stored board *incoming* would become, without saving anything."""
    from src.devices import BoardInstance
    from src.settings.board_shape import merge_board_write
    from src.settings.service import restore_masked_board_secrets

    board = copy.deepcopy(incoming)
    restore_masked_board_secrets(board, copy.deepcopy(stored))
    return BoardInstance.from_dict(merge_board_write(board, copy.deepcopy(stored))).to_dict()


def moves_a_stored_secret(incoming: dict[str, Any], stored: dict[str, Any], sent: Any = None) -> bool:
    """True when this write changes the connection but keeps a stored secret the request did not carry.

    *sent* is what the phone actually sent, when *incoming* has already been
    merged onto the stored board (a saved-board action); default *incoming*.
    """
    from src.settings.board_shape import board_view
    from src.settings.service import BoardSettings

    try:
        after = simulate_board_write(incoming, stored)
    except (ValueError, TypeError, KeyError):
        return False  # the real write refuses it with its own error
    masked_before = _connection(BoardSettings._mask_board(stored))
    masked_after = _connection(BoardSettings._mask_board(after))
    if masked_before == masked_after:
        return False
    raw_before = _connection(board_view(stored))
    raw_after = _connection(board_view(after))
    sent = json.dumps(incoming if sent is None else sent, default=str)
    for path, value in _leaves(masked_before):
        if value != MASK:
            continue
        secret = _at(raw_before, path)
        if secret in (None, "", MASK):
            continue
        survived = any(v == secret for _p, v in _leaves(raw_after))
        if survived and json.dumps(secret)[1:-1] not in sent:
            return True
    return False


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
