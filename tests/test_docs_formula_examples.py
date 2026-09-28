"""The published formula reference must not promise formulas the engine rejects.

``docs/reference/template-formulas.md`` is user-facing, and this repo has a long
tail of docs-drift issues (#1640, #2058, …) where a published example did not
work. These tests **read that page**: every ``{{= ... }}`` example in its code
fences and inline code spans is pulled out and checked against the engine — the
formula matcher has to recognize it, ``validate_expression`` has to accept it,
and the sources it names have to be ones the page itself introduces. Nothing is
hand-mirrored, so an example added or edited on the page is covered the day it
lands.

Examples whose *output* the page publishes are additionally evaluated for that
exact value, by the parametrized table further down.
"""

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.templates.engine import TemplateEngine
from src.templates.expressions import evaluate, find_formulas, validate_expression

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "reference" / "template-formulas.md"

#: Plugin-style sources the page introduces in its examples. Keeping this
#: explicit is the point: an example that names something else is either a typo
#: or a deliberate new example, and both deserve a human look.
#: ``test_the_source_allowlist_matches_the_page`` keeps it from rotting.
DOC_SOURCES = frozenset(
    {
        "baywheels",
        "home_assistant",
        "launch",
        "mlb",
        "stocks",
        "transit",
        "weather",
    }
)

#: The page writes ``{{= ... }}`` in prose when it means "a formula, any
#: formula". That is the marker, not an example.
_MARKER_PLACEHOLDER = "..."

#: Deliberately looser than the engine's own matcher: an example that the
#: engine would *not* recognize as a formula still has to be caught, not
#: skipped. ``test_every_published_example_is_a_formula_the_engine_recognizes``
#: is what closes the gap between the two.
_LOOSE_FORMULA = re.compile(r"\{\{=(.*?)\}\}", re.DOTALL)

_FENCE = "```"


def _code_regions(markdown: str) -> list[tuple[int, str]]:
    """Return ``(first line number, text)`` for each code region of the page.

    A region is a fenced block (whole, so multi-line examples survive) or one
    inline code span. Prose outside code is skipped: the page discusses ``{{=``
    and ``}}`` as separate spans of prose, which is not an example.
    """
    regions: list[tuple[int, str]] = []
    fence_start = 0
    fence_lines: list[str] = []
    in_fence = False

    for number, line in enumerate(markdown.splitlines(), start=1):
        if line.lstrip().startswith(_FENCE):
            if in_fence:
                regions.append((fence_start, "\n".join(fence_lines)))
                fence_lines = []
            else:
                fence_start = number + 1
            in_fence = not in_fence
            continue
        if in_fence:
            fence_lines.append(line)
        else:
            for span in re.finditer(r"`([^`\n]+)`", line):
                regions.append((number, span.group(1)))

    if in_fence:  # pragma: no cover - an unclosed fence is a broken page
        regions.append((fence_start, "\n".join(fence_lines)))
    return regions


def published_examples(markdown: str) -> list[tuple[int, str, str]]:
    """Return ``(line number, raw ``{{= }}`` text, body)`` for each example."""
    found: list[tuple[int, str, str]] = []
    for start, region in _code_regions(markdown):
        for match in _LOOSE_FORMULA.finditer(region):
            body = match.group(1).strip()
            if body == _MARKER_PLACEHOLDER:
                continue
            found.append((start + region[: match.start()].count("\n"), match.group(0), body))
    return found


EXAMPLES = published_examples(DOC_PATH.read_text(encoding="utf-8"))
EXAMPLE_IDS = [f"L{line}-{body[:40]}" for line, _, body in EXAMPLES]


def _sources_named(body: str) -> set[str]:
    """Sources ``body`` reads, via the public validator's own #REF reports."""
    return {
        issue.message.split(": ", 1)[1]
        for issue in validate_expression(body, known_sources=frozenset())
        if issue.code == "#REF"
    }


def test_the_extractor_finds_the_pages_examples():
    """A scanner that silently matched nothing would make every test below vacuous."""
    assert len(EXAMPLES) >= 15, f"only {len(EXAMPLES)} examples found in {DOC_PATH.name}"


@pytest.mark.parametrize(("line", "raw", "body"), EXAMPLES, ids=EXAMPLE_IDS)
def test_every_published_example_is_a_formula_the_engine_recognizes(line, raw, body):
    """The engine's own matcher has to see what the page calls a formula.

    It is stricter than it looks: ``{`` and ``}`` cannot appear inside a
    formula, so an example that puts a ``{sun}`` symbol in a string literal
    renders as its own source text on a real board.
    """
    assert find_formulas(raw) == [(0, len(raw), body)], f"line {line}: not a formula the engine will run"


@pytest.mark.parametrize(("line", "raw", "body"), EXAMPLES, ids=EXAMPLE_IDS)
def test_every_published_example_parses_and_validates(line, raw, body):
    """Parse errors, unknown functions, wrong arity, unknown sources — all caught."""
    issues = [(issue.code, issue.message) for issue in validate_expression(body, known_sources=DOC_SOURCES)]
    assert issues == [], f"line {line}: {body}"


def test_the_source_allowlist_matches_the_page():
    """Every allowed source is used, and every used source was allowed on purpose."""
    used = set().union(*(_sources_named(body) for _, _, body in EXAMPLES))
    assert used == set(DOC_SOURCES)


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
        # The page no longer claims a pattern is refused for its shape: this
        # one is simply run, and on a short subject it finishes and answers.
        ('REGEXMATCH(weather.summary, "(a+)+b")', "No"),
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
