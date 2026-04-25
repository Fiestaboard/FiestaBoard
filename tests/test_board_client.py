"""Tests for Board Local API client."""

import json

import pytest
from unittest.mock import Mock, patch
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


class TestValidGridDimensions:
    """Tests for _valid_grid_dimensions helper."""

    def test_returns_expected_dimension_set(self):
        from src.board_client import _valid_grid_dimensions

        dims = _valid_grid_dimensions()
        assert isinstance(dims, set)
        assert (6, 22) in dims
        assert (3, 15) in dims


class TestIsValidCharacterGrid:
    """Tests for _is_valid_character_grid validation."""

    def test_valid_flagship_grid(self):
        from src.board_client import _is_valid_character_grid

        grid = [[0] * 22 for _ in range(6)]
        assert _is_valid_character_grid(grid) is True

    def test_valid_note_grid(self):
        from src.board_client import _is_valid_character_grid

        grid = [[0] * 15 for _ in range(3)]
        assert _is_valid_character_grid(grid) is True

    def test_first_element_not_list(self):
        """Line 80: first row is not a list -> return False."""
        from src.board_client import _is_valid_character_grid

        assert _is_valid_character_grid(["not_a_list"]) is False

    def test_wrong_dimensions(self):
        """Line 87: valid structure but dimensions don't match any device."""
        from src.board_client import _is_valid_character_grid

        grid = [[0] * 10 for _ in range(4)]
        assert _is_valid_character_grid(grid) is False

    def test_ragged_row(self):
        """Line 89: a row with different column count."""
        from src.board_client import _is_valid_character_grid

        grid = [[0] * 22 for _ in range(6)]
        grid[3] = [0] * 21  # one short
        assert _is_valid_character_grid(grid) is False

    def test_non_int_value_in_row(self):
        """Line 89: non-int element in a row."""
        from src.board_client import _is_valid_character_grid

        grid = [[0] * 22 for _ in range(6)]
        grid[0][5] = "x"
        assert _is_valid_character_grid(grid) is False

    def test_empty_list(self):
        from src.board_client import _is_valid_character_grid

        assert _is_valid_character_grid([]) is False

    def test_not_a_list(self):
        from src.board_client import _is_valid_character_grid

        assert _is_valid_character_grid("string") is False


class TestParseReadMessagePayloadEdgeCases:
    """Additional edge cases for parse_read_message_payload."""

    def test_non_list_non_dict_returns_none(self):
        """Line 102: data is not list or dict."""
        assert parse_read_message_payload(42) is None
        assert parse_read_message_payload("hello") is None

    def test_layout_none_returns_none(self):
        """Line 110: layout is None."""
        body = {"currentMessage": {"layout": None}}
        assert parse_read_message_payload(body) is None

    def test_layout_empty_string_returns_none(self):
        """Line 110: layout is empty string."""
        body = {"currentMessage": {"layout": ""}}
        assert parse_read_message_payload(body) is None

    def test_layout_invalid_json_string_returns_none(self):
        """Lines 114-115: layout is invalid JSON string."""
        body = {"currentMessage": {"layout": "{invalid json"}}
        assert parse_read_message_payload(body) is None

    def test_layout_valid_json_but_invalid_grid(self):
        """Line 116->118: layout parses but is not a valid grid."""
        body = {"currentMessage": {"layout": json.dumps([[1, 2, 3]])}}
        assert parse_read_message_payload(body) is None

    def test_layout_is_non_list_parsed_value(self):
        """Line 116->118: layout string parses to a non-list type."""
        body = {"currentMessage": {"layout": json.dumps({"key": "val"})}}
        assert parse_read_message_payload(body) is None

    def test_message_key_invalid_grid(self):
        """message key present but value is not a valid grid."""
        assert parse_read_message_payload({"message": [[0] * 5]}) is None

    def test_message_key_not_list(self):
        """message key present but value is not a list."""
        assert parse_read_message_payload({"message": "text"}) is None

    def test_no_known_keys_returns_none(self):
        """Line 118: dict with no recognized keys falls through to return None."""
        assert parse_read_message_payload({"unknown": "data"}) is None


