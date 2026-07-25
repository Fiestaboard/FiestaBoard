"""Tests for editor device/size retarget + stale-reference detection (issue #1250).

Covers:
- ``PageUpdate`` accepting ``device_type`` (retarget an existing page)
- ``PageService.update_page`` re-validating the retargeted page
- ``find_incompatible_references()`` scanning schedules / active pages /
  collections for boards the page no longer fits
- ``PUT /pages/{page_id}`` returning ``incompatible_references`` when the
  page's size changed (warn-only: nothing is auto-removed)
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api_server import app
from src.collections.models import CollectionCreate
from src.collections.service import CollectionService
from src.collections.storage import CollectionStorage
from src.pages.models import PageCreate, PageUpdate, RowConfig
from src.pages.service import PageService, find_incompatible_references
from src.pages.storage import PageStorage
from src.schedules.models import ScheduleCreate
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
        {"id": "board-flagship", "name": "Kitchen", "device_type": "flagship"},
        {"id": "board-note", "name": "Office", "device_type": "note"},
    ]
    settings = MagicMock()
    settings.get_board_settings.return_value.boards = boards
    settings.get_primary_board_id.return_value = "board-flagship"
    settings.should_send_to_board.return_value = False
    active_by_board: dict[str, str] = {}
    settings.get_active_page_id.side_effect = lambda board_id=None: active_by_board.get(board_id)

    monkeypatch.setattr("src.pages.service.get_page_service", lambda: page_service)
    monkeypatch.setattr("src.pages.service.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.collections.service.get_collection_service", lambda: collection_service)
    monkeypatch.setattr("src.schedules.service.get_schedule_service", lambda: schedule_service)
    monkeypatch.setattr("src.schedules.service.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.api_server.get_page_service", lambda: page_service)
    monkeypatch.setattr("src.api_server.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.api_server.get_collection_service", lambda: collection_service)
    monkeypatch.setattr("src.api_server.get_schedule_service", lambda: schedule_service)
    monkeypatch.setattr("src.api_server.get_service", lambda: None)
    monkeypatch.setattr("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False)

    flagship_page = page_service.create_page(PageCreate(name="Flag Page", type="template", template=["a"]))

    return {
        "settings": settings,
        "active_by_board": active_by_board,
        "page_service": page_service,
        "collection_service": collection_service,
        "schedule_service": schedule_service,
        "flagship_page": flagship_page,
    }


def _schedule(env, page_ref, board_id="board-flagship"):
    return env["schedule_service"].create_schedule(
        ScheduleCreate(page_id=page_ref, board_id=board_id, start_time="09:00", end_time="10:00")
    )


class TestPageUpdateModel:
    def test_accepts_device_type(self):
        update = PageUpdate(device_type="note")
        assert update.device_type == "note"
        assert update.model_dump(exclude_unset=True) == {"device_type": "note"}

    def test_device_type_unset_by_default(self):
        assert "device_type" not in PageUpdate(name="x").model_dump(exclude_unset=True)

    def test_rejects_unknown_device_type(self):
        with pytest.raises(ValidationError):
            PageUpdate(device_type="jumbotron")


class TestUpdatePageRetarget:
    def test_retarget_flagship_to_note(self, env):
        page = env["flagship_page"]
        updated = env["page_service"].update_page(page.id, PageUpdate(device_type="note"))
        assert updated is not None
        assert updated.device_type == "note"
        # Reopening shows the new size
        assert env["page_service"].get_page(page.id).device_type == "note"

    def test_retarget_to_note_array_geometry(self, env):
        page = env["flagship_page"]
        updated = env["page_service"].update_page(
            page.id, PageUpdate(device_type="note_array", notes_wide=2, notes_tall=2)
        )
        assert updated.device_type == "note_array"
        assert (updated.notes_wide, updated.notes_tall) == (2, 2)

    def test_invalid_retarget_rejected(self, env):
        """A retarget that makes the page config invalid is blocked with ValueError."""
        composite = env["page_service"].create_page(
            PageCreate(
                name="Composite",
                type="composite",
                rows=[RowConfig(source="datetime", row_index=0, target_row=5)],
            )
        )
        with pytest.raises(ValueError):
            env["page_service"].update_page(composite.id, PageUpdate(device_type="note"))
        # Unchanged on disk
        assert env["page_service"].get_page(composite.id).device_type == "flagship"


class TestFindIncompatibleReferences:
    def test_schedule_reference_reported(self, env):
        page = env["flagship_page"]
        schedule = _schedule(env, page.id)
        retargeted = env["page_service"].update_page(page.id, PageUpdate(device_type="note"))
        refs = find_incompatible_references(retargeted)
        assert refs == [
            {
                "board_id": "board-flagship",
                "board_name": "Kitchen",
                "surface": "schedule",
                "schedule_id": schedule.id,
            }
        ]

    def test_active_page_reference_reported(self, env):
        page = env["flagship_page"]
        env["active_by_board"]["board-flagship"] = page.id
        retargeted = env["page_service"].update_page(page.id, PageUpdate(device_type="note"))
        refs = find_incompatible_references(retargeted)
        assert refs == [
            {
                "board_id": "board-flagship",
                "board_name": "Kitchen",
                "surface": "active_page",
                "schedule_id": None,
            }
        ]

    def test_collection_schedule_reference_reported(self, env):
        page = env["flagship_page"]
        other = env["page_service"].create_page(PageCreate(name="Other Flag", type="template", template=["b"]))
        collection = env["collection_service"].create_collection(
            CollectionCreate(name="Mixed", page_ids=[page.id, other.id])
        )
        schedule = _schedule(env, collection.id)
        retargeted = env["page_service"].update_page(page.id, PageUpdate(device_type="note"))
        refs = find_incompatible_references(retargeted)
        assert {
            "board_id": "board-flagship",
            "board_name": "Kitchen",
            "surface": "schedule",
            "schedule_id": schedule.id,
        } in refs

    def test_no_references_when_still_compatible(self, env):
        page = env["flagship_page"]
        _schedule(env, page.id)
        env["active_by_board"]["board-flagship"] = page.id
        assert find_incompatible_references(page) == []

    def test_compatible_board_references_not_reported(self, env):
        """Refs on a board the page still fits are not stale."""
        page = env["flagship_page"]
        env["active_by_board"]["board-flagship"] = page.id
        note_page = env["page_service"].create_page(
            PageCreate(name="Note Page", type="template", device_type="note", template=["n"])
        )
        env["active_by_board"]["board-note"] = note_page.id
        retargeted = env["page_service"].update_page(page.id, PageUpdate(device_type="note"))
        refs = find_incompatible_references(retargeted)
        # Only the flagship board's ref is stale; the note board references a
        # different page entirely.
        assert refs == [
            {
                "board_id": "board-flagship",
                "board_name": "Kitchen",
                "surface": "active_page",
                "schedule_id": None,
            }
        ]

    def test_other_pages_schedules_not_reported(self, env):
        page = env["flagship_page"]
        other = env["page_service"].create_page(PageCreate(name="Other", type="template", template=["b"]))
        _schedule(env, other.id)
        retargeted = env["page_service"].update_page(page.id, PageUpdate(device_type="note"))
        assert find_incompatible_references(retargeted) == []


class TestUpdatePageRoute:
    def test_size_change_returns_incompatible_references(self, client, env):
        page = env["flagship_page"]
        schedule = _schedule(env, page.id)
        response = client.put(f"/pages/{page.id}", json={"device_type": "note"})
        assert response.status_code == 200
        body = response.json()
        assert body["page"]["device_type"] == "note"
        assert body["incompatible_references"] == [
            {
                "board_id": "board-flagship",
                "board_name": "Kitchen",
                "surface": "schedule",
                "schedule_id": schedule.id,
            }
        ]

    def test_size_change_without_refs_returns_empty_list(self, client, env):
        page = env["flagship_page"]
        response = client.put(f"/pages/{page.id}", json={"device_type": "note"})
        assert response.status_code == 200
        assert response.json()["incompatible_references"] == []

    def test_no_size_change_omits_key(self, client, env):
        page = env["flagship_page"]
        _schedule(env, page.id)
        response = client.put(f"/pages/{page.id}", json={"name": "Renamed"})
        assert response.status_code == 200
        assert "incompatible_references" not in response.json()

    def test_references_not_mutated(self, client, env):
        """Warn-only: the stale schedule entry and active page are untouched."""
        page = env["flagship_page"]
        schedule = _schedule(env, page.id)
        env["active_by_board"]["board-flagship"] = page.id
        response = client.put(f"/pages/{page.id}", json={"device_type": "note"})
        assert response.status_code == 200
        remaining = env["schedule_service"].list_schedules(board_id="*")
        assert [s.id for s in remaining] == [schedule.id]
        env["settings"].set_active_page_id.assert_not_called()
