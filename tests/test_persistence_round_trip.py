"""Persistence round-trips: state written through the API survives a restart.

Part of #1730 Phase 0 (issue #1736). Every existing persistence test writes and
re-reads inside one process, with the service singletons still holding their
in-memory copy of the data — so a store that never actually flushed to disk, or
one whose loader silently drops a field, still passes. These tests close that
gap: they write through HTTP, throw every singleton away (which is what a
container restart does to on-disk-backed state), and read the same values back
through HTTP off the JSON files alone.

Two things are deliberate:

* **Everything goes through the API.** The point is the whole write path —
  route handler, service, storage, JSON encoder — not one store's `_save`.
* **Nothing hand-writes `pages.json`.** The schema-version machinery in
  ``src/pages/storage.py`` stamps ``CURRENT_SCHEMA_VERSION`` on save and runs
  migrations on load; seeding a file by hand would bypass exactly the code the
  restart is supposed to exercise.

Data isolation (see #1762): the app has no single data-directory seam. Each
store resolves its own path from ``Path(__file__)`` at construction time, so
``isolated_data_dir`` has to rebind five different constructors to keep the
suite off the developer's real ``data/`` directory. That fixture is the
workaround, not the fix.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config_manager import ConfigManager

# ── isolation ───────────────────────────────────────────────────────────────

#: Module path + attribute name of every service singleton that caches
#: on-disk state. This is the same list ``src.backup.service._reload_services``
#: drops after a restore — i.e. the app's own definition of "re-read from disk".
_SINGLETONS: tuple[tuple[str, str], ...] = (
    ("src.settings.service", "_settings_service"),
    ("src.pages.service", "_page_service"),
    ("src.collections.service", "_collection_service"),
    ("src.schedules.service", "_schedule_service"),
    ("src.backup.service", "_backup_service"),
)


def _drop_singletons() -> None:
    """Forget every cached service instance, as a process restart would.

    ``ConfigManager`` is cleared through the class imported at module scope,
    never through ``src.config_manager.ConfigManager``: the isolation fixture
    rebinds that name to a ``functools.partial``, and assigning ``_instance``
    on the partial leaves the class-level singleton — pointing at the repo's
    real ``data/config.json`` — very much alive.
    """
    import importlib

    ConfigManager._instance = None  # type: ignore[attr-defined]
    for module_path, attr in _SINGLETONS:
        setattr(importlib.import_module(module_path), attr, None)


def _bind_backup_service(data_dir: Path) -> None:
    """Rebuild the backup singleton against *data_dir*."""
    import src.backup.service as backup_module

    backup_module._backup_service = backup_module.BackupService(data_dir=data_dir)


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Point every on-disk store at *tmp_path* and hand back that path.

    Rebinds the class each singleton factory instantiates, so the *next*
    construction — including the ones that happen after a simulated restart —
    lands in the temp directory rather than the repo's ``data/``.
    """
    from src.collections.storage import CollectionStorage
    from src.pages.storage import PageStorage
    from src.schedules.storage import ScheduleStorage
    from src.settings.service import SettingsService

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    bindings = (
        ("src.config_manager.ConfigManager", ConfigManager, {"config_path": str(data_dir / "config.json")}),
        ("src.settings.service.SettingsService", SettingsService, {"settings_file": str(data_dir / "settings.json")}),
        ("src.pages.service.PageStorage", PageStorage, {"storage_file": str(data_dir / "pages.json")}),
        (
            "src.schedules.service.ScheduleStorage",
            ScheduleStorage,
            {"storage_file": str(data_dir / "schedules.json")},
        ),
        (
            "src.collections.service.CollectionStorage",
            CollectionStorage,
            {"storage_file": str(data_dir / "collections.json")},
        ),
    )
    for target, cls, kwargs in bindings:
        monkeypatch.setattr(target, functools.partial(cls, **kwargs))

    _drop_singletons()
    # BackupService takes its data dir up front, so the *instance* is bound
    # rather than the class; _drop_singletons has to run first or it clears it.
    _bind_backup_service(data_dir)
    try:
        yield data_dir
    finally:
        _drop_singletons()


