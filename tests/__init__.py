# tests/__init__.py

"""Test helpers package for FiestaBoard."""

from .conftest import (
    mock_board_client,
    mock_api_client,
    sample_page,
    sample_schedule,
    sample_plugin
)
from .factories import (
    create_test_page,
    create_test_schedule,
    create_test_plugin,
    create_test_board_state
)
from .helpers import (
    validate_board_layout,
    validate_api_response_shape,
    validate_plugin_output_format,
    validate_template_variables
)

__all__ = [
    # conftest fixtures
    "mock_board_client",
    "mock_api_client",
    "sample_page",
    "sample_schedule",
    "sample_plugin",
    # factories
    "create_test_page",
    "create_test_schedule",
    "create_test_plugin",
    "create_test_board_state",
    # helpers
    "validate_board_layout",
    "validate_api_response_shape",
    "validate_plugin_output_format",
    "validate_template_variables",
]
