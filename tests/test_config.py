"""Tests for src.config module.

Tests the Config class and classproperty descriptor, including all
configuration properties and helper methods. Uses a mocked ConfigManager
for isolation.
"""

import json
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


# ==================== Weather Configuration ====================


class TestWeatherConfig:
    """Test weather configuration properties."""

    def test_weather_api_key(self, mock_config_manager):
        mock_config_manager._feature_configs["weather"] = {"api_key": "weather-key"}
        assert Config.WEATHER_API_KEY == "weather-key"

    def test_weather_provider(self, mock_config_manager):
        mock_config_manager._feature_configs["weather"] = {"provider": "openweathermap"}
        assert Config.WEATHER_PROVIDER == "openweathermap"

    def test_weather_provider_default(self, mock_config_manager):
        assert Config.WEATHER_PROVIDER == "weatherapi"

    def test_weather_location(self, mock_config_manager):
        mock_config_manager._feature_configs["weather"] = {"location": "Boston, MA"}
        assert Config.WEATHER_LOCATION == "Boston, MA"

    def test_weather_location_default(self, mock_config_manager):
        assert Config.WEATHER_LOCATION == ""

    def test_weather_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["weather"] = {"enabled": True}
        assert Config.WEATHER_ENABLED is True

    def test_weather_enabled_default(self, mock_config_manager):
        assert Config.WEATHER_ENABLED is False

    def test_weather_refresh_seconds(self, mock_config_manager):
        mock_config_manager._feature_configs["weather"] = {"refresh_seconds": 600}
        assert Config.WEATHER_REFRESH_SECONDS == 600

    def test_weather_refresh_seconds_default(self, mock_config_manager):
        assert Config.WEATHER_REFRESH_SECONDS == 300


class TestWeatherLocations:
    """Test WEATHER_LOCATIONS with various formats."""

    def test_weather_locations_list_format(self, mock_config_manager):
        locations = [
            {"location": "NYC", "name": "New York"},
            {"location": "Boston", "name": "Boston"},
        ]
        mock_config_manager._feature_configs["weather"] = {"locations": locations}
        assert locations == Config.WEATHER_LOCATIONS

    def test_weather_locations_single_dict_wrapped_in_list(self, mock_config_manager):
        single = {"location": "SF", "name": "San Francisco"}
        mock_config_manager._feature_configs["weather"] = {"locations": single}
        assert [single] == Config.WEATHER_LOCATIONS

    def test_weather_locations_old_single_location_fallback(self, mock_config_manager):
        mock_config_manager._feature_configs["weather"] = {"location": "Chicago, IL"}
        result = Config.WEATHER_LOCATIONS
        assert result == [{"location": "Chicago, IL", "name": "HOME"}]

    def test_weather_locations_empty(self, mock_config_manager):
        assert Config.WEATHER_LOCATIONS == []


# ==================== DateTime Configuration ====================


class TestDateTimeConfig:
    """Test date_time configuration."""

    def test_timezone(self, mock_config_manager):
        mock_config_manager._feature_configs["date_time"] = {"timezone": "Europe/London"}
        assert Config.TIMEZONE == "Europe/London"

    def test_timezone_default(self, mock_config_manager):
        assert Config.TIMEZONE == ""

    def test_datetime_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["date_time"] = {"enabled": False}
        assert Config.DATETIME_ENABLED is False

    def test_datetime_enabled_default(self, mock_config_manager):
        mock_config_manager._feature_configs["date_time"] = {"enabled": True}
        assert Config.DATETIME_ENABLED is True


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


# ==================== Star Trek Quotes ====================


class TestStarTrekConfig:
    """Test Star Trek quotes configuration."""

    def test_star_trek_quotes_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["star_trek_quotes"] = {"enabled": True}
        assert Config.STAR_TREK_QUOTES_ENABLED is True

    def test_star_trek_quotes_ratio(self, mock_config_manager):
        mock_config_manager._feature_configs["star_trek_quotes"] = {"ratio": "1:2:3"}
        assert Config.STAR_TREK_QUOTES_RATIO == "1:2:3"

    def test_star_trek_quotes_ratio_default(self, mock_config_manager):
        assert Config.STAR_TREK_QUOTES_RATIO == "3:5:9"


