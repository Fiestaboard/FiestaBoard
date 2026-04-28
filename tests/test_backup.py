"""Tests for the backup/restore module and its API endpoints."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.backup.service import (
    BACKUP_FILE_MARKER,
    BACKUP_SCHEMA_VERSION,
    BackupError,
    BackupService,
)


# ── unit tests for BackupService ────────────────────────────────────────────


def _seed_data_dir(data_dir: Path) -> None:
    """Populate *data_dir* with realistic JSON files for round-trip tests."""
    (data_dir / "config.json").write_text(
        json.dumps(
            {
                "board": {
                    "host": "fiestaboard.example.test",
                    "local_api_key": "test_api_key_placeholder",
                }
            }
        )
    )
    (data_dir / "settings.json").write_text(
        json.dumps({"transitions": {"strategy": "column"}})
    )
    (data_dir / "pages.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pages": [{"id": "p1", "name": "Hello", "type": "single"}],
            }
        )
    )
    (data_dir / "carousels.json").write_text(json.dumps({"carousels": []}))
    (data_dir / "schedules.json").write_text(
        json.dumps({"schedules": [], "default_page_id": None})
    )


def test_build_backup_includes_all_data_files(tmp_path):
    _seed_data_dir(tmp_path)
    service = BackupService(data_dir=tmp_path)

    backup = service.build_backup()

    assert backup[BACKUP_FILE_MARKER] is True
    assert backup["schema_version"] == BACKUP_SCHEMA_VERSION
    assert "exported_at" in backup
    assert "app_version" in backup
    assert backup["data"]["config"]["board"]["host"] == "fiestaboard.example.test"
    assert backup["data"]["pages"]["pages"][0]["id"] == "p1"
    assert backup["data"]["settings"]["transitions"]["strategy"] == "column"
    assert backup["data"]["carousels"] == {"carousels": []}
    assert backup["data"]["schedules"]["schedules"] == []
    assert isinstance(backup["installed_plugins"], list)


def test_build_backup_with_missing_files_uses_none(tmp_path):
    # Empty data dir — every key should be present with value None.
    service = BackupService(data_dir=tmp_path)

    backup = service.build_backup()

    for key in ("config", "settings", "pages", "carousels", "schedules"):
        assert backup["data"][key] is None


def test_export_to_json_is_valid_json(tmp_path):
    _seed_data_dir(tmp_path)
    service = BackupService(data_dir=tmp_path)

    raw = service.export_to_json()

    parsed = json.loads(raw)
    assert parsed[BACKUP_FILE_MARKER] is True


def test_round_trip_export_then_import(tmp_path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    _seed_data_dir(src_dir)

    backup = BackupService(data_dir=src_dir).build_backup()

    with patch("src.backup.service._reload_services", return_value=[]):
        result = BackupService(data_dir=dst_dir).import_from_dict(
            backup, reinstall_plugins=False
        )

    assert result["status"] == "success"
    assert set(result["restored_files"]) == {
        "config.json",
        "settings.json",
        "pages.json",
        "carousels.json",
        "schedules.json",
    }
    # Data was actually written to the destination.
    assert (
        json.loads((dst_dir / "config.json").read_text())["board"]["host"]
        == "fiestaboard.example.test"
    )
    assert json.loads((dst_dir / "pages.json").read_text())["pages"][0]["id"] == "p1"


def test_import_preserves_existing_files_as_pre_restore_backup(tmp_path):
    _seed_data_dir(tmp_path)
    # Make config.json's existing content distinct so we can tell it apart
    # from what's about to be restored.
    (tmp_path / "config.json").write_text(json.dumps({"marker": "OLD"}))

    backup = {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": {"config": {"marker": "NEW"}},
    }

    with patch("src.backup.service._reload_services", return_value=[]):
        result = BackupService(data_dir=tmp_path).import_from_dict(
            backup, reinstall_plugins=False
        )

    assert json.loads((tmp_path / "config.json").read_text()) == {"marker": "NEW"}

    # The original file should have been preserved with the pre-restore suffix.
    suffix = result["pre_restore_backup_suffix"]
    preserved = tmp_path / f"config.json{suffix}"
    assert preserved.exists()
    assert json.loads(preserved.read_text()) == {"marker": "OLD"}


def test_import_skips_missing_data_keys(tmp_path):
    _seed_data_dir(tmp_path)
    backup = {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": {"config": {"only": "this"}},
    }

    with patch("src.backup.service._reload_services", return_value=[]):
        result = BackupService(data_dir=tmp_path).import_from_dict(
            backup, reinstall_plugins=False
        )

    assert "config.json" in result["restored_files"]
    # All other keys absent from the backup should be reported as skipped.
    assert "pages.json" in result["skipped_files"]
    assert "schedules.json" in result["skipped_files"]


def test_import_rejects_non_dict(tmp_path):
    service = BackupService(data_dir=tmp_path)
    with pytest.raises(BackupError):
        service.import_from_dict([1, 2, 3])


def test_import_rejects_missing_marker(tmp_path):
    service = BackupService(data_dir=tmp_path)
    with pytest.raises(BackupError):
        service.import_from_dict({"schema_version": 1, "data": {}})


def test_import_rejects_newer_schema_version(tmp_path):
    service = BackupService(data_dir=tmp_path)
    with pytest.raises(BackupError):
        service.import_from_dict(
            {
                BACKUP_FILE_MARKER: True,
                "schema_version": BACKUP_SCHEMA_VERSION + 1,
                "data": {},
            }
        )


def test_import_from_json_rejects_invalid_json(tmp_path):
    service = BackupService(data_dir=tmp_path)
    with pytest.raises(BackupError):
        service.import_from_json("{not valid json")


def test_collect_installed_plugins_skips_builtins(tmp_path):
    fake_source_builtin = MagicMock(source_type="builtin", repository_url="")
    fake_source_external = MagicMock(
        source_type="external",
        repository_url="https://github.com/example/plugin.git",
    )

    fake_loader = MagicMock(
        plugin_sources={
            "date_time": fake_source_builtin,
            "weather": fake_source_external,
        }
    )
    fake_registry = MagicMock(_loader=fake_loader)

    with patch(
        "src.plugins.get_plugin_registry", return_value=fake_registry, create=True
    ):
        plugins = BackupService._collect_installed_plugins()

    assert len(plugins) == 1
    assert plugins[0]["plugin_id"] == "weather"
    assert plugins[0]["source_type"] == "external"
    assert plugins[0]["repository_url"].startswith("https://")


def test_reinstall_plugins_skips_already_installed(tmp_path):
    fake_registry = MagicMock()
    fake_registry.get_plugin.return_value = object()  # already installed
    fake_registry.install_from_git.return_value = []

    with patch(
        "src.plugins.get_plugin_registry", return_value=fake_registry, create=True
    ):
        result = BackupService._reinstall_plugins(
            [
                {
                    "plugin_id": "weather",
                    "source_type": "external",
                    "repository_url": "https://example.com/p.git",
                }
            ]
        )

    assert result["already_present"] == ["weather"]
    assert result["installed"] == []
    fake_registry.install_from_git.assert_not_called()


def test_reinstall_plugins_records_failures(tmp_path):
    fake_registry = MagicMock()
    fake_registry.get_plugin.return_value = None
    fake_registry.install_from_git.return_value = ["clone failed"]

    with patch(
        "src.plugins.get_plugin_registry", return_value=fake_registry, create=True
    ):
        result = BackupService._reinstall_plugins(
            [
                {
                    "plugin_id": "weather",
                    "source_type": "external",
                    "repository_url": "https://example.com/p.git",
                }
            ]
        )

    assert result["installed"] == []
    assert result["failed"] and result["failed"][0]["plugin_id"] == "weather"


def test_reinstall_plugins_rejects_malicious_repository_url(tmp_path):
    """Repository URLs that don't match the strict allowlist must be rejected
    *before* reaching the install pipeline (defence against
    py/command-line-injection)."""
    fake_registry = MagicMock()
    fake_registry.get_plugin.return_value = None

    with patch(
        "src.plugins.get_plugin_registry", return_value=fake_registry, create=True
    ):
        result = BackupService._reinstall_plugins(
            [
                {
                    "plugin_id": "weather",
                    "source_type": "external",
                    # Leading dash + space would be highly suspicious — must
                    # be rejected by the URL allowlist regex.
                    "repository_url": "--upload-pack=evil https://example.com/p.git",
                },
                {
                    # Plugin id with shell metacharacter must also be rejected.
                    "plugin_id": "weather; rm -rf /",
                    "source_type": "external",
                    "repository_url": "https://example.com/p.git",
                },
            ]
        )

    assert result["installed"] == []
    assert result["attempted"] == []
    assert len(result["failed"]) == 2
    fake_registry.install_from_git.assert_not_called()


# ── API endpoint tests ──────────────────────────────────────────────────────


@pytest.fixture()
def client_with_data_dir(tmp_path):
    """TestClient backed by a BackupService pointed at *tmp_path*."""
    from src.api_server import app
    from src.backup import service as backup_service_mod

    _seed_data_dir(tmp_path)
    test_service = BackupService(data_dir=tmp_path)
    backup_service_mod._backup_service = test_service
    try:
        with patch.object(backup_service_mod, "_reload_services", return_value=[]):
            yield TestClient(app), tmp_path
    finally:
        backup_service_mod._backup_service = None


def test_export_endpoint_returns_attachment(client_with_data_dir):
    client, _ = client_with_data_dir

    response = client.get("/backup/export")

    assert response.status_code == 200
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "fiestaboard-backup-" in disposition
    body = response.json()
    assert body[BACKUP_FILE_MARKER] is True
    assert body["data"]["config"]["board"]["host"] == "fiestaboard.example.test"


def test_import_endpoint_round_trip(client_with_data_dir):
    client, data_dir = client_with_data_dir

    backup = client.get("/backup/export").json()

    # Mutate a value in the backup so we can confirm import wrote it.
    backup["data"]["config"]["board"]["host"] = "new-host.example.test"

    response = client.post(
        "/backup/import?reinstall_plugins=false", json=backup
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert "config.json" in body["restored_files"]
    assert (
        json.loads((data_dir / "config.json").read_text())["board"]["host"]
        == "new-host.example.test"
    )


def test_import_endpoint_rejects_invalid_payload(client_with_data_dir):
    client, _ = client_with_data_dir

    response = client.post(
        "/backup/import", json={"definitely": "not a backup"}
    )

    assert response.status_code == 400
    assert "marker" in response.json()["detail"].lower()
