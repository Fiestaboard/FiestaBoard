"""Parity between ``src.markup`` and FiestaUI's message parser.

The fixtures in ``tests/fixtures/markup/`` were produced by running FiestaUI's
real TypeScript ``parseLine`` / ``messageToGrid`` / ``richTokensEqual`` (see
``scripts/markup_fixtures/generate.sh``) on clean ``git archive`` exports of
committed FiestaUI source. Every case is replayed here against the Python
parser, with the same options.

- ``fiestaui_parse_line.json``: base and extended grammar, ``preserveCase``,
  grids and ``richTokensEqual``, from FiestaUI 530231c (PR #324, Task 1).
- ``fiestaui_base_grammar.json``: the base grammar alone, from FiestaUI
  5364439 (PR #323, Task 0). Kept as a pin: Task 1 claims it changes nothing
  without ``extendedMarkup``, and ``test_extended_commit_keeps_the_base_grammar``
  holds it to that.

``DIVERGENCES`` lists cases where Python deliberately follows the board over
FiestaUI. It is empty: every case matches. Its two guard tests stay so a
future divergence has to be declared, with a reason, rather than skipped.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.markup import (
    BOARD_ICON_ALIASES,
    BOARD_ICONS,
    SPAN_COLOR_CODES,
    BoardToken,
    message_to_grid,
    parse_line,
    rich_tokens_equal,
    tokens_to_codes,
)
from src.text_to_board import COLOR_CODES, text_to_board_array

FIXTURES = Path(__file__).parent / "fixtures" / "markup"
BASE = json.loads((FIXTURES / "fiestaui_base_grammar.json").read_text(encoding="utf-8"))
EXT = json.loads((FIXTURES / "fiestaui_parse_line.json").read_text(encoding="utf-8"))

# Case id -> why Python follows the board instead of FiestaUI here.
DIVERGENCES: dict[str, str] = {}


def _parse(case: dict):
    options = case["options"]
    return parse_line(
        case["line"],
        case.get("maxTokens"),
        extended_markup=options.get("extendedMarkup", False),
        preserve_case=options.get("preserveCase", False),
    )


def _params(cases, predicate=lambda c: True, prefix=""):
    return [pytest.param(c, id=prefix + c["id"]) for c in cases if predicate(c)]


ALL_LINES = _params(EXT["lines"]) + _params(BASE["lines"], prefix="base:")
PARITY = [p for p in ALL_LINES if p.values[0]["id"] not in DIVERGENCES]
CODE_PARITY = [p for p in PARITY if "codes" in p.values[0]]
DIVERGENT = [p for p in ALL_LINES if p.values[0]["id"] in DIVERGENCES]


@pytest.mark.parametrize("fixture", [BASE, EXT], ids=["base-grammar", "extended"])
def test_fixture_comes_from_committed_fiestaui_source(fixture):
    source = fixture["header"]["fiestaui"]
    assert re.fullmatch(r"[0-9a-f]{40}", source["commit"])
    assert source["dirty"] is False


def test_extended_fixture_covers_both_modes():
    assert EXT["header"]["modes"] == ["legacy", "ext"]


def test_extended_commit_keeps_the_base_grammar():
    task1 = {c["id"]: c["tokens"] for c in EXT["lines"]}
    changed = [c["id"] for c in BASE["lines"] if c["id"] in task1 and task1[c["id"]] != c["tokens"]]
    assert changed == []


def test_every_divergence_names_a_fixture_case():
    assert set(DIVERGENCES) <= {c["id"] for c in EXT["lines"] + BASE["lines"]}


@pytest.mark.parametrize("case", PARITY)
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


@pytest.mark.parametrize("case", _params(EXT["grids"]) + _params(BASE["grids"], prefix="base:"))
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


def _token(data: dict) -> BoardToken:
    return BoardToken(**data)


@pytest.mark.parametrize("case", _params(EXT["rich_equal"]))
def test_rich_tokens_equal_matches_fiestaui(case):
    assert rich_tokens_equal(_token(case["a"]), _token(case["b"])) is case["equal"]


def test_rich_equal_fixture_includes_pairs_a_flap_cannot_tell_apart():
    assert any(c["flapEqual"] and not c["equal"] for c in EXT["rich_equal"])


def test_tile_names_match_fiestaui():
    ours = {str(code) for code in range(63, 72)} | set(COLOR_CODES)
    assert set(EXT["colors"]) == ours


def test_icon_table_matches_fiestaui():
    ours = {name: {"label": i.label, "color": i.color, "fallback": i.fallback} for name, i in BOARD_ICONS.items()}
    assert ours == EXT["icons"]


def test_icon_aliases_match_fiestaui():
    assert dict(BOARD_ICON_ALIASES) == EXT["icon_aliases"]


def test_span_colours_are_fiestauis_colours_without_the_filled_tile():
    assert list(SPAN_COLOR_CODES) == [c for c in EXT["colors"] if c not in ("71", "filled")]
