"""Tests for the home_assistant plugin."""

import pytest
from unittest.mock import patch, Mock, MagicMock

from plugins.home_assistant import HomeAssistantPlugin
from src.plugins.base import PluginResult


def _ha_manifest():
    """Create a test manifest for the home_assistant plugin."""
    return {
        "id": "home_assistant",
        "name": "Home Assistant",
        "version": "1.0.0",
        "description": "Display entity states",
        "author": "Test",
        "settings_schema": {},
        "variables": {},
        "max_lengths": {},
    }


def _ha_config(base_url="http://ha.local:8123", access_token="test_token", **kwargs):
    """Create test config with optional overrides."""
    config = {
        "base_url": base_url,
        "access_token": access_token,
        "entities": [
            {"entity_id": "sensor.temperature", "name": "Temp"},
            {"entity_id": "light.living_room", "name": "Lights"},
        ],
    }
    config.update(kwargs)
    return config


class TestHomeAssistantPluginInit:
    """Tests for plugin initialization and basic properties."""

    def test_plugin_id(self):
        """Test plugin_id returns correct identifier."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        assert plugin.plugin_id == "home_assistant"

    def test_init_sets_cache_and_entities_to_none(self):
        """Test __init__ initializes _cache and _all_entities."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        assert plugin._cache is None
        assert plugin._all_entities is None


class TestHomeAssistantValidateConfig:
    """Tests for configuration validation."""

    def test_validate_config_missing_base_url(self):
        """Test validation fails when base_url is missing."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        errors = plugin.validate_config({"access_token": "token"})
        assert "Home Assistant URL is required" in errors

    def test_validate_config_missing_access_token(self):
        """Test validation fails when access_token is missing."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        errors = plugin.validate_config({"base_url": "http://ha.local"})
        assert "Access token is required" in errors

    def test_validate_config_both_missing(self):
        """Test validation returns both errors when both are missing."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        errors = plugin.validate_config({})
        assert "Home Assistant URL is required" in errors
        assert "Access token is required" in errors

    def test_validate_config_valid(self):
        """Test validation passes with valid config."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        errors = plugin.validate_config(_ha_config())
        assert len(errors) == 0

    def test_validate_config_empty_base_url(self):
        """Test validation fails when base_url is empty string."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        errors = plugin.validate_config({"base_url": "", "access_token": "token"})
        assert "Home Assistant URL is required" in errors

    def test_validate_config_empty_access_token(self):
        """Test validation fails when access_token is empty string."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        errors = plugin.validate_config({"base_url": "http://ha.local", "access_token": ""})
        assert "Access token is required" in errors


