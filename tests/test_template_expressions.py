"""Tests for the FiestaForm inline expression language.

Covers the standalone evaluator/parser as well as integration with the
template engine via ``{{= ... }}`` blocks.
"""

import pytest

from src.templates.expressions import (
    ErrorValue,
    evaluate,
    list_builtins,
    render_expressions,
)
from src.templates.engine import TemplateEngine


# --------------------------------------------------------------------------- #
# Standalone evaluator
# --------------------------------------------------------------------------- #


class TestLiteralsAndArithmetic:
    def test_integer_literal(self):
        assert evaluate("42") == "42"

    def test_float_literal(self):
        assert evaluate("3.14") == "3.1"  # one-decimal rendering

    def test_negative_number(self):
        assert evaluate("-5") == "-5"

    def test_string_literal(self):
        assert evaluate('"hello"') == "hello"

    def test_string_escapes(self):
        assert evaluate(r'"a\"b"') == 'a"b'

    def test_addition(self):
        assert evaluate("2 + 3") == "5"

    def test_subtraction(self):
        assert evaluate("10 - 4") == "6"

    def test_multiplication(self):
        assert evaluate("3 * 4") == "12"

    def test_division(self):
        assert evaluate("10 / 4") == "2.5"

    def test_modulo(self):
        assert evaluate("10 % 3") == "1"

    def test_precedence(self):
        assert evaluate("2 + 3 * 4") == "14"
        assert evaluate("(2 + 3) * 4") == "20"

    def test_unary_minus(self):
        assert evaluate("-(5 + 3)") == "-8"

    def test_division_by_zero(self):
        assert evaluate("1 / 0") == "#DIV/0"
        assert evaluate("5 % 0") == "#DIV/0"


class TestStringOps:
    def test_concat_with_amp(self):
        assert evaluate('"hello" & " " & "world"') == "hello world"

    def test_concat_mixed_types(self):
        assert evaluate('"x=" & 42') == "x=42"

    def test_upper(self):
        assert evaluate('UPPER("hi")') == "HI"

    def test_lower(self):
        assert evaluate('LOWER("HI")') == "hi"

    def test_trim(self):
        assert evaluate('TRIM("  hi  ")') == "hi"

    def test_left_right_mid(self):
        assert evaluate('LEFT("abcdef", 3)') == "abc"
        assert evaluate('RIGHT("abcdef", 2)') == "ef"
        # MID is 1-indexed (Excel-compatible)
        assert evaluate('MID("abcdef", 2, 3)') == "bcd"

    def test_len(self):
        assert evaluate('LEN("hello")') == "5"

    def test_replace(self):
        assert evaluate('REPLACE("foo bar foo", "foo", "x")') == "x bar x"

    def test_rept(self):
        assert evaluate('REPT("-", 5)') == "-----"

    def test_rept_capped(self):
        # Guard against runaway memory.
        assert evaluate('REPT("a", 2000)') == "#NUM"

    def test_contains_startswith_endswith(self):
        assert evaluate('CONTAINS("hello world", "lo wo")') == "Yes"
        assert evaluate('STARTSWITH("hello", "he")') == "Yes"
        assert evaluate('ENDSWITH("hello", "lo")') == "Yes"

    def test_pad(self):
        assert evaluate('PAD("ab", 5)') == "ab   "

    def test_padleft(self):
        assert evaluate('PADLEFT("7", 3)') == "  7"

    def test_center(self):
        assert evaluate('CENTER("hi", 6)') == "  hi  "

    def test_concat_function(self):
        assert evaluate('CONCAT("a", "b", "c")') == "abc"


