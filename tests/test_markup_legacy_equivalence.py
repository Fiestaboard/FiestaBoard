"""With extended markup off, nothing about today's rendering changes.

Property-style checks over seeded random input (hypothesis is not a project
dependency). The alphabet is weighted toward the characters that make the
grammar interesting: braces, colons, slashes, colour names, digits, case,
and the Unicode letters Python's case-insensitive regex treats specially.
"""

from __future__ import annotations

import random

import pytest

from src.markup import parse_line, tokens_to_codes
from src.text_to_board import count_tiles, take_tiles, text_to_board_array, wrap_message_text

PIECES = [
    "{",
    "}",
    "{",
    "}",
    ":",
    "/",
    "#",
    " ",
    " ",
    "\t",
    "a",
    "Z",
    "7",
    "°",
    "♥",
    "❤",
    "😀",
    "ı",
    "İ",
    "ſ",
    "K",
    "red",
    "RED",
    "Red",
    "purple",
    "filled",
    "black",
    "blacK",
    "vıolet",
    "white",
    "63",
    "71",
    "72",
    "icon",
    "sun",
    "bus",
    "ff8800",
    "black/white",
    "{/}",
    "{/red}",
    "{red}",
    "{63}",
    "{red:",
    "{icon:sun}",
]


def _random_lines(seed: int, count: int, *, allow_colon: bool = True) -> list[str]:
    rng = random.Random(seed)
    pieces = PIECES if allow_colon else [p for p in PIECES if ":" not in p]
    return ["".join(rng.choice(pieces) for _ in range(rng.randint(0, 14))) for _ in range(count)]


LINES = _random_lines(20261003, 3000)
MARKER_FREE = _random_lines(1793, 3000, allow_colon=False)


def test_legacy_parse_projects_to_todays_board_row():
    width = 80
    mismatches = []
    for line in LINES:
        codes = tokens_to_codes(parse_line(line, width))
        if (
            codes + [0] * (width - len(codes))
            != text_to_board_array(line, rows=1, cols=width, extended_markup=False)[0]
        ):
            mismatches.append(line)
    assert mismatches == []


def test_legacy_parse_honours_the_column_cap_like_todays_board():
    mismatches = []
    for line in LINES:
        for cols in (0, 1, 3, 15):
            codes = tokens_to_codes(parse_line(line, cols))
            if (
                codes + [0] * (cols - len(codes))
                != text_to_board_array(line, rows=1, cols=cols, extended_markup=False)[0]
            ):
                mismatches.append((line, cols))
    assert mismatches == []


@pytest.mark.parametrize("cols", [3, 15, 22])
def test_marker_free_text_board_rows_identical_with_extended_on(cols):
    changed = [
        line
        for line in MARKER_FREE
        if text_to_board_array(line, rows=1, cols=cols, extended_markup=True)
        != text_to_board_array(line, rows=1, cols=cols, extended_markup=False)
    ]
    assert changed == []


def test_marker_free_text_tile_count_identical_with_extended_on():
    changed = [
        line
        for line in MARKER_FREE
        if count_tiles(line, extended_markup=True) != count_tiles(line, extended_markup=False)
    ]
    assert changed == []


def test_marker_free_text_tile_split_identical_with_extended_on():
    changed = [
        (line, limit)
        for line in MARKER_FREE
        for limit in (0, 1, 4)
        if take_tiles(line, limit, extended_markup=True) != take_tiles(line, limit, extended_markup=False)
    ]
    assert changed == []


@pytest.mark.parametrize("cols", [3, 5, 15])
def test_marker_free_text_wrap_identical_with_extended_on(cols):
    changed = [
        line
        for line in MARKER_FREE
        if wrap_message_text(line, rows=8, cols=cols, extended_markup=True)
        != wrap_message_text(line, rows=8, cols=cols, extended_markup=False)
    ]
    assert changed == []
