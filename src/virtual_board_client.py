"""In-memory board client for virtual boards (FiestaPanel).

A virtual board has no hardware: "sending" a frame just stores it, and
FiestaPanel web viewers read it back through the panel API. Duck-type
compatible with :class:`~src.board_client.BoardClient` for every external
access the codebase makes (send/read, cache management, ``use_cloud`` for
read-poll interval selection), mirroring
:class:`~src.note_array_local_client.NoteArrayLocalClient`.

Frame state lives with the BOARD, not the client instance: several code
paths (live template render, detect-size) build throwaway clients via
``board_client_from_board_dict`` while the display loop holds its own
instance. A per-board-id registry keeps them all looking at the same
"glass" — without it, a live-edit send lands on a fresh instance and
evaporates before any viewer polls it.
"""

import logging
import threading
from typing import Any

from .board_client import (
    VALID_STRATEGIES,
    TransitionRenderMixin,
    TransitionStrategy,
)
from .devices import resolve_dimensions
from .outputs.frames import FrameCache

logger = logging.getLogger(__name__)


# A virtual board's "glass" is its runtime's FrameCache: the dedupe cache
# (cleared by clear_cache to force a re-send) and the last-frame store, which
# IS what the panel shows and survives clear_cache. It is shared per board id
# because a throwaway live-render client's runtime is not the display loop's
# (only the engine's client is bound to the board's runtime — a later layer
# routes every client through it); the cache's lock keeps a live-edit send
# racing the loop from desyncing the dedupe cache from the displayed frame,
# after which a real send would be skipped as "unchanged" and the TV would
# stick on the wrong frame.
_states: dict[str, FrameCache] = {}
_states_lock = threading.Lock()


def _state_for(board_id: str | None) -> FrameCache:
    """Shared state for a board id; instance-local state when anonymous."""
    if board_id is None:
        return FrameCache()
    with _states_lock:
        state = _states.get(board_id)
        if state is None:
            state = FrameCache()
            _states[board_id] = state
        return state


def release_virtual_board_state(board_id: str | None) -> None:
    """Drop a board's shared frame state from the registry.

    Called when a panel (and its virtual board) is deleted so the stored
    grids don't outlive the board. Safe for unknown or None ids; live client
    instances keep their reference and simply expire with them.
    """
    if board_id is None:
        return
    with _states_lock:
        _states.pop(board_id, None)


class VirtualBoardClient(TransitionRenderMixin):
    """Renders frames into memory instead of a physical Vestaboard.

    Args:
        device_type: "flagship", "note", "note_array" or "panel" — with
            notes_wide/notes_tall (note_array) or grid_rows/grid_cols
            (panel), fixes the accepted grid shape.
        board_id: Settings board id; instances sharing it share frame state.
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
        self._state = _state_for(board_id)
        # Transition-plugin render state (lock, cancel event, runner slot); the
        # runtime's frame cache is the board's shared glass.
        self._init_transition_state(frames=self._state)
        logger.info(
            "Virtual board client initialized (%s, %d×%d, board_id=%s)",
            device_type,
            self.rows,
            self.cols,
            board_id,
        )

    def device_key(self) -> str:
        """The board's shared glass: its board id (or the instance's own glass)."""
        if self.board_id is not None:
            return f"virtual:{self.board_id}"
        return f"virtual:anonymous-{id(self._state):x}"

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
        """Store the frame in the board's shared state.

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

        frames = self._frames
        with frames.lock:
            if self.skip_unchanged and not force and frames.matches(characters):
                logger.debug("Character array unchanged, skipping virtual send")
                return self._outcome(True, False, with_outcome=with_outcome)

            frames.record_sent(characters)
        logger.debug("Virtual board frame stored (%d×%d)", self.rows, self.cols)
        return self._outcome(True, True, with_outcome=with_outcome)

    def read_current_message(self, sync_cache: bool = False) -> list[list[int]] | None:
        """Return a copy of the displayed frame; the memory IS the board.

        A frame whose shape no longer matches the board's dimensions is
        treated as absent: a panel TV-size edit re-fits the board's grid,
        and serving the old-shape frame would leave the viewer rendering
        stale mismatched content forever (config says the new size, frame
        carries the old one).
        """
        frames = self._frames
        with frames.lock:
            displayed = frames.last_frame
            if displayed is None:
                return None
            if len(displayed) != self.rows or any(len(row) != self.cols for row in displayed):
                return None
            return [row[:] for row in displayed]

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
