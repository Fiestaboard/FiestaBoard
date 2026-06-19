"""Tests for ConfigManager singleton and configuration file management."""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.config_manager import (
    ConfigManager,
)


@pytest.fixture(autouse=True)
def mock_time_service():
    """Mock get_time_service to avoid TimeService dependency."""
    with patch("src.config_manager.get_time_service") as mock:
        mock_ts = MagicMock()
        mock.return_value = mock_ts
        mock_ts.local_to_utc_iso.side_effect = lambda t, tz: t
        yield mock_ts


@pytest.fixture(autouse=True)
def reset_singleton(tmp_path, monkeypatch):
    """Reset ConfigManager + SettingsService singletons and clear env vars."""
    # Clear environment variables that could interfere with validation tests
    monkeypatch.delenv("BOARD_READ_WRITE_KEY", raising=False)
    monkeypatch.delenv("FB_READ_WRITE_KEY", raising=False)
    monkeypatch.delenv("WEATHER_API_KEY", raising=False)
    monkeypatch.delenv("BOARD_LOCAL_API_KEY", raising=False)
    monkeypatch.delenv("FB_LOCAL_API_KEY", raising=False)
    monkeypatch.delenv("BOARD_HOST", raising=False)
    monkeypatch.delenv("FB_HOST", raising=False)

    ConfigManager._instance = None
    ConfigManager._lock = threading.Lock()

    # Pre-seed ConfigManager singleton with an empty tmp config so that
    # SettingsService._apply_global_connection() doesn't migrate the real
    # global config from data/config.json into the fresh settings instance.
    empty_config_path = tmp_path / "_empty_config.json"
    empty_config_path.write_text('{"board": {}, "features": {}, "general": {}}')
    ConfigManager(config_path=str(empty_config_path))

    # Reset SettingsService singleton and point it at an empty tmp settings
    # file so validate() doesn't pick up a real configured board from data/
    # (e.g. when tests run inside a populated dev container).
    import src.settings.service as settings_service_module

    settings_service_module._settings_service = settings_service_module.SettingsService(
        settings_file=str(tmp_path / "settings.json")
    )

    # Now clear the ConfigManager singleton so each test can pin its own
    # config_path via ConfigManager(config_path=...).
    ConfigManager._instance = None
    ConfigManager._lock = threading.Lock()

    yield tmp_path

    ConfigManager._instance = None
    settings_service_module._settings_service = None


# --- __init__ and _load_or_create ---


def test_creates_default_config_when_no_file_exists(tmp_path):
    """Creates default config when no file exists."""
    config_path = tmp_path / "config.json"
    assert not config_path.exists()
    ConfigManager(config_path=str(config_path))
    assert config_path.exists()
    loaded = json.loads(config_path.read_text())
    assert "board" in loaded
    assert "features" in loaded
    assert "general" in loaded
    assert loaded["board"]["api_mode"] == "local"


def test_pi_profile_defaults_instance_name_on_fresh_config(tmp_path, monkeypatch):
    """On the FiestaPi image, a brand-new config gets instance_name='FiestaPi'."""
    monkeypatch.setenv("FIESTABOARD_PROFILE", "pi")
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    assert cm.get_general()["instance_name"] == "FiestaPi"
    # Persisted to disk so the UI sees it without another save round-trip.
    on_disk = json.loads(config_path.read_text())
    assert on_disk["general"]["instance_name"] == "FiestaPi"


def test_docker_profile_leaves_instance_name_empty(tmp_path, monkeypatch):
    """Default Docker installs keep instance_name empty (existing behavior)."""
    monkeypatch.delenv("FIESTABOARD_PROFILE", raising=False)
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    assert cm.get_general()["instance_name"] == ""


def test_pi_profile_does_not_overwrite_existing_instance_name(tmp_path, monkeypatch):
    """Existing config (e.g. user renamed) is not stomped on next start."""
    monkeypatch.setenv("FIESTABOARD_PROFILE", "pi")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "board": {"api_mode": "local"},
                "features": {},
                "general": {"instance_name": "Kitchen Board"},
            }
        )
    )
    cm = ConfigManager(config_path=str(config_path))
    assert cm.get_general()["instance_name"] == "Kitchen Board"


