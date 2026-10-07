"""Resolving a canvas against the page's variables: expressions, if, foreach, source."""

import pytest

from src.canvas.evaluate import MAX_EXPANDED_SHAPES, resolve_canvas
from src.canvas.models import Canvas

RED = (235, 64, 52, 255)
BLUE = (74, 144, 217, 255)
GREEN = (126, 211, 33, 255)

CONTEXT = {
    "weather": {"temp": 30, "label": "HOT"},
    "scores": {"items": [{"name": "A", "value": 3}, {"name": "B", "value": 0}, {"name": "C", "value": 7}]},
    "series": {"values": [1, 4, 2]},
    "art": {
        "canvas": {"size": [4, 4], "shapes": [{"type": "rect", "x": 0, "y": 0, "w": 4, "h": 4, "fill": "green"}]},
        "json": '{"size": [2, 2], "background": "#ff0000"}',
        "broken": {"shapes": [{"type": "star"}]},
    },
}


def _canvas(content=None, source=None):
    data = {"id": "c", "area": {"row": 1, "col": 1, "rows": 1, "cols": 1}}
    if content is not None:
        data["content"] = content
    if source is not None:
        data["source"] = source
    return Canvas.model_validate(data)


def _shapes(*shapes, **content):
    return _canvas({"shapes": list(shapes), **content})


def _rect(**fields):
    return {"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "red", **fields}


def test_static_shape_resolves_to_numbers_and_rgba():
    resolved, issues = resolve_canvas(_shapes(_rect(x=1, y=2.5, w=3, h=4)), CONTEXT)
    assert issues == []
    (shape,) = resolved.shapes
    assert shape.type == "rect"
    assert shape.values == {"x": 1.0, "y": 2.5, "w": 3.0, "h": 4.0, "fill": RED, "stroke": None}


def test_whole_field_expression_is_a_number():
    resolved, _ = resolve_canvas(_shapes(_rect(x="{{weather.temp}}", w="{{= weather.temp / 10 }}")), CONTEXT)
    assert resolved.shapes[0].values["x"] == 30.0
    assert resolved.shapes[0].values["w"] == 3.0


def test_formula_without_equals_sign_and_if_function():
    shape = _rect(fill='{{IF(weather.temp > 25, "red", "blue")}}', stroke='{{= IF(weather.temp > 40, "red", "blue") }}')
    resolved, _ = resolve_canvas(_shapes(shape), CONTEXT)
    assert resolved.shapes[0].values["fill"] == RED
    assert resolved.shapes[0].values["stroke"] == BLUE


def test_let_inside_a_field():
    resolved, _ = resolve_canvas(_shapes(_rect(h="{{LET(t, weather.temp, t - 28)}}")), CONTEXT)
    assert resolved.shapes[0].values["h"] == 2.0


def test_text_interpolates_into_a_string():
    shape = {"type": "text", "x": 0, "y": 0, "text": "T {{weather.temp}} {{weather.label}}", "color": "white"}
    resolved, _ = resolve_canvas(_shapes(shape), CONTEXT)
    assert resolved.shapes[0].values["text"] == "T 30 HOT"


def test_if_falsy_skips_and_truthy_keeps():
    resolved, issues = resolve_canvas(
        _shapes(
            _rect(**{"if": "{{weather.temp > 40}}"}),
            _rect(**{"if": "{{weather.temp > 20}}"}, x=5),
            _rect(**{"if": False}, x=6),
            _rect(**{"if": True}, x=7),
        ),
        CONTEXT,
    )
    assert issues == []
    assert [s.values["x"] for s in resolved.shapes] == [5.0, 7.0]


def test_foreach_over_dicts_binds_fields_and_zero_based_index():
    shape = _rect(foreach="{{scores.items}}", x="{{p.index * 2}}", h="{{p.value}}", **{"as": "p"})
    resolved, issues = resolve_canvas(_shapes(shape), CONTEXT)
    assert issues == []
    assert [(s.values["x"], s.values["h"]) for s in resolved.shapes] == [(0.0, 3.0), (2.0, 0.0), (4.0, 7.0)]


def test_foreach_with_if_per_item():
    shape = _rect(foreach="{{scores.items}}", **{"as": "p", "if": "{{p.value > 0}}"}, x="{{p.index}}")
    resolved, _ = resolve_canvas(_shapes(shape), CONTEXT)
    assert [s.values["x"] for s in resolved.shapes] == [0.0, 2.0]


def test_foreach_over_scalars_binds_value():
    shape = _rect(foreach="{{series.values}}", x="{{p.index}}", h="{{p.value}}", **{"as": "p"})
    resolved, _ = resolve_canvas(_shapes(shape), CONTEXT)
    assert [(s.values["x"], s.values["h"]) for s in resolved.shapes] == [(0.0, 1.0), (1.0, 4.0), (2.0, 2.0)]


def test_foreach_default_name_is_item():
    shape = _rect(foreach="{{series.values}}", x="{{item.value}}")
    resolved, _ = resolve_canvas(_shapes(shape), CONTEXT)
    assert [s.values["x"] for s in resolved.shapes] == [1.0, 4.0, 2.0]


def test_foreach_colour_from_item():
    shape = _rect(foreach="{{scores.items}}", fill='{{IF(p.value > 5, "red", "green")}}', **{"as": "p"})
    resolved, _ = resolve_canvas(_shapes(shape), CONTEXT)
    assert [s.values["fill"] for s in resolved.shapes] == [GREEN, GREEN, RED]


def test_foreach_over_a_non_list_is_an_issue():
    resolved, issues = resolve_canvas(_shapes(_rect(foreach="{{weather.temp}}"), _rect(x=9)), CONTEXT)
    assert [s.values["x"] for s in resolved.shapes] == [9.0]
    assert issues[0].path == "shapes[0].foreach"
    assert "list" in issues[0].message


def test_polygon_points_may_be_expressions():
    shape = {"type": "polygon", "points": [[0, 0], ["{{weather.temp}}", 0], [0, "{{series.values.1}}"]], "fill": "red"}
    resolved, issues = resolve_canvas(_shapes(shape), CONTEXT)
    assert issues == []
    assert resolved.shapes[0].values["points"] == [(0.0, 0.0), (30.0, 0.0), (0.0, 4.0)]


def test_polygon_points_from_one_expression():
    shape = {"type": "polygon", "points": "{{tri.points}}", "fill": "red"}
    ctx = {"tri": {"points": [[0, 0], [3, 0], [0, 3]]}}
    resolved, issues = resolve_canvas(_shapes(shape), ctx)
    assert issues == []
    assert resolved.shapes[0].values["points"] == [(0.0, 0.0), (3.0, 0.0), (0.0, 3.0)]


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("x", "{{nope.field}}", "#REF"),
        ("x", "{{1 +}}", "#SYNTAX"),
        ("x", "{{weather.label}}", "number"),
        ("x", "{{1 / 0}}", "#DIV/0"),
        ("x", "{{weather.temp * 1000}}", "between -1024 and 1024"),
        ("fill", "{{weather.label}}", "not a colour"),
        ("if", "{{nope.x}}", "#REF"),
    ],
)
def test_bad_expressions_are_issues_not_exceptions(field, value, fragment):
    resolved, issues = resolve_canvas(_shapes(_rect(**{field: value}), _rect(x=9)), CONTEXT)
    assert [s.values["x"] for s in resolved.shapes] == [9.0]
    assert len(issues) == 1
    assert issues[0].canvas_id == "c"
    assert issues[0].path == f"shapes[0].{field}"
    assert fragment in issues[0].message


