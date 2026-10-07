"""Canvas geometry: character areas to panel pixels, text spans, grid retargets."""

import pytest

from src.canvas.geometry import (
    CanvasPlacement,
    PixelRect,
    area_rect,
    canvas_placement,
    covered_cells,
    free_spans,
    scale_area,
)
from src.canvas.models import Canvas, CanvasArea
from src.led.matrix import grid_layout

# A Divoom Pixoo 64 is a 64 x 64 matrix.
PIXOO_5X7 = grid_layout(64, 64, "5x7")
PIXOO_3X5 = grid_layout(64, 64, "3x5")


def _area(row, col, rows, cols):
    return CanvasArea(row=row, col=col, rows=rows, cols=cols)


def _canvas(row, col, rows, cols, *, bleed=(), scale=1, text="hide", cid="c"):
    return Canvas.model_validate(
        {
            "id": cid,
            "area": {"row": row, "col": col, "rows": rows, "cols": cols},
            "bleed": list(bleed),
            "scale": scale,
            "text": text,
            "content": {},
        }
    )


def test_pixoo_grids_are_the_ones_the_design_assumes():
    assert (PIXOO_5X7.rows, PIXOO_5X7.cols, PIXOO_5X7.origin_x, PIXOO_5X7.origin_y) == (8, 10, 2, 0)
    assert (PIXOO_3X5.rows, PIXOO_3X5.cols, PIXOO_3X5.origin_x, PIXOO_3X5.origin_y) == (10, 16, 0, 2)


def test_area_rect_5x7_top_left():
    # origin (2, 0), pitch 6 x 8, gutters 1: three cells wide is 3*6-1 = 17 px.
    assert area_rect(_area(1, 1, 2, 3), [], PIXOO_5X7) == PixelRect(2, 0, 17, 15)


def test_area_rect_3x5_interior():
    # origin (0, 2), pitch 4 x 6: col 3 starts at 8, row 2 at 2+6 = 8.
    assert area_rect(_area(2, 3, 2, 4), [], PIXOO_3X5) == PixelRect(8, 8, 15, 11)


def test_area_rect_matches_grid_cell_positions():
    # Every single-cell area is exactly that cell's glyph box.
    for grid, (gw, gh, px, py) in ((PIXOO_5X7, (5, 7, 6, 8)), (PIXOO_3X5, (3, 5, 4, 6))):
        for row in range(1, grid.rows + 1):
            for col in range(1, grid.cols + 1):
                rect = area_rect(_area(row, col, 1, 1), [], grid)
                assert rect == PixelRect(grid.origin_x + (col - 1) * px, grid.origin_y + (row - 1) * py, gw, gh)


def test_full_grid_without_bleed_leaves_the_margin():
    assert area_rect(_area(1, 1, 8, 10), [], PIXOO_5X7) == PixelRect(2, 0, 59, 63)


def test_full_grid_bleed_all_reaches_every_panel_edge():
    assert area_rect(_area(1, 1, 8, 10), ["all"], PIXOO_5X7) == PixelRect(0, 0, 64, 64)
    assert area_rect(_area(1, 1, 10, 16), ["all"], PIXOO_3X5) == PixelRect(0, 0, 64, 64)


def test_bleed_only_where_the_area_touches_the_grid_edge():
    # Interior area: bleed asked for on every side, honoured on none.
    assert area_rect(_area(2, 3, 2, 4), ["all"], PIXOO_3X5) == PixelRect(8, 8, 15, 11)
    # Left column, bleed left only.
    assert area_rect(_area(2, 1, 1, 2), ["left"], PIXOO_3X5) == PixelRect(0, 8, 7, 5)
    # Bottom-right corner, bleed right + bottom: x 60..64, y 56..64.
    assert area_rect(_area(10, 16, 1, 1), ["right", "bottom"], PIXOO_3X5) == PixelRect(60, 56, 4, 8)
    # Bleed top on the top row of the 3x5 grid (origin y 2) reaches y 0.
    assert area_rect(_area(1, 2, 1, 1), ["top"], PIXOO_3X5) == PixelRect(4, 0, 3, 7)


