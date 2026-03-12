"""Tests for the Home Assistant MQTT Statestream listener."""

import pytest
from unittest.mock import patch, Mock, MagicMock, call

from plugins.home_assistant.mqtt_listener import HAStateStreamListener


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_config(**overrides):
    """Return a minimal statestream config."""
    config = {
        "mqtt_statestream": True,
        "statestream_base_topic": "homeassistant/statestream",
        "statestream_broker_host": "mqtt.local",
        "statestream_broker_port": 1883,
    }
    config.update(overrides)
    return config


def _make_msg(topic: str, payload: str) -> Mock:
    """Create a mock MQTT message."""
    msg = Mock()
    msg.topic = topic
    msg.payload = payload.encode("utf-8")
    return msg


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestListenerInit:
    """Tests for HAStateStreamListener initialization."""

    def test_defaults(self):
        listener = HAStateStreamListener(_base_config())
        assert listener.is_connected() is False
        assert listener.entity_count == 0
        assert listener.get_entities() == {}

    def test_get_entity_returns_none_when_empty(self):
        listener = HAStateStreamListener(_base_config())
        assert listener.get_entity("sensor.temperature") is None


# ---------------------------------------------------------------------------
# Broker resolution
# ---------------------------------------------------------------------------

class TestBrokerResolution:
    """Tests for host/port/topic resolution logic."""

    def test_host_from_config(self):
        listener = HAStateStreamListener(_base_config(statestream_broker_host="custom.host"))
        assert listener._resolve_broker_host() == "custom.host"

    @patch.dict("os.environ", {"MQTT_BROKER_HOST": "env.host"}, clear=False)
    def test_host_falls_back_to_env(self):
        listener = HAStateStreamListener(_base_config(statestream_broker_host=None))
        # Manually remove the key so falsy check triggers env fallback
        del listener._config["statestream_broker_host"]
        assert listener._resolve_broker_host() == "env.host"

    def test_host_empty_when_nothing_set(self):
        listener = HAStateStreamListener({})
        with patch.dict("os.environ", {}, clear=True):
            assert listener._resolve_broker_host() == ""

    def test_port_from_config(self):
        listener = HAStateStreamListener(_base_config(statestream_broker_port=8883))
        assert listener._resolve_broker_port() == 8883

    @patch.dict("os.environ", {"MQTT_BROKER_PORT": "1884"}, clear=False)
    def test_port_falls_back_to_env(self):
        listener = HAStateStreamListener({})
        assert listener._resolve_broker_port() == 1884

    def test_port_defaults_to_1883(self):
        listener = HAStateStreamListener({})
        with patch.dict("os.environ", {}, clear=True):
            assert listener._resolve_broker_port() == 1883

    def test_base_topic_from_config(self):
        listener = HAStateStreamListener(_base_config(statestream_base_topic="custom/topic"))
        assert listener._resolve_base_topic() == "custom/topic"

    def test_base_topic_default(self):
        listener = HAStateStreamListener({})
        assert listener._resolve_base_topic() == "homeassistant/statestream"


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------

