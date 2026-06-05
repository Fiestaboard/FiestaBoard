"""Tests for automatic v1 -> v2 config migration.

Verifies that a legacy config (features-only, no plugins section) is
automatically migrated to the v2 plugin format on startup, and that
pages/schedules/general settings are preserved.
"""

import json
from pathlib import Path

import pytest

from src.config_manager import (
    DEFAULT_CONFIG,
    FEATURE_TO_PLUGIN_MAP,
    MIGRATION_EXCLUDED_FIELDS,
    ConfigManager,
)


def _reset_singleton():
    """Reset the ConfigManager singleton so a fresh instance can be created."""
    ConfigManager._instance = None


def _make_v1_config(**overrides):
    """Build a realistic v1 config (features populated, no plugins section)."""
    config = {
        "board": {
            "api_mode": "local",
            "local_api_key": "test-key-123",
            "host": "192.168.1.100",
        },
        "features": {
            "weather": {
                "enabled": True,
                "api_key": "weather-key-abc",
                "provider": "weatherapi",
                "location": "New York, NY",
                "refresh_seconds": 300,
                "color_rules": {
                    "temp": [
                        {"condition": ">=", "value": 90, "color": "red"},
                    ],
                },
            },
            "date_time": {
                "enabled": True,
                "timezone": "America/New_York",
                "color_rules": {},
            },
            "muni": {
                "enabled": True,
                "api_key": "muni-key-xyz",
                "stop_codes": ["15726", "15727"],
                "stop_names": ["Market & Castro", "Church & Duboce"],
                "refresh_seconds": 60,
                "color_rules": {},
            },
            "stocks": {
                "enabled": True,
                "finnhub_api_key": "finnhub-key",
                "symbols": ["AAPL", "GOOG"],
                "time_window": "1 Day",
                "refresh_seconds": 300,
                "color_rules": {
                    "change_percent": [
                        {"condition": ">", "value": 0, "color": "green"},
                    ],
                },
            },
            "guest_wifi": {
                "enabled": False,
                "ssid": "",
                "password": "",
                "color_rules": {},
            },
            "silence_schedule": {
                "enabled": True,
                "start_time": "22:00+00:00",
                "end_time": "06:00+00:00",
            },
        },
        "general": {
            "timezone": "America/New_York",
            "refresh_interval_seconds": 300,
            "output_target": "board",
        },
    }
    config.update(overrides)
    return config


@pytest.fixture(autouse=True)
def _clean_singleton():
    """Ensure each test gets a fresh ConfigManager."""
    _reset_singleton()
    yield
    _reset_singleton()


