"""The Vestaboard driver: Local API, RW Cloud and note-array Cloud.

The Vestaboard output plugin (``fiestaboard-output--vestaboard``) in core's
plugin driver, built from a board dict by the runtime factory exactly as the
engine builds it. (Was ``BoardClient``'s tests. Its text API — ``send_text``,
the text dedupe cache and ``would_send`` — is gone: nothing outside the old
client called it, and the output-plugin contract writes character grids only.)
"""

import json
from unittest.mock import Mock, patch

import pytest
import requests
from plugins.vestaboard import VestaboardOutput, transport
from plugins.vestaboard.transport import (
    LOCAL_API_PORT,
    VALID_STRATEGIES,
    is_successful_board_read_response,
    parse_read_message_payload,
    strip_color_markers,
)
from plugins.vestaboard.transport import is_valid_character_grid as _is_valid_character_grid

from src.outputs.factory import build_driver
from tests.first_party_drivers import cloud_driver, frames_of, local_driver, note_array_cloud_driver


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
    """A local board's endpoint and credential, as they reach the wire."""

    @patch("requests.post")
    def test_init_with_valid_params(self, mock_post):
        """The Local API URL and the official key header."""
        mock_post.return_value.raise_for_status = Mock()
        client = local_driver("test_key", "192.168.0.11")
        assert client.skip_unchanged is True
        client.send_characters([[0] * 22 for _ in range(6)])
        assert mock_post.call_args.args[0] == "http://192.168.0.11:7000/local-api/message"
        assert mock_post.call_args.kwargs["headers"]["X-Vestaboard-Local-Api-Key"] == "test_key"

    @patch("requests.post")
    def test_init_with_hostname(self, mock_post):
        """A hostname works where an IP does."""
        mock_post.return_value.raise_for_status = Mock()
        local_driver("test_key", "board.local").send_characters([[0] * 22 for _ in range(6)])
        assert mock_post.call_args.args[0] == "http://board.local:7000/local-api/message"

    def test_init_without_api_key_raises(self):
        """No key: the board has no connection (no driver), and the plugin refuses it."""
        assert build_driver({"api_mode": "local", "host": "192.168.0.11", "local_api_key": ""}) is None
        with pytest.raises(ValueError, match="not configured"):
            VestaboardOutput(None, {"api_mode": "local", "host": "192.168.0.11", "local_api_key": ""})

    def test_init_without_host_raises(self):
        """No host: the same."""
        assert build_driver({"api_mode": "local", "host": "", "local_api_key": "test_key"}) is None
        with pytest.raises(ValueError, match="not configured"):
            VestaboardOutput(None, {"api_mode": "local", "host": "", "local_api_key": "test_key"})

    @patch("requests.post")
    def test_init_with_skip_unchanged_false(self, mock_post):
        """skip_unchanged off: an identical grid is written again."""
        mock_post.return_value.raise_for_status = Mock()
        client = local_driver("test_key", "192.168.0.11")
        client.skip_unchanged = False
        grid = [[0] * 22 for _ in range(6)]
        assert client.send_characters(grid) == (True, True)
        assert client.send_characters(grid) == (True, True)
        assert mock_post.call_count == 2


