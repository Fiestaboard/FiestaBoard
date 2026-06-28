"""Tests for Board Local API client."""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from src.board_client import (
    VALID_STRATEGIES,
    BoardClient,
    _is_valid_character_grid,
    _note_array_last_send,
    board_client_from_board_dict,
    is_successful_board_read_response,
    parse_read_message_payload,
    strip_color_markers,
)


@pytest.fixture(autouse=True)
def _reset_note_array_throttle():
    """Clear the module-level note-array throttle state before each test.

    ``_note_array_last_send`` persists for the process lifetime by design, so
    without this reset a timestamp left by one test would throttle the first
    send of an unrelated test that reuses the same token.
    """
    _note_array_last_send.clear()
    yield
    _note_array_last_send.clear()


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
        client = BoardClient(api_key="test_key", host="192.168.0.11")
        assert client.host == "192.168.0.11"
        assert client.skip_unchanged is True
        assert client.base_url == "http://192.168.0.11:7000/local-api/message"
        assert "X-Vestaboard-Local-Api-Key" in client.headers  # Official board API header
        assert client.headers["X-Vestaboard-Local-Api-Key"] == "test_key"

    def test_init_with_hostname(self):
        """Test initialization with hostname instead of IP."""
        client = BoardClient(api_key="test_key", host="board.local")
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
        client = BoardClient(api_key="test_key", host="192.168.0.11", skip_unchanged=False)
        assert client.skip_unchanged is False