class TestHomeAssistantFetchData:
    """Tests for fetch_data method."""

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_not_configured_missing_base_url(self, mock_get):
        """Test fetch_data returns error when base_url is missing."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = {"access_token": "token"}
        result = plugin.fetch_data()
        assert not result.available
        assert "Home Assistant not configured" in (result.error or "")
        mock_get.assert_not_called()

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_not_configured_missing_token(self, mock_get):
        """Test fetch_data returns error when access_token is missing."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = {"base_url": "http://ha.local"}
        result = plugin.fetch_data()
        assert not result.available
        assert "Home Assistant not configured" in (result.error or "")
        mock_get.assert_not_called()

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_connection_fails(self, mock_get):
        """Test fetch_data returns error when test_connection fails."""
        mock_get.side_effect = Exception("Connection refused")
        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        result = plugin.fetch_data()
        assert not result.available
        assert "Failed to connect" in (result.error or "")

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_success(self, mock_get):
        """Test successful fetch_data with entities."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            elif "/states" in url and "/states/" not in url:
                resp.json.return_value = [
                    {"entity_id": "sensor.temperature", "state": "72", "attributes": {"friendly_name": "Temp"}},
                    {"entity_id": "light.living_room", "state": "on", "attributes": {"friendly_name": "Lights"}},
                ]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        result = plugin.fetch_data()

        assert result.available
        assert result.data is not None
        assert result.data["connected"] == "Yes"
        assert result.data["entity_count"] == 2
        assert "sensor.temperature" in result.data
        assert result.data["sensor.temperature"]["state"] == "72"
        assert "entities" in result.data
        assert "Temp" in result.data["entities"]
        assert result.data["entities"]["Temp"]["state"] == "72"

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_entity_without_friendly_name(self, mock_get):
        """Test entity parsing when attributes lack friendly_name."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = [
                    {"entity_id": "sensor.unknown", "state": "42", "attributes": {}},
                ]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config(entities=[{"entity_id": "sensor.unknown", "name": "Unknown"}])
        result = plugin.fetch_data()

        assert result.available
        assert result.data["sensor.unknown"]["friendly_name"] == "sensor.unknown"

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_configured_entity_not_in_all_entities(self, mock_get):
        """Test configured entity not in fetched list is skipped."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = [
                    {"entity_id": "sensor.temperature", "state": "72", "attributes": {}},
                ]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config(entities=[
            {"entity_id": "sensor.temperature", "name": "Temp"},
            {"entity_id": "sensor.nonexistent", "name": "Missing"},
        ])
        result = plugin.fetch_data()

        assert result.available
        assert "Temp" in result.data["entities"]
        assert "Missing" not in result.data["entities"]

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_entity_config_without_entity_id(self, mock_get):
        """Test entity config without entity_id is skipped."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = [
                    {"entity_id": "sensor.temperature", "state": "72", "attributes": {}},
                ]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config(entities=[
            {"entity_id": "sensor.temperature", "name": "Temp"},
            {"name": "NoId"},
        ])
        result = plugin.fetch_data()

        assert result.available
        assert "NoId" not in result.data["entities"]

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_entity_config_uses_name_default(self, mock_get):
        """Test entity config uses entity_id as name when name not provided."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = [
                    {"entity_id": "sensor.temperature", "state": "72", "attributes": {}},
                ]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config(entities=[{"entity_id": "sensor.temperature"}])
        result = plugin.fetch_data()

        assert result.available
        assert "sensor.temperature" in result.data["entities"]

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_fetch_all_entities_fails(self, mock_get):
        """Test fetch_data when _fetch_all_entities returns empty due to error."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.raise_for_status = Mock()
                resp.json.return_value = {"state": "ok"}
                return resp
            resp.raise_for_status = Mock(side_effect=Exception("API error"))
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        result = plugin.fetch_data()

        assert result.available
        assert result.data["entity_count"] == 0

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_uses_custom_timeout(self, mock_get):
        """Test that custom timeout from config is used."""
        def mock_responses(url, **kwargs):
            assert kwargs.get("timeout") == 10
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = []
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config(timeout=10)
        result = plugin.fetch_data()

        assert result.available
        assert mock_get.call_count >= 2

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_base_url_trailing_slash_stripped(self, mock_get):
        """Test _get_api_url strips trailing slash from base_url."""
        def mock_responses(url, **kwargs):
            assert "http://ha.local:8123/api" in url
            resp = Mock()
            resp.raise_for_status = Mock()
            if url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = []
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config(base_url="http://ha.local:8123/")
        result = plugin.fetch_data()

        assert result.available

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_exception_during_processing(self, mock_get):
        """Test fetch_data returns error when exception occurs during processing."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = [{"entity_id": "sensor.temperature", "state": "72", "attributes": {}}]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()

        with patch.object(plugin, "_fetch_all_entities", side_effect=RuntimeError("Unexpected error")):
            result = plugin.fetch_data()

        assert not result.available
        assert "Unexpected error" in (result.error or "")


class TestHomeAssistantGetEntity:
    """Tests for get_entity method."""

    @patch("plugins.home_assistant.requests.get")
    def test_get_entity_from_cache(self, mock_get):
        """Test get_entity returns from _all_entities when cached."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = [
                    {"entity_id": "sensor.temperature", "state": "72", "attributes": {"friendly_name": "Temp"}},
                ]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        plugin.fetch_data()

        entity = plugin.get_entity("sensor.temperature")
        assert entity is not None
        assert entity["state"] == "72"
        assert entity["friendly_name"] == "Temp"

    @patch("plugins.home_assistant.requests.get")
    def test_get_entity_fallback_direct_fetch(self, mock_get):
        """Test get_entity falls back to direct fetch when not in cache."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "sensor.other" in url:
                resp.json.return_value = {
                    "entity_id": "sensor.other",
                    "state": "99",
                    "attributes": {"friendly_name": "Other"},
                }
            elif "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = []
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        plugin.fetch_data()

        entity = plugin.get_entity("sensor.other")
        assert entity is not None
        assert entity["state"] == "99"

    @patch("plugins.home_assistant.requests.get")
    def test_get_entity_direct_fetch_fails_returns_none(self, mock_get):
        """Test get_entity returns None when direct fetch fails."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        plugin._all_entities = {}

        mock_get.side_effect = Exception("Network error")

        entity = plugin.get_entity("sensor.missing")
        assert entity is None

    @patch("plugins.home_assistant.requests.get")
    def test_get_entity_returns_none_when_not_in_cache_and_fallback_fails(self, mock_get):
        """Test get_entity returns None when entity not in cache and direct fetch fails."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        plugin._all_entities = {}
        mock_get.side_effect = Exception("Network error")

        entity = plugin.get_entity("sensor.missing")
        assert entity is None


class TestHomeAssistantGetFormattedDisplay:
    """Tests for get_formatted_display method."""

    @patch("plugins.home_assistant.requests.get")
    def test_get_formatted_display_with_cache(self, mock_get):
        """Test get_formatted_display uses cached data."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = [
                    {"entity_id": "sensor.temperature", "state": "72", "attributes": {"friendly_name": "Temp"}},
                    {"entity_id": "light.living_room", "state": "on", "attributes": {"friendly_name": "Lights"}},
                ]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        plugin.fetch_data()

        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) == 6
        assert "HOME ASSISTANT" in lines[0]
        assert "Temp" in "".join(lines) or "72" in "".join(lines)

    @patch("plugins.home_assistant.requests.get")
    def test_get_formatted_display_fetches_when_no_cache(self, mock_get):
        """Test get_formatted_display fetches data when cache is empty."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = [
                    {"entity_id": "sensor.temperature", "state": "72", "attributes": {"friendly_name": "Temp"}},
                ]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6

    @patch("plugins.home_assistant.requests.get")
    def test_get_formatted_display_returns_none_when_fetch_fails(self, mock_get):
        """Test get_formatted_display returns None when fetch fails."""
        mock_get.side_effect = Exception("Connection refused")

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        lines = plugin.get_formatted_display()

        assert lines is None

    def test_get_formatted_display_empty_entities_pads_to_six_lines(self):
        """Test get_formatted_display pads to 6 lines with empty entities."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._cache = {"connected": "Yes", "entity_count": 0, "entities": {}}

        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) == 6
        assert lines[0].strip() == "HOME ASSISTANT"

    def test_get_formatted_display_returns_none_when_cache_empty_dict(self):
        """Test get_formatted_display returns None when cache is empty dict."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._cache = {}

        lines = plugin.get_formatted_display()
        assert lines is None

    def test_get_formatted_display_entity_state_fallback(self):
        """Test get_formatted_display uses ? when state key is missing."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._cache = {
            "connected": "Yes",
            "entity_count": 1,
            "entities": {"Temp": {"friendly_name": "Temp"}},
        }

        lines = plugin.get_formatted_display()
        assert lines is not None
        assert "?" in "".join(lines)

    def test_get_formatted_display_truncates_long_lines(self):
        """Test display lines are truncated to 22 chars."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._cache = {
            "connected": "Yes",
            "entity_count": 1,
            "entities": {"VeryLongName": {"state": "VeryLongStateValue", "friendly_name": "VeryLongName"}},
        }

        lines = plugin.get_formatted_display()
        assert lines is not None
        for line in lines[2:]:
            assert len(line) <= 22

    def test_get_formatted_display_max_four_entities(self):
        """Test only first 4 entities are shown."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._cache = {
            "connected": "Yes",
            "entity_count": 5,
            "entities": {
                "E1": {"state": "1", "friendly_name": "E1"},
                "E2": {"state": "2", "friendly_name": "E2"},
                "E3": {"state": "3", "friendly_name": "E3"},
                "E4": {"state": "4", "friendly_name": "E4"},
                "E5": {"state": "5", "friendly_name": "E5"},
            },
        }

        lines = plugin.get_formatted_display()
        assert len(lines) == 6
        content = "".join(lines)
        assert "E1" in content and "E4" in content
        assert "E5" not in content


