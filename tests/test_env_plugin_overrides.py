"""Environment variables as a read-time overlay on plugin config (issue #1761).

Historically ``_apply_env_overrides`` wrote env values into the legacy
``features.*`` section and persisted them to ``config.json``. On any install
that had already migrated features to plugins, that made ``WEATHER_API_KEY``
(and every other plugin env var) a silent no-op: the value landed in a config
branch nothing reads anymore, and it stuck around on disk even after the env
var was unset.

The contract under test here:

* An env var maps to its ``plugins.<id>.<key>`` target and is visible
  wherever plugin config is read (``get_plugin_config`` /
  ``get_all_plugin_configs`` — the choke point the registry and API use).
* The overlay wins over the stored value while the env var is set.
* Nothing is ever persisted: ``config.json`` on disk never contains the
  env value, and unsetting the env var reverts reads to the stored value.
"""

import json

import pytest

from src.config_manager import ConfigManager


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Make sure ambient env vars can't leak into these tests."""
    for var in (
        "WEATHER_API_KEY",
        "WEATHER_PROVIDER",
        "WEATHER_LOCATION",
        "MUNI_API_KEY",
        "FINNHUB_API_KEY",
        "STOCKS_SYMBOLS",
        "HOME_ASSISTANT_ENTITIES",
    ):
        monkeypatch.delenv(var, raising=False)


def _write_migrated_install(config_path, weather_config=None):
    """A config.json as it looks on an install migrated to the plugin system.

    ``plugins.weather`` is configured, the v2 migration flag is set, and no
    legacy feature blocks remain in play.
    """
    config = {
        "board": {"api_mode": "local", "local_api_key": "test_local_key", "host": "192.168.1.100"},
        "features": {},
        "general": {"timezone": "America/Los_Angeles"},
        "plugins": {
            "weather": weather_config
            or {
                "enabled": True,
                "api_key": "stored_key",
                "provider": "weatherapi",
                "location": "New York, NY",
            },
        },
        "plugin_migrations": {"v2_completed": True},
    }
    config_path.write_text(json.dumps(config))
    return config