class TestListenerStartStop:
    """Tests for start() and stop() lifecycle."""

    @patch("plugins.home_assistant.mqtt_listener._import_paho")
    def test_start_success(self, mock_paho_fn):
        mock_paho = MagicMock()
        mock_paho.CallbackAPIVersion.VERSION2 = 2
        mock_paho.MQTTv311 = 4
        mock_client = MagicMock()
        mock_paho.Client.return_value = mock_client
        mock_paho_fn.return_value = mock_paho

        listener = HAStateStreamListener(_base_config())
        assert listener.start() is True
        assert listener._running is True

        mock_client.connect_async.assert_called_once_with("mqtt.local", 1883, keepalive=60)
        mock_client.loop_start.assert_called_once()

    @patch("plugins.home_assistant.mqtt_listener._import_paho")
    def test_start_connect_failure(self, mock_paho_fn):
        mock_paho = MagicMock()
        mock_paho.CallbackAPIVersion.VERSION2 = 2
        mock_paho.MQTTv311 = 4
        mock_client = MagicMock()
        mock_client.connect_async.side_effect = ConnectionRefusedError("refused")
        mock_paho.Client.return_value = mock_client
        mock_paho_fn.return_value = mock_paho

        listener = HAStateStreamListener(_base_config())
        assert listener.start() is False
        assert listener._running is False

    def test_start_no_host_returns_false(self):
        listener = HAStateStreamListener({})
        with patch.dict("os.environ", {}, clear=True):
            assert listener.start() is False

    @patch("plugins.home_assistant.mqtt_listener._import_paho")
    def test_start_paho_import_error(self, mock_paho_fn):
        mock_paho_fn.side_effect = ImportError("no paho")
        listener = HAStateStreamListener(_base_config())
        assert listener.start() is False

    @patch("plugins.home_assistant.mqtt_listener._import_paho")
    def test_stop_disconnects(self, mock_paho_fn):
        mock_paho = MagicMock()
        mock_paho.CallbackAPIVersion.VERSION2 = 2
        mock_paho.MQTTv311 = 4
        mock_client = MagicMock()
        mock_paho.Client.return_value = mock_client
        mock_paho_fn.return_value = mock_paho

        listener = HAStateStreamListener(_base_config())
        listener.start()
        listener.stop()

        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()
        assert listener._running is False
        assert listener._client is None

    @patch("plugins.home_assistant.mqtt_listener._import_paho")
    def test_start_already_running(self, mock_paho_fn):
        mock_paho = MagicMock()
        mock_paho.CallbackAPIVersion.VERSION2 = 2
        mock_paho.MQTTv311 = 4
        mock_client = MagicMock()
        mock_paho.Client.return_value = mock_client
        mock_paho_fn.return_value = mock_paho

        listener = HAStateStreamListener(_base_config())
        listener.start()
        # Second start should be a no-op
        assert listener.start() is True
        assert mock_client.connect_async.call_count == 1

    @patch("plugins.home_assistant.mqtt_listener._import_paho")
    def test_start_sets_auth_when_configured(self, mock_paho_fn):
        mock_paho = MagicMock()
        mock_paho.CallbackAPIVersion.VERSION2 = 2
        mock_paho.MQTTv311 = 4
        mock_client = MagicMock()
        mock_paho.Client.return_value = mock_client
        mock_paho_fn.return_value = mock_paho

        config = _base_config(
            statestream_broker_username="user",
            statestream_broker_password="pass",
        )
        listener = HAStateStreamListener(config)
        listener.start()

        mock_client.username_pw_set.assert_called_once_with("user", "pass")


# ---------------------------------------------------------------------------
# on_connect callback
# ---------------------------------------------------------------------------

class TestOnConnect:
    """Tests for the _on_connect callback."""

    def test_on_connect_success_subscribes(self):
        listener = HAStateStreamListener(_base_config())
        mock_client = MagicMock()

        listener._on_connect(mock_client, None, None, 0)

        assert listener.is_connected() is True
        mock_client.subscribe.assert_called_once_with(
            "homeassistant/statestream/+/+/+", qos=0
        )

    def test_on_connect_failure_does_not_subscribe(self):
        listener = HAStateStreamListener(_base_config())
        mock_client = MagicMock()

        listener._on_connect(mock_client, None, None, 5)

        assert listener.is_connected() is False
        mock_client.subscribe.assert_not_called()


# ---------------------------------------------------------------------------
# on_disconnect callback
# ---------------------------------------------------------------------------

class TestOnDisconnect:

    def test_on_disconnect_clears_connected(self):
        listener = HAStateStreamListener(_base_config())
        listener._connected = True
        listener._on_disconnect(MagicMock(), None, None, 0)
        assert listener.is_connected() is False


# ---------------------------------------------------------------------------
# on_message callback — entity state parsing
# ---------------------------------------------------------------------------

