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
import time

from .board_client import (
    VALID_STRATEGIES,
    TransitionRenderMixin,
    TransitionStrategy,
)
from .devices import resolve_dimensions

logger = logging.getLogger(__name__)


class _VirtualBoardState:
    """The shared 'glass' of one virtual board."""

    def __init__(self) -> None:
        # Skip-unchanged dedupe cache (cleared by clear_cache to force a re-send).
        self.last_characters: list[list[int]] | None = None
        # What the panel actually shows (survives clear_cache).
        self.displayed_characters: list[list[int]] | None = None
        self.last_text: str | None = None
        # When the current frame was stored (epoch seconds).
        self.last_sent_at: float | None = None


_states: dict[str, _VirtualBoardState] = {}
_states_lock = threading.Lock()


def _state_for(board_id: str | None) -> _VirtualBoardState:
    """Shared state for a board id; instance-local state when anonymous."""
    if board_id is None:
        return _VirtualBoardState()
    with _states_lock:
        state = _states.get(board_id)
        if state is None:
            state = _VirtualBoardState()
            _states[board_id] = state
        return state


class VirtualBoardClient(TransitionRenderMixin):
    """Renders frames into memory instead of a physical Vestaboard.

    Args:
        device_type: "flagship" or "note" — fixes the accepted grid shape.
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
    ):
        self.device_type = device_type
        self.board_id = board_id
        self.notes_wide = notes_wide
        self.notes_tall = notes_tall
        dims = resolve_dimensions(device_type, notes_wide, notes_tall)
        self.rows = dims.rows
        self.cols = dims.cols
        # Duck-type surface shared with BoardClient
        self.is_virtual = True
        self.use_cloud = False  # selects the local read-poll interval
        self.skip_unchanged = skip_unchanged
        self.api_key = ""
        self._state = _state_for(board_id)
        # Transition-plugin render state (lock, cancel event, runner slot).
        self._init_transition_state()
        logger.info(
            "Virtual board client initialized (%s, %d×%d, board_id=%s)",
            device_type,
            self.rows,
            self.cols,
            board_id,
        )

    # BoardClient exposes these as plain attributes; keep the same names
    # (external code reads them via getattr) while backing them with the
    # per-board shared state.
    @property
    def _last_characters(self) -> list[list[int]] | None:
        return self._state.last_characters

    @_last_characters.setter
    def _last_characters(self, value: list[list[int]] | None) -> None:
        self._state.last_characters = value

    @property
    def _last_text(self) -> str | None:
        return self._state.last_text

    @_last_text.setter
    def _last_text(self, value: str | None) -> None:
        self._state.last_text = value

    @property
    def _displayed_characters(self) -> list[list[int]] | None:
        return self._state.displayed_characters

    @property
    def _last_sent_at(self) -> float | None:
        return self._state.last_sent_at

    def send_text(self, text: str, force: bool = False) -> tuple[bool, bool]:
        """Virtual boards are characters-only; mirror the note-array refusal."""
        logger.error("send_text is not supported for virtual boards; use send_characters()")
        return (False, False)

    def send_characters(
        self,
        characters: list[list[int]],
        strategy: TransitionStrategy | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
    ) -> tuple[bool, bool]:
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
            return (False, False)

        if strategy is not None and strategy not in VALID_STRATEGIES:
            logger.error(f"Invalid strategy: {strategy}. Must be one of {VALID_STRATEGIES}")
            return (False, False)

        state = self._state
        if self.skip_unchanged and not force and state.last_characters == characters:
            logger.debug("Character array unchanged, skipping virtual send")
            return (True, False)

        state.last_characters = [row[:] for row in characters]
        state.displayed_characters = [row[:] for row in characters]
        state.last_text = None
        state.last_sent_at = time.time()
        logger.debug("Virtual board frame stored (%d×%d)", self.rows, self.cols)
        return (True, True)

    def read_current_message(self, sync_cache: bool = False) -> list[list[int]] | None:
        """Return a copy of the displayed frame; the memory IS the board."""
        displayed = self._state.displayed_characters
        if displayed is None:
            return None
        return [row[:] for row in displayed]

    def clear_cache(self) -> None:
        """Clear the skip-unchanged cache WITHOUT blanking the displayed frame.

        Callers use clear_cache to force a re-send; for a virtual board the
        next send always lands, so only the dedupe needs resetting. The
        displayed frame and last_sent_at survive so FiestaPanel viewers
        keep showing the board's content.
        """
        self._state.last_characters = None
        self._state.last_text = None
        logger.debug("Virtual board cache cleared")

    def get_cache_status(self) -> dict:
        return {
            "has_cached_text": False,
            "has_cached_characters": self._state.last_characters is not None,
            "skip_unchanged_enabled": self.skip_unchanged,
            "cached_text_preview": None,
        }

    def would_send(self, text: str | None = None, characters: list[list[int]] | None = None) -> bool:
        if not self.skip_unchanged:
            return True
        if characters is not None:
            return self._state.last_characters != characters
        return True

    def test_connection(self) -> bool:
        """A virtual board is always reachable."""
        return True