def test_loads_existing_valid_config_file(tmp_path):
    """Loads existing valid config file."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "cloud", "cloud_key": "test-cloud-key"},
        "features": {},
        "general": {"timezone": "UTC"},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    board = cm.get_board()
    assert board["api_mode"] == "cloud"
    assert board["cloud_key"] == "test-cloud-key"
    general = cm.get_general()
    assert general["timezone"] == "UTC"


def test_handles_invalid_json_creates_defaults(tmp_path):
    """Handles invalid JSON gracefully, creates defaults."""
    config_path = tmp_path / "config.json"
    config_path.write_text("{ invalid json here")
    cm = ConfigManager(config_path=str(config_path))
    board = cm.get_board()
    assert "api_mode" in board
    assert board["api_mode"] == "local"


def test_merges_loaded_config_with_defaults_adds_missing_keys(tmp_path):
    """Merges loaded config with defaults, adds missing keys."""
    config_path = tmp_path / "config.json"
    partial_config = {
        "board": {"api_mode": "local", "host": "192.168.1.1"},
        "features": {"weather": {"enabled": True}},
    }
    config_path.write_text(json.dumps(partial_config))
    cm = ConfigManager(config_path=str(config_path))
    board = cm.get_board()
    assert board["host"] == "192.168.1.1"
    assert "local_api_key" in board
    weather = cm.get_feature("weather")
    assert weather["enabled"] is True
    assert "api_key" in weather


# --- _deep_copy ---


def test_deep_copy_creates_independent_copies(tmp_path):
    """_deep_copy creates independent copies."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    config1 = cm.get_all()
    config2 = cm.get_all()
    config1["board"]["host"] = "modified"
    assert config2["board"]["host"] != "modified"
    assert cm.get_board()["host"] != "modified"


# --- _merge_with_defaults (via REPLACE_FIELDS) ---


def test_replace_fields_color_rules_replaced_entirely(tmp_path):
    """REPLACE_FIELDS (color_rules) are replaced entirely, not merged."""
    config_path = tmp_path / "config.json"
    user_color_rules = {
        "temp": [{"condition": ">=", "value": 100, "color": "red"}],
    }
    config_data = {
        "board": {"api_mode": "local"},
        "features": {
            "weather": {
                "enabled": False,
                "api_key": "",
                "color_rules": user_color_rules,
            },
        },
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    weather = cm.get_feature("weather")
    assert weather["color_rules"]["temp"] == user_color_rules["temp"]
    assert len(weather["color_rules"]["temp"]) == 1
    assert weather["color_rules"]["temp"][0]["value"] == 100


def test_merge_preserves_user_values(tmp_path):
    """_merge_with_defaults preserves user values."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "cloud", "cloud_key": "user-key"},
        "features": {},
        "general": {"timezone": "Europe/London"},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    assert cm.get_board()["cloud_key"] == "user-key"
    assert cm.get_general()["timezone"] == "Europe/London"


# --- _is_placeholder ---


def test_is_placeholder_your_api_key_here():
    """_is_placeholder: your_api_key_here -> True."""
    assert ConfigManager._is_placeholder("your_api_key_here") is True


def test_is_placeholder_your_key_here():
    """_is_placeholder: your-key-here -> True."""
    assert ConfigManager._is_placeholder("your-key-here") is True


def test_is_placeholder_changeme():
    """_is_placeholder: changeme -> True."""
    assert ConfigManager._is_placeholder("changeme") is True


def test_is_placeholder_replace_me():
    """_is_placeholder: replace_me -> True."""
    assert ConfigManager._is_placeholder("replace_me") is True


def test_is_placeholder_placeholder():
    """_is_placeholder: placeholder -> True."""
    assert ConfigManager._is_placeholder("placeholder") is True


def test_is_placeholder_real_key_false():
    """_is_placeholder: real_key_123 -> False."""
    assert ConfigManager._is_placeholder("real_key_123") is False


def test_is_placeholder_case_insensitive_and_strip():
    """_is_placeholder: case insensitive + strip."""
    assert ConfigManager._is_placeholder("  Your_stuff_here  ") is True
    assert ConfigManager._is_placeholder("CHANGEME") is True


# --- _apply_env_overrides ---


def test_apply_env_overrides_applies_when_empty(tmp_path):
    """Applies env vars when config values are empty."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"board": {}, "features": {}, "general": {}}))
    env_overrides = {
        "BOARD_HOST": "env-host.example.com",
        "FB_HOST": "env-host.example.com",
        "BOARD_LOCAL_API_KEY": "env-key-123",
        "FB_LOCAL_API_KEY": "env-key-123",
    }

    def mock_getenv(key, default=""):
        return env_overrides.get(key, default)

    with patch("src.config_manager.os.getenv", mock_getenv):
        cm = ConfigManager(config_path=str(config_path))
        board = cm.get_board()
        # When mock is active, env values are applied. When run in Docker with
        # BOARD_HOST/FB_HOST set, env wins; we verify the apply logic by checking
        # that host and local_api_key are non-empty (applied from somewhere).
        assert board["host"], "host should be set from env when config empty"
        assert board["local_api_key"], "local_api_key should be set from env when config empty"
        # If our mock was used, we get our values
        if board["host"] == "env-host.example.com":
            assert board["local_api_key"] == "env-key-123"


def test_apply_env_overrides_does_not_override_non_empty(monkeypatch, tmp_path):
    """Does NOT override non-empty config values."""
    monkeypatch.setenv("BOARD_HOST", "env-override.com")
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "host": "existing-host.com"},
        "features": {},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    assert cm.get_board()["host"] == "existing-host.com"


