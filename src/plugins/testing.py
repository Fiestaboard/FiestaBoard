"""Plugin testing utilities and base classes.

This module provides shared testing infrastructure for FiestaBoard plugins,
including base test classes, mock helpers, and coverage configuration.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from .base import PluginBase, PluginResult

# Coverage configuration constants
MINIMUM_COVERAGE_PERCENT = 80
COVERAGE_FAIL_UNDER = 80


class PluginTestCase:
    """Base test class for plugin tests.

    Provides common fixtures and utilities for testing plugins.

    Usage:
        class TestMyPlugin(PluginTestCase):
            plugin_class = MyPlugin

            def test_fetch_data_success(self, plugin):
                result = plugin.fetch_data()
                assert result.available
    """

    plugin_class: type[PluginBase] | None = None

    @pytest.fixture
    def plugin(self) -> PluginBase:
        """Create a plugin instance for testing."""
        if self.plugin_class is None:
            pytest.skip("plugin_class not defined")
        return self.plugin_class()

    @pytest.fixture
    def plugin_with_config(self) -> PluginBase:
        """Create a plugin instance with configuration."""
        if self.plugin_class is None:
            pytest.skip("plugin_class not defined")
        return self.plugin_class()

    @pytest.fixture
    def mock_config(self):
        """Fixture to provide mock configuration values."""
        return {}

    def assert_plugin_result_success(self, result: PluginResult):
        """Assert that a plugin result indicates success."""
        assert result.available, f"Plugin not available: {result.error}"
        assert result.error is None
        assert result.data is not None

    def assert_plugin_result_failure(self, result: PluginResult, expected_error: str | None = None):
        """Assert that a plugin result indicates failure."""
        assert not result.available
        if expected_error:
            assert expected_error in (result.error or "")

    def assert_variables_present(self, result: PluginResult, variables: list):
        """Assert that expected variables are present in result data."""
        assert result.data is not None
        for var in variables:
            assert var in result.data, f"Variable '{var}' not found in result data"


class MockResponse:
    """Mock HTTP response for testing API calls."""

    def __init__(self, json_data: Any = None, status_code: int = 200, text: str = "", raise_for_status: bool = True):
        self._json_data = json_data
        self.status_code = status_code
        self.text = text or json.dumps(json_data) if json_data else ""
        self._raise_for_status = raise_for_status

    def json(self):
        """Return JSON data."""
        return self._json_data

    def raise_for_status(self):
        """Raise exception if status indicates error."""
        if not self._raise_for_status or self.status_code >= 400:
            from requests.exceptions import HTTPError

            raise HTTPError(f"HTTP {self.status_code}")


def create_mock_response(data: Any = None, status_code: int = 200, raise_error: bool = False) -> MockResponse:
    """Create a mock HTTP response.

    Args:
        data: JSON response data
        status_code: HTTP status code
        raise_error: Whether to raise on raise_for_status()

    Returns:
        MockResponse instance
    """
    return MockResponse(json_data=data, status_code=status_code, raise_for_status=not raise_error)


def mock_requests_get(url_responses: dict[str, Any]):
    """Create a mock for requests.get that returns different responses by URL.

    Args:
        url_responses: Dict mapping URL patterns to response data

    Returns:
        Mock function suitable for patching requests.get

    Usage:
        with patch('requests.get', mock_requests_get({
            'api.example.com/data': {'key': 'value'},
            'api.example.com/error': None,  # Will return 500
        })):
            # test code
    """

    def mock_get(url, **kwargs):
        for pattern, response_data in url_responses.items():
            if pattern in url:
                if response_data is None:
                    return create_mock_response(status_code=500, raise_error=True)
                return create_mock_response(data=response_data)
        return create_mock_response(data={}, status_code=404, raise_error=True)

    return mock_get


def load_plugin_manifest(plugin_dir: Path) -> dict[str, Any]:
    """Load and return a plugin's manifest.json.

    Args:
        plugin_dir: Path to the plugin directory

    Returns:
        Parsed manifest dictionary
    """
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with manifest_path.open() as f:
        return json.load(f)


def get_plugin_test_dir(plugin_id: str) -> Path:
    """Get the tests directory for a plugin.

    Args:
        plugin_id: Plugin identifier

    Returns:
        Path to plugin's tests directory
    """
    plugins_dir = Path(__file__).parent.parent.parent / "plugins"
    return plugins_dir / plugin_id / "tests"


def validate_plugin_coverage(plugin_id: str, coverage_percent: float) -> bool:
    """Validate that a plugin meets coverage requirements.

    Args:
        plugin_id: Plugin identifier
        coverage_percent: Actual coverage percentage

    Returns:
        True if coverage meets minimum threshold
    """
    return coverage_percent >= MINIMUM_COVERAGE_PERCENT


class PluginTestFixtures:
    """Collection of reusable test fixtures for plugins."""

    @staticmethod
    def weather_api_response():
        """Sample weather API response."""
        return {
            "current": {"temp_f": 72, "condition": {"text": "Sunny"}, "humidity": 45, "wind_mph": 5},
            "location": {"name": "San Francisco", "region": "California"},
        }

    @staticmethod
    def stock_api_response():
        """Sample stock API response."""
        return {"symbol": "GOOG", "price": 150.25, "change": 1.18, "changePercent": 0.79}

    @staticmethod
    def transit_api_response():
        """Sample transit API response."""
        return {"predictions": [{"minutes": 5, "line": "N"}, {"minutes": 12, "line": "N"}]}

    @staticmethod
    def empty_plugin_result():
        """Empty but available plugin result."""
        return PluginResult(available=True, data={})

    @staticmethod
    def error_plugin_result(error: str = "Test error"):
        """Error plugin result."""
        return PluginResult(available=False, error=error)


# Shared conftest content for plugin tests
PLUGIN_CONFTEST_TEMPLATE = '''"""Plugin test fixtures and configuration."""

import pytest
from unittest.mock import patch, MagicMock

from src.plugins.testing import PluginTestCase, create_mock_response


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


@pytest.fixture
def mock_api_response():
    """Fixture to create mock API responses."""
    return create_mock_response
'''


def create_plugin_conftest(plugin_dir: Path) -> str:
    """Generate conftest.py content for a plugin.

    Args:
        plugin_dir: Path to the plugin directory

    Returns:
        conftest.py content string
    """
    return PLUGIN_CONFTEST_TEMPLATE
