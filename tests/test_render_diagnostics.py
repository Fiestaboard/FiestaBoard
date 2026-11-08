"""H5: what each formula evaluated to, and what each template line produced.

The 2.10 editor (04c) shows a value beside every ``{{= … }}`` atom and an
inspector clip report: "3 of 7 rows shown · line 5 stops the list · Hidden:
…", "↳ row 2 of 7 · from line 2", "widest row 10 of 22". The engine already
knows all of it (``_overflow_budget``, the FOREACH split) and discarded it.
``render_lines(..., report=RenderReport())`` now keeps it, and
``POST /templates/render`` / ``/render/live`` return it on
``diagnostics: true``. Pinned here:

- per formula: span, value (what the board shows), error code, ``#SYNTAX``
  offset, message, evaluated against the render's own context and clock;
- per template line: first row, rows wanted / shown, why it was clipped
  (``stopped_by_line``, ``board_end``, ``covered``, ``beyond_board``) and by
  which line, the widest row and whether it was cut, the hidden rows;
- the routes: off by default (unchanged), list templates fully, string
  templates formulas only, canvas pages ``null``;
- validate: a non-blank list line past the board's rows is ``beyond_board``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.templates.diagnostics import RenderReport
from src.templates.engine import TemplateEngine
from src.templates.expressions import find_formulas

ETAS = [
    {"route": "J", "eta": "DUE"},
    {"route": "14", "eta": "7M"},
    {"route": "49", "eta": "12M"},
    {"route": "J", "eta": "15M"},
    {"route": "14", "eta": "21M"},
    {"route": "49", "eta": "27M"},
    {"route": "KT", "eta": "8:15"},
]
CTX = {
    "transit": {"etas": ETAS, "three": ETAS[:3], "many": [{"route": str(n), "eta": "1M"} for n in range(20)]},
    "weather": {"temp": "62"},
    "demo": {"words": "ONE TWO THREE FOUR SIX SEVEN EIGHT NINE TEN"},
}
LIST = '{{= FOREACH(transit.etas, item.route & " " & item.eta) }}'
COMMUTE = ["MUNI", LIST, "", "", "{{weather.temp}} F", "BYE", "EXTRA"]


@pytest.fixture
def engine():
    return TemplateEngine()


def _report(engine, lines, *, metadata=None, **device) -> tuple[list[str], RenderReport]:
    report = RenderReport()
    rendered = engine.render_lines(lines, dict(CTX), line_metadata=metadata, report=report, **device)
    return rendered.split("\n"), report


def _line(report: RenderReport, number: int) -> dict:
    entry = report.lines[number - 1].to_json()
    assert entry["line"] == number
    return entry


# ── formulas ────────────────────────────────────────────────────────────────


def test_a_formula_reports_its_span_and_value(engine):
    line = "SUM {{= 1 + 2 }} OK"
    _, report = _report(engine, [line])

    (formula,) = [f.to_json() for f in report.formulas]
    (start, end, body) = find_formulas(line)[0]
    assert formula == {
        "line": 1,
        "start": start,
        "end": end,
        "source": body,
        "value": "3",
        "error": None,
        "error_at": None,
        "message": None,
        "value_truncated": False,
    }


def test_a_division_by_zero_reports_its_code(engine):
    _, report = _report(engine, ["{{= 1 / 0 }}"])

    formula = report.formulas[0].to_json()
    assert (formula["value"], formula["error"]) == ("#DIV/0", "#DIV/0")


def test_a_syntax_error_reports_where_in_the_body(engine):
    _, report = _report(engine, ["X", "{{= (1 + 2 }}"])

    formula = report.formulas[0].to_json()
    assert formula["line"] == 2
    assert formula["error"] == "#SYNTAX"
    assert isinstance(formula["error_at"], int)
    assert formula["value"] == f"#SYNTAX:{formula['error_at']}"
    assert formula["message"]


def test_a_missing_value_reports_ref_with_the_reason(engine):
    _, report = _report(engine, ["{{= nope.count + 1 }}"])

    formula = report.formulas[0].to_json()
    assert formula["error"] == "#REF"
    assert formula["message"] == "No value at nope.count"


def test_a_missing_list_names_the_list_not_the_loop_item(engine):
    _, report = _report(engine, ["{{= FOREACH(nope.items, item.route) }}"])

    formula = report.formulas[0].to_json()
    assert (formula["error"], formula["message"]) == ("#REF", "No value at nope.items")


def test_a_formula_value_is_what_the_board_shows_at_the_renders_instant(engine):
    from datetime import datetime

    from src.templates.expressions import RENDER_CLOCK_KEY

    report = RenderReport()
    context = {**CTX, RENDER_CLOCK_KEY: datetime(2001, 2, 3, 4, 5, 6)}
    rows = engine.render_lines(['{{= FORMATDATE(NOW(), "HH:mm:ss") }}'], context, report=report).split("\n")

    assert report.formulas[0].value == rows[0].strip() == "04:05:06"


def test_formulas_on_lines_past_the_board_are_still_reported(engine):
    _, report = _report(engine, ["A", "B", "C", "{{= 2 * 3 }}"], device_type="note")

    assert [(f.line, f.value) for f in report.formulas] == [(4, "6")]


# ── lines ───────────────────────────────────────────────────────────────────


def test_a_plain_line_shows_its_one_row(engine):
    _, report = _report(engine, COMMUTE)

    assert _line(report, 1) == {
        "line": 1,
        "first_row": 1,
        "rows_wanted": 1,
        "rows_shown": 1,
        "clip": None,
        "clip_line": None,
        "widest": 4,
        "cut": False,
        "hidden": [],
    }


def test_a_list_stopped_by_a_line_below_says_which_and_what_it_hid(engine):
    rows, report = _report(engine, COMMUTE)

    entry = _line(report, 2)
    assert (entry["first_row"], entry["rows_wanted"], entry["rows_shown"]) == (2, 7, 3)
    assert (entry["clip"], entry["clip_line"]) == ("stopped_by_line", 5)
    assert entry["hidden"] == ["J 15M", "14 21M", "49 27M", "KT 8:15"]
    assert entry["widest"] == 6  # "49 12M", the widest of the three rows shown
    assert rows[1].strip() == "J DUE"


def test_the_lines_a_list_spills_over_are_covered_by_it(engine):
    _, report = _report(engine, COMMUTE)

    for number in (3, 4):
        entry = _line(report, number)
        assert (entry["first_row"], entry["rows_shown"]) == (None, 0)
        assert (entry["clip"], entry["clip_line"]) == ("covered", 2)


def test_a_line_past_the_last_row_is_beyond_the_board(engine):
    _, report = _report(engine, COMMUTE)

    entry = _line(report, 7)
    assert (entry["first_row"], entry["rows_shown"], entry["clip"]) == (None, 0, "beyond_board")
    assert len(report.lines) == len(COMMUTE)


def test_a_list_that_runs_off_the_bottom_is_clipped_by_the_board(engine):
    lines = ["A", "B", "C", "D", "{{= FOREACH(transit.three, item.route) }}", ""]
    _, report = _report(engine, lines)

    entry = _line(report, 5)
    assert (entry["first_row"], entry["rows_wanted"], entry["rows_shown"]) == (5, 3, 2)
    assert (entry["clip"], entry["clip_line"]) == ("board_end", None)
    assert entry["hidden"] == ["49"]


def test_a_wrapped_line_reports_the_rows_it_needs(engine):
    metadata = [{"alignment": "left", "wrap": True}, {"alignment": "left", "wrap": False}]
    _, report = _report(engine, ["{{demo.words}}", "END"], metadata=metadata)

    entry = _line(report, 1)
    assert (entry["rows_wanted"], entry["rows_shown"]) == (2, 1)
    assert (entry["clip"], entry["clip_line"]) == ("stopped_by_line", 2)
    assert entry["hidden"] == ["SEVEN EIGHT NINE TEN"]


def test_a_wrapped_line_with_room_shows_every_row(engine):
    metadata = [{"alignment": "left", "wrap": True}] + [{"alignment": "left", "wrap": False}] * 2
    _, report = _report(engine, ["{{demo.words}}", "", "END"], metadata=metadata)

    entry = _line(report, 1)
    assert (entry["rows_wanted"], entry["rows_shown"], entry["clip"]) == (2, 2, None)
    assert (_line(report, 2)["clip"], _line(report, 2)["clip_line"]) == ("covered", 1)


def test_an_over_wide_line_is_measured_and_cut(engine):
    _, report = _report(engine, ["A" * 30])

    entry = _line(report, 1)
    assert (entry["widest"], entry["cut"]) == (30, True)


def test_hidden_rows_are_capped_at_the_boards_height(engine):
    _, report = _report(engine, ["{{= FOREACH(transit.many, item.route) }}"], device_type="note")

    entry = _line(report, 1)
    assert (entry["rows_wanted"], entry["rows_shown"]) == (20, 3)
    assert len(entry["hidden"]) == 3


def test_no_report_renders_exactly_as_before(engine):
    with_report, _ = _report(engine, COMMUTE)
    without = engine.render_lines(COMMUTE, dict(CTX)).split("\n")

    assert with_report == without


# ── the routes ──────────────────────────────────────────────────────────────


@pytest.fixture
def client(_isolated_data_dir, monkeypatch):
    from src.api_server import app

    monkeypatch.setattr(TemplateEngine, "_build_context", lambda self, *a, **k: dict(CTX))
    return TestClient(app)


def test_render_without_the_flag_is_unchanged(client):
    body = client.post("/templates/render", json={"template": COMMUTE}).json()

    assert set(body) == {"rendered", "lines", "line_count"}


def test_render_with_the_flag_reports_formulas_and_lines(client):
    response = client.post("/templates/render", json={"template": COMMUTE, "diagnostics": True})

    assert response.status_code == 200, response.text
    diagnostics = response.json()["diagnostics"]
    assert [f["line"] for f in diagnostics["formulas"]] == [2]
    assert [entry["clip"] for entry in diagnostics["lines"]] == [
        None,
        "stopped_by_line",
        "covered",
        "covered",
        None,
        None,
        "beyond_board",
    ]


def test_live_render_reports_too(client):
    response = client.post("/templates/render/live", json={"template": COMMUTE, "diagnostics": True})

    assert response.status_code == 200, response.text
    assert response.json()["diagnostics"]["lines"][1]["rows_shown"] == 3


def test_a_string_template_reports_formulas_only(client):
    response = client.post("/templates/render", json={"template": "A {{= 2 + 2 }}", "diagnostics": True})

    diagnostics = response.json()["diagnostics"]
    assert [(f["value"], f["start"]) for f in diagnostics["formulas"]] == [("4", 2)]
    assert diagnostics["lines"] is None


def test_a_page_with_canvases_reports_nothing_yet(client):
    canvas = {"id": "sun", "area": {"row": 1, "col": 1, "rows": 1, "cols": 2}, "content": {"background": "#ff0000"}}
    request = {"template": ["HELLO"], "device_type": "panel", "grid_rows": 10, "grid_cols": 16}
    response = client.post("/templates/render", json={**request, "canvases": [canvas], "diagnostics": True})

    assert response.status_code == 200, response.text
    assert response.json()["diagnostics"] is None


# ── validate: lines past the board (carried from H4) ────────────────────────


def test_validate_flags_a_list_line_past_the_boards_rows(client):
    body = client.post("/templates/validate", json={"template": ["A", "B", "C", "D"], "device_type": "note"}).json()

    assert [(e["line"], e["code"]) for e in body["errors"]] == [(4, "beyond_board")]
    assert body["valid"] is False


def test_validate_allows_blank_lines_past_the_rows(client):
    body = client.post(
        "/templates/validate", json={"template": ["A", "B", "C", "", "  "], "device_type": "note"}
    ).json()

    assert body == {"valid": True, "errors": [], "rows": 3, "cols": 15}


def test_validate_leaves_a_string_template_alone(client):
    body = client.post("/templates/validate", json={"template": "A\nB\nC\nD", "device_type": "note"}).json()

    assert body["valid"] is True


# ── review follow-ups: a bounded payload, and the surviving mutants ─────────

#: 16 KB: longer than a Flagship could show, within any formula length cap.
LONG = '{{= REPT(REPT("A",1024),16) }}'
#: The review's one-line megabyte (a capped evaluator answers #VALUE instead).
NESTED = '{{= REPT(REPT("A",1024),1024) }}'


def test_a_long_formula_value_is_cut_and_flagged(engine):
    _, report = _report(engine, [LONG])

    formula = report.formulas[0].to_json()
    assert formula["value_truncated"] is True
    assert len(formula["value"]) == 4096


def test_a_short_formula_value_is_whole(engine):
    _, report = _report(engine, ["{{= 1 + 2 }}"])

    assert report.formulas[0].to_json()["value_truncated"] is False


def test_a_big_boards_value_limit_is_its_area(engine):
    many = "{{= FOREACH(transit.many, REPT(item.route, 200)) }}"
    _, report = _report(engine, [many], device_type="panel", grid_rows=96, grid_cols=128)

    formula = report.formulas[0].to_json()
    assert formula["value_truncated"] is False
    assert len(formula["value"]) > 4096


def test_hidden_rows_are_cut_to_the_board_width(engine):
    wide = '{{= FOREACH(transit.many, REPT("W", 500)) }}'
    _, report = _report(engine, [wide], device_type="note")

    entry = _line(report, 1)
    assert entry["hidden"] and all(row == "W" * 15 for row in entry["hidden"])


def test_render_with_diagnostics_of_a_long_formula_stays_small(client):
    response = client.post("/templates/render", json={"template": [LONG], "diagnostics": True})

    assert response.status_code == 200, response.text
    assert len(response.content) < 16 * 1024
    assert response.json()["diagnostics"]["formulas"][0]["value_truncated"] is True


def test_render_with_diagnostics_of_nested_rept_stays_small(client):
    response = client.post("/templates/render", json={"template": [NESTED], "diagnostics": True})

    assert response.status_code == 200, response.text
    assert len(response.content) < 16 * 1024


def test_a_row_exactly_the_board_width_is_not_cut(engine):
    _, report = _report(engine, ["A" * 22])

    entry = _line(report, 1)
    assert (entry["widest"], entry["cut"]) == (22, False)


def test_fill_space_does_not_count_toward_the_widest_row(engine):
    _, report = _report(engine, ["AB{{fill_space}}CD"])

    entry = _line(report, 1)
    assert (entry["widest"], entry["cut"]) == (4, False)


def test_a_missing_loop_field_is_not_reported_as_a_plugin_path(engine):
    _, report = _report(engine, ["{{= FOREACH(transit.etas, item.absent) }}"])

    formula = report.formulas[0].to_json()
    assert formula["error"] == "#REF"
    assert formula["message"] is None