@pytest.fixture()
def v1_config_path(tmp_path):
    """Write a v1 config to a temp file and return the path."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(_make_v1_config(), indent=2))
    return str(cfg_path)


class TestAutoMigration:
    """Tests for _auto_migrate_features_to_plugins."""

    def test_v1_features_copied_to_plugins(self, v1_config_path):
        """Enabled features should appear in the plugins section after init."""
        cm = ConfigManager(config_path=v1_config_path)

        plugins = cm.get_all_plugin_configs()
        assert "weather" in plugins
        assert "date_time" in plugins
        assert "muni" in plugins
        assert "stocks" in plugins

    def test_plugin_configs_match_feature_values(self, v1_config_path):
        """Migrated plugin config should carry over the feature values."""
        cm = ConfigManager(config_path=v1_config_path)

        weather = cm.get_plugin_config("weather")
        assert weather["enabled"] is True
        assert weather["api_key"] == "weather-key-abc"
        assert weather["location"] == "New York, NY"

        muni = cm.get_plugin_config("muni")
        assert muni["stop_codes"] == ["15726", "15727"]
        assert muni["api_key"] == "muni-key-xyz"

    def test_color_rules_excluded(self, v1_config_path):
        """color_rules should NOT be copied into plugin configs."""
        cm = ConfigManager(config_path=v1_config_path)

        weather = cm.get_plugin_config("weather")
        assert "color_rules" not in weather

        stocks = cm.get_plugin_config("stocks")
        assert "color_rules" not in stocks

    def test_silence_schedule_not_migrated(self, v1_config_path):
        """silence_schedule is a system feature, not a plugin."""
        cm = ConfigManager(config_path=v1_config_path)

        assert cm.get_plugin_config("silence_schedule") is None

    def test_disabled_features_still_migrated(self, v1_config_path):
        """Even disabled features should be migrated so they're visible in the UI."""
        cm = ConfigManager(config_path=v1_config_path)

        wifi = cm.get_plugin_config("guest_wifi")
        assert wifi is not None
        assert wifi["enabled"] is False

    def test_features_section_preserved(self, v1_config_path):
        """The original features section should not be removed."""
        cm = ConfigManager(config_path=v1_config_path)

        full = cm.get_all()
        assert "features" in full
        assert "weather" in full["features"]

    def test_idempotent(self, v1_config_path):
        """Running init twice should not duplicate or overwrite plugin configs."""
        cm = ConfigManager(config_path=v1_config_path)
        weather_first = cm.get_plugin_config("weather")

        # Simulate a restart
        _reset_singleton()
        cm2 = ConfigManager(config_path=v1_config_path)
        weather_second = cm2.get_plugin_config("weather")

        assert weather_first == weather_second

    def test_existing_plugins_not_overwritten(self, tmp_path):
        """If a plugin already exists, the feature should NOT overwrite it."""
        config = _make_v1_config()
        config["plugins"] = {
            "weather": {
                "enabled": True,
                "api_key": "already-configured-key",
                "provider": "openweathermap",
                "location": "London, UK",
            },
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config, indent=2))

        cm = ConfigManager(config_path=str(cfg_path))

        weather = cm.get_plugin_config("weather")
        assert weather["api_key"] == "already-configured-key"
        assert weather["location"] == "London, UK"

    def test_backup_created(self, v1_config_path):
        """A .v1_backup file should be created before migration."""
        ConfigManager(config_path=v1_config_path)

        backup = Path(v1_config_path).with_suffix(".json.v1_backup")
        assert backup.exists()

        original = json.loads(backup.read_text())
        assert "plugins" not in original or original["plugins"] == {}

    def test_backup_not_overwritten_on_restart(self, v1_config_path):
        """The backup should not be overwritten on subsequent starts."""
        ConfigManager(config_path=v1_config_path)
        backup = Path(v1_config_path).with_suffix(".json.v1_backup")
        first_content = backup.read_text()

        _reset_singleton()

        config_data = json.loads(Path(v1_config_path).read_text())
        config_data["general"]["timezone"] = "Europe/London"
        Path(v1_config_path).write_text(json.dumps(config_data))

        ConfigManager(config_path=v1_config_path)
        assert backup.read_text() == first_content


class TestNoMigrationNeeded:
    """Tests for configs that should NOT trigger migration."""

    def test_fresh_install_no_migration(self, tmp_path):
        """A brand new config (no features configured) should not migrate."""
        cfg_path = tmp_path / "config.json"
        cm = ConfigManager(config_path=str(cfg_path))

        plugins = cm.get_all_plugin_configs()
        assert plugins == {}

        backup = cfg_path.with_suffix(".json.v1_backup")
        assert not backup.exists()

    def test_already_v2_no_migration(self, tmp_path):
        """A config that already has plugins should not re-migrate."""
        config = {
            "plugins": {
                "weather": {
                    "enabled": True,
                    "api_key": "my-key",
                },
            },
            "features": {
                "weather": {
                    "enabled": True,
                    "api_key": "old-key",
                    "color_rules": {},
                },
            },
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config, indent=2))

        cm = ConfigManager(config_path=str(cfg_path))

        weather = cm.get_plugin_config("weather")
        assert weather["api_key"] == "my-key"


