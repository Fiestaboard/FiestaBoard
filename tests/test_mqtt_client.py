"""Tests for MQTT client."""

import pytest
from unittest.mock import MagicMock, patch, call

from src.mqtt.config import MQTTConfig
from src.mqtt.client import MQTTClient, set_mqtt_client_instance, get_mqtt_client


@pytest.fixture
def mqtt_config():
    return MQTTConfig(
        enabled=True,
        broker_host="broker.test",
        broker_port=1883,
        instance_id="fiestaboard_1",
        base_topic="fiestaboard",
        discovery_prefix="homeassistant",
    )


@pytest.fixture
def mock_paho():
    mock_client = MagicMock()
    mock_module = MagicMock()
    mock_module.Client = MagicMock(return_value=mock_client)
    mock_module.CallbackAPIVersion.VERSION2 = 2
    mock_module.MQTTv311 = 4
    return mock_module, mock_client


class TestMQTTClientStart:
    """Tests for MQTTClient.start()."""

    @patch("src.mqtt.client._get_paho_client")
    def test_start_calls_connect_and_loop_start(self, get_paho, mqtt_config, mock_paho):
        mock_module, mock_client = mock_paho
        get_paho.return_value = mock_module
        client = MQTTClient(mqtt_config)
        client.start()
        mock_client.connect_async.assert_called_once_with(
            "broker.test", 1883, keepalive=60
        )
        mock_client.loop_start.assert_called_once()
        assert client.is_running()

    @patch("src.mqtt.client._get_paho_client")
    def test_start_sets_will_set(self, get_paho, mqtt_config, mock_paho):
        mock_module, mock_client = mock_paho
        get_paho.return_value = mock_module
        client = MQTTClient(mqtt_config)
        client.start()
        mock_client.will_set.assert_called_once()
        args, kwargs = mock_client.will_set.call_args
        assert args[0] == "fiestaboard/status"
        assert kwargs.get("payload") == "offline"
        assert kwargs.get("retain") is True

    @patch("src.mqtt.client._get_paho_client")
    def test_start_invalid_config_does_not_connect(self, get_paho, mock_paho):
        mock_module, mock_client = mock_paho
        get_paho.return_value = mock_module
        config = MQTTConfig(enabled=True, broker_host="", broker_port=1883)
        client = MQTTClient(config)
        client.start()
        mock_client.connect_async.assert_not_called()
        assert not client.is_running()

    @patch("src.mqtt.client._get_paho_client")
    def test_start_when_already_running(self, get_paho, mqtt_config, mock_paho):
        mock_module, mock_client = mock_paho
        get_paho.return_value = mock_module
        client = MQTTClient(mqtt_config)
        client.start()
        client.start()
        assert mock_client.connect_async.call_count == 1


class TestMQTTClientOnConnect:
    """Tests for on_connect callback behavior."""

    @patch("src.mqtt.client._get_paho_client")
    def test_on_connect_publishes_status_and_subscribes(self, get_paho, mqtt_config, mock_paho):
        mock_module, mock_client = mock_paho
        get_paho.return_value = mock_module
        client = MQTTClient(mqtt_config)
        client.start()
        client._connected = True
        client._on_connect(mock_client, None, None, 0, None)
        publish_calls = mock_client.publish.call_args_list
        topics = [c[0][0] for c in publish_calls]
        assert "fiestaboard/status" in topics
        mock_client.subscribe.assert_called_once()
        sub_call = mock_client.subscribe.call_args[0][0]
        assert "fiestaboard/+/set" == sub_call


class TestMQTTClientStop:
    """Tests for MQTTClient.stop()."""

    @patch("src.mqtt.client._get_paho_client")
    def test_stop_publishes_offline_and_disconnects(self, get_paho, mqtt_config, mock_paho):
        mock_module, mock_client = mock_paho
        get_paho.return_value = mock_module
        client = MQTTClient(mqtt_config)
        client.start()
        client._connected = True
        client.stop()
        publish_calls = [c[0] for c in mock_client.publish.call_args_list]
        assert any("offline" in str(c) for c in publish_calls)
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()
        assert not client.is_running()


class TestMQTTClientPublishState:
    """Tests for publish_state."""

    @patch("src.mqtt.client._get_paho_client")
    def test_publish_state_when_connected(self, get_paho, mqtt_config, mock_paho):
        mock_module, mock_client = mock_paho
        get_paho.return_value = mock_module
        client = MQTTClient(mqtt_config)
        client._client = mock_client
        client._connected = True
        client.publish_state("schedule_enabled", "ON")
        mock_client.publish.assert_called_once()
        args = mock_client.publish.call_args[0]
        assert args[0] == "fiestaboard/schedule_enabled/state"
        assert args[1] == "ON"

    def test_publish_state_when_not_connected_does_nothing(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._client = MagicMock()
        client._connected = False
        client.publish_state("schedule_enabled", "ON")
        client._client.publish.assert_not_called()


class TestMQTTClientSingleton:
    """Tests for get_mqtt_client / set_mqtt_client_instance."""

    def test_get_mqtt_client_none_by_default(self):
        set_mqtt_client_instance(None)
        assert get_mqtt_client() is None

    def test_set_and_get_mqtt_client(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        set_mqtt_client_instance(client)
        assert get_mqtt_client() is client
        set_mqtt_client_instance(None)
