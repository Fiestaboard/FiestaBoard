"""Tests for Board Local API client."""

import json

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

from src.board_client import (
    BoardClient,
    VALID_STRATEGIES,
    is_successful_board_read_response,
    parse_read_message_payload,
    strip_color_markers,
)


class TestStripColorMarkers:
    """Tests for color marker stripping."""
    
    def test_strip_numeric_color_codes(self):
        """Test stripping numeric color codes like {63}."""
        text = "{63}Red text{/}"
        assert strip_color_markers(text) == "Red text"
    
    def test_strip_named_colors(self):
        """Test stripping named colors like {red}."""
        text = "{red}Warning{/red}"
        assert strip_color_markers(text) == "Warning"
    
    def test_strip_multiple_colors(self):
        """Test stripping multiple color markers."""
        text = "{66}Guest WiFi{/}\n{67}SSID: {68}network{/}"
        assert strip_color_markers(text) == "Guest WiFi\nSSID: network"
    
    def test_preserve_non_color_braces(self):
        """Test that non-color braces are preserved."""
        text = "Hello {world} test"
        assert strip_color_markers(text) == "Hello {world} test"
    
    def test_strip_all_color_codes(self):
        """Test all color codes are stripped."""
        for code in range(63, 71):
            text = f"{{{code}}}test{{/}}"
            assert strip_color_markers(text) == "test"
    
    def test_case_insensitive(self):
        """Test that named colors are stripped case-insensitively."""
        assert strip_color_markers("{RED}test{/RED}") == "test"
        assert strip_color_markers("{Red}test{/Red}") == "test"


class TestBoardClientInit:
    """Tests for BoardClient initialization."""
    
    def test_init_with_valid_params(self):
        """Test successful initialization with valid parameters."""
        client = BoardClient(
            api_key="test_key",
            host="192.168.0.11"
        )
        assert client.host == "192.168.0.11"
        assert client.skip_unchanged is True
        assert client.base_url == "http://192.168.0.11:7000/local-api/message"
        assert "X-Vestaboard-Local-Api-Key" in client.headers  # Official board API header
        assert client.headers["X-Vestaboard-Local-Api-Key"] == "test_key"
    
    def test_init_with_hostname(self):
        """Test initialization with hostname instead of IP."""
        client = BoardClient(
            api_key="test_key",
            host="board.local"
        )
        assert client.base_url == "http://board.local:7000/local-api/message"
    
    def test_init_without_api_key_raises(self):
        """Test that missing api_key raises ValueError."""
        with pytest.raises(ValueError, match="api_key is required"):
            BoardClient(api_key="", host="192.168.0.11")
    
    def test_init_without_host_raises(self):
        """Test that missing host raises ValueError."""
        with pytest.raises(ValueError, match="host is required"):
            BoardClient(api_key="test_key", host="")
    
    def test_init_with_skip_unchanged_false(self):
        """Test initialization with skip_unchanged disabled."""
        client = BoardClient(
            api_key="test_key",
            host="192.168.0.11",
            skip_unchanged=False
        )
        assert client.skip_unchanged is False