class TestGeneralAndSystemPreservation:
    """Verify non-plugin data survives migration."""

    def test_general_settings_preserved(self, v1_config_path):
        cm = ConfigManager(config_path=v1_config_path)

        general = cm.get_general()
        assert general["timezone"] == "America/New_York"
        assert general["refresh_interval_seconds"] == 300
        assert general["output_target"] == "board"

    def test_board_settings_preserved(self, v1_config_path):
        cm = ConfigManager(config_path=v1_config_path)

        board = cm.get_board()
        assert board["local_api_key"] == "test-key-123"
        assert board["host"] == "192.168.1.100"

    def test_silence_schedule_preserved_in_features(self, v1_config_path):
        cm = ConfigManager(config_path=v1_config_path)

        silence = cm.get_feature("silence_schedule")
        assert silence["enabled"] is True
        assert silence["start_time"] == "22:00+00:00"
        assert silence["end_time"] == "06:00+00:00"


class TestMigrationMapping:
    """Verify the feature-to-plugin mapping covers all expected features."""

    def test_all_non_system_features_mapped(self):
        """Every feature in DEFAULT_CONFIG except silence_schedule has a mapping."""
        default_features = set(DEFAULT_CONFIG.get("features", {}).keys())
        mapped_features = set(FEATURE_TO_PLUGIN_MAP.keys())
        system_features = {"silence_schedule"}

        unmapped = default_features - mapped_features - system_features
        assert unmapped == set(), f"Features without plugin mapping: {unmapped}"

    def test_color_rules_in_excluded_fields(self):
        assert "color_rules" in MIGRATION_EXCLUDED_FIELDS


class TestPartialV1Config:
    """Test migration with configs that only have some features configured."""

    def test_partial_features_migrated(self, tmp_path):
        """Only features present in config should be migrated."""
        config = {
            "features": {
                "weather": {
                    "enabled": True,
                    "api_key": "test-key",
                    "color_rules": {},
                },
            },
            "general": {"timezone": "UTC"},
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config, indent=2))

        cm = ConfigManager(config_path=str(cfg_path))

        assert cm.get_plugin_config("weather") is not None
        assert cm.get_plugin_config("muni") is None

    def test_empty_feature_not_migrated(self, tmp_path):
        """A feature with an empty dict should not create a plugin entry."""
        config = {
            "features": {
                "weather": {},
            },
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config, indent=2))

        cm = ConfigManager(config_path=str(cfg_path))

        assert cm.get_plugin_config("weather") is None


class TestConfigPersistence:
    """Verify migrated config is persisted to disk."""

    def test_migration_saved_to_disk(self, v1_config_path):
        ConfigManager(config_path=v1_config_path)

        on_disk = json.loads(Path(v1_config_path).read_text())
        assert "plugins" in on_disk
        assert "weather" in on_disk["plugins"]
        assert on_disk["plugins"]["weather"]["api_key"] == "weather-key-abc"

    def test_migration_survives_restart(self, v1_config_path):
        """After migration + restart, plugins should still be there."""
        ConfigManager(config_path=v1_config_path)
        _reset_singleton()

        cm2 = ConfigManager(config_path=v1_config_path)
        assert cm2.get_plugin_config("weather") is not None
        assert cm2.get_plugin_config("muni") is not None


