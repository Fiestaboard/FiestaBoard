"""Conditional collection/schedule edits use the generation originally read."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.collections.models import Collection
from src.collections.storage import CollectionStorage
from src.pages.storage import PageRevisionConflict
from src.schedules.models import ScheduleEntry
from src.schedules.storage import ScheduleStorage


@pytest.fixture(params=["collection", "schedule"])
def content(request, tmp_path):
    if request.param == "collection":
        store = CollectionStorage(str(tmp_path / "collections.json"))
        item = Collection(name="Example", page_ids=["page-a"])
        change = {"name": "Updated"}
    else:
        store = ScheduleStorage(str(tmp_path / "schedules.json"))
        item = ScheduleEntry(page_id="page-a", start_time="10:00")
        change = {"enabled": False}
    return store, store.create(item), change


def test_original_revision_rejects_update_and_delete_after_legacy_write(content):
    store, item, change = content
    assert item.revision
    updated = store.update(item.id, change)
    assert updated.revision != item.revision
    with pytest.raises(PageRevisionConflict):
        store.update(item.id, change, expected_revision=item.revision)
    with pytest.raises(PageRevisionConflict):
        store.delete(item.id, expected_revision=item.revision)
    assert store.get(item.id) == updated


def test_only_one_simultaneous_writer_can_use_original_revision(content):
    store, item, change = content

    def write(_):
        try:
            store.update(item.id, change, expected_revision=item.revision)
            return "saved"
        except PageRevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, range(2))) == ["conflict", "saved"]


def test_reload_and_same_id_recreation_invalidate_and_metadata_is_not_persisted(content):
    store, item, change = content
    disk = json.loads(store.storage_file.read_text())
    assert "revision" not in str(disk)
    assert "edit_protocol" not in str(disk)
    store._load()
    assert store.get(item.id).revision != item.revision
    with pytest.raises(PageRevisionConflict):
        store.update(item.id, change, expected_revision=item.revision)
    assert store.delete(item.id)
    recreated = store.create(item)
    assert recreated.revision != item.revision


def test_default_revision_rotates_for_any_default_write_and_reload(tmp_path):
    store = ScheduleStorage(str(tmp_path / "schedules.json"))
    original = store.default_revision
    store.set_default_page_id("page-a", "board-a", expected_revision=original)
    assert store.default_revision != original
    with pytest.raises(PageRevisionConflict):
        store.set_default_page_id(None, "board-b", expected_revision=original)
    assert store.get_default_page_id("board-a") == "page-a"
    latest = store.default_revision
    store._load()
    assert store.default_revision != latest


@pytest.mark.parametrize("domain", ["collections", "schedules"])
@pytest.mark.parametrize("first_prefix,second_prefix", [("", "/v1"), ("/v1", "")])
def test_http_both_save_orders_and_stale_delete(domain, first_prefix, second_prefix):
    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.pages.models import Page
    from src.pages.service import get_page_service

    page = get_page_service().storage.create(Page(name="Example", type="template", template=["EXAMPLE"]))
    client = TestClient(app)
    payload = (
        {"name": "Example", "page_ids": [page.id]}
        if domain == "collections"
        else {"page_id": page.id, "start_time": "10:00"}
    )
    original = client.post(f"{first_prefix}/{domain}", json=payload).json()
    change = {"name": "Edited"} if domain == "collections" else {"enabled": False}
    response = client.put(
        f"{first_prefix}/{domain}/{original['id']}", json={**change, "expected_revision": original["revision"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] != original["revision"]
    assert response.json()["edit_protocol"] == f"{domain[:-1]}-revision-v1"
    stale = client.put(
        f"{second_prefix}/{domain}/{original['id']}", json={**change, "expected_revision": original["revision"]}
    )
    assert stale.status_code == 412, stale.text
    stale_delete = client.delete(
        f"{second_prefix}/{domain}/{original['id']}", params={"expected_revision": original["revision"]}
    )
    assert stale_delete.status_code == 412, stale_delete.text
    current = client.get(f"{second_prefix}/{domain}/{original['id']}").json()
    assert current["revision"] == response.json()["revision"]


def test_schedule_null_clears_nullable_fields_and_omission_retains_them(tmp_path):
    store = ScheduleStorage(str(tmp_path / "schedules.json"))
    original = store.create(ScheduleEntry(page_id="page-a", start_time="10:00", end_time="11:00"))
    updated = store.update(original.id, {"enabled": False}, expected_revision=original.revision)
    assert updated.end_time == "11:00"
    cleared = store.update(original.id, {"end_time": None}, expected_revision=updated.revision)
    assert cleared.end_time is None


def test_collection_null_clears_inactive_mode_config_and_omission_preserves_it(tmp_path):
    from src.collections.models import VariableModeConfig

    store = CollectionStorage(str(tmp_path / "collections.json"))
    original = store.create(
        Collection(name="Example", page_ids=["page-a"], variable=VariableModeConfig(default_page_id="page-a"))
    )
    updated = store.update(original.id, {"name": "New name"}, expected_revision=original.revision)
    assert updated.variable == original.variable
    cleared = store.update(original.id, {"variable": None}, expected_revision=updated.revision)
    assert cleared.variable is None


def test_runtime_metadata_cannot_be_written_through_update(content):
    store, original, change = content
    updated = store.update(original.id, {**change, "revision": "forged", "edit_protocol": "forged"})
    assert updated.revision not in {"forged", original.revision}
    assert updated.edit_protocol == original.edit_protocol


def test_load_ignores_untrusted_runtime_metadata_in_stored_content(content):
    store, original, _ = content
    data = json.loads(store.storage_file.read_text())
    key = "collections" if isinstance(store, CollectionStorage) else "schedules"
    data[key][0].update(revision={"poison": True}, edit_protocol=["untrusted"])
    store.storage_file.write_text(json.dumps(data))
    store._load()
    current = store.get(original.id)
    assert current is not None
    assert current.revision != original.revision
    assert current.edit_protocol == original.edit_protocol


def test_explicit_supported_reload_recovers_after_future_schema_refusal(content):
    from src.storage.json_store import SchemaTooNewError

    store, original, change = content
    supported = store.storage_file.read_text()
    newer = json.loads(supported)
    newer["schema_version"] = 999
    store.storage_file.write_text(json.dumps(newer))
    with pytest.raises(SchemaTooNewError):
        store._load()
    with pytest.raises(SchemaTooNewError):
        store.update(original.id, change)
    assert json.loads(store.storage_file.read_text())["schema_version"] == 999
    store.storage_file.write_text(supported)
    store._load()
    with pytest.raises(PageRevisionConflict):
        store.update(original.id, change, expected_revision=original.revision)
    assert store.update(original.id, change, expected_revision=store.get(original.id).revision)


def test_legacy_carousel_restore_replaces_existing_live_collection_store():
    from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, BackupService
    from src.collections.service import get_collection_service

    collections = get_collection_service()
    old = collections.storage.create(Collection(name="Before", page_ids=["page-a"]))
    backup = {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": {
            "carousels": {
                "carousels": [
                    {
                        "id": "carousel:restored",
                        "name": "Restored",
                        "page_ids": ["page-a"],
                        "interval_seconds": 60,
                    }
                ]
            }
        },
    }
    BackupService(data_dir=collections.storage.storage_file.parent).import_from_dict(backup, reinstall_plugins=False)
    assert get_collection_service() is collections
    assert collections.get_collection(old.id) is None
    restored = collections.get_collection("collection:restored")
    assert restored.name == "Restored"
    assert restored.time.interval_seconds == 60
    assert restored.revision


def test_default_primary_aba_and_settings_writes_never_revive_original_token():
    from copy import deepcopy

    from src.schedules.service import get_schedule_service
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    settings.set_boards([{"id": bid, "name": bid, "device_type": "flagship"} for bid in ["board-a", "board-b"]])
    schedules = get_schedule_service()
    schedules.set_default_page("page-a", "board-a")
    state = schedules.get_default_page_state()
    assert state["default_page_id"] == "page-a"
    boards = deepcopy(settings.get_board_settings().boards)
    settings.set_boards(list(reversed(boards)))
    settings.set_boards(boards)
    with pytest.raises(PageRevisionConflict):
        schedules.set_default_page("page-b", expected_revision=state["revision"])
    assert schedules.get_default_page() == "page-a"


def test_restore_keeps_live_collection_and_schedule_owners_and_invalidates_tokens(monkeypatch):
    from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, BackupService
    from src.collections.service import get_collection_service
    from src.schedules.service import get_schedule_service

    collections = get_collection_service()
    schedules = get_schedule_service()
    collection = collections.storage.create(Collection(name="Before", page_ids=["page-a"]))
    schedule = schedules.storage.create(ScheduleEntry(page_id="page-a", start_time="10:00"))
    root = collections.storage.storage_file.parent
    backup = {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": {
            "collections": {
                "schema_version": 1,
                "collections": [{**collection.model_dump(mode="json"), "name": "Restored"}],
            },
            "schedules": {"schema_version": 2, "schedules": [{**schedule.model_dump(mode="json"), "enabled": False}]},
        },
    }
    BackupService(data_dir=root).import_from_dict(backup, reinstall_plugins=False)
    assert get_collection_service() is collections
    assert get_schedule_service() is schedules
    assert collections.storage.get(collection.id).name == "Restored"
    assert schedules.storage.get(schedule.id).enabled is False
    for owner in (collections.storage, schedules.storage):
        disk = json.loads(owner.storage_file.read_text())
        records = disk["collections" if owner is collections.storage else "schedules"]
        assert "revision" not in records[0]
        assert "edit_protocol" not in records[0]
    with pytest.raises(PageRevisionConflict):
        collections.storage.update(collection.id, {"name": "Stale"}, expected_revision=collection.revision)
    with pytest.raises(PageRevisionConflict):
        schedules.storage.update(schedule.id, {"enabled": True}, expected_revision=schedule.revision)


def test_stale_collection_delete_leaves_references_untouched():
    from copy import deepcopy

    from src.collections.service import get_collection_service
    from src.schedules.service import get_schedule_service

    collections = get_collection_service()
    schedules = get_schedule_service().storage
    original = collections.storage.create(Collection(name="Before", page_ids=["page-a"]))
    schedules.create(ScheduleEntry(page_id=original.id, start_time="10:00"))
    before = deepcopy(schedules.list_all(board_id="*"))
    collections.storage.update(original.id, {"name": "After"})
    with pytest.raises(PageRevisionConflict):
        collections.delete_collection(original.id, expected_revision=original.revision)
    assert schedules.list_all(board_id="*") == before


def test_collection_delete_follows_cross_store_lock_order_during_resize(monkeypatch):
    import threading
    from contextlib import ExitStack

    from src.collections.service import get_collection_service
    from src.config_manager import get_config_manager
    from src.pages.service import get_page_service
    from src.schedules.service import get_schedule_service
    from src.settings.service import get_settings_service

    collections = get_collection_service()
    original = collections.storage.create(Collection(name="Before", page_ids=["page-a"]))
    settings = get_settings_service()
    config = get_config_manager()
    pages = get_page_service().storage
    schedules = get_schedule_service().storage
    started = threading.Event()
    completed = threading.Event()
    errors = []
    owning_thread = threading.get_ident()
    settings_lock = settings.lock

    class ObservedSettingsLock:
        def __enter__(self):
            if threading.get_ident() != owning_thread:
                started.set()
            return settings_lock.__enter__()

        def __exit__(self, *args):
            return settings_lock.__exit__(*args)

    monkeypatch.setattr(settings._store, "_lock", ObservedSettingsLock())

    def delete():
        try:
            collections.delete_collection(original.id, expected_revision=original.revision)
        except Exception as exc:
            errors.append(exc)
        finally:
            completed.set()

    # A conversion already owns settings before it enters the child stores.
    # A delete must wait there, rather than owning collections and waiting
    # back on settings (which would deadlock conversion).
    with settings.lock:
        thread = threading.Thread(target=delete, daemon=True)
        thread.start()
        assert started.wait(2), "delete did not enter the owning settings lock first"
        with ExitStack() as locks:
            for lock in (config.lock, pages.lock, collections.storage.lock, schedules.lock):
                assert lock.acquire(timeout=2), "delete inverted the conversion lock order"
                locks.callback(lock.release)
        assert not completed.is_set()
    thread.join(2)
    assert completed.is_set(), "delete did not finish after conversion released its owners"
    assert not errors


def test_settings_restore_preserves_owner_lock_and_invalidates_default_editors():
    from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, BackupService
    from src.schedules.service import get_schedule_service
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    settings._save_to_file()
    owner_lock = settings.lock
    schedules = get_schedule_service()
    original = schedules.get_default_page_state()
    payload = json.loads(settings.settings_file.read_text())
    payload["display"]["reduce_motion"] = True
    backup = {BACKUP_FILE_MARKER: True, "schema_version": BACKUP_SCHEMA_VERSION, "data": {"settings": payload}}
    BackupService(data_dir=settings.settings_file.parent).import_from_dict(backup, reinstall_plugins=False)
    assert get_settings_service() is settings
    assert settings.lock is owner_lock
    assert settings.get_display_settings().reduce_motion is True
    with pytest.raises(PageRevisionConflict):
        schedules.set_default_page(None, expected_revision=original["revision"])


def test_default_read_captures_one_settings_owner_per_operation(monkeypatch):
    import src.schedules.service as service
    from src.schedules.service import get_schedule_service
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    calls = []

    def get_owner():
        calls.append(1)
        assert len(calls) == 1, "default helper reacquired a potentially different settings owner"
        return settings

    schedules = get_schedule_service()
    monkeypatch.setattr(service, "get_settings_service", get_owner)
    state = schedules.get_default_page_state()
    assert state["revision"]
    calls.clear()
    assert schedules.set_default_page(None, expected_revision=state["revision"])["default_page_id"] is None