class TestSendCharacters:
    """Tests for send_characters method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return local_driver("test_key", "192.168.0.11")

    @pytest.fixture
    def valid_grid(self):
        """Create a valid 6x22 character grid."""
        return [[0] * 22 for _ in range(6)]

    @patch("requests.post")
    def test_send_characters_success(self, mock_post, client, valid_grid):
        """Test successful character array send."""
        mock_post.return_value.raise_for_status = Mock()

        success, was_sent = client.send_characters(valid_grid)

        assert success is True
        assert was_sent is True
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["characters"] == valid_grid

    @patch("requests.post")
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

    @patch("requests.post")
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

    @patch("requests.post")
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
        return local_driver("test_key", "192.168.0.11")

    @patch("requests.get")
    def test_read_current_message_success(self, mock_get, client):
        """Test successful read of current message."""
        expected_chars = [[0] * 22 for _ in range(6)]
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.return_value = expected_chars

        result = client.read_current_message()

        assert result == expected_chars

    @patch("requests.get")
    def test_read_current_message_with_sync_cache(self, mock_get, client):
        """Test that sync_cache updates internal cache."""
        expected_chars = [[1] * 22 for _ in range(6)]
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.return_value = expected_chars

        result = client.read_current_message(sync_cache=True)

        assert result == expected_chars
        assert frames_of(client).characters == expected_chars

    @patch("requests.get")
    def test_read_current_message_network_error(self, mock_get, client):
        """Test handling of network error during read."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

        result = client.read_current_message()

        assert result is None

    @patch("requests.get")
    def test_read_current_message_cloud_current_message_shape(self, mock_get):
        """Cloud API returns currentMessage.layout (stringified JSON)."""
        grid = [[0] * 15 for _ in range(3)]
        client = cloud_driver("rw-key")
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
        return local_driver("test_key", "192.168.0.11")

    def test_clear_cache(self, client):
        """Test that clear_cache clears the dedupe cache."""
        frames_of(client).record_read([[0] * 22 for _ in range(6)])

        client.clear_cache()

        assert frames_of(client).characters is None

    def test_get_cache_status_empty(self, client):
        """Test cache status when empty."""
        status = client.get_cache_status()

        assert status["has_cached_text"] is False
        assert status["has_cached_characters"] is False
        assert status["skip_unchanged_enabled"] is True


class TestConnectionTest:
    """Tests for test_connection method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return local_driver("test_key", "192.168.0.11")

    @patch("requests.get")
    def test_connection_success(self, mock_get, client):
        """Test successful connection test."""
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.return_value = [[0] * 22 for _ in range(6)]

        assert client.test_connection() is True

    @patch("requests.get")
    def test_connection_failure(self, mock_get, client):
        """Test failed connection test."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

        assert client.test_connection() is False


class TestValidGridDimensions:
    """The fixed Vestaboard sizes a grid is checked against."""

    def test_returns_expected_dimension_set(self):
        assert {transport.FLAGSHIP, transport.NOTE} == {(6, 22), (3, 15)}


class TestIsValidCharacterGrid:
    """Tests for _is_valid_character_grid validation."""

    def test_valid_flagship_grid(self):
        grid = [[0] * 22 for _ in range(6)]
        assert _is_valid_character_grid(grid) is True

    def test_valid_note_grid(self):
        grid = [[0] * 15 for _ in range(3)]
        assert _is_valid_character_grid(grid) is True

    def test_first_element_not_list(self):
        """Line 80: first row is not a list -> return False."""
        assert _is_valid_character_grid(["not_a_list"]) is False

    def test_wrong_dimensions(self):
        """Line 87: valid structure but dimensions don't match any device."""
        grid = [[0] * 10 for _ in range(4)]
        assert _is_valid_character_grid(grid) is False

    def test_ragged_row(self):
        """Line 89: a row with different column count."""
        grid = [[0] * 22 for _ in range(6)]
        grid[3] = [0] * 21  # one short
        assert _is_valid_character_grid(grid) is False

    def test_non_int_value_in_row(self):
        """Line 89: non-int element in a row."""
        grid = [[0] * 22 for _ in range(6)]
        grid[0][5] = "x"
        assert _is_valid_character_grid(grid) is False

    def test_empty_list(self):
        assert _is_valid_character_grid([]) is False

    def test_not_a_list(self):
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


