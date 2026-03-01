"""Tests for the dad_jokes plugin."""

import pytest
from unittest.mock import patch, Mock
import json
from pathlib import Path
from datetime import datetime, timedelta

from plugins.dad_jokes import DadJokesPlugin
from src.plugins.base import PluginResult
from src.plugins.testing import PluginTestCase, create_mock_response


MANIFEST_WITH_REFRESH = {
    "id": "dad_jokes",
    "name": "Dad Jokes",
    "version": "1.0.0",
    "settings_schema": {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "default": False},
            "refresh_seconds": {
                "type": "integer",
                "default": 300,
                "minimum": 30,
                "maximum": 3600,
            },
        },
    },
}


class TestDadJokesPlugin:
    """Tests for the DadJokesPlugin class."""

    @pytest.fixture
    def plugin(self):
        """Create a plugin instance with full manifest (including settings_schema)."""
        return DadJokesPlugin(MANIFEST_WITH_REFRESH)

    @pytest.fixture
    def plugin_bare(self):
        """Create a plugin instance with minimal manifest (no settings_schema)."""
        return DadJokesPlugin({
            "id": "dad_jokes",
            "name": "Dad Jokes",
            "version": "1.0.0",
        })

    def test_plugin_id(self, plugin):
        """Test plugin ID matches the directory name."""
        assert plugin.plugin_id == "dad_jokes"

    @patch("plugins.dad_jokes.requests.get")
    def test_fetch_data_success(self, mock_get, plugin):
        """Test successful data fetch returns joke."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "joke": "Why did the scarecrow win an award? Because he was outstanding in his field!",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data is not None
        assert "joke" in result.data
        assert result.data["joke"] == "Why did the scarecrow win an award? Because he was outstanding in his field!"

    @patch("plugins.dad_jokes.requests.get")
    def test_fetch_data_returns_all_variables(self, mock_get, plugin):
        """Test fetch_data returns all expected variables from manifest."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "xyz789",
            "joke": "I'm reading a book about anti-gravity. It's impossible to put down!",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = plugin.fetch_data()

        assert result.available is True
        assert "joke" in result.data

        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        declared_vars = manifest["variables"]["simple"]
        for var in declared_vars:
            assert var in result.data, f"Variable '{var}' declared in manifest but not in data"

    @patch("plugins.dad_jokes.requests.get")
    def test_fetch_data_api_error(self, mock_get, plugin):
        """Test handling of API errors."""
        mock_get.side_effect = Exception("Network error")

        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None
        assert "Network error" in result.error

    @patch("plugins.dad_jokes.requests.get")
    def test_fetch_data_http_error(self, mock_get, plugin):
        """Test handling of HTTP errors."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")
        mock_get.return_value = mock_response

        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    @patch("plugins.dad_jokes.requests.get")
    def test_fetch_data_empty_joke(self, mock_get, plugin):
        """Test handling of empty joke response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "joke": "",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = plugin.fetch_data()

        assert result.available is False
        assert "No joke returned" in result.error

    @patch("plugins.dad_jokes.requests.get")
    def test_fetch_data_missing_joke_field(self, mock_get, plugin):
        """Test handling of response missing joke field."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = plugin.fetch_data()

        assert result.available is False

    @patch("plugins.dad_jokes.requests.get")
    def test_fetch_data_sets_correct_headers(self, mock_get, plugin):
        """Test that API requests include correct headers."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "joke": "Test joke",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        plugin.fetch_data()

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        headers = call_kwargs.kwargs.get("headers", {}) or call_kwargs[1].get("headers", {})
        assert headers.get("Accept") == "application/json"
        assert "User-Agent" in headers

    @patch("plugins.dad_jokes.requests.get")
    def test_get_formatted_display(self, mock_get, plugin):
        """Test formatted display returns lines with proper content."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "joke": "Why don't scientists trust atoms? Because they make up everything!",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6
        assert all(isinstance(line, str) for line in lines)
        content = " ".join(line for line in lines if line)
        assert "scientists" in content
        for line in lines:
            assert len(line) <= 22

    @patch("plugins.dad_jokes.requests.get")
    def test_get_formatted_display_returns_none_on_error(self, mock_get, plugin):
        """Test formatted display returns None on API error."""
        mock_get.side_effect = Exception("Network error")

        lines = plugin.get_formatted_display()

        assert lines is None

    @patch("plugins.dad_jokes.requests.get")
    def test_fetch_data_timeout(self, mock_get, plugin):
        """Test handling of request timeout."""
        mock_get.side_effect = Exception("Connection timed out")

        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    def test_plugin_initialization(self, plugin):
        """Test plugin initializes correctly."""
        assert plugin.plugin_id == "dad_jokes"
        assert plugin.manifest is not None

    # --- Base class refresh_seconds validation (via _validate_refresh_seconds) ---

    def test_validate_refresh_valid(self, plugin):
        """Test base validation accepts valid refresh_seconds."""
        errors = plugin._validate_refresh_seconds({"refresh_seconds": 300})
        assert errors == []

    def test_validate_refresh_minimum_boundary(self, plugin):
        """Test base validation accepts the minimum refresh interval."""
        errors = plugin._validate_refresh_seconds({"refresh_seconds": 30})
        assert errors == []

    def test_validate_refresh_maximum_boundary(self, plugin):
        """Test base validation accepts the maximum refresh interval."""
        errors = plugin._validate_refresh_seconds({"refresh_seconds": 3600})
        assert errors == []

    def test_validate_refresh_below_minimum(self, plugin):
        """Test base validation rejects refresh interval below minimum."""
        errors = plugin._validate_refresh_seconds({"refresh_seconds": 10})
        assert len(errors) == 1
        assert "at least 30 seconds" in errors[0]

    def test_validate_refresh_above_maximum(self, plugin):
        """Test base validation rejects refresh interval above maximum."""
        errors = plugin._validate_refresh_seconds({"refresh_seconds": 7200})
        assert len(errors) == 1
        assert "must not exceed 3600 seconds" in errors[0]

    def test_validate_refresh_non_integer(self, plugin):
        """Test base validation rejects non-integer refresh interval."""
        errors = plugin._validate_refresh_seconds({"refresh_seconds": "fast"})
        assert len(errors) == 1
        assert "must be a number" in errors[0]

    def test_validate_refresh_missing_key(self, plugin):
        """Test base validation passes when refresh_seconds key is absent."""
        errors = plugin._validate_refresh_seconds({})
        assert errors == []

    def test_validate_refresh_no_schema(self, plugin_bare):
        """Test base validation passes when manifest has no refresh_seconds schema."""
        errors = plugin_bare._validate_refresh_seconds({"refresh_seconds": 5})
        assert errors == []

    # --- Base class caching via get_data() ---

    @patch("plugins.dad_jokes.requests.get")
    def test_get_data_caches_result(self, mock_get, plugin):
        """Test get_data caches results and reuses them within refresh interval."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "joke": "Cached joke",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        plugin._config = {"refresh_seconds": 300}

        result1 = plugin.get_data()
        assert result1.available is True
        assert result1.data["joke"] == "Cached joke"
        assert mock_get.call_count == 1

        result2 = plugin.get_data()
        assert result2.available is True
        assert result2.data["joke"] == "Cached joke"
        assert mock_get.call_count == 1

    @patch("plugins.dad_jokes.requests.get")
    def test_get_data_refreshes_after_expiry(self, mock_get, plugin):
        """Test get_data fetches new data after cache expires."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "joke": "Fresh joke",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        plugin._config = {"refresh_seconds": 60}

        plugin.get_data()
        assert mock_get.call_count == 1

        plugin._last_fetch_time = datetime.now() - timedelta(seconds=120)

        plugin.get_data()
        assert mock_get.call_count == 2

    @patch("plugins.dad_jokes.requests.get")
    def test_get_data_no_cache_without_schema(self, mock_get, plugin_bare):
        """Test get_data always fetches fresh when manifest has no refresh_seconds."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "joke": "Always fresh",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        plugin_bare.get_data()
        plugin_bare.get_data()
        assert mock_get.call_count == 2

    @patch("plugins.dad_jokes.requests.get")
    def test_clear_cache_forces_refetch(self, mock_get, plugin):
        """Test clear_cache forces a fresh fetch on next get_data call."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "joke": "Joke",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        plugin._config = {"refresh_seconds": 300}

        plugin.get_data()
        assert mock_get.call_count == 1

        plugin.clear_cache()

        plugin.get_data()
        assert mock_get.call_count == 2

    def test_refresh_seconds_property(self, plugin):
        """Test refresh_seconds returns configured value or manifest default."""
        assert plugin.refresh_seconds == 300

        plugin._config = {"refresh_seconds": 120}
        assert plugin.refresh_seconds == 120

    def test_refresh_seconds_none_without_schema(self, plugin_bare):
        """Test refresh_seconds returns None without manifest schema."""
        assert plugin_bare.refresh_seconds is None


Plugin = DadJokesPlugin
