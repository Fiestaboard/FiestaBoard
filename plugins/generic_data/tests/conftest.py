"""Plugin test fixtures and configuration for generic_data."""

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
        "url": "https://api.example.com/data",
        "format": "json",
        "method": "GET",
        "headers": [],
        "mappings": [
            {"variable": "temperature", "path": "current.temp_f", "default": "N/A"},
            {"variable": "condition", "path": "current.condition.text", "default": "Unknown"},
        ],
        "refresh_seconds": 300,
    }


@pytest.fixture
def sample_json_response():
    """Sample JSON API response for testing."""
    return {
        "current": {
            "temp_f": 72,
            "condition": {"text": "Sunny"},
            "humidity": 45,
        },
        "location": {
            "name": "San Francisco",
            "region": "California",
        },
        "forecast": [
            {"day": "Monday", "high": 75, "low": 60},
            {"day": "Tuesday", "high": 68, "low": 55},
        ],
    }


@pytest.fixture
def sample_xml_response():
    """Sample XML response string for testing."""
    return (
        "<weather>"
        "<current>"
        "<temp>72</temp>"
        "<condition>Sunny</condition>"
        "</current>"
        "<location>"
        "<name>San Francisco</name>"
        "</location>"
        "</weather>"
    )