class TestSendCharactersEdgeCases:
    """Additional edge cases for send_characters."""

    @pytest.fixture
    def client(self):
        return local_driver("test_key", "192.168.0.11")

    @pytest.fixture
    def cloud_client(self):
        return cloud_driver("rw-key")

    @pytest.fixture
    def valid_grid(self):
        return [[0] * 22 for _ in range(6)]

    @patch("requests.post")
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

    @patch("requests.post")
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
    """The vestaboard output's configurations, built through the runtime factory."""

    def test_cloud_mode_with_key(self):
        """Lines 414-416: cloud mode creates client."""
        from src.outputs.factory import build_driver

        board = {"api_mode": "cloud", "cloud_key": "rw-key-123"}
        client = build_driver(board)

        assert client is not None
        assert client.use_cloud is True
        assert client.plugin.connection.key == "rw-key-123"

    def test_cloud_mode_without_key_returns_none(self):
        """Lines 414-416: cloud mode with empty key returns None."""
        from src.outputs.factory import build_driver

        board = {"api_mode": "cloud", "cloud_key": ""}
        assert build_driver(board) is None

    def test_cloud_mode_missing_key_returns_none(self):
        from src.outputs.factory import build_driver

        board = {"api_mode": "cloud"}
        assert build_driver(board) is None

    def test_local_mode_with_key_and_host(self):
        """Lines 428-430: local mode creates client."""
        from src.outputs.factory import build_driver

        board = {
            "api_mode": "local",
            "local_api_key": "local-key",
            "host": "192.168.0.11",
        }
        client = build_driver(board)

        assert client is not None
        assert client.use_cloud is False
        assert client.plugin.connection.host == "192.168.0.11"

    def test_local_mode_missing_key_returns_none(self):
        from src.outputs.factory import build_driver

        board = {"api_mode": "local", "local_api_key": "", "host": "192.168.0.11"}
        assert build_driver(board) is None

    def test_local_mode_missing_host_returns_none(self):
        from src.outputs.factory import build_driver

        board = {"api_mode": "local", "local_api_key": "key", "host": ""}
        assert build_driver(board) is None

    def test_default_api_mode_is_local(self):
        """Line 442: missing api_mode defaults to local."""
        from src.outputs.factory import build_driver

        board = {"local_api_key": "key", "host": "10.0.0.1"}
        client = build_driver(board)

        assert client is not None
        assert client.use_cloud is False

    def test_port_as_string_is_converted(self):
        """Lines 454-458: string port is cast to int."""
        from src.outputs.factory import build_driver

        board = {
            "api_mode": "local",
            "local_api_key": "key",
            "host": "10.0.0.1",
            "port": "7001",
        }
        client = build_driver(board)

        assert client is not None
        assert client.plugin.connection.port == 7001

    def test_port_invalid_string_uses_default(self):
        """Lines 457-458: non-numeric port string falls back to None -> default."""
        from src.outputs.factory import build_driver

        board = {
            "api_mode": "local",
            "local_api_key": "key",
            "host": "10.0.0.1",
            "port": "not_a_number",
        }
        client = build_driver(board)

        assert client is not None
        assert client.plugin.connection.port == LOCAL_API_PORT

    def test_port_as_int_used_directly(self):
        """Port as int is used as-is."""
        from src.outputs.factory import build_driver

        board = {
            "api_mode": "local",
            "local_api_key": "key",
            "host": "10.0.0.1",
            "port": 8080,
        }
        client = build_driver(board)

        assert client is not None
        assert client.plugin.connection.port == 8080


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


class TestTestConnectionException:
    """Tests for test_connection unexpected exception path."""

    @pytest.fixture
    def client(self):
        return local_driver("test_key", "192.168.0.11")

    @patch("requests.get")
    def test_connection_unexpected_exception(self, mock_get, client):
        """Lines 428-430: non-request exception caught by broad except."""
        mock_get.side_effect = RuntimeError("Unexpected")
        assert client.test_connection() is False


class TestSendCharactersNoResponseOnError:
    """Test send_characters error path where exception has no response."""

    @pytest.fixture
    def client(self):
        return local_driver("test_key", "192.168.0.11")

    @patch("requests.post")
    def test_send_characters_error_no_response(self, mock_post, client):
        """Line 344->346: exception without response attribute."""
        mock_post.side_effect = requests.exceptions.ConnectionError("timeout")
        grid = [[0] * 22 for _ in range(6)]
        success, was_sent = client.send_characters(grid)
        assert success is False
        assert was_sent is False


# ---------------------------------------------------------------------------
# Issue #1168 — Note-array Cloud API send/read
# ---------------------------------------------------------------------------

