"""Safety and store-compatibility contracts for the isolated audit fixture.

These exercise the real provisioner and domain readers, never a running hub.
The production browser preflight is still required after boot.
"""

import hashlib
import json
import stat
from pathlib import Path

import pytest

from scripts.prod_a11y_seed import create_dataset


@pytest.fixture
def parent(tmp_path):
    path = tmp_path / "audit-datasets"
    path.mkdir()
    return path.resolve()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_requires_explicit_synthetic_acknowledgment_before_writing(parent):
    with pytest.raises(ValueError, match="synthetic"):
        create_dataset(parent, "prod-a11y-empty-one", acknowledge_synthetic=False)
    assert list(parent.iterdir()) == []


@pytest.mark.parametrize(
    "dataset_id",
    ["", "existing", "../prod-a11y-escape", "prod-a11y-a/b", "/prod-a11y-abs", "prod-a11y-Upper", "prod-a11y-"],
)
def test_rejects_non_child_or_invalid_dataset_id_without_writing(parent, dataset_id):
    with pytest.raises(ValueError, match="dataset"):
        create_dataset(parent, dataset_id, acknowledge_synthetic=True)
    assert list(parent.iterdir()) == []


def test_requires_existing_absolute_parent(parent, monkeypatch):
    monkeypatch.chdir(parent.parent)
    with pytest.raises(ValueError, match="absolute"):
        create_dataset(Path(parent.name), "prod-a11y-empty-one", acknowledge_synthetic=True)
    absent = parent / "absent"
    with pytest.raises(FileNotFoundError):
        create_dataset(absent, "prod-a11y-empty-one", acknowledge_synthetic=True)
    assert not absent.exists()


@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "broken-symlink"])
def test_never_replaces_existing_destination(parent, kind):
    destination = parent / "prod-a11y-existing"
    outside = parent.parent / "unrelated-user-data"
    outside.mkdir()
    sentinel = outside / "config.json"
    sentinel.write_text("keep user data", encoding="utf-8")
    if kind == "directory":
        destination.mkdir()
        (destination / "keep").write_bytes(b"existing evidence")
    elif kind == "file":
        destination.write_bytes(b"existing evidence")
    else:
        destination.symlink_to(outside if kind == "symlink" else parent / "absent")
    before = list(parent.iterdir())
    with pytest.raises(FileExistsError):
        create_dataset(parent, destination.name, acknowledge_synthetic=True)
    assert list(parent.iterdir()) == before
    assert sentinel.read_text(encoding="utf-8") == "keep user data"
    if kind == "directory":
        assert (destination / "keep").read_bytes() == b"existing evidence"
        assert list(destination.iterdir()) == [destination / "keep"]
    elif kind == "file":
        assert destination.read_bytes() == b"existing evidence"
    else:
        assert destination.is_symlink()


def test_refuses_a_symlinked_parent_or_ancestor(parent):
    alias = parent.parent / "alias"
    alias.symlink_to(parent, target_is_directory=True)
    child = parent / "child"
    child.mkdir()
    for candidate in (alias, alias / "child"):
        with pytest.raises(ValueError, match="canonical"):
            create_dataset(candidate, "prod-a11y-empty-one", acknowledge_synthetic=True)
    assert list(child.iterdir()) == []


def test_writes_empty_synthetic_stores_and_separate_initial_hash_manifest(parent):
    dataset = create_dataset(parent, "prod-a11y-empty-one", acknowledge_synthetic=True)
    data = dataset / "data"
    manifest_path = dataset / "seed-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["synthetic_only"] is True
    assert manifest["dataset_id"] == dataset.name
    assert manifest["source_review"]["sha"] == "83236253aa8103db856b7efa456e088b9c9ec548"
    assert manifest["source_review"]["version"] == "11.0.0-alpha.3"
    assert manifest["boot_verified"] is False
    assert set(manifest["files"]) == {p.name for p in data.iterdir()}
    assert (dataset / "seed-manifest.sha256").read_text().strip() == hashlib.sha256(manifest_bytes).hexdigest()
    for filename, facts in manifest["files"].items():
        raw = (data / filename).read_bytes()
        assert facts == {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    for filename, key in (
        ("pages.json", "pages"),
        ("collections.json", "collections"),
        ("schedules.json", "schedules"),
        ("panels.json", "panels"),
    ):
        assert read_json(data / filename)[key] == []
    config = read_json(data / "config.json")
    assert config["plugins"] == {}
    assert config["ai_providers"] == {"enabled": False, "providers": [], "default_provider_id": None}
    settings = read_json(data / "settings.json")
    assert settings["plugins"]["auto_update"] is False
    assert settings["mqtt"]["enabled"] is False
    assert settings["wizard"]["state"] == "completed"
    assert settings["active_page"] == {"page_id": None, "by_board": {}}
    assert len(settings["board"]["boards"]) == 1
    board = settings["board"]["boards"][0]
    assert board["output"] == "fiestapanel"
    assert board["output_config"] == {}
    assert board["id"] == "prod-a11y-synthetic-board"
    assert board["schedule_enabled"] is False
    assert board["auto_restore"] is False
    assert read_json(data / "auth.json")["auth_pref"] == "disabled"
    assert read_json(data / "auth.json")["users"] == []
    assert read_json(data / ".system-update.json")["auto_update_interval"] == "manual"
    assert not (data / "settings_restore_notice.json").exists()
    assert stat.S_IMODE((data / "auth.json").stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o444
    # Boot may mutate mounted data; the evidence manifest is outside that mount.
    (data / "config.json").write_text('{"boot_changed": true}\n', encoding="utf-8")
    assert manifest_path.read_bytes() == manifest_bytes


def test_seed_is_readable_as_configured_empty_alpha3_compatible_stores(parent, monkeypatch):
    from src.auth.service import AuthService
    from src.collections.storage import CollectionStorage
    from src.config_api import service as config_api
    from src.config_manager import ConfigManager
    from src.pages.storage import PageStorage
    from src.schedules.storage import ScheduleStorage
    from src.settings import service as settings_service

    dataset = create_dataset(parent, "prod-a11y-domain-read", acknowledge_synthetic=True)
    data = dataset / "data"
    monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(data))
    for name in (
        "BOARD_READ_WRITE_KEY",
        "FB_READ_WRITE_KEY",
        "BOARD_LOCAL_API_KEY",
        "FB_LOCAL_API_KEY",
        "BOARD_HOST",
        "FB_HOST",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VERSION", "11.0.0-alpha.3")
    settings = settings_service.SettingsService(data / "settings.json")
    monkeypatch.setattr(settings_service, "get_settings_service", lambda: settings)
    config = ConfigManager(config_path=data / "config.json")
    monkeypatch.setattr(config_api, "get_config_manager", lambda: config)
    monkeypatch.setattr(config_api, "get_settings_service", lambda: settings)
    validity = config_api.determine_config_validity()
    assert validity.valid is True
    assert validity.is_first_run is False
    assert validity.errors == []
    assert validity.missing_fields == []
    assert settings.get_restore_notice() is None
    assert PageStorage(str(data / "pages.json")).list_all() == []
    assert CollectionStorage(str(data / "collections.json")).list_all() == []
    assert ScheduleStorage(str(data / "schedules.json")).list_all() == []
    auth = AuthService(data / "auth.json")
    assert auth.get_auth_preference() == "disabled"
    assert auth.has_user() is False
