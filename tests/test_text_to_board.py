"""Tests for src/text_to_board.py.

text_to_board contains pure, deterministic conversion logic — character
mapping and board array construction. This addresses issue #505.
"""

import pytest
from src.text_to_board import (
    text_to_board_array,
    format_board_array_preview,
    validate_board_array,
    COLOR_CODES,
)
from src.board_chars import BoardChars


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_empty_board(rows=6, cols=22):
    return [[BoardChars.SPACE] * cols for _ in range(rows)]


# ---------------------------------------------------------------------------
# text_to_board_array — basic conversion
# ---------------------------------------------------------------------------

class TestTextToBoardArray:
    def test_empty_string_returns_blank_board(self):
        board = text_to_board_array("")
        assert len(board) == 6
        assert all(len(row) == 22 for row in board)
        assert all(code == BoardChars.SPACE for row in board for code in row)

    def test_default_dimensions(self):
        board = text_to_board_array("A")
        assert len(board) == 6
        assert len(board[0]) == 22

    def test_custom_dimensions(self):
        board = text_to_board_array("A", rows=3, cols=15)
        assert len(board) == 3
        assert len(board[0]) == 15

    def test_letter_a_placed_first_column(self):
        board = text_to_board_array("A")
        # 'A' should be code 1
        assert board[0][0] == BoardChars.get_char_code('A')

    def test_multiple_letters(self):
        board = text_to_board_array("ABC")
        a_code = BoardChars.get_char_code('A')
        b_code = BoardChars.get_char_code('B')
        c_code = BoardChars.get_char_code('C')
        assert board[0][0] == a_code
        assert board[0][1] == b_code
        assert board[0][2] == c_code

    def test_lowercase_treated_as_uppercase(self):
        board_lower = text_to_board_array("hello")
        board_upper = text_to_board_array("HELLO")
        assert board_lower == board_upper

    def test_newline_starts_new_row(self):
        board = text_to_board_array("A\nB")
        a_code = BoardChars.get_char_code('A')
        b_code = BoardChars.get_char_code('B')
        assert board[0][0] == a_code
        assert board[1][0] == b_code

    def test_too_many_lines_truncated_to_rows(self):
        text = "\n".join(["X"] * 20)
        board = text_to_board_array(text)
        assert len(board) == 6

    def test_line_longer_than_cols_truncated(self):
        text = "A" * 30
        board = text_to_board_array(text)
        assert len(board[0]) == 22

    def test_unknown_character_becomes_space(self):
        board = text_to_board_array("€")
        assert board[0][0] == BoardChars.SPACE

    def test_space_character(self):
        board = text_to_board_array(" ")
        assert board[0][0] == BoardChars.SPACE


# ---------------------------------------------------------------------------
# text_to_board_array — color markers
# ---------------------------------------------------------------------------

class TestColorMarkers:
    def test_named_color_red(self):
        board = text_to_board_array("{red}")
        assert board[0][0] == COLOR_CODES["red"]

    def test_named_color_blue(self):
        board = text_to_board_array("{blue}")
        assert board[0][0] == COLOR_CODES["blue"]

    def test_numeric_color_code_63(self):
        board = text_to_board_array("{63}")
        assert board[0][0] == 63  # red

    def test_numeric_color_code_66(self):
        board = text_to_board_array("{66}")
        assert board[0][0] == 66  # green

    def test_color_takes_one_tile(self):
        # {red}A should place red at col 0, A at col 1
        board = text_to_board_array("{red}A")
        assert board[0][0] == COLOR_CODES["red"]
        assert board[0][1] == BoardChars.get_char_code('A')

    def test_end_tag_ignored(self):
        # {/red} should be skipped, not consuming a tile
        board = text_to_board_array("{/red}A")
        assert board[0][0] == BoardChars.get_char_code('A')

    def test_use_color_tiles_false_strips_markers(self):
        board = text_to_board_array("{red}A", use_color_tiles=False)
        # Color marker is stripped; A goes to position 0
        assert board[0][0] == BoardChars.get_char_code('A')

    def test_double_brace_color_marker_not_processed(self):
        # The formatter uses {{red}} syntax but text_to_board uses {red}
        # Double braces should NOT match the single-brace pattern
        board = text_to_board_array("{{red}}")
        # The { is unknown, r, e, d are letters, etc.
        # Just verify it doesn't crash and is a valid board
        assert len(board) == 6

    def test_all_named_colors(self):
        for name, code in COLOR_CODES.items():
            board = text_to_board_array(f"{{{name}}}")
            assert board[0][0] == code, f"Color {name} should map to code {code}"

    def test_case_insensitive_color_names(self):
        board_lower = text_to_board_array("{red}")
        board_upper = text_to_board_array("{RED}")
        assert board_lower == board_upper

    def test_purple_alias_for_violet(self):
        board_purple = text_to_board_array("{purple}")
        board_violet = text_to_board_array("{violet}")
        assert board_purple == board_violet


# ---------------------------------------------------------------------------
# validate_board_array
# ---------------------------------------------------------------------------

