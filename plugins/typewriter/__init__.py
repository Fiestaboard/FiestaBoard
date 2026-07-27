"""Typewriter transition plugin.

Reveals the target grid one tile at a time, left-to-right and top-to-bottom,
producing the classic "typewriter" effect.  The reveal moves through every
position on the board -- positions that are unchanged still tick by, so the
animation feels uniform regardless of how much content has actually changed.
"""

from collections.abc import Iterator
from typing import Any

from src.plugins.base import TransitionPluginBase


class TypewriterTransition(TransitionPluginBase):
    """Left-to-right, char-by-char reveal of the target grid."""

    @property
    def plugin_id(self) -> str:
        return "typewriter"

    def generate_frames(
        self,
        from_grid: list[list[int]],
        to_grid: list[list[int]],
        device: Any,
        config: dict[str, Any],
    ) -> Iterator[tuple[list[list[int]], int]]:
        chars_per_frame = max(1, int(config.get("chars_per_frame", 1)))
        frame_interval_ms = max(0, int(config.get("frame_interval_ms", 120)))

        rows = len(to_grid)
        cols = len(to_grid[0]) if rows else 0
        if rows == 0 or cols == 0:
            return

        # Copy the from-grid; we'll overwrite tiles one batch at a time as
        # the typewriter head sweeps across every position.
        working = [list(row) for row in from_grid]

        revealed = 0
        total = rows * cols
        while revealed < total:
            end = min(revealed + chars_per_frame, total)
            for idx in range(revealed, end):
                r, c = divmod(idx, cols)
                working[r][c] = to_grid[r][c]
            revealed = end
            yield [list(row) for row in working], frame_interval_ms