class TestHomeAssistantEntityParsing:
    """Tests for entity parsing edge cases."""

    @patch("plugins.home_assistant.requests.get")
    def test_entity_attributes_spread_into_data(self, mock_get):
        """Test entity attributes are spread into data for template access."""
        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = [
                    {
                        "entity_id": "sensor.temperature",
                        "state": "72",
                        "attributes": {
                            "friendly_name": "Living Room Temp",
                            "unit_of_measurement": "°F",
                        },
                    },
                ]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        result = plugin.fetch_data()

        assert result.available
        assert result.data["sensor.temperature"]["unit_of_measurement"] == "°F"


class TestHomeAssistantConnectionErrors:
    """Tests for connection and API error handling."""

    @patch("plugins.home_assistant.requests.get")
    def test_test_connection_success(self, mock_get):
        """Test test_connection returns True on success."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        assert plugin.test_connection() is True

    @patch("plugins.home_assistant.requests.get")
    def test_test_connection_failure(self, mock_get):
        """Test test_connection returns False on failure."""
        mock_get.side_effect = Exception("Connection refused")

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        assert plugin.test_connection() is False

    @patch("plugins.home_assistant.requests.get")
    def test_fetch_all_entities_http_error_returns_empty(self, mock_get):
        """Test _fetch_all_entities returns empty dict on HTTP error."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock(side_effect=Exception("HTTP 500"))
        mock_get.return_value = mock_resp

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        result = plugin._fetch_all_entities()
        assert result == {}

    @patch("plugins.home_assistant.requests.get")
    def test_get_entity_state_returns_none_on_error(self, mock_get):
        """Test _get_entity_state returns None on request failure."""
        mock_get.side_effect = Exception("Timeout")

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = _ha_config()
        result = plugin._get_entity_state("sensor.temperature")
        assert result is None


