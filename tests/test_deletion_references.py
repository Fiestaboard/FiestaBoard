"""Deletion must preserve references or refuse before changing stored content."""

import pytest
from fastapi.testclient import TestClient

from src.collections.models import CollectionCreate
from src.collections.service import get_collection_service
from src.config_manager import get_config_manager
from src.pages.models import PageCreate
from src.pages.service import get_page_service
from src.schedules.models import ScheduleEntry
from src.schedules.service import get_schedule_service
from src.settings.service import get_settings_service


@pytest.fixture
def content():
    settings = get_settings_service()
    settings.set_boards(
        [
            {"id": "primary", "name": "Main", "device_type": "flagship"},
            {"id": "secondary", "name": "Desk", "device_type": "note"},
            {"id": "third", "name": "Other", "device_type": "note"},
        ]
    )
    pages = get_page_service()
    primary = pages.create_page(PageCreate(name="Main", type="template", template=["Main"]))
    target = pages.create_page(PageCreate(name="Desk", type="template", device_type="note", template=["Desk"]))
    settings.set_active_page_id(primary.id, "primary")
    settings.set_active_page_id(target.id, "secondary")
    settings.set_active_page_id(target.id, "third")
    return pages, settings, primary, target


def test_delete_replaces_every_active_board_with_compatible_page(content):
    pages, settings, primary, target = content
    replacement = pages.create_page(PageCreate(name="Next", type="template", device_type="note", template=["Next"]))
    result = pages.delete_page(target.id)
    assert result.deleted
    assert settings.get_active_page_id("primary") == primary.id
    assert settings.get_active_page_id("secondary") == replacement.id
    assert settings.get_active_page_id("third") == replacement.id


def test_delete_creates_compatible_fallback_when_only_other_sizes_remain(content):
    pages, settings, primary, target = content
    pages.delete_page(target.id)
    replacement_id = settings.get_active_page_id("secondary")
    replacement = pages.get_page(replacement_id)
    assert replacement is not None
    assert replacement.device_type == "note"
    assert replacement.id != target.id
    assert settings.get_active_page_id("third") == replacement.id
    assert settings.get_active_page_id("primary") == primary.id


@pytest.mark.parametrize("kind", ["page", "collection"])
@pytest.mark.parametrize("dependency", ["schedule", "default", "silence", "silence_default"])
@pytest.mark.parametrize("prefix", ["/api", "/api/v1"])
def test_referenced_content_delete_returns_actionable_conflict_without_mutation(content, kind, dependency, prefix):
    from src.api_server import app
    from src.paths import get_data_dir

    _pages, _settings, _primary, target = content
    collection = get_collection_service().create_collection(CollectionCreate(name="Rotation", page_ids=[target.id]))
    ref = target.id if kind == "page" else collection.id
    # The collection membership is tested separately; isolate each dependency.
    if kind == "page":
        get_collection_service().storage.delete(collection.id)
    schedules = get_schedule_service().storage
    if dependency == "schedule":
        schedules.create(
            ScheduleEntry(page_id=ref, board_id="secondary", start_time="09:00", end_time="10:00", enabled=False)
        )
    elif dependency == "default":
        schedules.set_default_page_id(ref, "secondary")
    else:
        config = get_config_manager()
        if dependency == "silence":
            config.set_silence_schedule_for_board("secondary", {"page_id": ref, "mode": "page"})
        else:
            config.set_feature("silence_schedule", {"page_id": ref, "mode": "page"})
    before = {str(p): p.read_bytes() for p in get_data_dir().glob("*.json")}
    response = TestClient(app).delete(f"{prefix}/{kind}s/{ref}")
    assert response.status_code == 409, response.text
    assert dependency.split("_")[0] in response.json()["detail"].lower()
    assert ref in response.json()["detail"]
    assert {str(p): p.read_bytes() for p in get_data_dir().glob("*.json")} == before


def test_collection_member_deletion_is_refused_without_changing_membership(content):
    from src.api_server import app

    pages, settings, _primary, target = content
    collections = get_collection_service()
    collection = collections.create_collection(CollectionCreate(name="Rotation", page_ids=[target.id]))
    response = TestClient(app).delete(f"/api/v1/pages/{target.id}")
    assert response.status_code == 409
    assert collection.id in response.json()["detail"]
    assert collections.get_collection(collection.id).page_ids == [target.id]
    assert pages.get_page(target.id) is not None
    assert settings.get_active_page_id("secondary") == target.id


def test_pinned_collection_deletion_is_refused_on_secondary_board(content):
    from src.api_server import app

    _pages, settings, _primary, target = content
    collections = get_collection_service()
    collection = collections.create_collection(CollectionCreate(name="Rotation", page_ids=[target.id]))
    settings.set_active_page_id(collection.id, "secondary")
    response = TestClient(app).delete(f"/api/v1/collections/{collection.id}")
    assert response.status_code == 409
    assert "secondary" in response.json()["detail"]
    assert collections.get_collection(collection.id) is not None
    assert settings.get_active_page_id("secondary") == collection.id


def test_unreferenced_collection_deletes_and_keeps_member_pages(content):
    pages, _settings, _primary, target = content
    collections = get_collection_service()
    collection = collections.create_collection(CollectionCreate(name="Rotation", page_ids=[target.id]))
    assert collections.delete_collection(collection.id)
    assert collections.get_collection(collection.id) is None
    assert pages.get_page(target.id) is not None


@pytest.mark.parametrize(
    "geometry",
    [
        {"device_type": "note_array", "notes_wide": 2, "notes_tall": 2},
        {"device_type": "panel", "grid_rows": 8, "grid_cols": 16},
    ],
)
@pytest.mark.parametrize("last_page", [False, True])
def test_fallback_preserves_board_geometry(content, geometry, last_page):
    from src.devices import pages_compatible_with_board

    pages, settings, _primary, _target = content
    board = {"id": "custom-board", "name": "Custom", **geometry}
    if geometry["device_type"] == "panel":
        board["api_mode"] = "virtual"
    settings.set_boards([board])
    page = pages.create_page(PageCreate(name="Custom", type="template", template=["Hello"], **geometry))
    settings.set_active_page_id(page.id, "custom-board")
    if last_page:
        for other in pages.list_pages():
            if other.id != page.id:
                pages.storage.delete(other.id)
    pages.delete_page(page.id)
    replacement = pages.get_page(settings.get_active_page_id("custom-board"))
    assert replacement is not None
    assert pages_compatible_with_board(replacement, geometry)
    for key, value in geometry.items():
        assert getattr(replacement, key) == value
    if last_page:
        assert len(pages.list_pages()) == 1


@pytest.mark.parametrize("field", ["page_id", "revert_page_id"])
@pytest.mark.parametrize("expired", [False, True])
def test_override_references_refuse_deletion_without_expiring_override(content, field, expired):
    from src.api_server import app
    from src.settings.service import TemporaryOverride

    pages, settings, _primary, target = content
    settings.set_temporary_override(
        TemporaryOverride(
            **{
                **(
                    {"page_id": target.id}
                    if field == "page_id"
                    else {"template": ["One off"], "revert_page_id": target.id}
                ),
                "expires_at": "2000-01-01T00:00:00+00:00" if expired else None,
            }
        )
    )
    before = settings.settings_file.read_bytes()
    response = TestClient(app).delete(f"/api/v1/pages/{target.id}")
    assert response.status_code == 409
    assert "override" in response.json()["detail"].lower()
    assert settings.settings_file.read_bytes() == before
    assert pages.get_page(target.id) is not None
