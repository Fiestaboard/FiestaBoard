"""Schema v7 for flexible pages, and the share-string envelope version they use."""

import base64
import json

import pytest

from src.pages import storage as pages_storage
from src.pages.models import Page, PageCreate
from src.pages.share import decode_page, encode_page
from src.pages.storage import CURRENT_SCHEMA_VERSION, MIGRATIONS, PageStorage
from src.storage.json_store import SchemaTooNewError

FLEX = {
    "name": "Morning",
    "type": "flexible",
    "blocks": [
        {"id": "b1", "kind": "text", "text": "{{date_time.time}}", "style": {"size": "large"}, "priority": 1},
        {"id": "b2", "kind": "text", "text": "HI", "if": "{{weather.temp}} > 50"},
    ],
}


def _envelope(share_string: str) -> dict:
    padded = share_string + "=" * (-len(share_string) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def test_v6_file_migrates_to_v7_without_touching_pages(tmp_path):
    path = tmp_path / "pages.json"
    page = {
        "id": "p1",
        "name": "G",
        "type": "template",
        "template": ["HI"],
        "device_type": "flagship",
        "canvases": None,
    }
    path.write_text(json.dumps({"schema_version": 6, "pages": [dict(page)]}))
    storage = PageStorage(storage_file=str(path))
    data = json.loads(path.read_text())
    assert data["schema_version"] == 7
    assert storage.get("p1").template == ["HI"]
    assert pages_storage._migrate_v6_to_v7([dict(page)]) == 0


def test_failed_upgrade_backup_blocks_load_and_cached_writes_until_successful_reload(tmp_path, monkeypatch):
    from src.storage import json_store

    path = tmp_path / "pages.json"
    path.write_text(json.dumps({"schema_version": 7, "pages": []}))
    storage = PageStorage(storage_file=str(path))
    original = json.dumps({"schema_version": 6, "pages": [{"id": "old", "name": "Grid", "type": "template", "template": ["KEEP"]}]})
    path.write_text(original)
    copy = json_store.shutil.copy2

    def fail_copy(*args, **kwargs):
        raise OSError("backup disk full")

    monkeypatch.setattr(json_store.shutil, "copy2", fail_copy)
    with pytest.raises(RuntimeError, match="backup"):
        storage._load()
    with pytest.raises(RuntimeError, match="backup"):
        storage._store.save({"pages": []})
    assert path.read_text() == original
    monkeypatch.setattr(json_store.shutil, "copy2", copy)
    storage._load()
    assert storage.get("old").template == ["KEEP"]
    assert path.with_suffix(".json.v6_backup").read_text() == original


def test_schema_version_is_7_with_the_flexible_migration_last():
    assert CURRENT_SCHEMA_VERSION == 7
    assert MIGRATIONS[-1] == (7, pages_storage._migrate_v6_to_v7)


def test_flexible_page_survives_save_and_reload(tmp_path):
    s = PageStorage(storage_file=str(tmp_path / "pages.json"))
    created = s.create(Page.model_validate(FLEX))
    again = PageStorage(storage_file=str(tmp_path / "pages.json")).get(created.id)
    assert again.type == "flexible" and [b.id for b in again.blocks] == ["b1", "b2"]


def test_v8_file_is_refused_not_mangled(tmp_path):
    path = tmp_path / "pages.json"
    original = json.dumps({"schema_version": 8, "pages": []})
    path.write_text(original)
    with pytest.raises(SchemaTooNewError, match="newer"):
        PageStorage(storage_file=str(path))
    assert path.read_text() == original


def test_flexible_share_uses_envelope_v2_and_grid_stays_v1():
    assert _envelope(encode_page(Page.model_validate(FLEX)))["v"] == 2
    assert _envelope(encode_page(Page(name="G", type="template", template=["X"])))["v"] == 1


def test_v2_share_round_trips_to_page_create():
    data = decode_page(encode_page(Page.model_validate(FLEX)))
    assert PageCreate.model_validate(data).type == "flexible"
