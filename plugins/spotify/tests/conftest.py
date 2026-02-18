"""Plugin test fixtures and configuration for Spotify."""

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


@pytest.fixture
def sample_manifest():
    """Return sample manifest for testing."""
    return {
        "id": "spotify",
        "name": "Spotify Now Playing",
        "version": "1.0.0",
        "settings_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "refresh_token": {"type": "string"},
                "refresh_seconds": {"type": "integer", "default": 30},
                "show_album": {"type": "boolean", "default": False},
            },
            "required": ["client_id", "client_secret", "refresh_token"],
        },
    }


@pytest.fixture
def sample_config():
    """Return sample configuration for testing."""
    return {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "refresh_token": "test_refresh_token",
        "refresh_seconds": 30,
        "show_album": False,
        "enabled": True,
    }


@pytest.fixture
def token_response():
    """Return a sample Spotify token refresh response."""
    return {
        "access_token": "test_access_token_12345",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "user-read-currently-playing",
    }


@pytest.fixture
def nowplaying_response():
    """Return a sample Spotify currently playing response."""
    return {
        "is_playing": True,
        "currently_playing_type": "track",
        "item": {
            "name": "Test Song",
            "artists": [
                {"name": "Test Artist", "id": "artist123"}
            ],
            "album": {
                "name": "Test Album",
                "images": [
                    {"url": "https://example.com/large.jpg", "height": 640, "width": 640},
                    {"url": "https://example.com/medium.jpg", "height": 300, "width": 300},
                    {"url": "https://example.com/small.jpg", "height": 64, "width": 64},
                ],
            },
            "external_urls": {
                "spotify": "https://open.spotify.com/track/test123"
            },
        },
    }


@pytest.fixture
def paused_response():
    """Return a sample Spotify response when playback is paused."""
    return {
        "is_playing": False,
        "currently_playing_type": "track",
        "item": {
            "name": "Paused Song",
            "artists": [
                {"name": "Paused Artist", "id": "artist456"}
            ],
            "album": {
                "name": "Paused Album",
                "images": [
                    {"url": "https://example.com/artwork.jpg", "height": 640, "width": 640},
                ],
            },
            "external_urls": {
                "spotify": "https://open.spotify.com/track/paused123"
            },
        },
    }


@pytest.fixture
def no_item_response():
    """Return a sample Spotify response with no item (e.g. ad playing)."""
    return {
        "is_playing": True,
        "currently_playing_type": "track",
        "item": None,
    }