class TestSendText:
    """Tests for send_text method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return BoardClient(api_key="test_key", host="192.168.0.11")

    @patch("src.board_client.requests.post")
    def test_send_text_success(self, mock_post, client):
        """Test successful text send."""
        mock_post.return_value.raise_for_status = Mock()

        success, was_sent = client.send_text("Hello World")

        assert success is True
        assert was_sent is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["json"] == {"text": "HELLO WORLD"}

    @patch("src.board_client.requests.post")
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

    @patch("src.board_client.requests.post")
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

    @patch("src.board_client.requests.post")
    def test_send_text_network_error(self, mock_post, client):
        """Test handling of network error."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Network error")

        success, was_sent = client.send_text("Hello World")

        assert success is False
        assert was_sent is False

    @patch("src.board_client.requests.post")
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

    @patch("src.board_client.requests.post")
    def test_send_characters_success(self, mock_post, client, valid_grid):
        """Test successful character array send."""
        mock_post.return_value.raise_for_status = Mock()

        success, was_sent = client.send_characters(valid_grid)

        assert success is True
        assert was_sent is True
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["characters"] == valid_grid

    @patch("src.board_client.requests.post")
    def test_send_characters_with_transition(self, mock_post, client, valid_grid):
        """Test sending with transition settings."""
        mock_post.return_value.raise_for_status = Mock()

        success, was_sent = client.send_characters(valid_grid, strategy="column", step_interval_ms=500, step_size=2)

        assert success is True
        assert was_sent is True
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert payload["strategy"] == "column"
        assert payload["step_interval_ms"] == 500
        assert payload["step_size"] == 2

    @patch("src.board_client.requests.post")
    def test_send_characters_all_strategies(self, mock_post, client, valid_grid):
        """Test all valid transition strategies."""
        mock_post.return_value.raise_for_status = Mock()

        for strategy in VALID_STRATEGIES:
            client.clear_cache()  # Clear cache between tests
            success, _was_sent = client.send_characters(valid_grid, strategy=strategy)
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

    @patch("src.board_client.requests.post")
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

    @patch("src.board_client.requests.get")
    def test_read_current_message_success(self, mock_get, client):
        """Test successful read of current message."""
        expected_chars = [[0] * 22 for _ in range(6)]
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.return_value = expected_chars

        result = client.read_current_message()

        assert result == expected_chars

    @patch("src.board_client.requests.get")
    def test_read_current_message_with_sync_cache(self, mock_get, client):
        """Test that sync_cache updates internal cache."""
        expected_chars = [[1] * 22 for _ in range(6)]
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.return_value = expected_chars

        result = client.read_current_message(sync_cache=True)

        assert result == expected_chars
        assert client._last_characters == expected_chars

    @patch("src.board_client.requests.get")
    def test_read_current_message_network_error(self, mock_get, client):
        """Test handling of network error during read."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

        result = client.read_current_message()

        assert result is None

    @patch("src.board_client.requests.get")
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

    @patch("src.board_client.requests.post")
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

    @patch("src.board_client.requests.get")
    def test_connection_success(self, mock_get, client):
        """Test successful connection test."""
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.return_value = [[0] * 22 for _ in range(6)]

        assert client.test_connection() is True

    @patch("src.board_client.requests.get")
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

    @patch("src.board_client.requests.post")
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

    @patch("src.board_client.requests.post")
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

    @patch("src.board_client.requests.post")
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

    @patch("src.board_client.requests.get")
    def test_connection_unexpected_exception(self, mock_get, client):
        """Lines 428-430: non-request exception caught by broad except."""
        mock_get.side_effect = RuntimeError("Unexpected")
        assert client.test_connection() is False


class TestSendCharactersNoResponseOnError:
    """Test send_characters error path where exception has no response."""

    @pytest.fixture
    def client(self):
        return BoardClient(api_key="test_key", host="192.168.0.11")

    @patch("src.board_client.requests.post")
    def test_send_characters_error_no_response(self, mock_post, client):
        """Line 344->346: exception without response attribute."""
        mock_post.side_effect = requests.exceptions.ConnectionError("timeout")
        grid = [[0] * 22 for _ in range(6)]
        success, was_sent = client.send_characters(grid)
        assert success is False
        assert was_sent is False


# ---------------------------------------------------------------------------
# Issue #1168 — Note-array Cloud API send/read in BoardClient
# ---------------------------------------------------------------------------

# Hermetic: track the note-array Cloud URL the client is ACTUALLY configured to
# use. BoardClient.CLOUD_NOTE_ARRAY_API_URL honors VESTABOARD_CLOUD_API_URL, so
# these URL assertions pass both in CI (env unset → real cloud.vestaboard.com)
# and inside the dev container (env set → the mock-cloud service), instead of
# failing whenever the suite runs in the documented `docker exec … pytest` flow.
CLOUD_NOTE_ARRAY_URL = BoardClient.CLOUD_NOTE_ARRAY_API_URL
RW_CLOUD_URL = "https://rw.vestaboard.com/"


class TestNoteArrayClientInit:
    """BoardClient stores note-array state correctly."""

    def test_note_array_client_has_is_note_array_flag(self):
        client = BoardClient(
            api_key="tok",
            use_cloud=True,
            note_array_token="tok",
            notes_wide=4,
            notes_tall=1,
        )
        assert client._is_note_array is True
        assert client._note_array_token == "tok"
        assert client._notes_wide == 4
        assert client._notes_tall == 1

    def test_non_note_array_client_is_note_array_false(self):
        client = BoardClient(api_key="key", host="10.0.0.1")
        assert client._is_note_array is False

    def test_cloud_rw_client_is_note_array_false(self):
        client = BoardClient(api_key="rw-key", use_cloud=True)
        assert client._is_note_array is False


class TestIsValidCharacterGridNoteArray:
    """_is_valid_character_grid accepts valid note-array grids and rejects malformed ones."""

    def test_valid_note_array_3x60(self):
        # 4 notes wide × 1 note tall
        grid = [[0] * 60 for _ in range(3)]
        assert _is_valid_character_grid(grid) is True

    def test_valid_note_array_6x30(self):
        # 2 notes wide × 2 notes tall
        grid = [[0] * 30 for _ in range(6)]
        assert _is_valid_character_grid(grid) is True

    def test_valid_note_array_3x15(self):
        # 1×1 note: same as the Note device (already in _valid_grid_dimensions)
        grid = [[0] * 15 for _ in range(3)]
        assert _is_valid_character_grid(grid) is True

    def test_valid_flagship_still_accepted(self):
        grid = [[0] * 22 for _ in range(6)]
        assert _is_valid_character_grid(grid) is True

    def test_valid_note_still_accepted(self):
        grid = [[0] * 15 for _ in range(3)]
        assert _is_valid_character_grid(grid) is True

    def test_invalid_note_array_non_multiple_rows(self):
        # 4 rows is not a multiple of 3
        grid = [[0] * 30 for _ in range(4)]
        assert _is_valid_character_grid(grid) is False

    def test_invalid_note_array_non_multiple_cols(self):
        # 20 cols is not a multiple of 15
        grid = [[0] * 20 for _ in range(3)]
        assert _is_valid_character_grid(grid) is False

    def test_invalid_arbitrary_size_rejected(self):
        grid = [[0] * 10 for _ in range(4)]
        assert _is_valid_character_grid(grid) is False


class TestNoteArraySendCharacters:
    """send_characters routes note-array boards to the new Cloud API."""

    @pytest.fixture
    def note_array_client(self):
        return BoardClient(
            api_key="na-tok",
            use_cloud=True,
            note_array_token="na-tok",
            notes_wide=4,
            notes_tall=1,
        )

    @pytest.fixture
    def valid_3x60_grid(self):
        return [[0] * 60 for _ in range(3)]

    @pytest.fixture
    def valid_6x30_grid(self):
        return [[0] * 30 for _ in range(6)]

    @patch("src.board_client.requests.post")
    def test_send_note_array_posts_to_cloud_note_array_url(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        note_array_client.send_characters(valid_3x60_grid)
        assert mock_post.call_args.args[0] == CLOUD_NOTE_ARRAY_URL

    @patch("src.board_client.requests.post")
    def test_send_note_array_uses_x_vestaboard_token_header(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        note_array_client.send_characters(valid_3x60_grid)
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["X-Vestaboard-Token"] == "na-tok"

    @patch("src.board_client.requests.post")
    def test_send_note_array_body_is_characters_dict(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        note_array_client.send_characters(valid_3x60_grid)
        body = mock_post.call_args.kwargs["json"]
        assert body == {"characters": valid_3x60_grid}

    @patch("src.board_client.requests.post")
    def test_send_note_array_success_returns_true_true(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        result = note_array_client.send_characters(valid_3x60_grid)
        assert result == (True, True)

    @patch("src.board_client.requests.post")
    def test_send_note_array_network_error(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.side_effect = requests.exceptions.ConnectionError("connection refused")
        result = note_array_client.send_characters(valid_3x60_grid)
        assert result == (False, False)

    @patch("src.board_client.requests.post")
    def test_send_note_array_6x30_grid_accepted(self, mock_post, note_array_client, valid_6x30_grid):
        # The client is configured 4x1 (expects 3x60) but a 6x30 grid is still
        # accepted: _is_valid_character_grid validates note-array shape, not the
        # client's specific size (grid-size enforcement is a future follow-up).
        mock_post.return_value.raise_for_status = Mock()
        result = note_array_client.send_characters(valid_6x30_grid)
        assert result == (True, True)

    @patch("src.board_client.requests.post")
    def test_send_text_not_supported_for_note_array(self, mock_post, note_array_client):
        """send_text on a note-array board fails gracefully and never POSTs (Cloud API is characters-only)."""
        result = note_array_client.send_text("HELLO")
        assert result == (False, False)
        mock_post.assert_not_called()

    @patch("src.board_client.requests.post")
    def test_send_note_array_does_not_use_rw_cloud_url(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        note_array_client.send_characters(valid_3x60_grid)
        assert mock_post.call_args.args[0] != RW_CLOUD_URL

    @patch("src.board_client.requests.post")
    def test_rw_cloud_still_sends_bare_array(self, mock_post):
        """Existing RW Cloud API behavior must be unchanged (bare array, not wrapped)."""
        rw_client = BoardClient(api_key="rw", use_cloud=True)
        valid_6x22 = [[0] * 22 for _ in range(6)]
        mock_post.return_value.raise_for_status = Mock()
        rw_client.send_characters(valid_6x22)
        body = mock_post.call_args.kwargs["json"]
        assert body == valid_6x22


class TestNoteArrayReadCurrentMessage:
    """read_current_message routes note-array boards to the new Cloud API."""

    @pytest.fixture
    def note_array_client(self):
        return BoardClient(
            api_key="na-tok",
            use_cloud=True,
            note_array_token="na-tok",
            notes_wide=4,
            notes_tall=1,
        )

    def _make_layout_response(self, grid):
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {"currentMessage": {"layout": json.dumps(grid)}}
        return mock_resp

    @patch("src.board_client.requests.get")
    def test_read_note_array_gets_cloud_note_array_url(self, mock_get, note_array_client):
        grid = [[0] * 60 for _ in range(3)]
        mock_get.return_value = self._make_layout_response(grid)
        note_array_client.read_current_message()
        assert mock_get.call_args.args[0] == CLOUD_NOTE_ARRAY_URL

    @patch("src.board_client.requests.get")
    def test_read_note_array_uses_x_vestaboard_token_header(self, mock_get, note_array_client):
        grid = [[0] * 60 for _ in range(3)]
        mock_get.return_value = self._make_layout_response(grid)
        note_array_client.read_current_message()
        headers = mock_get.call_args.kwargs["headers"]
        assert headers["X-Vestaboard-Token"] == "na-tok"

    @patch("src.board_client.requests.get")
    def test_read_note_array_parses_layout_to_grid(self, mock_get, note_array_client):
        grid = [[0] * 60 for _ in range(3)]
        mock_get.return_value = self._make_layout_response(grid)
        result = note_array_client.read_current_message()
        assert result == grid

    @patch("src.board_client.requests.get")
    def test_read_note_array_6x30_parses_correctly(self, mock_get, note_array_client):
        grid = [[0] * 30 for _ in range(6)]
        mock_get.return_value = self._make_layout_response(grid)
        result = note_array_client.read_current_message()
        assert result == grid

    @patch("src.board_client.requests.get")
    def test_read_note_array_network_error_returns_none(self, mock_get, note_array_client):
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")
        result = note_array_client.read_current_message()
        assert result is None


class TestBoardClientFactoryNoteArray:
    """board_client_from_board_dict wires note-array boards correctly."""

    def test_note_array_board_creates_client(self):
        board = {
            "device_type": "note_array",
            "note_array_token": "tok",
            "notes_wide": 4,
            "notes_tall": 1,
        }
        client = board_client_from_board_dict(board)
        assert client is not None
        assert client._is_note_array is True
        assert client._note_array_token == "tok"

    def test_note_array_board_no_token_returns_none(self):
        board = {
            "device_type": "note_array",
            "note_array_token": "",
            "notes_wide": 4,
            "notes_tall": 1,
        }
        assert board_client_from_board_dict(board) is None

    def test_note_array_board_missing_token_returns_none(self):
        board = {"device_type": "note_array"}
        assert board_client_from_board_dict(board) is None

    def test_note_array_notes_wide_tall_stored(self):
        board = {
            "device_type": "note_array",
            "note_array_token": "tok",
            "notes_wide": 2,
            "notes_tall": 3,
        }
        client = board_client_from_board_dict(board)
        assert client is not None
        assert client._notes_wide == 2
        assert client._notes_tall == 3

    def test_flagship_board_cloud_unaffected(self):
        board = {"api_mode": "cloud", "cloud_key": "rw-key"}
        client = board_client_from_board_dict(board)
        assert client is not None
        assert client._is_note_array is False

    def test_flagship_board_local_unaffected(self):
        board = {"api_mode": "local", "local_api_key": "k", "host": "10.0.0.1"}
        client = board_client_from_board_dict(board)
        assert client is not None
        assert client._is_note_array is False


# ---------------------------------------------------------------------------
# Issue #1169 — Note-array send constraints (no transitions, 15s rate limit)
# ---------------------------------------------------------------------------


def _clock(*values):
    """Return a callable that yields the given values in order, then repeats the last."""
    seq = list(values)

    def _next():
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return _next


class TestNoteArrayConstraints:
    """Note-array sends strip transitions and enforce a 15s rate limit."""

    @pytest.fixture
    def note_array_client_with_clock(self):
        """Factory: call with (time_func, token) to get a throttle-testable client."""

        def _make(time_func, token):
            return BoardClient(
                api_key=token,
                use_cloud=True,
                note_array_token=token,
                notes_wide=4,
                notes_tall=1,
                _time_func=time_func,
            )

        return _make

    @pytest.fixture
    def note_array_client(self):
        return BoardClient(
            api_key="na-tok",
            use_cloud=True,
            note_array_token="na-strip-tok",
            notes_wide=4,
            notes_tall=1,
        )

    @pytest.fixture
    def valid_3x60_grid(self):
        return [[0] * 60 for _ in range(3)]

    @pytest.fixture
    def other_3x60_grid(self):
        # A distinct grid to bypass the content-unchanged cache on a second send.
        return [[1] * 60 for _ in range(3)]

    # --- transition stripping -------------------------------------------------

    @patch("src.board_client.requests.post")
    def test_note_array_send_omits_strategy_even_when_passed(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()

        result = note_array_client.send_characters(
            valid_3x60_grid, strategy="column", step_interval_ms=500, step_size=2
        )

        body = mock_post.call_args.kwargs["json"]
        assert "strategy" not in body
        assert "step_interval_ms" not in body
        assert "step_size" not in body
        assert result == (True, True)

    @patch("src.board_client.requests.post")
    def test_note_array_send_omits_strategy_none_also_fine(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()

        note_array_client.send_characters(valid_3x60_grid, strategy=None)

        body = mock_post.call_args.kwargs["json"]
        assert body == {"characters": valid_3x60_grid}

    # --- throttle -------------------------------------------------------------

    @patch("src.board_client.requests.post")
    def test_note_array_second_send_within_15s_is_throttled(
        self, mock_post, note_array_client_with_clock, valid_3x60_grid, other_3x60_grid, caplog
    ):
        mock_post.return_value.raise_for_status = Mock()
        # First send at t=0, throttle-check on second send at t=10 (<15s).
        client = note_array_client_with_clock(_clock(0.0, 10.0), "na-throttle-within")

        first = client.send_characters(valid_3x60_grid)
        assert first == (True, True)
        assert mock_post.call_count == 1

        with caplog.at_level("WARNING"):
            second = client.send_characters(other_3x60_grid)

        assert second == (True, False)
        assert mock_post.call_count == 1  # not sent again
        assert any(record.levelname == "WARNING" and "throttled" in record.message for record in caplog.records)

    @patch("src.board_client.requests.post")
    def test_note_array_second_send_at_exactly_15s_goes_through(
        self, mock_post, note_array_client_with_clock, valid_3x60_grid, other_3x60_grid
    ):
        mock_post.return_value.raise_for_status = Mock()
        client = note_array_client_with_clock(_clock(0.0, 15.0), "na-throttle-exact")

        assert client.send_characters(valid_3x60_grid) == (True, True)
        assert client.send_characters(other_3x60_grid) == (True, True)
        assert mock_post.call_count == 2

    @patch("src.board_client.requests.post")
    def test_note_array_second_send_after_15s_goes_through(
        self, mock_post, note_array_client_with_clock, valid_3x60_grid, other_3x60_grid
    ):
        mock_post.return_value.raise_for_status = Mock()
        client = note_array_client_with_clock(_clock(0.0, 16.0), "na-throttle-after")

        assert client.send_characters(valid_3x60_grid) == (True, True)
        assert client.send_characters(other_3x60_grid) == (True, True)
        assert mock_post.call_count == 2

    @patch("src.board_client.requests.post")
    def test_note_array_first_send_always_goes_through(self, mock_post, note_array_client_with_clock, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        # Token never previously seen in _note_array_last_send.
        client = note_array_client_with_clock(_clock(100.0), "na-throttle-first")

        assert client.send_characters(valid_3x60_grid) == (True, True)
        assert mock_post.call_count == 1

    @patch("src.board_client.requests.post")
    def test_note_array_throttle_state_persists_across_client_recreation(
        self, mock_post, note_array_client_with_clock, valid_3x60_grid, other_3x60_grid
    ):
        """A new BoardClient with the same token still sees the prior send's timestamp."""
        mock_post.return_value.raise_for_status = Mock()
        token = "na-throttle-persist"

        first_client = note_array_client_with_clock(_clock(0.0), token)
        assert first_client.send_characters(valid_3x60_grid) == (True, True)
        assert mock_post.call_count == 1

        # New instance (simulating reinitialize_board_client), clock at t=5 (<15s).
        second_client = note_array_client_with_clock(_clock(5.0), token)
        result = second_client.send_characters(other_3x60_grid)

        assert result == (True, False)
        assert mock_post.call_count == 1  # second instance's send was throttled

    # --- regression -----------------------------------------------------------

    @patch("src.board_client.requests.post")
    def test_flagship_transitions_unchanged(self, mock_post):
        """Flagship local sends still carry transition params."""
        client = BoardClient(api_key="local-key", host="192.168.0.11")
        grid = [[0] * 22 for _ in range(6)]
        mock_post.return_value.raise_for_status = Mock()

        result = client.send_characters(grid, strategy="column", step_interval_ms=500, step_size=2)

        body = mock_post.call_args.kwargs["json"]
        assert body["strategy"] == "column"
        assert body["step_interval_ms"] == 500
        assert body["step_size"] == 2
        assert result == (True, True)
