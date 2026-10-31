"""A grid page drawn at its own text size (face) on an LED board, as one
opaque full-frame pixel layer (design section 7, delivery via section 6)."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.canvas.layer import CanvasLayer
from src.led.matrix import LedLayoutOptions, LedMatrixSpec, layout_message, rasterize
from src.led.page_frame import full_frame_layer, is_full_frame_layer, render_grid_page_frame, send_layers
from src.outputs.display_profile import DisplayProfile

#: A Pixoo 64 set to Large text (5x7): 8 x 10 cells. Its 3x5 grid is 10 x 16,
#: starting at pixel (0, 2); its 5x7 grid starts at (2, 0).
PIXOO_5X7 = DisplayProfile(
    technology="led_matrix",
    device_model="divoom_pixoo64",
    charset="led_5x7",
    color="rgb",
    font="5x7",
    rows=8,
    cols=10,
    width=64,
    height=64,
)


def px(frame, x, y):
    i = (y * frame.width + x) * 3
    return frame.pixels[i : i + 3]


def test_a_10x16_page_draws_in_the_3x5_face_on_a_5x7_board():
    frame = render_grid_page_frame("H", 10, 16, "3x5", PIXOO_5X7)
    assert (frame.width, frame.height) == (64, 64) and px(frame, 0, 2) != b"\0\0\0"


def test_a_grid_the_face_does_not_produce_is_refused():
    with pytest.raises(ValueError, match="10x16"):
        render_grid_page_frame("H", 8, 10, "3x5", PIXOO_5X7)


def test_the_pages_canvas_layers_paint_over_the_text():
    red = CanvasLayer(x=0, y=2, w=1, h=1, rgba=bytes([255, 0, 0, 255]))
    assert px(render_grid_page_frame("H", 10, 16, "3x5", PIXOO_5X7, [red]), 0, 2) == bytes([255, 0, 0])


def test_a_monochrome_board_lights_text_in_its_panel_colour():
    mono = replace(PIXOO_5X7, monochrome="#ff0000", color="mono")
    assert px(render_grid_page_frame("H", 10, 16, "3x5", mono), 0, 2) == bytes([255, 0, 0])


def test_alternate_face_mono_frame_survives_final_adapter_composition():
    mono = replace(PIXOO_5X7, monochrome="#ff3b1f", color="mono")
    expected = render_grid_page_frame("H", 10, 16, "3x5", mono)
    layers = send_layers(SimpleNamespace(formatted="H", layers=[], face="3x5"), 10, 16, mono)
    final = rasterize(
        layout_message(
            "",
            LedMatrixSpec(64, 64, "5x7"),
            LedLayoutOptions(monochrome=mono.monochrome),
            layers=layers,
        )
    )
    assert any(expected.pixels)
    assert final.pixels == expected.pixels


def test_the_full_frame_layer_covers_the_matrix_opaquely_black_included():
    layer = full_frame_layer(render_grid_page_frame("", 10, 16, "3x5", PIXOO_5X7))
    assert (layer.x, layer.y, layer.w, layer.h) == (0, 0, 64, 64)
    assert set(layer.rgba[3::4]) == {255} and layer.rgba[:3] == b"\0\0\0"


def test_a_canvas_layer_is_not_a_full_frame():
    assert not is_full_frame_layer(CanvasLayer(0, 0, 64, 64, bytes(64 * 64 * 4)), 64, 64)  # alpha 0


def test_send_layers_wraps_a_face_result_and_passes_others_through():
    face = SimpleNamespace(formatted="H", layers=[], face="3x5")
    plain = SimpleNamespace(formatted="H", layers=["L"], face=None)
    assert is_full_frame_layer(send_layers(face, 10, 16, PIXOO_5X7)[0], 64, 64)
    assert send_layers(plain, 8, 10, PIXOO_5X7) == ["L"]
