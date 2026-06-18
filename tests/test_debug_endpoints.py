"""Tests for debug API endpoints."""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app

# ---------------------------------------------------------------------------
# Helper: build a mock SettingsService pre-configured for a given board type
# ---------------------------------------------------------------------------


def _mock_ss(device_type="flagship", notes_wide=1, notes_tall=1, send_to_board=True):
    """Return a Mock SettingsService wired for a specific board geometry.

    Args:
        device_type: "flagship", "note", or "note_array"
        notes_wide: number of notes side-by-side (for note_array)
        notes_tall: number of notes stacked (for note_array)
        send_to_board: return value for should_send_to_board()
    """
    ss = Mock()
    ss.should_send_to_board.return_value = send_to_board
    ss.is_paused.return_value = False
    board_settings = Mock()
    board_settings.boards = [{"device_type": device_type, "notes_wide": notes_wide, "notes_tall": notes_tall}]
    ss.get_board_settings.return_value = board_settings
    return ss


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_board_client():
    """Mock board client."""
    with patch("src.api_server._get_board_client") as mock:
        client = Mock()
        client.send_characters.return_value = (True, True)
        client.test_connection.return_value = True
        client.clear_cache.return_value = None
        client.get_cache_status.return_value = {
            "has_cached_text": False,
            "has_cached_characters": False,
            "skip_unchanged_enabled": True,
            "cached_text_preview": None,
        }
        mock.return_value = client
        yield client


class TestDebugBlank:
    """Tests for /debug/blank endpoint."""

    def test_blank_board_success(self, client, mock_board_client):
        """Test blanking the board successfully."""
        response = client.post("/debug/blank")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "blanked" in data["message"].lower()

        # Verify send_characters was called with blank array
        mock_board_client.send_characters.assert_called_once()
        args = mock_board_client.send_characters.call_args
        assert args[0][0] == [[0] * 22 for _ in range(6)]
        assert args[1]["force"] is True

    def test_blank_board_no_client(self, client):
        """Test blanking board when client not configured."""
        with patch("src.api_server._get_board_client", return_value=None):
            response = client.post("/debug/blank")
            assert response.status_code == 400
            assert "not configured" in response.json()["detail"].lower()

    # --- geometry tests: blank array must be sized per board type ---

    def test_blank_flagship_grid_size(self, client, mock_board_client):
        """Flagship board: blank produces a 6×22 array of zeros."""
        with patch("src.api_server.get_settings_service", return_value=_mock_ss("flagship")):
            response = client.post("/debug/blank")
        assert response.status_code == 200
        args = mock_board_client.send_characters.call_args
        assert args[0][0] == [[0] * 22 for _ in range(6)]

    def test_blank_note_grid_size(self, client, mock_board_client):
        """Note board: blank produces a 3×15 array of zeros."""
        with patch("src.api_server.get_settings_service", return_value=_mock_ss("note")):
            response = client.post("/debug/blank")
        assert response.status_code == 200
        args = mock_board_client.send_characters.call_args
        assert args[0][0] == [[0] * 15 for _ in range(3)]

    def test_blank_note_array_2x2_grid_size(self, client, mock_board_client):
        """Note-array 2×2: blank produces a 6×30 array of zeros."""
        with patch(
            "src.api_server.get_settings_service",
            return_value=_mock_ss("note_array", notes_wide=2, notes_tall=2),
        ):
            response = client.post("/debug/blank")
        assert response.status_code == 200
        args = mock_board_client.send_characters.call_args
        assert args[0][0] == [[0] * 30 for _ in range(6)]


