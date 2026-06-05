# tests/__init__.py

"""Test helpers package for FiestaBoard."""

from .conftest import mock_api_client, mock_board_client, sample_page, sample_plugin, sample_schedule
from .factories import create_test_board_state, create_test_page, create_test_plugin, create_test_schedule
from .helpers import (
    validate_api_response_shape,
    validate_board_layout,
    validate_plugin_output_format,
    validate_template_variables,
)

__all__ = [
    "create_test_board_state",
    # factories
    "create_test_page",
    "create_test_plugin",
    "create_test_schedule",
    "mock_api_client",
    # conftest fixtures
    "mock_board_client",
    "sample_page",
    "sample_plugin",
    "sample_schedule",
    "validate_api_response_shape",
    # helpers
    "validate_board_layout",
    "validate_plugin_output_format",
    "validate_template_variables",
]
