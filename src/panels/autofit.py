"""Auto-fit grid calculation for FiestaPanel.

A panel's board is sized so each flap renders at real-world scale and the
grid fills as much of the screen as possible. Grids come in note-array
blocks (15 columns × 3 rows) because that is the shape every content tool
in the platform — page editor, schedules, template slicing, the board
renderer — already understands.

Physical anchoring:

- Column pitch comes from the real Vestaboard Note: a frameless Note unit
  is 24.5" wide for 15 columns → 1.6333" per column.
- Row pitch follows the renderer's invariant tile geometry (see FiestaUI
  board-metrics.ts: tile width = 0.70·h, gutter = 0.145·h in both axes),
  so column pitch = 0.845·h and row pitch = 1.145·h. Anchoring width to
  the physical column pitch fixes h, and the row pitch falls out as
  1.6333 × (1.145 / 0.845) ≈ 2.2132". Fitting rows with the renderer's
  own ratio (rather than the Note unit's bezel-heavy height) is what lets
  a uniform scale keep BOTH axes true on screen.

The screen's width/height are derived from the user-entered diagonal and
aspect ratio (default 16:9 — the overwhelmingly common TV shape); the
viewer's ±10% stretch-to-fill and the calibration nudge absorb small
deviations. A screen smaller than one Note block still gets a 1×1 grid,
which the viewer shrinks to fit (3" pocket displays).

``compute_autofit_grid`` is mirrored in ``web/src/lib/panel-scale.ts``
(computeAutofitGrid) so the panel editor can preview the grid live —
keep the two in lockstep (their tests share the same example cases).
"""

import math

from src.devices import MAX_NOTES_PER_AXIS, NOTE_COLS, NOTE_ROWS

# Real Vestaboard Note: 24.5" wide (frameless unit) for 15 columns.
NOTE_UNIT_WIDTH_IN = 24.5

# Renderer tile geometry (FiestaUI board-metrics.ts TILE_RATIOS).
_COL_PITCH_RATIO = 0.70 + 0.145  # tile width + gutter, in tile heights
_ROW_PITCH_RATIO = 1.0 + 0.145  # tile height + gutter, in tile heights

COL_PITCH_IN = NOTE_UNIT_WIDTH_IN / NOTE_COLS
ROW_PITCH_IN = COL_PITCH_IN * (_ROW_PITCH_RATIO / _COL_PITCH_RATIO)

BLOCK_WIDTH_IN = NOTE_COLS * COL_PITCH_IN
BLOCK_HEIGHT_IN = NOTE_ROWS * ROW_PITCH_IN

# Default screen aspect when only the diagonal is known.
_ASPECT_W = 16
_ASPECT_H = 9


def screen_dimensions_in(
    diagonal_inches: float,
    aspect_w: float = _ASPECT_W,
    aspect_h: float = _ASPECT_H,
) -> tuple[float, float]:
    """(width, height) in inches of an aspect_w:aspect_h screen of the given diagonal."""
    if diagonal_inches <= 0:
        raise ValueError(f"diagonal must be positive (got {diagonal_inches})")
    if aspect_w <= 0 or aspect_h <= 0:
        raise ValueError(f"aspect ratio must be positive (got {aspect_w}:{aspect_h})")
    hyp = math.hypot(aspect_w, aspect_h)
    return (
        diagonal_inches * aspect_w / hyp,
        diagonal_inches * aspect_h / hyp,
    )


def compute_autofit_grid(
    diagonal_inches: float,
    aspect_w: float = _ASPECT_W,
    aspect_h: float = _ASPECT_H,
) -> tuple[int, int]:
    """(notes_wide, notes_tall) of the largest true-scale grid that fits.

    Always returns at least 1×1 (a screen smaller than one Note block gets
    a Note-sized grid that the viewer shrinks to fit) and at most
    MAX_NOTES_PER_AXIS per axis.
    """
    width_in, height_in = screen_dimensions_in(diagonal_inches, aspect_w, aspect_h)

    def clamp(blocks: int) -> int:
        return max(1, min(MAX_NOTES_PER_AXIS, blocks))

    return (
        clamp(math.floor(width_in / BLOCK_WIDTH_IN)),
        clamp(math.floor(height_in / BLOCK_HEIGHT_IN)),
    )
