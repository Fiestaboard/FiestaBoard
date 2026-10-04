"""A board's two shapes: settings v4 storage and the settings-v3 flat view (plan D8).

Settings v4 stores every board with an ``output`` and an ``output_config``;
a Vestaboard's connection (``api_mode``, ``host``, ``port``,
``local_api_key``, ``cloud_key``, ``note_array_token``, ``tiles``) lives in
its ``output_config``. Every public API still answers in the flat shape, and
today's web UI still writes it, so until the Vestaboard settings screen moves
onto the plugin renderer (Phase 4, P4d) this module projects both ways:

- :func:`board_view` — stored board → flat view (plus ``output`` and
  ``output_config``), for every reader and response that speaks flat fields;
- :func:`merge_board_write` — an incoming write carrying flat fields, an
  ``output_config``, or both → one unambiguous board, honouring whichever
  half the client actually changed;
- :func:`migrate_board_to_v4` — the raw settings v3 → v4 move of one board.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.devices import BUILTIN_OUTPUT_IDS, LEGACY_CONNECTION_FIELDS, derive_output_id

VESTABOARD = "vestaboard"
FIESTAPANEL = "fiestapanel"

#: The settings-v3 order of a board's fields: the flat view keeps it, so a
#: client reading the board sees the shape it always has.
_V3_ORDER: tuple[str, ...] = (
    "id",
    "name",
    "device_type",
    "board_color",
    "code62_glyph",
    "enabled",
    "paused",
    "schedule_enabled",
    *LEGACY_CONNECTION_FIELDS[:-1],
    "notes_wide",
    "notes_tall",
    "grid_rows",
    "grid_cols",
    "tiles",
    "output",
    "output_config",
    "device_model",
)


def _defaults() -> dict[str, Any]:
    from src.outputs.vestaboard.connection import CONNECTION_DEFAULTS

    return {k: (list(v) if isinstance(v, list) else v) for k, v in CONNECTION_DEFAULTS.items()}


def flat_connection(board: Mapping[str, Any]) -> dict[str, Any]:
    """The settings-v3 flat connection fields of *board*, either shape.

    A Vestaboard's come from its ``output_config`` (over any flat fields a
    v3 dict still carries); a FiestaPanel reads ``api_mode: "virtual"``; an
    output plugin's board reads the v3 defaults it was always stored with.
    Values are as stored, unset ones default.
    """
    output = derive_output_id(board)
    values = _defaults()
    if output == VESTABOARD:
        values.update({k: board[k] for k in LEGACY_CONNECTION_FIELDS if k in board})
        config = board.get("output_config")
        if isinstance(config, Mapping):
            values.update({k: config[k] for k in LEGACY_CONNECTION_FIELDS if k in config})
    elif output == FIESTAPANEL:
        values["api_mode"] = "virtual"
    return values


def board_view(board: Mapping[str, Any]) -> dict[str, Any]:
    """*board* in the settings-v3 flat shape, plus ``output`` and ``output_config``.

    Idempotent (a view of a view is the same view) and never mutates
    *board*. Credentials are NOT masked: this is the in-process reader view;
    the API masks it (``BoardSettings._mask_board``).
    """
    merged = dict(board)
    merged.update(flat_connection(board))
    merged["output"] = derive_output_id(board)
    if not isinstance(merged.get("output_config"), dict):
        merged["output_config"] = {}
    view = {key: merged[key] for key in _V3_ORDER if key in merged}
    view.update({key: value for key, value in merged.items() if key not in view})
    return view


def merge_board_write(incoming: dict, existing: Mapping[str, Any] | None) -> dict:
    """One unambiguous board from a write in either shape (D8 bidirectional).

    *incoming* has had its ``"***"`` secrets restored already. A write in the
    flat shape (today's web UI, ``/config/board``, MCP) carries connection
    fields at the top level; one in the v4 shape carries them in
    ``output_config``; an echo of ``GET /settings/board`` carries both. When
    both halves carry a field with different values, the half that differs
    from the stored board is the client's edit and wins — so the flat form
    can edit while echoing a stale ``output_config``, and a v4 form can edit
    ``output_config`` while echoing stale flat fields. With no stored board
    (a new one) the flat half wins (:meth:`BoardInstance.from_dict`).

    Returns a dict for :meth:`BoardInstance.from_dict` with no flat fields
    left when there was a stored board to resolve against.
    """
    flat = {k: incoming[k] for k in LEGACY_CONNECTION_FIELDS if k in incoming}
    if not flat or existing is None:
        return incoming
    out = {k: v for k, v in incoming.items() if k not in LEGACY_CONNECTION_FIELDS}
    stored = board_view(existing)
    explicit = incoming.get("output")
    explicit = explicit.strip() if isinstance(explicit, str) and explicit.strip() else None
    if explicit is not None and explicit not in BUILTIN_OUTPUT_IDS:
        return out  # an output plugin's board: flat fields never meant anything

    def edited(name: str) -> bool:
        return name in flat and flat[name] != stored.get(name)

    flat_says = FIESTAPANEL if str(flat.get("api_mode") or "").lower() == "virtual" else VESTABOARD
    if "api_mode" in flat and (explicit is None or (flat_says != explicit and edited("api_mode"))):
        output = flat_says
    elif explicit is not None:
        output = explicit
    else:
        output = stored["output"]
    out["output"] = output
    if output not in BUILTIN_OUTPUT_IDS:
        return out
    config = incoming.get("output_config")
    config = dict(config) if isinstance(config, dict) else None
    if output == VESTABOARD:
        merged = dict(config) if config is not None else {}
        for name, value in flat.items():
            if config is None or name not in config or (value != config[name] and edited(name)):
                merged[name] = value
        out["output_config"] = merged
    else:
        out["output_config"] = config or {}
    return out


def migrate_board_to_v4(board: dict) -> bool:
    """Settings v3 → v4 for one raw board dict, in place. True when it changed.

    Precedence for ``output``: an explicit ``output`` wins → ``api_mode ==
    "virtual"`` is ``fiestapanel`` → else ``vestaboard``. A Vestaboard's flat
    connection fields MOVE into ``output_config`` (a flat value wins over one
    already there: a v3 dict carrying both halves was a flat write). Flat
    fields mean nothing to a FiestaPanel (it renders to memory) or an output
    plugin, so theirs are dropped; the pre-migration backup keeps them.
    Identity, display, flags and geometry stay top-level. Idempotent: a v4
    board has no flat fields and an explicit output, and is left alone.
    """
    flat_present = [k for k in LEGACY_CONNECTION_FIELDS if k in board]
    explicit = board.get("output")
    has_output = isinstance(explicit, str) and bool(explicit.strip())
    config = board.get("output_config")
    if not flat_present and has_output and isinstance(config, dict):
        return False
    output = derive_output_id(board)
    flat = {k: board.pop(k) for k in flat_present}
    config = dict(config) if isinstance(config, dict) else {}
    if output == VESTABOARD:
        config = {**config, **flat}
    elif output == FIESTAPANEL:
        config = {}
    if "output" in board:
        board["output"] = output
    if "output_config" in board:
        board["output_config"] = config
    board.setdefault("output", output)
    board.setdefault("output_config", config)
    return True
