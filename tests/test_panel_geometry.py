"""The "panel" device type: an explicit rows × cols grid (FiestaPanel boards).

Panels are sized per character from a TV, so their grids are not multiples
of a Note. Every geometry helper in src/devices.py must carry the explicit
grid through instead of silently falling back to a flagship.
"""

import pytest

from src.devices import (
    DEVICE_TYPES,
    MAX_GRID_COLS,
    MAX_GRID_ROWS,
    MIN_GRID_COLS,
    MIN_GRID_ROWS,
    BoardInstance,
    DeviceDimensions,
    Geometry,
    board_context_for,
    dimensions_of,
    geometry_of,
    is_panel,
    pages_compatible_with_board,
    resolve_dimensions,
    size_key,
)

VIRTUAL_PANEL = {"device_type": "panel", "api_mode": "virtual"}


class TestVocabulary:
    def test_panel_is_a_device_type(self):
        assert "panel" in DEVICE_TYPES

    def test_is_panel(self):
        assert is_panel("panel")
        assert not is_panel("note_array")


class TestResolveDimensions:
    def test_panel_resolves_its_explicit_grid(self):
        assert resolve_dimensions("panel", grid_rows=12, grid_cols=29) == DeviceDimensions(12, 29)

    def test_panel_grid_need_not_be_a_note_multiple(self):
        assert resolve_dimensions("panel", grid_rows=7, grid_cols=17) == (7, 17)

    def test_panel_ignores_notes(self):
        assert resolve_dimensions("panel", 4, 4, 12, 29) == (12, 29)

    def test_panel_without_a_grid_raises(self):
        with pytest.raises(ValueError, match="grid_rows"):
            resolve_dimensions("panel")

    def test_panel_with_one_axis_missing_raises(self):
        with pytest.raises(ValueError, match="grid_cols"):
            resolve_dimensions("panel", grid_rows=12)

    def test_panel_rejects_a_boolean_axis(self):
        with pytest.raises(ValueError):
            resolve_dimensions("panel", grid_rows=True, grid_cols=29)

    def test_panel_grid_is_clamped_to_one_note_minimum(self):
        assert resolve_dimensions("panel", grid_rows=1, grid_cols=5) == (MIN_GRID_ROWS, MIN_GRID_COLS)

    def test_panel_grid_is_clamped_to_the_maximum(self):
        assert resolve_dimensions("panel", grid_rows=500, grid_cols=500) == (MAX_GRID_ROWS, MAX_GRID_COLS)

    def test_grid_args_do_not_change_other_types(self):
        assert resolve_dimensions("flagship", grid_rows=12, grid_cols=29) == (6, 22)
        assert resolve_dimensions("note_array", 2, 1, 12, 29) == (3, 30)


class TestSizeKey:
    def test_panel_key_carries_the_grid(self):
        assert size_key("panel", grid_rows=12, grid_cols=29) == "panel:12x29"

    def test_two_panel_sizes_have_different_keys(self):
        assert size_key("panel", grid_rows=12, grid_cols=29) != size_key("panel", grid_rows=14, grid_cols=34)

    def test_panel_is_its_own_family_even_at_a_note_array_size(self):
        assert size_key("panel", grid_rows=12, grid_cols=30) != size_key("note_array", 2, 4)

    def test_panel_without_a_grid_falls_back_like_any_bad_value(self):
        assert size_key("panel") == "flagship:6x22"


class TestGeometryOf:
    def test_reads_a_board_dict(self):
        board = {"device_type": "panel", "grid_rows": 12, "grid_cols": 29}
        assert geometry_of(board) == Geometry("panel", 1, 1, 12, 29)

    def test_reads_an_object(self):
        board = BoardInstance.from_dict(
            {"device_type": "panel", "api_mode": "virtual", "grid_rows": 12, "grid_cols": 29}
        )
        assert geometry_of(board) == Geometry("panel", 1, 1, 12, 29)

    def test_defaults_for_an_empty_dict(self):
        assert geometry_of({}) == Geometry("flagship", 1, 1, None, None)

    def test_garbage_grid_values_read_as_missing(self):
        assert geometry_of({"device_type": "panel", "grid_rows": "x", "grid_cols": True}).grid_rows is None

    def test_dimensions_of_a_panel_board(self):
        assert dimensions_of({"device_type": "panel", "grid_rows": 9, "grid_cols": 22}) == (9, 22)


class TestCompatibility:
    def test_page_matching_the_panel_grid_is_compatible(self):
        page = {"device_type": "panel", "grid_rows": 12, "grid_cols": 29}
        board = {"device_type": "panel", "grid_rows": 12, "grid_cols": 29}
        assert pages_compatible_with_board(page, board)

    def test_page_for_another_panel_size_is_not(self):
        page = {"device_type": "panel", "grid_rows": 12, "grid_cols": 29}
        board = {"device_type": "panel", "grid_rows": 14, "grid_cols": 34}
        assert not pages_compatible_with_board(page, board)


class TestBoardContext:
    def test_plugins_see_the_panel_grid(self):
        ctx = board_context_for("panel", grid_rows=12, grid_cols=29)
        assert (ctx.device_type, ctx.rows, ctx.cols) == ("panel", 12, 29)


class TestBoardInstance:
    def test_round_trips_the_grid(self):
        data = BoardInstance.from_dict(
            {"device_type": "panel", "api_mode": "virtual", "grid_rows": 12, "grid_cols": 29}
        ).to_dict()
        restored = BoardInstance.from_dict(data)
        assert (restored.grid_rows, restored.grid_cols) == (12, 29)

    def test_panel_type_survives_normalization(self):
        board = BoardInstance.from_dict({**VIRTUAL_PANEL, "grid_rows": 12, "grid_cols": 29})
        assert board.device_type == "panel"

    def test_a_physical_board_cannot_be_a_panel(self):
        """No Vestaboard takes an arbitrary grid: only FiestaPanel's virtual boards are panels."""
        board = BoardInstance.from_dict({"device_type": "panel", "api_mode": "local", "grid_rows": 12, "grid_cols": 29})
        assert (board.device_type, board.grid_rows) == ("flagship", None)

    def test_a_panel_missing_its_grid_gets_the_minimum(self):
        board = BoardInstance.from_dict(VIRTUAL_PANEL)
        assert (board.grid_rows, board.grid_cols) == (MIN_GRID_ROWS, MIN_GRID_COLS)

    def test_a_panel_grid_is_clamped(self):
        board = BoardInstance.from_dict({**VIRTUAL_PANEL, "grid_rows": 1000, "grid_cols": 2})
        assert (board.grid_rows, board.grid_cols) == (MAX_GRID_ROWS, MIN_GRID_COLS)

    def test_non_panel_boards_drop_a_stale_grid(self):
        board = BoardInstance.from_dict({"device_type": "flagship", "grid_rows": 12, "grid_cols": 29})
        assert (board.grid_rows, board.grid_cols) == (None, None)

    def test_panel_draws_the_heart(self):
        board = BoardInstance.from_dict(
            {"device_type": "panel", "api_mode": "virtual", "grid_rows": 12, "grid_cols": 29, "code62_glyph": "degree"}
        )
        assert board.effective_code62_glyph == "heart"
