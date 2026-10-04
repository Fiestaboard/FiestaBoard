"""A Vestaboard board's connection, as core reads it from ``output_config``.

Settings v4 (plan D8) stores a Vestaboard's connection — ``api_mode``,
``host``, ``port``, ``local_api_key``, ``cloud_key``, ``note_array_token``
and the local note-array ``tiles`` — in the board's ``output_config``, the
same place every output plugin keeps its settings. Core's board record
(:class:`src.devices.BoardInstance`) keeps only identity, display, geometry,
``output`` and ``output_config``; this module is the one place core still
interprets a Vestaboard's config:

- :class:`VestaboardConnection` normalises it (the rules ``BoardInstance``
  applied to its flat fields through settings v3) and answers the
  questions core still asks of a Vestaboard board — is it configured, is it
  a local-tile array, which tiles can be driven;
- :func:`restore_connection_secrets` / :func:`mask_connection_secrets` are
  the ``"***"`` rules for its credentials, including each tile's key, which
  is matched to the stored tile by endpoint and then by grid position (a
  generic ``output_config`` unmask cannot: tiles carry no id).

The plugin (``fiestaboard-output--vestaboard``) reads the same
``output_config`` itself; nothing here talks to a board. It goes with the
rest of the Vestaboard knowledge in core when the settings screen moves onto
the plugin renderer (Phase 4, P4d/P4e).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

#: The Vestaboard connection fields, in their settings-v3 (flat) order.
CONNECTION_FIELDS: tuple[str, ...] = (
    "api_mode",
    "host",
    "port",
    "local_api_key",
    "cloud_key",
    "note_array_token",
    "tiles",
)

#: The board-level credentials (masked as ``"***"`` in every API view).
SECRET_FIELDS = frozenset({"local_api_key", "cloud_key", "note_array_token"})

#: The per-tile credential of a local note array.
TILE_SENSITIVE_FIELDS = frozenset({"local_api_key"})

#: The Local API's port, and every connection field's value when unset.
DEFAULT_PORT = 7000
CONNECTION_DEFAULTS: dict[str, Any] = {
    "api_mode": "local",
    "host": "",
    "port": DEFAULT_PORT,
    "local_api_key": "",
    "cloud_key": "",
    "note_array_token": "",
    "tiles": [],
}

MASKED = "***"


def normalize_note_array_tiles(tiles: Any) -> list[dict]:
    """Normalize a local note-array tile list.

    Each tile addresses one physical Note over the local API:
    ``{"row", "col", "host", "port", "local_api_key", "enabled"}`` with
    ``row``/``col`` 0-indexed in note coordinates.

    Drops non-dict entries and entries without a usable row/col, coerces field
    types, and dedupes by (row, col) keeping the last occurrence. Does NOT
    filter to the board's current notes_wide/notes_tall — out-of-range tiles
    are preserved in storage so shrinking and re-growing an array never
    destroys hard-to-reobtain local API keys. Filter at point of use via
    :meth:`VestaboardConnection.configured_tiles`.
    """
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
                port = DEFAULT_PORT
        by_pos[(row, col)] = {
            "row": row,
            "col": col,
            "host": str(tile.get("host") or "").strip(),
            "port": port,
            "local_api_key": str(tile.get("local_api_key") or "").strip(),
            "enabled": bool(tile.get("enabled", True)),
        }
    return [by_pos[key] for key in sorted(by_pos)]


def _port(value: Any) -> int:
    if value is None:
        return DEFAULT_PORT
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_PORT


@dataclass
class VestaboardConnection:
    """One Vestaboard board's normalised connection settings."""

    api_mode: str = "local"
    host: str = ""
    port: int = DEFAULT_PORT
    local_api_key: str = ""
    cloud_key: str = ""
    note_array_token: str = ""
    tiles: list = field(default_factory=list)

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None, device_type: str) -> VestaboardConnection:
        """The connection a board's ``output_config`` describes, normalised.

        An unknown ``api_mode`` is ``"local"``; ``port`` is an int (7000 when
        unusable); the note-array token is stripped; tiles are kept only on a
        note array (``device_type == "note_array"``) and normalised.
        """
        from src.devices import VALID_API_MODES, is_note_array

        config = config if isinstance(config, Mapping) else {}
        api_mode = config.get("api_mode", "local")
        return cls(
            api_mode=api_mode if api_mode in VALID_API_MODES else "local",
            host=config.get("host", "") if config.get("host") is not None else "",
            port=_port(config.get("port")),
            local_api_key=config.get("local_api_key", "") if config.get("local_api_key") is not None else "",
            cloud_key=config.get("cloud_key", "") if config.get("cloud_key") is not None else "",
            note_array_token=(config.get("note_array_token") or "").strip(),
            tiles=normalize_note_array_tiles(config.get("tiles") or []) if is_note_array(device_type) else [],
        )

    def to_config(self) -> dict[str, Any]:
        """The ``output_config`` this connection is stored as."""
        return {
            "api_mode": self.api_mode,
            "host": self.host,
            "port": self.port,
            "local_api_key": self.local_api_key,
            "cloud_key": self.cloud_key,
            "note_array_token": self.note_array_token,
            "tiles": [dict(t) for t in self.tiles],
        }

    def uses_local_tiles(self, device_type: str) -> bool:
        """True when this note array is driven tile-by-tile over the local API.

        Requires BOTH api_mode == "local" and at least one saved tile: legacy
        array dicts created without an explicit api_mode default to "local"
        but carry only a cloud token — those must keep driving via the cloud.
        """
        from src.devices import is_note_array

        return is_note_array(device_type) and self.api_mode == "local" and bool(self.tiles)

    def configured_tiles(self, notes_wide: int, notes_tall: int) -> list[dict]:
        """Tiles that are in-range for the W×H, enabled, and credentialed.

        Single source of truth for "which tiles can actually be driven" —
        used by the configured check and identify.
        """
        return [
            t
            for t in self.tiles
            if t["row"] < notes_tall and t["col"] < notes_wide and t["enabled"] and t["host"] and t["local_api_key"]
        ]

    def is_configured(self, device_type: str, notes_wide: int, notes_tall: int) -> bool:
        """Whether a driver can be built from this connection."""
        from src.devices import is_note_array

        if self.api_mode == "virtual":
            return True
        if is_note_array(device_type):
            if self.uses_local_tiles(device_type):
                # A partial array is usable: assigned tiles receive their
                # slice, unassigned slots simply stay dark. Requiring every
                # slot would flip a half-assembled array back to
                # "unconfigured" and could re-trigger first-run detection.
                return bool(self.configured_tiles(notes_wide, notes_tall))
            # notes_wide/notes_tall are always >= 1, so configuration
            # hinges solely on having a token.
            return bool(self.note_array_token)
        if self.api_mode == "cloud":
            return bool(self.cloud_key)
        return bool(self.local_api_key and self.host)

    def has_attempt(self) -> bool:
        """True when the user has entered ANY connection detail (see
        ``BoardInstance.has_connection_attempt``)."""
        if self.api_mode == "virtual":
            return True
        return bool(self.host or self.local_api_key or self.cloud_key or self.note_array_token or self.tiles)


