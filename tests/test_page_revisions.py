"""Optimistic editing uses live storage generations, never document hashes."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, RLock, Thread, current_thread
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, BackupService
from src.pages.models import Page, PageUpdate
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.storage.json_store import SchemaTooNewError


@pytest.fixture
def storage(tmp_path):
    return PageStorage(str(tmp_path / "pages.json"))


@pytest.fixture
def page(storage):
    return storage.create(Page(id="editor-page", name="Original", type="template", template=["hello"]))


def test_read_revision_is_opaque_and_not_a_stored_page_field(storage, page):
    assert isinstance(page.revision, str) and page.revision
    assert storage.get(page.id).revision == page.revision
    assert storage.list_all()[0].revision == page.revision
    assert "revision" not in json.loads(storage.storage_file.read_text())["pages"][0]


def test_stored_pages_advertise_runtime_edit_protocol_without_persisting_it(storage, page):
    assert storage.get(page.id).model_dump()["edit_protocol"] == "page-revision-v1"
    assert storage.list_all()[0].model_dump()["edit_protocol"] == "page-revision-v1"
    saved = storage.update(page.id, {"name": "Saved"}, expected_revision=page.revision)
    assert saved.model_dump()["edit_protocol"] == "page-revision-v1"
    assert "edit_protocol" not in json.loads(storage.storage_file.read_text())["pages"][0]
    restarted = PageStorage(str(storage.storage_file))
    assert restarted.get(page.id).model_dump()["edit_protocol"] == "page-revision-v1"


def test_page_input_cannot_override_runtime_edit_protocol(storage):
    supplied = Page(name="Protocol override", type="template", template=["hello"], edit_protocol="future-protocol")
    created = storage.create(supplied)
    assert created.model_dump()["edit_protocol"] == "page-revision-v1"
    saved = storage.update(created.id, {"edit_protocol": "future-protocol"}, expected_revision=created.revision)
    assert saved.model_dump()["edit_protocol"] == "page-revision-v1"
    assert "edit_protocol" not in json.loads(storage.storage_file.read_text())["pages"][0]


def test_persisted_input_cannot_override_runtime_edit_protocol(storage, page):
    document = json.loads(storage.storage_file.read_text())
    document["pages"][0]["edit_protocol"] = "future-protocol"
    storage.storage_file.write_text(json.dumps(document))
    storage._load()
    assert storage.get(page.id).model_dump()["edit_protocol"] == "page-revision-v1"
    storage.update(page.id, {"name": "Saved"})
    assert "edit_protocol" not in json.loads(storage.storage_file.read_text())["pages"][0]


@pytest.mark.parametrize("first,second", [("native", "web"), ("web", "native")])
def test_two_editors_first_save_wins_in_either_order(storage, page, first, second):
    revision = page.revision
    saved = storage.update(page.id, {"name": first}, expected_revision=revision)
    assert saved.revision != revision
    with pytest.raises(ValueError, match="Page changed"):
        storage.update(page.id, {"name": second}, expected_revision=revision)
    assert storage.get(page.id).name == first


def test_concurrent_preconditions_are_checked_inside_mutation_lock(storage, page):
    barrier = Barrier(2)

    def save(name):
        barrier.wait(timeout=5)
        try:
            return storage.update(page.id, {"name": name}, expected_revision=page.revision).name
        except ValueError as exc:
            assert "Page changed" in str(exc)
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["native", "web"]))
    assert results.count("conflict") == 1
    assert storage.get(page.id).name in results


def test_unconditional_legacy_update_invalidates_editor_revision(storage, page):
    storage.update(page.id, {"name": "legacy"})
    with pytest.raises(ValueError, match="Page changed"):
        storage.update(page.id, {"name": "stale"}, expected_revision=page.revision)
    with pytest.raises(ValueError, match="Page changed"):
        storage.delete(page.id, expected_revision=page.revision)
    assert storage.get(page.id).name == "legacy"


def test_identical_content_after_aba_does_not_reuse_revision(storage, page):
    storage.update(page.id, {"name": "temporary"})
    current = storage.update(page.id, {"name": page.name})
    assert current.revision != page.revision
    with pytest.raises(ValueError, match="Page changed"):
        storage.update(page.id, {"name": "stale"}, expected_revision=page.revision)


def test_delete_recreate_same_id_invalidates_old_revision(storage, page):
    assert storage.delete(page.id, expected_revision=page.revision)
    replacement = storage.create(page.model_copy())
    assert replacement.revision != page.revision
    with pytest.raises(ValueError, match="Page changed"):
        storage.delete(page.id, expected_revision=page.revision)
    assert storage.get(page.id) is not None


def test_restart_invalidates_old_revision(storage, page):
    restarted = PageStorage(str(storage.storage_file))
    assert restarted.get(page.id).revision != page.revision
    with pytest.raises(ValueError, match="Page changed"):
        restarted.update(page.id, {"name": "stale"}, expected_revision=page.revision)


def test_revision_from_another_page_cannot_authorize_edit(storage, page):
    other = storage.create(Page(name="Other", type="template", template=["other"]))
    with pytest.raises(ValueError, match="Page changed"):
        storage.update(page.id, {"name": "wrong page"}, expected_revision=other.revision)
    assert storage.get(page.id).name == page.name


def test_unreadable_restored_schema_does_not_leave_old_live_pages(storage, page, monkeypatch):
    service = PageService(storage=storage)
    monkeypatch.setattr("src.pages.service.get_page_service", lambda: service)
    backup = {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": {"pages": {"schema_version": 999, "pages": []}},
    }
    with pytest.raises(SchemaTooNewError):
        BackupService(data_dir=storage.storage_file.parent).import_from_dict(backup, reinstall_plugins=False)
    # Restore is not transactional, but cached requests cannot keep reading
    # or conditionally saving pages from the pre-restore document.
    assert service.get_page(page.id) is None
    assert service.update_page(page.id, PageUpdate(name="stale", expected_revision=page.revision)) is None
    assert json.loads(storage.storage_file.read_text())["schema_version"] == 999


def test_valid_restore_recovers_same_owner_after_future_schema_refusal(storage, page, monkeypatch):
    service = PageService(storage=storage)
    monkeypatch.setattr("src.pages.service.get_page_service", lambda: service)
    backup = BackupService(data_dir=storage.storage_file.parent)
    valid = {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": {"pages": json.loads(storage.storage_file.read_text())},
    }
    future = {**valid, "data": {"pages": {"schema_version": 999, "pages": []}}}
    with pytest.raises(SchemaTooNewError):
        backup.import_from_dict(future, reinstall_plugins=False)
    # A refused future document remains protected until explicitly replaced
    # and successfully loaded, even through unconditional legacy writes.
    with pytest.raises(SchemaTooNewError):
        storage.create(Page(name="Cannot overwrite future data", type="template", template=["guard"]))
    assert json.loads(storage.storage_file.read_text())["schema_version"] == 999
    with patch("src.backup.service._reload_services", return_value=[]):
        result = backup.import_from_dict(valid, reinstall_plugins=False)
    assert result["status"] == "success"
    restored = service.get_page(page.id)
    saved = service.update_page(page.id, PageUpdate(name="Recovered", expected_revision=restored.revision))
    assert saved.name == "Recovered"
    assert service.delete_page(page.id, expected_revision=saved.revision).deleted
    assert all(p["id"] != page.id for p in json.loads(storage.storage_file.read_text())["pages"])


def test_conditional_delete_and_panel_resize_follow_same_outer_lock_order(storage, page, monkeypatch):
    """Force resize's outer locks to overlap deletion; timeouts bound failures."""
    from src.devices import DeviceDimensions
    from src.panels.content_resize import panel_content_resize

    resize_at_pages = Event()
    delete_at_outer_lock = Event()
    failures = []

    class BoundedLock:
        def __init__(self, real=None, *, pages=False):
            self.real = real or RLock()
            self.pages = pages

        def __enter__(self):
            if self.pages and current_thread().name == "resize":
                resize_at_pages.set()
                if not delete_at_outer_lock.wait(2):
                    raise TimeoutError("delete did not reach an outer lock")
            if not self.pages and current_thread().name == "delete":
                delete_at_outer_lock.set()
            if not self.real.acquire(timeout=2):
                raise TimeoutError("inverted page/outer lock acquisition")
            return self

        def __exit__(self, *args):
            self.real.release()

    monkeypatch.setattr(storage._store, "_lock", BoundedLock(storage.lock, pages=True))
    service = PageService(storage=storage)
    settings = Mock(lock=BoundedLock())
    settings.get_board_settings.return_value = SimpleNamespace(boards=[{"id": "board"}])
    settings.get_active_page_id.return_value = None
    settings.get_active_page_settings.return_value = SimpleNamespace()
    settings.peek_temporary_override.return_value = None
    config_lock = BoundedLock()

    def get_feature(_name):
        with config_lock:
            return {}

    config = SimpleNamespace(lock=config_lock, get_feature=get_feature, _config={})
    schedules = Mock()
    schedules.storage.lock = BoundedLock()
    schedules.storage.list_all.return_value = []
    schedules.storage.get_default_page_id.return_value = None
    schedules.storage._default_page_by_board = {}
    schedules.get_default_page.return_value = None
    schedules.list_schedules.return_value = []
    collections = Mock()
    collections.storage.lock = BoundedLock()
    collections.list_collections.return_value = []
    for module in ("src.settings.service", "src.pages.service", "src.panels.content_resize"):
        monkeypatch.setattr(module + ".get_settings_service", lambda: settings)
    for module in ("src.config_manager", "src.panels.content_resize"):
        monkeypatch.setattr(module + ".get_config_manager", lambda: config)
    for module in ("src.schedules.service", "src.panels.content_resize"):
        monkeypatch.setattr(module + ".get_schedule_service", lambda: schedules)
    for module in ("src.collections.service", "src.panels.content_resize"):
        monkeypatch.setattr(module + ".get_collection_service", lambda: collections)
    monkeypatch.setattr("src.panels.content_resize.get_page_service", lambda: service)
    monkeypatch.setattr("src.panels.content_resize.prepare_resize_journal", lambda *a, **kw: None)
    monkeypatch.setattr("src.panels.content_resize.commit_resize_journal", lambda journal: None)
    monkeypatch.setattr("src.panels.content_resize.discard_resize_journal", lambda journal: None)

    def resize():
        with panel_content_resize({"id": "board"}, DeviceDimensions(6, 22), True):
            pass

    def delete():
        assert service.delete_page(page.id, expected_revision=page.revision).deleted

    def capture(action):
        try:
            action()
        except BaseException as exc:
            failures.append(exc)

    resize_thread = Thread(name="resize", target=capture, args=(resize,), daemon=True)
    delete_thread = Thread(name="delete", target=capture, args=(delete,), daemon=True)
    resize_thread.start()
    assert resize_at_pages.wait(2)
    delete_thread.start()
    for thread in (resize_thread, delete_thread):
        thread.join(timeout=6)
    assert not resize_thread.is_alive() and not delete_thread.is_alive()
    assert failures == []
    assert storage.get(page.id) is None


