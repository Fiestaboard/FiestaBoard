"""Regression tests for issue #1888: schedule write endpoints must 404 on an
unknown board_id instead of persisting phantom entries (or silently dropping
the write) while reporting success.

Covers the four live write paths from the issue:
  - POST /schedules
  - PUT /schedules/{schedule_id}
  - PUT /schedules/default-page
  - PUT /schedules/enabled
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.pages.models import PageCreate
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Real page/schedule services on temp storage, mocked settings with one board."""
    page_service = PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))
    schedule_service = ScheduleService(storage=ScheduleStorage(storage_file=str(tmp_path / "schedules.json")))

    boards = [{"id": "board-flagship", "name": "Big Board", "device_type": "flagship"}]
    settings = MagicMock()
    settings.get_board_settings.return_value.boards = boards
    settings.get_primary_board_id.return_value = "board-flagship"
    settings.should_send_to_board.return_value = False

    monkeypatch.setattr("src.pages.service.get_page_service", lambda: page_service)
    monkeypatch.setattr("src.pages.service.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.api_server.get_page_service", lambda: page_service)
    monkeypatch.setattr("src.api_server.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.api_server.get_schedule_service", lambda: schedule_service)
    monkeypatch.setattr("src.api_server.get_service", lambda: None)
    monkeypatch.setattr("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False)

    page = page_service.create_page(PageCreate(name="Flag Page", type="template", template=["a"]))

    return {
        "settings": settings,
        "schedule_service": schedule_service,
        "page": page,
    }


def _payload(page_id, board_id):
    return {"page_id": page_id, "board_id": board_id, "start_time": "09:00", "end_time": "10:00"}


class TestCreateScheduleBoardValidation:
    """POST /schedules must reject an unknown board_id."""

    def test_create_with_unknown_board_404s(self, client, env):
        response = client.post("/schedules", json=_payload(env["page"].id, "board-ghost"))
        assert response.status_code == 404
        assert "board-ghost" in response.json()["detail"]

    def test_create_with_unknown_board_persists_nothing(self, client, env):
        client.post("/schedules", json=_payload(env["page"].id, "board-ghost"))
        assert env["schedule_service"].list_schedules(board_id="*") == []

    def test_create_with_known_board_accepted(self, client, env):
        response = client.post("/schedules", json=_payload(env["page"].id, "board-flagship"))
        assert response.status_code == 200

    def test_create_with_default_board_sentinel_accepted(self, client, env):
        """board_id="" is the legacy default-board sentinel and stays valid."""
        response = client.post("/schedules", json=_payload(env["page"].id, ""))
        assert response.status_code == 200


class TestUpdateScheduleBoardValidation:
    """PUT /schedules/{id} must not re-parent a schedule onto an unknown board."""

    def test_update_to_unknown_board_404s(self, client, env):
        created = client.post("/schedules", json=_payload(env["page"].id, "board-flagship")).json()
        response = client.put(f"/schedules/{created['id']}", json={"board_id": "board-ghost"})
        assert response.status_code == 404
        assert "board-ghost" in response.json()["detail"]

    def test_update_to_unknown_board_leaves_schedule_unchanged(self, client, env):
        created = client.post("/schedules", json=_payload(env["page"].id, "board-flagship")).json()
        client.put(f"/schedules/{created['id']}", json={"board_id": "board-ghost"})
        stored = env["schedule_service"].get_schedule(created["id"])
        assert stored.board_id == "board-flagship"

    def test_update_without_board_id_accepted(self, client, env):
        created = client.post("/schedules", json=_payload(env["page"].id, "board-flagship")).json()
        response = client.put(f"/schedules/{created['id']}", json={"start_time": "11:00"})
        assert response.status_code == 200


class TestDefaultPageBoardValidation:
    """PUT /schedules/default-page must reject an unknown board_id."""

    def test_set_default_page_with_unknown_board_404s(self, client, env):
        response = client.put(
            "/schedules/default-page",
            json={"page_id": env["page"].id, "board_id": "board-ghost"},
        )
        assert response.status_code == 404
        assert "board-ghost" in response.json()["detail"]

    def test_set_default_page_with_unknown_board_writes_nothing(self, client, env):
        client.put(
            "/schedules/default-page",
            json={"page_id": env["page"].id, "board_id": "board-ghost"},
        )
        assert env["schedule_service"].get_default_page(board_id="board-ghost") is None

    def test_set_default_page_with_known_board_accepted(self, client, env):
        response = client.put(
            "/schedules/default-page",
            json={"page_id": env["page"].id, "board_id": "board-flagship"},
        )
        assert response.status_code == 200

    def test_set_default_page_without_board_accepted(self, client, env):
        response = client.put("/schedules/default-page", json={"page_id": env["page"].id})
        assert response.status_code == 200


class TestScheduleEnabledBoardValidation:
    """PUT /schedules/enabled must reject an unknown board_id instead of
    reporting success for a write that never happened."""

    def test_set_enabled_with_unknown_board_404s(self, client, env):
        response = client.put("/schedules/enabled", json={"enabled": True, "board_id": "board-ghost"})
        assert response.status_code == 404
        assert "board-ghost" in response.json()["detail"]

    def test_set_enabled_with_unknown_board_writes_nothing(self, client, env):
        client.put("/schedules/enabled", json={"enabled": True, "board_id": "board-ghost"})
        env["settings"].set_schedule_enabled.assert_not_called()

    def test_set_enabled_with_known_board_accepted(self, client, env):
        response = client.put("/schedules/enabled", json={"enabled": True, "board_id": "board-flagship"})
        assert response.status_code == 200
        env["settings"].set_schedule_enabled.assert_called_once_with(True, board_id="board-flagship")

    def test_set_enabled_without_board_accepted(self, client, env):
        response = client.put("/schedules/enabled", json={"enabled": False})
        assert response.status_code == 200
