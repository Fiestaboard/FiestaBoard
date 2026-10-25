"""Canvas data model: what validates, every limit, and the messages people see."""

import pytest

from src.canvas.models import (
    MAX_CANVASES_PER_PAGE,
    MAX_PALETTE_KEYS,
    MAX_PIXEL_COLS,
    MAX_PIXEL_ROWS,
    MAX_SHAPES,
    Canvas,
    CanvasContent,
    RectShape,
    TextShape,
    parse_color,
    validate_page_canvases,
)
from src.led.matrix import BOARD_COLORS


def _canvas(**overrides):
    data = {"id": "sky", "area": {"row": 1, "col": 1, "rows": 2, "cols": 3}, "content": {}}
    data.update(overrides)
    return data


def _error(fn, *args, **kwargs) -> str:
    with pytest.raises(ValueError) as exc:
        fn(*args, **kwargs)
    return str(exc.value)


# --- A good canvas -----------------------------------------------------------


def test_full_example_from_the_design_validates():
    canvas = Canvas.model_validate(
        {
            "id": "sky",
            "area": {"row": 1, "col": 1, "rows": 4, "cols": 16},
            "bleed": ["top", "left", "right"],
            "scale": 1,
            "text": "flow",
            "content": {
                "size": [64, 32],
                "background": "#000000",
                "palette": {"k": "#000000", "y": "#ffcc00"},
                "shapes": [
                    {"type": "rect", "x": 0, "y": 0, "w": 4, "h": 4, "fill": "y"},
                    {"type": "circle", "cx": 8, "cy": 8, "r": 3, "stroke": "red"},
                    {"type": "ellipse", "cx": 8, "cy": 8, "rx": 3, "ry": 2, "fill": "#fff"},
                    {"type": "line", "x1": 0, "y1": 0, "x2": 5, "y2": 5, "stroke": "blue", "width": 2},
                    {"type": "polygon", "points": [[0, 0], [4, 0], [2, 3]], "fill": "green"},
                    {"type": "text", "x": 1, "y": 1, "text": "HI", "color": "white", "font": "3x5"},
                    {"type": "gradient", "from": "red", "to": "blue", "angle": 0},
                    {
                        "type": "rect",
                        "foreach": "{{scores.items}}",
                        "as": "p",
                        "if": "{{p.value > 0}}",
                        "x": "{{p.index * 2}}",
                        "y": 0,
                        "w": 1,
                        "h": "{{p.value}}",
                        "fill": '{{IF(p.value > 5, "red", "green")}}',
                    },
                ],
                "pixels": ["kkyy..", "..yykk"],
            },
            "source": "{{generative_ai_art.canvas}}",
        }
    )
    assert canvas.text == "flow"
    assert canvas.content.size == (64, 32)
    assert len(canvas.content.shapes) == 8
    assert canvas.content.shapes[-1].foreach == "{{scores.items}}"
    assert canvas.content.shapes[-1].as_ == "p"


def test_defaults():
    canvas = Canvas.model_validate(_canvas())
    assert canvas.bleed == []
    assert canvas.scale == 1
    assert canvas.text == "hide"
    assert canvas.source is None


def test_source_alone_is_enough():
    canvas = Canvas.model_validate({"id": "a", "area": {"row": 1, "col": 1, "rows": 1, "cols": 1}, "source": "{{x.y}}"})
    assert canvas.content is None


def test_neither_content_nor_source_is_refused():
    msg = _error(Canvas.model_validate, {"id": "a", "area": {"row": 1, "col": 1, "rows": 1, "cols": 1}})
    assert "needs content, a source, or both" in msg


def test_shape_fields_accept_expressions():
    shape = RectShape.model_validate({"type": "rect", "x": "{{a.b}}", "y": 1.5, "w": 2, "h": "{{= 1 + 1 }}"})
    assert shape.x == "{{a.b}}"
    assert shape.y == 1.5


# --- Ids, area, scale, text, bleed -------------------------------------------