class TestSendText:
    """Tests for send_text method."""
    
    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return BoardClient(api_key="test_key", host="192.168.0.11")
    
    @patch('src.board_client.requests.post')
    def test_send_text_success(self, mock_post, client):
        """Test successful text send."""
        mock_post.return_value.raise_for_status = Mock()
        
        success, was_sent = client.send_text("Hello World")
        
        assert success is True
        assert was_sent is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["json"] == {"text": "HELLO WORLD"}
    
    @patch('src.board_client.requests.post')
    def test_send_text_cached_skips(self, mock_post, client):
        """Test that sending same text twice skips the second send."""
        mock_post.return_value.raise_for_status = Mock()
        
        # First send
        client.send_text("Hello World")
        
        # Second send (should skip)
        success, was_sent = client.send_text("Hello World")
        
        assert success is True
        assert was_sent is False
        assert mock_post.call_count == 1  # Only called once
    
    @patch('src.board_client.requests.post')
    def test_send_text_force_ignores_cache(self, mock_post, client):
        """Test that force=True ignores cache."""
        mock_post.return_value.raise_for_status = Mock()
        
        # First send
        client.send_text("Hello World")
        
        # Second send with force
        success, was_sent = client.send_text("Hello World", force=True)
        
        assert success is True
        assert was_sent is True
        assert mock_post.call_count == 2
    
    @patch('src.board_client.requests.post')
    def test_send_text_network_error(self, mock_post, client):
        """Test handling of network error."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Network error")
        
        success, was_sent = client.send_text("Hello World")
        
        assert success is False
        assert was_sent is False
    
    @patch('src.board_client.requests.post')
    def test_send_text_strips_color_markers(self, mock_post, client):
        """Test that color markers are stripped from text."""
        mock_post.return_value.raise_for_status = Mock()
        
        success, was_sent = client.send_text("{63}Warning{/}: Check {66}status{/}")
        
        assert success is True
        assert was_sent is True
        call_args = mock_post.call_args
        # Color markers should be stripped
        assert call_args.kwargs["json"]["text"] == "WARNING: CHECK STATUS"


class TestSendCharacters:
    """Tests for send_characters method."""
    
    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return BoardClient(api_key="test_key", host="192.168.0.11")
    
    @pytest.fixture
    def valid_grid(self):
        """Create a valid 6x22 character grid."""
        return [[0] * 22 for _ in range(6)]
    
    @patch('src.board_client.requests.post')
    def test_send_characters_success(self, mock_post, client, valid_grid):
        """Test successful character array send."""
        mock_post.return_value.raise_for_status = Mock()
        
        success, was_sent = client.send_characters(valid_grid)
        
        assert success is True
        assert was_sent is True
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["characters"] == valid_grid
    
    @patch('src.board_client.requests.post')
    def test_send_characters_with_transition(self, mock_post, client, valid_grid):
        """Test sending with transition settings."""
        mock_post.return_value.raise_for_status = Mock()
        
        success, was_sent = client.send_characters(
            valid_grid,
            strategy="column",
            step_interval_ms=500,
            step_size=2
        )
        
        assert success is True
        assert was_sent is True
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert payload["strategy"] == "column"
        assert payload["step_interval_ms"] == 500
        assert payload["step_size"] == 2
    
    @patch('src.board_client.requests.post')
    def test_send_characters_all_strategies(self, mock_post, client, valid_grid):
        """Test all valid transition strategies."""
        mock_post.return_value.raise_for_status = Mock()
        
        for strategy in VALID_STRATEGIES:
            client.clear_cache()  # Clear cache between tests
            success, was_sent = client.send_characters(valid_grid, strategy=strategy)
            assert success is True, f"Strategy {strategy} failed"
    
    def test_send_characters_invalid_strategy(self, client, valid_grid):
        """Test that invalid strategy returns error."""
        success, was_sent = client.send_characters(valid_grid, strategy="invalid")
        
        assert success is False
        assert was_sent is False
    
    def test_send_characters_invalid_rows(self, client):
        """Test that wrong number of rows returns error."""
        invalid_grid = [[0] * 22 for _ in range(5)]  # Only 5 rows
        
        success, was_sent = client.send_characters(invalid_grid)
        
        assert success is False
        assert was_sent is False
    
    def test_send_characters_invalid_columns(self, client):
        """Test that wrong number of columns returns error."""
        invalid_grid = [[0] * 20 for _ in range(6)]  # Only 20 columns
        
        success, was_sent = client.send_characters(invalid_grid)
        
        assert success is False
        assert was_sent is False
    
    @patch('src.board_client.requests.post')
    def test_send_characters_cached_skips(self, mock_post, client, valid_grid):
        """Test that sending same characters twice skips the second send."""
        mock_post.return_value.raise_for_status = Mock()
        
        # First send
        client.send_characters(valid_grid)
        
        # Second send (should skip)
        success, was_sent = client.send_characters(valid_grid)
        
        assert success is True
        assert was_sent is False
        assert mock_post.call_count == 1


class TestParseReadMessagePayload:
    """Vestaboard Cloud vs Local GET body shapes."""

    def test_cloud_current_message_layout_string_note(self):
        grid = [[0] * 15 for _ in range(3)]
        body = {"currentMessage": {"layout": json.dumps(grid), "id": "x"}}
        assert parse_read_message_payload(body) == grid

    def test_cloud_current_message_layout_list_flagship(self):
        grid = [[0] * 22 for _ in range(6)]
        body = {"currentMessage": {"layout": grid, "id": "x"}}
        assert parse_read_message_payload(body) == grid

    def test_legacy_message_key(self):
        grid = [[0] * 22 for _ in range(6)]
        assert parse_read_message_payload({"message": grid}) == grid

    def test_local_raw_list_note(self):
        grid = [[1] * 15 for _ in range(3)]
        assert parse_read_message_payload(grid) == grid

    def test_invalid_dimensions_rejected(self):
        grid = [[0] * 10 for _ in range(4)]
        assert parse_read_message_payload(grid) is None

    def test_is_successful_empty_current_message(self):
        assert is_successful_board_read_response({"currentMessage": None}) is True


class TestReadCurrentMessage:
    """Tests for read_current_message method."""
    
    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return BoardClient(api_key="test_key", host="192.168.0.11")
    
    @patch('src.board_client.requests.get')
    def test_read_current_message_success(self, mock_get, client):
        """Test successful read of current message."""
        expected_chars = [[0] * 22 for _ in range(6)]
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.return_value = expected_chars
        
        result = client.read_current_message()
        
        assert result == expected_chars
    
    @patch('src.board_client.requests.get')
    def test_read_current_message_with_sync_cache(self, mock_get, client):
        """Test that sync_cache updates internal cache."""
        expected_chars = [[1] * 22 for _ in range(6)]
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.return_value = expected_chars
        
        result = client.read_current_message(sync_cache=True)
        
        assert result == expected_chars
        assert client._last_characters == expected_chars
    
    @patch('src.board_client.requests.get')
    def test_read_current_message_network_error(self, mock_get, client):
        """Test handling of network error during read."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")
        
        result = client.read_current_message()
        
        assert result is None

    @patch('src.board_client.requests.get')
    def test_read_current_message_cloud_current_message_shape(self, mock_get):
        """Cloud API returns currentMessage.layout (stringified JSON)."""
        grid = [[0] * 15 for _ in range(3)]
        client = BoardClient(api_key="rw-key", use_cloud=True)
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.return_value = {
            "currentMessage": {"layout": json.dumps(grid), "id": "u"},
        }
        assert client.read_current_message() == grid