class TestSendTextHTTPError:
    """Test send_text HTTP error with response body."""

    @pytest.fixture
    def client(self):
        return BoardClient(api_key="test_key", host="192.168.0.11")

    @patch('src.board_client.requests.post')
    def test_send_text_http_error_with_response_body(self, mock_post, client):
        """Line 245: log response text on HTTP error."""
        mock_response = Mock()
        mock_response.text = "Bad Request"
        mock_response.status_code = 400
        exc = requests.exceptions.HTTPError(response=mock_response)
        exc.response = mock_response
        mock_post.side_effect = exc

        success, was_sent = client.send_text("Test")
        assert success is False
        assert was_sent is False


class TestSendCharactersEdgeCases:
    """Additional edge cases for send_characters."""

    @pytest.fixture
    def client(self):
        return BoardClient(api_key="test_key", host="192.168.0.11")

    @pytest.fixture
    def cloud_client(self):
        return BoardClient(api_key="rw-key", use_cloud=True)

    @pytest.fixture
    def valid_grid(self):
        return [[0] * 22 for _ in range(6)]

    @patch('src.board_client.requests.post')
    def test_send_characters_cloud_api_format(self, mock_post, cloud_client, valid_grid):
        """Lines 294-295 / 310: cloud API sends array directly as payload."""
        mock_post.return_value.raise_for_status = Mock()

        success, was_sent = cloud_client.send_characters(valid_grid)

        assert success is True
        assert was_sent is True
        call_args = mock_post.call_args
        # Cloud API sends the raw grid, not wrapped in {"characters": ...}
        assert call_args.kwargs["json"] == valid_grid

    def test_send_characters_ragged_row(self, client):
        """Line 310: ragged row detected after dimension check passes."""
        grid = [[0] * 22 for _ in range(6)]
        grid[2] = [0] * 21  # make one row short

        success, was_sent = client.send_characters(grid)

        assert success is False
        assert was_sent is False

    @patch('src.board_client.requests.post')
    def test_send_characters_http_error_with_response(self, mock_post, client, valid_grid):
        """Lines 342-346: HTTP exception with response body in send_characters."""
        mock_response = Mock()
        mock_response.text = "Server Error"
        mock_response.status_code = 500
        exc = requests.exceptions.HTTPError(response=mock_response)
        exc.response = mock_response
        mock_post.side_effect = exc

        success, was_sent = client.send_characters(valid_grid)
        assert success is False
        assert was_sent is False