class TestDebugFill:
    """Tests for /debug/fill endpoint."""

    def test_fill_board_success(self, client, mock_board_client):
        """Test filling the board with a character."""
        response = client.post("/debug/fill", json={"character_code": 63})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "63" in data["message"]

        # Verify send_characters was called with fill array
        mock_board_client.send_characters.assert_called_once()
        args = mock_board_client.send_characters.call_args
        assert args[0][0] == [[63] * 22 for _ in range(6)]

    def test_fill_board_invalid_code(self, client, mock_board_client):
        """Test filling board with invalid character code."""
        # Code too high
        response = client.post("/debug/fill", json={"character_code": 72})
        assert response.status_code == 400
        assert "0-71" in response.json()["detail"]

        # Code negative
        response = client.post("/debug/fill", json={"character_code": -1})
        assert response.status_code == 400

        # Missing code
        response = client.post("/debug/fill", json={})
        assert response.status_code == 400

    def test_fill_board_no_client(self, client):
        """Test filling board when client not configured."""
        with patch("src.api_server._get_board_client", return_value=None):
            response = client.post("/debug/fill", json={"character_code": 63})
            assert response.status_code == 400

    # --- geometry tests: grid must be sized per board type ---

    def test_fill_flagship_grid_size(self, client, mock_board_client):
        """Flagship board: fill produces a 6×22 grid."""
        with patch("src.api_server.get_settings_service", return_value=_mock_ss("flagship")):
            response = client.post("/debug/fill", json={"character_code": 63})
        assert response.status_code == 200
        args = mock_board_client.send_characters.call_args
        assert args[0][0] == [[63] * 22 for _ in range(6)]

    def test_fill_note_grid_size(self, client, mock_board_client):
        """Note board: fill produces a 3×15 grid."""
        with patch("src.api_server.get_settings_service", return_value=_mock_ss("note")):
            response = client.post("/debug/fill", json={"character_code": 5})
        assert response.status_code == 200
        args = mock_board_client.send_characters.call_args
        assert args[0][0] == [[5] * 15 for _ in range(3)]

    def test_fill_note_array_2wide_grid_size(self, client, mock_board_client):
        """Note-array 2-wide: fill produces a 3×30 grid."""
        with patch(
            "src.api_server.get_settings_service",
            return_value=_mock_ss("note_array", notes_wide=2, notes_tall=1),
        ):
            response = client.post("/debug/fill", json={"character_code": 1})
        assert response.status_code == 200
        args = mock_board_client.send_characters.call_args
        assert args[0][0] == [[1] * 30 for _ in range(3)]

    def test_fill_note_array_2tall_grid_size(self, client, mock_board_client):
        """Note-array 2-tall: fill produces a 6×15 grid."""
        with patch(
            "src.api_server.get_settings_service",
            return_value=_mock_ss("note_array", notes_wide=1, notes_tall=2),
        ):
            response = client.post("/debug/fill", json={"character_code": 0})
        assert response.status_code == 200
        args = mock_board_client.send_characters.call_args
        assert args[0][0] == [[0] * 15 for _ in range(6)]


class TestDebugInfo:
    """Tests for /debug/info endpoint."""

    def test_show_debug_info_success(self, client, mock_board_client):
        """Test showing debug info on board."""
        response = client.post("/debug/info")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "debug_info" in data

        # Verify debug_info contains expected content
        debug_text = data["debug_info"]
        assert "DEBUG INFO" in debug_text
        assert "BOARD:" in debug_text
        assert "SERVER:" in debug_text

        # Verify send_characters was called
        mock_board_client.send_characters.assert_called_once()

    def test_show_debug_info_no_client(self, client):
        """Test showing debug info when client not configured."""
        with patch("src.api_server._get_board_client", return_value=None):
            response = client.post("/debug/info")
            assert response.status_code == 400

    # --- geometry tests: info should not crash for any board type ---

    def test_info_sends_to_board_flagship(self, client, mock_board_client):
        """Flagship board: /debug/info succeeds without crashing."""
        with patch("src.api_server.get_settings_service", return_value=_mock_ss("flagship")):
            response = client.post("/debug/info")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_info_note_array_does_not_crash(self, client, mock_board_client):
        """Note-array board: /debug/info does not crash and returns success."""
        with patch(
            "src.api_server.get_settings_service",
            return_value=_mock_ss("note_array", notes_wide=2, notes_tall=1),
        ):
            response = client.post("/debug/info")
        assert response.status_code == 200
        assert response.json()["status"] == "success"


