"""Tests for POST /settings/board/{board_id}/identify (local note-array identify flash)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.devices import NOTE_COLS, NOTE_ROWS


@pytest.fixture
def client():
    return TestClient(app)


def _tile(row=0, col=0, host=None, key="tile-key", enabled=True):
    return {
        "row": row,
        "col": col,
        "host": host or f"192.168.0.{10 + row * 8 + col}",
        "port": 7000,
        "local_api_key": key,
        "enabled": enabled,
    }


def _array_board(
    board_id="board-1", api_mode="local", tiles=None, notes_wide=2, notes_tall=1
):
    return {
        "id": board_id,
        "device_type": "note_array",
        "api_mode": api_mode,
        "local_api_key": "",
        "host": "",
        "cloud_key": "",
        "note_array_token": "",
        "notes_wide": notes_wide,
        "notes_tall": notes_tall,
        "tiles": tiles if tiles is not None else [_tile(0, 0), _tile(0, 1)],
    }


def _board_settings_mock(boards):
    bs = MagicMock()
    bs.boards = boards
    return bs


def _patch_settings(mock_ss, boards):
    mock_ss.return_value.get_board_settings.return_value = _board_settings_mock(boards)


class TestIdentifySuccess:
    @patch("src.api_server.get_service")
    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.send_characters", return_value=(True, True))
    def test_identify_single_tile(self, mock_send, mock_ss, mock_service, client):
        _patch_settings(mock_ss, [_array_board()])

        resp = client.post(
            "/settings/board/board-1/identify",
            json={"target": "tile", "row": 0, "col": 1},
        )

        assert resp.status_code == 200
        assert resp.json()["results"] == [{"row": 0, "col": 1, "success": True}]
        assert mock_send.call_count == 1
        pattern = mock_send.call_args.args[0]
        assert len(pattern) == NOTE_ROWS
        assert all(len(r) == NOTE_COLS for r in pattern)
        assert mock_send.call_args.kwargs["force"] is True

    @patch("src.api_server.get_service")
    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.send_characters", return_value=(True, True))
    def test_identify_all_flashes_every_configured_tile(
        self, mock_send, mock_ss, mock_service, client
    ):
        _patch_settings(mock_ss, [_array_board()])

        resp = client.post("/settings/board/board-1/identify", json={"target": "all"})

        assert resp.status_code == 200
        assert {(r["row"], r["col"]) for r in resp.json()["results"]} == {
            (0, 0),
            (0, 1),
        }
        assert mock_send.call_count == 2

    @patch("src.api_server.get_service")
    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.send_characters", return_value=(True, True))
    def test_identify_unsaved_override(self, mock_send, mock_ss, mock_service, client):
        """The assign dialog can identify a board before its tile is saved."""
        _patch_settings(mock_ss, [_array_board(tiles=[])])

        resp = client.post(
            "/settings/board/board-1/identify",
            json={
                "target": "tile",
                "row": 0,
                "col": 1,
                "host": "192.168.0.42",
                "local_api_key": "unsaved-key",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["results"] == [{"row": 0, "col": 1, "success": True}]

    @patch("src.api_server.get_service")
    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.send_characters", return_value=(True, True))
    def test_identify_invalidates_board_content(
        self, mock_send, mock_ss, mock_service, client
    ):
        _patch_settings(mock_ss, [_array_board()])
        service = MagicMock()
        mock_service.return_value = service

        client.post("/settings/board/board-1/identify", json={"target": "all"})

        service.invalidate_board_content.assert_called_once_with("board-1")

    @patch("src.api_server.get_service")
    @patch("src.api_server.get_settings_service")
    @patch("src.board_client.BoardClient.send_characters", return_value=(False, False))
    def test_tile_failure_reported_per_tile(
        self, mock_send, mock_ss, mock_service, client
    ):
        _patch_settings(mock_ss, [_array_board(tiles=[_tile(0, 0)])])

        resp = client.post("/settings/board/board-1/identify", json={"target": "all"})

        assert resp.status_code == 200
        assert resp.json()["results"] == [{"row": 0, "col": 0, "success": False}]


class TestIdentifyErrors:
    @patch("src.api_server.get_settings_service")
    def test_unknown_board_404(self, mock_ss, client):
        _patch_settings(mock_ss, [])
        resp = client.post("/settings/board/nope/identify", json={"target": "all"})
        assert resp.status_code == 404

    @patch("src.api_server.get_settings_service")
    def test_cloud_array_400(self, mock_ss, client):
        _patch_settings(mock_ss, [_array_board(api_mode="cloud")])
        resp = client.post("/settings/board/board-1/identify", json={"target": "all"})
        assert resp.status_code == 400

    @patch("src.api_server.get_settings_service")
    def test_non_array_400(self, mock_ss, client):
        board = _array_board()
        board["device_type"] = "flagship"
        _patch_settings(mock_ss, [board])
        resp = client.post("/settings/board/board-1/identify", json={"target": "all"})
        assert resp.status_code == 400

    @patch("src.api_server.get_settings_service")
    def test_bad_target_400(self, mock_ss, client):
        _patch_settings(mock_ss, [_array_board()])
        resp = client.post(
            "/settings/board/board-1/identify", json={"target": "everything"}
        )
        assert resp.status_code == 400

    @patch("src.api_server.get_settings_service")
    def test_tile_target_requires_row_col(self, mock_ss, client):
        _patch_settings(mock_ss, [_array_board()])
        resp = client.post("/settings/board/board-1/identify", json={"target": "tile"})
        assert resp.status_code == 400

    @patch("src.api_server.get_settings_service")
    def test_unknown_tile_400(self, mock_ss, client):
        _patch_settings(mock_ss, [_array_board()])
        resp = client.post(
            "/settings/board/board-1/identify",
            json={"target": "tile", "row": 0, "col": 7},
        )
        assert resp.status_code == 400

    @patch("src.api_server.get_settings_service")
    def test_no_configured_tiles_400(self, mock_ss, client):
        _patch_settings(mock_ss, [_array_board(tiles=[])])
        resp = client.post("/settings/board/board-1/identify", json={"target": "all"})
        assert resp.status_code == 400

    @patch("src.api_server.get_settings_service")
    def test_override_rejects_public_host(self, mock_ss, client):
        """SSRF guard: the credential override must stay on the local network."""
        _patch_settings(mock_ss, [_array_board(tiles=[])])
        resp = client.post(
            "/settings/board/board-1/identify",
            json={
                "target": "tile",
                "row": 0,
                "col": 0,
                "host": "8.8.8.8",
                "local_api_key": "k",
            },
        )
        assert resp.status_code == 400

    @patch("src.api_server.get_settings_service")
    def test_override_rejects_url_shaped_host(self, mock_ss, client):
        _patch_settings(mock_ss, [_array_board(tiles=[])])
        resp = client.post(
            "/settings/board/board-1/identify",
            json={
                "target": "tile",
                "row": 0,
                "col": 0,
                "host": "evil.com/path",
                "local_api_key": "k",
            },
        )
        assert resp.status_code == 400

    @patch("src.api_server.get_settings_service")
    def test_override_requires_row_col(self, mock_ss, client):
        _patch_settings(mock_ss, [_array_board(tiles=[])])
        resp = client.post(
            "/settings/board/board-1/identify",
            json={"target": "all", "host": "192.168.0.42", "local_api_key": "k"},
        )
        assert resp.status_code == 400