class TestValidateBoardArray:
    def test_valid_default_board(self):
        board = text_to_board_array("Hello World")
        assert validate_board_array(board) is True

    def test_valid_custom_size(self):
        board = text_to_board_array("Hi", rows=3, cols=15)
        assert validate_board_array(board, rows=3, cols=15) is True

    def test_wrong_row_count(self):
        board = [[0] * 22 for _ in range(3)]
        assert validate_board_array(board, rows=6, cols=22) is False

    def test_wrong_col_count(self):
        board = [[0] * 10 for _ in range(6)]
        assert validate_board_array(board, rows=6, cols=22) is False

    def test_not_a_list(self):
        assert validate_board_array("not a list") is False

    def test_invalid_char_code_negative(self):
        board = [[0] * 22 for _ in range(6)]
        board[0][0] = -1
        assert validate_board_array(board) is False

    def test_invalid_char_code_too_high(self):
        board = [[0] * 22 for _ in range(6)]
        board[2][5] = 72  # Max valid is 71
        assert validate_board_array(board) is False

    def test_valid_boundary_codes(self):
        board = [[0] * 22 for _ in range(6)]
        board[0][0] = 0   # Min
        board[0][1] = 71  # Max
        assert validate_board_array(board) is True

    def test_empty_board(self):
        assert validate_board_array([]) is False


# ---------------------------------------------------------------------------
# format_board_array_preview
# ---------------------------------------------------------------------------

class TestFormatBoardArrayPreview:
    def test_returns_string(self):
        board = text_to_board_array("TEST")
        result = format_board_array_preview(board)
        assert isinstance(result, str)

    def test_six_lines_output(self):
        board = text_to_board_array("HELLO")
        result = format_board_array_preview(board)
        lines = result.split("\n")
        assert len(lines) == 6

    def test_letter_a_shows_in_preview(self):
        board = text_to_board_array("A")
        result = format_board_array_preview(board)
        assert "A" in result

    def test_color_tiles_shown_as_bracketed_codes(self):
        board = text_to_board_array("{red}")
        result = format_board_array_preview(board)
        assert "[RED]" in result

    def test_blue_tile_in_preview(self):
        board = text_to_board_array("{blue}")
        result = format_board_array_preview(board)
        assert "[BLU]" in result

    def test_empty_board_shows_spaces(self):
        board = text_to_board_array("")
        result = format_board_array_preview(board)
        # Should be all spaces
        for line in result.split("\n"):
            assert line.strip() == "" or all(c == " " for c in line)

    def test_numbers_in_preview(self):
        board = text_to_board_array("123")
        result = format_board_array_preview(board)
        assert "1" in result
        assert "2" in result
        assert "3" in result


# ---------------------------------------------------------------------------
# COLOR_CODES constants
# ---------------------------------------------------------------------------

class TestColorCodes:
    def test_all_colors_defined(self):
        expected = {"red", "orange", "yellow", "green", "blue", "violet", "purple", "white", "black", "filled"}
        assert expected == set(COLOR_CODES.keys())

    def test_codes_in_valid_range(self):
        for name, code in COLOR_CODES.items():
            assert 63 <= code <= 71, f"{name} code {code} out of range"

    def test_purple_same_as_violet(self):
        assert COLOR_CODES["purple"] == COLOR_CODES["violet"]

    def test_red_is_63(self):
        assert COLOR_CODES["red"] == 63

    def test_black_is_70(self):
        assert COLOR_CODES["black"] == 70

    def test_filled_is_71(self):
        assert COLOR_CODES["filled"] == 71


class TestNoteFillSpaceEndToEnd:
    """End-to-end tests for FILL_SPACE_REPEAT on NOTE devices through the full pipeline."""

    def test_fill_space_repeat_blue_note_board_array(self):
        """FILL_SPACE_REPEAT:BLUE rendered text should produce correct board array for NOTE."""
        # This is the rendered output from TemplateEngine for "LUNCH:{{FILL_SPACE_REPEAT:BLUE}}"
        # on a NOTE device: 6 text chars + 9 blue tiles = 15 tiles
        rendered = "LUNCH:{67}{67}{67}{67}{67}{67}{67}{67}{67}\n               \n               "
        board = text_to_board_array(rendered, rows=3, cols=15)
        
        assert len(board) == 3
        assert len(board[0]) == 15
        
        # First row: L=12, U=21, N=14, C=3, H=8, :=50, then 9 blue tiles (67)
        assert board[0] == [12, 21, 14, 3, 8, 50, 67, 67, 67, 67, 67, 67, 67, 67, 67]
        
        # Blue tile count should be exactly 9
        blue_count = sum(1 for code in board[0] if code == 67)
        assert blue_count == 9

    def test_fill_space_repeat_fills_all_note_columns(self):
        """All 15 columns on NOTE should be filled (no empty last tile)."""
        # Entire line of green
        rendered = "{66}" * 15 + "\n" + " " * 15 + "\n" + " " * 15
        board = text_to_board_array(rendered, rows=3, cols=15)
        
        # All 15 positions should be green (66)
        assert all(code == 66 for code in board[0])

    def test_filled_color_code_71_in_board_array(self):
        """Color code 71 (filled) should be recognized in text_to_board_array."""
        rendered = "A{71}B"
        board = text_to_board_array(rendered, rows=1, cols=3)
        assert board[0][0] == 1   # A
        assert board[0][1] == 71  # filled
        assert board[0][2] == 2   # B
