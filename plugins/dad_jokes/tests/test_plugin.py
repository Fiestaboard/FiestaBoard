"""Tests for the dad_jokes plugin."""

import pytest
from unittest.mock import patch, Mock
import json
from pathlib import Path

from plugins.dad_jokes import DadJokesPlugin
from src.plugins.base import PluginResult
from src.plugins.testing import PluginTestCase, create_mock_response


class TestDadJokesPlugin:
    """Tests for the DadJokesPlugin class."""

    @pytest.fixture
    def plugin(self):
        """Create a plugin instance."""
        manifest = {
            "id": "dad_jokes",
            "name": "Dad Jokes",
            "version": "1.0.0",
        }
        return DadJokesPlugin(manifest)

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

        # Validate against manifest variables
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
        # The joke text should appear in the non-empty lines
        content = " ".join(line for line in lines if line)
        assert "scientists" in content
        # Each line should fit within 22 characters
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

    def test_validate_config_valid(self, plugin):
        """Test validate_config accepts valid configuration."""
        errors = plugin.validate_config({"refresh_seconds": 300})
        assert errors == []

    def test_validate_config_minimum_boundary(self, plugin):
        """Test validate_config accepts the minimum refresh interval."""
        errors = plugin.validate_config({"refresh_seconds": 30})
        assert errors == []

    def test_validate_config_maximum_boundary(self, plugin):
        """Test validate_config accepts the maximum refresh interval."""
        errors = plugin.validate_config({"refresh_seconds": 3600})
        assert errors == []

    def test_validate_config_below_minimum(self, plugin):
        """Test validate_config rejects refresh interval below minimum."""
        errors = plugin.validate_config({"refresh_seconds": 10})
        assert len(errors) == 1
        assert "at least 30 seconds" in errors[0]

    def test_validate_config_above_maximum(self, plugin):
        """Test validate_config rejects refresh interval above maximum."""
        errors = plugin.validate_config({"refresh_seconds": 7200})
        assert len(errors) == 1
        assert "must not exceed 3600 seconds" in errors[0]

    def test_validate_config_non_integer(self, plugin):
        """Test validate_config rejects non-integer refresh interval."""
        errors = plugin.validate_config({"refresh_seconds": "fast"})
        assert len(errors) >= 1
        assert "at least 30 seconds" in errors[0]

    def test_validate_config_default_when_missing(self, plugin):
        """Test validate_config uses default when refresh_seconds is missing."""
        errors = plugin.validate_config({})
        assert errors == []

    @patch("plugins.dad_jokes.requests.get")
    def test_fetch_data_caches_result(self, mock_get, plugin):
        """Test fetch_data caches results and reuses them within refresh interval."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "joke": "Cached joke",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        plugin.config = {"refresh_seconds": 300}

        # First call fetches from API
        result1 = plugin.fetch_data()
        assert result1.available is True
        assert result1.data["joke"] == "Cached joke"
        assert mock_get.call_count == 1

        # Second call should use cache
        result2 = plugin.fetch_data()
        assert result2.available is True
        assert result2.data["joke"] == "Cached joke"
        assert mock_get.call_count == 1  # Still 1, no new API call

    @patch("plugins.dad_jokes.requests.get")
    def test_fetch_data_refreshes_after_expiry(self, mock_get, plugin):
        """Test fetch_data fetches new data after cache expires."""
        from datetime import timedelta

        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "abc123",
            "joke": "Fresh joke",
            "status": 200,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        plugin.config = {"refresh_seconds": 60}

        # First call
        plugin.fetch_data()
        assert mock_get.call_count == 1

        # Simulate cache expiry by backdating _last_fetch
        from datetime import datetime
        plugin._last_fetch = datetime.now() - timedelta(seconds=120)

        # Second call should fetch again
        plugin.fetch_data()
        assert mock_get.call_count == 2