# ==================== Surf Configuration ====================


class TestSurfConfig:
    """Test surf configuration."""

    def test_surf_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["surf"] = {"enabled": True}
        assert Config.SURF_ENABLED is True

    def test_surf_latitude(self, mock_config_manager):
        mock_config_manager._feature_configs["surf"] = {"latitude": 40.0}
        assert Config.SURF_LATITUDE == 40.0

    def test_surf_latitude_default(self, mock_config_manager):
        assert Config.SURF_LATITUDE == 37.7599

    def test_surf_longitude(self, mock_config_manager):
        mock_config_manager._feature_configs["surf"] = {"longitude": -120.0}
        assert Config.SURF_LONGITUDE == -120.0

    def test_surf_refresh_seconds(self, mock_config_manager):
        mock_config_manager._feature_configs["surf"] = {"refresh_seconds": 900}
        assert Config.SURF_REFRESH_SECONDS == 900


# ==================== Guest WiFi Configuration ====================


class TestGuestWifiConfig:
    """Test guest WiFi configuration."""

    def test_guest_wifi_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["guest_wifi"] = {"enabled": True}
        assert Config.GUEST_WIFI_ENABLED is True

    def test_guest_wifi_ssid(self, mock_config_manager):
        mock_config_manager._feature_configs["guest_wifi"] = {"ssid": "GuestNet"}
        assert Config.GUEST_WIFI_SSID == "GuestNet"

    def test_guest_wifi_password(self, mock_config_manager):
        mock_config_manager._feature_configs["guest_wifi"] = {"password": "secret123"}
        assert Config.GUEST_WIFI_PASSWORD == "secret123"

    def test_guest_wifi_refresh_seconds(self, mock_config_manager):
        mock_config_manager._feature_configs["guest_wifi"] = {"refresh_seconds": 120}
        assert Config.GUEST_WIFI_REFRESH_SECONDS == 120


# ==================== Home Assistant Configuration ====================


class TestHomeAssistantConfig:
    """Test Home Assistant configuration."""

    def test_home_assistant_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["home_assistant"] = {"enabled": True}
        assert Config.HOME_ASSISTANT_ENABLED is True

    def test_home_assistant_base_url(self, mock_config_manager):
        mock_config_manager._feature_configs["home_assistant"] = {"base_url": "http://ha.local:8123"}
        assert Config.HOME_ASSISTANT_BASE_URL == "http://ha.local:8123"

    def test_home_assistant_access_token(self, mock_config_manager):
        mock_config_manager._feature_configs["home_assistant"] = {"access_token": "token-abc"}
        assert Config.HOME_ASSISTANT_ACCESS_TOKEN == "token-abc"

    def test_home_assistant_entities_returns_json_string(self, mock_config_manager):
        entities = [{"entity_id": "light.living", "name": "Living Room"}]
        mock_config_manager._feature_configs["home_assistant"] = {"entities": entities}
        result = Config.HOME_ASSISTANT_ENTITIES
        assert result == json.dumps(entities)
        assert json.loads(result) == entities

    def test_home_assistant_timeout(self, mock_config_manager):
        mock_config_manager._feature_configs["home_assistant"] = {"timeout": 10}
        assert Config.HOME_ASSISTANT_TIMEOUT == 10

    def test_home_assistant_timeout_default(self, mock_config_manager):
        assert Config.HOME_ASSISTANT_TIMEOUT == 5

    def test_home_assistant_refresh_seconds(self, mock_config_manager):
        mock_config_manager._feature_configs["home_assistant"] = {"refresh_seconds": 60}
        assert Config.HOME_ASSISTANT_REFRESH_SECONDS == 60


