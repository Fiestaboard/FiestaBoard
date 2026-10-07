"""The template engine's one-expression helper the canvas evaluator rides on.

``evaluate_value`` returns a formula's *native* value (numbers stay numbers,
dicts and lists stay data) and raises :class:`FormulaError` instead of
rendering an error tag, so a caller can tell a value from a failure.
"""

from unittest.mock import patch

import pytest

from src.templates.expressions import FormulaError, evaluate, evaluate_value, value_to_text


def test_variable_path_returns_native_number():
    assert evaluate_value("weather.temp", {"weather": {"temp": 21.5}}) == 21.5


def test_variable_path_returns_native_dict():
    content = {"size": [8, 8], "shapes": []}
    assert evaluate_value("art.canvas", {"art": {"canvas": content}}) == content


def test_formula_with_if_and_let():
    ctx = {"weather": {"temp": 30}}
    assert evaluate_value('IF(weather.temp > 25, "red", "blue")', ctx) == "red"
    assert evaluate_value("LET(t, weather.temp, t * 2)", ctx) == 60


def test_bindings_resolve_as_locals():
    bound = {"p": {"index": 2, "x": 7}}
    assert evaluate_value("p.x + p.index", {}, bindings=bound) == 9


def test_bindings_are_case_insensitive_names():
    assert evaluate_value("P.x", {}, bindings={"P": {"x": 3}}) == 3


def test_missing_variable_raises_ref():
    with pytest.raises(FormulaError) as exc:
        evaluate_value("nope.field", {})
    assert exc.value.code == "#REF"


def test_syntax_error_raises_with_position():
    with pytest.raises(FormulaError) as exc:
        evaluate_value("1 +", {})
    assert exc.value.code == "#SYNTAX"


def test_division_by_zero_raises():
    with pytest.raises(FormulaError) as exc:
        evaluate_value("1 / 0", {})
    assert exc.value.code == "#DIV/0"


def test_value_to_text_matches_template_rendering():
    assert value_to_text(3.0) == "3"
    assert value_to_text(True) == "Yes"
    assert value_to_text("hi") == "hi"


def test_engine_method_delegates_with_bindings():
    with patch("src.templates.engine.get_plugin_registry"):
        from src.templates.engine import TemplateEngine

        engine = TemplateEngine()
    assert engine.evaluate_expression("p.value * 2", {}, bindings={"p": {"value": 4}}) == 8


def test_string_evaluate_is_unchanged():
    # The existing renderer still renders errors as tags.
    assert evaluate("nope.field", {}) == "#REF"
    assert evaluate("1 + 2", {}) == "3"