def test_backup_restore_reloads_live_storage_before_releasing_owner_lock(storage, page, monkeypatch):
    """A request holding a pre-restore service must see the restored generation."""
    service = PageService(storage=storage)
    monkeypatch.setattr("src.pages.service.get_page_service", lambda: service)
    backup = {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": {"pages": json.loads(storage.storage_file.read_text())},
    }
    storage.update(page.id, {"name": "before restore"})
    before_restore = storage.get(page.id).revision
    with patch("src.backup.service._reload_services", return_value=[]):
        BackupService(data_dir=storage.storage_file.parent).import_from_dict(backup, reinstall_plugins=False)
    assert service.get_page(page.id).name == "Original"
    assert service.get_page(page.id).revision not in (page.revision, before_restore)
    with pytest.raises(ValueError, match="Page changed"):
        service.update_page(page.id, PageUpdate(name="stale", expected_revision=before_restore))
    assert json.loads(storage.storage_file.read_text())["pages"][0]["name"] == "Original"


@pytest.mark.parametrize("prefix", ["", "/v1"])
def test_http_update_and_delete_reject_stale_revision(prefix, storage, page, monkeypatch):
    from src.api_server import app

    service = PageService(storage=storage)
    monkeypatch.setattr("src.pages.routes.get_page_service", lambda: service)
    client = TestClient(app)
    revision = client.get(f"{prefix}/pages/{page.id}").json()["revision"]
    saved = client.put(f"{prefix}/pages/{page.id}", json={"name": "first", "expected_revision": revision})
    assert saved.status_code == 200
    assert saved.json()["page"]["revision"] != revision
    stale = client.put(f"{prefix}/pages/{page.id}", json={"name": "stale", "expected_revision": revision})
    assert stale.status_code == 412
    deleted = client.delete(f"{prefix}/pages/{page.id}", params={"expected_revision": revision})
    assert deleted.status_code == 412
    assert client.get(f"{prefix}/pages/{page.id}").json()["name"] == "first"