# ==================== Air/Fog Configuration ====================


class TestAirFogConfig:
    """Test air quality/fog configuration."""

    def test_air_fog_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["air_fog"] = {"enabled": True}
        assert Config.AIR_FOG_ENABLED is True

    def test_purpleair_api_key(self, mock_config_manager):
        mock_config_manager._feature_configs["air_fog"] = {"purpleair_api_key": "pa-key"}
        assert Config.PURPLEAIR_API_KEY == "pa-key"

    def test_purpleair_sensor_id(self, mock_config_manager):
        mock_config_manager._feature_configs["air_fog"] = {"purpleair_sensor_id": "12345"}
        assert Config.PURPLEAIR_SENSOR_ID == "12345"

    def test_openweathermap_api_key(self, mock_config_manager):
        mock_config_manager._feature_configs["air_fog"] = {"openweathermap_api_key": "owm-key"}
        assert Config.OPENWEATHERMAP_API_KEY == "owm-key"

    def test_air_fog_latitude(self, mock_config_manager):
        mock_config_manager._feature_configs["air_fog"] = {"latitude": 40.0}
        assert Config.AIR_FOG_LATITUDE == 40.0

    def test_air_fog_longitude(self, mock_config_manager):
        mock_config_manager._feature_configs["air_fog"] = {"longitude": -74.0}
        assert Config.AIR_FOG_LONGITUDE == -74.0

    def test_air_fog_refresh_seconds(self, mock_config_manager):
        mock_config_manager._feature_configs["air_fog"] = {"refresh_seconds": 600}
        assert Config.AIR_FOG_REFRESH_SECONDS == 600


# ==================== Muni Configuration ====================


class TestMuniConfig:
    """Test Muni transit configuration."""

    def test_muni_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"enabled": True}
        assert Config.MUNI_ENABLED is True

    def test_muni_api_key(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"api_key": "511-key"}
        assert Config.MUNI_API_KEY == "511-key"

    def test_muni_stop_code_returns_first_from_list(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"stop_codes": ["15726", "15727"]}
        assert Config.MUNI_STOP_CODE == "15726"

    def test_muni_stop_code_old_format_fallback(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"stop_code": "12345"}
        assert Config.MUNI_STOP_CODE == "12345"

    def test_muni_stop_codes_array_format(self, mock_config_manager):
        codes = ["15726", "15727"]
        mock_config_manager._feature_configs["muni"] = {"stop_codes": codes}
        assert codes == Config.MUNI_STOP_CODES

    def test_muni_stop_codes_single_value_wrapped(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"stop_codes": "15726"}
        assert Config.MUNI_STOP_CODES == ["15726"]

    def test_muni_stop_codes_old_single_format_fallback(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"stop_code": "15726"}
        assert Config.MUNI_STOP_CODES == ["15726"]

    def test_muni_stop_names(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"stop_names": ["Market & Castro", "Church & Duboce"]}
        assert Config.MUNI_STOP_NAMES == ["Market & Castro", "Church & Duboce"]

    def test_muni_line_name(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"line_name": "N"}
        assert Config.MUNI_LINE_NAME == "N"

    def test_muni_refresh_seconds(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"refresh_seconds": 90}
        assert Config.MUNI_REFRESH_SECONDS == 90

    def test_transit_cache_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"transit_cache_enabled": False}
        assert Config.TRANSIT_CACHE_ENABLED is False

    def test_transit_cache_refresh_seconds(self, mock_config_manager):
        mock_config_manager._feature_configs["muni"] = {"transit_cache_refresh_seconds": 120}
        assert Config.TRANSIT_CACHE_REFRESH_SECONDS == 120


# ==================== Bay Wheels Configuration ====================