def test_apply_env_overrides_ignores_placeholder_values(monkeypatch, tmp_path):
    """Ignores placeholder env var values."""
    monkeypatch.setenv("BOARD_LOCAL_API_KEY", "your_api_key_here")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"board": {}, "features": {}, "general": {}}))
    cm = ConfigManager(config_path=str(config_path))
    assert cm.get_board()["local_api_key"] == ""


def test_apply_env_overrides_invalid_int_value(monkeypatch, tmp_path):
    """Handles invalid int env var values."""
    monkeypatch.setenv("BOARD_TRANSITION_INTERVAL_MS", "not_a_number")
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "transition_interval_ms": None},
        "features": {},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    board = cm.get_board()
    assert board.get("transition_interval_ms") is None


def test_apply_env_overrides_invalid_float_value(monkeypatch, tmp_path):
    """Handles invalid float env var values."""
    monkeypatch.setenv("SURF_LATITUDE", "not_a_float")
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {},
        "features": {"surf": {"latitude": None}},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    surf = cm.get_feature("surf")
    assert surf.get("latitude") != "not_a_float"


# --- get_all and get_all_masked ---


def test_get_all_returns_deep_copy(tmp_path):
    """get_all returns deep copy of config."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    config = cm.get_all()
    config["board"]["host"] = "mutated"
    assert cm.get_board()["host"] != "mutated"


def test_get_all_masked_masks_sensitive_fields(tmp_path):
    """get_all_masked masks sensitive fields with ***."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "local_api_key": "secret-key"},
        "features": {},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    masked = cm.get_all_masked()
    assert masked["board"]["local_api_key"] == "***"


# --- _mask_sensitive ---


def test_mask_sensitive_masks_fields_with_values(tmp_path):
    """_mask_sensitive masks fields in SENSITIVE_FIELDS when they have values."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    obj = {"api_key": "secret123", "other": "visible"}
    result = cm._mask_sensitive(obj)
    assert result["api_key"] == "***"
    assert result["other"] == "visible"


def test_mask_sensitive_does_not_mask_empty_values(tmp_path):
    """_mask_sensitive doesn't mask empty values."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    obj = {"api_key": "", "password": ""}
    result = cm._mask_sensitive(obj)
    assert result["api_key"] == ""
    assert result["password"] == ""


def test_mask_sensitive_handles_nested_dicts_and_lists(tmp_path):
    """_mask_sensitive handles nested dicts and lists."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    obj = {"plugins": {"weather": {"api_key": "key123", "enabled": True}}}
    result = cm._mask_sensitive(obj)
    assert result["plugins"]["weather"]["api_key"] == "***"
    assert result["plugins"]["weather"]["enabled"] is True


# --- get_board / set_board ---


def test_get_board_returns_board_config(tmp_path):
    """get_board returns board config."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    board = cm.get_board()
    assert "api_mode" in board
    assert "host" in board


