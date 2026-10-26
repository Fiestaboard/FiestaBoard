"""Optimistic editing uses live storage generations, never document hashes."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

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