@pytest.mark.parametrize("bad", ["", "Sky", "a b", "x" * 17, "sky!"])
def test_bad_ids_are_refused(bad):
    msg = _error(Canvas.model_validate, _canvas(id=bad))
    assert "canvas id" in msg and "a-z, 0-9, _ or -" in msg


def test_area_must_be_one_based_and_positive():
    msg = _error(Canvas.model_validate, _canvas(area={"row": 0, "col": 1, "rows": 1, "cols": 1}))
    assert "greater than or equal to 1" in msg
    msg = _error(Canvas.model_validate, _canvas(area={"row": 1, "col": 1, "rows": 0, "cols": 1}))
    assert "greater than or equal to 1" in msg


@pytest.mark.parametrize("scale", [0, 9])
def test_scale_is_one_to_eight(scale):
    msg = _error(Canvas.model_validate, _canvas(scale=scale))
    assert "scale" in msg


def test_text_mode_is_hide_or_flow():
    msg = _error(Canvas.model_validate, _canvas(text="wrap"))
    assert "'hide' or 'flow'" in msg


def test_bleed_sides():
    assert Canvas.model_validate(_canvas(bleed=["all"])).bleed == ["all"]
    msg = _error(Canvas.model_validate, _canvas(bleed=["up"]))
    assert "bleed" in msg


def test_unknown_canvas_field_is_refused():
    msg = _error(Canvas.model_validate, _canvas(colour="red"))
    assert "colour" in msg


# --- Page-level limits -------------------------------------------------------


def test_page_allows_eight_canvases():
    canvases = [_canvas(id=f"c{i}") for i in range(MAX_CANVASES_PER_PAGE)]
    assert len(validate_page_canvases(canvases)) == MAX_CANVASES_PER_PAGE


def test_page_refuses_nine_canvases():
    canvases = [_canvas(id=f"c{i}") for i in range(MAX_CANVASES_PER_PAGE + 1)]
    assert "at most 8 canvases" in _error(validate_page_canvases, canvases)


def test_page_refuses_duplicate_ids():
    msg = _error(validate_page_canvases, [_canvas(), _canvas()])
    assert "'sky'" in msg and "unique" in msg


def test_page_none_is_empty():
    assert validate_page_canvases(None) == []


# --- Content limits ----------------------------------------------------------


@pytest.mark.parametrize("size", [[0, 8], [8, 129], [8]])
def test_content_size_is_bounded(size):
    msg = _error(CanvasContent.model_validate, {"size": size})
    assert "size" in msg


def test_palette_limit():
    keys = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    assert len(keys) == MAX_PALETTE_KEYS
    CanvasContent.model_validate({"palette": dict.fromkeys(keys, "#000")})
    # A 63rd key cannot exist ("." is reserved, other characters invalid).
    msg = _error(CanvasContent.model_validate, {"palette": {**dict.fromkeys(keys, "#000"), "_": "#000"}})
    assert "at most 62 keys" in msg


def test_palette_dot_is_reserved():
    msg = _error(CanvasContent.model_validate, {"palette": {".": "#000"}})
    assert '"." is reserved for transparent' in msg


def test_palette_key_must_be_one_character():
    msg = _error(CanvasContent.model_validate, {"palette": {"ab": "#000"}})
    assert "single character" in msg


def test_palette_value_must_be_a_colour():
    msg = _error(CanvasContent.model_validate, {"palette": {"a": "#12"}})
    assert "not a colour" in msg


