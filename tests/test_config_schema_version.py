"""``config.json`` is schema-versioned like every other store (Phase 2 audit).

Every store under ``data/`` records an integer ``schema_version`` and runs
ordered migrations keyed on it — except ``config.json``, whose two structural
migrations were guarded by heuristics ("is there a ``plugins.weather`` entry
yet?"). CLAUDE.md forbids exactly that for pages, and the failure mode is real:
a heuristic cannot tell "not migrated yet" from "migrated, then deliberately
changed by the user", so an uninstalled plugin with a surviving legacy
``features.*`` block was silently re-created on every boot.

These tests drive a **real pre-versioning config file**
(``tests/golden/storage/config_pre_versioning.json`` — the shape a v2-era
install actually had on disk) through a first boot and a second boot.
"""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
from pathlib import Path

import pytest

from src.config_manager import (
    CURRENT_SCHEMA_VERSION,
    MIGRATIONS,
    SCHEMA_VERSION_KEY,
    ConfigManager,
)

PRE_VERSIONING_FIXTURE = Path(__file__).parent / "golden" / "storage" / "config_pre_versioning.json"


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@contextlib.contextmanager
def captured_config_logs():
    """Collect ``src.config_manager`` INFO records WITHOUT propagating to root.

    ``caplog`` cannot be used here. It works by adding a handler to the *root*
    logger and raising the target logger's level so records reach it — and in a
    full-suite run the root logger also carries the api_server log handler,
    which re-enters ``ConfigManager()`` for every record it formats. That
    nested ``__init__`` rebinds ``_config_path`` to the default data dir (the
    documented re-entrancy hazard in ``ConfigManager.__new__``), so merely
    *observing* the migration logs would destroy the thing being observed:
    the test passed alone and failed after ``tests/test_logs.py``.

    Attaching the handler directly to ``src.config_manager`` with
    ``propagate=False`` keeps the records off root entirely.
    """
    logger = logging.getLogger("src.config_manager")
    handler = _Collect()
    old_level, old_propagate = logger.level, logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        yield handler.messages
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.propagate = old_propagate


@pytest.fixture(autouse=True)
def _no_env_plugin_overrides(monkeypatch):
    """Neutralize the #1761 read-time env overlay (CI exports WEATHER_API_KEY)."""
    from src.config_manager import ENV_PLUGIN_OVERRIDES

    for env_var in ENV_PLUGIN_OVERRIDES:
        monkeypatch.delenv(env_var, raising=False)


@pytest.fixture
def config_file(tmp_path) -> Path:
    """A real pre-versioning ``config.json`` copied into a throwaway data dir."""
    path = tmp_path / "config.json"
    shutil.copyfile(PRE_VERSIONING_FIXTURE, path)
    return path


def _boot(config_file: Path) -> ConfigManager:
    """Construct a ConfigManager as a fresh process would."""
    ConfigManager._instance = None  # type: ignore[attr-defined]
    return ConfigManager(config_path=str(config_file))


def _on_disk(config_file: Path) -> dict:
    return json.loads(config_file.read_text())


