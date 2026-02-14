"""Plugin test fixtures and configuration for WSDOT."""

import json
from pathlib import Path

import pytest

from src.plugins.testing import create_mock_response


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


def load_wsdot_manifest():
    """Load wsdot manifest.json."""
    manifest_path = Path(__file__).parent.parent / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def manifest():
    """Plugin manifest for WSDOT."""
    return load_wsdot_manifest()


@pytest.fixture
def plugin(manifest):
    """WSDOT plugin instance with manifest."""
    from plugins.wsdot import WsdotPlugin
    return WsdotPlugin(manifest)


@pytest.fixture
def mock_api_response():
    """Fixture to create mock API responses."""
    return create_mock_response