def test_shapes_limit():
    shape = {"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "red"}
    CanvasContent.model_validate({"shapes": [shape] * MAX_SHAPES})
    msg = _error(CanvasContent.model_validate, {"shapes": [shape] * (MAX_SHAPES + 1)})
    assert "at most 256 shapes" in msg


def test_pixel_rows_limit():
    CanvasContent.model_validate({"pixels": ["."] * MAX_PIXEL_ROWS})
    msg = _error(CanvasContent.model_validate, {"pixels": ["."] * (MAX_PIXEL_ROWS + 1)})
    assert "at most 128 rows" in msg


def test_pixel_row_length_limit():
    CanvasContent.model_validate({"pixels": ["." * MAX_PIXEL_COLS]})
    msg = _error(CanvasContent.model_validate, {"pixels": ["." * (MAX_PIXEL_COLS + 1)]})
    assert "at most 128 characters" in msg


def test_pixels_must_use_palette_keys():
    msg = _error(CanvasContent.model_validate, {"palette": {"k": "#000"}, "pixels": ["k.z"]})
    assert "row 1" in msg and "'z'" in msg and "not in the palette" in msg


def test_shape_palette_reference_must_exist():
    msg = _error(
        CanvasContent.model_validate, {"shapes": [{"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "q"}]}
    )
    assert "shapes[0].fill" in msg and "'q'" in msg


def test_unknown_shape_type():
    msg = _error(CanvasContent.model_validate, {"shapes": [{"type": "star"}]})
    assert "star" in msg


def test_missing_shape_field():
    msg = _error(CanvasContent.model_validate, {"shapes": [{"type": "circle", "cx": 1, "cy": 1}]})
    assert "r" in msg and "Field required" in msg


def test_line_needs_stroke():
    msg = _error(CanvasContent.model_validate, {"shapes": [{"type": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1}]})
    assert "stroke" in msg


def test_polygon_needs_three_points():
    msg = _error(CanvasContent.model_validate, {"shapes": [{"type": "polygon", "points": [[0, 0], [1, 1]]}]})
    assert "at least 3 points" in msg


def test_coordinates_are_bounded():
    msg = _error(RectShape.model_validate, {"type": "rect", "x": 99999, "y": 0, "w": 1, "h": 1})
    assert "between -1024 and 1024" in msg


def test_plain_string_number_is_refused():
    msg = _error(RectShape.model_validate, {"type": "rect", "x": "ten", "y": 0, "w": 1, "h": 1})
    assert "number or a {{" in msg


def test_text_font_choices():
    assert TextShape.model_validate({"type": "text", "x": 0, "y": 0, "text": "A", "color": "red"}).font == "5x7"
    msg = _error(TextShape.model_validate, {"type": "text", "x": 0, "y": 0, "text": "A", "color": "red", "font": "8x8"})
    assert "font" in msg


def test_as_without_foreach_is_refused():
    msg = _error(RectShape.model_validate, {"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "as": "p"})
    assert '"as" names the "foreach" item' in msg


def test_as_must_be_an_identifier():
    msg = _error(
        RectShape.model_validate, {"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "foreach": "{{a.b}}", "as": "1p"}
    )
    assert '"as"' in msg


def test_foreach_must_be_an_expression():
    msg = _error(RectShape.model_validate, {"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "foreach": "a.b"})
    assert "foreach" in msg and "{{" in msg


# --- Colours -----------------------------------------------------------------


def test_hex_colours():
    assert parse_color("#fff") == (255, 255, 255, 255)
    assert parse_color("#Ff8000") == (255, 128, 0, 255)


def test_board_colour_names_use_the_led_palette():
    for name, hex_value in BOARD_COLORS.items():
        r, g, b = int(hex_value[1:3], 16), int(hex_value[3:5], 16), int(hex_value[5:7], 16)
        assert parse_color(name) == (r, g, b, 255)
    assert parse_color("RED") == parse_color("red")


def test_transparent_names():
    assert parse_color("none") is None
    assert parse_color("transparent") is None
    assert parse_color(".") is None


def test_palette_key_colour():
    assert parse_color("y", {"y": "#ffcc00"}) == (255, 204, 0, 255)


@pytest.mark.parametrize("bad", ["#12", "#12345", "#ggg", "chartreuse", "q", ""])
def test_bad_colours(bad):
    assert "not a colour" in _error(parse_color, bad)
