"""Tests for the FiestaPanel API endpoints."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.panels.models import Panel
from src.panels.service import PanelService
from src.panels.storage import PanelStorage
from src.virtual_board_client import VirtualBoardClient


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def mock_panel_service():
    with patch("src.api_server.get_panel_service") as mock:
        service = Mock()
        mock.return_value = service
        yield service


def _panel(**overrides):
    defaults = {"name": "Living Room TV", "board_id": "vboard-1"}
    defaults.update(overrides)
    return Panel(**defaults)


class TestPanelCrudEndpoints:
    def test_list_panels(self, client, mock_panel_service):
        """GET /panels returns panels with board info attached."""
        mock_panel_service.list_panels.return_value = [_panel()]
        with patch("src.api_server._find_board") as find_board:
            find_board.return_value = {"id": "vboard-1", "device_type": "flagship"}
            response = client.get("/panels")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["panels"][0]["device_type"] == "flagship"
        assert data["panels"][0]["board_missing"] is False

    def test_list_panels_reports_orphaned_board(self, client, mock_panel_service):
        """A panel whose virtual board was deleted reports board_missing."""
        mock_panel_service.list_panels.return_value = [_panel()]
        with patch("src.api_server._find_board", return_value=None):
            response = client.get("/panels")
        assert response.status_code == 200
        assert response.json()["panels"][0]["board_missing"] is True

    def test_patch_unknown_panel_404s(self, client, mock_panel_service):
        mock_panel_service.update_panel.return_value = None
        response = client.patch("/panels/nope", json={"name": "X"})
        assert response.status_code == 404

    def test_patch_updates_panel(self, client, mock_panel_service):
        mock_panel_service.update_panel.return_value = _panel(name="Bedroom TV")
        response = client.patch("/panels/abc", json={"name": "Bedroom TV"})
        assert response.status_code == 200
        assert response.json()["panel"]["name"] == "Bedroom TV"

    def test_delete_unknown_panel_404s(self, client, mock_panel_service):
        mock_panel_service.delete_panel.return_value = None
        response = client.delete("/panels/nope")
        assert response.status_code == 404


class TestPublicPanelEndpoints:
    def test_get_panel_returns_board_geometry(self, client, mock_panel_service):
        mock_panel_service.get_panel.return_value = _panel()
        board = {
            "id": "vboard-1",
            "device_type": "note",
            "board_color": "white",
            "api_mode": "virtual",
        }
        with patch("src.api_server._find_board", return_value=board):
            response = client.get("/panel/abc123def456")
        assert response.status_code == 200
        data = response.json()
        assert (data["rows"], data["cols"]) == (3, 15)
        assert data["board_color"] == "white"
        assert data["board_missing"] is False

    def test_get_panel_unknown_404s_with_stable_detail(self, client, mock_panel_service):
        mock_panel_service.get_panel.return_value = None
        response = client.get("/panel/nope")
        assert response.status_code == 404
        assert response.json()["detail"] == "Panel not found"

    def test_get_panel_orphaned_board(self, client, mock_panel_service):
        mock_panel_service.get_panel.return_value = _panel()
        with patch("src.api_server._find_board", return_value=None):
            response = client.get("/panel/abc123def456")
        assert response.status_code == 200
        data = response.json()
        assert data["board_missing"] is True
        assert data["rows"] is None

    def test_frame_returns_sent_grid(self, client, mock_panel_service):
        mock_panel_service.get_panel.return_value = _panel()
        vclient = VirtualBoardClient(device_type="note")
        grid = [[7] * 15 for _ in range(3)]
        vclient.send_characters(grid)
        board = {"id": "vboard-1", "device_type": "note", "api_mode": "virtual"}
        display = Mock()
        display.get_board_client.return_value = vclient
        with (
            patch("src.api_server._find_board", return_value=board),
            patch("src.api_server.get_service", return_value=display),
        ):
            response = client.get("/panel/abc123def456/frame")
        assert response.status_code == 200
        data = response.json()
        assert data["characters"] == grid
        assert (data["rows"], data["cols"]) == (3, 15)
        assert data["updated_at"] is not None
        assert isinstance(data["message"], str)

    def test_frame_empty_board_returns_nulls_with_dims(self, client, mock_panel_service):
        mock_panel_service.get_panel.return_value = _panel()
        vclient = VirtualBoardClient(device_type="flagship")
        board = {"id": "vboard-1", "device_type": "flagship", "api_mode": "virtual"}
        display = Mock()
        display.get_board_client.return_value = vclient
        with (
            patch("src.api_server._find_board", return_value=board),
            patch("src.api_server.get_service", return_value=display),
        ):
            response = client.get("/panel/abc123def456/frame")
        assert response.status_code == 200
        data = response.json()
        assert data["characters"] is None
        assert data["message"] is None
        assert (data["rows"], data["cols"]) == (6, 22)
        assert data["updated_at"] is None

    def test_frame_never_http_reads_a_non_virtual_client(self, client, mock_panel_service):
        """A panel misconfigured onto a physical board must not trigger live reads."""
        mock_panel_service.get_panel.return_value = _panel()
        board = {"id": "vboard-1", "device_type": "flagship", "api_mode": "local"}
        physical = Mock(spec=["read_current_message", "_last_characters"])
        physical._last_characters = None
        display = Mock()
        display.get_board_client.return_value = physical
        with (
            patch("src.api_server._find_board", return_value=board),
            patch("src.api_server.get_service", return_value=display),
        ):
            response = client.get("/panel/abc123def456/frame")
        assert response.status_code == 200
        physical.read_current_message.assert_not_called()


class TestPanelOrchestration:
    """POST/DELETE co-manage the virtual board through the settings service."""

    def _fake_settings_service(self):
        boards: list[dict] = []

        def add_board(board: dict):
            boards.append(dict(board))

        def remove_board(board_id: str):
            before = len(boards)
            boards[:] = [b for b in boards if b.get("id") != board_id]
            if len(boards) == before:
                raise ValueError(f"Board not found: {board_id}")

        return SimpleNamespace(
            add_board=add_board,
            remove_board=remove_board,
            boards=boards,
            get_board_settings=lambda: SimpleNamespace(boards=boards),
            get_primary_board_id=lambda: "primary-board",
        )

    def test_create_panel_creates_virtual_board(self, client, tmp_path):
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service()
        with (
            patch("src.api_server.get_panel_service", return_value=real_service),
            patch("src.api_server.get_settings_service", return_value=fake_settings),
            patch("src.api_server._reinitialize_board_clients") as reinit,
        ):
            response = client.post(
                "/panels",
                json={"name": "Hall TV", "device_type": "flagship", "screen_diagonal_inches": 65},
            )
        assert response.status_code == 200
        panel = response.json()["panel"]
        assert len(fake_settings.boards) == 1
        board = fake_settings.boards[0]
        assert board["api_mode"] == "virtual"
        assert board["device_type"] == "flagship"
        assert board["id"] == panel["board_id"]
        assert reinit.called
        assert real_service.get_panel(panel["id"]) is not None

    def test_delete_panel_removes_virtual_board(self, client, tmp_path):
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service()
        with (
            patch("src.api_server.get_panel_service", return_value=real_service),
            patch("src.api_server.get_settings_service", return_value=fake_settings),
            patch("src.api_server._reinitialize_board_clients"),
        ):
            created = client.post("/panels", json={"name": "Hall TV", "device_type": "note"}).json()["panel"]
            assert len(fake_settings.boards) == 1
            response = client.delete(f"/panels/{created['id']}")
        assert response.status_code == 200
        assert fake_settings.boards == []
        assert real_service.get_panel(created["id"]) is None

    def test_delete_tolerates_already_deleted_board(self, client, tmp_path):
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service()
        with (
            patch("src.api_server.get_panel_service", return_value=real_service),
            patch("src.api_server.get_settings_service", return_value=fake_settings),
            patch("src.api_server._reinitialize_board_clients"),
        ):
            created = client.post("/panels", json={"name": "Hall TV", "device_type": "note"}).json()["panel"]
            fake_settings.boards.clear()  # board deleted out-of-band
            response = client.delete(f"/panels/{created['id']}")
        assert response.status_code == 200
        assert real_service.get_panel(created["id"]) is None
