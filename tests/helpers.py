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
