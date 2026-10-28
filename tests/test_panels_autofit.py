"""Tests for the FiestaPanel auto-fit grid calculation.

The grid is sized so each flap renders at real-world scale: column pitch
anchored to the Vestaboard Note (24.5" / 15 columns), row pitch following
the renderer's invariant tile geometry (row pitch / col pitch = 1.145/0.845).
"""

import math

import pytest

from src.devices import MAX_GRID_COLS, MAX_GRID_ROWS, MIN_GRID_COLS, MIN_GRID_ROWS
from src.panels.autofit import (
    COL_PITCH_IN,
    ROW_PITCH_IN,
    compute_autofit_grid,
    screen_dimensions_in,
)


class TestConstants:
    def test_col_pitch_matches_note_unit(self):
        assert pytest.approx(24.5 / 15) == COL_PITCH_IN

    def test_row_pitch_follows_renderer_geometry(self):
        # tile w=0.70h gutter=0.145h → col pitch 0.845h, row pitch 1.145h
        assert pytest.approx(COL_PITCH_IN * (1.145 / 0.845)) == ROW_PITCH_IN


class TestScreenDimensions:
    def test_16_9_diagonal_decomposition(self):
        w, h = screen_dimensions_in(65)
        assert w == pytest.approx(65 * 16 / math.hypot(16, 9))
        assert h == pytest.approx(65 * 9 / math.hypot(16, 9))
        assert math.hypot(w, h) == pytest.approx(65)


class TestComputeAutofitGrid:
    """The grid is fit per character, not per Note block.

    A 55" TV is 47.9" wide: that holds 29 columns at Note pitch, but only one
    whole 15-column Note block — fitting in blocks left half the screen dark.
    """

    def test_returns_rows_and_cols(self):
        grid = compute_autofit_grid(55)
        assert (grid.rows, grid.cols) == (12, 29)

    def test_55_inch_tv_fills_the_width_a_note_block_fit_wasted(self):
        assert compute_autofit_grid(55).cols == 29

    def test_columns_are_not_rounded_to_note_blocks(self):
        assert compute_autofit_grid(65) == (14, 34)

    def test_rows_are_not_rounded_to_note_blocks(self):
        assert compute_autofit_grid(32) == (7, 17)

    def test_43_inch_tv(self):
        assert compute_autofit_grid(43) == (9, 22)

    def test_85_inch_tv(self):
        assert compute_autofit_grid(85) == (18, 45)

    def test_3_inch_pocket_screen_gets_a_note_sized_grid(self):
        """The smallest supported panel still gets a Note-sized grid; the
        viewer shrinks it to fit rather than cropping it."""
        assert compute_autofit_grid(3) == (MIN_GRID_ROWS, MIN_GRID_COLS) == (3, 15)

    def test_a_screen_narrower_than_a_note_keeps_note_width(self):
        # 24" holds 12 columns; every plugin is authored for >= 15.
        assert compute_autofit_grid(24) == (5, MIN_GRID_COLS)
        # Literally 15: the 3x10 floor is for LED boards in pixels, not panels.
        assert compute_autofit_grid(24) == (5, 15)

    def test_largest_supported_screen_fits_without_clamping(self):
        assert compute_autofit_grid(200) == (44, 106)

    def test_gigantic_screen_clamps_to_the_grid_maximum(self):
        assert compute_autofit_grid(500) == (MAX_GRID_ROWS, MAX_GRID_COLS)

    def test_rejects_non_positive_diagonal(self):
        with pytest.raises(ValueError):
            compute_autofit_grid(0)


class TestAspectRatios:
    """Non-16:9 screens (issue: aspect-aware panel setup).

    These example cases are mirrored VERBATIM in
    web/src/__tests__/panel-scale.test.ts (computeAutofitGrid parity) — the
    editor previews the grid with the TS twin, so drift between the two
    mirrors must fail one of the suites.
    """

    def test_ultrawide_21_9_55_inch(self):
        assert compute_autofit_grid(55, 21, 9) == (9, 30)

    def test_portrait_9_16_55_inch(self):
        assert compute_autofit_grid(55, 9, 16) == (21, 16)

    def test_portrait_9_16_200_inch(self):
        assert compute_autofit_grid(200, 9, 16) == (78, 60)

    def test_4_3_signage_40_inch(self):
        assert compute_autofit_grid(40, 4, 3) == (10, 19)

    def test_default_aspect_is_16_9(self):
        assert compute_autofit_grid(65) == compute_autofit_grid(65, 16, 9)

    def test_rejects_non_positive_aspect(self):
        with pytest.raises(ValueError):
            compute_autofit_grid(55, 0, 9)
        with pytest.raises(ValueError):
            compute_autofit_grid(55, 16, -1)
