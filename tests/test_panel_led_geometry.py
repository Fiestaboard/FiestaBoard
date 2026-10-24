"""A TV's LED surface defines its authorable grid, independently of flap sizing."""

import pytest

from src.canvas.geometry import area_rect
from src.canvas.models import CanvasArea
from src.led.matrix import grid_layout
from src.panels.models import Panel


def screen_panel(**overrides):
    return Panel(name="TV", board_id="tv", render_style="led_matrix", matrix_layout="screen", **overrides)


def test_screen_led_grid_follows_pixels_and_font():
    from src.panels.geometry import resolve_panel_geometry

    large = resolve_panel_geometry(screen_panel())
    small = resolve_panel_geometry(screen_panel(matrix_font="3x5"))
    assert (large.width, large.height, large.cols, large.rows) == (192, 108, 32, 13)
    assert (small.width, small.height, small.cols, small.rows) == (192, 108, 48, 18)
    assert small.model["charset"] == "led_3x5"


@pytest.mark.parametrize("inches", [3, 32, 55, 85, 200])
def test_led_density_is_independent_of_physical_size(inches):
    from src.panels.geometry import resolve_panel_geometry

    g = resolve_panel_geometry(screen_panel(screen_diagonal_inches=inches, calibration_scale=1.1, matrix_pitch_mm=10))
    assert (g.width, g.height, g.cols, g.rows) == (192, 108, 32, 13)


@pytest.mark.parametrize("aspect, pixels", [((9, 16), (108, 192)), ((4, 3), (192, 144)), ((21, 9), (189, 81))])
def test_aspect_matched_surface_has_no_unusable_cell_columns(aspect, pixels):
    from src.panels.geometry import resolve_panel_geometry

    g = resolve_panel_geometry(screen_panel(screen_aspect_w=aspect[0], screen_aspect_h=aspect[1]))
    assert (g.width, g.height) == pixels
    raster = grid_layout(g.width, g.height, g.font)
    assert (raster.cols, raster.rows) == (g.cols, g.rows)
    full = area_rect(CanvasArea(row=1, col=1, rows=g.rows, cols=g.cols), ["all"], raster)
    assert (full.x, full.y, full.w, full.h) == (0, 0, g.width, g.height)


def test_legacy_led_uses_stored_grid_without_phantom_columns():
    from src.panels.geometry import resolve_panel_geometry

    p = Panel(name="Old TV", board_id="tv", render_style="led_matrix")
    g = resolve_panel_geometry(p, {"device_type": "panel", "grid_rows": 12, "grid_cols": 29})
    assert (g.cols, g.rows, g.width, g.height) == (29, 12, 174, 96)


def test_split_flap_keeps_physical_autofit():
    from src.panels.geometry import resolve_panel_geometry

    g = resolve_panel_geometry(Panel(name="Flaps", board_id="tv", screen_diagonal_inches=55, matrix_layout="screen"))
    assert (g.cols, g.rows, g.width, g.height) == (29, 12, None, None)


@pytest.mark.parametrize("aspect", [(100, 1), (1, 100)])
def test_impossible_screen_shape_is_rejected_not_clamped(aspect):
    from src.panels.geometry import PanelGeometryError, resolve_panel_geometry

    with pytest.raises(PanelGeometryError):
        resolve_panel_geometry(screen_panel(screen_aspect_w=aspect[0], screen_aspect_h=aspect[1]))


def test_key_changes_with_font_and_not_presentation():
    from src.panels.geometry import resolve_panel_geometry

    first = resolve_panel_geometry(screen_panel())
    assert first.key == resolve_panel_geometry(screen_panel(matrix_sizing="true_size", calibration_scale=1.1)).key
    assert first.key != resolve_panel_geometry(screen_panel(matrix_font="3x5")).key


def test_shared_renderer_fixtures_keep_corner_text_and_all_edge_canvas():
    import json
    from pathlib import Path

    from src.led import LED_FONTS, LedMatrixSpec, layout_message, rasterize

    fixture = json.loads((Path(__file__).parent / "fixtures/panel-led-geometry.json").read_text())
    for case in fixture["cases"]:
        grid = grid_layout(case["width"], case["height"], case["font"])
        assert (grid.rows, grid.cols, grid.origin_x, grid.origin_y) == (
            case["rows"],
            case["cols"],
            case["origin_x"],
            case["origin_y"],
        ), case["name"]
        edge_row = "X" + " " * (grid.cols - 2) + "X"
        message = "\n".join([edge_row] + ["" for _ in range(grid.rows - 2)] + [edge_row])
        frame = rasterize(layout_message(message, LedMatrixSpec(grid.width, grid.height, grid.font)))
        face = LED_FONTS[grid.font]
        # X has lit pixels at each corner; test all four corner cells.
        for row in (0, grid.rows - 1):
            for col in (0, grid.cols - 1):
                x = grid.origin_x + col * (face.glyph_width + face.spacing_x)
                y = grid.origin_y + row * (face.glyph_height + face.spacing_y)
                offset = (y * grid.width + x) * 3
                assert any(frame.pixels[offset : offset + 3]), case["name"]
        rect = area_rect(CanvasArea(row=1, col=1, rows=grid.rows, cols=grid.cols), ["all"], grid)
        assert (rect.x, rect.y, rect.w, rect.h) == (0, 0, grid.width, grid.height)
