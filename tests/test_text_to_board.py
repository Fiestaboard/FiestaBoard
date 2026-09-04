"""Tests for src/text_to_board.py.

text_to_board contains pure, deterministic conversion logic — character
mapping and board array construction. This addresses issue #505.
"""

import logging

from src.board_chars import BoardChars
from src.text_to_board import (
    COLOR_CODES,
    format_board_array_preview,
    text_to_board_array,
    validate_board_array,
    wrap_message_text,
)

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
        assert board[0][0] == BoardChars.get_char_code("A")

    def test_multiple_letters(self):
        board = text_to_board_array("ABC")
        a_code = BoardChars.get_char_code("A")
        b_code = BoardChars.get_char_code("B")
        c_code = BoardChars.get_char_code("C")
        assert board[0][0] == a_code
        assert board[0][1] == b_code
        assert board[0][2] == c_code

    def test_lowercase_treated_as_uppercase(self):
        board_lower = text_to_board_array("hello")
        board_upper = text_to_board_array("HELLO")
        assert board_lower == board_upper

    def test_newline_starts_new_row(self):
        board = text_to_board_array("A\nB")
        a_code = BoardChars.get_char_code("A")
        b_code = BoardChars.get_char_code("B")
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
        assert board[0][1] == BoardChars.get_char_code("A")

    def test_end_tag_ignored(self):
        # {/red} should be skipped, not consuming a tile
        board = text_to_board_array("{/red}A")
        assert board[0][0] == BoardChars.get_char_code("A")

    def test_use_color_tiles_false_strips_markers(self):
        board = text_to_board_array("{red}A", use_color_tiles=False)
        # Color marker is stripped; A goes to position 0
        assert board[0][0] == BoardChars.get_char_code("A")

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
        board[0][0] = 0  # Min
        board[0][1] = 71  # Max
        assert validate_board_array(board) is True

    def test_empty_board(self):
        assert validate_board_array([]) is False


# ---------------------------------------------------------------------------
# format_board_array_preview
# ---------------------------------------------------------------------------


