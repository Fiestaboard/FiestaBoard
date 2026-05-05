"""Matrix tests for DisplayService._build_silence_indicator_array.

Validates that for every (device_type, position) pair the indicator text:
- Lands on the correct row
- Lands at the correct starting column (left/right/center alignment)
- Does not overlay any other cell (rest of board is SPACE)

Also covers truncation for over-long text and case normalization.
"""
from unittest.mock import patch

import pytest

from src.board_chars import BoardChars
from src.devices import get_dimensions
from src.main import DisplayService


def _patch_silence_feature(feature_dict):
    """Patch Config._get_feature so SILENCE_SCHEDULE_* read from this dict."""
    from src.config import Config
    return patch.object(Config, "_get_feature", classmethod(lambda cls, name: feature_dict))


def _decode_row(row):
    """Decode a board row into a string (letters/digits/space)."""
    rev = {0: " "}
    for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", start=1):
        rev[i] = ch
    for i, ch in enumerate("123456789", start=27):
        rev[i] = ch
    rev[36] = "0"
    return "".join(rev.get(code, "?") for code in row)


def _expected_row_col(position, dims, text_len):
    if position == "top-left":
        return 0, 0
    if position == "top-right":
        return 0, max(0, dims.cols - text_len)
    if position == "bottom-left":
        return dims.rows - 1, 0
    if position == "bottom-right":
        return dims.rows - 1, max(0, dims.cols - text_len)
    # center
    return dims.rows // 2, max(0, (dims.cols - text_len) // 2)


@pytest.mark.parametrize("device_type", ["note", "flagship"])
@pytest.mark.parametrize(
    "position",
    ["center", "top-left", "top-right", "bottom-left", "bottom-right"],
)
def test_indicator_renders_at_correct_position(device_type, position):
    """Each (device, position) pair must produce a clean board with text in the right cell."""
    feature = {
        "indicator_text": "SNOOZING",
        "indicator_position": position,
    }
    dims = get_dimensions(device_type)
    expected_row, expected_col = _expected_row_col(position, dims, len("SNOOZING"))

    svc = DisplayService()
    with _patch_silence_feature(feature):
        board = svc._build_silence_indicator_array(device_type)

    # Dimensions match device
    assert len(board) == dims.rows
    assert all(len(row) == dims.cols for row in board)

    # Target row contains "SNOOZING" at expected_col, rest is space
    target = _decode_row(board[expected_row])
    assert target[expected_col : expected_col + len("SNOOZING")] == "SNOOZING"
    # Outside the indicator span, target row is all spaces
    before = target[:expected_col]
    after = target[expected_col + len("SNOOZING") :]
    assert before.strip() == ""
    assert after.strip() == ""

    # All OTHER rows are entirely SPACE - no overlay
    for r, row in enumerate(board):
        if r == expected_row:
            continue
        assert all(c == BoardChars.SPACE for c in row), f"Row {r} not blank"


@pytest.mark.parametrize("device_type", ["note", "flagship"])
def test_custom_text_renders_uppercase(device_type):
    """Lowercase config text is uppercased by Config; renderer puts uppercase on board."""
    feature = {"indicator_text": "bedtime", "indicator_position": "center"}
    svc = DisplayService()
    with _patch_silence_feature(feature):
        board = svc._build_silence_indicator_array(device_type)

    flat = "\n".join(_decode_row(r) for r in board)
    assert "BEDTIME" in flat
    assert "bedtime" not in flat


def test_text_longer_than_cols_is_truncated():
    """A note (15 cols) with a 20-char message must show only the first 15 chars."""
    feature = {
        "indicator_text": "ABCDEFGHIJKLMNOPQRST",  # 20 chars
        "indicator_position": "top-left",
    }
    svc = DisplayService()
    with _patch_silence_feature(feature):
        board = svc._build_silence_indicator_array("note")

    dims = get_dimensions("note")
    assert _decode_row(board[0]) == "ABCDEFGHIJKLMNO"  # first 15 chars
    assert len(board[0]) == dims.cols


def test_text_equal_to_cols_with_top_right_starts_at_zero():
    """Edge case: if text length == cols, top-right should start at column 0."""
    feature = {
        "indicator_text": "A" * 15,
        "indicator_position": "top-right",
    }
    svc = DisplayService()
    with _patch_silence_feature(feature):
        board = svc._build_silence_indicator_array("note")

    assert _decode_row(board[0]) == "A" * 15


def test_default_text_when_indicator_text_missing():
    """When config has no indicator_text, falls back to SNOOZING."""
    feature = {"indicator_position": "center"}
    svc = DisplayService()
    with _patch_silence_feature(feature):
        board = svc._build_silence_indicator_array("flagship")

    flat = "\n".join(_decode_row(r) for r in board)
    assert "SNOOZING" in flat


def test_unknown_chars_do_not_crash():
    """Characters without a board code leave their cell at SPACE; render must not raise."""
    # `~` is not a supported board character.
    feature = {"indicator_text": "A~B", "indicator_position": "top-left"}
    svc = DisplayService()
    with _patch_silence_feature(feature):
        board = svc._build_silence_indicator_array("note")

    # 'A' at col 0, unknown char leaves col 1 blank, 'B' at col 2
    assert board[0][0] == BoardChars.get_char_code("A")
    assert board[0][1] == BoardChars.SPACE
    assert board[0][2] == BoardChars.get_char_code("B")
