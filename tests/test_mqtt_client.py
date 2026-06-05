"""Tests for MQTT client."""

from unittest.mock import MagicMock, patch

import pytest

from src.mqtt.client import MQTTClient, get_mqtt_client, set_mqtt_client_instance
from src.mqtt.config import MQTTConfig


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
        mock_client.connect_async.assert_called_once_with("broker.test", 1883, keepalive=60)
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
        assert sub_call == "fiestaboard/+/set"


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


class TestGetPahoClient:
    """Tests for _get_paho_client lazy import."""

    def test_get_paho_client_returns_module(self):
        from src.mqtt.client import _get_paho_client

        mod = _get_paho_client()
        assert hasattr(mod, "Client")


class TestSetters:
    """Tests for set_state_publisher and set_command_handler."""

    def test_set_state_publisher(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        publisher = MagicMock()
        client.set_state_publisher(publisher)
        assert client._state_publisher is publisher

    def test_set_command_handler(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        handler = MagicMock()
        client.set_command_handler(handler)
        assert client._command_handler is handler


class TestStartConnectException:
    """Tests for exception path in start() when connect_async raises."""

    @patch("src.mqtt.client._get_paho_client")
    def test_start_connect_async_exception(self, get_paho, mqtt_config, mock_paho):
        mock_module, mock_client = mock_paho
        get_paho.return_value = mock_module
        mock_client.connect_async.side_effect = OSError("connection refused")
        client = MQTTClient(mqtt_config)
        client.start()
        assert not client.is_running()
        assert client._client is not None  # client was created before exception


class TestStopExceptionPath:
    """Tests for stop() when disconnect raises an exception."""

    @patch("src.mqtt.client._get_paho_client")
    def test_stop_exception_during_disconnect(self, get_paho, mqtt_config, mock_paho):
        mock_module, mock_client = mock_paho
        get_paho.return_value = mock_module
        client = MQTTClient(mqtt_config)
        client._client = mock_client
        client._connected = True
        client._running = True
        mock_client.disconnect.side_effect = Exception("disconnect error")
        client.stop()
        assert not client.is_running()
        assert not client.is_connected()
        assert client._client is None


class TestOnConnectPaths:
    """Tests for _on_connect callback edge cases."""

    def test_on_connect_nonzero_reason_code(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._client = MagicMock()
        client._connected = False
        client._on_connect(client._client, None, None, 5, None)
        assert not client._connected
        client._client.subscribe.assert_not_called()

    @patch("src.mqtt.client.build_all_discovery_messages", return_value=[])
    def test_on_connect_with_state_publisher(self, mock_build, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._client = MagicMock()
        publisher = MagicMock()
        client._state_publisher = publisher
        client._on_connect(client._client, None, None, 0, None)
        publisher.gather_and_publish.assert_called_once()

    @patch("src.mqtt.client.build_all_discovery_messages", return_value=[])
    def test_on_connect_state_publisher_exception(self, mock_build, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._client = MagicMock()
        publisher = MagicMock()
        publisher.gather_and_publish.side_effect = Exception("publish error")
        client._state_publisher = publisher
        # Should not raise
        client._on_connect(client._client, None, None, 0, None)
        assert client._connected


class TestOnDisconnect:
    """Tests for _on_disconnect callback."""

    def test_on_disconnect_sets_connected_false(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._connected = True
        client._on_disconnect(MagicMock(), None, None, 0, None)
        assert not client._connected

    def test_on_disconnect_nonzero_reason_code(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._connected = True
        client._on_disconnect(MagicMock(), None, None, 1, None)
        assert not client._connected


class TestOnMessage:
    """Tests for _on_message callback paths."""

    def test_on_message_valid_command_with_handler(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        handler = MagicMock()
        client._command_handler = handler
        msg = MagicMock()
        msg.topic = "fiestaboard/schedule_enabled/set"
        msg.payload = b"ON"
        client._on_message(MagicMock(), None, msg)
        handler.handle.assert_called_once_with("schedule_enabled", "ON")

    def test_on_message_valid_command_no_handler(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._command_handler = None
        msg = MagicMock()
        msg.topic = "fiestaboard/schedule_enabled/set"
        msg.payload = b"ON"
        # Should not raise, just log warning
        client._on_message(MagicMock(), None, msg)

    def test_on_message_empty_payload(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        handler = MagicMock()
        client._command_handler = handler
        msg = MagicMock()
        msg.topic = "fiestaboard/schedule_enabled/set"
        msg.payload = b""
        client._on_message(MagicMock(), None, msg)
        handler.handle.assert_called_once_with("schedule_enabled", "")

    def test_on_message_no_payload(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        handler = MagicMock()
        client._command_handler = handler
        msg = MagicMock()
        msg.topic = "fiestaboard/schedule_enabled/set"
        msg.payload = None
        client._on_message(MagicMock(), None, msg)
        handler.handle.assert_called_once_with("schedule_enabled", "")

    def test_on_message_non_matching_topic(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        handler = MagicMock()
        client._command_handler = handler
        msg = MagicMock()
        msg.topic = "other/topic/state"
        msg.payload = b"value"
        client._on_message(MagicMock(), None, msg)
        handler.handle.assert_not_called()

    def test_on_message_handler_exception(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        handler = MagicMock()
        handler.handle.side_effect = Exception("handler error")
        client._command_handler = handler
        msg = MagicMock()
        msg.topic = "fiestaboard/schedule_enabled/set"
        msg.payload = b"ON"
        # Should not raise
        client._on_message(MagicMock(), None, msg)

    def test_on_message_decode_exception(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        msg = MagicMock()
        msg.topic = "fiestaboard/test/set"
        msg.payload = MagicMock()
        msg.payload.decode.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "bad")
        # Should not raise
        client._on_message(MagicMock(), None, msg)


class TestPublishDiscoveryErrors:
    """Tests for _publish_discovery error paths."""

    @patch("src.mqtt.client.build_all_discovery_messages", return_value=[])
    def test_publish_discovery_version_import_error(self, mock_build, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._client = MagicMock()
        with patch.dict("sys.modules", {"src": None}):
            client._publish_discovery()
        mock_build.assert_called_once()
        kwargs = mock_build.call_args[1]
        assert kwargs["sw_version"] == "1.0.0"

    @patch("src.mqtt.client.build_all_discovery_messages", return_value=[])
    def test_publish_discovery_page_service_exception(self, mock_build, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._client = MagicMock()
        with patch("src.mqtt.client.build_all_discovery_messages", return_value=[]) as mb:
            with patch("src.pages.service.get_page_service", side_effect=Exception("no service")):
                client._publish_discovery()
            kwargs = mb.call_args[1]
            assert kwargs["page_names"] == []


class TestPublishStateRawErrors:
    """Tests for publish_state_raw and publish_attributes error paths."""

    def test_publish_state_raw_exception(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._client = MagicMock()
        client._connected = True
        client._client.publish.side_effect = Exception("publish error")
        # Should not raise
        client.publish_state_raw("topic/test", "value")

    def test_publish_attributes_when_connected(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._client = MagicMock()
        client._connected = True
        client.publish_attributes("current_page", '{"page_id": "main"}')
        client._client.publish.assert_called_once()
        args = client._client.publish.call_args[0]
        assert args[0] == "fiestaboard/current_page/attributes"

    def test_publish_attributes_not_connected(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        client._client = MagicMock()
        client._connected = False
        client.publish_attributes("current_page", '{"page_id": "main"}')
        client._client.publish.assert_not_called()


class TestSyncLoop:
    """Tests for _sync_loop error and skip paths."""

    def test_sync_loop_calls_state_publisher(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        publisher = MagicMock()
        client._state_publisher = publisher
        client._running = True
        client._connected = True
        client._sync_interval = 0.01

        def stop_after_one(*args, **kwargs):
            client._running = False

        publisher.gather_and_publish.side_effect = stop_after_one

        with patch("src.mqtt.client.time.sleep"):
            client._sync_loop()
        publisher.gather_and_publish.assert_called_once()

    def test_sync_loop_exception_in_publisher(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        publisher = MagicMock()
        client._state_publisher = publisher
        client._running = True
        client._connected = True
        client._sync_interval = 0.01
        call_count = 0

        def fail_then_stop(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("sync error")
            client._running = False

        publisher.gather_and_publish.side_effect = fail_then_stop

        with patch("src.mqtt.client.time.sleep"):
            client._sync_loop()
        assert call_count == 2

    def test_sync_loop_skips_when_not_connected(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        publisher = MagicMock()
        client._state_publisher = publisher
        client._running = True
        client._connected = False
        client._sync_interval = 0.01
        call_count = 0

        def sleep_and_stop(_seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                client._running = False

        with patch("src.mqtt.client.time.sleep", side_effect=sleep_and_stop):
            client._sync_loop()
        publisher.gather_and_publish.assert_not_called()

    def test_is_connected(self, mqtt_config):
        client = MQTTClient(mqtt_config)
        assert not client.is_connected()
        client._connected = True
        assert client.is_connected()
