"""How a Vestaboard board is reached, from its settings.

A board saved before settings v4 keeps its Vestaboard connection in flat
fields beside its identity — ``api_mode``, ``host``, ``port``,
``local_api_key``, ``cloud_key``, ``note_array_token``, ``tiles`` — and its
shape in ``device_type`` / ``notes_wide`` / ``notes_tall``.
:func:`board_config` picks exactly those out of a saved board (the plugin's
``config_from_board``); :func:`resolve` turns them into one
:class:`Connection`, by the rules FiestaBoard core's driver factory used
before the Vestaboard was a plugin:

- a **note array** is driven tile by tile over the Local API when its
  ``api_mode`` is ``local`` and it has saved tiles (only the in-range,
  enabled, credentialed ones are driven; none → not configured); otherwise
  through the note-array Cloud API with its token;
- ``api_mode: cloud`` is the RW Cloud API with ``cloud_key``;
- anything else is the Local API, which needs ``host`` and ``local_api_key``.

``None`` means the board has no usable connection: FiestaBoard builds no
driver and shows the board as unconfigured.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from .transport import LOCAL_API_PORT, MAX_NOTES_PER_AXIS

#: The board fields a Vestaboard's settings live in.
CONNECTION_FIELDS = (
    "api_mode",
    "host",
    "port",
    "local_api_key",
    "cloud_key",
    "note_array_token",
    "tiles",
)
#: The board fields that size it (read, never owned, by the output).
GEOMETRY_FIELDS = ("device_type", "notes_wide", "notes_tall")

#: The ``api_mode`` values a board may store; anything else reads as local.
_API_MODES = ("local", "cloud", "virtual")

Mode = Literal["local", "cloud", "note_array_cloud", "local_tiles"]


@dataclass(frozen=True)
class Tile:
    """One Note of a local note array, reached over its own Local API."""

    row: int
    col: int
    host: str
    port: int
    local_api_key: str


@dataclass(frozen=True)
class Connection:
    """One board's way to its Vestaboard."""

    mode: Mode
    #: The credential: Local API key, RW Cloud key, or note-array token.
    key: str = ""
    host: str = ""
    port: int = LOCAL_API_PORT
    notes_wide: int = 1
    notes_tall: int = 1
    tiles: tuple[Tile, ...] = field(default_factory=tuple)

    @property
    def use_cloud(self) -> bool:
        return self.mode in ("cloud", "note_array_cloud")


def board_config(board: Mapping[str, Any]) -> dict[str, Any]:
    """A saved board's Vestaboard settings: its flat connection and shape
    fields, with any ``output_config`` the board carries laid over them."""
    config = {name: board[name] for name in (*CONNECTION_FIELDS, *GEOMETRY_FIELDS) if name in board}
    output_config = board.get("output_config")
    if isinstance(output_config, Mapping):
        config.update(output_config)
    return config


def _notes(value: Any) -> int:
    """A note-array axis, clamped to 1..8 (anything but a positive int is 1)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return 1
    return min(value, MAX_NOTES_PER_AXIS)


def normalize_tiles(tiles: Any) -> list[dict]:
    """A local note array's saved tiles, cleaned: dicts with an integer,
    non-negative ``row``/``col`` only, fields coerced (``port`` → int, 7000
    when unusable), deduped by position (the last wins), in position order.
    Out-of-range tiles are kept: the array's size is filtered at use."""
    if not isinstance(tiles, list):
        return []
    by_pos: dict[tuple[int, int], dict] = {}
    for tile in tiles:
        if not isinstance(tile, dict):
            continue
        try:
            row = int(tile.get("row"))
            col = int(tile.get("col"))
        except (TypeError, ValueError):
            continue
        if isinstance(tile.get("row"), bool) or isinstance(tile.get("col"), bool):
            continue
        if row < 0 or col < 0:
            continue
        port = tile.get("port")
        if not isinstance(port, int) or isinstance(port, bool):
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = LOCAL_API_PORT
        by_pos[(row, col)] = {
            "row": row,
            "col": col,
            "host": str(tile.get("host") or "").strip(),
            "port": port,
            "local_api_key": str(tile.get("local_api_key") or "").strip(),
            "enabled": bool(tile.get("enabled", True)),
        }
    return [by_pos[key] for key in sorted(by_pos)]


def _driven_tiles(tiles: list[dict], notes_wide: int, notes_tall: int) -> tuple[Tile, ...]:
    """The tiles that can actually be driven: in range, enabled, credentialed."""
    return tuple(
        Tile(t["row"], t["col"], t["host"], t["port"] or LOCAL_API_PORT, t["local_api_key"])
        for t in tiles
        if t["row"] < notes_tall and t["col"] < notes_wide and t["enabled"] and t["host"] and t["local_api_key"]
    )


def _port(value: Any) -> int:
    if value is not None and not isinstance(value, int):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = None
    return value if value is not None else LOCAL_API_PORT


def resolve(config: Mapping[str, Any]) -> Connection | None:
    """The board's :class:`Connection`, or ``None`` when it has none usable."""
    raw_mode = config.get("api_mode")
    if (config.get("device_type") or "flagship") == "note_array":
        mode = raw_mode if raw_mode in _API_MODES else "local"
        tiles = normalize_tiles(config.get("tiles") or [])
        if mode == "local" and tiles:
            notes_wide, notes_tall = _notes(config.get("notes_wide", 1)), _notes(config.get("notes_tall", 1))
            driven = _driven_tiles(tiles, notes_wide, notes_tall)
            if not driven:
                return None
            return Connection("local_tiles", notes_wide=notes_wide, notes_tall=notes_tall, tiles=driven)
        token = config.get("note_array_token") or ""
        if not token:
            return None
        return Connection(
            "note_array_cloud",
            key=token,
            notes_wide=config.get("notes_wide") or 1,
            notes_tall=config.get("notes_tall") or 1,
        )
    if (raw_mode or "local").lower() == "cloud":
        key = config.get("cloud_key") or ""
        return Connection("cloud", key=key) if key else None
    key = config.get("local_api_key") or ""
    host = config.get("host") or ""
    if not key or not host:
        return None
    return Connection("local", key=key, host=host, port=_port(config.get("port")))
