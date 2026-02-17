"""Plugin test fixtures and configuration."""

import pytest
from unittest.mock import patch, MagicMock

from src.plugins.testing import PluginTestCase, create_mock_response


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "intensity": "light",
        "drop_color": "white",
        "enabled": True,
    }


@pytest.fixture
def sample_manifest():
    """Sample manifest for plugin initialization."""
    return {
        "id": "white_noise",
        "name": "White Noise",
        "version": "1.0.0",
        "description": "Gentle rain / white noise mode",
        "author": "FiestaBoard Team",
        "settings_schema": {},
        "variables": {
            "simple": ["white_noise", "intensity", "drop_color", "active_drops"]
        },
    }
