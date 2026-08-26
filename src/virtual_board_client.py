"""In-memory board client for virtual boards (FiestaPanel).

A virtual board has no hardware: "sending" a frame just stores it on the
client, and FiestaPanel web viewers read it back through the panel API.
Duck-type compatible with :class:`~src.board_client.BoardClient` for every
external access the codebase makes (send/read, cache management,
``use_cloud`` for read-poll interval selection), mirroring
:class:`~src.note_array_local_client.NoteArrayLocalClient`.
"""

import logging
import time

from .board_client import (
    VALID_STRATEGIES,
    TransitionRenderMixin,
    TransitionStrategy,
)
from .devices import resolve_dimensions

logger = logging.getLogger(__name__)


class VirtualBoardClient(TransitionRenderMixin):
    """Renders frames into memory instead of a physical Vestaboard.

    Args:
        device_type: "flagship" or "note" — fixes the accepted grid shape.
        skip_unchanged: Skip acknowledging a re-send of an identical grid.
    """

    def __init__(self, device_type: str = "flagship", skip_unchanged: bool = True):
        self.device_type = device_type
        dims = resolve_dimensions(device_type)
        self.rows = dims.rows
        self.cols = dims.cols
        # Duck-type surface shared with BoardClient
        self.is_virtual = True
        self.use_cloud = False  # selects the local read-poll interval
        self.skip_unchanged = skip_unchanged
        self.api_key = ""
        self._last_characters: list[list[int]] | None = None
        self._last_text: str | None = None
        # What the panel actually shows. Kept separate from _last_characters
        # (the skip-unchanged dedupe cache) so clear_cache() can force a
        # re-send without blanking every FiestaPanel viewer.
        self._displayed_characters: list[list[int]] | None = None
        # When the current frame was stored (epoch seconds); panel API surfaces it.
        self._last_sent_at: float | None = None
        # Transition-plugin render state (lock, cancel event, runner slot).
        self._init_transition_state()
        logger.info(
            "Virtual board client initialized (%s, %d×%d)",
            device_type,
            self.rows,
            self.cols,
        )

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
        """Store the frame in memory.

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

        if self.skip_unchanged and not force and self._last_characters == characters:
            logger.debug("Character array unchanged, skipping virtual send")
            return (True, False)

        self._last_characters = [row[:] for row in characters]
        self._displayed_characters = [row[:] for row in characters]
        self._last_text = None
        self._last_sent_at = time.time()
        logger.debug("Virtual board frame stored (%d×%d)", self.rows, self.cols)
        return (True, True)

    def read_current_message(self, sync_cache: bool = False) -> list[list[int]] | None:
        """Return a copy of the displayed frame; the memory IS the board."""
        if self._displayed_characters is None:
            return None
        return [row[:] for row in self._displayed_characters]

    def clear_cache(self) -> None:
        """Clear the skip-unchanged cache WITHOUT blanking the displayed frame.

        Callers use clear_cache to force a re-send; for a virtual board the
        next send always lands, so only the dedupe needs resetting. The
        displayed frame and _last_sent_at survive so FiestaPanel viewers
        keep showing the board's content.
        """
        self._last_characters = None
        self._last_text = None
        logger.debug("Virtual board cache cleared")

    def get_cache_status(self) -> dict:
        return {
            "has_cached_text": False,
            "has_cached_characters": self._last_characters is not None,
            "skip_unchanged_enabled": self.skip_unchanged,
            "cached_text_preview": None,
        }

    def would_send(self, text: str | None = None, characters: list[list[int]] | None = None) -> bool:
        if not self.skip_unchanged:
            return True
        if characters is not None:
            return self._last_characters != characters
        return True

    def test_connection(self) -> bool:
        """A virtual board is always reachable."""
        return True
