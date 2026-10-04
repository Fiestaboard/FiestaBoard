"""Parity between ``src.markup`` and FiestaUI's message parser.

The fixtures in ``tests/fixtures/markup/`` were produced by running FiestaUI's
real TypeScript ``parseLine`` / ``messageToGrid`` (see
``scripts/markup_fixtures/generate.sh``). Every case is replayed here against
the Python parser, with the same options.

There are two fixture files, because no single FiestaUI commit has both
halves yet:

- ``fiestaui_base_grammar.json``: the base (flag-off) grammar, from FiestaUI
  commit 5364439 (PR #323, the board-parity fix). Every ``legacy/`` case
  comes from here, and all of them match.
- ``fiestaui_parse_line.json``: extended markup and ``preserveCase``, from
  the FiestaUI LED working tree that predates PR #323. Every ``ext/`` case and
  the ``legacy/case-preserve-*`` cases come from here.

The extended fixtures still carry the base-grammar bugs PR #323 fixed, and
still accept ``71`` as a span colour, so those ``ext/`` cases stay listed in
``DIVERGENCES``; in every one the Python side draws what the physical board
draws. Two guard tests keep the list honest: an entry that stops diverging
fails (regenerate, then delete the entry), and so does an entry whose Python
output stops matching today's board.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.markup import BOARD_ICONS, SPAN_COLOR_CODES, message_to_grid, parse_line, tokens_to_codes
from src.text_to_board import COLOR_CODES, text_to_board_array

FIXTURES = Path(__file__).parent / "fixtures" / "markup"
BASE = json.loads((FIXTURES / "fiestaui_base_grammar.json").read_text(encoding="utf-8"))
EXT = json.loads((FIXTURES / "fiestaui_parse_line.json").read_text(encoding="utf-8"))

# Each case from the newest FiestaUI source that can produce it.
_BASE_IDS = {c["id"] for c in BASE["lines"]}
LINES = BASE["lines"] + [c for c in EXT["lines"] if c["id"] not in _BASE_IDS]
GRIDS = BASE["grids"] + [c for c in EXT["grids"] if c["id"].startswith("ext/")]

# Fixed upstream in PR #323 (c6b34f4, 5364439) but still shown by the extended
# fixtures, which predate it: the tokens or the flap codes differ. Delete these
# when the extended fixtures are regenerated from a FiestaUI commit that has
# both (its Task 1).
_PREDATES_PR323 = "extended fixtures predate FiestaUI PR #323, which fixed this: "
DIVERGENCES = {
    "ext/alias-filled": _PREDATES_PR323 + "the board draws {filled} as tile 71",
    "ext/alias-filled-upper": _PREDATES_PR323 + "the board draws {FILLED} as tile 71",
    "ext/end-unknown-name": _PREDATES_PR323 + "the board only drops {/} and {/<colour>}",
    "ext/end-numeric": _PREDATES_PR323 + "the board draws {/63} literally",
    "ext/end-with-colon": _PREDATES_PR323 + "the board draws {/white:A} literally",
    "ext/block-half-head-bg": _PREDATES_PR323 + "the board draws {/red:A} literally",
    "ext/plain-emoji": _PREDATES_PR323 + "an emoji is one cell, not two UTF-16 halves",
    "ext/code62-heart-suit": _PREDATES_PR323 + "a typed heart projects to code 62",
    "ext/code62-heart-emoji": _PREDATES_PR323 + "a typed ❤ is normalised to ♥, code 62",
    "ext/span-filled-numeric": _PREDATES_PR323 + "71 is the filled tile, not a span colour: {71:A} is literal",
}


def _parse(case: dict):
    options = case["options"]
    return parse_line(
        case["line"],
        case.get("maxTokens"),
        extended_markup=options.get("extendedMarkup", False),
        preserve_case=options.get("preserveCase", False),
    )


def _cases(predicate):
    return [pytest.param(c, id=c["id"]) for c in LINES if predicate(c)]


TOKEN_PARITY = _cases(lambda c: c["id"] not in DIVERGENCES)
CODE_PARITY = _cases(lambda c: "codes" in c and c["id"] not in DIVERGENCES)
DIVERGENT = _cases(lambda c: c["id"] in DIVERGENCES)


@pytest.mark.parametrize("fixture", [BASE, EXT], ids=["base-grammar", "extended"])
def test_fixture_records_its_fiestaui_source(fixture):
    source = fixture["header"]["fiestaui"]
    assert re.fullmatch(r"[0-9a-f]{40}", source["commit"])
    assert source["branch"] != "unknown"


def test_base_grammar_fixture_is_from_a_committed_fiestaui_source():
    assert BASE["header"]["fiestaui"]["dirty"] is False


def test_every_divergence_names_a_fixture_case():
    assert set(DIVERGENCES) <= {c["id"] for c in LINES}


@pytest.mark.parametrize("case", TOKEN_PARITY)
def test_tokens_match_fiestaui(case):
    assert [t.to_dict() for t in _parse(case)] == case["tokens"]


@pytest.mark.parametrize("case", CODE_PARITY)
def test_flap_codes_match_fiestaui(case):
    assert tokens_to_codes(_parse(case)) == case["codes"]


@pytest.mark.parametrize("case", DIVERGENT)
def test_known_divergence_still_diverges(case):
    tokens = _parse(case)
    assert ([t.to_dict() for t in tokens], tokens_to_codes(tokens)) != (case["tokens"], case["codes"])


@pytest.mark.parametrize("case", DIVERGENT)
def test_known_divergence_draws_what_the_board_draws_today(case):
    width = 40
    today = text_to_board_array(case["line"], rows=1, cols=width)[0]
    codes = tokens_to_codes(_parse(case))
    assert codes + [0] * (width - len(codes)) == today


@pytest.mark.parametrize("case", [pytest.param(c, id=c["id"]) for c in GRIDS])
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


def test_tile_names_match_fiestaui_base_grammar():
    ours = {str(code) for code in range(63, 72)} | set(COLOR_CODES)
    assert set(BASE["colors"]) == ours


def test_icon_table_matches_fiestaui():
    ours = {name: {"label": i.label, "color": i.color, "fallback": i.fallback} for name, i in BOARD_ICONS.items()}
    assert ours == EXT["icons"]


def test_span_colour_names_are_fiestauis_colours_without_the_filled_tile():
    # The extended fixtures' colour table predates PR #323: it still has "71"
    # (and, like PR #323, no "filled"). A span head never names the filled tile.
    assert list(SPAN_COLOR_CODES) == [c for c in EXT["colors"] if c not in ("71", "filled")]
