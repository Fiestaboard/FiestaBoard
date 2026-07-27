"""Quiet Library transition plugin.

Updates the board with the minimum possible mechanical noise: the diff
between the current and target grids is applied one small batch of tiles
at a time, word by word, with a long pause between sends so only a few
split-flap modules are ever spinning at once.

The behavior is modeled after the split-flap board in the Qantas First
Class lounge at Sydney airport, which updates methodically one word at a
time to keep the room quiet.  Concept and algorithm by @wonkybutt
(PR #711), reimplemented on the transition-plugin SDK.

Algorithm:

1. Diff ``from_grid`` against ``to_grid`` cell by cell.
2. Group each row's changed cells into *word blocks*: a changed cell
   that lands on a non-blank target tile belongs to the word (maximal
   run of non-blank target tiles) containing it; a changed cell that
   becomes blank (clearing a leftover) attaches to the preceding word
   in the row (or the following word when the row starts with cleanup).
3. Split each block into micro-batches of at most ``batch_size`` tiles.
   A batch never spans two words.
4. Apply batches in reading order, yielding one frame per batch with
   ``step_delay_ms`` between sends.

The default 14.5s delay clears the Vestaboard hardware's internal flap
debounce window, so every batch is actually animated by the board rather
than coalesced or dropped.
"""

from collections.abc import Iterator
from typing import Any

from src.plugins.base import TransitionPluginBase

BLANK = 0

DEFAULT_BATCH_SIZE = 6
DEFAULT_STEP_DELAY_MS = 14_500


def _word_segments(row: list[int]) -> list[tuple[int, int]]:
    """Return (start, end) column spans of maximal non-blank runs in *row*.

    ``end`` is exclusive.  Blank is tile code 0.
    """
    segments: list[tuple[int, int]] = []
    start: int | None = None
    for col, code in enumerate(row):
        if code != BLANK and start is None:
            start = col
        elif code == BLANK and start is not None:
            segments.append((start, col))
            start = None
    if start is not None:
        segments.append((start, len(row)))
    return segments


def _group_row_changes(
    changed_cols: list[int],
    target_row: list[int],
) -> list[list[int]]:
    """Group a row's changed columns into ordered word blocks.

    Each block is a sorted list of columns that flip together (in
    batch-sized chunks).  Changed cells whose target is non-blank belong
    to the word containing them; cells being cleared to blank attach to
    the preceding word (or the following word when there is none), so
    trailing-space cleanup rides along with the word it trails.
    """
    if not changed_cols:
        return []

    segments = _word_segments(target_row)
    # Key: segment index, or -1 for "no word in this row at all".
    blocks: dict[int, list[int]] = {}

    def segment_for(col: int) -> int:
        preceding = -1
        for idx, (start, end) in enumerate(segments):
            if start <= col < end:
                return idx
            if end <= col:
                preceding = idx
            else:
                # Segment starts after col: attach leading cleanup to it
                # only when no word precedes.
                return preceding if preceding != -1 else idx
        return preceding

    for col in changed_cols:
        blocks.setdefault(segment_for(col), []).append(col)

    return [sorted(blocks[key]) for key in sorted(blocks)]


class QuietLibraryTransition(TransitionPluginBase):
    """Word-by-word micro-batched diff for near-silent board updates."""

    @property
    def plugin_id(self) -> str:
        return "quiet_library"

    def generate_frames(
        self,
        from_grid: list[list[int]],
        to_grid: list[list[int]],
        device: Any,
        config: dict[str, Any],
    ) -> Iterator[tuple[list[list[int]], int]]:
        batch_size = max(1, int(config.get("batch_size", DEFAULT_BATCH_SIZE)))
        step_delay_ms = max(0, int(config.get("step_delay_ms", DEFAULT_STEP_DELAY_MS)))

        rows = len(to_grid)
        cols = len(to_grid[0]) if rows else 0
        if rows == 0 or cols == 0:
            return

        working = [list(row) for row in from_grid]
        # Tolerate a from-grid whose shape disagrees with the target (e.g.
        # a stale cache from a reconfigured board): pad/crop to the target.
        working = [
            [(working[r][c] if r < len(working) and c < len(working[r]) else BLANK) for c in range(cols)]
            for r in range(rows)
        ]

        for r in range(rows):
            changed = [c for c in range(cols) if working[r][c] != to_grid[r][c]]
            for block in _group_row_changes(changed, to_grid[r]):
                for i in range(0, len(block), batch_size):
                    for c in block[i : i + batch_size]:
                        working[r][c] = to_grid[r][c]
                    yield [list(row) for row in working], step_delay_ms