class TestNoteArrayPresets:
    """Verify text_to_board_array and validate_board_array at note-array preset sizes.

    Covers issue #1173: rendering at any valid note-array dimensions.
    """

    # --- 3×30 (2 notes wide, 1 tall) ---

    def test_3x30_shape(self):
        board = text_to_board_array("HELLO", rows=3, cols=30)
        assert len(board) == 3
        assert all(len(row) == 30 for row in board)

    def test_3x30_text_starts_at_col0(self):
        board = text_to_board_array("A", rows=3, cols=30)
        assert board[0][0] == BoardChars.get_char_code("A")
        # rest of row 0 should be spaces
        assert all(code == BoardChars.SPACE for code in board[0][1:])

    def test_3x30_long_line_truncated_at_30(self):
        board = text_to_board_array("X" * 40, rows=3, cols=30)
        assert len(board[0]) == 30
        assert board[0][29] == BoardChars.get_char_code("X")

    def test_3x30_validate_passes(self):
        board = text_to_board_array("HELLO WORLD", rows=3, cols=30)
        assert validate_board_array(board, rows=3, cols=30)

    # --- 3×60 (4 notes wide, 1 tall) ---

    def test_3x60_shape(self):
        board = text_to_board_array("HELLO", rows=3, cols=60)
        assert len(board) == 3
        assert all(len(row) == 60 for row in board)

    def test_3x60_text_starts_at_col0(self):
        board = text_to_board_array("A", rows=3, cols=60)
        assert board[0][0] == BoardChars.get_char_code("A")

    def test_3x60_long_line_truncated_at_60(self):
        board = text_to_board_array("Y" * 80, rows=3, cols=60)
        assert len(board[0]) == 60
        assert board[0][59] == BoardChars.get_char_code("Y")

    def test_3x60_validate_passes(self):
        board = text_to_board_array("WIDE BOARD TEST", rows=3, cols=60)
        assert validate_board_array(board, rows=3, cols=60)

    # --- 6×15 (1 note wide, 2 tall) ---

    def test_6x15_shape(self):
        board = text_to_board_array("LINE1\nLINE2", rows=6, cols=15)
        assert len(board) == 6
        assert all(len(row) == 15 for row in board)

    def test_6x15_long_line_truncated_at_15(self):
        board = text_to_board_array("A" * 20, rows=6, cols=15)
        assert len(board[0]) == 15

    def test_6x15_validate_passes(self):
        board = text_to_board_array("LINE1\nLINE2", rows=6, cols=15)
        assert validate_board_array(board, rows=6, cols=15)

    # --- 12×15 (1 note wide, 4 tall) ---

    def test_12x15_shape(self):
        text = "\n".join(f"ROW{i}" for i in range(12))
        board = text_to_board_array(text, rows=12, cols=15)
        assert len(board) == 12
        assert all(len(row) == 15 for row in board)

    def test_12x15_all_12_rows_populated(self):
        text = "\n".join(f"R{i}" for i in range(12))
        board = text_to_board_array(text, rows=12, cols=15)
        # Row 11 (index 11) should have 'R' in it
        assert board[11][0] == BoardChars.get_char_code("R")

    def test_12x15_validate_passes(self):
        text = "\n".join(f"ROW{i}" for i in range(12))
        board = text_to_board_array(text, rows=12, cols=15)
        assert validate_board_array(board, rows=12, cols=15)

    # --- 6×30 (2 notes wide, 2 tall) ---

    def test_6x30_shape(self):
        board = text_to_board_array("HELLO WORLD", rows=6, cols=30)
        assert len(board) == 6
        assert all(len(row) == 30 for row in board)

    def test_6x30_validate_passes(self):
        board = text_to_board_array("HELLO WORLD", rows=6, cols=30)
        assert validate_board_array(board, rows=6, cols=30)

    # --- validate_board_array rejects wrong shapes ---

    def test_validate_rejects_wrong_rows(self):
        board = text_to_board_array("A", rows=6, cols=15)
        assert not validate_board_array(board, rows=12, cols=15)

    def test_validate_rejects_wrong_cols(self):
        board = text_to_board_array("A", rows=3, cols=30)
        assert not validate_board_array(board, rows=3, cols=60)

    # --- format_board_array_preview sanity checks ---

    def test_format_preview_3x60_no_crash(self):
        board = text_to_board_array("CENTERED HEADLINE ON WIDE BOARD", rows=3, cols=60)
        preview = format_board_array_preview(board)
        lines = preview.split("\n")
        assert len(lines) == 3
        assert all(len(line) >= 1 for line in lines)

    def test_format_preview_12x15_no_crash(self):
        board = text_to_board_array("TALL\nBOARD", rows=12, cols=15)
        preview = format_board_array_preview(board)
        lines = preview.split("\n")
        assert len(lines) == 12


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
        assert board[0][0] == 1  # A
        assert board[0][1] == 71  # filled
        assert board[0][2] == 2  # B


# ---------------------------------------------------------------------------
# wrap_message_text — free-form message preparation (issue #1793)
# ---------------------------------------------------------------------------


class TestWrapMessageText:
    def test_short_text_unchanged(self):
        assert wrap_message_text("HELLO", rows=3, cols=15) == "HELLO"

    def test_wraps_long_line_at_word_boundaries(self):
        result = wrap_message_text("TACO TUESDAY PARTY TIME", rows=3, cols=15)
        assert result == "TACO TUESDAY\nPARTY TIME"

    def test_explicit_newlines_preserved_and_wrapping_fills_within(self):
        result = wrap_message_text("HI\nTACO TUESDAY PARTY TIME", rows=6, cols=15)
        assert result == "HI\nTACO TUESDAY\nPARTY TIME"

    def test_truncates_wrapped_output_to_rows(self):
        result = wrap_message_text("AAAA BBBB CCCC DDDD EEEE FFFF GGGG HHHH IIII JJJJ", rows=3, cols=15)
        assert result == "AAAA BBBB CCCC\nDDDD EEEE FFFF\nGGGG HHHH IIII"

    def test_truncates_explicit_lines_to_rows(self):
        result = wrap_message_text("A\nB\nC\nD", rows=3, cols=15)
        assert result == "A\nB\nC"