class TestCacheManagement:
    """Tests for cache management methods."""
    
    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return BoardClient(api_key="test_key", host="192.168.0.11")
    
    def test_clear_cache(self, client):
        """Test that clear_cache clears internal state."""
        client._last_text = "test"
        client._last_characters = [[0] * 22 for _ in range(6)]
        
        client.clear_cache()
        
        assert client._last_text is None
        assert client._last_characters is None
    
    def test_get_cache_status_empty(self, client):
        """Test cache status when empty."""
        status = client.get_cache_status()
        
        assert status["has_cached_text"] is False
        assert status["has_cached_characters"] is False
        assert status["skip_unchanged_enabled"] is True
    
    @patch('src.board_client.requests.post')
    def test_get_cache_status_with_text(self, mock_post, client):
        """Test cache status after sending text."""
        mock_post.return_value.raise_for_status = Mock()
        client.send_text("Hello World")
        
        status = client.get_cache_status()
        
        assert status["has_cached_text"] is True
        assert status["cached_text_preview"] == "HELLO WORLD"
    
    def test_would_send_with_same_text(self, client):
        """Test would_send returns False for cached text."""
        client._last_text = "HELLO WORLD"
        
        assert client.would_send(text="HELLO WORLD") is False
        assert client.would_send(text="Different") is True
    
    def test_would_send_with_skip_unchanged_disabled(self, client):
        """Test would_send always returns True when caching disabled."""
        client.skip_unchanged = False
        client._last_text = "HELLO WORLD"
        
        assert client.would_send(text="HELLO WORLD") is True


class TestConnectionTest:
    """Tests for test_connection method."""
    
    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return BoardClient(api_key="test_key", host="192.168.0.11")
    
    @patch('src.board_client.requests.get')
    def test_connection_success(self, mock_get, client):
        """Test successful connection test."""
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.return_value = [[0] * 22 for _ in range(6)]
        
        assert client.test_connection() is True
    
    @patch('src.board_client.requests.get')
    def test_connection_failure(self, mock_get, client):
        """Test failed connection test."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")
        
        assert client.test_connection() is False