# Hermetic: track the note-array Cloud URL the plugin is ACTUALLY configured to
# use. Its CLOUD_NOTE_ARRAY_API_URL honors VESTABOARD_CLOUD_API_URL, so
# these URL assertions pass both in CI (env unset → real cloud.vestaboard.com)
# and inside the dev container (env set → the mock-cloud service), instead of
# failing whenever the suite runs in the documented `docker exec … pytest` flow.
CLOUD_NOTE_ARRAY_URL = transport.CLOUD_NOTE_ARRAY_API_URL
RW_CLOUD_URL = "https://rw.vestaboard.com/"


class TestNoteArrayClientInit:
    """The plugin resolves a note array's connection correctly."""

    def test_note_array_client_has_is_note_array_flag(self):
        connection = note_array_cloud_driver("tok", 4, 1).plugin.connection
        assert connection.mode == "note_array_cloud"
        assert connection.key == "tok"
        assert connection.notes_wide == 4
        assert connection.notes_tall == 1

    def test_non_note_array_client_is_note_array_false(self):
        assert local_driver("key", "10.0.0.1").plugin.connection.mode == "local"

    def test_cloud_rw_client_is_note_array_false(self):
        assert cloud_driver("rw-key").plugin.connection.mode == "cloud"


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
        return note_array_cloud_driver("na-tok", 4, 1)

    @pytest.fixture
    def valid_3x60_grid(self):
        return [[0] * 60 for _ in range(3)]

    @pytest.fixture
    def valid_6x30_grid(self):
        return [[0] * 30 for _ in range(6)]

    @patch("requests.post")
    def test_send_note_array_posts_to_cloud_note_array_url(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        note_array_client.send_characters(valid_3x60_grid)
        assert mock_post.call_args.args[0] == CLOUD_NOTE_ARRAY_URL

    @patch("requests.post")
    def test_send_note_array_uses_x_vestaboard_token_header(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        note_array_client.send_characters(valid_3x60_grid)
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["X-Vestaboard-Token"] == "na-tok"

    @patch("requests.post")
    def test_send_note_array_body_is_characters_dict(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        note_array_client.send_characters(valid_3x60_grid)
        body = mock_post.call_args.kwargs["json"]
        assert body == {"characters": valid_3x60_grid}

    @patch("requests.post")
    def test_send_note_array_success_returns_true_true(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        result = note_array_client.send_characters(valid_3x60_grid)
        assert result == (True, True)

    @patch("requests.post")
    def test_send_note_array_network_error(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.side_effect = requests.exceptions.ConnectionError("connection refused")
        result = note_array_client.send_characters(valid_3x60_grid)
        assert result == (False, False)

    @patch("requests.post")
    def test_send_note_array_6x30_grid_accepted(self, mock_post, note_array_client, valid_6x30_grid):
        # The client is configured 4x1 (expects 3x60) but a 6x30 grid is still
        # accepted: _is_valid_character_grid validates note-array shape, not the
        # client's specific size (grid-size enforcement is a future follow-up).
        mock_post.return_value.raise_for_status = Mock()
        result = note_array_client.send_characters(valid_6x30_grid)
        assert result == (True, True)

    def test_send_text_not_supported_for_note_array(self, note_array_client):
        """Characters only (the Cloud API has no text endpoint): there is no text send."""
        assert not hasattr(note_array_client, "send_text")

    @patch("requests.post")
    def test_send_note_array_does_not_use_rw_cloud_url(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        note_array_client.send_characters(valid_3x60_grid)
        assert mock_post.call_args.args[0] != RW_CLOUD_URL

    @patch("requests.post")
    def test_rw_cloud_still_sends_bare_array(self, mock_post):
        """Existing RW Cloud API behavior must be unchanged (bare array, not wrapped)."""
        rw_client = cloud_driver("rw")
        valid_6x22 = [[0] * 22 for _ in range(6)]
        mock_post.return_value.raise_for_status = Mock()
        rw_client.send_characters(valid_6x22)
        body = mock_post.call_args.kwargs["json"]
        assert body == valid_6x22


class TestNoteArrayReadCurrentMessage:
    """read_current_message routes note-array boards to the new Cloud API."""

    @pytest.fixture
    def note_array_client(self):
        return note_array_cloud_driver("na-tok", 4, 1)

    def _make_layout_response(self, grid):
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {"currentMessage": {"layout": json.dumps(grid)}}
        return mock_resp

    @patch("requests.get")
    def test_read_note_array_gets_cloud_note_array_url(self, mock_get, note_array_client):
        grid = [[0] * 60 for _ in range(3)]
        mock_get.return_value = self._make_layout_response(grid)
        note_array_client.read_current_message()
        assert mock_get.call_args.args[0] == CLOUD_NOTE_ARRAY_URL

    @patch("requests.get")
    def test_read_note_array_uses_x_vestaboard_token_header(self, mock_get, note_array_client):
        grid = [[0] * 60 for _ in range(3)]
        mock_get.return_value = self._make_layout_response(grid)
        note_array_client.read_current_message()
        headers = mock_get.call_args.kwargs["headers"]
        assert headers["X-Vestaboard-Token"] == "na-tok"

    @patch("requests.get")
    def test_read_note_array_parses_layout_to_grid(self, mock_get, note_array_client):
        grid = [[0] * 60 for _ in range(3)]
        mock_get.return_value = self._make_layout_response(grid)
        result = note_array_client.read_current_message()
        assert result == grid

    @patch("requests.get")
    def test_read_note_array_6x30_parses_correctly(self, mock_get, note_array_client):
        grid = [[0] * 30 for _ in range(6)]
        mock_get.return_value = self._make_layout_response(grid)
        result = note_array_client.read_current_message()
        assert result == grid

    @patch("requests.get")
    def test_read_note_array_network_error_returns_none(self, mock_get, note_array_client):
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")
        result = note_array_client.read_current_message()
        assert result is None


class TestBoardClientFactoryNoteArray:
    """The runtime factory wires note-array boards correctly."""

    def test_note_array_board_creates_client(self):
        board = {
            "device_type": "note_array",
            "note_array_token": "tok",
            "notes_wide": 4,
            "notes_tall": 1,
        }
        client = build_driver(board)
        assert client is not None
        assert client.plugin.connection.mode == "note_array_cloud"
        assert client.plugin.connection.key == "tok"

    def test_note_array_board_no_token_returns_none(self):
        board = {
            "device_type": "note_array",
            "note_array_token": "",
            "notes_wide": 4,
            "notes_tall": 1,
        }
        assert build_driver(board) is None

    def test_note_array_board_missing_token_returns_none(self):
        board = {"device_type": "note_array"}
        assert build_driver(board) is None

    def test_note_array_notes_wide_tall_stored(self):
        board = {
            "device_type": "note_array",
            "note_array_token": "tok",
            "notes_wide": 2,
            "notes_tall": 3,
        }
        client = build_driver(board)
        assert client is not None
        assert client.plugin.connection.notes_wide == 2
        assert client.plugin.connection.notes_tall == 3

    def test_flagship_board_cloud_unaffected(self):
        board = {"api_mode": "cloud", "cloud_key": "rw-key"}
        client = build_driver(board)
        assert client is not None
        assert client.plugin.connection.mode != "note_array_cloud"

    def test_flagship_board_local_unaffected(self):
        board = {"api_mode": "local", "local_api_key": "k", "host": "10.0.0.1"}
        client = build_driver(board)
        assert client is not None
        assert client.plugin.connection.mode != "note_array_cloud"


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
            return note_array_cloud_driver(token, 4, 1, clock=time_func)

        return _make

    @pytest.fixture
    def note_array_client(self):
        return note_array_cloud_driver("na-strip-tok", 4, 1)

    @pytest.fixture
    def valid_3x60_grid(self):
        return [[0] * 60 for _ in range(3)]

    @pytest.fixture
    def other_3x60_grid(self):
        # A distinct grid to bypass the content-unchanged cache on a second send.
        return [[1] * 60 for _ in range(3)]

    # --- transition stripping -------------------------------------------------

    @patch("requests.post")
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

    @patch("requests.post")
    def test_note_array_send_omits_strategy_none_also_fine(self, mock_post, note_array_client, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()

        note_array_client.send_characters(valid_3x60_grid, strategy=None)

        body = mock_post.call_args.kwargs["json"]
        assert body == {"characters": valid_3x60_grid}

    # --- throttle -------------------------------------------------------------

    @patch("requests.post")
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

    @patch("requests.post")
    def test_note_array_second_send_at_exactly_15s_goes_through(
        self, mock_post, note_array_client_with_clock, valid_3x60_grid, other_3x60_grid
    ):
        mock_post.return_value.raise_for_status = Mock()
        client = note_array_client_with_clock(_clock(0.0, 15.0), "na-throttle-exact")

        assert client.send_characters(valid_3x60_grid) == (True, True)
        assert client.send_characters(other_3x60_grid) == (True, True)
        assert mock_post.call_count == 2

    @patch("requests.post")
    def test_note_array_second_send_after_15s_goes_through(
        self, mock_post, note_array_client_with_clock, valid_3x60_grid, other_3x60_grid
    ):
        mock_post.return_value.raise_for_status = Mock()
        client = note_array_client_with_clock(_clock(0.0, 16.0), "na-throttle-after")

        assert client.send_characters(valid_3x60_grid) == (True, True)
        assert client.send_characters(other_3x60_grid) == (True, True)
        assert mock_post.call_count == 2

    @patch("requests.post")
    def test_throttled_send_is_reported_via_last_send_throttled(
        self, mock_post, note_array_client_with_clock, valid_3x60_grid, other_3x60_grid
    ):
        """A throttled send and an unchanged-content skip both return
        ``(True, False)``, but only the first means the board never got the
        content. Callers need to tell them apart (issue #1794 review)."""
        mock_post.return_value.raise_for_status = Mock()
        client = note_array_client_with_clock(_clock(0.0, 10.0), "na-throttle-flag")

        client.send_characters(valid_3x60_grid)
        assert client.last_send_throttled is False

        assert client.send_characters(other_3x60_grid) == (True, False)
        assert client.last_send_throttled is True

    @patch("requests.post")
    def test_unchanged_content_skip_is_not_reported_as_throttled(
        self, mock_post, note_array_client_with_clock, valid_3x60_grid
    ):
        """Re-sending identical content skips, but the frame IS on the board."""
        mock_post.return_value.raise_for_status = Mock()
        client = note_array_client_with_clock(_clock(0.0, 100.0), "na-unchanged-flag")

        client.send_characters(valid_3x60_grid)
        assert client.send_characters(valid_3x60_grid) == (True, False)
        assert client.last_send_throttled is False

    @patch("requests.post")
    def test_note_array_first_send_always_goes_through(self, mock_post, note_array_client_with_clock, valid_3x60_grid):
        mock_post.return_value.raise_for_status = Mock()
        # Token never previously seen by the core send floor.
        client = note_array_client_with_clock(_clock(100.0), "na-throttle-first")

        assert client.send_characters(valid_3x60_grid) == (True, True)
        assert mock_post.call_count == 1

    @patch("requests.post")
    def test_note_array_throttle_state_persists_across_client_recreation(
        self, mock_post, note_array_client_with_clock, valid_3x60_grid, other_3x60_grid
    ):
        """A new driver with the same token still sees the prior send's timestamp."""
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

    @patch("requests.post")
    def test_flagship_transitions_unchanged(self, mock_post):
        """Flagship local sends still carry transition params."""
        client = local_driver("local-key", "192.168.0.11")
        grid = [[0] * 22 for _ in range(6)]
        mock_post.return_value.raise_for_status = Mock()

        result = client.send_characters(grid, strategy="column", step_interval_ms=500, step_size=2)

        body = mock_post.call_args.kwargs["json"]
        assert body["strategy"] == "column"
        assert body["step_interval_ms"] == 500
        assert body["step_size"] == 2
        assert result == (True, True)
