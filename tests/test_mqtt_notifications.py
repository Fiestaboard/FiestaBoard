"""Tests for MQTT notification command and discovery entity."""

import pytest
from unittest.mock import MagicMock, patch

from src.mqtt.config import MQTTConfig
from src.mqtt.client import MQTTClient
from src.mqtt.commands import CommandHandler
from src.mqtt.discovery import ENTITY_DEFINITIONS, build_discovery_payload, build_device_info


@pytest.fixture
def mqtt_config():
    return MQTTConfig(
        enabled=True,
        broker_host="broker.test",
        broker_port=1883,
        instance_id="fiestaboard_1",
        base_topic="fiestaboard",
    )


@pytest.fixture
def mock_client():
    client = MagicMock(spec=MQTTClient)
    client._state_publisher = None
    client.config = MQTTConfig(enabled=True, base_topic="fiestaboard")
    return client


@pytest.fixture
def handler(mock_client):
    start_fn = MagicMock(return_value=True)
    stop_fn = MagicMock(return_value=True)
    return CommandHandler(
        mock_client,
        start_display_service=start_fn,
        stop_display_service=stop_fn,
    )


class TestSendNotificationCommand:
    """Tests for the send_notification MQTT command."""

    @patch("src.notifications.service.get_notification_service")
    def test_handle_send_notification_creates_notification(self, get_notif_svc, handler):
        """send_notification command creates a notification via the service."""
        notif_svc = MagicMock()
        get_notif_svc.return_value = notif_svc
        handler.handle("send_notification", "Hello from HA!")
        notif_svc.create_notification.assert_called_once()
        call_args = notif_svc.create_notification.call_args[0][0]
        assert call_args.message == "Hello from HA!"

    @patch("src.notifications.service.get_notification_service")
    def test_handle_send_notification_empty_payload_ignored(self, get_notif_svc, handler):
        """send_notification with empty payload is ignored."""
        notif_svc = MagicMock()
        get_notif_svc.return_value = notif_svc
        handler.handle("send_notification", "")
        notif_svc.create_notification.assert_not_called()


class TestNotificationDiscoveryEntity:
    """Tests for the send_notification discovery entity."""

    def test_send_notification_entity_exists(self):
        """The send_notification entity is defined in ENTITY_DEFINITIONS."""
        entity_ids = [e.object_id for e in ENTITY_DEFINITIONS]
        assert "send_notification" in entity_ids

    def test_send_notification_entity_is_text(self):
        """The send_notification entity is a text type."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "send_notification")
        assert entity.entity_type == "text"
        assert entity.has_command is True

    def test_send_notification_discovery_payload(self, mqtt_config):
        """The discovery payload for send_notification is well-formed."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "send_notification")
        device_info = build_device_info(mqtt_config)
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["name"] == "Send Notification"
        assert "command_topic" in payload
        assert payload["min"] == 1
        assert payload["max"] == 132


class TestNotificationCountSensor:
    """Tests for the notification_count sensor entity."""

    def test_notification_count_entity_exists(self):
        """The notification_count entity is defined in ENTITY_DEFINITIONS."""
        entity_ids = [e.object_id for e in ENTITY_DEFINITIONS]
        assert "notification_count" in entity_ids

    def test_notification_count_entity_is_sensor(self):
        """The notification_count entity is a sensor type."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "notification_count")
        assert entity.entity_type == "sensor"
