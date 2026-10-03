"""Parity between ``src.markup`` and FiestaUI's message parser.

The fixtures in ``tests/fixtures/markup/`` were produced by running FiestaUI's
real TypeScript ``parseLine`` / ``messageToGrid`` (see
``scripts/markup_fixtures/generate.sh``). Every case is replayed here against
the Python parser, with the same options.

A handful of inputs parse differently on purpose. Each is listed in
``KNOWN_DIVERGENCES`` with the reason, and in every one of them the Python
side draws what the physical board draws today — the FiestaUI preview is the
one that disagrees with the hardware. Two guard tests keep that list honest:
an entry that stops diverging (FiestaUI fixed it upstream) fails, and so does
an entry whose Python output stops matching today's board.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.markup import BOARD_ICONS, SPAN_COLOR_CODES, message_to_grid, parse_line, tokens_to_codes
from src.text_to_board import text_to_board_array

FIXTURE = Path(__file__).parent / "fixtures" / "markup" / "fiestaui_parse_line.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))

# Case ids without their "legacy/" / "ext/" prefix: the divergence holds in both modes.
TOKEN_DIVERGENCES = {
    "alias-filled": "FiestaUI has no `filled` colour name; the board draws {filled} as tile 71",
    "alias-filled-upper": "FiestaUI has no `filled` colour name; the board draws {FILLED} as tile 71",
    "end-unknown-name": "FiestaUI drops any {/...}; the board only drops {/} and {/<colour>}",
    "end-numeric": "FiestaUI drops any {/...}; the board draws {/63} literally",
    "end-with-colon": "FiestaUI drops any {/...}; the board draws {/white:A} literally",
    "block-half-head-bg": "FiestaUI drops any {/...}; the board draws {/red:A} literally",
    "plain-emoji": "JavaScript strings are UTF-16: FiestaUI splits an emoji into two surrogate cells",
}
# Same tokens, different 0-71 projection.
CODE_DIVERGENCES = {
    "code62-heart-suit": "the board encodes a typed heart as code 62; FiestaUI's getCharIndex has no entry for it",
    "code62-heart-emoji": "the board encodes a typed heart as code 62; FiestaUI's getCharIndex has no entry for it",
}


def _base_id(case_id: str) -> str:
    # "ext/cap-long-span/cap-3" -> "cap-long-span"
    return case_id.split("/")[1]


def _parse(case: dict):
    options = case["options"]
    return parse_line(
        case["line"],
        case.get("maxTokens"),
        extended_markup=options.get("extendedMarkup", False),
        preserve_case=options.get("preserveCase", False),
    )


def _cases(predicate):
    return [pytest.param(c, id=c["id"]) for c in DATA["lines"] if predicate(c)]


TOKEN_PARITY = _cases(lambda c: _base_id(c["id"]) not in TOKEN_DIVERGENCES)
CODE_PARITY = _cases(lambda c: "codes" in c and _base_id(c["id"]) not in TOKEN_DIVERGENCES | CODE_DIVERGENCES)
TOKEN_DIVERGENT = _cases(lambda c: _base_id(c["id"]) in TOKEN_DIVERGENCES)
CODE_DIVERGENT = _cases(lambda c: _base_id(c["id"]) in CODE_DIVERGENCES)


def test_fixture_records_its_fiestaui_source():
    source = DATA["header"]["fiestaui"]
    assert re.fullmatch(r"[0-9a-f]{40}", source["commit"])
    assert source["branch"] != "unknown"


@pytest.mark.parametrize("case", TOKEN_PARITY)
def test_tokens_match_fiestaui(case):
    assert [t.to_dict() for t in _parse(case)] == case["tokens"]


@pytest.mark.parametrize("case", CODE_PARITY)
def test_flap_codes_match_fiestaui(case):
    assert tokens_to_codes(_parse(case)) == case["codes"]


@pytest.mark.parametrize("case", TOKEN_DIVERGENT + CODE_DIVERGENT)
def test_known_divergence_still_diverges(case):
    tokens = _parse(case)
    if _base_id(case["id"]) in TOKEN_DIVERGENCES:
        assert [t.to_dict() for t in tokens] != case["tokens"]
    else:
        assert tokens_to_codes(tokens) != case["codes"]


@pytest.mark.parametrize("case", TOKEN_DIVERGENT + CODE_DIVERGENT)
def test_known_divergence_draws_what_the_board_draws_today(case):
    width = 40
    today = text_to_board_array(case["line"], rows=1, cols=width)[0]
    codes = tokens_to_codes(_parse(case))
    assert codes + [0] * (width - len(codes)) == today


@pytest.mark.parametrize("case", [pytest.param(c, id=c["id"]) for c in DATA["grids"]])
def test_grid_matches_fiestaui(case):
    grid = message_to_grid(
        case["message"],
        case["rows"],
        case["cols"],
        device_type=case["deviceType"],
        code62_glyph=case["code62Glyph"],
        extended_markup=case["options"]["extendedMarkup"],
    )
    assert [[t.to_dict() for t in row] for row in grid] == case["grid"]


def test_icon_table_matches_fiestaui():
    ours = {name: {"label": i.label, "color": i.color, "fallback": i.fallback} for name, i in BOARD_ICONS.items()}
    assert ours == DATA["icons"]


def test_span_colour_names_match_fiestaui():
    assert list(SPAN_COLOR_CODES) == DATA["colors"]