@pytest.mark.parametrize("prefix", ["", "/v1"])
def test_http_reads_and_save_receipts_advertise_exact_edit_protocol(prefix, storage, page, monkeypatch):
    from src.api_server import app

    monkeypatch.setattr("src.pages.routes.get_page_service", lambda: PageService(storage=storage))
    client = TestClient(app)
    fetched = client.get(f"{prefix}/pages/{page.id}")
    assert fetched.status_code == 200
    assert fetched.json()["edit_protocol"] == "page-revision-v1"
    listed = client.get(f"{prefix}/pages")
    assert listed.status_code == 200
    assert listed.json()["pages"][0]["edit_protocol"] == "page-revision-v1"
    created = client.post(
        f"{prefix}/pages",
        json={"name": "Created", "type": "template", "template": ["NEW"], "edit_protocol": "caller-value"},
    )
    assert created.status_code == 201
    assert created.json()["edit_protocol"] == "page-revision-v1"
    saved = client.put(
        f"{prefix}/pages/{page.id}",
        json={"name": "Saved", "expected_revision": fetched.json()["revision"], "edit_protocol": "caller-value"},
    )
    assert saved.status_code == 200
    assert saved.json()["page"]["edit_protocol"] == "page-revision-v1"
    assert saved.json()["page"]["revision"] != fetched.json()["revision"]
    assert saved.json()["incompatible_references"] == []


