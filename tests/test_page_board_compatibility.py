"""Tests for page<->board size compatibility enforcement (issue #1245).

Covers the check_ref_board_compatibility() service helper plus the API write
paths that enforce it: PUT /settings/active-page and POST/PUT /schedules.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.collections.models import CollectionCreate
from src.collections.service import CollectionService
from src.collections.storage import CollectionStorage
from src.pages.models import PageCreate
from src.pages.service import PageService, check_ref_board_compatibility
from src.pages.storage import PageStorage
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Real page/collection/schedule services on temp storage, mocked settings."""
    page_service = PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))
    collection_service = CollectionService(storage=CollectionStorage(storage_file=str(tmp_path / "collections.json")))
    schedule_service = ScheduleService(storage=ScheduleStorage(storage_file=str(tmp_path / "schedules.json")))

    boards = [
        {"id": "board-flagship", "name": "Big Board", "device_type": "flagship"},
        {"id": "board-note", "name": "Small Board", "device_type": "note"},
    ]
    settings = MagicMock()
    settings.get_board_settings.return_value.boards = boards
    settings.get_primary_board_id.return_value = "board-flagship"
    settings.should_send_to_board.return_value = False

    monkeypatch.setattr("src.pages.service.get_page_service", lambda: page_service)
    monkeypatch.setattr("src.pages.service.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.collections.service.get_collection_service", lambda: collection_service)
    monkeypatch.setattr("src.api_server.get_page_service", lambda: page_service)
    monkeypatch.setattr("src.api_server.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.api_server.get_collection_service", lambda: collection_service)
    monkeypatch.setattr("src.api_server.get_schedule_service", lambda: schedule_service)
    monkeypatch.setattr("src.api_server.get_service", lambda: None)
    monkeypatch.setattr("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False)

    flagship_page = page_service.create_page(PageCreate(name="Flag Page", type="template", template=["a"]))
    note_page = page_service.create_page(
        PageCreate(name="Note Page", type="template", device_type="note", template=["a"])
    )
    mixed = collection_service.create_collection(
        CollectionCreate(name="Mixed", page_ids=[flagship_page.id, note_page.id])
    )
    all_note = collection_service.create_collection(CollectionCreate(name="All Note", page_ids=[note_page.id]))

    return {
        "settings": settings,
        "page_service": page_service,
        "flagship_page": flagship_page,
        "note_page": note_page,
        "mixed_collection": mixed,
        "all_note_collection": all_note,
    }


class TestCheckRefBoardCompatibility:
    """Direct tests of the service-layer helper."""

    def test_compatible_page(self, env):
        result = check_ref_board_compatibility(env["flagship_page"].id, "board-flagship")
        assert result.ok is True
        assert result.warnings == []

    def test_incompatible_page(self, env):
        result = check_ref_board_compatibility(env["note_page"].id, "board-flagship")
        assert result.ok is False
        assert "not compatible" in result.error

    def test_none_ref_passes(self, env):
        result = check_ref_board_compatibility(None, "board-flagship")
        assert result.ok is True

    def test_collection_mixed_warns_with_member_names(self, env):
        result = check_ref_board_compatibility(env["mixed_collection"].id, "board-flagship")
        assert result.ok is True
        assert len(result.warnings) == 1
        assert "Note Page" in result.warnings[0]

    def test_collection_none_fit_blocked(self, env):
        result = check_ref_board_compatibility(env["all_note_collection"].id, "board-flagship")
        assert result.ok is False

    def test_collection_all_fit_no_warnings(self, env):
        result = check_ref_board_compatibility(env["all_note_collection"].id, "board-note")
        assert result.ok is True
        assert result.warnings == []


class TestActivePageCompatibility:
    """PUT /settings/active-page enforcement."""

    def test_compatible_page_accepted(self, client, env):
        response = client.put("/settings/active-page", json={"page_id": env["flagship_page"].id})
        assert response.status_code == 200
        env["settings"].set_active_page_id.assert_called_once()

    def test_incompatible_page_rejected_400(self, client, env):
        response = client.put("/settings/active-page", json={"page_id": env["note_page"].id})
        assert response.status_code == 400
        assert "not compatible" in response.json()["detail"]
        env["settings"].set_active_page_id.assert_not_called()

    def test_board_id_in_body_targets_that_board(self, client, env):
        response = client.put("/settings/active-page", json={"page_id": env["note_page"].id, "board_id": "board-note"})
        assert response.status_code == 200

    def test_collection_mixed_allowed_with_warnings(self, client, env):
        response = client.put("/settings/active-page", json={"page_id": env["mixed_collection"].id})
        assert response.status_code == 200
        warnings = response.json().get("warnings", [])
        assert len(warnings) == 1
        assert "Note Page" in warnings[0]

    def test_collection_none_fit_rejected_400(self, client, env):
        response = client.put("/settings/active-page", json={"page_id": env["all_note_collection"].id})
        assert response.status_code == 400

    def test_clearing_active_page_unaffected(self, client, env):
        response = client.put("/settings/active-page", json={"page_id": None})
        assert response.status_code == 200


class TestScheduleRoutesCompatibility:
    """POST/PUT /schedules enforcement + warnings passthrough."""

    @staticmethod
    def _payload(page_id, board_id="board-flagship"):
        return {"page_id": page_id, "board_id": board_id, "start_time": "09:00", "end_time": "10:00"}

    def test_create_incompatible_rejected_400(self, client, env):
        response = client.post("/schedules", json=self._payload(env["note_page"].id))
        assert response.status_code == 400
        assert "not compatible" in response.json()["detail"]

    def test_create_compatible_accepted(self, client, env):
        response = client.post("/schedules", json=self._payload(env["flagship_page"].id))
        assert response.status_code == 200

    def test_create_collection_mixed_returns_warnings(self, client, env):
        response = client.post("/schedules", json=self._payload(env["mixed_collection"].id))
        assert response.status_code == 200
        warnings = response.json().get("warnings", [])
        assert len(warnings) == 1
        assert "Note Page" in warnings[0]

    def test_update_to_incompatible_rejected_400(self, client, env):
        created = client.post("/schedules", json=self._payload(env["flagship_page"].id)).json()
        response = client.put(f"/schedules/{created['id']}", json={"page_id": env["note_page"].id})
        assert response.status_code == 400

    def test_update_collection_mixed_returns_warnings(self, client, env):
        created = client.post("/schedules", json=self._payload(env["flagship_page"].id)).json()
        response = client.put(f"/schedules/{created['id']}", json={"page_id": env["mixed_collection"].id})
        assert response.status_code == 200
        warnings = response.json().get("warnings", [])
        assert len(warnings) == 1
