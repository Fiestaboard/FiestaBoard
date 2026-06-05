"""Tests for the inline template expression language.

Covers the standalone evaluator/parser as well as integration with the
template engine via ``{{= ... }}`` blocks.
"""

import pytest

from src.templates.engine import TemplateEngine
from src.templates.expressions import (
    ErrorValue,
    evaluate,
    list_builtins,
    render_expressions,
)

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

    def test_home_assistant_entity_state(self):
        # HA entities are stored under their real ID which contains a dot
        # (e.g. "sensor.outdoor_temp"). The template path uses underscores.
        ctx = {"home_assistant": {"sensor.outdoor_temp": {"state": "72"}}}
        assert evaluate("home_assistant.sensor_outdoor_temp.state", ctx) == "72"

    def test_home_assistant_domain_with_underscore(self):
        # Domains like media_player, binary_sensor contain underscores; the
        # smart resolution must try each position to find the right split.
        ctx = {
            "home_assistant": {
                "media_player.living_room": {"state": "playing"},
                "binary_sensor.front_door": {"state": "on"},
            }
        }
        assert evaluate("home_assistant.media_player_living_room.state", ctx) == "playing"
        assert evaluate("home_assistant.binary_sensor_front_door.state", ctx) == "on"

    def test_home_assistant_nested_attribute(self):
        ctx = {
            "home_assistant": {
                "sensor.outdoor_temp": {
                    "state": "72",
                    "attributes": {"friendly_name": "Outdoor Temp"},
                }
            }
        }
        assert evaluate("home_assistant.sensor_outdoor_temp.attributes.friendly_name", ctx) == "Outdoor Temp"

    def test_home_assistant_missing_entity_returns_ref(self):
        ctx = {"home_assistant": {"sensor.outdoor_temp": {"state": "72"}}}
        assert evaluate("home_assistant.no_such_entity.state", ctx) == "#REF"

    def test_home_assistant_in_arithmetic(self):
        ctx = {"home_assistant": {"sensor.outdoor_temp": {"state": 72}}}
        assert evaluate("home_assistant.sensor_outdoor_temp.state + 32", ctx) == "104"

    def test_home_assistant_in_iferror(self):
        ctx = {"home_assistant": {}}
        assert evaluate('IFERROR(home_assistant.missing_entity.state, "n/a")', ctx) == "n/a"

    def test_home_assistant_direct_key_still_works(self):
        # If the context already stores the entity under an underscore key
        # (no dot conversion needed), the direct lookup path is used.
        ctx = {"home_assistant": {"sensor_no_dot": {"state": "ok"}}}
        assert evaluate("home_assistant.sensor_no_dot.state", ctx) == "ok"


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
        # New: #SYNTAX errors include a character position when available.
        assert evaluate("1 + ").startswith("#SYNTAX")
        assert evaluate('"unterminated').startswith("#SYNTAX")
        assert evaluate("(1 + 2").startswith("#SYNTAX")
        assert evaluate("@@@").startswith("#SYNTAX")

    def test_syntax_error_includes_position(self):
        # Position is the character offset in the source.
        assert evaluate("@@@") == "#SYNTAX:0"
        assert evaluate("1 + @") == "#SYNTAX:4"


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
            render_expressions('{{= UPPER("hi") }} - {{w.t}}', {"w": {"t": 1}})
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
        out = engine.render('{{= weather.temperature & "F" }}', ctx)
        assert out == "72F"

    def test_render_if(self, engine):
        ctx = {"weather": {"temperature": 90}}
        out = engine.render('{{= IF(weather.temperature > 80, "HOT", "OK") }}', ctx)
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
            "old={{weather.temperature}} new={{= weather.temperature + 1 }}",
            ctx,
        )
        assert out == "old=72 new=73"

    def test_named_color_tag_still_works(self, engine):
        out = engine.render("{{red}}HI", context={})
        assert out.startswith("{63}")

    def test_formula_and_named_color_together(self, engine):
        ctx = {"weather": {"temperature": 72}}
        out = engine.render("{{red}}{{= weather.temperature }}", ctx)
        assert out == "{63}72"

    def test_formula_render_lines(self, engine):
        ctx = {"weather": {"temperature": 72}}
        rendered = engine.render_lines(
            ['{{= "Temp " & weather.temperature & "F" }}'],
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
        for required in ("IF", "IFS", "AND", "OR", "NOT", "COLOR", "UPPER", "ROUND", "IFERROR", "CONCAT"):
            assert required in names

    def test_list_builtins_matches_signatures(self):
        # Every built-in must have signature metadata so the editor's
        # function picker is never missing entries. This is the test that
        # would have caught COALESCE/PROPER/etc. being added without docs.
        from src.templates.expressions import function_signatures

        assert set(list_builtins()) == set(function_signatures().keys())

    def test_error_value_repr(self):
        assert str(ErrorValue("#REF")) == "#REF"


# --------------------------------------------------------------------------- #
# New built-ins added in response to review feedback
# --------------------------------------------------------------------------- #


class TestCoalesce:
    def test_returns_first_real_value(self):
        assert evaluate('COALESCE(NULL, "", missing.x, "fallback")') == "fallback"

    def test_passes_through_first_value(self):
        assert evaluate('COALESCE("a", "b", "c")') == "a"

    def test_skips_blanks_and_errors(self):
        assert evaluate('COALESCE("", missing.x, 7)') == "7"

    def test_skips_null_in_isolation(self):
        assert evaluate('COALESCE(NULL, "x")') == "x"

    def test_skips_empty_string_in_isolation(self):
        assert evaluate('COALESCE("", "x")') == "x"

    def test_skips_missing_variable_in_isolation(self):
        assert evaluate('COALESCE(missing.var, "x")') == "x"

    def test_returns_last_when_all_blank(self):
        # Same shape as SQL: if every input is null/blank, hand back the
        # final fallback so the user always sees *something*.
        assert evaluate('COALESCE("", NULL, "—")') == "—"

    def test_no_args(self):
        assert evaluate("COALESCE()") == "#VALUE"

    def test_single_arg(self):
        assert evaluate('COALESCE("x")') == "x"


class TestProper:
    def test_simple(self):
        assert evaluate('PROPER("hello world")') == "Hello World"

    def test_handles_apostrophes(self):
        # ``str.title()`` famously breaks on this; PROPER must not.
        assert evaluate('PROPER("don\'t stop")') == "Don't Stop"

    def test_mixed_case_input(self):
        assert evaluate('PROPER("hELLO wORLD")') == "Hello World"

    def test_numbers_and_punctuation(self):
        assert evaluate('PROPER("foo-bar 123 baz")') == "Foo-Bar 123 Baz"


class TestFindSearch:
    def test_find_basic(self):
        assert evaluate('FIND("lo", "hello")') == "4"

    def test_find_missing_returns_value_error(self):
        assert evaluate('FIND("xx", "hello")') == "#VALUE"

    def test_find_is_case_sensitive(self):
        assert evaluate('FIND("LO", "hello")') == "#VALUE"

    def test_find_with_start(self):
        assert evaluate('FIND("o", "foo bar foo", 5)') == "10"

    def test_search_is_case_insensitive(self):
        assert evaluate('SEARCH("LO", "hello")') == "4"

    def test_search_missing_returns_zero(self):
        # Template-friendly: 0 lets you do `IF(SEARCH(...) > 0, ...)`.
        assert evaluate('SEARCH("xx", "hello")') == "0"


class TestPowerSqrt:
    def test_power_int_exp(self):
        assert evaluate("POWER(2, 10)") == "1024"

    def test_power_fractional(self):
        assert evaluate("POWER(9, 0.5)") == "3"

    def test_power_zero(self):
        assert evaluate("POWER(0, 0)") == "1"

    def test_power_negative_fractional_returns_num(self):
        # math.pow(-1, 0.5) is a complex; surface as #NUM.
        assert evaluate("POWER(-1, 0.5)") == "#NUM"

    def test_sqrt(self):
        assert evaluate("SQRT(16)") == "4"

    def test_sqrt_zero(self):
        assert evaluate("SQRT(0)") == "0"

    def test_sqrt_negative(self):
        assert evaluate("SQRT(-1)") == "#NUM"


class TestRoundUpDown:
    def test_roundup_positive(self):
        assert evaluate("ROUNDUP(3.2)") == "4"
        assert evaluate("ROUNDUP(3.21, 1)") == "3.3"

    def test_roundup_negative_goes_away_from_zero(self):
        # Excel ROUNDUP rounds away from zero, not toward +infinity.
        assert evaluate("ROUNDUP(-3.2)") == "-4"

    def test_rounddown_positive(self):
        assert evaluate("ROUNDDOWN(3.7)") == "3"
        assert evaluate("ROUNDDOWN(3.79, 1)") == "3.7"

    def test_rounddown_negative_toward_zero(self):
        assert evaluate("ROUNDDOWN(-3.7)") == "-3"


# --------------------------------------------------------------------------- #
# Validation API + engine integration
# --------------------------------------------------------------------------- #


class TestValidateExpression:
    def test_clean_expression(self):
        from src.templates.expressions import validate_expression

        assert validate_expression("1 + 2") == []
        assert validate_expression('IF(1 > 0, "y", "n")') == []

    def test_syntax_error_reports_position(self):
        from src.templates.expressions import validate_expression

        issues = validate_expression("1 + @")
        assert len(issues) == 1
        assert issues[0].code == "#SYNTAX"
        assert issues[0].pos == 4

    def test_unknown_function(self):
        from src.templates.expressions import validate_expression

        issues = validate_expression("BOGUS(1)")
        assert any(i.code == "#NAME?" for i in issues)

    def test_arity_too_few(self):
        from src.templates.expressions import validate_expression

        issues = validate_expression("IF(TRUE)")
        assert any(i.code == "#VALUE" and "expected at least 2" in i.message for i in issues)

    def test_arity_too_many(self):
        from src.templates.expressions import validate_expression

        issues = validate_expression("ABS(1, 2, 3)")
        assert any(i.code == "#VALUE" and "expected at most 1" in i.message for i in issues)

    def test_unknown_source_with_known_set(self):
        from src.templates.expressions import validate_expression

        issues = validate_expression("missing.field", known_sources={"weather"})
        assert any(i.code == "#REF" for i in issues)

    def test_known_source_no_issue(self):
        from src.templates.expressions import validate_expression

        issues = validate_expression("weather.temperature", known_sources={"weather"})
        assert issues == []

    def test_plugin_instance_with_colon(self):
        from src.templates.expressions import validate_expression

        # ``weather:home.temperature`` -- the source is "weather".
        issues = validate_expression("weather:home.temperature", known_sources={"weather"})
        assert issues == []


class TestFindFormulas:
    def test_single_formula(self):
        from src.templates.expressions import find_formulas

        out = find_formulas("Hi {{= 1 + 1 }} there")
        assert len(out) == 1
        start, end, body = out[0]
        assert body == "1 + 1"
        assert start == 3

    def test_multiple_formulas(self):
        from src.templates.expressions import find_formulas

        out = find_formulas("{{= 1 }} and {{= 2 }}")
        assert [o[2] for o in out] == ["1", "2"]

    def test_ignores_plain_vars(self):
        from src.templates.expressions import find_formulas

        assert find_formulas("hi {{plugin.field}} there") == []


class TestFunctionSignatures:
    def test_returns_dict(self):
        from src.templates.expressions import function_signatures, list_builtins

        sigs = function_signatures()
        # Every built-in is documented.
        assert set(sigs.keys()) == set(list_builtins())
        # Each entry has the documented shape.
        for name, info in sigs.items():
            assert set(info.keys()) == {"category", "signature", "summary"}
            assert info["signature"].startswith(name)
            assert info["summary"]
            assert info["category"] in {"logic", "math", "text", "convert", "color"}

    def test_categories_balance(self):
        from src.templates.expressions import function_signatures

        sigs = function_signatures()
        # A sanity check that we have a useful spread.
        cats = {info["category"] for info in sigs.values()}
        assert cats >= {"logic", "math", "text", "convert", "color"}


class TestEngineValidationIntegration:
    @pytest.fixture
    def engine(self):
        e = TemplateEngine()
        # Pretend "weather" is a known plugin so unknown-source errors
        # actually trigger.
        from unittest.mock import Mock

        e._plugin_registry = Mock()
        e._plugin_registry.plugins = {"weather": object()}
        e._plugin_registry._manifests = {}
        return e

    def test_clean_template_no_errors(self, engine):
        errs = engine.validate_template("{{= weather.temperature + 1 }}")
        assert errs == []

    def test_formula_syntax_error_surfaced(self, engine):
        errs = engine.validate_template("{{= 1 + @ }}")
        assert any("Formula #SYNTAX" in e.message for e in errs)

    def test_formula_unknown_function_surfaced(self, engine):
        errs = engine.validate_template("{{= BOGUSFN(1) }}")
        assert any("Formula #NAME?" in e.message for e in errs)

    def test_formula_unknown_source_surfaced(self, engine):
        errs = engine.validate_template("{{= mystery.thing }}")
        assert any("Formula #REF" in e.message and "mystery" in e.message for e in errs)

    def test_formula_arity_error_surfaced(self, engine):
        errs = engine.validate_template("{{= IF(TRUE) }}")
        assert any("Formula #VALUE" in e.message for e in errs)

    def test_plain_var_unknown_source_still_flagged(self, engine):
        # Make sure formula validation doesn't break the existing path.
        errs = engine.validate_template("{{mystery.thing}}")
        assert any("Unknown source" in e.message for e in errs)

    def test_formula_validation_does_not_double_count_plain_var(self, engine):
        # The new "skip ``=``" guard in the plain-var loop must really skip.
        errs = engine.validate_template("{{= weather.temperature }}")
        assert errs == []


class TestRenderLinesIntegration:
    """End-to-end: a formula in a real ``render_lines`` call."""

    @pytest.fixture
    def engine(self):
        return TemplateEngine()

    def test_left_aligned_formula(self, engine):
        ctx = {"weather": {"temperature": 72}}
        out = engine.render_lines(
            ['{{= weather.temperature & "F" }}'],
            context=ctx,
            line_metadata=[{"alignment": "left", "wrap": False}],
            device_type="flagship",
        )
        line = out.split("\n")[0]
        assert line.startswith("72F")
        assert len(line) == 22

    def test_centered_formula(self, engine):
        out = engine.render_lines(
            ['{{= "HI" }}'],
            context={},
            line_metadata=[{"alignment": "center", "wrap": False}],
            device_type="flagship",
        )
        line = out.split("\n")[0]
        # "HI" centered in 22 cols.
        assert line.strip() == "HI"
        assert "HI" in line[9:13]

    def test_color_function_counts_as_one_tile(self, engine):
        # Verify: a COLOR(...) tile inside a formula gets the same single-
        # tile treatment that a static {{red}} would.
        ctx = {"weather": {"temperature": 72}}
        out = engine.render_lines(
            ['{{= COLOR("red") }}{{= weather.temperature }}'],
            context=ctx,
            line_metadata=[{"alignment": "left", "wrap": False}],
            device_type="flagship",
        )
        line = out.split("\n")[0]
        # 1 color tile + "72" + 19 spaces of padding = 22 board cells.
        assert engine._count_tiles(line) == 22


class TestDeepNestingAndStress:
    def test_deeply_nested_if(self):
        # 30 levels of IF -- well within reasonable.
        expr = "1"
        for _ in range(30):
            expr = f"IF(TRUE, {expr}, 0)"
        assert evaluate(expr) == "1"

    def test_long_arg_list(self):
        # SUM of 100 numbers.
        expr = "SUM(" + ",".join(str(i) for i in range(100)) + ")"
        assert evaluate(expr) == "4950"

    def test_long_string_concat(self):
        expr = " & ".join(['"a"'] * 50)
        assert evaluate(expr) == "a" * 50


class TestNullAndBlankSemantics:
    def test_null_literal_renders_empty(self):
        assert evaluate("NULL") == ""

    def test_null_in_concat(self):
        assert evaluate('"x:" & NULL & ":y"') == "x::y"

    def test_null_in_arithmetic_is_zero(self):
        # Excel-ish: NULL coerces to 0 in numeric context.
        assert evaluate("NULL + 5") == "5"

    def test_null_isblank(self):
        assert evaluate("ISBLANK(NULL)") == "Yes"

    def test_missing_sentinel_treated_as_blank(self):
        # If a plain {{var}} was rendered before us as ``???``, ISBLANK and
        # DEFAULT must still recognise it.
        ctx = {"x": {"y": "???"}}
        assert evaluate("ISBLANK(x.y)", ctx) == "Yes"
        assert evaluate('DEFAULT(x.y, "fallback")', ctx) == "fallback"


class TestExpressionIssueShape:
    def test_is_serializable_friendly(self):
        from dataclasses import asdict

        from src.templates.expressions import validate_expression

        issues = validate_expression("@@@")
        assert issues
        d = asdict(issues[0])
        assert set(d.keys()) == {"code", "message", "pos"}
        assert d["code"] == "#SYNTAX"
        assert d["pos"] == 0
