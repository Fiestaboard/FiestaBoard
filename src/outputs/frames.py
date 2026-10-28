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

**Rich cells** (``cells`` / ``last_cells``) ride beside the grid for an
output that takes them (an output plugin with a rich character set, see
:mod:`src.outputs.cells`): :meth:`matches_frame` is then colour-aware —
the same flaps recoloured are a different frame — and layer-aware: rich
cells carry the page's pixel-canvas layers (``cells.layers``), so a canvas
change alone is a different frame too. Every other board stores none, and
for them :meth:`matches_frame` is :meth:`matches`.

Sub-unit caches stay with the driver: a local note array keeps one per tile
so a retry re-posts only the tiles that failed (plan D3).

Every grid is copied on the way in. The ``characters`` and ``last_frame``
attributes hand back the stored list itself; callers treat it as read-only.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cells import RichCellFrame

Grid = list[list[int]]


def _copy(grid: Grid) -> Grid:
    return [row[:] for row in grid]


class FrameCache:
    """One board's dedupe cache and last-frame store."""

    def __init__(self) -> None:
        # Re-entrant so a driver can hold it across check-then-record (the
        # virtual board client does) while the record methods take it too.
        self.lock = threading.RLock()
        self.characters: Grid | None = None
        self.text: str | None = None
        self.generation: int = 0
        self.last_frame: Grid | None = None
        self.last_sent_at: float | None = None
        #: The rich cells of ``characters`` / ``last_frame``, when the write
        #: carried them; else ``None``. Treated as immutable.
        self.cells: RichCellFrame | None = None
        self.last_cells: RichCellFrame | None = None

    # --- dedupe ------------------------------------------------------------------

    def matches(self, characters: Grid) -> bool:
        """True when *characters* equals what the board is known to show."""
        with self.lock:
            return self.characters == characters

    def matches_frame(self, characters: Grid, cells: RichCellFrame | None) -> bool:
        """True when *characters* and its rich *cells* (colour-aware) both
        equal what the board is known to show. With no cells on either side
        this is :meth:`matches`."""
        from .cells import cells_equal

        with self.lock:
            return self.characters == characters and cells_equal(self.cells, cells)

    def matches_text(self, text: str) -> bool:
        """True when *text* equals the text message the board is known to show."""
        with self.lock:
            return self.text == text

    def snapshot(self) -> tuple[Grid | None, int]:
        """``(characters, generation)`` read together."""
        with self.lock:
            return self.characters, self.generation

    def record_sent(self, characters: Grid, *, at: float | None = None, cells: RichCellFrame | None = None) -> None:
        """A device write of *characters* (and its rich *cells*, if it carried
        any) succeeded.

        Updates both the dedupe cache and the last-frame store.
        """
        with self.lock:
            self.cells = cells
            self.last_cells = cells
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
            self.cells = None
            self.generation += 1

    def record_read(self, characters: Grid) -> None:
        """A read-back says the board shows *characters* (cache sync).

        Only the dedupe cache moves: FiestaBoard did not send this frame.
        """
        with self.lock:
            self.characters = _copy(characters)
            self.cells = None
            self.text = None
            self.generation += 1

    # --- the last-frame store ----------------------------------------------------

    def last_frame_shaped(self, rows: int, cols: int) -> Grid | None:
        """A copy of the last frame sent, if it is *rows* x *cols*; else ``None``.

        The stale-shape refusal: a board re-fit to a new grid (a FiestaPanel
        TV-size change) must never be served the frame it showed at the old
        size — the viewer would render mismatched content until the next send.
        """
        with self.lock:
            frame = self.last_frame
            if frame is None or len(frame) != rows or any(len(row) != cols for row in frame):
                return None
            return _copy(frame)

    def last_cells_shaped(self, rows: int, cols: int) -> RichCellFrame | None:
        """The rich cells of the last frame sent, under the same stale-shape
        refusal as :meth:`last_frame_shaped`; ``None`` when it carried none."""
        from .cells import RichCells, frame_layers

        with self.lock:
            cells = self.last_cells
            if cells is None or len(cells) != rows or any(len(row) != cols for row in cells):
                return None
            return RichCells((row[:] for row in cells), frame_layers(cells))

    def clear(self) -> None:
        """Release everything: the dedupe cache *and* the last-frame store.

        For a board whose frames must not outlive it — a deleted panel, or one
        re-fit to a new grid. A forced re-send uses :meth:`forget` instead.
        """
        with self.lock:
            self.characters = None
            self.cells = None
            self.text = None
            self.generation += 1
            self.last_frame = None
            self.last_sent_at = None
            self.cells = None
            self.last_cells = None

    def forget(self) -> None:
        """Clear the dedupe cache so the next send goes through.

        The last-frame store survives: forcing a re-send is not a blank board.
        """
        with self.lock:
            self.characters = None
            self.text = None
            self.generation += 1
