"""Unit tests for Spotify Now Playing plugin."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from plugins.spotify import SpotifyPlugin, SPOTIFY_TOKEN_URL, SPOTIFY_NOW_PLAYING_URL


class TestSpotifyPlugin:
    """Test Spotify plugin."""

    def test_plugin_id(self, sample_manifest):
        """Test plugin ID matches manifest."""
        plugin = SpotifyPlugin(sample_manifest)
        assert plugin.plugin_id == "spotify"

    def test_init(self, sample_manifest):
        """Test plugin initialization."""
        plugin = SpotifyPlugin(sample_manifest)
        assert plugin._cache is None
        assert plugin._cache_time is None
        assert plugin._access_token is None
        assert plugin._token_expiry is None

    def test_validate_config_valid(self, sample_manifest, sample_config):
        """Test config validation with valid config."""
        plugin = SpotifyPlugin(sample_manifest)
        errors = plugin.validate_config(sample_config)
        assert errors == []

    def test_validate_config_missing_client_id(self, sample_manifest):
        """Test config validation with missing client ID."""
        plugin = SpotifyPlugin(sample_manifest)
        config = {
            "client_secret": "secret",
            "refresh_token": "token",
            "refresh_seconds": 30,
        }
        errors = plugin.validate_config(config)
        assert any("client id" in e.lower() for e in errors)

    def test_validate_config_missing_client_secret(self, sample_manifest):
        """Test config validation with missing client secret."""
        plugin = SpotifyPlugin(sample_manifest)
        config = {
            "client_id": "id",
            "refresh_token": "token",
            "refresh_seconds": 30,
        }
        errors = plugin.validate_config(config)
        assert any("client secret" in e.lower() for e in errors)

    def test_validate_config_missing_refresh_token(self, sample_manifest):
        """Test config validation with missing refresh token."""
        plugin = SpotifyPlugin(sample_manifest)
        config = {
            "client_id": "id",
            "client_secret": "secret",
            "refresh_seconds": 30,
        }
        errors = plugin.validate_config(config)
        assert any("refresh token" in e.lower() for e in errors)

    def test_validate_config_invalid_refresh(self, sample_manifest):
        """Test config validation with invalid refresh interval."""
        plugin = SpotifyPlugin(sample_manifest)
        config = {
            "client_id": "id",
            "client_secret": "secret",
            "refresh_token": "token",
            "refresh_seconds": 5,
        }
        errors = plugin.validate_config(config)
        assert any("refresh" in e.lower() or "10 seconds" in e.lower() for e in errors)

    @patch.dict(
        "os.environ",
        {
            "SPOTIFY_CLIENT_ID": "envid",
            "SPOTIFY_CLIENT_SECRET": "envsecret",
            "SPOTIFY_REFRESH_TOKEN": "envtoken",
        },
    )
    def test_validate_config_from_env(self, sample_manifest):
        """Test config validation uses environment variables as fallback."""
        plugin = SpotifyPlugin(sample_manifest)
        config = {}  # Empty config, should use env vars
        errors = plugin.validate_config(config)
        assert errors == []

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_nowplaying(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
        nowplaying_response,
    ):
        """Test fetch_data with currently playing track."""
        # Mock token refresh
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        # Mock currently playing
        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = nowplaying_response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["title"] == "Test Song"
        assert result.data["artist"] == "Test Artist"
        assert result.data["album"] == "Test Album"
        assert result.data["is_playing"] is True
        assert result.data["status"] == "NOW PLAYING"
        assert "large" in result.data["artwork_url"]
        assert "Test Song by Test Artist" in result.data["formatted"]

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_paused(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
        paused_response,
    ):
        """Test fetch_data with paused playback."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = paused_response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["title"] == "Paused Song"
        assert result.data["artist"] == "Paused Artist"
        assert result.data["is_playing"] is False
        assert result.data["status"] == "PAUSED"

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_nothing_playing(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
    ):
        """Test fetch_data when nothing is playing (204 response)."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        mock_playing_response = Mock()
        mock_playing_response.status_code = 204
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["title"] == ""
        assert result.data["is_playing"] is False
        assert "Nothing playing" in result.data["status"]

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_no_item(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
        no_item_response,
    ):
        """Test fetch_data when item is None."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = no_item_response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["title"] == ""
        assert "Nothing playing" in result.data["status"]

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_auth_failed(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
    ):
        """Test fetch_data handles 401 unauthorized."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        mock_playing_response = Mock()
        mock_playing_response.status_code = 401
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result = plugin.fetch_data()

        assert result.available is False
        assert "authentication" in result.error.lower()

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_forbidden(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
    ):
        """Test fetch_data handles 403 forbidden."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        mock_playing_response = Mock()
        mock_playing_response.status_code = 403
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result = plugin.fetch_data()

        assert result.available is False
        assert "forbidden" in result.error.lower()

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_network_error(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
    ):
        """Test fetch_data handles network errors."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result = plugin.fetch_data()

        assert result.available is False
        assert "Network error" in result.error

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_timeout(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
    ):
        """Test fetch_data handles timeout."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        import requests

        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result = plugin.fetch_data()

        assert result.available is False
        assert "timed out" in result.error.lower()

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_uses_cache(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
        nowplaying_response,
    ):
        """Test fetch_data uses cache within refresh interval."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = nowplaying_response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        # First call
        result1 = plugin.fetch_data()
        assert result1.available is True
        assert mock_get.call_count == 1

        # Second call (should use cache)
        result2 = plugin.fetch_data()
        assert result2.available is True
        assert mock_get.call_count == 1  # No additional API call
        assert result2.data["title"] == result1.data["title"]

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_cache_expires(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
        nowplaying_response,
    ):
        """Test fetch_data refreshes cache after interval."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = nowplaying_response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        # First call
        plugin.fetch_data()
        assert mock_get.call_count == 1

        # Simulate cache expiration
        plugin._cache_time = datetime.now() - timedelta(seconds=60)

        # Second call (should refresh)
        plugin.fetch_data()
        assert mock_get.call_count == 2

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_fallback_to_cache_on_error(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
        nowplaying_response,
    ):
        """Test fetch_data falls back to cache on network error."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        # First successful call
        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = nowplaying_response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result1 = plugin.fetch_data()
        assert result1.available is True

        # Simulate cache expiration
        plugin._cache_time = datetime.now() - timedelta(seconds=60)

        # Second call fails
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

        result2 = plugin.fetch_data()

        # Should return cached data
        assert result2.available is True
        assert result2.data["title"] == "Test Song"

    def test_fetch_data_missing_client_id(self, sample_manifest):
        """Test fetch_data returns error when client ID missing."""
        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = {"client_secret": "secret", "refresh_token": "token"}

        result = plugin.fetch_data()

        assert result.available is False
        assert "client id" in result.error.lower()

    def test_fetch_data_missing_client_secret(self, sample_manifest):
        """Test fetch_data returns error when client secret missing."""
        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = {"client_id": "id", "refresh_token": "token"}

        result = plugin.fetch_data()

        assert result.available is False
        assert "client secret" in result.error.lower()

    def test_fetch_data_missing_refresh_token(self, sample_manifest):
        """Test fetch_data returns error when refresh token missing."""
        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = {"client_id": "id", "client_secret": "secret"}

        result = plugin.fetch_data()

        assert result.available is False
        assert "refresh token" in result.error.lower()

    @patch("plugins.spotify.requests.post")
    def test_token_refresh_failure(
        self,
        mock_post,
        sample_manifest,
        sample_config,
    ):
        """Test fetch_data handles token refresh failure."""
        mock_token_response = Mock()
        mock_token_response.status_code = 400
        mock_post.return_value = mock_token_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result = plugin.fetch_data()

        assert result.available is False
        assert "access token" in result.error.lower()

    @patch("plugins.spotify.requests.post")
    def test_token_refresh_reuses_valid_token(
        self,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
    ):
        """Test that a valid cached token is reused."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        # Set a valid token
        plugin._access_token = "existing_token"
        plugin._token_expiry = datetime.now() + timedelta(hours=1)

        token = plugin._refresh_access_token()

        assert token == "existing_token"
        mock_post.assert_not_called()

    @patch("plugins.spotify.requests.post")
    def test_token_refresh_network_error(
        self,
        mock_post,
        sample_manifest,
        sample_config,
    ):
        """Test token refresh handles network errors."""
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError("Network error")

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        token = plugin._refresh_access_token()

        assert token is None

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_no_artists(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
    ):
        """Test fetch_data handles track with no artists."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        response = {
            "is_playing": True,
            "currently_playing_type": "track",
            "item": {
                "name": "Test Song",
                "artists": [],
                "album": {"name": "Test Album", "images": []},
                "external_urls": {},
            },
        }

        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["artist"] == "Unknown"

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_get_formatted_display(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
        nowplaying_response,
    ):
        """Test get_formatted_display returns 6 lines."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = nowplaying_response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6
        assert "NOW PLAYING" in lines[0]
        assert "Test Song" in lines[2]
        assert "Test Artist" in lines[3]

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_get_formatted_display_with_album(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        token_response,
        nowplaying_response,
    ):
        """Test get_formatted_display includes album when configured."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = nowplaying_response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "refresh_token": "test_refresh_token",
            "show_album": True,
        }

        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6
        assert any("Test Album" in line for line in lines)

    def test_cleanup(self, sample_manifest):
        """Test cleanup clears all state."""
        plugin = SpotifyPlugin(sample_manifest)
        plugin._cache = {"title": "cached"}
        plugin._cache_time = datetime.now()
        plugin._access_token = "token"
        plugin._token_expiry = datetime.now()

        plugin.cleanup()

        assert plugin._cache is None
        assert plugin._cache_time is None
        assert plugin._access_token is None
        assert plugin._token_expiry is None

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_api_request_params(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
        nowplaying_response,
    ):
        """Test correct API parameters are sent."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = nowplaying_response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        plugin.fetch_data()

        # Check token refresh was called
        mock_post.assert_called_once()
        post_args = mock_post.call_args
        assert post_args[0][0] == SPOTIFY_TOKEN_URL

        # Check currently playing was called with auth header
        mock_get.assert_called_once()
        get_args = mock_get.call_args
        assert get_args[0][0] == SPOTIFY_NOW_PLAYING_URL
        assert "Bearer" in get_args[1]["headers"]["Authorization"]

    @patch("plugins.spotify.requests.post")
    @patch("plugins.spotify.requests.get")
    def test_fetch_data_401_with_cache(
        self,
        mock_get,
        mock_post,
        sample_manifest,
        sample_config,
        token_response,
        nowplaying_response,
    ):
        """Test fetch_data returns cache on 401 when cache exists."""
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = token_response
        mock_post.return_value = mock_token_response

        # First successful call to populate cache
        mock_playing_response = Mock()
        mock_playing_response.status_code = 200
        mock_playing_response.json.return_value = nowplaying_response
        mock_get.return_value = mock_playing_response

        plugin = SpotifyPlugin(sample_manifest)
        plugin.config = sample_config

        result1 = plugin.fetch_data()
        assert result1.available is True

        # Expire cache and token
        plugin._cache_time = datetime.now() - timedelta(seconds=60)
        plugin._access_token = None
        plugin._token_expiry = None

        # Second call returns 401
        mock_playing_401 = Mock()
        mock_playing_401.status_code = 401
        mock_get.return_value = mock_playing_401

        result2 = plugin.fetch_data()

        # Should return cached data
        assert result2.available is True
        assert result2.data["title"] == "Test Song"