def test_area_is_clamped_to_the_grid():
    assert area_rect(_area(7, 9, 5, 5), [], PIXOO_5X7) == area_rect(_area(7, 9, 2, 2), [], PIXOO_5X7)


def test_area_outside_the_grid_has_no_rect():
    assert area_rect(_area(9, 1, 1, 1), [], PIXOO_5X7) is None
    assert area_rect(_area(1, 11, 1, 1), [], PIXOO_5X7) is None


def test_placement_scale_one_fills_the_rect():
    placed = canvas_placement(_canvas(1, 1, 2, 3), PIXOO_5X7)
    assert placed == CanvasPlacement(rect=PixelRect(2, 0, 17, 15), x=2, y=0, width=17, height=15, scale=1)


def test_placement_scale_two_is_floored_and_centred():
    placed = canvas_placement(_canvas(2, 3, 2, 4, scale=2), PIXOO_3X5)
    # 15 x 11 px rect -> 7 x 5 canvas pixels (14 x 10 px), centred: +0, +0.
    assert placed == CanvasPlacement(rect=PixelRect(8, 8, 15, 11), x=8, y=8, width=7, height=5, scale=2)


def test_placement_scale_centres_odd_leftovers():
    placed = canvas_placement(_canvas(1, 1, 8, 10, scale=3), PIXOO_5X7)
    # 59 x 63 -> 19 x 21 canvas px (57 x 63), x offset (59-57)//2 = 1.
    assert (placed.x, placed.y, placed.width, placed.height) == (3, 0, 19, 21)


def test_placement_too_small_for_the_scale_is_none():
    assert canvas_placement(_canvas(1, 1, 1, 1, scale=8), PIXOO_3X5) is None


def test_covered_cells_is_zero_based_and_includes_every_mode():
    hide = _canvas(1, 1, 1, 2, cid="a")
    flow = _canvas(3, 4, 1, 1, text="flow", cid="b")
    assert covered_cells([hide, flow], 3, 10) == {(0, 0), (0, 1), (2, 3)}


def test_covered_cells_are_clamped():
    assert covered_cells([_canvas(3, 9, 4, 4)], 3, 10) == {(2, 8), (2, 9)}


def test_free_spans_split_rows_around_flow_canvases():
    flow = _canvas(1, 4, 2, 2, text="flow")
    assert free_spans([flow], 3, 10) == [[(0, 3), (5, 10)], [(0, 3), (5, 10)], [(0, 10)]]


def test_free_spans_ignore_hide_canvases():
    assert free_spans([_canvas(1, 1, 3, 10)], 3, 10) == [[(0, 10)]] * 3


def test_free_spans_merge_overlapping_canvases_and_edges():
    a = _canvas(1, 1, 1, 3, text="flow", cid="a")
    b = _canvas(1, 3, 1, 2, text="flow", cid="b")
    c = _canvas(1, 9, 1, 2, text="flow", cid="c")
    assert free_spans([a, b, c], 1, 10) == [[(4, 8)]]


def test_free_spans_fully_covered_row_is_empty():
    assert free_spans([_canvas(1, 1, 1, 10, text="flow")], 2, 10) == [[], [(0, 10)]]


@pytest.mark.parametrize(
    ("area", "old", "new", "expected"),
    [
        ((1, 1, 4, 5), (8, 10), (10, 16), (1, 1, 5, 8)),
        ((8, 10, 1, 1), (8, 10), (10, 16), (10, 15, 1, 2)),
        ((10, 16, 1, 1), (10, 16), (8, 10), (8, 10, 1, 1)),
        ((1, 1, 8, 10), (8, 10), (10, 16), (1, 1, 10, 16)),
        # Rounding would run past the bottom: clamped to the grid.
        ((3, 1, 2, 1), (4, 10), (3, 10), (3, 1, 1, 1)),
        # Tiny areas never vanish.
        ((1, 1, 1, 1), (10, 16), (3, 10), (1, 1, 1, 1)),
    ],
)
def test_scale_area(area, old, new, expected):
    scaled = scale_area(_area(*area), old, new)
    assert (scaled.row, scaled.col, scaled.rows, scaled.cols) == expected
