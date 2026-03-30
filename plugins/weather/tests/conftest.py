"""Plugin test fixtures and configuration for weather."""

import pytest
from unittest.mock import patch, MagicMock
import json
from pathlib import Path

from src.plugins.testing import PluginTestCase, create_mock_response


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


@pytest.fixture
def mock_api_response():
    """Fixture to create mock API responses."""
    return create_mock_response


@pytest.fixture
def sample_manifest():
    """Load the plugin manifest for testing."""
    manifest_path = Path(__file__).parent.parent / "manifest.json"
    with open(manifest_path) as f:
        return json.load(f)


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "enabled": True,
        "api_key": "test_api_key_12345",
        "provider": "weatherapi",
        "location": "San Francisco",
    }


@pytest.fixture
def sample_weatherapi_response():
    """Sample WeatherAPI.com JSON response."""
    return {
        "location": {"name": "San Francisco"},
        "current": {
            "temp_f": 72.1,
            "feelslike_f": 68.4,
            "condition": {"text": "Partly Cloudy"},
            "humidity": 65,
            "wind_mph": 12.3,
        },
    }


@pytest.fixture
def sample_openweathermap_response():
    """Sample OpenWeatherMap JSON response."""
    return {
        "name": "San Francisco",
        "main": {
            "temp": 72.1,
            "feels_like": 68.4,
            "humidity": 65,
        },
        "weather": [{"description": "partly cloudy"}],
        "wind": {"speed": 12.3},
    }