def restore_connection_secrets(target: dict, existing: Mapping[str, Any]) -> dict:
    """Restore every echoed ``"***"`` credential in *target* from *existing*, in place.

    Both are Vestaboard connections (flat board fields or an
    ``output_config``). A board-level secret echoed as ``"***"`` takes the
    stored value (``""`` when there is none). Each tile's key is matched to
    the stored tile by host:port FIRST, so the key follows the physical board
    when tiles are moved/swapped to new grid positions (the UI's "Move to
    position" sends masked keys at the NEW coordinates — a position-only
    match would pair each host with the OTHER board's key), then by
    (row, col) for the change-the-IP-keep-the-key flow.
    """
    for key in SECRET_FIELDS:
        if target.get(key) == MASKED:
            target[key] = existing.get(key, "") or ""
    incoming_tiles = target.get("tiles")
    if isinstance(incoming_tiles, list):
        existing_tiles = [t for t in existing.get("tiles") or [] if isinstance(t, dict)]
        existing_tiles_by_pos = {(t.get("row"), t.get("col")): t for t in existing_tiles}
        existing_tiles_by_endpoint: dict = {}
        for t in existing_tiles:
            existing_tiles_by_endpoint.setdefault((t.get("host"), t.get("port")), t)
        for tile in incoming_tiles:
            if not isinstance(tile, dict):
                continue
            existing_tile = existing_tiles_by_endpoint.get(
                (tile.get("host"), tile.get("port"))
            ) or existing_tiles_by_pos.get((tile.get("row"), tile.get("col")), {})
            for key in TILE_SENSITIVE_FIELDS:
                if tile.get(key) == MASKED:
                    tile[key] = existing_tile.get(key, "")
    return target


def mask_connection_secrets(config: Mapping[str, Any]) -> dict:
    """A copy of a Vestaboard connection with every set credential ``"***"``.

    Tiles are rebuilt, never mutated, so masking a shallow copy cannot
    corrupt the stored dicts.
    """
    masked = dict(config)
    for key in SECRET_FIELDS:
        if masked.get(key):
            masked[key] = MASKED
    tiles = masked.get("tiles")
    if isinstance(tiles, list):
        masked["tiles"] = [
            {**tile, **{k: MASKED for k in TILE_SENSITIVE_FIELDS if tile.get(k)}} if isinstance(tile, dict) else tile
            for tile in tiles
        ]
    return masked