@pytest.mark.parametrize("prefix", ["", "/v1"])
def test_http_sparse_page_put_preserves_untouched_fields_without_hardware_delivery(prefix, storage, monkeypatch):
    from src.api_server import app

    fixture = json.loads((Path(__file__).parent / "fixtures/page-editing/page-revision-v1.json").read_text())
    page = storage.create(Page(**fixture["read"]))
    monkeypatch.setattr("src.pages.routes.get_page_service", lambda: PageService(storage=storage))

    def forbidden_delivery(*args, **kwargs):
        pytest.fail("page PUT must not access the hardware display service")

    monkeypatch.setattr("src.pages.routes.get_service", forbidden_delivery)
    monkeypatch.setattr("src.display_runtime.get_service", forbidden_delivery)
    client = TestClient(app)
    before = client.get(f"{prefix}/pages/{page.id}").json()
    assert before == {**fixture["read"], "revision": before["revision"]}
    lines = fixture["request"]["template"]
    response = client.put(
        f"{prefix}/pages/{page.id}",
        json={**fixture["request"], "expected_revision": before["revision"]},
    )
    assert response.status_code == 200
    saved = response.json()["page"]
    assert saved["revision"] != before["revision"]
    assert saved["updated_at"] is not None
    assert response.json() == {
        **fixture["save"],
        "page": {**fixture["save"]["page"], "revision": saved["revision"], "updated_at": saved["updated_at"]},
    }
    assert saved["template"] == lines
    for key, value in before.items():
        if key not in {"template", "revision", "updated_at"}:
            assert saved[key] == value
    # Legacy precondition-free writes remain compatible and invalidate old drafts.
    legacy = client.put(f"{prefix}/pages/{page.id}", json={"name": "Legacy rename"})
    assert legacy.status_code == 200
    assert legacy.json()["page"]["template"] == lines
    assert legacy.json()["page"]["revision"] != saved["revision"]
    stale = client.put(
        f"{prefix}/pages/{page.id}",
        json={"name": "Stale", "expected_revision": saved["revision"]},
    )
    assert stale.status_code == 412
    assert stale.json() == fixture["conflict"]
    assert client.get(f"{prefix}/pages/{page.id}").json()["name"] == "Legacy rename"
