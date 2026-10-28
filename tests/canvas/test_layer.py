"""CanvasLayer serialisation and the end-to-end render_canvases entry point."""

import base64

import pytest

from src.canvas.layer import CanvasLayer, render_canvases
from src.canvas.models import Canvas
from src.fiestaui import builtin_device_models

MODELS = builtin_device_models()
PIXOO = MODELS["divoom_pixoo64"]  # 64 x 64, own font 3x5 -> 10 x 16 grid, origin (0, 2)


def _canvas(**overrides):
    data = {
        "id": "c",
        "area": {"row": 1, "col": 1, "rows": 1, "cols": 1},
        "content": {"size": [1, 1], "palette": {"r": "#f00"}, "pixels": ["r"]},
    }
    data.update(overrides)
    return Canvas.model_validate(data)


def test_layer_json_round_trip():
    layer = CanvasLayer(x=3, y=4, w=1, h=2, rgba=bytes([1, 2, 3, 4, 5, 6, 7, 8]))
    data = layer.to_json()
    # Keys match FiestaUI's LedBitmapLayer JSON: width / height, not w / h.
    assert data == {
        "x": 3,
        "y": 4,
        "width": 1,
        "height": 2,
        "rgba": base64.b64encode(bytes([1, 2, 3, 4, 5, 6, 7, 8])).decode(),
    }
    assert CanvasLayer.from_json(data) == layer


def test_layer_is_frozen():
    layer = CanvasLayer(x=0, y=0, w=1, h=1, rgba=bytes(4))
    with pytest.raises(AttributeError):
        layer.x = 1


def test_layer_rejects_a_wrong_byte_count():
    with pytest.raises(ValueError, match="4 bytes per pixel"):
        CanvasLayer(x=0, y=0, w=2, h=2, rgba=bytes(4))


def test_from_json_rejects_bad_base64():
    with pytest.raises(ValueError):
        CanvasLayer.from_json({"x": 0, "y": 0, "width": 1, "height": 1, "rgba": "!!"})


def test_render_on_a_pixel_model_places_the_layer_at_the_cell():
    layers, issues = render_canvases([_canvas()], PIXOO, {})
    assert issues == []
    (layer,) = layers
    # 3x5 cell (1, 1) is at (0, 2), 3 x 5 px; one red content pixel at
    # (0, 0) is letterboxed into the 3 x 5 canvas: 3 x 3 centred at y 1.
    assert (layer.x, layer.y, layer.w, layer.h) == (0, 2, 3, 5)
    red = bytes([255, 0, 0, 255])
    clear = bytes(4)
    assert layer.rgba == clear * 3 + red * 9 + clear * 3


def test_render_with_bleed_and_scale():
    canvas = _canvas(area={"row": 1, "col": 1, "rows": 10, "cols": 16}, bleed=["all"], scale=4)
    (layer,), _ = render_canvases([canvas], PIXOO, {})
    assert (layer.x, layer.y, layer.w, layer.h) == (0, 0, 64, 64)
    assert layer.rgba == bytes([255, 0, 0, 255]) * 64 * 64


def test_render_follows_the_board_font():
    (layer,), _ = render_canvases([_canvas()], PIXOO, {}, font="5x7")
    # 5x7 grid on 64 x 64: origin (2, 0), cell 5 x 7.
    assert (layer.x, layer.y, layer.w, layer.h) == (2, 0, 5, 7)


def test_render_keeps_canvas_order():
    a = _canvas(id="a", area={"row": 1, "col": 1, "rows": 1, "cols": 1})
    b = _canvas(id="b", area={"row": 2, "col": 2, "rows": 1, "cols": 1})
    layers, _ = render_canvases([a, b], PIXOO, {})
    assert [(layer.x, layer.y) for layer in layers] == [(0, 2), (4, 8)]


def test_render_uses_the_context_and_reports_issues():
    canvas = _canvas(
        content={
            "shapes": [
                {"type": "rect", "x": 0, "y": 0, "w": "{{bar.width}}", "h": 5, "fill": "#0f0"},
                {"type": "rect", "x": "{{nope.x}}", "y": 0, "w": 1, "h": 1, "fill": "#f00"},
            ]
        }
    )
    (layer,), issues = render_canvases([canvas], PIXOO, {"bar": {"width": 2}})
    green, clear = bytes([0, 255, 0, 255]), bytes(4)
    assert layer.rgba == (green * 2 + clear) * 5
    assert [(i.canvas_id, i.path) for i in issues] == [("c", "shapes[1].x")]


def test_canvas_outside_the_grid_is_an_issue_not_a_layer():
    layers, issues = render_canvases([_canvas(area={"row": 11, "col": 1, "rows": 1, "cols": 1})], PIXOO, {})
    assert layers == []
    assert issues[0].path == "area"
    assert "outside" in issues[0].message


def test_empty_canvas_still_yields_a_transparent_layer():
    canvas = _canvas(content=None, source="{{nothing.here}}")
    layers, issues = render_canvases([canvas], PIXOO, {})
    assert layers[0].rgba == bytes(3 * 5 * 4)
    assert issues[0].path == "source"


@pytest.mark.parametrize("model_id", ["vestaboard_flagship", "vestaboard_note", "vestaboard_panel"])
def test_non_pixel_models_get_no_layers(model_id):
    assert render_canvases([_canvas()], MODELS[model_id], {}) == ([], [])


def test_no_canvases():
    assert render_canvases([], PIXOO, {}) == ([], [])
    assert render_canvases(None, PIXOO, {}) == ([], [])
