"""Plugin test fixtures and configuration.

This is a template conftest.py for new plugins.
Copy this file to your plugin's tests/ directory.
"""

import pytest

from src.plugins.testing import create_mock_response


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


@pytest.fixture
def mock_api_response():
    """Fixture to create mock API responses."""
    return create_mock_response