def test_set_board_updates_only_provided_fields(tmp_path):
    """set_board updates only provided fields."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_board({"host": "new-host.com"})
    board = cm.get_board()
    assert board["host"] == "new-host.com"


def test_set_board_ignores_masked_values_for_sensitive_fields(tmp_path):
    """set_board ignores masked *** values for sensitive fields."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "local_api_key": "real-secret"},
        "features": {},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    cm.set_board({"local_api_key": "***"})
    full = cm.get_all()
    assert full["board"]["local_api_key"] == "real-secret"


def test_set_board_ignores_fields_not_in_default(tmp_path):
    """set_board ignores fields not in DEFAULT_CONFIG['board']."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_board({"unknown_field": "ignored"})
    board = cm.get_board()
    assert "unknown_field" not in board


# --- get_feature / set_feature ---


def test_get_feature_returns_feature_config(tmp_path):
    """get_feature returns feature config."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    weather = cm.get_feature("weather")
    assert weather is not None
    assert "enabled" in weather
    assert "api_key" in weather


def test_get_feature_returns_default_if_not_in_config(tmp_path):
    """get_feature returns default if feature not in config but in defaults."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"board": {}, "features": {}, "general": {}}))
    cm = ConfigManager(config_path=str(config_path))
    weather = cm.get_feature("weather")
    assert weather is not None
    assert weather["provider"] == "weatherapi"


def test_get_feature_returns_none_for_unknown_feature(tmp_path):
    """get_feature returns None for unknown features."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    assert cm.get_feature("unknown_feature_xyz") is None


def test_set_feature_updates_only_provided_fields(tmp_path):
    """set_feature updates only provided fields."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_feature("weather", {"enabled": True, "location": "Boston, MA"})
    weather = cm.get_feature("weather")
    assert weather["enabled"] is True
    assert weather["location"] == "Boston, MA"


def test_set_feature_preserves_masked_sensitive_fields(tmp_path):
    """set_feature preserves masked *** sensitive fields."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {},
        "features": {"weather": {"enabled": False, "api_key": "real-weather-key"}},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    cm.set_feature("weather", {"api_key": "***"})
    full = cm.get_all()
    assert full["features"]["weather"]["api_key"] == "real-weather-key"


def test_set_feature_returns_false_for_unknown_feature(tmp_path):
    """set_feature returns False for unknown features."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    result = cm.set_feature("unknown_xyz", {"enabled": True})
    assert result is False


# --- get_general / set_general ---


def test_get_general_returns_general_config(tmp_path):
    """get_general returns general config."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    general = cm.get_general()
    assert "timezone" in general
    assert "refresh_interval_seconds" in general


def test_set_general_updates_fields_preserves_masked(tmp_path):
    """set_general updates fields, preserves masked sensitive fields."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    result = cm.set_general({"timezone": "Europe/Paris"})
    assert result is True
    assert cm.get_general()["timezone"] == "Europe/Paris"


# --- is_feature_enabled ---


def test_is_feature_enabled_true(tmp_path):
    """is_feature_enabled returns True when enabled."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_feature("weather", {"enabled": True})
    assert cm.is_feature_enabled("weather") is True


def test_is_feature_enabled_false(tmp_path):
    """is_feature_enabled returns False when disabled."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_feature("weather", {"enabled": False})
    assert cm.is_feature_enabled("weather") is False


# --- get_feature_list ---


def test_get_feature_list_returns_feature_names(tmp_path):
    """get_feature_list returns list of feature names."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    features = cm.get_feature_list()
    assert "weather" in features
    assert "date_time" in features
    assert "guest_wifi" in features


# --- get_color_rules ---


def test_get_color_rules_returns_rules_for_feature_field(tmp_path):
    """get_color_rules returns rules for feature/field."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    rules = cm.get_color_rules("weather", "temp")
    assert isinstance(rules, list)
    assert len(rules) > 0
    assert rules[0]["condition"] == ">="


def test_get_color_rules_returns_empty_list_for_missing(tmp_path):
    """get_color_rules returns empty list for missing field."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    rules = cm.get_color_rules("weather", "nonexistent_field")
    assert rules == []


# --- validate ---


