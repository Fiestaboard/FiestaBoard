"""Optional device-owned page rotation, independent of any device protocol."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from .cells import RichCellFrame, cells_equal


@dataclass(frozen=True, eq=False)
class NativePlaylistEntry:
    """One page snapshot. ``duration_ms=0`` uses the output's single-page default.

    The wrapper is frozen; cells are an owned deep copy, including canvas
    layers. Plugins must treat this copy as read-only, like a ``write_cells``
    frame. Repeated page ids are valid and retain their ordered occurrences.
    """

    page_id: str
    cells: RichCellFrame
    duration_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.page_id, str) or not self.page_id:
            raise ValueError("A native playlist entry needs a page id")
        if type(self.duration_ms) is not int or self.duration_ms < 0:
            raise ValueError("Native playlist duration must be a nonnegative integer in milliseconds")
        if not self.cells or not self.cells[0] or any(len(row) != len(self.cells[0]) for row in self.cells):
            raise ValueError("Native playlist cells must be a nonempty rectangular grid")
        object.__setattr__(self, "cells", copy.deepcopy(self.cells))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NativePlaylistEntry):
            return NotImplemented
        return (
            self.page_id == other.page_id
            and self.duration_ms == other.duration_ms
            and cells_equal(self.cells, other.cells)
        )


@dataclass(frozen=True)
class NativePlaylist:
    """An ordered board snapshot; an empty entries tuple retires owned slots.

    ``reference_id`` remains the configured page/collection reference. Sync
    success says the playlist is installed, never which member is visible.
    """

    board_id: str
    reference_id: str
    entries: tuple[NativePlaylistEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.board_id, str) or not self.board_id:
            raise ValueError("A native playlist needs a board id")
        if not isinstance(self.reference_id, str) or not self.reference_id:
            raise ValueError("A native playlist needs a reference id")
        entries = tuple(self.entries)
        if any(not isinstance(entry, NativePlaylistEntry) for entry in entries):
            raise ValueError("Native playlist entries must be NativePlaylistEntry snapshots")
        object.__setattr__(self, "entries", entries)


@dataclass(frozen=True)
class NativePageSelection:
    """Actual device selection. ``page_id=None`` means unknown or foreign.

    ``DevicePoll.native_selection=None`` instead means no selection feedback
    arrived; core retains the previous known selection in that case.
    """

    page_id: str | None
