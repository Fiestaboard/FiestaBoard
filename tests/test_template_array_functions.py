"""Array/collection functions in the inline expression language.

Issue #2050: a plugin can declare ``variables.arrays`` in its manifest, but a
template could only index one item at a time (``{{p.games.0.team1}}``) with no
way to ask how many items exist. Authors hand-unrolled one line per possible
item and wrapped each in an ``IF`` to hide ``???`` for items that weren't
there. These tests cover the functions that replace that pattern.
"""

from src.templates.engine import TemplateEngine
from src.templates.expressions import evaluate

GAMES_CTX = {
    "mlb": {
        "games": [
            {"team1": "SF", "score1": 4, "team2": "LA", "score2": 2, "final": True},
            {"team1": "NY", "score1": 1, "team2": "BOS", "score2": 7, "final": False},
            {"team1": "CHC", "score1": 3, "team2": "STL", "score2": 3, "final": False},
        ],
        "count_label": "games",
    },
    "transit": {"etas": [4, 11, 26]},
    "empty": {"items": []},
}


class TestCount:
    def test_counts_array_of_dicts(self):
        assert evaluate("COUNT(mlb.games)", GAMES_CTX) == "3"

    def test_counts_array_of_scalars(self):
        assert evaluate("COUNT(transit.etas)", GAMES_CTX) == "3"

    def test_empty_array_is_zero(self):
        assert evaluate("COUNT(empty.items)", GAMES_CTX) == "0"

    def test_missing_source_is_ref_error(self):
        assert evaluate("COUNT(nope.items)", GAMES_CTX) == "#REF"

    def test_scalar_is_value_error(self):
        assert evaluate("COUNT(mlb.count_label)", GAMES_CTX) == "#VALUE"

    def test_drives_conditional_display(self):
        assert evaluate('IF(COUNT(mlb.games) > 2, "MANY", "FEW")', GAMES_CTX) == "MANY"


class TestAt:
    def test_reads_field_of_nth_item(self):
        assert evaluate('AT(mlb.games, 0, "team1")', GAMES_CTX) == "SF"

    def test_index_is_zero_based(self):
        assert evaluate('AT(mlb.games, 1, "team1")', GAMES_CTX) == "NY"

    def test_out_of_range_is_blank_not_error(self):
        assert evaluate('AT(mlb.games, 9, "team1")', GAMES_CTX) == ""

    def test_missing_field_is_blank(self):
        assert evaluate('AT(mlb.games, 0, "nope")', GAMES_CTX) == ""

    def test_scalar_array_without_field(self):
        assert evaluate("AT(transit.etas, 1)", GAMES_CTX) == "11"

    def test_negative_index_is_blank(self):
        assert evaluate('AT(mlb.games, -1, "team1")', GAMES_CTX) == ""


class TestForeach:
    def test_emits_one_row_per_item(self):
        out = evaluate('FOREACH(mlb.games, item.team1 & " " & item.score1)', GAMES_CTX)
        assert out == "SF 4\nNY 1\nCHC 3"

    def test_limit_caps_rows(self):
        assert evaluate("FOREACH(mlb.games, item.team1, 2)", GAMES_CTX) == "SF\nNY"

    def test_limit_larger_than_array_emits_all(self):
        assert evaluate("FOREACH(mlb.games, item.team1, 99)", GAMES_CTX) == "SF\nNY\nCHC"

    def test_empty_array_emits_nothing(self):
        assert evaluate("FOREACH(empty.items, item.x)", GAMES_CTX) == ""

    def test_scalar_items_bind_to_bare_item(self):
        assert evaluate('FOREACH(transit.etas, item & "M")', GAMES_CTX) == "4M\n11M\n26M"

    def test_row_expression_may_use_functions_and_outer_variables(self):
        out = evaluate('FOREACH(mlb.games, UPPER(item.team1) & "/" & mlb.count_label, 1)', GAMES_CTX)
        assert out == "SF/games"

    def test_index_is_available_as_item_index(self):
        out = evaluate('FOREACH(mlb.games, item.index & ":" & item.team1, 2)', GAMES_CTX)
        assert out == "1:SF\n2:NY"

    def test_item_outside_foreach_is_ref_error(self):
        assert evaluate("item.team1", GAMES_CTX) == "#REF"

    def test_non_array_first_arg_is_value_error(self):
        assert evaluate("FOREACH(mlb.count_label, item)", GAMES_CTX) == "#VALUE"