def test_validate_valid_cloud_config(tmp_path):
    """Valid cloud config (has cloud_key)."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "cloud", "cloud_key": "valid-key"},
        "features": {},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    valid, errors = cm.validate()
    assert valid is True
    assert len(errors) == 0


def test_validate_invalid_cloud_config_missing_key(tmp_path):
    """Invalid cloud config (missing cloud_key)."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "cloud", "cloud_key": ""},
        "features": {},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    valid, errors = cm.validate()
    assert valid is False
    assert any("cloud_key" in e for e in errors)


def test_validate_valid_local_config(tmp_path):
    """Valid local config (has local_api_key and host)."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "local_api_key": "key", "host": "host"},
        "features": {},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    valid, _errors = cm.validate()
    assert valid is True


def test_validate_invalid_local_config_missing_key_or_host(tmp_path):
    """Invalid local config (missing key or host)."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "local_api_key": "", "host": ""},
        "features": {},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    valid, errors = cm.validate()
    assert valid is False
    assert any("local_api_key" in e or "host" in e for e in errors)


def test_validate_local_config_passes_when_only_multi_board_configured(tmp_path, monkeypatch):
    """Empty legacy board config still validates if a multi-board instance has creds.

    Regression for issue #1102: users who configured their board through the
    multi-board Settings flow (not the first-run wizard) ended up with an empty
    legacy ``config["board"]`` block. ``Config.validate()`` at startup would
    fail with ``Board local_api_key/host is required``, even though the
    multi-board settings service had a fully configured board. The service
    would then sit in a 60s retry loop refusing to initialize.
    """
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "local_api_key": "", "host": ""},
        "features": {},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))

    fake_board_settings = MagicMock()
    fake_board_settings.boards = [{"api_mode": "local", "local_api_key": "real-key", "host": "10.0.0.5"}]
    fake_service = MagicMock()
    fake_service.get_board_settings.return_value = fake_board_settings
    monkeypatch.setattr("src.settings.service.get_settings_service", lambda: fake_service)

    valid, errors = cm.validate()
    assert valid is True, f"expected valid config, got errors: {errors}"
    assert not any("local_api_key" in e or "host" in e for e in errors)


def test_validate_local_config_fails_when_multi_board_also_empty(tmp_path, monkeypatch):
    """Legacy and multi-board both empty: validation still reports board errors."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "local_api_key": "", "host": ""},
        "features": {},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))

    fake_board_settings = MagicMock()
    fake_board_settings.boards = [{"api_mode": "local", "local_api_key": "", "host": ""}]
    fake_service = MagicMock()
    fake_service.get_board_settings.return_value = fake_board_settings
    monkeypatch.setattr("src.settings.service.get_settings_service", lambda: fake_service)

    valid, errors = cm.validate()
    assert valid is False
    assert any("local_api_key" in e for e in errors)
    assert any("host" in e for e in errors)


def test_validate_enabled_weather_without_api_key(tmp_path):
    """Enabled weather without api_key."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "local_api_key": "k", "host": "h"},
        "features": {"weather": {"enabled": True, "api_key": ""}},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    valid, errors = cm.validate()
    assert valid is False
    assert any("Weather" in e for e in errors)


def test_validate_enabled_home_assistant_without_base_url_or_token(tmp_path):
    """Enabled home_assistant without base_url or access_token."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "local_api_key": "k", "host": "h"},
        "features": {
            "home_assistant": {"enabled": True, "base_url": "", "access_token": ""},
        },
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    valid, errors = cm.validate()
    assert valid is False
    assert any("base_url" in e or "access_token" in e for e in errors)


def test_validate_enabled_guest_wifi_without_ssid_or_password(monkeypatch, tmp_path):
    """Enabled guest_wifi without ssid or password."""
    # Clear env vars that might fill in ssid/password (e.g. in Docker)
    for key in ("GUEST_WIFI_SSID", "GUEST_WIFI_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {"api_mode": "local", "local_api_key": "k", "host": "h"},
        "features": {"guest_wifi": {"enabled": True, "ssid": "", "password": ""}},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    valid, errors = cm.validate()
    assert valid is False
    assert any("SSID" in e or "password" in e for e in errors)


# --- Plugin config methods ---


def test_get_plugin_config_returns_config_or_none(tmp_path):
    """get_plugin_config returns plugin config or None."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    assert cm.get_plugin_config("weather") is None
    cm.set_plugin_config("weather", {"enabled": True, "api_key": "key"})
    cfg = cm.get_plugin_config("weather")
    assert cfg is not None
    assert cfg["enabled"] is True


