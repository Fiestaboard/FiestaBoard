"""Tests for POST /settings/board/{board_id}/detect-size endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_board_dict(
    board_id: str = "board-1",
    device_type: str = "flagship",
    api_mode: str = "local",
    local_api_key: str = "lk",
    host: str = "192.168.0.1",
    cloud_key: str = "",
    note_array_token: str = "",
    notes_wide: int = 1,
    notes_tall: int = 1,
) -> dict:
    return {
        "id": board_id,
        "device_type": device_type,
        "api_mode": api_mode,
        "local_api_key": local_api_key,
        "host": host,
        "port": 7000,
        "cloud_key": cloud_key,
        "note_array_token": note_array_token,
        "notes_wide": notes_wide,
        "notes_tall": notes_tall,
    }


def _board_settings_mock(boards: list[dict]):
    """Return a mock BoardSettings exposing the given boards list."""
    bs = MagicMock()
    bs.boards = boards
    return bs


# ---------------------------------------------------------------------------
# Success cases — one per api_mode / device family
# ---------------------------------------------------------------------------


class TestDetectSizeSuccess:
    """Endpoint returns the classification of the live grid for each transport."""

    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.read_current_message")
    def test_local_flagship_6x22(self, mock_read, mock_ss, client):
        """Local API, flagship 6×22 grid → device_type flagship."""
        mock_ss.return_value.get_board_settings.return_value = _board_settings_mock(
            [_make_board_dict(api_mode="local")]
        )
        mock_read.return_value = [[0] * 22 for _ in range(6)]

        resp = client.post("/settings/board/board-1/detect-size")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_type"] == "flagship"
        assert data["rows"] == 6
        assert data["cols"] == 22
        assert "notes_wide" not in data

    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.read_current_message")
    def test_cloud_note_3x15(self, mock_read, mock_ss, client):
        """Cloud API, Note 3×15 grid → device_type note (classified from the grid)."""
        mock_ss.return_value.get_board_settings.return_value = _board_settings_mock(
            [_make_board_dict(api_mode="cloud", cloud_key="ck", local_api_key="", host="")]
        )
        mock_read.return_value = [[0] * 15 for _ in range(3)]

        resp = client.post("/settings/board/board-1/detect-size")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_type"] == "note"
        assert data["rows"] == 3
        assert data["cols"] == 15

    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.read_current_message")
    def test_note_array_6x30_2x2_grid(self, mock_read, mock_ss, client):
        """Note-array board, 6×30 grid → note_array 2×2, preset '2×2 grid'."""
        mock_ss.return_value.get_board_settings.return_value = _board_settings_mock(
            [
                _make_board_dict(
                    device_type="note_array",
                    api_mode="cloud",
                    note_array_token="tok-abc",
                    notes_wide=2,
                    notes_tall=2,
                    local_api_key="tok-abc",
                    host="",
                )
            ]
        )
        mock_read.return_value = [[0] * 30 for _ in range(6)]

        resp = client.post("/settings/board/board-1/detect-size")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_type"] == "note_array"
        assert data["notes_wide"] == 2
        assert data["notes_tall"] == 2
        assert data["matched_preset"] == "2×2 grid"
        assert data["rows"] == 6
        assert data["cols"] == 30

    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.read_current_message")
    def test_note_array_3x60_4_side_by_side(self, mock_read, mock_ss, client):
        """Note-array board, 3×60 grid → note_array 4×1, preset '4 side-by-side'."""
        mock_ss.return_value.get_board_settings.return_value = _board_settings_mock(
            [
                _make_board_dict(
                    device_type="note_array",
                    api_mode="cloud",
                    note_array_token="tok-abc",
                    notes_wide=4,
                    notes_tall=1,
                    local_api_key="tok-abc",
                    host="",
                )
            ]
        )
        mock_read.return_value = [[0] * 60 for _ in range(3)]

        resp = client.post("/settings/board/board-1/detect-size")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_type"] == "note_array"
        assert data["notes_wide"] == 4
        assert data["notes_tall"] == 1
        assert data["matched_preset"] == "4 side-by-side"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestDetectSizeErrors:
    """Endpoint returns structured errors for each failure mode."""

    @patch("src.api_server.get_settings_service")
    def test_board_not_found_404(self, mock_ss, client):
        """Unknown board_id → 404."""
        mock_ss.return_value.get_board_settings.return_value = _board_settings_mock([])

        resp = client.post("/settings/board/nonexistent/detect-size")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @patch("src.api_server.get_settings_service")
    def test_board_not_configured_400(self, mock_ss, client):
        """Board exists but has no credentials → 400."""
        mock_ss.return_value.get_board_settings.return_value = _board_settings_mock(
            [_make_board_dict(local_api_key="", host="")]
        )

        resp = client.post("/settings/board/board-1/detect-size")
        assert resp.status_code == 400
        assert "not configured" in resp.json()["detail"].lower()

    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.read_current_message")
    def test_board_unreachable_422(self, mock_read, mock_ss, client):
        """Board configured but read returns None (unreachable/blank) → 422."""
        mock_ss.return_value.get_board_settings.return_value = _board_settings_mock([_make_board_dict()])
        mock_read.return_value = None

        resp = client.post("/settings/board/board-1/detect-size")
        assert resp.status_code == 422
        assert "no layout" in resp.json()["detail"].lower()

    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.read_current_message")
    def test_unclassifiable_grid_422(self, mock_read, mock_ss, client):
        """Board returns a 5×15 grid (5 % 3 != 0) → 422 unclassifiable."""
        mock_ss.return_value.get_board_settings.return_value = _board_settings_mock([_make_board_dict()])
        mock_read.return_value = [[0] * 15 for _ in range(5)]

        resp = client.post("/settings/board/board-1/detect-size")
        assert resp.status_code == 422
        assert "unclassifiable" in resp.json()["detail"].lower()


class TestDetectSizeLocalArrays:
    """Local-mode arrays define their own shape — detection is cloud-only."""

    @staticmethod
    def _local_array_board(tiles):
        board = _make_board_dict(
            device_type="note_array",
            api_mode="local",
            local_api_key="",
            host="",
            notes_wide=2,
            notes_tall=1,
        )
        board["tiles"] = tiles
        return board

    @patch("src.api_server.get_settings_service")
    def test_local_tiles_array_rejected_400(self, mock_ss, client):
        """An array driven by saved tiles cannot be auto-detected."""
        tiles = [
            {"row": 0, "col": 0, "host": "192.168.0.10", "port": 7000, "local_api_key": "k", "enabled": True},
            {"row": 0, "col": 1, "host": "192.168.0.11", "port": 7000, "local_api_key": "k", "enabled": True},
        ]
        mock_ss.return_value.get_board_settings.return_value = _board_settings_mock([self._local_array_board(tiles)])

        resp = client.post("/settings/board/board-1/detect-size")

        assert resp.status_code == 400
        assert "local-mode note arrays" in resp.json()["detail"]

    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.read_current_message")
    def test_token_fallback_array_still_detects_via_cloud(self, mock_read, mock_ss, client):
        """api_mode 'local' with NO tiles drives via the cloud token — detect keeps working."""
        board = self._local_array_board(tiles=[])
        board["note_array_token"] = "tok"
        mock_ss.return_value.get_board_settings.return_value = _board_settings_mock([board])
        mock_read.return_value = [[0] * 30 for _ in range(3)]

        resp = client.post("/settings/board/board-1/detect-size")

        assert resp.status_code == 200
        assert resp.json()["device_type"] == "note_array"
        assert resp.json()["notes_wide"] == 2
