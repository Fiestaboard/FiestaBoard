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