class TestComparisonAndLogic:
    def test_equality_excel_single_equals(self):
        assert evaluate("3 = 3") == "Yes"

    def test_equality_double_equals(self):
        assert evaluate("3 == 3") == "Yes"

    def test_not_equal_bang_equals(self):
        assert evaluate("3 != 4") == "Yes"

    def test_not_equal_excel_diamond(self):
        assert evaluate("3 <> 4") == "Yes"

    def test_lt_gt(self):
        assert evaluate("3 < 4") == "Yes"
        assert evaluate("3 > 4") == "No"

    def test_lte_gte(self):
        assert evaluate("4 <= 4") == "Yes"
        assert evaluate("4 >= 5") == "No"

    def test_numeric_string_coercion(self):
        # "10" compares as 10, not lexicographically.
        assert evaluate('"10" > "9"') == "Yes"

    def test_string_comparison_caseinsensitive(self):
        assert evaluate('"Apple" == "apple"') == "Yes"

    def test_and_or_not(self):
        assert evaluate("AND(TRUE, TRUE)") == "Yes"
        assert evaluate("AND(TRUE, FALSE)") == "No"
        assert evaluate("OR(FALSE, TRUE)") == "Yes"
        assert evaluate("NOT(FALSE)") == "Yes"

    def test_logical_keywords_and_operators(self):
        assert evaluate("TRUE AND FALSE") == "No"
        assert evaluate("TRUE OR FALSE") == "Yes"
        assert evaluate("!FALSE") == "Yes"
        assert evaluate("TRUE && TRUE") == "Yes"
        assert evaluate("FALSE || TRUE") == "Yes"

    def test_short_circuit_and(self):
        # Right side would error, but AND short-circuits.
        assert evaluate("FALSE AND (1 / 0)") == "No"

    def test_short_circuit_or(self):
        assert evaluate("TRUE OR (1 / 0)") == "Yes"


class TestConditionals:
    def test_if_true(self):
        assert evaluate('IF(1 < 2, "yes", "no")') == "yes"

    def test_if_false(self):
        assert evaluate('IF(1 > 2, "yes", "no")') == "no"

    def test_if_two_arg_default_empty(self):
        assert evaluate('IF(1 > 2, "yes")') == ""

    def test_nested_if(self):
        expr = 'IF(1 > 2, "a", IF(1 == 1, "b", "c"))'
        assert evaluate(expr) == "b"

    def test_ifs_first_match_wins(self):
        expr = 'IFS(FALSE, "a", TRUE, "b", TRUE, "c")'
        assert evaluate(expr) == "b"

    def test_ifs_default_value(self):
        expr = 'IFS(FALSE, "a", FALSE, "b", "default")'
        assert evaluate(expr) == "default"

    def test_ifs_no_match_no_default(self):
        assert evaluate('IFS(FALSE, "a")') == "#VALUE"

    def test_switch(self):
        expr = 'SWITCH(2, 1, "one", 2, "two", 3, "three", "other")'
        assert evaluate(expr) == "two"

    def test_switch_default(self):
        expr = 'SWITCH(99, 1, "one", 2, "two", "other")'
        assert evaluate(expr) == "other"


class TestVariables:
    def test_simple_lookup(self):
        ctx = {"weather": {"temperature": 72}}
        assert evaluate("weather.temperature", ctx) == "72"

    def test_in_arithmetic(self):
        ctx = {"weather": {"temperature": 70}}
        assert evaluate("weather.temperature + 5", ctx) == "75"

    def test_missing_source(self):
        assert evaluate("foo.bar", {}) == "#REF"

    def test_missing_field(self):
        ctx = {"weather": {"temperature": 72}}
        assert evaluate("weather.nope", ctx) == "#REF"

    def test_nested_lookup(self):
        ctx = {"stocks": {"AAPL": {"price": 175.5}}}
        assert evaluate("stocks.AAPL.price", ctx) == "175.5"

    def test_array_index(self):
        ctx = {"baywheels": {"stations": [{"name": "A"}, {"name": "B"}]}}
        assert evaluate("baywheels.stations.1.name", ctx) == "B"

    def test_array_out_of_range(self):
        ctx = {"baywheels": {"stations": [{"name": "A"}]}}
        assert evaluate("baywheels.stations.5.name", ctx) == "#REF"


