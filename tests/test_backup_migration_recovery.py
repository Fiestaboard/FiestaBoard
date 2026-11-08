"""Owner migrations are part of a restore's own writes, not external edits."""

import json

import pytest

from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, BackupRestoreAborted, BackupService
from src.pages.models import Page
from src.pages.service import PageService
from src.pages.storage import CURRENT_SCHEMA_VERSION, PageStorage


@pytest.mark.parametrize("failure", ["later file", "owner reload"])
def test_migrated_restore_recovers_original_file_and_live_owner(tmp_path, monkeypatch, failure):
    storage = PageStorage(str(tmp_path / "pages.json"))
    original = storage.create(Page(name="Original", type="template", template=["original"]))
    before = storage.storage_file.read_bytes()
    pages = PageService(storage)
    monkeypatch.setattr("src.pages.service.get_page_service", lambda: pages)
    backup = BackupService(tmp_path)
    reload_owner = backup._reload_owner
    write_json = backup._write_json_with_backup
    observed = []

    def reload(filename):
        reload_owner(filename)
        if filename == "pages.json" and storage.get("restored") is not None:
            observed.append(json.loads(storage.storage_file.read_text())["schema_version"])
            if failure == "owner reload":
                raise OSError("synthetic failure after migration")

    def write(path, payload, timestamp):
        if path.name == "schedules.json":
            raise OSError("synthetic later-file failure")
        return write_json(path, payload, timestamp)

    monkeypatch.setattr(backup, "_reload_owner", reload)
    monkeypatch.setattr(backup, "_write_json_with_backup", write)
    document = {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": {
            "pages": {
                "schema_version": 1,
                "pages": [{"id": "restored", "name": "Restored", "type": "template", "template": ["restored"]}],
            },
            "schedules": {"schedules": []},
        },
    }
    with pytest.raises(BackupRestoreAborted, match="Original files recovered"):
        backup.import_from_dict(document, reinstall_plugins=False)
    assert observed == [CURRENT_SCHEMA_VERSION]
    assert storage.storage_file.read_bytes() == before
    assert storage.get("restored") is None
    recovered = storage.get(original.id)
    assert recovered.name == original.name
    assert recovered.revision != original.revision
    with pytest.raises(ValueError, match="Page changed"):
        storage.update(original.id, {"name": "stale"}, expected_revision=original.revision)