@pytest.fixture
def client(isolated_data_dir):
    """A TestClient whose every request resolves services from the temp dir."""
    from src.api_server import app

    return TestClient(app)


def _restart(data_dir: Path) -> TestClient:
    """Throw away all in-memory state and return a client reading from disk.

    Route handlers resolve their services per request through the singleton
    getters, so dropping the singletons is precisely what a container restart
    does: the next request rebuilds each store by parsing the JSON files.
    """
    from src.api_server import app

    _drop_singletons()
    _bind_backup_service(data_dir)
    return TestClient(app)


# ── seed helpers ────────────────────────────────────────────────────────────

#: A throwaway AI provider. Its api_key is a placeholder, never a real key.
_AI_PROVIDER = {
    "id": "test-provider",
    "name": "Test Provider",
    "base_url": "https://llm.example.test/v1",
    "api_key": "test_api_key_placeholder",
    "models": ["test-model"],
    "default_model": "test-model",
}


def _create_page(client: TestClient, name: str = "Restart Survivor") -> dict:
    response = client.post(
        "/pages",
        json={
            "name": name,
            "type": "template",
            "template": ["HELLO", "FROM DISK", "", "", "", ""],
            "duration_seconds": 42,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["page"]


def _create_schedule(client: TestClient, page_id: str) -> dict:
    response = client.post(
        "/schedules",
        json={"page_id": page_id, "start_time": "07:30", "end_time": "09:15", "day_pattern": "weekdays"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_collection(client: TestClient, page_id: str) -> dict:
    response = client.post(
        "/collections",
        json={"name": "Mornings", "page_ids": [page_id]},
    )
    assert response.status_code == 200, response.text
    return response.json()["collection"]


# ── restart round-trips ─────────────────────────────────────────────────────


def test_page_survives_a_restart(client, isolated_data_dir):
    """A page created through the API is byte-identical after a restart."""
    created = _create_page(client)

    after = _restart(isolated_data_dir).get(f"/pages/{created['id']}")

    assert after.status_code == 200, after.text
    assert after.json() == created


def test_schedule_survives_a_restart(client, isolated_data_dir):
    """A schedule entry keeps every field across a restart."""
    page = _create_page(client)
    created = _create_schedule(client, page["id"])

    after = _restart(isolated_data_dir).get(f"/schedules/{created['id']}")

    assert after.status_code == 200, after.text
    assert after.json()["start_time"] == created["start_time"]
    assert after.json()["end_time"] == created["end_time"]
    assert after.json()["day_pattern"] == created["day_pattern"]
    assert after.json()["page_id"] == page["id"]


def test_collection_survives_a_restart(client, isolated_data_dir):
    """A collection keeps its member pages across a restart."""
    page = _create_page(client)
    created = _create_collection(client, page["id"])

    after = _restart(isolated_data_dir).get(f"/collections/{created['id']}")

    assert after.status_code == 200, after.text
    assert after.json()["name"] == "Mornings"
    assert after.json()["page_ids"] == [page["id"]]


def test_display_settings_survive_a_restart(client, isolated_data_dir):
    """settings.json values written through the API reload from disk."""
    written = client.put(
        "/settings/display",
        json={"reduce_motion": True, "board_animations": "off", "site_animations": "off"},
    )
    assert written.status_code == 200, written.text

    after = _restart(isolated_data_dir).get("/settings/display")

    assert after.status_code == 200, after.text
    assert after.json()["reduce_motion"] is True
    assert after.json()["board_animations"] == "off"
    assert after.json()["site_animations"] == "off"


def test_polling_settings_survive_a_restart(client, isolated_data_dir):
    """A numeric settings field round-trips without being coerced or reset."""
    written = client.put("/settings/polling", json={"interval_seconds": 37})
    assert written.status_code == 200, written.text

    after = _restart(isolated_data_dir).get("/settings/polling")

    assert after.status_code == 200, after.text
    assert after.json()["interval_seconds"] == 37


def test_board_type_survives_a_restart(client, isolated_data_dir):
    """The board settings block reloads from settings.json."""
    written = client.put("/settings/board", json={"board_type": "white"})
    assert written.status_code == 200, written.text

    after = _restart(isolated_data_dir).get("/settings/board")

    assert after.status_code == 200, after.text
    assert after.json()["board_type"] == "white"


def test_config_json_survives_a_restart(client, isolated_data_dir):
    """config.json is a different store from settings.json and also reloads.

    ``/settings/ai`` is the AI-provider block in ``config.json``, written
    through ``ConfigManager`` rather than ``SettingsService``.
    """
    written = client.put("/settings/ai", json={"enabled": True, "providers": [_AI_PROVIDER]})
    assert written.status_code == 200, written.text

    after = _restart(isolated_data_dir).get("/settings/ai")

    assert after.status_code == 200, after.text
    assert after.json()["enabled"] is True
    assert [p["id"] for p in after.json()["providers"]] == [_AI_PROVIDER["id"]]


def test_a_secret_in_config_json_survives_a_restart_unmasked_on_disk(client, isolated_data_dir):
    """The stored secret must be the real key, not the mask the API returns.

    A restart re-reads ``config.json``; if the mask had been persisted the
    credential would be gone for good.
    """
    assert client.put("/settings/ai", json={"enabled": True, "providers": [_AI_PROVIDER]}).status_code == 200

    _restart(isolated_data_dir)

    stored = json.loads((isolated_data_dir / "config.json").read_text())
    assert stored["ai_providers"]["providers"][0]["api_key"] == _AI_PROVIDER["api_key"]


def test_pages_file_is_stamped_with_the_current_schema_version(client, isolated_data_dir):
    """Saving through the API stamps the version the migration ladder expects.

    Without the stamp every subsequent load re-runs the whole ladder from 0.
    """
    from src.pages.storage import CURRENT_SCHEMA_VERSION

    _create_page(client)

    on_disk = json.loads((isolated_data_dir / "pages.json").read_text())
    assert on_disk["schema_version"] == CURRENT_SCHEMA_VERSION


def test_restart_does_not_re_migrate_an_already_current_pages_file(client, isolated_data_dir):
    """A restart must not treat current data as un-migrated.

    ``PageStorage._load`` snapshots the file to ``pages.json.v<n>_backup``
    before the first migration runs. If that backup appears on a plain restart,
    the version gate is being ignored and every restart is rewriting user data.
    """
    _create_page(client)

    restarted = _restart(isolated_data_dir)
    assert restarted.get("/pages").status_code == 200

    assert not list(isolated_data_dir.glob("pages.json.v*_backup"))


# ── backup export → import round-trips ──────────────────────────────────────


def test_backup_export_is_a_recognisable_backup_document(client):
    """The exported payload carries the marker its own importer requires."""
    from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION

    exported = client.get("/backup/export")

    assert exported.status_code == 200, exported.text
    payload = exported.json()
    assert payload[BACKUP_FILE_MARKER] is True
    assert payload["schema_version"] == BACKUP_SCHEMA_VERSION


def test_backup_import_restores_a_deleted_page(client, isolated_data_dir):
    """Export, delete the page, import — the page comes back unchanged."""
    page = _create_page(client)
    backup = client.get("/backup/export").json()

    assert client.delete(f"/pages/{page['id']}").status_code == 200
    assert client.get(f"/pages/{page['id']}").status_code == 404

    imported = client.post("/backup/import?reinstall_plugins=false", json=backup)
    assert imported.status_code == 200, imported.text

    restored = client.get(f"/pages/{page['id']}")
    assert restored.status_code == 200, restored.text
    assert restored.json() == page


def test_backup_import_restores_overwritten_settings(client):
    """A settings value changed after the export is rolled back by the import."""
    assert client.put("/settings/display", json={"reduce_motion": True}).status_code == 200
    backup = client.get("/backup/export").json()

    assert client.put("/settings/display", json={"reduce_motion": False}).status_code == 200
    assert client.get("/settings/display").json()["reduce_motion"] is False

    assert client.post("/backup/import?reinstall_plugins=false", json=backup).status_code == 200

    assert client.get("/settings/display").json()["reduce_motion"] is True


def test_backup_import_restores_every_data_file_byte_for_byte(client, isolated_data_dir):
    """Every file the backup format covers is restored to its exported content.

    Model-level checks can hide a field the encoder drops on the way out. This
    compares the parsed JSON of all five ``DATA_FILES`` before and after.
    """
    from src.backup.service import DATA_FILES

    page = _create_page(client)
    _create_schedule(client, page["id"])
    _create_collection(client, page["id"])
    assert client.put("/settings/display", json={"reduce_motion": True}).status_code == 200
    assert client.put("/settings/ai", json={"enabled": True, "providers": [_AI_PROVIDER]}).status_code == 200

    before = {name: json.loads((isolated_data_dir / name).read_text()) for name in DATA_FILES}
    backup = client.get("/backup/export").json()

    # Mutate every store so a no-op import cannot pass.
    assert client.delete(f"/pages/{page['id']}").status_code == 200
    assert client.put("/settings/display", json={"reduce_motion": False}).status_code == 200
    after_mutation = {name: json.loads((isolated_data_dir / name).read_text()) for name in DATA_FILES}
    assert after_mutation != before, "the mutation step changed nothing — the test proves nothing"

    assert client.post("/backup/import?reinstall_plugins=false", json=backup).status_code == 200

    after = {name: json.loads((isolated_data_dir / name).read_text()) for name in DATA_FILES}
    assert after == before


def test_restored_state_survives_a_restart(client, isolated_data_dir):
    """An import writes to disk, not just to the in-memory singletons."""
    page = _create_page(client)
    backup = client.get("/backup/export").json()

    assert client.delete(f"/pages/{page['id']}").status_code == 200
    assert client.post("/backup/import?reinstall_plugins=false", json=backup).status_code == 200

    after = _restart(isolated_data_dir).get(f"/pages/{page['id']}")

    assert after.status_code == 200, after.text
    assert after.json() == page


def test_import_rejects_a_document_that_is_not_a_backup(client, isolated_data_dir):
    """An arbitrary JSON upload must not be written over the data directory."""
    page = _create_page(client)

    response = client.post("/backup/import?reinstall_plugins=false", json={"pages": {"pages": []}})

    assert response.status_code == 400
    assert client.get(f"/pages/{page['id']}").status_code == 200, "a rejected upload still overwrote pages.json"


# ── isolation guard ─────────────────────────────────────────────────────────


def test_the_isolation_fixture_keeps_writes_out_of_the_repo_data_dir(client, isolated_data_dir):
    """Guard for #1762: these tests must never touch the developer's data/.

    If the fixture stops covering a store, that store writes into the repo and
    this assertion is the thing that notices.
    """
    repo_data = Path(__file__).resolve().parent.parent / "data"
    before = {p.name: p.stat().st_mtime_ns for p in repo_data.glob("*.json")} if repo_data.exists() else {}

    page = _create_page(client)
    _create_schedule(client, page["id"])
    _create_collection(client, page["id"])
    assert client.put("/settings/display", json={"reduce_motion": True}).status_code == 200
    assert client.put("/settings/ai", json={"enabled": True, "providers": [_AI_PROVIDER]}).status_code == 200

    assert (isolated_data_dir / "pages.json").exists(), "the fixture never redirected pages.json"
    after = {p.name: p.stat().st_mtime_ns for p in repo_data.glob("*.json")} if repo_data.exists() else {}
    assert after == before