def test_set_plugin_config_preserves_masked_fields(tmp_path):
    """set_plugin_config preserves masked fields."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_plugin_config("weather", {"enabled": True, "api_key": "secret-key"})
    cm.set_plugin_config("weather", {"enabled": True, "api_key": "***"})
    full = cm.get_all()
    assert full["plugins"]["weather"]["api_key"] == "secret-key"


def test_update_plugin_config_merges_preserves_masked(tmp_path):
    """update_plugin_config merges updates, preserves masked fields."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_plugin_config("weather", {"enabled": True, "api_key": "secret"})
    cm.update_plugin_config("weather", {"location": "NYC", "api_key": "***"})
    full = cm.get_all()
    assert full["plugins"]["weather"]["api_key"] == "secret"
    assert full["plugins"]["weather"]["location"] == "NYC"


def test_is_plugin_enabled(tmp_path):
    """is_plugin_enabled returns True/False."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_plugin_config("weather", {"enabled": True})
    assert cm.is_plugin_enabled("weather") is True
    cm.disable_plugin("weather")
    assert cm.is_plugin_enabled("weather") is False


def test_enable_plugin_disable_plugin(tmp_path):
    """enable_plugin / disable_plugin."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_plugin_config("weather", {"enabled": False})
    cm.enable_plugin("weather")
    assert cm.is_plugin_enabled("weather") is True
    cm.disable_plugin("weather")
    assert cm.is_plugin_enabled("weather") is False


def test_get_all_plugin_configs_and_masked(tmp_path):
    """get_all_plugin_configs / get_all_plugin_configs_masked."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_plugin_config("weather", {"enabled": True, "api_key": "secret"})
    all_cfgs = cm.get_all_plugin_configs()
    assert "weather" in all_cfgs
    assert all_cfgs["weather"]["api_key"] == "secret"
    masked = cm.get_all_plugin_configs_masked()
    assert masked["weather"]["api_key"] == "***"


def test_get_enabled_plugins(tmp_path):
    """get_enabled_plugins returns list of enabled plugin IDs."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_plugin_config("weather", {"enabled": True})
    cm.set_plugin_config("stocks", {"enabled": False})
    enabled = cm.get_enabled_plugins()
    assert "weather" in enabled
    assert "stocks" not in enabled


def test_migrate_feature_to_plugin(tmp_path):
    """migrate_feature_to_plugin copies feature to plugin."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {},
        "features": {"weather": {"enabled": True, "api_key": "key", "location": "SF"}},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    result = cm.migrate_feature_to_plugin("weather", "weather")
    assert result is True
    plugin_cfg = cm.get_plugin_config("weather")
    assert plugin_cfg["enabled"] is True
    assert plugin_cfg["api_key"] == "key"


# --- reload ---


def test_reload_reloads_from_file(tmp_path):
    """reload reloads from file."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_board({"host": "original.com"})
    config_path.write_text(
        json.dumps(
            {
                "board": {"api_mode": "local", "host": "reloaded.com"},
                "features": {},
                "general": {},
            }
        )
    )
    cm.reload()
    assert cm.get_board()["host"] == "reloaded.com"


# --- _auto_migrate_features_to_plugins ---


def test_auto_migrate_migrates_features_not_in_plugins(tmp_path):
    """_auto_migrate migrates features in raw config but not in plugins."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {},
        "features": {"weather": {"enabled": True, "api_key": "key"}},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    plugin_cfg = cm.get_plugin_config("weather")
    assert plugin_cfg is not None
    assert plugin_cfg["enabled"] is True
    assert plugin_cfg["api_key"] == "key"


def test_auto_migrate_skips_features_already_in_plugins(tmp_path):
    """_auto_migrate skips features already in plugins."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {},
        "features": {"weather": {"enabled": True, "api_key": "old"}},
        "plugins": {"weather": {"enabled": True, "api_key": "existing"}},
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    plugin_cfg = cm.get_plugin_config("weather")
    assert plugin_cfg["api_key"] == "existing"