class TestErrorPropagation:
    def test_arithmetic_with_missing_propagates(self):
        assert evaluate("1 + bogus.field", {}) == "#REF"

    def test_iferror_traps_ref(self):
        assert evaluate('IFERROR(bogus.field, "fallback")') == "fallback"

    def test_iferror_passthrough_on_non_error(self):
        assert evaluate('IFERROR(5, "fallback")') == "5"

    def test_iserror_true(self):
        assert evaluate("ISERROR(1 / 0)") == "Yes"

    def test_iserror_false(self):
        assert evaluate("ISERROR(1 + 1)") == "No"

    def test_isblank(self):
        assert evaluate('ISBLANK("")') == "Yes"
        assert evaluate('ISBLANK("hi")') == "No"
        # Missing variable surfaces as blank for templating purposes? No --
        # we treat it as an error so the user can choose explicit handling.
        # ISBLANK on an error propagates the error.
        assert evaluate("ISBLANK(missing.field)") == "#REF"

    def test_default_replaces_missing(self):
        assert evaluate('DEFAULT(missing.field, "n/a")') == "n/a"

    def test_default_passes_through_value(self):
        assert evaluate('DEFAULT(7, "n/a")') == "7"

    def test_default_replaces_blank(self):
        ctx = {"x": {"y": ""}}
        assert evaluate('DEFAULT(x.y, "fallback")', ctx) == "fallback"

    def test_unknown_function(self):
        assert evaluate("BOGUSFN(1)") == "#NAME?"

    def test_syntax_error(self):
        assert evaluate("1 + ") == "#SYNTAX"
        assert evaluate('"unterminated') == "#SYNTAX"
        assert evaluate("(1 + 2") == "#SYNTAX"
        assert evaluate("@@@") == "#SYNTAX"


class TestMath:
    def test_abs(self):
        assert evaluate("ABS(-7)") == "7"

    def test_round(self):
        assert evaluate("ROUND(3.567, 1)") == "3.6"
        assert evaluate("ROUND(3.567)") == "4"

    def test_floor_ceil(self):
        assert evaluate("FLOOR(3.9)") == "3"
        assert evaluate("CEIL(3.1)") == "4"
        assert evaluate("FLOOR(-3.1)") == "-4"
        assert evaluate("CEIL(-3.9)") == "-3"

    def test_min_max(self):
        assert evaluate("MIN(3, 1, 4, 1, 5)") == "1"
        assert evaluate("MAX(3, 1, 4, 1, 5)") == "5"

    def test_sum_avg(self):
        assert evaluate("SUM(1, 2, 3, 4)") == "10"
        assert evaluate("AVG(1, 2, 3, 4)") == "2.5"

    def test_mod(self):
        assert evaluate("MOD(10, 3)") == "1"
        assert evaluate("MOD(5, 0)") == "#DIV/0"

    def test_int(self):
        assert evaluate("INT(3.7)") == "3"

    def test_sign(self):
        assert evaluate("SIGN(-5)") == "-1"
        assert evaluate("SIGN(5)") == "1"
        assert evaluate("SIGN(0)") == "0"


class TestConversions:
    def test_text(self):
        assert evaluate("TEXT(42)") == "42"
        assert evaluate("TEXT(TRUE)") == "Yes"

    def test_num(self):
        assert evaluate('NUM("42")') == "42"
        assert evaluate('NUM("3.5")') == "3.5"
        assert evaluate('NUM("abc")') == "#VALUE"

    def test_fixed(self):
        assert evaluate("FIXED(3.14159, 2)") == "3.14"
        assert evaluate("FIXED(3, 0)") == "3"
        assert evaluate("FIXED(3)") == "3.00"


class TestColorFunction:
    def test_color_by_name(self):
        # Returns single-brace marker matching engine's normalized form.
        assert evaluate('COLOR("red")') == "{63}"
        assert evaluate('COLOR("green")') == "{66}"

    def test_color_by_code(self):
        assert evaluate("COLOR(67)") == "{67}"

    def test_color_invalid_name(self):
        assert evaluate('COLOR("chartreuse")') == "#VALUE"

    def test_color_out_of_range(self):
        assert evaluate("COLOR(50)") == "#VALUE"


