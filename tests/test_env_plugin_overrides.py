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
import logging
import re
from pathlib import Path

import pytest
from dotenv import dotenv_values

from src import config_manager as config_manager_module
from src.config_manager import ENV_PLUGIN_OVERRIDES, ConfigManager

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Make sure ambient env vars can't leak into these tests.

    CI exports ``WEATHER_API_KEY`` (and a developer shell may export more), so
    every plugin override variable is cleared, not just the ones named here.
    The once-per-variable override-warning memory is reset too, so one test's
    warning cannot suppress the next test's.
    """
    for var in ENV_PLUGIN_OVERRIDES:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(config_manager_module, "_warned_env_overrides", set(), raising=False)


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

    def test_overlay_never_applies_to_named_instances(self, tmp_path, monkeypatch):
        """Base env vars must not clobber ``base:label`` instances.

        Reversed from ``test_overlay_applies_to_plugin_instances`` (#1864
        review): inheriting the base plugin's overrides meant a years-inert
        ``WEATHER_LOCATION`` in someone's compose file would, on upgrade,
        override the one setting that makes ``weather:sf`` a different
        instance — every named instance snapping to the base env value. Env
        vars are named for the base plugin, so they scope to the base plugin
        only; instances keep their stored values.
        """
        config_path = tmp_path / "config.json"
        config = _write_migrated_install(config_path)
        config["plugins"]["weather:sf"] = {"enabled": True, "api_key": "sf_stored", "location": "San Francisco, CA"}
        config_path.write_text(json.dumps(config))
        monkeypatch.setenv("WEATHER_API_KEY", "test_key_env")
        monkeypatch.setenv("WEATHER_LOCATION", "Env City")

        cm = ConfigManager(config_path=str(config_path))
        instance = cm.get_plugin_config("weather:sf")
        assert instance["api_key"] == "sf_stored"
        assert instance["location"] == "San Francisco, CA"
        # The base plugin still gets the overlay.
        base = cm.get_plugin_config("weather")
        assert base["api_key"] == "test_key_env"
        assert base["location"] == "Env City"

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


# ── #2108: values copied from env.example must not override the UI ─────────
#
# Every plugin value env.example shipped up to v9.10.0, verbatim — the right-
# hand side of the line, inline comment and all. Kept literal here (not read
# from the production constant) so the test pins the real historical file:
# an install that ran ``cp env.example .env`` before the fix still has these
# exact lines. API-key placeholders (``your_*_here``) are left out; the
# existing pattern check already covers them.
OLD_ENV_EXAMPLE_PLUGIN_LINES = {
    "WEATHER_PROVIDER": "weatherapi  # Options: weatherapi, openweathermap",
    "WEATHER_LOCATION": "San Francisco, CA",
    "GUEST_WIFI_SSID": "GuestNetwork",
    "GUEST_WIFI_PASSWORD": "YourPasswordHere",
    "GUEST_WIFI_REFRESH_SECONDS": "60",
    "HOME_ASSISTANT_BASE_URL": "http://192.168.1.100:8123",
    "HOME_ASSISTANT_ENTITIES": (
        '[{"entity_id": "binary_sensor.front_door", "name": "Front Door"}, '
        '{"entity_id": "cover.garage_door", "name": "Garage"}]'
    ),
    "HOME_ASSISTANT_TIMEOUT": "5",
    "HOME_ASSISTANT_REFRESH_SECONDS": "30",
    "STAR_TREK_QUOTES_RATIO": "3:5:9",
    "MUNI_REFRESH_SECONDS": "60",
    "TRAFFIC_REFRESH_SECONDS": "300",
    "BAYWHEELS_REFRESH_SECONDS": "60",
    "SURF_LATITUDE": "37.7599  # Ocean Beach, SF (default)",
    "SURF_LONGITUDE": "-122.5121  # Ocean Beach, SF (default)",
    "SURF_REFRESH_SECONDS": "600  # 10 minutes",
    "PURPLEAIR_SENSOR_ID": "  # Optional: specific sensor ID",
    "AIR_FOG_LATITUDE": "37.7749  # San Francisco (default)",
    "AIR_FOG_LONGITUDE": "-122.4194  # San Francisco (default)",
    "AIR_FOG_REFRESH_SECONDS": "300  # 5 minutes",
    "STOCKS_SYMBOLS": 'GOOG  # Comma-separated list of stock symbols (max 5, e.g., "GOOG,AAPL,MSFT,TSLA,NVDA")',
    "STOCKS_TIME_WINDOW": (
        '1 Day  # Options: "1 Day", "5 Days", "1 Month", "3 Months", "6 Months", "1 Year", "2 Years", "5 Years", "ALL"'
    ),
    "STOCKS_REFRESH_SECONDS": "300  # How often to fetch stock data (default: 5 minutes)",
}

# A saved value for each target that differs from the example, by type.
_SAVED_BY_TYPE = {str: "saved-in-the-ui", int: 9999, float: 12.3456}


def _saved_value_for(env_var):
    _plugin_id, key, parse = ENV_PLUGIN_OVERRIDES[env_var]
    if key == "entities":
        return [{"entity_id": "light.saved_in_ui", "name": "Saved"}]
    if key == "symbols":
        return ["SAVED"]
    return _SAVED_BY_TYPE[parse]


def _compose_value(rhs):
    """What ``docker compose`` hands the container for an unquoted .env value.

    Compose drops an inline `` # comment`` after a value — except when the
    value is empty, where it passes the comment itself through (the
    PURPLEAIR_SENSOR_ID case in #2108).
    """
    stripped = rhs.strip()
    if stripped.startswith("#"):
        return stripped
    return stripped.split(" #", 1)[0].strip()


def _install_with(config_path, plugin_id, plugin_config):
    config = _write_migrated_install(config_path)
    config["plugins"][plugin_id] = {"enabled": True, **plugin_config}
    config_path.write_text(json.dumps(config))


class TestEnvExampleValuesDoNotOverrideSavedSettings:
    def test_example_home_assistant_base_url_keeps_saved_url(self, tmp_path, monkeypatch):
        """The exact #2108 report: the example URL must not replace the UI's URL."""
        config_path = tmp_path / "config.json"
        _install_with(config_path, "home_assistant", {"base_url": "http://homeassistant:8123"})
        monkeypatch.setenv("HOME_ASSISTANT_BASE_URL", "http://192.168.1.100:8123")

        cm = ConfigManager(config_path=str(config_path))

        assert cm.get_plugin_config("home_assistant")["base_url"] == "http://homeassistant:8123"

    def test_real_home_assistant_base_url_still_overrides(self, tmp_path, monkeypatch):
        """A value the user actually chose keeps the #1761 env-wins behavior."""
        config_path = tmp_path / "config.json"
        _install_with(config_path, "home_assistant", {"base_url": "http://homeassistant:8123"})
        monkeypatch.setenv("HOME_ASSISTANT_BASE_URL", "http://ha.example.test:8123")

        cm = ConfigManager(config_path=str(config_path))

        assert cm.get_plugin_config("home_assistant")["base_url"] == "http://ha.example.test:8123"

    @pytest.mark.parametrize("env_var", sorted(OLD_ENV_EXAMPLE_PLUGIN_LINES))
    def test_old_example_value_as_compose_passes_it_keeps_saved_value(self, tmp_path, monkeypatch, env_var):
        """Every plugin value a copied env.example sets is ignored, in both read paths."""
        plugin_id, key, _parse = ENV_PLUGIN_OVERRIDES[env_var]
        saved = _saved_value_for(env_var)
        config_path = tmp_path / "config.json"
        _install_with(config_path, plugin_id, {key: saved})
        monkeypatch.setenv(env_var, _compose_value(OLD_ENV_EXAMPLE_PLUGIN_LINES[env_var]))

        cm = ConfigManager(config_path=str(config_path))

        assert cm.get_plugin_config(plugin_id)[key] == saved
        assert cm.get_all_plugin_configs()[plugin_id][key] == saved
        assert key not in ConfigManager.get_plugin_env_overrides(plugin_id)

    @pytest.mark.parametrize("env_var", sorted(OLD_ENV_EXAMPLE_PLUGIN_LINES))
    def test_old_example_line_passed_verbatim_keeps_saved_value(self, tmp_path, monkeypatch, env_var):
        """``docker run --env-file`` keeps the inline comment as part of the value.

        That form of the example line must be recognised too, rather than
        e.g. turning ``STOCKS_SYMBOLS`` into a list of comment fragments.
        """
        plugin_id, key, _parse = ENV_PLUGIN_OVERRIDES[env_var]
        saved = _saved_value_for(env_var)
        config_path = tmp_path / "config.json"
        _install_with(config_path, plugin_id, {key: saved})
        monkeypatch.setenv(env_var, OLD_ENV_EXAMPLE_PLUGIN_LINES[env_var])

        cm = ConfigManager(config_path=str(config_path))

        assert cm.get_plugin_config(plugin_id)[key] == saved

    def test_purpleair_sensor_id_comment_text_is_not_applied(self, tmp_path, monkeypatch):
        """``PURPLEAIR_SENSOR_ID=  # Optional: ...`` must not become the sensor id."""
        config_path = tmp_path / "config.json"
        _install_with(config_path, "air_fog", {"purpleair_sensor_id": "123456"})
        monkeypatch.setenv("PURPLEAIR_SENSOR_ID", "# Optional: specific sensor ID")

        cm = ConfigManager(config_path=str(config_path))

        assert cm.get_plugin_config("air_fog")["purpleair_sensor_id"] == "123456"

    def test_example_entities_with_different_json_spacing_are_still_recognised(self, tmp_path, monkeypatch):
        """Structured examples compare by parsed value, not by exact whitespace."""
        saved = [{"entity_id": "light.saved_in_ui", "name": "Saved"}]
        config_path = tmp_path / "config.json"
        _install_with(config_path, "home_assistant", {"entities": saved})
        monkeypatch.setenv(
            "HOME_ASSISTANT_ENTITIES",
            '[{"entity_id":"binary_sensor.front_door","name":"Front Door"},'
            '{"entity_id":"cover.garage_door","name":"Garage"}]',
        )

        cm = ConfigManager(config_path=str(config_path))

        assert cm.get_plugin_config("home_assistant")["entities"] == saved


class TestOverrideWarning:
    def _override_warnings(self, caplog, env_var):
        return [r for r in caplog.records if r.levelno == logging.WARNING and env_var in r.getMessage()]

    def test_override_of_a_different_saved_value_warns_once(self, tmp_path, monkeypatch, caplog):
        """Overlay is computed on every read; the warning must not repeat with it."""
        config_path = tmp_path / "config.json"
        _install_with(config_path, "home_assistant", {"base_url": "http://homeassistant:8123"})
        monkeypatch.setenv("HOME_ASSISTANT_BASE_URL", "http://ha.example.test:8123")
        cm = ConfigManager(config_path=str(config_path))

        with caplog.at_level(logging.WARNING, logger="src.config_manager"):
            for _ in range(3):
                cm.get_plugin_config("home_assistant")
                cm.get_all_plugin_configs()

        warnings = self._override_warnings(caplog, "HOME_ASSISTANT_BASE_URL")
        assert len(warnings) == 1
        assert "home_assistant" in warnings[0].getMessage()
        assert "base_url" in warnings[0].getMessage()

    def test_no_warning_when_env_value_matches_saved_value(self, tmp_path, monkeypatch, caplog):
        """Nothing is being overridden, so there is nothing to warn about."""
        config_path = tmp_path / "config.json"
        _install_with(config_path, "home_assistant", {"base_url": "http://ha.example.test:8123"})
        monkeypatch.setenv("HOME_ASSISTANT_BASE_URL", "http://ha.example.test:8123")
        cm = ConfigManager(config_path=str(config_path))

        with caplog.at_level(logging.WARNING, logger="src.config_manager"):
            cm.get_plugin_config("home_assistant")

        assert self._override_warnings(caplog, "HOME_ASSISTANT_BASE_URL") == []

    def test_no_warning_for_ignored_example_value(self, tmp_path, monkeypatch, caplog):
        """An ignored example value overrides nothing, so it must not claim to."""
        config_path = tmp_path / "config.json"
        _install_with(config_path, "home_assistant", {"base_url": "http://homeassistant:8123"})
        monkeypatch.setenv("HOME_ASSISTANT_BASE_URL", "http://192.168.1.100:8123")
        cm = ConfigManager(config_path=str(config_path))

        with caplog.at_level(logging.WARNING, logger="src.config_manager"):
            cm.get_plugin_config("home_assistant")

        assert self._override_warnings(caplog, "HOME_ASSISTANT_BASE_URL") == []

    def test_override_warning_never_logs_the_secret(self, tmp_path, monkeypatch, caplog):
        """The warning names the variable and key, never a sensitive value."""
        config_path = tmp_path / "config.json"
        _write_migrated_install(config_path)
        monkeypatch.setenv("WEATHER_API_KEY", "test_secret_from_env")
        cm = ConfigManager(config_path=str(config_path))

        with caplog.at_level(logging.WARNING, logger="src.config_manager"):
            cm.get_plugin_config("weather")

        warnings = self._override_warnings(caplog, "WEATHER_API_KEY")
        assert len(warnings) == 1
        assert "test_secret_from_env" not in caplog.text
        assert "stored_key" not in caplog.text


class TestShippedEnvExample:
    def test_env_example_sets_no_plugin_values(self):
        """A fresh ``cp env.example .env`` must leave every plugin setting alone."""
        values = dotenv_values(REPO_ROOT / "env.example")

        set_plugin_vars = sorted(var for var in ENV_PLUGIN_OVERRIDES if (values.get(var) or "").strip())
        assert set_plugin_vars == []

    def test_env_example_has_no_comment_after_an_empty_value(self):
        """``KEY=  # comment`` makes Compose pass the comment through as the value."""
        text = (REPO_ROOT / "env.example").read_text()

        offenders = re.findall(r"^([A-Z][A-Z0-9_]*)=[ \t]*#", text, flags=re.MULTILINE)
        assert offenders == []
