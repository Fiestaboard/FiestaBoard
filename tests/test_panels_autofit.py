"""Tests for the FiestaPanel auto-fit grid calculation.

The grid is sized so each flap renders at real-world scale: column pitch
anchored to the Vestaboard Note (24.5" / 15 columns), row pitch following
the renderer's invariant tile geometry (row pitch / col pitch = 1.145/0.845).
"""

import math

import pytest

from src.panels.autofit import (
    BLOCK_HEIGHT_IN,
    BLOCK_WIDTH_IN,
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

    def test_block_dimensions(self):
        assert pytest.approx(15 * COL_PITCH_IN) == BLOCK_WIDTH_IN
        assert pytest.approx(3 * ROW_PITCH_IN) == BLOCK_HEIGHT_IN


class TestScreenDimensions:
    def test_16_9_diagonal_decomposition(self):
        w, h = screen_dimensions_in(65)
        assert w == pytest.approx(65 * 16 / math.hypot(16, 9))
        assert h == pytest.approx(65 * 9 / math.hypot(16, 9))
        assert math.hypot(w, h) == pytest.approx(65)


class TestComputeAutofitGrid:
    def test_65_inch_tv(self):
        # 56.65" × 31.87" usable → 2 blocks wide (49"), 4 blocks tall (26.6")
        assert compute_autofit_grid(65) == (2, 4)

    def test_43_inch_tv(self):
        assert compute_autofit_grid(43) == (1, 3)

    def test_85_inch_tv(self):
        assert compute_autofit_grid(85) == (3, 6)

    def test_3_inch_pocket_screen_gets_one_block(self):
        """The smallest supported panel still gets a full Note block; the
        viewer shrinks it to fit rather than cropping it."""
        assert compute_autofit_grid(3) == (1, 1)

    def test_tiny_screen_clamps_to_one_block(self):
        assert compute_autofit_grid(10) == (1, 1)

    def test_gigantic_screen_clamps_to_max_notes_per_axis(self):
        wide, tall = compute_autofit_grid(200)
        assert wide <= 8
        assert tall <= 8

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
        assert compute_autofit_grid(55, 21, 9) == (2, 3)

    def test_portrait_9_16_55_inch(self):
        assert compute_autofit_grid(55, 9, 16) == (1, 7)

    def test_4_3_signage_40_inch(self):
        assert compute_autofit_grid(40, 4, 3) == (1, 3)

    def test_default_aspect_is_16_9(self):
        assert compute_autofit_grid(65) == compute_autofit_grid(65, 16, 9)

    def test_rejects_non_positive_aspect(self):
        with pytest.raises(ValueError):
            compute_autofit_grid(55, 0, 9)
        with pytest.raises(ValueError):
            compute_autofit_grid(55, 16, -1)
