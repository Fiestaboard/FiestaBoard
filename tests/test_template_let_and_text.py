"""LET bindings, SPLIT, and the guarded regex functions.

Before LET, the reference told authors to repeat a subexpression because
"boards are short" — which is what made six-row templates with a long
IFERROR chain per row unreadable. SPLIT and the regex trio exist because
plugins expose composite strings (``"72F / Sunny"``) that a template had no
way to take apart.
"""

from src.templates.expressions import evaluate, validate_expression

CTX = {
    "weather": {"summary": "72F / Sunny", "temp": 72},
    "board": {"tags": "sf,oak,bay"},
}


class TestLet:
    def test_binds_a_name_for_the_body(self):
        assert evaluate('LET(t, weather.temp, t & "F")', CTX) == "72F"

    def test_binding_is_computed_once_and_reused(self):
        assert evaluate('LET(t, weather.temp * 2, t & "/" & t)', CTX) == "144/144"

    def test_supports_several_bindings(self):
        assert evaluate("LET(a, 2, b, 3, a * b)", CTX) == "6"

    def test_later_binding_may_use_an_earlier_one(self):
        assert evaluate("LET(a, 4, b, a + 1, b)", CTX) == "5"

    def test_binding_shadows_nothing_outside_the_body(self):
        assert evaluate('LET(t, 1, t) & IFERROR(t, "gone")', CTX) == "1gone"

    def test_even_number_of_args_is_a_value_error(self):
        assert evaluate("LET(a, 1)", CTX) == "#VALUE"

    def test_non_identifier_binding_name_is_a_value_error(self):
        assert evaluate('LET("a", 1, 2)', CTX) == "#VALUE"

    def test_bound_name_is_not_reported_as_an_unknown_source(self):
        issues = validate_expression('LET(t, weather.temp, t & "F")', known_sources={"weather"})
        assert issues == []

    def test_unknown_source_inside_let_is_still_reported(self):
        issues = validate_expression("LET(t, nope.field, t)", known_sources={"weather"})
        assert [i.code for i in issues] == ["#REF"]

    def test_pairs_with_arrays_to_avoid_repeating_a_filter(self):
        ctx = {"mlb": {"games": [{"final": True, "team1": "SF"}, {"final": False, "team1": "NY"}]}}
        out = evaluate(
            'LET(done, FILTER(mlb.games, item.final), COUNT(done) & ": " & JOIN(done, ",", "team1"))',
            ctx,
        )
        assert out == "1: SF"


class TestSplit:
    def test_splits_into_an_array(self):
        assert evaluate('COUNT(SPLIT(board.tags, ","))', CTX) == "3"

    def test_items_are_usable(self):
        assert evaluate('AT(SPLIT(board.tags, ","), 1)', CTX) == "oak"

    def test_composes_with_foreach(self):
        assert evaluate('FOREACH(SPLIT(board.tags, ","), UPPER(item))', CTX) == "SF\nOAK\nBAY"

    def test_default_separator_is_whitespace(self):
        assert evaluate('JOIN(SPLIT(weather.summary), "|")', CTX) == "72F|/|Sunny"

    def test_missing_separator_yields_one_item(self):
        assert evaluate('COUNT(SPLIT(board.tags, ";"))', CTX) == "1"


class TestRegex:
    def test_match_is_boolean(self):
        assert evaluate('REGEXMATCH(weather.summary, "Sunny")', CTX) == "Yes"
        assert evaluate('REGEXMATCH(weather.summary, "Rain")', CTX) == "No"

    def test_extract_returns_first_match(self):
        assert evaluate('REGEXEXTRACT(weather.summary, "[0-9]+")', CTX) == "72"

    def test_extract_returns_a_capture_group(self):
        assert evaluate('REGEXEXTRACT(weather.summary, "([0-9]+)F", 1)', CTX) == "72"

    def test_extract_with_no_match_is_blank(self):
        assert evaluate('REGEXEXTRACT(weather.summary, "[0-9]+MPH")', CTX) == ""

    def test_replace_substitutes_every_match(self):
        assert evaluate('REGEXREPLACE(board.tags, ",", " ")', CTX) == "sf oak bay"

    def test_invalid_pattern_is_a_value_error(self):
        assert evaluate('REGEXMATCH(board.tags, "([")', CTX) == "#VALUE"

    def test_nested_quantifier_pattern_is_refused(self):
        # A render drives hardware on a loop; catastrophic backtracking is
        # refused up front rather than hung on.
        assert evaluate('REGEXMATCH(board.tags, "(a+)+b")', CTX) == "#VALUE"

    def test_overlong_pattern_is_refused(self):
        long_pattern = "a" * 200
        assert evaluate(f'REGEXMATCH(board.tags, "{long_pattern}")', CTX) == "#VALUE"
