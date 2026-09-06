"""Tests for src.config module.

Tests the Config class and classproperty descriptor, including all
configuration properties and helper methods. Uses a mocked ConfigManager
for isolation.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.config import Config, classproperty

# ==================== Fixture ====================


@pytest.fixture(autouse=True)
def mock_config_manager():
    """Mock ConfigManager singleton for all tests."""
    mock_cm = MagicMock()
    mock_cm.get_board.return_value = {
        "api_mode": "local",
        "local_api_key": "test-key",
        "cloud_key": "",
        "host": "192.168.1.100",
        "transition_strategy": "column",
        "transition_interval_ms": 100,
        "transition_step_size": 2,
    }
    mock_cm.get_general.return_value = {
        "timezone": "America/New_York",
        "refresh_interval_seconds": 600,
        "output_target": "both",
    }
    mock_cm.validate.return_value = (True, [])
    mock_cm.reload.return_value = None

    # Feature configs - tests can modify this dict
    feature_configs = {}

    def get_feature(name):
        return feature_configs.get(name, {})

    mock_cm.get_feature.side_effect = get_feature
    mock_cm._feature_configs = feature_configs

    # Plugin configs (#1761: get_summary reads plugins.*, not features.*)
    plugin_configs = {}

    def get_plugin_config(plugin_id, **_kwargs):
        return plugin_configs.get(plugin_id)

    def is_plugin_enabled(plugin_id):
        cfg = plugin_configs.get(plugin_id) or {}
        return bool(cfg.get("enabled", False))

    mock_cm.get_plugin_config.side_effect = get_plugin_config
    mock_cm.is_plugin_enabled.side_effect = is_plugin_enabled
    mock_cm._plugin_configs = plugin_configs

    with patch("src.config.get_config_manager", return_value=mock_cm):
        yield mock_cm


# ==================== classproperty Descriptor ====================


class TestClassproperty:
    """Test the classproperty descriptor."""

    def test_classproperty_returns_value_on_class_access(self):
        """classproperty returns func(cls) when accessed on class."""

        class Foo:
            @classproperty
            def bar(cls):
                return "baz"

        assert Foo.bar == "baz"

    def test_classproperty_receives_class_as_argument(self):
        """classproperty passes the class (objtype) to the function."""
        received = []

        class Foo:
            @classproperty
            def bar(cls):
                received.append(cls)
                return cls.__name__

        assert Foo.bar == "Foo"
        assert received[0] is Foo

    def test_classproperty_on_instance_access(self):
        """classproperty on instance access uses objtype (the class)."""

        class Foo:
            @classproperty
            def bar(cls):
                return "from-class"

        assert Foo().bar == "from-class"


# ==================== Board API Configuration ====================


class TestBoardApiConfig:
    """Test Board API configuration properties."""

    def test_board_api_mode(self, mock_config_manager):
        assert Config.BOARD_API_MODE == "local"

    def test_board_api_mode_from_config(self, mock_config_manager):
        mock_config_manager.get_board.return_value = {"api_mode": "cloud"}
        assert Config.BOARD_API_MODE == "cloud"

    def test_board_local_api_key(self, mock_config_manager):
        assert Config.BOARD_LOCAL_API_KEY == "test-key"

    def test_board_read_write_key(self, mock_config_manager):
        mock_config_manager.get_board.return_value = {"cloud_key": "cloud-key-123"}
        assert Config.BOARD_READ_WRITE_KEY == "cloud-key-123"

    def test_board_host(self, mock_config_manager):
        assert Config.BOARD_HOST == "192.168.1.100"

    def test_board_transition_strategy(self, mock_config_manager):
        assert Config.BOARD_TRANSITION_STRATEGY == "column"

    def test_board_transition_interval_ms(self, mock_config_manager):
        assert Config.BOARD_TRANSITION_INTERVAL_MS == 100

    def test_board_transition_step_size(self, mock_config_manager):
        assert Config.BOARD_TRANSITION_STEP_SIZE == 2

    def test_board_defaults_when_empty(self, mock_config_manager):
        mock_config_manager.get_board.return_value = {}
        assert Config.BOARD_API_MODE == "local"
        assert Config.BOARD_LOCAL_API_KEY == ""
        assert Config.BOARD_READ_WRITE_KEY == ""
        assert Config.BOARD_HOST == ""
        assert Config.BOARD_TRANSITION_STRATEGY is None
        assert Config.BOARD_TRANSITION_INTERVAL_MS is None
        assert Config.BOARD_TRANSITION_STEP_SIZE is None


class TestGetBoardApiKey:
    """Test get_board_api_key method."""

    def test_returns_local_key_when_mode_local(self, mock_config_manager):
        mock_config_manager.get_board.return_value = {
            "api_mode": "local",
            "local_api_key": "local-123",
            "cloud_key": "cloud-456",
        }
        assert Config.get_board_api_key() == "local-123"

    def test_returns_cloud_key_when_mode_cloud(self, mock_config_manager):
        mock_config_manager.get_board.return_value = {
            "api_mode": "cloud",
            "local_api_key": "local-123",
            "cloud_key": "cloud-456",
        }
        assert Config.get_board_api_key() == "cloud-456"

    def test_cloud_mode_case_insensitive(self, mock_config_manager):
        mock_config_manager.get_board.return_value = {
            "api_mode": "CLOUD",
            "local_api_key": "local-123",
            "cloud_key": "cloud-456",
        }
        assert Config.get_board_api_key() == "cloud-456"


# ==================== Backward Compatibility Aliases ====================


class TestBackwardCompatibilityAliases:
    """Test FB_* and get_vb_api_key aliases."""

    def test_fb_api_mode(self, mock_config_manager):
        assert Config.FB_API_MODE == Config.BOARD_API_MODE

    def test_fb_local_api_key(self, mock_config_manager):
        assert Config.FB_LOCAL_API_KEY == Config.BOARD_LOCAL_API_KEY

    def test_fb_read_write_key(self, mock_config_manager):
        assert Config.FB_READ_WRITE_KEY == Config.BOARD_READ_WRITE_KEY

    def test_fb_host(self, mock_config_manager):
        assert Config.FB_HOST == Config.BOARD_HOST

    def test_fb_transition_strategy(self, mock_config_manager):
        assert Config.FB_TRANSITION_STRATEGY == Config.BOARD_TRANSITION_STRATEGY

    def test_fb_transition_interval_ms(self, mock_config_manager):
        assert Config.FB_TRANSITION_INTERVAL_MS == Config.BOARD_TRANSITION_INTERVAL_MS

    def test_fb_transition_step_size(self, mock_config_manager):
        assert Config.FB_TRANSITION_STEP_SIZE == Config.BOARD_TRANSITION_STEP_SIZE

    def test_get_vb_api_key(self, mock_config_manager):
        assert Config.get_vb_api_key() == Config.get_board_api_key()


# ==================== Output Configuration ====================


class TestOutputTarget:
    """Test OUTPUT_TARGET property."""

    def test_output_target_from_config(self, mock_config_manager):
        assert Config.OUTPUT_TARGET == "both"

    def test_output_target_default(self, mock_config_manager):
        mock_config_manager.get_general.return_value = {}
        assert Config.OUTPUT_TARGET == "board"

    def test_output_target_ui(self, mock_config_manager):
        mock_config_manager.get_general.return_value = {"output_target": "ui"}
        assert Config.OUTPUT_TARGET == "ui"


# ==================== General Configuration ====================


class TestGeneralConfig:
    """Test general configuration."""

    def test_general_timezone(self, mock_config_manager):
        assert Config.GENERAL_TIMEZONE == "America/New_York"

    def test_general_timezone_default(self, mock_config_manager):
        mock_config_manager.get_general.return_value = {}
        assert Config.GENERAL_TIMEZONE == ""

    def test_refresh_interval_seconds(self, mock_config_manager):
        assert Config.REFRESH_INTERVAL_SECONDS == 600

    def test_refresh_interval_seconds_default(self, mock_config_manager):
        mock_config_manager.get_general.return_value = {}
        assert Config.REFRESH_INTERVAL_SECONDS == 300


# ==================== Silence Schedule Configuration ====================


class TestSilenceScheduleConfig:
    """Test silence schedule configuration."""

    def test_silence_schedule_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["silence_schedule"] = {"enabled": True}
        assert Config.SILENCE_SCHEDULE_ENABLED is True

    def test_silence_schedule_start_time(self, mock_config_manager):
        mock_config_manager._feature_configs["silence_schedule"] = {"start_time": "22:00"}
        assert Config.SILENCE_SCHEDULE_START_TIME == "22:00"

    def test_silence_schedule_start_time_default(self, mock_config_manager):
        assert Config.SILENCE_SCHEDULE_START_TIME == "20:00"

    def test_silence_schedule_end_time(self, mock_config_manager):
        mock_config_manager._feature_configs["silence_schedule"] = {"end_time": "08:00"}
        assert Config.SILENCE_SCHEDULE_END_TIME == "08:00"

    def test_silence_schedule_end_time_default(self, mock_config_manager):
        assert Config.SILENCE_SCHEDULE_END_TIME == "07:00"


class TestGetTransitionSettings:
    """Test get_transition_settings helper."""

    def test_get_transition_settings_returns_dict(self, mock_config_manager):
        result = Config.get_transition_settings()
        assert result == {
            "strategy": "column",
            "step_interval_ms": 100,
            "step_size": 2,
        }

    def test_get_transition_settings_with_none_values(self, mock_config_manager):
        mock_config_manager.get_board.return_value = {}
        result = Config.get_transition_settings()
        assert result == {
            "strategy": None,
            "step_interval_ms": None,
            "step_size": None,
        }


class TestReload:
    """Test reload method."""

    def test_reload_delegates_to_config_manager(self, mock_config_manager):
        Config.reload()
        mock_config_manager.reload.assert_called_once()


class TestValidate:
    """Test validate method."""

    def test_validate_returns_true_when_valid(self, mock_config_manager):
        mock_config_manager.validate.return_value = (True, [])
        assert Config.validate() is True

    def test_validate_returns_false_when_invalid(self, mock_config_manager):
        mock_config_manager.validate.return_value = (
            False,
            ["Missing required field: api_key"],
        )
        assert Config.validate() is False

    def test_validate_delegates_to_config_manager(self, mock_config_manager):
        Config.validate()
        mock_config_manager.validate.assert_called_once()


class TestGetSummary:
    """Test get_summary method."""

    def test_get_summary_returns_correct_structure(self, mock_config_manager):
        mock_config_manager._plugin_configs["weather"] = {"api_key": "key", "enabled": True}
        result = Config.get_summary()

        assert "weather_provider" in result
        assert "weather_location" in result
        assert "timezone" in result
        assert "refresh_interval_seconds" in result
        assert "datetime_enabled" in result
        assert "weather_enabled" in result
        assert "guest_wifi_enabled" in result
        assert "home_assistant_enabled" in result
        assert "star_trek_quotes_enabled" in result
        assert "air_fog_enabled" in result
        assert "muni_enabled" in result
        assert "surf_enabled" in result
        assert "baywheels_enabled" in result
        assert "traffic_enabled" in result
        assert "stocks_enabled" in result
        assert "board_api_mode" in result
        assert "board_host" in result
        assert "board_key_set" in result
        assert "weather_key_set" in result
        assert "transition_strategy" in result
        assert "transition_interval_ms" in result
        assert "transition_step_size" in result

    def test_get_summary_board_host_cloud_when_cloud_mode(self, mock_config_manager):
        mock_config_manager.get_board.return_value = {"api_mode": "cloud", "host": ""}
        result = Config.get_summary()
        assert result["board_host"] == "cloud"

    def test_get_summary_board_host_actual_when_local_mode(self, mock_config_manager):
        mock_config_manager.get_board.return_value = {
            "api_mode": "local",
            "host": "192.168.1.100",
        }
        result = Config.get_summary()
        assert result["board_host"] == "192.168.1.100"

    def test_get_summary_transition_keys_none_when_cloud_mode(self, mock_config_manager):
        mock_config_manager.get_board.return_value = {"api_mode": "cloud"}
        result = Config.get_summary()
        assert result["transition_strategy"] is None
        assert result["transition_interval_ms"] is None
        assert result["transition_step_size"] is None

    def test_get_summary_enabled_flags_come_from_plugin_configs(self, mock_config_manager):
        """#1761: *_enabled flags report plugins.* enablement, not legacy features."""
        mock_config_manager._plugin_configs["weather"] = {"api_key": "key", "enabled": True}
        mock_config_manager._plugin_configs["stocks"] = {"enabled": True}
        mock_config_manager._plugin_configs["muni"] = {"enabled": False}

        result = Config.get_summary()

        assert result["weather_enabled"] is True
        assert result["stocks_enabled"] is True
        assert result["muni_enabled"] is False
        assert result["surf_enabled"] is False

    def test_get_summary_weather_enabled_requires_api_key(self, mock_config_manager):
        mock_config_manager._plugin_configs["weather"] = {"enabled": True}
        result = Config.get_summary()
        assert result["weather_enabled"] is False
        assert result["weather_key_set"] is False

    def test_get_summary_baywheels_flag_reads_renamed_plugin(self, mock_config_manager):
        """The baywheels feature became the lyft_bike_share plugin."""
        mock_config_manager._plugin_configs["lyft_bike_share"] = {"enabled": True}
        result = Config.get_summary()
        assert result["baywheels_enabled"] is True

    def test_get_summary_timezone_is_general_timezone(self, mock_config_manager):
        result = Config.get_summary()
        assert result["timezone"] == "America/New_York"