class TestBayWheelsConfig:
    """Test Bay Wheels configuration."""

    def test_baywheels_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["baywheels"] = {"enabled": True}
        assert Config.BAYWHEELS_ENABLED is True

    def test_baywheels_station_id_returns_first_from_list(self, mock_config_manager):
        mock_config_manager._feature_configs["baywheels"] = {"station_ids": ["123", "456"]}
        assert Config.BAYWHEELS_STATION_ID == "123"

    def test_baywheels_station_id_old_format_fallback(self, mock_config_manager):
        mock_config_manager._feature_configs["baywheels"] = {"station_id": "789"}
        assert Config.BAYWHEELS_STATION_ID == "789"

    def test_baywheels_station_ids_array_format(self, mock_config_manager):
        ids = ["123", "456"]
        mock_config_manager._feature_configs["baywheels"] = {"station_ids": ids}
        assert ids == Config.BAYWHEELS_STATION_IDS

    def test_baywheels_station_ids_single_string(self, mock_config_manager):
        mock_config_manager._feature_configs["baywheels"] = {"station_ids": "123"}
        assert Config.BAYWHEELS_STATION_IDS == ["123"]

    def test_baywheels_station_ids_old_format_single_string(self, mock_config_manager):
        mock_config_manager._feature_configs["baywheels"] = {"station_id": "123"}
        assert Config.BAYWHEELS_STATION_IDS == ["123"]

    def test_baywheels_station_ids_old_format_list(self, mock_config_manager):
        mock_config_manager._feature_configs["baywheels"] = {"station_id": ["123"]}
        assert Config.BAYWHEELS_STATION_IDS == ["123"]

    def test_baywheels_station_name(self, mock_config_manager):
        mock_config_manager._feature_configs["baywheels"] = {"station_name": "Castro"}
        assert Config.BAYWHEELS_STATION_NAME == "Castro"

    def test_baywheels_station_name_default(self, mock_config_manager):
        assert Config.BAYWHEELS_STATION_NAME == "19TH"

    def test_baywheels_refresh_seconds(self, mock_config_manager):
        mock_config_manager._feature_configs["baywheels"] = {"refresh_seconds": 120}
        assert Config.BAYWHEELS_REFRESH_SECONDS == 120


# ==================== Traffic Configuration ====================


class TestTrafficConfig:
    """Test traffic configuration."""

    def test_traffic_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["traffic"] = {"enabled": True}
        assert Config.TRAFFIC_ENABLED is True

    def test_google_routes_api_key(self, mock_config_manager):
        mock_config_manager._feature_configs["traffic"] = {"api_key": "google-key"}
        assert Config.GOOGLE_ROUTES_API_KEY == "google-key"

    def test_traffic_origin(self, mock_config_manager):
        mock_config_manager._feature_configs["traffic"] = {"origin": "123 Main St"}
        assert Config.TRAFFIC_ORIGIN == "123 Main St"

    def test_traffic_destination(self, mock_config_manager):
        mock_config_manager._feature_configs["traffic"] = {"destination": "456 Oak Ave"}
        assert Config.TRAFFIC_DESTINATION == "456 Oak Ave"

    def test_traffic_destination_name(self, mock_config_manager):
        mock_config_manager._feature_configs["traffic"] = {"destination_name": "Downtown SF"}
        assert Config.TRAFFIC_DESTINATION_NAME == "Downtown SF"

    def test_traffic_destination_name_default(self, mock_config_manager):
        assert Config.TRAFFIC_DESTINATION_NAME == "DOWNTOWN"

    def test_traffic_routes_array_format(self, mock_config_manager):
        routes = [
            {"origin": "A", "destination": "B", "destination_name": "B"},
            {"origin": "C", "destination": "D", "destination_name": "D"},
        ]
        mock_config_manager._feature_configs["traffic"] = {"routes": routes}
        assert routes == Config.TRAFFIC_ROUTES

    def test_traffic_routes_single_dict_wrapped(self, mock_config_manager):
        route = {"origin": "A", "destination": "B", "destination_name": "B"}
        mock_config_manager._feature_configs["traffic"] = {"routes": route}
        assert [route] == Config.TRAFFIC_ROUTES

    def test_traffic_routes_old_format_fallback(self, mock_config_manager):
        mock_config_manager._feature_configs["traffic"] = {
            "origin": "Home",
            "destination": "Work",
            "destination_name": "Office",
        }
        result = Config.TRAFFIC_ROUTES
        assert result == [
            {
                "origin": "Home",
                "destination": "Work",
                "destination_name": "Office",
            }
        ]

    def test_traffic_routes_empty_when_no_origin_destination(self, mock_config_manager):
        mock_config_manager._feature_configs["traffic"] = {}
        assert Config.TRAFFIC_ROUTES == []

    def test_traffic_refresh_seconds(self, mock_config_manager):
        mock_config_manager._feature_configs["traffic"] = {"refresh_seconds": 600}
        assert Config.TRAFFIC_REFRESH_SECONDS == 600


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


