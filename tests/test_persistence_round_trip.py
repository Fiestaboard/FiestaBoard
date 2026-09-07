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

Data isolation (#1762): every store's default path now resolves through
``src.paths.get_data_dir()``, which honors ``FIESTABOARD_DATA_DIR`` — set to a
throwaway tmp dir by the autouse ``_isolated_data_dir`` fixture in
``tests/conftest.py``. ``isolated_data_dir`` below is a thin alias for it, and
``_restart`` only needs to drop the singletons: the next construction lands in
the same isolated dir via the seam, with no constructor rebinding.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── isolation ───────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_data_dir(_isolated_data_dir: Path) -> Path:
    """The throwaway data dir every default store path resolves into.

    Alias for conftest's autouse ``_isolated_data_dir`` (#1762): the env seam
    plus the singleton drops it performs are the whole isolation story now.
    Kept as a named fixture so these tests read as "this one asserts against
    the data dir" rather than depending on an autouse underscore fixture.
    """
    return _isolated_data_dir


@pytest.fixture
def client(isolated_data_dir):
    """A TestClient whose every request resolves services from the temp dir."""
    from src.api_server import app

    return TestClient(app)


def _restart(data_dir: Path) -> TestClient:
    """Throw away all in-memory state and return a client reading from disk.

    Route handlers resolve their services per request through the singleton
    getters, so dropping the singletons is precisely what a container restart
    does: the next request rebuilds each store by parsing the JSON files —
    which the ``FIESTABOARD_DATA_DIR`` seam keeps pointed at *data_dir*.
    """
    from src.api_server import app
    from tests.conftest import _drop_all_singletons

    _drop_all_singletons()
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


def _create_panel(client: TestClient, name: str = "Kitchen TV") -> dict:
    """Create a panel (and, implicitly, its backing virtual board).

    ``panels.json`` joined ``DATA_FILES`` with the FiestaPanel work, so the
    two whole-store guards below have to write it like every other store.
    """
    response = client.post("/panels", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["panel"]


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
    _create_panel(client)
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

    # The v2->v3 plugin migration stamps `plugin_migrations.v2_completed` the
    # first time the plugin registry is built against a config (#1817 routes
    # the restore path through `PluginRegistry.initialize(force=True)` in
    # `_reload_services` for exactly that reason — pinned by
    # `test_backup_import_is_not_clobbered_by_the_pre_restore_config_manager`).
    # Under per-test isolation (#1762) each test builds its registry fresh, so
    # the flag lands in config.json during this test's own setup — *before*
    # the export. The exported document therefore already carries it, and the
    # restore + reload re-derives the identical value: the round trip is a
    # byte-for-byte no-op, with nothing added at all.
    assert before["config.json"].get("plugin_migrations") == {"v2_completed": True}, (
        "expected the v2 plugin migration to have stamped this test's config during setup"
    )
    added = set(after["config.json"]) - set(before["config.json"])
    assert added == set(), f"restore added unexpected config.json keys: {sorted(added)}"
    assert after == before


def test_backup_import_is_not_clobbered_by_the_pre_restore_config_manager(client, isolated_data_dir):
    """The plugin-registry reload that follows a restore must read the restored config.

    `src.backup.service._reload_services` reloads ConfigManager from disk
    *before* it calls `PluginRegistry.initialize(force=True)` (#1817). That
    order is load-bearing and easy to lose: the registry reload runs the v2->v3
    plugin migration, which writes back through ConfigManager. Run it against
    the pre-restore in-memory config and the write lands on top of the file the
    restore just produced — the "an upgrade stranded my plugin configs" failure
    shape of #948/#1102/#1301, reached this time through a restore.

    It is also the reason `test_backup_import_restores_every_data_file_byte_for_byte`
    tolerates a re-derived `plugin_migrations` key: the migration is *supposed*
    to run here, over restored data.
    """
    assert client.put("/settings/ai", json={"enabled": True, "providers": [_AI_PROVIDER]}).status_code == 200
    backup = client.get("/backup/export").json()

    # Diverge the live config (and the live ConfigManager) from the backup.
    assert client.put("/settings/ai", json={"enabled": False, "providers": []}).status_code == 200
    assert json.loads((isolated_data_dir / "config.json").read_text())["ai_providers"]["enabled"] is False

    assert client.post("/backup/import?reinstall_plugins=false", json=backup).status_code == 200

    on_disk = json.loads((isolated_data_dir / "config.json").read_text())
    assert on_disk["ai_providers"]["enabled"] is True, (
        "the post-restore reload wrote the pre-restore config back over the restored one"
    )
    assert [p["id"] for p in on_disk["ai_providers"]["providers"]] == [_AI_PROVIDER["id"]]


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

    Every store is written with a marker unique to this run, then the repo's
    ``data/`` is searched for it. Looking for *our own* content is what makes
    this order-independent, the way the sibling guard in
    ``test_plugin_lifecycle_round_trip.py`` does it.

    A wholesale comparison of the repo's files — of mtimes or of bytes — would
    be a cross-worker race instead of a guard: other suites in the same
    ``-n auto`` run legitimately write ``<repo>/data/config.json``
    (``test_config_manager.py`` does), so it would fail on their writes, not on
    a leak from here. Verified: swapping this for a byte comparison fails 5 runs
    in 6 alongside ``tests/test_config_manager.py``.
    """
    from src.backup.service import DATA_FILES

    marker = f"isolation-guard-{uuid.uuid4().hex}"
    repo_data = Path(__file__).resolve().parent.parent / "data"

    page = _create_page(client, name=marker)  # pages.json
    _create_schedule(client, page["id"])  # schedules.json
    _create_collection(client, page["id"])  # collections.json
    assert client.put("/settings/mqtt", json={"broker_host": marker}).status_code == 200  # settings.json
    ai = client.put("/settings/ai", json={"enabled": True, "providers": [{**_AI_PROVIDER, "name": marker}]})
    assert ai.status_code == 200, ai.text  # config.json
    _create_panel(client, name=marker)  # panels.json

    # Both tokens are unique to this run: the marker string this test chose,
    # and the id the API minted for its page.
    written_token = {
        "pages.json": marker,
        "schedules.json": page["id"],
        "collections.json": page["id"],
        "settings.json": marker,
        "config.json": marker,
        "panels.json": marker,
    }
    assert set(written_token) == set(DATA_FILES), "DATA_FILES changed — give the new file a token"

    for name, token in written_token.items():
        written = isolated_data_dir / name
        assert written.exists(), f"the fixture never redirected {name}"
        assert token in written.read_text(), f"{name} did not receive this test's write"

    for name in DATA_FILES:
        leaked = repo_data / name
        if leaked.exists():
            text = leaked.read_text()
            assert marker not in text, f"this test's data leaked into <repo>/data/{name}"
            assert page["id"] not in text, f"this test's page leaked into <repo>/data/{name}"