class TestDebugTestConnection:
    """Tests for /debug/test-connection endpoint."""

    def test_connection_success(self, client, mock_board_client):
        """Test successful connection test."""
        mock_board_client.test_connection.return_value = True

        response = client.post("/debug/test-connection")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["connected"] is True
        assert "latency_ms" in data
        assert isinstance(data["latency_ms"], int)

    def test_connection_failure(self, client, mock_board_client):
        """Test failed connection test."""
        mock_board_client.test_connection.return_value = False

        response = client.post("/debug/test-connection")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["connected"] is False

    def test_connection_no_client(self, client):
        """Test connection test when client not configured."""
        with patch("src.api_server._get_board_client", return_value=None):
            response = client.post("/debug/test-connection")
            assert response.status_code == 400


class TestDebugClearCache:
    """Tests for /debug/clear-cache endpoint."""

    def test_clear_cache_success(self, client, mock_board_client):
        """Test clearing cache successfully."""
        response = client.post("/debug/clear-cache")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "cache cleared" in data["message"].lower()

        # Verify clear_cache was called
        mock_board_client.clear_cache.assert_called_once()

    def test_clear_cache_no_client(self, client):
        """Test clearing cache when client not configured."""
        with patch("src.api_server._get_board_client", return_value=None):
            response = client.post("/debug/clear-cache")
            assert response.status_code == 400


class TestDebugCacheStatus:
    """Tests for /debug/cache-status endpoint."""

    def test_get_cache_status_success(self, client, mock_board_client):
        """Test getting cache status."""
        response = client.get("/debug/cache-status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "cache" in data

        cache = data["cache"]
        assert "has_cached_text" in cache
        assert "has_cached_characters" in cache
        assert "skip_unchanged_enabled" in cache

        # Verify get_cache_status was called
        mock_board_client.get_cache_status.assert_called_once()

    def test_get_cache_status_no_client(self, client):
        """Test getting cache status when client not configured."""
        with patch("src.api_server._get_board_client", return_value=None):
            response = client.get("/debug/cache-status")
            assert response.status_code == 400


class TestDebugSystemInfo:
    """Tests for /debug/system-info endpoint."""

    def test_get_system_info_success(self, client, mock_board_client):
        """Test getting system info."""
        response = client.get("/debug/system-info")
        assert response.status_code == 200
        data = response.json()

        # Verify all expected fields are present
        assert "board_ip" in data
        assert "server_ip" in data
        assert "uptime_seconds" in data or data["uptime_seconds"] is None
        assert "uptime_formatted" in data
        assert "connection_mode" in data
        assert "version" in data
        assert "timestamp" in data
        assert "cache_status" in data or data["cache_status"] is None
        assert "board_configured" in data
        assert "service_running" in data

    def test_get_system_info_structure(self, client, mock_board_client):
        """Test system info response structure."""
        response = client.get("/debug/system-info")
        assert response.status_code == 200
        data = response.json()

        # Verify types
        assert isinstance(data["uptime_formatted"], str)
        assert isinstance(data["connection_mode"], str)
        assert isinstance(data["version"], str)
        assert isinstance(data["board_configured"], bool)
        assert isinstance(data["service_running"], bool)


class TestDebugUtilityFunctions:
    """Tests for debug utility functions."""

    def test_get_server_ip(self):
        """Test server IP detection."""
        from src.api_server import _get_server_ip

        ip = _get_server_ip()
        assert isinstance(ip, str)
        # Should be either a valid IP or "unknown"
        assert ip == "unknown" or len(ip.split(".")) == 4

    def test_format_uptime(self):
        """Test uptime formatting."""
        from src.api_server import _format_uptime

        # Test None
        assert _format_uptime(None) == "not running"

        # Test seconds only
        assert _format_uptime(30) == "0m"

        # Test minutes
        assert _format_uptime(120) == "2m"

        # Test hours
        assert _format_uptime(3661) == "1h 1m"

        # Test days
        assert _format_uptime(90061) == "1d 1h 1m"

    def test_get_service_uptime(self):
        """Test service uptime calculation."""
        from src.api_server import _get_service_uptime

        # When service not started
        with patch("src.api_server._service_start_time", None):
            assert _get_service_uptime() is None

        # When service started
        import time

        start_time = time.time() - 100
        with patch("src.api_server._service_start_time", start_time):
            uptime = _get_service_uptime()
            assert uptime is not None
            assert 99 <= uptime <= 101  # Allow small variation