class TestVersioningMachinery:
    def test_migrations_are_ordered_and_contiguous_up_to_current(self):
        targets = [target for target, _ in MIGRATIONS]
        assert targets == sorted(targets), "MIGRATIONS must be in ascending target order"
        assert targets == list(range(1, CURRENT_SCHEMA_VERSION + 1)), (
            f"MIGRATIONS targets {targets} must cover 1..{CURRENT_SCHEMA_VERSION}"
        )

    def test_a_fresh_install_is_created_at_the_current_version(self, tmp_path):
        path = tmp_path / "config.json"
        _boot(path)
        assert _on_disk(path)[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION

    def test_a_fresh_install_writes_no_migration_backup(self, tmp_path):
        path = tmp_path / "config.json"
        _boot(path)
        assert not list(tmp_path.glob("config.json.v*_backup")), "nothing to migrate, so nothing to back up"


class TestFirstBoot:
    def test_pre_versioning_config_is_stamped_with_the_current_version(self, config_file):
        assert SCHEMA_VERSION_KEY not in _on_disk(config_file), "fixture must be pre-versioning"

        _boot(config_file)

        assert _on_disk(config_file)[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION

    def test_a_backup_of_the_pre_migration_file_is_written_before_migrating(self, config_file):
        original = config_file.read_bytes()

        _boot(config_file)

        backup = config_file.with_suffix(".json.v0_backup")
        assert backup.exists(), "no pre-migration backup was written"
        assert backup.read_bytes() == original, "backup does not hold the pre-migration bytes"

    def test_each_migration_logs_how_many_entries_it_affected(self, config_file):
        with captured_config_logs() as lines:
            _boot(config_file)

        # 4 legacy features in the fixture map to plugins (weather, date_time,
        # baywheels, guest_wifi); 1 of the resulting blocks is then renamed.
        assert "config schema migration v0->v1: 4 entries affected" in lines, lines
        assert "config schema migration v1->v2: 1 entry affected" in lines, lines

    def test_legacy_features_are_copied_into_plugins(self, config_file):
        cm = _boot(config_file)
        plugins = cm.get_all()["plugins"]

        assert plugins["weather"]["api_key"] == "example_weather_key"
        assert plugins["date_time"]["timezone"] == "America/New_York"
        assert plugins["guest_wifi"]["ssid"] == "example-ssid"
        # color_rules are excluded from the copy (manifest defaults own them)
        assert "color_rules" not in plugins["weather"]

    def test_a_plugin_the_user_already_configured_is_not_overwritten(self, config_file):
        cm = _boot(config_file)
        assert cm.get_all()["plugins"]["muni"]["api_key"] == "example_muni_key"

    def test_renamed_plugin_ids_are_applied_in_order_after_the_feature_copy(self, config_file):
        cm = _boot(config_file)
        plugins = cm.get_all()["plugins"]

        assert "baywheels" not in plugins
        assert plugins["lyft_bike_share"]["station_ids"] == ["station-0001"]
        assert "station_id" not in plugins["lyft_bike_share"]


class TestSecondBootIsANoOp:
    def test_the_second_boot_runs_no_migrations(self, config_file):
        with captured_config_logs() as first_boot_lines:
            _boot(config_file)
        assert [m for m in first_boot_lines if "config schema migration" in m], (
            "precondition: the first boot must have migrated, or this proves nothing"
        )

        with captured_config_logs() as second_boot_lines:
            _boot(config_file)

        assert not [m for m in second_boot_lines if "config schema migration" in m], (
            "migrations re-ran against an already-current config"
        )

    def test_the_second_boot_writes_no_second_backup(self, config_file):
        _boot(config_file)
        first = config_file.with_suffix(".json.v0_backup").read_bytes()

        _boot(config_file)

        assert config_file.with_suffix(".json.v0_backup").read_bytes() == first
        assert len(list(config_file.parent.glob("config.json.v*_backup"))) == 1

    def test_a_plugin_the_user_uninstalled_is_not_resurrected(self, config_file):
        """The heuristic guard's actual bug: ``features.weather`` survives an
        uninstall, so every boot silently re-created ``plugins.weather``."""
        _boot(config_file)

        stored = _on_disk(config_file)
        assert "weather" in stored["plugins"], "precondition: the first boot migrated it"
        del stored["plugins"]["weather"]
        config_file.write_text(json.dumps(stored, indent=2))

        cm = _boot(config_file)

        assert "weather" not in cm.get_all()["plugins"], (
            "a deliberately uninstalled plugin was re-created from its legacy features block"
        )
        assert "weather" in _on_disk(config_file)["features"], (
            "precondition: the legacy features block is still on disk, so only "
            "schema_version can be what stopped the re-migration"
        )

    def test_a_plugin_rename_is_not_re_applied_after_the_user_reverts_it(self, config_file):
        _boot(config_file)

        stored = _on_disk(config_file)
        stored["plugins"]["baywheels"] = {"enabled": True, "station_id": "station-0002"}
        config_file.write_text(json.dumps(stored, indent=2))

        cm = _boot(config_file)

        assert "baywheels" in cm.get_all()["plugins"], "the rename migration re-ran on an already-current config"


class TestVersionGuard:
    def test_a_config_already_at_current_version_is_left_alone(self, config_file):
        stored = _on_disk(config_file)
        stored[SCHEMA_VERSION_KEY] = CURRENT_SCHEMA_VERSION
        config_file.write_text(json.dumps(stored, indent=2))

        cm = _boot(config_file)

        assert "weather" not in cm.get_all()["plugins"], (
            "migration ran despite the file already declaring the current schema version"
        )

    def test_a_non_integer_schema_version_is_treated_as_unversioned(self, config_file):
        stored = _on_disk(config_file)
        stored[SCHEMA_VERSION_KEY] = "2"
        config_file.write_text(json.dumps(stored, indent=2))

        cm = _boot(config_file)

        assert "weather" in cm.get_all()["plugins"]
        assert _on_disk(config_file)[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION

    def test_reload_migrates_a_config_swapped_in_out_of_band(self, config_file):
        cm = _boot(config_file)
        assert _on_disk(config_file)[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION

        # A backup restore / rollback drops an older file in place.
        shutil.copyfile(PRE_VERSIONING_FIXTURE, config_file)
        cm.reload()

        assert _on_disk(config_file)[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION
        assert "weather" in cm.get_all()["plugins"]
