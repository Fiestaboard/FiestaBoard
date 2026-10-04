"""In-memory board client for virtual boards (the ``fiestapanel`` output).

A virtual board has no hardware: "sending" a frame just records it in the
board's runtime, and FiestaPanel viewers pull it back through the panel API
(``GET /panel/{id}/frame``). Duck-type compatible with
:class:`~src.board_client.BoardClient` for every external access the
codebase makes (send/read, cache management, ``use_cloud`` for read-poll
interval selection), mirroring
:class:`~src.note_array_local_client.NoteArrayLocalClient`.

The frame lives in core, not here: the board's
:class:`~src.outputs.runtime.OutputRuntime` keeps the last frame sent (its
:class:`~src.outputs.frames.FrameCache`), which is exactly what a pull
viewer is served, with core's stale-shape refusal and core's release when a
panel is deleted or re-fit. Every write to a saved board goes through that
one live runtime, so no per-board registry of frames is needed.
"""

import logging
from typing import Any

from .board_client import (
    LOCAL_READ_BACK,
    VALID_STRATEGIES,
    TransitionRenderMixin,
    TransitionStrategy,
)
from .devices import resolve_dimensions
from .outputs.hooks import ReadBack

logger = logging.getLogger(__name__)


class VirtualBoardClient(TransitionRenderMixin):
    """Renders frames into memory instead of a physical Vestaboard.

    Args:
        device_type: "flagship", "note", "note_array" or "panel" — with
            notes_wide/notes_tall (note_array) or grid_rows/grid_cols
            (panel), fixes the accepted grid shape.
        board_id: Settings board id (identity for logs and ``device_key``).
        skip_unchanged: Skip acknowledging a re-send of an identical grid.
    """

    def __init__(
        self,
        device_type: str = "flagship",
        board_id: str | None = None,
        skip_unchanged: bool = True,
        notes_wide: int = 1,
        notes_tall: int = 1,
        grid_rows: int | None = None,
        grid_cols: int | None = None,
    ):
        self.device_type = device_type
        self.board_id = board_id
        self.notes_wide = notes_wide
        self.notes_tall = notes_tall
        dims = resolve_dimensions(device_type, notes_wide, notes_tall, grid_rows, grid_cols)
        self.rows = dims.rows
        self.cols = dims.cols
        # Duck-type surface shared with BoardClient
        self.is_virtual = True
        self.use_cloud = False  # selects the local read-poll interval
        self.skip_unchanged = skip_unchanged
        self.api_key = ""
        # Send lock, cancel token and frame cache: a private runtime until the
        # board's BoardRuntime binds its own (set_output_runtime).
        self._init_transition_state()
        logger.info(
            "Virtual board client initialized (%s, %d×%d, board_id=%s)",
            device_type,
            self.rows,
            self.cols,
            board_id,
        )

    @property
    def native_transitions(self) -> frozenset[str]:
        """None: the FiestaPanel viewer animates every frame change itself."""
        return frozenset()

    def device_key(self) -> str:
        """The board: its board id (or, for an anonymous instance, the instance)."""
        if self.board_id is not None:
            return f"virtual:{self.board_id}"
        return f"virtual:anonymous-{id(self):x}"

    def send_text(self, text: str, force: bool = False, *, with_outcome: bool = False) -> Any:
        """Virtual boards are characters-only; mirror the note-array refusal."""
        logger.error("send_text is not supported for virtual boards; use send_characters()")
        return self._outcome(False, False, with_outcome=with_outcome)

    def send_characters(
        self,
        characters: list[list[int]],
        strategy: TransitionStrategy | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
        *,
        with_outcome: bool = False,
    ) -> Any:
        """Record the frame in the board's runtime (its last-frame store).

        Transition params are accepted for interface parity but ignored —
        the FiestaPanel viewer animates every frame change itself.

        Returns (success, was_sent) like the HTTP clients: an unchanged
        grid with skip_unchanged on is acknowledged without a "send".
        """
        if (
            not isinstance(characters, list)
            or len(characters) != self.rows
            or any(not isinstance(r, list) or len(r) != self.cols for r in characters)
        ):
            nrows = len(characters) if isinstance(characters, list) else 0
            ncols = len(characters[0]) if nrows and isinstance(characters[0], list) else 0
            logger.error(
                "Invalid grid for virtual board: got %dx%d, need %dx%d",
                nrows,
                ncols,
                self.rows,
                self.cols,
            )
            return self._outcome(False, False, with_outcome=with_outcome)

        if strategy is not None and strategy not in VALID_STRATEGIES:
            logger.error(f"Invalid strategy: {strategy}. Must be one of {VALID_STRATEGIES}")
            return self._outcome(False, False, with_outcome=with_outcome)

        # One runtime write, like every driver's: preempts the in-flight
        # transition when called directly, under the board's send lock.
        with self._output_runtime.write():
            frames = self._frames
            with frames.lock:
                if self.skip_unchanged and not force and frames.matches(characters):
                    logger.debug("Character array unchanged, skipping virtual send")
                    return self._outcome(True, False, with_outcome=with_outcome)

                frames.record_sent(characters)
            logger.debug("Virtual board frame stored (%d×%d)", self.rows, self.cols)
            return self._outcome(True, True, with_outcome=with_outcome)

    def read_current_message(self, sync_cache: bool = False) -> list[list[int]] | None:
        """Return a copy of the displayed frame; the runtime's store IS the board.

        Core's stale-shape refusal applies: a frame whose shape no longer
        matches this board's dimensions is treated as absent
        (:meth:`~src.outputs.runtime.OutputRuntime.displayed_frame`).
        """
        return self._output_runtime.displayed_frame(self.rows, self.cols)

    def clear_cache(self) -> None:
        """Clear the skip-unchanged cache WITHOUT blanking the displayed frame.

        Callers use clear_cache to force a re-send; for a virtual board the
        next send always lands, so only the dedupe needs resetting. The
        displayed frame and last_sent_at survive so FiestaPanel viewers
        keep showing the board's content.
        """
        self._frames.forget()
        logger.debug("Virtual board cache cleared")

    def get_cache_status(self) -> dict:
        return {
            "has_cached_text": False,
            "has_cached_characters": self._frames.characters is not None,
            "skip_unchanged_enabled": self.skip_unchanged,
            "cached_text_preview": None,
        }

    def would_send(self, text: str | None = None, characters: list[list[int]] | None = None) -> bool:
        if not self.skip_unchanged:
            return True
        if characters is not None:
            return not self._frames.matches(characters)
        return True

    def test_connection(self) -> bool:
        """A virtual board is always reachable."""
        return True

    @property
    def read_back(self) -> ReadBack:
        """The frame is read from core's store in memory: always cheap."""
        return LOCAL_READ_BACK

    @property
    def connection_label(self) -> str:
        """MQTT ``board_api_mode`` has always said "Local API" for a panel
        (it was derived from ``use_cloud``); kept so the sensor's value does
        not change under existing installs."""
        return "Local API"


def build_fiestapanel_driver(board: dict) -> VirtualBoardClient:
    """The ``fiestapanel`` output's driver for a board dict.

    Registered in :mod:`src.outputs.registry`; only the runtime factory
    (:mod:`src.outputs.factory`) calls it. A virtual board has no connection
    to configure, so it always builds.
    """
    from .devices import geometry_of

    geometry = geometry_of(board)
    return VirtualBoardClient(
        device_type=geometry.device_type,
        board_id=board.get("id"),
        notes_wide=geometry.notes_wide,
        notes_tall=geometry.notes_tall,
        grid_rows=geometry.grid_rows,
        grid_cols=geometry.grid_cols,
    )
