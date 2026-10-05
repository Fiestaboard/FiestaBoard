"""The FiestaPanel output: a board FiestaBoard draws itself, on any screen.

A FiestaPanel has no hardware to write. Delivery is **pull**: "sending" a
frame stores it as the board's last frame in FiestaBoard core, and panel
viewers (a TV app, a browser) fetch it through ``GET /panel/{id}/frame`` —
core's last-frame store, with its stale-shape refusal and its release when
a panel is deleted or re-fit. This class only says which frames fit.

Moved from FiestaBoard core's ``src/virtual_board_client.py``.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Mapping
from typing import Any

from src.plugins import ConnectionCheck, OutputPluginBase, ReadBack, WriteResult

logger = logging.getLogger(__name__)

#: The board shapes a panel board may be stored as.
DEVICE_TYPES = ("flagship", "note", "note_array", "panel")
_FIXED = {"flagship": (6, 22), "note": (3, 15)}
_NOTE_ROWS, _NOTE_COLS = 3, 15
#: A panel grid's bounds: at least one Note, at most what a 200" TV needs.
MIN_GRID_ROWS, MIN_GRID_COLS = 3, 15
MAX_GRID_ROWS, MAX_GRID_COLS = 96, 128

#: The frame is read from core's store, in memory: always cheap.
READ_BACK = ReadBack(supported=True, cost="cheap", suggested_interval_s=30)


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def board_dimensions(config: Mapping[str, Any]) -> tuple[int, int]:
    """``(rows, cols)`` of the board's grid.

    Raises:
        ValueError: an unknown shape, or a panel without an integer grid.
    """
    device_type = config.get("device_type")
    if device_type in _FIXED:
        return _FIXED[device_type]
    if device_type == "note_array":
        return config["notes_tall"] * _NOTE_ROWS, config["notes_wide"] * _NOTE_COLS
    if device_type == "panel":
        rows, cols = config.get("grid_rows"), config.get("grid_cols")
        for name, value in (("grid_rows", rows), ("grid_cols", cols)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"A panel grid needs an integer {name} (got {value!r})")
        return (
            max(MIN_GRID_ROWS, min(MAX_GRID_ROWS, int(rows))),
            max(MIN_GRID_COLS, min(MAX_GRID_COLS, int(cols))),
        )
    raise ValueError(f"Unknown device type: {device_type}. Must be one of {DEVICE_TYPES}")


class FiestaPanelOutput(OutputPluginBase):
    """One FiestaPanel board: frames of its grid's shape, kept by core."""

    plugin_id = "fiestapanel"

    #: The viewer draws the 0–71 grid itself, so content keeps split-flap
    #: markup whatever the panel's look (its LED model's set is rich).
    markup_follows_charset = False

    def __init__(self, board_id: str | None, config: dict[str, Any]) -> None:
        super().__init__(board_id, config)
        self.rows, self.cols = board_dimensions(self.config)
        logger.info(
            "Virtual board client initialized (%s, %d×%d, board_id=%s)",
            self.config.get("device_type"),
            self.rows,
            self.cols,
            board_id,
        )

    @classmethod
    def config_from_board(cls, board: Mapping[str, Any]) -> dict[str, Any]:
        """The board's shape — all a panel needs. Every panel board builds."""
        return {
            "device_type": str(board.get("device_type") or "flagship"),
            "notes_wide": _optional_int(board.get("notes_wide")) or 1,
            "notes_tall": _optional_int(board.get("notes_tall")) or 1,
            "grid_rows": _optional_int(board.get("grid_rows")),
            "grid_cols": _optional_int(board.get("grid_cols")),
        }

    @classmethod
    def declared_capabilities(cls, manifest: Any) -> Any:
        """A screen the viewer draws, pulled from core; the viewer animates
        every frame change itself, so no native strategy is declared."""
        return dataclasses.replace(
            manifest.capabilities,
            technology="screen",
            delivery="pull",
            animation="stream",
            native_transitions=frozenset(),
            min_interval_ms=0,
            read_back=None,
            device_models=(),
            charset=None,
            max_frames=None,
            write_timeout_ms=None,
        )

    def capabilities(self) -> Any:
        if self._output_manifest is None:
            raise RuntimeError("FiestaPanelOutput: no manifest bound")
        return dataclasses.replace(self.declared_capabilities(self._output_manifest), read_back=READ_BACK)

    @property
    def board_geometry(self) -> tuple[int, int]:
        """The panel's grid: the shape a stored frame must have to be shown."""
        return self.rows, self.cols

    def connection_label(self) -> str:
        """MQTT ``board_api_mode`` has always said "Local API" for a panel."""
        return "Local API"

    def device_key(self) -> str:
        """The board: its board id (or, for a draft, the instance)."""
        if self.board_id is not None:
            return f"virtual:{self.board_id}"
        return f"virtual:anonymous-{id(self):x}"

    def accepts_frame(self, frame: Any) -> bool:
        if (
            not isinstance(frame, list)
            or len(frame) != self.rows
            or any(not isinstance(r, list) or len(r) != self.cols for r in frame)
        ):
            nrows = len(frame) if isinstance(frame, list) else 0
            ncols = len(frame[0]) if nrows and isinstance(frame[0], list) else 0
            logger.error("Invalid grid for virtual board: got %dx%d, need %dx%d", nrows, ncols, self.rows, self.cols)
            return False
        return True

    def write(self, frame: Any, *, native: Any, cancel: Any) -> WriteResult:
        """Nothing to transmit: core stores the frame for the panel's viewers."""
        if not self.accepts_frame(frame):
            return WriteResult(False, False)
        logger.debug("Virtual board frame stored (%d×%d)", self.rows, self.cols)
        return WriteResult(True, True)

    def check_connection(self) -> ConnectionCheck:
        """A panel is always reachable: FiestaBoard is the device."""
        return ConnectionCheck(success=True, message="Successfully connected to your board!")

    def test_connection(self) -> bool:
        return True