class TestBoardClientFactory:
    """Tests for board_client_from_board_dict factory function."""

    def test_cloud_mode_with_key(self):
        """Lines 414-416: cloud mode creates client."""
        from src.board_client import board_client_from_board_dict

        board = {"api_mode": "cloud", "cloud_key": "rw-key-123"}
        client = board_client_from_board_dict(board)

        assert client is not None
        assert client.use_cloud is True
        assert client.api_key == "rw-key-123"

    def test_cloud_mode_without_key_returns_none(self):
        """Lines 414-416: cloud mode with empty key returns None."""
        from src.board_client import board_client_from_board_dict

        board = {"api_mode": "cloud", "cloud_key": ""}
        assert board_client_from_board_dict(board) is None

    def test_cloud_mode_missing_key_returns_none(self):
        from src.board_client import board_client_from_board_dict

        board = {"api_mode": "cloud"}
        assert board_client_from_board_dict(board) is None

    def test_local_mode_with_key_and_host(self):
        """Lines 428-430: local mode creates client."""
        from src.board_client import board_client_from_board_dict

        board = {
            "api_mode": "local",
            "local_api_key": "local-key",
            "host": "192.168.0.11",
        }
        client = board_client_from_board_dict(board)

        assert client is not None
        assert client.use_cloud is False
        assert client.host == "192.168.0.11"

    def test_local_mode_missing_key_returns_none(self):
        from src.board_client import board_client_from_board_dict

        board = {"api_mode": "local", "local_api_key": "", "host": "192.168.0.11"}
        assert board_client_from_board_dict(board) is None

    def test_local_mode_missing_host_returns_none(self):
        from src.board_client import board_client_from_board_dict

        board = {"api_mode": "local", "local_api_key": "key", "host": ""}
        assert board_client_from_board_dict(board) is None

    def test_default_api_mode_is_local(self):
        """Line 442: missing api_mode defaults to local."""
        from src.board_client import board_client_from_board_dict

        board = {"local_api_key": "key", "host": "10.0.0.1"}
        client = board_client_from_board_dict(board)

        assert client is not None
        assert client.use_cloud is False

    def test_port_as_string_is_converted(self):
        """Lines 454-458: string port is cast to int."""
        from src.board_client import board_client_from_board_dict

        board = {
            "api_mode": "local",
            "local_api_key": "key",
            "host": "10.0.0.1",
            "port": "7001",
        }
        client = board_client_from_board_dict(board)

        assert client is not None
        assert client._port == 7001

    def test_port_invalid_string_uses_default(self):
        """Lines 457-458: non-numeric port string falls back to None -> default."""
        from src.board_client import board_client_from_board_dict

        board = {
            "api_mode": "local",
            "local_api_key": "key",
            "host": "10.0.0.1",
            "port": "not_a_number",
        }
        client = board_client_from_board_dict(board)

        assert client is not None
        assert client._port == BoardClient.LOCAL_API_PORT

    def test_port_as_int_used_directly(self):
        """Port as int is used as-is."""
        from src.board_client import board_client_from_board_dict

        board = {
            "api_mode": "local",
            "local_api_key": "key",
            "host": "10.0.0.1",
            "port": 8080,
        }
        client = board_client_from_board_dict(board)

        assert client is not None
        assert client._port == 8080


class TestIsSuccessfulBoardReadResponse:
    """Tests for is_successful_board_read_response edge cases."""

    def test_valid_grid_returns_true(self):
        """Line 124: returns True when parse_read_message_payload succeeds."""
        grid = [[0] * 22 for _ in range(6)]
        assert is_successful_board_read_response(grid) is True

    def test_invalid_data_returns_false(self):
        """Line 127: returns False for unrecognized data."""
        assert is_successful_board_read_response({"unknown": "data"}) is False
        assert is_successful_board_read_response(42) is False


class TestWouldSendCharacters:
    """Tests for would_send with character arrays."""

    @pytest.fixture
    def client(self):
        return BoardClient(api_key="test_key", host="192.168.0.11")

    def test_would_send_characters_different(self, client):
        """Lines 414-415: would_send returns True for different characters."""
        client._last_characters = [[0] * 22 for _ in range(6)]
        different = [[1] * 22 for _ in range(6)]
        assert client.would_send(characters=different) is True

    def test_would_send_characters_same(self, client):
        """Lines 414-415: would_send returns False for same characters."""
        grid = [[0] * 22 for _ in range(6)]
        client._last_characters = grid
        assert client.would_send(characters=grid) is False

    def test_would_send_no_args_returns_true(self, client):
        """Line 416: would_send with no text/characters returns True."""
        assert client.would_send() is True


class TestTestConnectionException:
    """Tests for test_connection unexpected exception path."""

    @pytest.fixture
    def client(self):
        return BoardClient(api_key="test_key", host="192.168.0.11")

    @patch('src.board_client.requests.get')
    def test_connection_unexpected_exception(self, mock_get, client):
        """Lines 428-430: non-request exception caught by broad except."""
        mock_get.side_effect = RuntimeError("Unexpected")
        assert client.test_connection() is False


class TestSendCharactersNoResponseOnError:
    """Test send_characters error path where exception has no response."""

    @pytest.fixture
    def client(self):
        return BoardClient(api_key="test_key", host="192.168.0.11")

    @patch('src.board_client.requests.post')
    def test_send_characters_error_no_response(self, mock_post, client):
        """Line 344->346: exception without response attribute."""
        mock_post.side_effect = requests.exceptions.ConnectionError("timeout")
        grid = [[0] * 22 for _ in range(6)]
        success, was_sent = client.send_characters(grid)
        assert success is False
        assert was_sent is False