class TestArraySetOps:
    def test_filter_keeps_matching_items(self):
        assert evaluate("FOREACH(FILTER(mlb.games, item.final), item.team1)", GAMES_CTX) == "SF"

    def test_filter_with_comparison(self):
        out = evaluate("FOREACH(FILTER(mlb.games, item.score2 > 2), item.team2)", GAMES_CTX)
        assert out == "BOS\nSTL"

    def test_filter_on_scalars(self):
        assert evaluate("COUNT(FILTER(transit.etas, item > 10))", GAMES_CTX) == "2"

    def test_sort_ascending_by_field(self):
        assert evaluate('FOREACH(SORT(mlb.games, "score1"), item.team1)', GAMES_CTX) == "NY\nCHC\nSF"

    def test_sort_descending(self):
        out = evaluate('FOREACH(SORT(mlb.games, "score1", "desc"), item.team1)', GAMES_CTX)
        assert out == "SF\nCHC\nNY"

    def test_sort_scalars_without_field(self):
        assert evaluate('JOIN(SORT(transit.etas, "", "desc"), ",")', GAMES_CTX) == "26,11,4"

    def test_slice_takes_a_window(self):
        assert evaluate("FOREACH(SLICE(mlb.games, 1, 2), item.team1)", GAMES_CTX) == "NY\nCHC"

    def test_join_scalars(self):
        assert evaluate('JOIN(transit.etas, " ")', GAMES_CTX) == "4 11 26"

    def test_join_field_of_dicts(self):
        assert evaluate('JOIN(mlb.games, "-", "team1")', GAMES_CTX) == "SF-NY-CHC"

    def test_aggregates_over_a_field(self):
        assert evaluate('SUMOF(mlb.games, "score1")', GAMES_CTX) == "8"
        assert evaluate('MAXOF(mlb.games, "score1")', GAMES_CTX) == "4"
        assert evaluate('MINOF(mlb.games, "score1")', GAMES_CTX) == "1"

    def test_aggregates_over_scalars(self):
        assert evaluate("SUMOF(transit.etas)", GAMES_CTX) == "41"
        assert evaluate("AVGOF(transit.etas)", GAMES_CTX) == "13.7"

    def test_aggregate_of_empty_array_is_zero(self):
        assert evaluate("SUMOF(empty.items)", GAMES_CTX) == "0"

    def test_composed_pipeline(self):
        out = evaluate(
            'FOREACH(SLICE(SORT(FILTER(mlb.games, item.score1 > 1), "score1", "desc"), 0, 2),'
            " item.team1 & PADLEFT(item.score1, 3))",
            GAMES_CTX,
        )
        assert out == "SF  4\nCHC  3"


class TestBareArrayRendering:
    def test_bare_array_is_value_error_not_python_repr(self):
        assert evaluate("mlb.games", GAMES_CTX) == "#VALUE"

    def test_array_in_arithmetic_is_value_error(self):
        assert evaluate("mlb.games + 1", GAMES_CTX) == "#VALUE"


class TestForeachRendersAcrossBoardRows:
    def test_row_emitting_formula_fills_lines_below(self):
        engine = TemplateEngine()
        rendered = engine.render_lines(
            ["SCORES", '{{= FOREACH(mlb.games, item.team1 & " " & item.score1, 3) }}'],
            context=GAMES_CTX,
            device_type="flagship",
        )
        lines = rendered.split("\n")
        assert lines[0].strip() == "SCORES"
        assert lines[1].strip() == "SF 4"
        assert lines[2].strip() == "NY 1"
        assert lines[3].strip() == "CHC 3"

    def test_rows_below_a_foreach_are_not_overwritten_beyond_its_output(self):
        engine = TemplateEngine()
        rendered = engine.render_lines(
            ["{{= FOREACH(mlb.games, item.team1, 2) }}", "", "", "FOOTER"],
            context=GAMES_CTX,
            device_type="flagship",
        )
        lines = rendered.split("\n")
        assert lines[0].strip() == "SF"
        assert lines[1].strip() == "NY"
        assert lines[3].strip() == "FOOTER"

    def test_row_emitting_formula_does_not_trigger_line_too_long(self):
        engine = TemplateEngine()
        errors = engine.validate_template('{{= FOREACH(mlb.games, item.team1 & " " & item.score1) }}', cols=22)
        assert [e.message for e in errors if "too long" in e.message] == []
