# tests/helpers.py

"""Helper assertions and utilities for common test patterns."""

import re


def validate_board_layout(board_state):
    """Validate that a board state has correct layout structure."""
    if not isinstance(board_state, dict):
        raise AssertionError("Board state must be a dictionary")
    if "layout" not in board_state:
        raise AssertionError("Board state must have 'layout' field")
    layout = board_state["layout"]
    if not isinstance(layout, list):
        raise AssertionError("Board layout must be a list")
    for row in layout:
        if not isinstance(row, list):
            raise AssertionError("Board row must be a list")
        if not all(isinstance(cell, int) for cell in row):
            raise AssertionError("Board cell must be an integer")
    return True


def validate_api_response_shape(response, expected_fields):
    """Validate that an API response has the expected fields."""
    if not isinstance(response, dict):
        raise AssertionError("API response must be a dictionary")
    missing = set(expected_fields) - set(response.keys())
    if missing:
        raise AssertionError(f"API response missing fields: {missing}")
    return True


def validate_plugin_output_format(output, expected_keys):
    """Validate that plugin output matches expected format."""
    if not isinstance(output, dict):
        raise AssertionError("Plugin output must be a dictionary")
    for key in expected_keys:
        if key not in output:
            raise AssertionError(f"Plugin output missing key: {key}")
    return True


def validate_template_variables(template, variables):
    """Validate that template has required variables."""
    pattern = r"\{\{(\w+)\}\}"
    found_vars = set(re.findall(pattern, template))
    missing = found_vars - set(variables.keys())
    if missing:
        raise AssertionError(f"Template missing variable values: {missing}")
    return True


# --- Board frame decoding -------------------------------------------------
#
# Board clients receive grids of Vestaboard character codes. Tests that assert
# on what actually reached the hardware read much better against the words on
# the flaps than against arrays of integers.

_BOARD_CHAR_BY_CODE = {0: " "}
for _i, _ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", start=1):
    _BOARD_CHAR_BY_CODE[_i] = _ch
for _i, _ch in enumerate("123456789", start=27):
    _BOARD_CHAR_BY_CODE[_i] = _ch
_BOARD_CHAR_BY_CODE[36] = "0"


def decode_board_rows(board_array):
    """Board character grid -> one string per row, padding preserved.

    Use this when *placement* on the board is the thing under test. Codes
    outside the letters/digits/blank set decode to "?" — deliberately loud, so
    a test never silently asserts against a character it did not mean.
    """
    return ["".join(_BOARD_CHAR_BY_CODE.get(code, "?") for code in row) for row in board_array]


def decode_board_text(board_array):
    """Board character grid -> the text an owner would read off the flaps.

    Blank rows and padding are dropped, so an assertion reads as words rather
    than as a fixed-width grid. Use :func:`decode_board_rows` when the exact
    row/column placement matters.
    """
    return "\n".join(line.strip() for line in decode_board_rows(board_array) if line.strip())
