"""A one-row LED board works end to end in the LED stack.

The LED floor is 1 x 5 characters, so a 32 x 8 Ulanzi TC001 is a 1 x 8
board in the 3x5 face and 1 x 5 in the 5x7 one. Pinned here: layout and
rasterising on one row, every LED transition on it, the text size switch
moving such a model between its two grids, a page taller than the board,
and a pixel canvas covering the whole matrix.
"""

from __future__ import annotations

import pytest

from src.fiestaui import builtin_device_models
from src.led import LedMatrixSpec, layout_message, rasterize
from src.led.matrix import LedBitmapLayer, model_with_led_font
from src.led.transitions import LED_TRANSITION_KINDS, plan_transition, transition_frames
from src.outputs.board_profile import board_font
from src.outputs.geometry import model_cell_grid

TC001_3X5 = LedMatrixSpec(32, 8, "3x5")
TC001_5X7 = LedMatrixSpec(32, 8, "5x7")


def _lit_rows(frame) -> set[int]:
    w = frame.width
    return {
        y for y in range(frame.height) for x in range(w) if any(frame.pixels[(y * w + x) * 3 : (y * w + x) * 3 + 3])
    }


def test_a_32x8_matrix_lays_out_one_row_of_8_at_3x5():
    layout = layout_message("SUNNY 72", TC001_3X5)
    assert (layout.grid.rows, layout.grid.cols) == (1, 8)
    frame = rasterize(layout)
    assert (frame.width, frame.height) == (32, 8)
    assert len(frame.pixels) == 32 * 8 * 3
    # Centred: (8 - 5) // 2 == 1, so the glyphs sit on y 1-5.
    assert layout.grid.origin_y == 1
    assert _lit_rows(frame) == {1, 2, 3, 4, 5}
    assert layout.text == "SUNNY 72"


def test_a_32x8_matrix_lays_out_one_row_of_5_at_5x7():
    layout = layout_message("SUNNY", TC001_5X7)
    assert (layout.grid.rows, layout.grid.cols) == (1, 5)
    frame = rasterize(layout)
    assert (frame.width, frame.height) == (32, 8)
    assert layout.grid.origin_y == 0
    assert _lit_rows(frame) == {0, 1, 2, 3, 4, 5, 6}
    assert layout.text == "SUNNY"


@pytest.mark.parametrize("kind", LED_TRANSITION_KINDS)
def test_every_led_transition_runs_on_a_1x8_board(kind):
    before = layout_message("HELLO", TC001_3X5)
    after = layout_message("WORLD", TC001_3X5)
    transition = plan_transition(before, after, kind)
    frames = transition_frames(transition)
    assert len(frames) >= 1
    for frame in frames:
        assert (frame.width, frame.height) == (32, 8)
        assert len(frame.pixels) == 32 * 8 * 3
    assert frames[-1].pixels == rasterize(after).pixels
    # A one-row board still animates: something lies between the two frames.
    assert transition.duration_ms > 0
    assert len(frames) > 1


def _tc001_with_font_choice() -> dict:
    model = dict(builtin_device_models()["ulanzi_tc001_awtrix"])
    model["layoutOptions"] = {**model["layoutOptions"], "font": {"allowed": ["3x5", "5x7"], "default": "3x5"}}
    return model


def test_the_font_switch_moves_a_32x8_model_between_1x8_and_1x5():
    model = _tc001_with_font_choice()

    large = board_font({"id": "b1", "output_config": {"font": "5x7"}, "grid_rows": 1, "grid_cols": 8}, model)
    assert large == "5x7"
    assert model_cell_grid(model_with_led_font(model, large)) == (1, 5)

    small = board_font({"id": "b2", "output_config": {"font": "3x5"}, "grid_rows": 1, "grid_cols": 5}, model)
    assert small == "3x5"
    assert model_cell_grid(model_with_led_font(model, small)) == (1, 8)

    # Saved before the choice existed: the face whose grid is the stored one.
    assert board_font({"id": "b3", "output_config": {}, "grid_rows": 1, "grid_cols": 5}, model) == "5x7"
    assert board_font({"id": "b4", "output_config": {}, "grid_rows": 1, "grid_cols": 8}, model) == "3x5"


def test_a_page_longer_than_one_row_is_cut_to_the_first_row():
    layout = layout_message("HELLO\nWORLD\nAGAIN", TC001_3X5)
    assert (layout.grid.rows, layout.grid.cols) == (1, 8)
    assert layout.text == "HELLO"
    assert rasterize(layout).pixels == rasterize(layout_message("HELLO", TC001_3X5)).pixels


def test_a_canvas_layer_covers_all_32x8_pixels():
    # Every pixel its own colour, fully opaque, so each frame pixel names its source.
    rgba = bytearray()
    expected = bytearray()
    for y in range(8):
        for x in range(32):
            rgb = (x * 8 + 1, y * 32 + 1, 200)
            rgba += bytes((*rgb, 255))
            expected += bytes(rgb)
    layer = LedBitmapLayer(x=0, y=0, width=32, height=8, rgba=bytes(rgba))
    layout = layout_message("SUNNY 72", TC001_3X5, layers=[layer])
    assert (layout.grid.rows, layout.grid.cols) == (1, 8)
    frame = rasterize(layout)
    assert frame.pixels == bytes(expected)