class TestPluginIdRename:
    """Tests for one-shot plugin id renames (e.g. baywheels -> lyft_bike_share)."""

    def test_baywheels_renamed_to_lyft_bike_share(self, tmp_path):
        """plugins.baywheels should be renamed to plugins.lyft_bike_share."""
        config = {
            "plugins": {
                "baywheels": {
                    "enabled": True,
                    "station_ids": ["123", "456"],
                    "refresh_seconds": 90,
                },
            },
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        cm = ConfigManager(config_path=str(cfg_path))

        assert cm.get_plugin_config("baywheels") is None
        lyft = cm.get_plugin_config("lyft_bike_share")
        assert lyft is not None
        assert lyft["enabled"] is True
        assert lyft["station_ids"] == ["123", "456"]
        assert lyft["refresh_seconds"] == 90
        # gbfs_base_url default should be seeded
        assert lyft["gbfs_base_url"] == "https://gbfs.baywheels.com/gbfs/en"

    def test_baywheels_legacy_station_id_promoted(self, tmp_path):
        """A user with only the legacy singular station_id should keep that station."""
        config = {
            "plugins": {
                "baywheels": {
                    "enabled": True,
                    "station_id": "abc-1",
                    "station_name": "Market St",
                    "station_ids": [],
                    "refresh_seconds": 60,
                },
            },
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        cm = ConfigManager(config_path=str(cfg_path))

        lyft = cm.get_plugin_config("lyft_bike_share")
        assert lyft is not None
        assert lyft["station_ids"] == ["abc-1"]
        # Deprecated singular fields removed
        assert "station_id" not in lyft
        assert "station_name" not in lyft

    def test_baywheels_rename_preserves_existing_lyft_bike_share(self, tmp_path):
        """If both ids exist, the new id wins and the old one is dropped."""
        config = {
            "plugins": {
                "baywheels": {
                    "enabled": True,
                    "station_ids": ["old"],
                    "refresh_seconds": 60,
                },
                "lyft_bike_share": {
                    "enabled": True,
                    "station_ids": ["new"],
                    "refresh_seconds": 120,
                    "gbfs_base_url": "https://gbfs.citibikenyc.com/gbfs/en",
                },
            },
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        cm = ConfigManager(config_path=str(cfg_path))

        assert cm.get_plugin_config("baywheels") is None
        lyft = cm.get_plugin_config("lyft_bike_share")
        assert lyft["station_ids"] == ["new"]
        assert lyft["refresh_seconds"] == 120
        assert lyft["gbfs_base_url"] == "https://gbfs.citibikenyc.com/gbfs/en"

    def test_baywheels_rename_idempotent(self, tmp_path):
        """A second startup must not recreate or alter the renamed entry."""
        config = {
            "plugins": {
                "baywheels": {
                    "enabled": True,
                    "station_ids": ["123"],
                    "refresh_seconds": 60,
                },
            },
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        cm = ConfigManager(config_path=str(cfg_path))
        first = cm.get_plugin_config("lyft_bike_share")

        _reset_singleton()
        cm2 = ConfigManager(config_path=str(cfg_path))
        second = cm2.get_plugin_config("lyft_bike_share")

        assert first == second
        assert cm2.get_plugin_config("baywheels") is None

    def test_no_rename_when_old_id_absent(self, tmp_path):
        """Configs with no obsolete plugin id should be left untouched."""
        config = {
            "plugins": {
                "weather": {"enabled": True, "api_key": "x"},
            },
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        cm = ConfigManager(config_path=str(cfg_path))

        assert cm.get_plugin_config("baywheels") is None
        assert cm.get_plugin_config("lyft_bike_share") is None
        assert cm.get_plugin_config("weather")["api_key"] == "x"

    def test_baywheels_feature_then_rename_chain(self, tmp_path):
        """v1 features.baywheels should migrate to plugins, then rename to lyft_bike_share."""
        config = _make_v1_config()
        config["features"]["baywheels"] = {
            "enabled": True,
            "station_id": "xyz",
            "station_name": "Embarcadero",
            "station_ids": [],
            "refresh_seconds": 75,
            "color_rules": {},
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        cm = ConfigManager(config_path=str(cfg_path))

        # Old id should not exist; new one should, with promoted station id
        assert cm.get_plugin_config("baywheels") is None
        lyft = cm.get_plugin_config("lyft_bike_share")
        assert lyft is not None
        assert lyft["enabled"] is True
        assert lyft["station_ids"] == ["xyz"]
        assert lyft["refresh_seconds"] == 75
        assert "station_id" not in lyft
        assert "station_name" not in lyft
