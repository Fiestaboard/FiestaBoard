"""Simple dissolve transition plugin.

Reveals the target grid by flipping tiles in a randomized order.  Only the
tiles that actually differ between ``from_grid`` and ``to_grid`` are
shuffled, so unchanged content stays in place.
"""

import random
from collections.abc import Iterator
from typing import Any

from src.plugins.base import TransitionPluginBase


class SimpleDissolveTransition(TransitionPluginBase):
    """Random-order tile reveal from the current grid to the target grid."""

    @property
    def plugin_id(self) -> str:
        return "simple_dissolve"

    def generate_frames(
        self,
        from_grid: list[list[int]],
        to_grid: list[list[int]],
        device: Any,
        config: dict[str, Any],
    ) -> Iterator[tuple[list[list[int]], int]]:
        tiles_per_frame = max(1, int(config.get("tiles_per_frame", 6)))
        frame_interval_ms = max(0, int(config.get("frame_interval_ms", 100)))
        seed = config.get("seed") or 0

        rows = len(to_grid)
        cols = len(to_grid[0]) if rows else 0
        if rows == 0 or cols == 0:
            return

        # Collect positions that actually differ.  A new instance of
        # ``random.Random`` is used so each transition has its own shuffle
        # state independent of the global RNG.
        diff_positions: list[tuple[int, int]] = []
        for r in range(rows):
            row_to = to_grid[r]
            row_from = from_grid[r] if r < len(from_grid) else [0] * cols
            for c in range(cols):
                src = row_from[c] if c < len(row_from) else 0
                if src != row_to[c]:
                    diff_positions.append((r, c))

        if not diff_positions:
            # Nothing to do; runner will still snap to to_grid.
            return

        rng = random.Random(seed) if seed else random.Random()
        rng.shuffle(diff_positions)

        working = [list(row) for row in from_grid] if from_grid else [[0] * cols for _ in range(rows)]
        # Right-pad / truncate working to match to_grid shape in case the
        # caller handed us a mismatched from_grid (defensive only).
        if len(working) != rows:
            working = [working[r] if r < len(working) else [0] * cols for r in range(rows)]
        for r in range(rows):
            if len(working[r]) != cols:
                working[r] = (working[r] + [0] * cols)[:cols]

        flipped = 0
        total = len(diff_positions)
        while flipped < total:
            batch = diff_positions[flipped : flipped + tiles_per_frame]
            for r, c in batch:
                working[r][c] = to_grid[r][c]
            flipped += len(batch)
            yield [list(row) for row in working], frame_interval_ms
