"""Slot machine transition plugin.

Each column "spins" through a sequence of random tile codes (mimicking
a flap reel cycling) before locking on the target column.  Columns lock
left-to-right with a configurable stagger so the whole board settles in
a cascade rather than all at once.

Unchanged tiles still spin -- the visual effect is what we're after, and
the noise / mechanical wear is a deliberate trade for the spectacle.
The default cap of 300 frames and 60-second runtime keep things bounded.
"""

import random
from collections.abc import Iterator
from typing import Any

from src.plugins.base import TransitionPluginBase

# Char codes we'll sample for the spin animation.  Letters (1-26) and
# digits (27-36) read as natural slot-reel content; we deliberately skip
# the color tiles (63-71) so spinning columns never flash giant blocks
# of color in the middle of plain text.
_SPIN_CODES = list(range(1, 37))


class SlotMachineTransition(TransitionPluginBase):
    """Per-column flap-reel spin transition."""

    @property
    def plugin_id(self) -> str:
        return "slot_machine"

    def generate_frames(
        self,
        from_grid: list[list[int]],
        to_grid: list[list[int]],
        device: Any,
        config: dict[str, Any],
    ) -> Iterator[tuple[list[list[int]], int]]:
        spin_frames = max(1, int(config.get("spin_frames", 6)))
        column_stagger = max(0, int(config.get("column_stagger", 1)))
        frame_interval_ms = max(0, int(config.get("frame_interval_ms", 80)))
        seed = config.get("seed") or 0

        rows = len(to_grid)
        cols = len(to_grid[0]) if rows else 0
        if rows == 0 or cols == 0:
            return

        rng = random.Random(seed) if seed else random.Random()

        # Per-column lock frame: column c locks at frame ``c * stagger + spin_frames``.
        # The transition runs until the last column has locked.
        lock_at = [c * column_stagger + spin_frames for c in range(cols)]
        last_lock = lock_at[-1] if lock_at else 0

        for frame_idx in range(1, last_lock + 1):
            frame = []
            for r in range(rows):
                row_chars = []
                for c in range(cols):
                    if frame_idx >= lock_at[c]:
                        # Column has locked -- show the target tile.
                        row_chars.append(to_grid[r][c])
                    else:
                        # Still spinning -- pick a random tile each frame.
                        row_chars.append(rng.choice(_SPIN_CODES))
                frame.append(row_chars)
            yield frame, frame_interval_ms