def test_auto_migrate_excludes_color_rules(tmp_path):
    """_auto_migrate excludes MIGRATION_EXCLUDED_FIELDS (color_rules)."""
    config_path = tmp_path / "config.json"
    config_data = {
        "board": {},
        "features": {
            "weather": {
                "enabled": True,
                "api_key": "key",
                "color_rules": {"temp": [{"condition": ">=", "value": 90, "color": "red"}]},
            },
        },
        "general": {},
    }
    config_path.write_text(json.dumps(config_data))
    cm = ConfigManager(config_path=str(config_path))
    plugin_cfg = cm.get_plugin_config("weather")
    assert "color_rules" not in plugin_cfg


# --- v2 plugin migration flag (issue #937) ---


def test_v2_plugin_migration_flag_defaults_to_false(tmp_path):
    """On a brand-new config, the v2 plugin migration flag is unset/false so the
    one-shot migration runs once on first boot."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    assert cm.is_v2_plugin_migration_done() is False


def test_v2_plugin_migration_flag_persists_across_loads(tmp_path):
    """Marking the migration done writes through to disk so the next process
    skips the migration. This is the lock that prevents #937's sticky-plugin
    reinstall loop."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.mark_v2_plugin_migration_done()
    assert cm.is_v2_plugin_migration_done() is True

    # Simulate a fresh process: drop the singleton, reload from disk.
    ConfigManager._instance = None
    cm2 = ConfigManager(config_path=str(config_path))
    assert cm2.is_v2_plugin_migration_done() is True


def test_v2_plugin_migration_flag_idempotent(tmp_path):
    """Marking done twice does not raise and stays True."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.mark_v2_plugin_migration_done()
    cm.mark_v2_plugin_migration_done()
    assert cm.is_v2_plugin_migration_done() is True


# --- v2 plugin migration retry list (issue #948) ---
#
# Regression for the upgrade-eats-integrations report: per-plugin install
# failures must survive across boots so a flaky first attempt can recover,
# without us giving up the #937 "don't resurrect deliberately-deleted
# plugins" guarantee.


def test_v2_plugin_failed_installs_default_empty(tmp_path):
    """On a fresh install the retry queue is empty (and stays out of the file)."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    assert cm.get_v2_plugin_failed_installs() == []
    saved = json.loads(config_path.read_text())
    assert "v2_failed_installs" not in saved.get("plugin_migrations", {})


def test_v2_plugin_failed_installs_round_trip(tmp_path):
    """Setting + reloading from disk preserves the queue (deduped + sorted)."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_v2_plugin_failed_installs(["weather", "muni", "weather"])
    assert cm.get_v2_plugin_failed_installs() == ["muni", "weather"]

    # Reload from disk to confirm persistence.
    ConfigManager._instance = None
    cm2 = ConfigManager(config_path=str(config_path))
    assert cm2.get_v2_plugin_failed_installs() == ["muni", "weather"]


def test_v2_plugin_failed_installs_clear_removes_key(tmp_path):
    """Clearing the queue drops the field entirely so the config stays tidy."""
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    cm.set_v2_plugin_failed_installs(["weather"])
    cm.clear_v2_plugin_failed_installs()
    assert cm.get_v2_plugin_failed_installs() == []
    saved = json.loads(config_path.read_text())
    assert "v2_failed_installs" not in saved.get("plugin_migrations", {})


def test_v2_plugin_failed_installs_ignores_non_string_entries(tmp_path):
    """Defensive: stale on-disk corruption (None, ints, empty strings) is filtered."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "plugin_migrations": {
                    "v2_completed": True,
                    "v2_failed_installs": ["muni", "", None, 7, "weather"],
                },
            }
        )
    )
    cm = ConfigManager(config_path=str(config_path))
    assert cm.get_v2_plugin_failed_installs() == ["muni", "weather"]


# --- app_version_seen stamp + pre-boot snapshot (issue #948) ---


def test_app_version_seen_stamped_on_fresh_config(tmp_path):
    """A brand-new config records the running version so the next boot can
    detect upgrades without us having to scrape image digests."""
    from src import __version__

    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    saved = json.loads(config_path.read_text())
    assert saved.get("app_version_seen") == __version__
    assert cm._config.get("app_version_seen") == __version__


