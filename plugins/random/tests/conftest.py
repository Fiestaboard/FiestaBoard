"""Test fixtures for the random plugin."""

import pytest
import json
from pathlib import Path

from src.plugins.testing import PluginTestCase, create_mock_response


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    yield


@pytest.fixture
def mock_api_response():
    return create_mock_response


@pytest.fixture
def sample_manifest():
    manifest_path = Path(__file__).parent.parent / "manifest.json"
    with open(manifest_path) as f:
        return json.load(f)


@pytest.fixture
def sample_config():
    return {
        "enabled": True,
        "choices": ["Alpha", "Beta", "Gamma"],
        "refresh_seconds": 60,
    }
