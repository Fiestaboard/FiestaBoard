"""Every formula example in the published reference must actually evaluate.

``docs/reference/template-formulas.md`` is user-facing, and this repo has a long
tail of docs-drift issues (#1640, #2058, …) where a published example did not
work. These tests run the examples the array/date/reuse sections added, so the
page cannot promise a formula the engine rejects.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.templates.engine import TemplateEngine
from src.templates.expressions import evaluate

NOW = datetime(2026, 9, 24, 17, 30, tzinfo=ZoneInfo("America/Los_Angeles"))

CTX = {
    "__now__": NOW,
    "mlb": {
        "games": [
            {"team1": "SF", "team2": "LA", "score1": 4, "score2": 2, "final": True},
            {"team1": "NY", "team2": "BOS", "score1": 1, "score2": 7, "final": False},
            {"team1": "CHC", "team2": "STL", "score1": 3, "score2": 3, "final": False},
        ]
    },
    "transit": {"stops": [{"eta": 4, "name": "MAIN"}, {"eta": 11, "name": "OAK"}]},
    "launch": {"day": "2026-12-25"},
    "weather": {"temperature": 72, "condition": "sunny", "summary": "72F / Sunny"},
}


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        # Arrays section
        ("COUNT(mlb.games)", "3"),
        ('AT(mlb.games, 0, "team1")', "SF"),
        ('AT(mlb.games, 9, "team1")', ""),
        ('FOREACH(mlb.games, item.team1 & " " & item.score1, 4)', "SF 4\nNY 1\nCHC 3"),
        ("mlb.games", "#VALUE"),
        (
            'FOREACH(SLICE(SORT(FILTER(mlb.games, item.final), "score1", "desc"), 0, 3),'
            " item.team1 & PADLEFT(item.score1, 3))",
            "SF  4",
        ),
        # Dates section
        ("DATEDIFF(TODAY(), DATE(launch.day))", "92"),
        ('FORMATDATE(NOW(), "ddd hh:mm AP")', "THU 5:30 PM"),
        ('IF(HOUR(NOW()) >= 17, "EVENING", "DAY")', "EVENING"),
        ('DATEADD(DATE("2026-01-31"), 1, "months")', "2026-02-28 00:00"),
        ("WEEKDAY(NOW())", "4"),
        # Reuse section
        (
            'LET(done, FILTER(mlb.games, item.final), COUNT(done) & " FINAL: " & JOIN(done, " ", "team1"))',
            "1 FINAL: SF",
        ),
        # Text section
        ('JOIN(SPLIT(weather.summary), "|")', "72F|/|Sunny"),
        ('REGEXEXTRACT(weather.summary, "[0-9]+")', "72"),
        ('REGEXMATCH(weather.summary, "(a+)+b")', "#VALUE"),
        # Cookbook
        ('COUNT(mlb.games) & " GAMES"', "3 GAMES"),
        (
            'IF(COUNT(transit.stops) = 0, "NO SERVICE",'
            ' FOREACH(SLICE(transit.stops, 0, 3), item.eta & " " & item.name))',
            "4 MAIN\n11 OAK",
        ),
        (
            'LET(live, FILTER(mlb.games, NOT(item.final)), COUNT(live) & " IN PROGRESS")',
            "2 IN PROGRESS",
        ),
    ],
)
def test_documented_expression_evaluates_as_published(expression, expected):
    assert evaluate(expression, CTX) == expected


def test_the_documented_scoreboard_renders_the_documented_board():
    """The reference shows this exact template and this exact output."""
    rendered = TemplateEngine().render_lines(
        [
            "SCORES ({{= COUNT(mlb.games) }})",
            '{{= FOREACH(mlb.games, item.team1 & " " & item.score1, 4) }}',
        ],
        context=CTX,
        device_type="flagship",
    )
    assert [line.strip() for line in rendered.split("\n")][:4] == ["SCORES (3)", "SF 4", "NY 1", "CHC 3"]


def test_an_empty_array_leaves_the_rows_it_would_have_filled_alone():
    rendered = TemplateEngine().render_lines(
        ["{{= FOREACH(empty.items, item.x, 4) }}", "", "FOOTER"],
        context={"empty": {"items": []}},
        device_type="flagship",
    )
    lines = [line.strip() for line in rendered.split("\n")]
    assert lines[0] == ""
    assert lines[2] == "FOOTER"
