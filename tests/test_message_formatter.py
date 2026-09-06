"""Tests for src/formatters/message_formatter.py.

MessageFormatter's line-splitting logic is pure and highly testable
(no I/O, no hardware dependencies). This addresses issue #505.
"""

import pytest

from src.formatters.message_formatter import MessageFormatter
from src.text_to_board import count_tiles


@pytest.fixture
def fmt():
    return MessageFormatter()


class TestSplitIntoLines:
    def test_short_text_unchanged(self, fmt):
        lines = fmt.split_into_lines("Hello")
        assert lines == ["Hello"]

    def test_splits_long_line_on_spaces(self, fmt):
        text = "The quick brown fox jumped over the lazy dog today"
        lines = fmt.split_into_lines(text)
        for line in lines:
            assert len(line) <= fmt.MAX_COLS

    def test_respects_max_lines(self, fmt):
        # Create a text with many newlines
        text = "\n".join(["line"] * 20)
        lines = fmt.split_into_lines(text, max_lines=3)
        assert len(lines) <= 3

    def test_preserves_existing_newlines(self, fmt):
        text = "Line one\nLine two"
        lines = fmt.split_into_lines(text)
        assert len(lines) == 2
        assert lines[0] == "Line one"

    def test_empty_string(self, fmt):
        lines = fmt.split_into_lines("")
        assert lines == [""]


class TestSplitIntoLinesTileWidth:
    """Width is measured in flaps, not characters (issue #1793 review)."""

    def test_colour_marker_costs_one_tile_not_five_characters(self):
        fmt = MessageFormatter(rows=3, cols=15)
        # 18 characters, 14 tiles — fits one Note row.
        assert fmt.split_into_lines("{red} TACO TUESDAY") == ["{red} TACO TUESDAY"]

    def test_closing_tag_costs_no_tiles(self):
        fmt = MessageFormatter(rows=3, cols=15)
        assert fmt.split_into_lines("{green}HI{/green} TACO TUESDAY") == [
            "{green}HI{/green} TACO",
            "TUESDAY",
        ]


class TestSplitIntoLinesLongWords:
    """A word wider than the board is broken across rows, not cut off."""

    def test_over_long_word_is_hard_broken(self):
        fmt = MessageFormatter(rows=6, cols=22)
        assert fmt.split_into_lines("SEE HTTPS://EXAMPLE.COM/VERYLONGPATH") == [
            "SEE",
            "HTTPS://EXAMPLE.COM/VE",
            "RYLONGPATH",
        ]

    def test_hard_break_does_not_split_a_colour_marker(self):
        fmt = MessageFormatter(rows=6, cols=22)
        assert fmt.split_into_lines("A" * 21 + "{red}" + "B" * 4) == ["A" * 21 + "{red}", "B" * 4]

    def test_every_returned_line_fits_the_board(self):
        fmt = MessageFormatter(rows=6, cols=22)
        for line in fmt.split_into_lines("X" * 100):
            assert count_tiles(line) <= 22


class TestSplitIntoLinesWhitespaceOnly:
    def test_long_whitespace_line_still_yields_a_row(self):
        fmt = MessageFormatter(rows=6, cols=22)
        # Used to return [] and silently eat the row (issue #1793 review).
        assert fmt.split_into_lines("TOP\n" + " " * 40 + "\nBOTTOM") == ["TOP", "", "BOTTOM"]


class TestMessageFormatterDimensions:
    def test_init_flagship_defaults(self):
        """Default constructor produces 6×22 instance."""
        fmt = MessageFormatter()
        assert fmt._rows == 6
        assert fmt._cols == 22

    def test_init_note_dimensions(self):
        """Note-sized constructor produces 3×15 instance."""
        fmt = MessageFormatter(rows=3, cols=15)
        assert fmt._rows == 3
        assert fmt._cols == 15

    def test_class_constants_unchanged(self):
        """Class-level MAX_ROWS/MAX_COLS must remain 6/22 for backward compat."""
        assert MessageFormatter.MAX_ROWS == 6
        assert MessageFormatter.MAX_COLS == 22

    def test_split_into_lines_note_cols_wraps_at_15(self):
        """Note-sized formatter wraps each line at 15 characters."""
        fmt = MessageFormatter(rows=3, cols=15)
        long_text = "This is a long sentence that needs wrapping"
        lines = fmt.split_into_lines(long_text)
        for line in lines:
            assert len(line) <= 15

    def test_split_into_lines_note_array_wide(self):
        """Wide note-array formatter wraps each line at 30 characters."""
        fmt = MessageFormatter(rows=3, cols=30)
        long_text = "This is a sentence that is longer than thirty characters total"
        lines = fmt.split_into_lines(long_text)
        for line in lines:
            assert len(line) <= 30