def test_issue_in_one_foreach_item_skips_only_that_item():
    ctx = {"s": {"items": [{"x": 1}, {"y": 2}, {"x": 3}]}}
    shape = _rect(foreach="{{s.items}}", x="{{p.x}}", **{"as": "p"})
    resolved, issues = resolve_canvas(_shapes(shape), ctx)
    assert [s.values["x"] for s in resolved.shapes] == [1.0, 3.0]
    assert issues[0].path == "shapes[0].x"
    assert "item 1" in issues[0].message


def test_expansion_is_capped():
    ctx = {"big": {"items": list(range(MAX_EXPANDED_SHAPES + 5))}}
    resolved, issues = resolve_canvas(_shapes(_rect(foreach="{{big.items}}")), ctx)
    assert len(resolved.shapes) == MAX_EXPANDED_SHAPES
    assert any(f"at most {MAX_EXPANDED_SHAPES}" in i.message for i in issues)


def test_background_and_palette_resolve():
    resolved, _ = resolve_canvas(
        _canvas({"background": "blue", "palette": {"k": "#000", "n": "none"}, "pixels": ["kn"]}), {}
    )
    assert resolved.background == BLUE
    assert resolved.palette == {"k": (0, 0, 0, 255), "n": None}
    assert resolved.pixels == ("kn",)


def test_background_expression():
    resolved, _ = resolve_canvas(_canvas({"background": '{{IF(weather.temp > 25, "red", "blue")}}'}), CONTEXT)
    assert resolved.background == RED


# --- source ------------------------------------------------------------------


def test_source_yields_content():
    resolved, issues = resolve_canvas(_canvas(source="{{art.canvas}}"), CONTEXT)
    assert issues == []
    assert resolved.size == (4, 4)
    assert resolved.shapes[0].values["fill"] == GREEN


def test_source_may_be_a_json_string():
    resolved, issues = resolve_canvas(_canvas(source="{{art.json}}"), CONTEXT)
    assert issues == []
    assert resolved.size == (2, 2)
    assert resolved.background == (255, 0, 0, 255)


def test_source_wins_over_stored_content():
    resolved, _ = resolve_canvas(_canvas({"size": [9, 9]}, source="{{art.canvas}}"), CONTEXT)
    assert resolved.size == (4, 4)


def test_missing_source_falls_back_to_stored_content():
    resolved, issues = resolve_canvas(_canvas({"size": [9, 9]}, source="{{art.nothing}}"), CONTEXT)
    assert resolved.size == (9, 9)
    assert issues[0].path == "source"
    assert "#REF" in issues[0].message


def test_invalid_source_content_falls_back_with_the_validation_message():
    resolved, issues = resolve_canvas(_canvas({"size": [9, 9]}, source="{{art.broken}}"), CONTEXT)
    assert resolved.size == (9, 9)
    assert issues[0].path == "source"
    assert "star" in issues[0].message


def test_source_that_is_not_an_object():
    resolved, issues = resolve_canvas(_canvas(source="{{weather.temp}}"), CONTEXT)
    assert resolved is None
    assert "content object" in issues[0].message


def test_missing_source_and_no_content_is_empty():
    resolved, issues = resolve_canvas(_canvas(source="{{art.nothing}}"), CONTEXT)
    assert resolved is None
    assert len(issues) == 1
