"""LET bindings, SPLIT, and the guarded regex functions.

Before LET, the reference told authors to repeat a subexpression because
"boards are short" — which is what made six-row templates with a long
IFERROR chain per row unreadable. SPLIT and the regex trio exist because
plugins expose composite strings (``"72F / Sunny"``) that a template had no
way to take apart.
"""

import time

from src.templates.expressions import _MATCH_TIMEOUT_SECONDS, evaluate, validate_expression

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

    def test_a_catastrophic_pattern_is_abandoned_rather_than_run_forever(self):
        # A render drives hardware on a loop. This pattern backtracks
        # exponentially on a long run of ``a``; the match is abandoned at the
        # timeout and reported as #VALUE instead of stalling the loop.
        assert evaluate('REGEXMATCH(p.t, "(a+)+$")', {"p": {"t": "a" * 4096 + "!"}}) == "#VALUE"

    def test_the_same_pattern_on_a_short_subject_just_answers(self):
        # Nothing is refused for its shape any more, so a pattern that happens
        # to finish returns its real answer.
        assert evaluate('REGEXMATCH(board.tags, "(a+)+b")', CTX) == "No"

    def test_overlong_pattern_is_refused(self):
        long_pattern = "a" * 200
        assert evaluate(f'REGEXMATCH(board.tags, "{long_pattern}")', CTX) == "#VALUE"


class TestCatastrophicPatternsAreBounded:
    """No pattern can run longer than the match timeout, whatever its shape.

    This used to be a blacklist of dangerous pattern shapes, and it was proved
    unsound three times: refusing a nested quantifier missed ``(a|a)+b``;
    refusing any quantified group missed ``((a)|(a))*$`` and the group-free
    ``a*a*a*a*a*a*a*a*a*b``. Every widening also refused more legitimate
    patterns. The bound is now on the work — ``regex`` abandons a match past
    ``_MATCH_TIMEOUT_SECONDS`` — so the shape no longer matters.
    """

    #: Each of these defeated some earlier version of the shape blacklist.
    CATASTROPHIC = (
        "(a+)+$",
        "(a|a)+$",
        "(a|ab)*$",
        "(?:a|a)+$",
        "((a)|(a))*$",
        "((a|a))*$",
    )

    #: Long enough that every pattern above backtracks past the timeout. A
    #: plugin returning a long text blob is ordinary, so this is not exotic.
    SUBJECT = "a" * 4096 + "!"

    def test_every_catastrophic_shape_is_abandoned_at_the_timeout(self):
        for pattern in self.CATASTROPHIC:
            assert evaluate(f'REGEXMATCH(p.t, "{pattern}")', {"p": {"t": self.SUBJECT}}) == "#VALUE", pattern

    def test_abandoning_takes_about_the_timeout_not_forever(self):
        """Pins that the cost is the budget, not that it merely terminates.

        Without a bound these patterns do not finish at all, so a plain
        assertion that the loop returned would be satisfied by any
        implementation that eventually completes — including one that takes
        minutes.
        """
        budget = len(self.CATASTROPHIC) * _MATCH_TIMEOUT_SECONDS
        start = time.perf_counter()
        for pattern in self.CATASTROPHIC:
            evaluate(f'REGEXMATCH(p.t, "{pattern}")', {"p": {"t": self.SUBJECT}})
        elapsed = time.perf_counter() - start
        assert elapsed < budget * 3, (
            f"{len(self.CATASTROPHIC)} abandoned matches took {elapsed:.2f}s; each should cost about "
            f"{_MATCH_TIMEOUT_SECONDS}s. The timeout in src/templates/expressions.py is not being applied."
        )

    def test_a_group_without_a_quantifier_still_compiles(self):
        assert evaluate('REGEXEXTRACT(weather.summary, "([0-9]+)F", 1)', CTX) == "72"

    def test_patterns_the_old_shape_blacklist_refused_now_work(self):
        r"""The cost of guessing from shape: these are ordinary and were banned.

        ``(ab)+`` is a repeated group and ``\d+/\d+/\d+`` carries more
        quantifiers than the old cap allowed. Neither can backtrack badly.
        """
        assert evaluate('REGEXMATCH("abab", "^(ab)+$")', CTX) == "Yes"
        assert evaluate('REGEXEXTRACT("on 12/25/2026 ok", "\\\\d+/\\\\d+/\\\\d+")', CTX) == "12/25/2026"

    def test_patterns_a_board_actually_needs_are_not_collateral(self):
        assert evaluate('REGEXEXTRACT("72F / Sunny", "([0-9]+)F / (\\\\w+)", 2)', CTX) == "Sunny"
        assert evaluate('REGEXMATCH("ABC-123", "^[A-Z]{3}-[0-9]+$")', CTX) == "Yes"
        assert evaluate('REGEXREPLACE("a  b   c", "\\\\s+", " ")', CTX) == "a b c"
