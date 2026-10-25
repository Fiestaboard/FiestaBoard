"""Substituted variable values are data, not markup (plan D19, rule 1).

A value may carry exactly the base grammar: tile tokens ``{63}``…``{71}``,
the tile names ``{red}``…``{black}`` and ``{filled}``, and base end tags
``{/}`` / ``{/<colour name>}`` — art plugins (e.g. pride) inject tiles through
data. Every other brace becomes ``(`` / ``)``, so data can never open a span,
a block or an icon.
"""

from __future__ import annotations

import pytest

from src.markup import RESERVED_PLUGIN_IDS, neutralize_data
from src.text_to_board import text_to_board_array

PRIDE_ROW = "{red}{red}{red}{orange}{orange}{orange}{yellow}{yellow}{green}{green}{blue}{blue}{violet}{violet}"


def test_pride_flag_row_passes_through_unchanged():
    assert neutralize_data(PRIDE_ROW) == PRIDE_ROW


def test_pride_flag_row_draws_its_tiles_on_a_flap():
    row = text_to_board_array(neutralize_data(PRIDE_ROW), rows=1, cols=14)[0]
    assert row == [63, 63, 63, 64, 64, 64, 65, 65, 66, 66, 67, 67, 68, 68]


def test_tile_then_text_then_end_tag_passes_through():
    assert neutralize_data("{red}HOT{/red}") == "{red}HOT{/red}"


def test_tile_then_text_then_end_tag_draws_as_today():
    assert text_to_board_array(neutralize_data("{red}HOT{/red}"), rows=1, cols=4) == [[63, 8, 15, 20]]


@pytest.mark.parametrize("tile", ["{63}", "{71}", "{RED}", "{purple}", "{filled}", "{FILLED}", "{/}", "{/filled}"])
def test_base_grammar_tiles_and_end_tags_are_kept(tile):
    assert neutralize_data(f"a{tile}b") == f"a{tile}b"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("{/63}", "(/63)"),
        ("{/foo}", "(/foo)"),
        ("{red:HOT}", "(red:HOT)"),
        ("{black/white:OPEN}", "(black/white:OPEN)"),
        ("{icon:sun}", "(icon:sun)"),
        ("{sun}", "(sun)"),
        ("a{b", "a(b"),
        ("}", ")"),
        ("{{demo.temp}}", "((demo.temp))"),
        ("{62}", "(62)"),
    ],
)
def test_every_other_brace_becomes_a_parenthesis(value, expected):
    assert neutralize_data(value) == expected


def test_a_neutralised_span_draws_as_literal_text_with_extended_markup():
    drawn = text_to_board_array(neutralize_data("{red:HI}"), rows=1, cols=8, extended_markup=True)[0]
    assert drawn == [41, 18, 5, 4, 50, 8, 9, 42]


def test_reserved_plugin_ids_are_colour_names_tile_codes_and_icon():
    names = {"red", "orange", "yellow", "green", "blue", "violet", "purple", "white", "black", "filled"}
    assert names | {str(code) for code in range(63, 72)} | {"icon"} == RESERVED_PLUGIN_IDS