# ==================== Stocks Configuration ====================


class TestStocksConfig:
    """Test stocks configuration."""

    def test_stocks_enabled(self, mock_config_manager):
        mock_config_manager._feature_configs["stocks"] = {"enabled": True}
        assert Config.STOCKS_ENABLED is True

    def test_finnhub_api_key(self, mock_config_manager):
        mock_config_manager._feature_configs["stocks"] = {"finnhub_api_key": "fh-key"}
        assert Config.FINNHUB_API_KEY == "fh-key"

    def test_stocks_symbols_list(self, mock_config_manager):
        mock_config_manager._feature_configs["stocks"] = {"symbols": ["AAPL", "GOOG", "MSFT"]}
        assert Config.STOCKS_SYMBOLS == ["AAPL", "GOOG", "MSFT"]

    def test_stocks_symbols_string_converted_to_list(self, mock_config_manager):
        mock_config_manager._feature_configs["stocks"] = {"symbols": "AAPL"}
        assert Config.STOCKS_SYMBOLS == ["AAPL"]

    def test_stocks_symbols_empty_string(self, mock_config_manager):
        mock_config_manager._feature_configs["stocks"] = {"symbols": ""}
        assert Config.STOCKS_SYMBOLS == []

    def test_stocks_symbols_max_five(self, mock_config_manager):
        mock_config_manager._feature_configs["stocks"] = {"symbols": ["A", "B", "C", "D", "E", "F"]}
        assert Config.STOCKS_SYMBOLS == ["A", "B", "C", "D", "E"]

    def test_stocks_symbols_empty_list(self, mock_config_manager):
        mock_config_manager._feature_configs["stocks"] = {"symbols": []}
        assert Config.STOCKS_SYMBOLS == []

    def test_stocks_time_window(self, mock_config_manager):
        mock_config_manager._feature_configs["stocks"] = {"time_window": "1 Week"}
        assert Config.STOCKS_TIME_WINDOW == "1 Week"

    def test_stocks_time_window_default(self, mock_config_manager):
        assert Config.STOCKS_TIME_WINDOW == "1 Day"

    def test_stocks_refresh_seconds(self, mock_config_manager):
        mock_config_manager._feature_configs["stocks"] = {"refresh_seconds": 600}
        assert Config.STOCKS_REFRESH_SECONDS == 600


# ==================== Helper Methods ====================


class TestGetHaEntities:
    """Test get_ha_entities helper."""

    def test_get_ha_entities_returns_list(self, mock_config_manager):
        entities = [{"entity_id": "light.living", "name": "Living"}]
        mock_config_manager._feature_configs["home_assistant"] = {"entities": entities}
        assert Config.get_ha_entities() == entities

    def test_get_ha_entities_empty_when_not_list(self, mock_config_manager):
        mock_config_manager._feature_configs["home_assistant"] = {"entities": "invalid"}
        assert Config.get_ha_entities() == []


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
        mock_config_manager._feature_configs["weather"] = {"api_key": "key", "enabled": True}
        mock_config_manager._feature_configs["date_time"] = {"timezone": "America/LA"}
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