class TestWrapMessageTextMeasuresTilesNotCharacters:
    """Wrapping must count flaps. ``{red}`` writes five characters but
    occupies one tile, and ``{/green}`` occupies none (issue #1793 review)."""

    def test_colour_marker_line_that_fits_stays_on_one_row(self):
        # "{red} TACO TUESDAY" is 18 characters but only 14 tiles, so it
        # fits a 15-wide Note row without wrapping.
        assert wrap_message_text("{red} TACO TUESDAY", rows=3, cols=15) == "{red} TACO TUESDAY"

    def test_closing_tag_costs_no_flaps_so_the_row_is_filled(self):
        # "{green}HI{/green} TACO" is 8 tiles; "TUESDAY" pushes it to 16,
        # so only TUESDAY moves down.
        result = wrap_message_text("{green}HI{/green} TACO TUESDAY", rows=3, cols=15)
        assert result == "{green}HI{/green} TACO\nTUESDAY"

    def test_numeric_marker_counted_as_one_tile(self):
        assert wrap_message_text("{63}{64}{65} HELLO WORLD", rows=3, cols=15) == "{63}{64}{65} HELLO WORLD"


class TestWrapMessageTextLongWords:
    """A word wider than the board is hard-broken across rows instead of
    being silently cut mid-word (issue #1793 review)."""

    def test_long_word_hard_breaks_onto_the_next_row(self):
        result = wrap_message_text("SEE HTTPS://EXAMPLE.COM/VERYLONGPATH", rows=6, cols=22)
        assert result == "SEE\nHTTPS://EXAMPLE.COM/VE\nRYLONGPATH"

    def test_hard_break_never_splits_a_colour_marker(self):
        # 21 tiles of A, then a marker: the marker cannot straddle the break.
        result = wrap_message_text("A" * 21 + "{red}" + "B" * 4, rows=6, cols=22)
        assert result == "A" * 21 + "{red}\n" + "B" * 4

    def test_word_exactly_board_width_is_not_broken(self):
        assert wrap_message_text("A" * 22, rows=6, cols=22) == "A" * 22


class TestWrapMessageTextWhitespaceLines:
    def test_whitespace_only_long_line_keeps_its_row(self):
        # A blank spacer line longer than the board used to yield zero lines
        # and eat a row (issue #1793 review).
        result = wrap_message_text("TOP\n" + " " * 40 + "\nBOTTOM", rows=6, cols=22)
        assert result == "TOP\n\nBOTTOM"


class TestWrapMessageTextBackslashes:
    """``\\n`` unescaping is opt-in, and has an escape hatch when on."""

    def test_backslash_text_is_untouched_by_default(self):
        assert wrap_message_text("C:\\new", rows=6, cols=22) == "C:\\new"

    def test_backslash_text_is_untouched_by_default_mid_sentence(self):
        assert wrap_message_text("GO \\north 5 MILES", rows=6, cols=22) == "GO \\north 5 MILES"

    def test_opt_in_unescape_turns_backslash_n_into_a_line_break(self):
        result = wrap_message_text("HI\\nTHERE", rows=3, cols=15, unescape_newlines=True)
        assert result == "HI\nTHERE"

    def test_doubled_backslash_is_the_escape_hatch_for_a_literal(self):
        # Typing C:\\new asks for the literal text C:\new.
        result = wrap_message_text("C:\\\\new", rows=6, cols=22, unescape_newlines=True)
        assert result == "C:\\new"

    def test_other_backslash_sequences_pass_through_when_unescaping(self):
        result = wrap_message_text("C:\\temp", rows=6, cols=22, unescape_newlines=True)
        assert result == "C:\\temp"


class TestWrapMessageTextOverflowIsLogged:
    """Content that does not fit is dropped, but no longer silently."""

    def test_dropped_rows_are_logged(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.text_to_board"):
            wrap_message_text("A\nB\nC\nD", rows=3, cols=15)
        warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("too long" in msg.lower() for msg in warnings), warnings

    def test_no_warning_when_everything_fits(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.text_to_board"):
            wrap_message_text("A\nB\nC", rows=3, cols=15)
        assert [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING] == []