class TestRenderExpressions:
    def test_no_formulas_passthrough(self):
        assert render_expressions("hello {{var}}") == "hello {{var}}"

    def test_single_formula(self):
        assert render_expressions("{{= 1 + 2 }}") == "3"

    def test_multiple_formulas(self):
        ctx = {"w": {"t": 70}}
        out = render_expressions("{{= w.t }}F  {{= w.t > 60 }}", ctx)
        assert out == "70F  Yes"

    def test_formula_alongside_plain_var(self):
        assert (
            render_expressions(
                "{{= UPPER(\"hi\") }} - {{w.t}}", {"w": {"t": 1}}
            )
            == "HI - {{w.t}}"  # plain {{var}} is left for the next pass
        )

    def test_empty_formula_renders_empty(self):
        assert render_expressions("[{{= }}]") == "[]"

    def test_whitespace_in_marker(self):
        assert render_expressions("{{=  1+1 }}") == "2"

    def test_error_does_not_break_surrounding_text(self):
        out = render_expressions("before {{= 1/0 }} after")
        assert out == "before #DIV/0 after"


# --------------------------------------------------------------------------- #
# Integration with the template engine
# --------------------------------------------------------------------------- #


class TestEngineIntegration:
    @pytest.fixture
    def engine(self):
        return TemplateEngine()

    def test_render_arithmetic(self, engine):
        assert engine.render("{{= 2 + 2 }}", context={}) == "4"

    def test_render_variable_in_formula(self, engine):
        ctx = {"weather": {"temperature": 72}}
        out = engine.render("{{= weather.temperature & \"F\" }}", ctx)
        assert out == "72F"

    def test_render_if(self, engine):
        ctx = {"weather": {"temperature": 90}}
        out = engine.render(
            '{{= IF(weather.temperature > 80, "HOT", "OK") }}', ctx
        )
        assert out == "HOT"

    def test_render_color_function_produces_tile(self, engine):
        ctx = {"stocks": {"AAPL": {"change": 1.2}}}
        out = engine.render(
            '{{= IF(stocks.AAPL.change >= 0, COLOR("green"), COLOR("red")) }} AAPL',
            ctx,
        )
        assert out == "{66} AAPL"

    def test_color_tile_counts_as_one_tile(self, engine):
        # Sanity check that the engine's tile counter still treats
        # color markers produced by COLOR(...) as a single tile.
        text = engine.render('{{= COLOR("red") }}HI', context={})
        assert engine._count_tiles(text) == 3  # tile + H + I

    def test_formulas_do_not_break_existing_var_syntax(self, engine):
        ctx = {"weather": {"temperature": 72}}
        # Mix old-style and new-style.
        out = engine.render(
            'old={{weather.temperature}} new={{= weather.temperature + 1 }}',
            ctx,
        )
        assert out == "old=72 new=73"

    def test_named_color_tag_still_works(self, engine):
        out = engine.render("{{red}}HI", context={})
        assert out.startswith("{63}")

    def test_formula_and_named_color_together(self, engine):
        ctx = {"weather": {"temperature": 72}}
        out = engine.render(
            "{{red}}{{= weather.temperature }}", ctx
        )
        assert out == "{63}72"

    def test_formula_render_lines(self, engine):
        ctx = {"weather": {"temperature": 72}}
        rendered = engine.render_lines(
            ["{{= \"Temp \" & weather.temperature & \"F\" }}"],
            context=ctx,
            line_metadata=[{"alignment": "left", "wrap": False}],
            device_type="flagship",
        )
        # Result is padded to 22 columns, left-aligned.
        first_line = rendered.split("\n")[0]
        assert first_line.startswith("Temp 72F")
        assert len(first_line) == 22

    def test_iferror_in_template(self, engine):
        out = engine.render('{{= IFERROR(missing.thing, "n/a") }}', context={})
        assert out == "n/a"


# --------------------------------------------------------------------------- #
# Misc API
# --------------------------------------------------------------------------- #


class TestPublicAPI:
    def test_list_builtins_returns_sorted_unique(self):
        names = list_builtins()
        assert names == tuple(sorted(set(names)))
        # Spot-check a few that absolutely must be present.
        for required in ("IF", "IFS", "AND", "OR", "NOT", "COLOR", "UPPER",
                         "ROUND", "IFERROR", "CONCAT"):
            assert required in names

    def test_error_value_repr(self):
        assert str(ErrorValue("#REF")) == "#REF"
