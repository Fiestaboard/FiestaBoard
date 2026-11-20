"""Formula lines in ``validate_template`` (bug bash BB-B-1, BB-B-2).

A ``{{= … }}`` has no plugin ``max_lengths`` entry, so the width check used
to count every formula as the whole board (22 tiles) and reported lines the
board shows in full as "cut off". It is now measured by the value it renders
to, the same evaluation Inspect and the render diagnostics report.

The Problems list is the validate response. It used to hold only the static
checks, so a formula the board draws as ``#DIV/0`` or ``#VALUE`` was not a
problem while an ``IFERROR`` that handles its missing source was.
"""

from unittest.mock import patch

import pytest

from src.templates.engine import TemplateEngine

BROKEN_FORMULA = [
    "DEBUG ME",
    "{{= missing.value }}",
    "{{= 1 / 0 }}",
    '{{= IFERROR(nope.x, "FALLBACK") }}',
    '{{= FIXED("abc", 2) }}',
    "",
]


@pytest.fixture
def engine():
    engine = TemplateEngine()
    with (
        patch.object(TemplateEngine, "get_available_variables", return_value={"countdown": ["event_name"]}),
        patch.object(TemplateEngine, "get_all_known_sources", return_value={"countdown"}),
        patch.object(TemplateEngine, "_build_context", return_value={"countdown": {"event_name": "Launch"}}),
    ):
        yield engine


def too_long(errors):
    return {e.line: e.max_length for e in errors if e.code == "line_too_long"}


class TestFormulaWidth:
    def test_a_short_formula_beside_text_fits(self, engine):
        template = '12" PIZZA $12.00\n16" PIZZA {{= LET(p, 18.5, "$" & FIXED(p, 2)) }}'
        assert too_long(engine.validate_template(template, cols=22)) == {}

    def test_price_with_a_trailing_space_fits(self, engine):
        assert too_long(engine.validate_template('PRICE {{= "$" & FIXED(3.5, 2) }}', cols=22)) == {}

    def test_a_formula_is_measured_by_its_value(self, engine):
        errors = engine.validate_template('NEXT {{= "ABCDEFGHIJKLMNOPQRSTUVWXYZ" }}', cols=22)
        assert too_long(errors) == {1: 31}

    def test_a_formula_reading_data_is_measured_by_the_current_value(self, engine):
        errors = engine.validate_template("EVENT: {{= UPPER(countdown.event_name) }}", cols=22)
        assert too_long(errors) == {}

    def test_a_colour_tile_from_a_formula_is_one_tile(self, engine):
        template = '{{= COLOR("red") }} {{= countdown.event_name }} XXXXXXXXXXXXX'
        # 1 tile + space + "Launch" (6) + space + 13 = 22
        assert too_long(engine.validate_template(template, cols=22)) == {}


class TestFormulaProblems:
    def problems(self, engine):
        return [(e.line, e.message) for e in engine.validate_template("\n".join(BROKEN_FORMULA), cols=22)]

    def test_every_formula_the_board_draws_as_an_error_is_a_problem(self, engine):
        lines = sorted({line for line, _ in self.problems(engine)})
        assert lines == [2, 3, 5]

    def test_the_runtime_error_is_named(self, engine):
        messages = dict(self.problems(engine))
        assert "#DIV/0" in messages[3]
        assert "#VALUE" in messages[5]

    def test_an_iferror_that_handles_its_missing_source_is_not_a_problem(self, engine):
        assert all(line != 4 for line, _ in self.problems(engine))

    def test_a_static_problem_is_not_reported_twice(self, engine):
        assert [line for line, _ in self.problems(engine)].count(2) == 1

    def test_missing_data_from_a_known_source_is_not_a_template_problem(self, engine):
        assert engine.validate_template('{{= countdown.days & " DAYS" }}', cols=22) == []
