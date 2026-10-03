"""What one board is showing, as far as FiestaBoard knows — owned by core.

A :class:`FrameCache` lives on the board's
:class:`~src.outputs.runtime.OutputRuntime` and holds two different answers
that used to be private attributes of each board client:

- **The dedupe cache** (``characters`` / ``text``): the grid the device was
  last *known* to show — set by a successful send, or by a read-back that
  syncs it (startup). A send of an equal grid is acknowledged without a
  device write. :meth:`forget` clears it to force the next send through.
  ``generation`` advances every time it is replaced, which is what
  external-write detection judges "did we write in between?" by.
- **The last-frame store** (``last_frame`` / ``last_sent_at``): the grid
  FiestaBoard last actually *sent*, and when (epoch seconds). Written on
  every successful device write and never cleared by :meth:`forget` — a
  forced re-send must not blank what a viewer of the store sees.

Sub-unit caches stay with the driver: a local note array keeps one per tile
so a retry re-posts only the tiles that failed (plan D3).

Every grid is copied on the way in. The ``characters`` and ``last_frame``
attributes hand back the stored list itself; callers treat it as read-only.
"""

from __future__ import annotations

import threading
import time

Grid = list[list[int]]


def _copy(grid: Grid) -> Grid:
    return [row[:] for row in grid]


class FrameCache:
    """One board's dedupe cache and last-frame store."""

    def __init__(self) -> None:
        # Re-entrant so a driver can hold it across check-then-record (the
        # virtual board's "glass" does) while the record methods take it too.
        self.lock = threading.RLock()
        self.characters: Grid | None = None
        self.text: str | None = None
        self.generation: int = 0
        self.last_frame: Grid | None = None
        self.last_sent_at: float | None = None

    # --- dedupe ------------------------------------------------------------------

    def matches(self, characters: Grid) -> bool:
        """True when *characters* equals what the board is known to show."""
        with self.lock:
            return self.characters == characters

    def matches_text(self, text: str) -> bool:
        """True when *text* equals the text message the board is known to show."""
        with self.lock:
            return self.text == text

    def snapshot(self) -> tuple[Grid | None, int]:
        """``(characters, generation)`` read together."""
        with self.lock:
            return self.characters, self.generation

    def record_sent(self, characters: Grid, *, at: float | None = None) -> None:
        """A device write of *characters* succeeded.

        Updates both the dedupe cache and the last-frame store.
        """
        with self.lock:
            self.characters = _copy(characters)
            self.text = None
            self.generation += 1
            self.last_frame = _copy(characters)
            self.last_sent_at = time.time() if at is None else at

    def record_text_sent(self, text: str) -> None:
        """A plain-text write succeeded; the grid it produced is unknown."""
        with self.lock:
            self.text = text
            self.characters = None
            self.generation += 1

    def record_read(self, characters: Grid) -> None:
        """A read-back says the board shows *characters* (cache sync).

        Only the dedupe cache moves: FiestaBoard did not send this frame.
        """
        with self.lock:
            self.characters = _copy(characters)
            self.text = None
            self.generation += 1

    def forget(self) -> None:
        """Clear the dedupe cache so the next send goes through.

        The last-frame store survives: forcing a re-send is not a blank board.
        """
        with self.lock:
            self.characters = None
            self.text = None
            self.generation += 1