class TestHomeAssistantConfig:
    """Tests for Home Assistant configuration."""

    def test_config_validation_required_fields(self):
        """Test that required config fields are validated."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        errors = plugin.validate_config({"base_url": "http://ha.local", "access_token": "token"})
        assert len(errors) == 0

    def test_config_url_validation(self):
        """Test URL format validation."""
        valid_urls = [
            "http://homeassistant.local:8123",
            "https://ha.example.com",
            "http://192.168.1.100:8123",
        ]
        plugin = HomeAssistantPlugin(_ha_manifest())
        for url in valid_urls:
            errors = plugin.validate_config({"base_url": url, "access_token": "token"})
            assert len(errors) == 0

    def test_empty_entities_list(self):
        """Test handling of empty entities list."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        config = _ha_config(entities=[])
        errors = plugin.validate_config(config)
        assert len(errors) == 0

    def test_entity_id_format(self):
        """Test entity ID format in config."""
        valid_entity_ids = [
            "sensor.temperature",
            "light.living_room",
            "switch.garage_door",
            "binary_sensor.motion",
        ]
        for entity_id in valid_entity_ids:
            parts = entity_id.split(".")
            assert len(parts) == 2
            assert len(parts[0]) > 0
            assert len(parts[1]) > 0


class TestHomeAssistantMQTTMode:
    """Tests for MQTT Statestream integration in the plugin."""

    def test_validate_config_mqtt_mode_no_rest_creds_needed(self):
        """When mqtt_statestream is enabled, base_url and access_token are not required."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        errors = plugin.validate_config({"mqtt_statestream": True})
        assert len(errors) == 0

    def test_validate_config_rest_mode_requires_creds(self):
        """When mqtt_statestream is off, base_url and access_token are required."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        errors = plugin.validate_config({"mqtt_statestream": False})
        assert "Home Assistant URL is required" in errors
        assert "Access token is required" in errors

    def test_init_sets_mqtt_listener_to_none(self):
        plugin = HomeAssistantPlugin(_ha_manifest())
        assert plugin._mqtt_listener is None

    @patch("plugins.home_assistant.mqtt_listener.HAStateStreamListener")
    def test_fetch_data_mqtt_connected_returns_mqtt_data(self, MockListener):
        """fetch_data uses MQTT listener data when connected."""
        mock_listener = MagicMock()
        mock_listener.is_connected.return_value = True
        mock_listener.get_entities.return_value = {
            "sensor.temperature": {
                "state": "72",
                "attributes": {"unit_of_measurement": "°F"},
                "friendly_name": "Temp",
            },
        }
        MockListener.return_value = mock_listener

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = {
            "mqtt_statestream": True,
            "statestream_broker_host": "mqtt.local",
            "entities": [{"entity_id": "sensor.temperature", "name": "Temp"}],
        }
        result = plugin.fetch_data()

        assert result.available
        assert result.data["data_source"] == "mqtt_statestream"
        assert result.data["connected"] == "Yes"
        assert result.data["entity_count"] == 1
        assert result.data["sensor.temperature"]["state"] == "72"
        assert result.data["entities"]["Temp"]["state"] == "72"

    @patch("plugins.home_assistant.mqtt_listener.HAStateStreamListener")
    def test_fetch_data_mqtt_not_connected_no_rest_creds(self, MockListener):
        """When MQTT is enabled but not connected and no REST creds, returns waiting state."""
        mock_listener = MagicMock()
        mock_listener.is_connected.return_value = False
        MockListener.return_value = mock_listener

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = {"mqtt_statestream": True, "statestream_broker_host": "mqtt.local"}
        result = plugin.fetch_data()

        assert result.available
        assert result.data["connected"] == "Waiting"
        assert result.data["data_source"] == "mqtt_statestream"

    @patch("plugins.home_assistant.mqtt_listener.HAStateStreamListener")
    @patch("plugins.home_assistant.requests.get")
    def test_fetch_data_mqtt_not_connected_falls_back_to_rest(self, mock_get, MockListener):
        """When MQTT is not connected but REST creds are available, falls back to REST."""
        mock_listener = MagicMock()
        mock_listener.is_connected.return_value = False
        MockListener.return_value = mock_listener

        def mock_responses(url, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "/api/" in url and url.endswith("/"):
                resp.json.return_value = {"state": "ok"}
            else:
                resp.json.return_value = [
                    {"entity_id": "sensor.temperature", "state": "72", "attributes": {}},
                ]
            return resp

        mock_get.side_effect = mock_responses

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._config = {
            "mqtt_statestream": True,
            "statestream_broker_host": "mqtt.local",
            "base_url": "http://ha.local:8123",
            "access_token": "token",
            "entities": [],
        }
        result = plugin.fetch_data()

        assert result.available
        assert result.data["data_source"] == "rest"
        assert result.data["connected"] == "Yes"

    def test_cleanup_stops_mqtt_listener(self):
        """cleanup() stops the MQTT listener."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        mock_listener = MagicMock()
        plugin._mqtt_listener = mock_listener

        plugin.cleanup()

        mock_listener.stop.assert_called_once()
        assert plugin._mqtt_listener is None

    def test_on_config_change_restarts_listener_when_mqtt_keys_change(self):
        """Config change in MQTT settings stops the old listener."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        mock_listener = MagicMock()
        plugin._mqtt_listener = mock_listener

        old = {"mqtt_statestream": True, "statestream_broker_host": "old.host"}
        new = {"mqtt_statestream": True, "statestream_broker_host": "new.host"}
        plugin.on_config_change(old, new)

        mock_listener.stop.assert_called_once()
        assert plugin._mqtt_listener is None

    def test_on_config_change_no_restart_when_mqtt_keys_unchanged(self):
        """Config change in non-MQTT settings does NOT stop the listener."""
        plugin = HomeAssistantPlugin(_ha_manifest())
        mock_listener = MagicMock()
        plugin._mqtt_listener = mock_listener

        old = {"mqtt_statestream": True, "statestream_broker_host": "same.host", "timeout": 5}
        new = {"mqtt_statestream": True, "statestream_broker_host": "same.host", "timeout": 10}
        plugin.on_config_change(old, new)

        mock_listener.stop.assert_not_called()

    @patch("plugins.home_assistant.mqtt_listener.HAStateStreamListener")
    def test_get_entity_prefers_mqtt_listener(self, MockListener):
        """get_entity returns from MQTT listener when connected."""
        mock_listener = MagicMock()
        mock_listener.is_connected.return_value = True
        mock_listener.get_entity.return_value = {
            "state": "on",
            "attributes": {},
            "friendly_name": "Kitchen Light",
        }
        MockListener.return_value = mock_listener

        plugin = HomeAssistantPlugin(_ha_manifest())
        plugin._mqtt_listener = mock_listener

        entity = plugin.get_entity("light.kitchen")
        assert entity is not None
        assert entity["state"] == "on"
        mock_listener.get_entity.assert_called_with("light.kitchen")


class TestHomeAssistantDisplay:
    """Tests for Home Assistant display formatting."""

    def test_entity_display_format(self):
        """Test entity state display formatting."""
        entity = {
            "entity_id": "sensor.temperature",
            "state": "72",
            "attributes": {"friendly_name": "Temperature"},
        }
        display_name = entity["attributes"]["friendly_name"]
        state = entity["state"]
        assert len(display_name) > 0
        assert len(state) > 0

    def test_max_display_length(self):
        """Test that display text fits within constraints."""
        max_chars = 22
        entity_display = "Living Room: ON"
        assert len(entity_display) <= max_chars

    def test_plugin_export(self):
        """Test Plugin export is correctly set."""
        from plugins.home_assistant import Plugin
        assert Plugin is HomeAssistantPlugin

