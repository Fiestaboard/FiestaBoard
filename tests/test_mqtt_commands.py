"""Tests for MQTT command handler."""

import pytest
from unittest.mock import MagicMock, patch

from src.mqtt.config import MQTTConfig
from src.mqtt.client import MQTTClient
from src.mqtt.commands import CommandHandler


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


class TestCommandHandlerScheduleEnabled:
    """Tests for schedule_enabled command."""

    @patch("src.mqtt.commands.get_settings_service")
    def test_handle_schedule_on(self, get_settings, handler):
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("schedule_enabled", "ON")
        settings.set_schedule_enabled.assert_called_once_with(True)

    @patch("src.mqtt.commands.get_settings_service")
    def test_handle_schedule_off(self, get_settings, handler):
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("schedule_enabled", "OFF")
        settings.set_schedule_enabled.assert_called_once_with(False)


class TestCommandHandlerDisplayService:
    """Tests for display_service command."""

    def test_handle_display_on_calls_start(self, handler):
        handler.handle("display_service", "ON")
        handler._start_display_service.assert_called_once()

    def test_handle_display_off_calls_stop(self, handler):
        handler.handle("display_service", "OFF")
        handler._stop_display_service.assert_called_once()


class TestCommandHandlerActivePage:
    """Tests for active_page command."""

    @patch("src.mqtt.commands.get_settings_service")
    @patch("src.mqtt.commands.get_page_service")
    def test_handle_active_page_by_name(self, get_page, get_settings, handler):
        page_svc = MagicMock()
        page = MagicMock()
        page.name = "Weather"
        page.id = "page-weather-id"
        page_svc.list_pages.return_value = [page]
        get_page.return_value = page_svc
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("active_page", "Weather")
        settings.set_active_page_id.assert_called_once_with("page-weather-id")

    @patch("src.mqtt.commands.get_page_service")
    def test_handle_active_page_unknown_name_logs(self, get_page, handler):
        page_svc = MagicMock()
        page_svc.list_pages.return_value = []
        get_page.return_value = page_svc
        handler.handle("active_page", "Nonexistent")
        # No exception; handler logs and returns


class TestCommandHandlerTransitionStyle:
    """Tests for transition_style command."""

    @patch("src.mqtt.commands.VALID_STRATEGIES", ["column", "random"])
    @patch("src.mqtt.commands.get_settings_service")
    def test_handle_transition_style(self, get_settings, handler):
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("transition_style", "column")
        settings.update_transition_settings.assert_called_once_with(strategy="column")


class TestCommandHandlerRefreshInterval:
    """Tests for refresh_interval command."""

    @patch("src.mqtt.commands.get_settings_service")
    def test_handle_refresh_interval(self, get_settings, handler):
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("refresh_interval", "120")
        settings.set_polling_interval.assert_called_once_with(120)

    @patch("src.mqtt.commands.get_settings_service")
    def test_handle_refresh_interval_invalid_ignored(self, get_settings, handler):
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("refresh_interval", "not-a-number")
        settings.set_polling_interval.assert_not_called()


class TestCommandHandlerUnknown:
    """Tests for unknown object_id."""

    def test_unknown_object_id_no_exception(self, handler):
        handler.handle("unknown_entity", "payload")
        # Should not raise