def test_app_version_seen_stamped_on_existing_config(tmp_path):
    """Loading a config that pre-dates the stamp adds it on first boot."""
    from src import __version__

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"plugins": {"weather": {"enabled": True}}}))
    ConfigManager(config_path=str(config_path))
    saved = json.loads(config_path.read_text())
    assert saved.get("app_version_seen") == __version__


def test_pre_boot_snapshot_written_when_version_changes(tmp_path):
    """When the on-disk version differs from the running one, a pre-init
    snapshot is dropped into update-backups/ before any migration runs.

    This is the safety net for issue #948: every upgrade path now leaves
    behind a rollback target, regardless of which mechanism the user used
    (compose pull, FiestaUpdater button, FiestaPi update, etc.).
    """
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_version_seen": "6.99.0",
                "plugins": {"weather": {"enabled": True, "api_key": "k"}},
                "board": {"api_mode": "local", "local_api_key": "x", "host": "h"},
            }
        )
    )
    # Plant a couple of sibling data files so the snapshot captures them too.
    (tmp_path / "pages.json").write_text('{"pages": []}')

    ConfigManager(config_path=str(config_path))

    snapshot_dir = tmp_path / "update-backups"
    assert snapshot_dir.is_dir(), "snapshot dir was not created"
    snapshots = list(snapshot_dir.glob("pre-update-*.json"))
    assert len(snapshots) == 1, f"expected exactly one boot snapshot, got {snapshots}"

    doc = json.loads(snapshots[0].read_text())
    meta = doc.get("_fiestaupdater") or {}
    assert meta.get("trigger") == "boot-version-change"
    assert meta.get("previous_version") == "6.99.0"
    # The captured config payload reflects the pre-merge state — specifically
    # it still carries the OLD app_version_seen, not the new one that __init__
    # is about to stamp in.
    snap_config = (doc.get("data") or {}).get("config") or {}
    assert snap_config.get("plugins", {}).get("weather", {}).get("enabled") is True
    assert snap_config.get("app_version_seen") == "6.99.0"


def test_no_pre_boot_snapshot_when_versions_match(tmp_path):
    """A normal restart (same version, same data) is not noisy — no extra
    snapshot files are dropped into update-backups/."""
    from src import __version__

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_version_seen": __version__,
                "plugins": {"weather": {"enabled": True}},
                "board": {"api_mode": "local", "local_api_key": "x", "host": "h"},
            }
        )
    )
    ConfigManager(config_path=str(config_path))

    snapshot_dir = tmp_path / "update-backups"
    assert not snapshot_dir.exists() or not list(snapshot_dir.glob("pre-update-*.json"))


def test_no_pre_boot_snapshot_on_brand_new_install(tmp_path):
    """A first-ever boot (no config file, no data worth backing up) does not
    leave a junk snapshot behind."""
    config_path = tmp_path / "config.json"
    # No file exists; ConfigManager will create one.
    ConfigManager(config_path=str(config_path))

    snapshot_dir = tmp_path / "update-backups"
    assert not snapshot_dir.exists() or not list(snapshot_dir.glob("pre-update-*.json"))


# --- version_changed_on_load ---


def test_version_changed_on_load_true_after_upgrade(tmp_path, monkeypatch):
    """An existing config with an older app_version_seen flags a version change."""
    import src

    monkeypatch.setattr(src, "__version__", "9.9.9")
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"app_version_seen": "1.0.0", "plugins": {"weather": {"enabled": True}}})
    )
    cm = ConfigManager(config_path=str(cfg))
    assert cm.version_changed_on_load is True


def test_version_changed_on_load_false_same_version(tmp_path, monkeypatch):
    """Restart on the same version is not a version change."""
    import src

    monkeypatch.setattr(src, "__version__", "9.9.9")
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"app_version_seen": "9.9.9", "plugins": {}}))
    cm = ConfigManager(config_path=str(cfg))
    assert cm.version_changed_on_load is False


def test_version_changed_on_load_false_fresh_install(tmp_path, monkeypatch):
    """A brand-new config (no file) is not a version change."""
    import src

    monkeypatch.setattr(src, "__version__", "9.9.9")
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    assert cm.version_changed_on_load is False