class TestEnvOverlayOnMigratedInstall:
    def test_env_var_overrides_plugin_config_read(self, tmp_path, monkeypatch):
        """WEATHER_API_KEY must reach the live plugin config on a migrated install."""
        config_path = tmp_path / "config.json"
        _write_migrated_install(config_path)
        monkeypatch.setenv("WEATHER_API_KEY", "test_key_env")

        cm = ConfigManager(config_path=str(config_path))
        cfg = cm.get_plugin_config("weather")

        assert cfg is not None
        assert cfg["api_key"] == "test_key_env"

    def test_env_var_overrides_get_all_plugin_configs(self, tmp_path, monkeypatch):
        """The registry boots from get_all_plugin_configs — the overlay must show there too."""
        config_path = tmp_path / "config.json"
        _write_migrated_install(config_path)
        monkeypatch.setenv("WEATHER_API_KEY", "test_key_env")

        cm = ConfigManager(config_path=str(config_path))
        all_configs = cm.get_all_plugin_configs()

        assert all_configs["weather"]["api_key"] == "test_key_env"

    def test_env_value_never_persisted_and_unset_reverts(self, tmp_path, monkeypatch):
        """Env overrides are a read-time overlay: never written to disk, gone when unset."""
        config_path = tmp_path / "config.json"
        _write_migrated_install(config_path)
        monkeypatch.setenv("WEATHER_API_KEY", "test_key_env")

        cm = ConfigManager(config_path=str(config_path))
        assert cm.get_plugin_config("weather")["api_key"] == "test_key_env"

        # Nothing persisted: the env value must not appear anywhere on disk,
        # and the stored plugin value must be untouched.
        on_disk = json.loads(config_path.read_text())
        assert on_disk["plugins"]["weather"]["api_key"] == "stored_key"
        assert "test_key_env" not in config_path.read_text()

        # Unset -> the stored value returns, without any restart or reload.
        monkeypatch.delenv("WEATHER_API_KEY")
        assert cm.get_plugin_config("weather")["api_key"] == "stored_key"

    def test_overlay_only_augments_existing_plugin_entries(self, tmp_path, monkeypatch):
        """An env var for a plugin with no stored config must not conjure one up."""
        config_path = tmp_path / "config.json"
        _write_migrated_install(config_path)
        monkeypatch.setenv("MUNI_API_KEY", "muni_env_key")

        cm = ConfigManager(config_path=str(config_path))
        assert cm.get_plugin_config("muni") is None
        assert "muni" not in cm.get_all_plugin_configs()

    def test_placeholder_env_values_are_ignored(self, tmp_path, monkeypatch):
        """Unedited .env placeholders (your_*_here) must not override anything."""
        config_path = tmp_path / "config.json"
        _write_migrated_install(config_path)
        monkeypatch.setenv("WEATHER_API_KEY", "your_weather_api_key_here")

        cm = ConfigManager(config_path=str(config_path))
        assert cm.get_plugin_config("weather")["api_key"] == "stored_key"

    def test_overlay_applies_to_plugin_instances(self, tmp_path, monkeypatch):
        """Instance keys like weather:sf share the base plugin's env overrides."""
        config_path = tmp_path / "config.json"
        config = _write_migrated_install(config_path)
        config["plugins"]["weather:sf"] = {"enabled": True, "api_key": "sf_stored", "location": "San Francisco, CA"}
        config_path.write_text(json.dumps(config))
        monkeypatch.setenv("WEATHER_API_KEY", "test_key_env")

        cm = ConfigManager(config_path=str(config_path))
        assert cm.get_plugin_config("weather:sf")["api_key"] == "test_key_env"

    def test_typed_overrides_parse_int_and_list(self, tmp_path, monkeypatch):
        """Int and CSV-list env vars parse into their native types."""
        config_path = tmp_path / "config.json"
        config = _write_migrated_install(config_path)
        config["plugins"]["stocks"] = {"enabled": True, "symbols": ["GOOG"], "refresh_seconds": 300}
        config_path.write_text(json.dumps(config))
        monkeypatch.setenv("STOCKS_REFRESH_SECONDS", "600")
        monkeypatch.setenv("STOCKS_SYMBOLS", "AAPL, MSFT")

        cm = ConfigManager(config_path=str(config_path))
        stocks = cm.get_plugin_config("stocks")
        assert stocks["refresh_seconds"] == 600
        assert stocks["symbols"] == ["AAPL", "MSFT"]

    def test_invalid_numeric_override_is_ignored(self, tmp_path, monkeypatch):
        """An unparseable numeric env value must not override the stored value."""
        config_path = tmp_path / "config.json"
        config = _write_migrated_install(config_path)
        config["plugins"]["surf"] = {"enabled": True, "latitude": 37.7599}
        config_path.write_text(json.dumps(config))
        monkeypatch.setenv("SURF_LATITUDE", "not_a_float")

        cm = ConfigManager(config_path=str(config_path))
        assert cm.get_plugin_config("surf")["latitude"] == 37.7599

    def test_write_paths_can_read_stored_config_without_overlay(self, tmp_path, monkeypatch):
        """Persistence paths must be able to see the raw stored value.

        The API's read-merge-write endpoints un-mask "***" against the stored
        config; if that read returned the overlay, a routine settings save
        would persist the env secret to disk.
        """
        config_path = tmp_path / "config.json"
        _write_migrated_install(config_path)
        monkeypatch.setenv("WEATHER_API_KEY", "test_key_env")

        cm = ConfigManager(config_path=str(config_path))
        stored = cm.get_plugin_config("weather", include_env_overrides=False)
        assert stored["api_key"] == "stored_key"


class TestBoardEnvVarsUnchanged:
    def test_board_read_write_key_still_seeds_board_config(self, tmp_path, monkeypatch):
        """Board-connection env vars keep today's persist-when-empty behavior."""
        config_path = tmp_path / "config.json"
        monkeypatch.setenv("BOARD_READ_WRITE_KEY", "board_env_key")
        monkeypatch.setenv("BOARD_API_MODE", "cloud")

        cm = ConfigManager(config_path=str(config_path))
        assert cm.get_board()["cloud_key"] == "board_env_key"
        # And it persists (the documented board behavior, unlike plugin vars).
        on_disk = json.loads(config_path.read_text())
        assert on_disk["board"]["cloud_key"] == "board_env_key"