class TestOnMessage:
    """Tests for MQTT message parsing and entity store updates."""

    def test_state_update(self):
        listener = HAStateStreamListener(_base_config())
        msg = _make_msg("homeassistant/statestream/sensor/temperature/state", "72.5")
        listener._on_message(None, None, msg)

        entity = listener.get_entity("sensor.temperature")
        assert entity is not None
        assert entity["state"] == "72.5"

    def test_attribute_update(self):
        listener = HAStateStreamListener(_base_config())
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/sensor/temperature/state", "72.5"
        ))
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/sensor/temperature/unit_of_measurement", "°F"
        ))

        entity = listener.get_entity("sensor.temperature")
        assert entity["attributes"]["unit_of_measurement"] == "°F"

    def test_friendly_name_update(self):
        listener = HAStateStreamListener(_base_config())
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/sensor/temperature/friendly_name", "Living Room Temp"
        ))

        entity = listener.get_entity("sensor.temperature")
        assert entity["friendly_name"] == "Living Room Temp"
        assert entity["attributes"]["friendly_name"] == "Living Room Temp"

    def test_multiple_entities(self):
        listener = HAStateStreamListener(_base_config())
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/sensor/temperature/state", "72"
        ))
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/light/kitchen/state", "on"
        ))
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/binary_sensor/door/state", "off"
        ))

        assert listener.entity_count == 3
        entities = listener.get_entities()
        assert "sensor.temperature" in entities
        assert "light.kitchen" in entities
        assert "binary_sensor.door" in entities

    def test_state_overwrites_previous(self):
        listener = HAStateStreamListener(_base_config())
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/sensor/temperature/state", "70"
        ))
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/sensor/temperature/state", "72"
        ))

        assert listener.get_entity("sensor.temperature")["state"] == "72"

    def test_ignores_wrong_base_topic(self):
        listener = HAStateStreamListener(_base_config())
        listener._on_message(None, None, _make_msg(
            "other/topic/sensor/temperature/state", "99"
        ))
        assert listener.entity_count == 0

    def test_ignores_malformed_topic(self):
        listener = HAStateStreamListener(_base_config())
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/only_two_parts", "val"
        ))
        assert listener.entity_count == 0

    def test_empty_payload_stores_empty_string(self):
        listener = HAStateStreamListener(_base_config())
        msg = Mock()
        msg.topic = "homeassistant/statestream/sensor/temperature/state"
        msg.payload = b""
        listener._on_message(None, None, msg)

        assert listener.get_entity("sensor.temperature")["state"] == ""

    def test_custom_base_topic(self):
        listener = HAStateStreamListener(_base_config(statestream_base_topic="ha/stream"))
        listener._on_message(None, None, _make_msg(
            "ha/stream/sensor/temperature/state", "72"
        ))
        assert listener.get_entity("sensor.temperature")["state"] == "72"

    def test_entity_created_on_first_attribute(self):
        """An entity record is created even if we see an attribute before state."""
        listener = HAStateStreamListener(_base_config())
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/sensor/temperature/unit_of_measurement", "°C"
        ))
        entity = listener.get_entity("sensor.temperature")
        assert entity is not None
        assert entity["state"] == ""
        assert entity["attributes"]["unit_of_measurement"] == "°C"


# ---------------------------------------------------------------------------
# Thread-safety (basic)
# ---------------------------------------------------------------------------

class TestThreadSafety:
    """Ensure get_entities returns a snapshot copy."""

    def test_get_entities_returns_copy(self):
        listener = HAStateStreamListener(_base_config())
        listener._on_message(None, None, _make_msg(
            "homeassistant/statestream/sensor/temperature/state", "72"
        ))
        snapshot = listener.get_entities()
        # Mutating the snapshot should not affect internal store
        snapshot["sensor.temperature"]["state"] = "MUTATED"
        assert listener.get_entity("sensor.temperature")["state"] == "72"
