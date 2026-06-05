"""Tests for MQTT command handler."""

from unittest.mock import MagicMock, patch

import pytest

from src.mqtt.client import MQTTClient
from src.mqtt.commands import CommandHandler
from src.mqtt.config import MQTTConfig


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


@pytest.fixture
def handler_with_publisher(mock_client):
    """Handler with a mock state publisher for event testing."""
    publisher = MagicMock()
    mock_client._state_publisher = publisher
    start_fn = MagicMock(return_value=True)
    stop_fn = MagicMock(return_value=True)
    h = CommandHandler(
        mock_client,
        start_display_service=start_fn,
        stop_display_service=stop_fn,
    )
    return h, publisher


class TestCommandHandlerScheduleEnabled:
    """Tests for schedule_enabled command."""

    @patch("src.settings.service.get_settings_service")
    def test_handle_schedule_on(self, get_settings, handler):
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("schedule_enabled", "ON")
        settings.set_schedule_enabled.assert_called_once_with(True)

    @patch("src.settings.service.get_settings_service")
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

    @patch("src.settings.service.get_settings_service")
    @patch("src.pages.service.get_page_service")
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

    @patch("src.pages.service.get_page_service")
    def test_handle_active_page_unknown_name_logs(self, get_page, handler):
        page_svc = MagicMock()
        page_svc.list_pages.return_value = []
        get_page.return_value = page_svc
        handler.handle("active_page", "Nonexistent")
        # No exception; handler logs and returns


class TestCommandHandlerTransitionStyle:
    """Tests for transition_style command."""

    @patch("src.board_client.VALID_STRATEGIES", ["column", "random"])
    @patch("src.settings.service.get_settings_service")
    def test_handle_transition_style(self, get_settings, handler):
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("transition_style", "column")
        settings.update_transition_settings.assert_called_once_with(strategy="column")


class TestCommandHandlerRefreshInterval:
    """Tests for refresh_interval command."""

    @patch("src.settings.service.get_settings_service")
    def test_handle_refresh_interval(self, get_settings, handler):
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("refresh_interval", "120")
        settings.set_polling_interval.assert_called_once_with(120)

    @patch("src.settings.service.get_settings_service")
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


class TestCommandHandlerEventPublishing:
    """Tests for event publishing from command handlers."""

    @patch("src.settings.service.get_settings_service")
    @patch("src.pages.service.get_page_service")
    def test_active_page_fires_page_changed_event(self, get_page, get_settings, handler_with_publisher):
        handler, publisher = handler_with_publisher
        page_svc = MagicMock()
        page = MagicMock()
        page.name = "Weather"
        page.id = "page-weather-id"
        page_svc.list_pages.return_value = [page]
        get_page.return_value = page_svc
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("active_page", "Weather")
        publisher.publish_event.assert_called_once()
        args = publisher.publish_event.call_args[0]
        assert args[0] == "page_changed"
        assert args[1] == "page_switched"
        assert args[2]["page_name"] == "Weather"
        assert "timestamp" in args[2]

    @patch("src.settings.service.get_settings_service")
    @patch("src.pages.service.get_page_service")
    def test_active_page_case_insensitive(self, get_page, get_settings, handler):
        """Page matching should be case-insensitive."""
        page_svc = MagicMock()
        page = MagicMock()
        page.name = "Weather Dashboard"
        page.id = "page-weather-id"
        page_svc.list_pages.return_value = [page]
        get_page.return_value = page_svc
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("active_page", "weather dashboard")
        settings.set_active_page_id.assert_called_once_with("page-weather-id")

    @patch("src.api_server.get_service")
    def test_refresh_display_fires_display_updated_event(self, get_service, handler_with_publisher):
        handler, publisher = handler_with_publisher
        get_service.return_value = None
        handler.handle("refresh_display", "")
        publisher.publish_event.assert_called_once()
        args = publisher.publish_event.call_args[0]
        assert args[0] == "display_updated"
        assert args[1] == "page_refreshed"
        assert "timestamp" in args[2]

    @patch("src.api_server.get_service")
    def test_refresh_display_marks_last_update(self, get_service, handler_with_publisher):
        """Refresh display should call mark_display_updated."""
        handler, publisher = handler_with_publisher
        get_service.return_value = None
        handler.handle("refresh_display", "")
        publisher.mark_display_updated.assert_called_once()

    @patch("src.settings.service.get_settings_service")
    @patch("src.api_server._get_board_client")
    def test_blank_board_fires_display_updated_event(self, get_board, get_settings, handler_with_publisher):
        handler, publisher = handler_with_publisher
        board_client = MagicMock()
        get_board.return_value = board_client
        settings = MagicMock()
        settings.should_send_to_board.return_value = True
        get_settings.return_value = settings
        handler.handle("blank_board", "")
        publisher.publish_event.assert_called_once()
        args = publisher.publish_event.call_args[0]
        assert args[0] == "display_updated"
        assert args[1] == "board_blanked"
        assert "timestamp" in args[2]

    @patch("src.settings.service.get_settings_service")
    @patch("src.text_to_board.text_to_board_array")
    @patch("src.api_server.get_service")
    @patch("src.config.Config")
    def test_send_message_fires_display_updated_event(
        self, mock_config, get_service, text_to_board, get_settings, handler_with_publisher
    ):
        handler, publisher = handler_with_publisher
        mock_config.is_silence_mode_active.return_value = False
        service = MagicMock()
        service.vb_client = MagicMock()
        get_service.return_value = service
        text_to_board.return_value = [[0] * 22 for _ in range(6)]
        settings = MagicMock()
        settings.get_transition_settings.return_value = MagicMock(strategy="column", step_interval_ms=100, step_size=1)
        get_settings.return_value = settings
        handler.handle("send_message", "Hello World")
        publisher.publish_event.assert_called_once()
        args = publisher.publish_event.call_args[0]
        assert args[0] == "display_updated"
        assert args[1] == "message_sent"
        assert "timestamp" in args[2]


class TestCommandHandlerRefreshIntervalClamping:
    """Tests for refresh_interval clamping to 30-3600 bounds."""

    @patch("src.settings.service.get_settings_service")
    def test_handle_refresh_interval_below_minimum_clamped(self, get_settings, handler):
        """Values below 30 should be clamped to 30."""
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("refresh_interval", "5")
        settings.set_polling_interval.assert_called_once_with(30)

    @patch("src.settings.service.get_settings_service")
    def test_handle_refresh_interval_above_maximum_clamped(self, get_settings, handler):
        """Values above 3600 should be clamped to 3600."""
        settings = MagicMock()
        get_settings.return_value = settings
        handler.handle("refresh_interval", "7200")
        settings.set_polling_interval.assert_called_once_with(3600)


class TestCommandHandlerPageNavigation:
    """Tests for next_page and previous_page commands."""

    @patch("src.settings.service.get_settings_service")
    @patch("src.pages.service.get_page_service")
    def test_next_page_advances_to_next(self, get_page, get_settings, handler_with_publisher):
        handler, publisher = handler_with_publisher
        page_svc = MagicMock()
        page1 = MagicMock()
        page1.name = "Weather"
        page1.id = "p1"
        page2 = MagicMock()
        page2.name = "Sports"
        page2.id = "p2"
        page3 = MagicMock()
        page3.name = "News"
        page3.id = "p3"
        page_svc.list_pages.return_value = [page1, page2, page3]
        get_page.return_value = page_svc
        settings = MagicMock()
        settings.get_active_page_id.return_value = "p1"
        get_settings.return_value = settings
        handler.handle("next_page", "")
        settings.set_active_page_id.assert_called_once_with("p2")
        publisher.publish_event.assert_called_once()
        args = publisher.publish_event.call_args[0]
        assert args[2]["direction"] == "next"
        assert args[2]["page_name"] == "Sports"

    @patch("src.settings.service.get_settings_service")
    @patch("src.pages.service.get_page_service")
    def test_next_page_wraps_around(self, get_page, get_settings, handler):
        """At the last page, next should wrap to the first."""
        page_svc = MagicMock()
        page1 = MagicMock()
        page1.name = "A"
        page1.id = "p1"
        page2 = MagicMock()
        page2.name = "B"
        page2.id = "p2"
        page_svc.list_pages.return_value = [page1, page2]
        get_page.return_value = page_svc
        settings = MagicMock()
        settings.get_active_page_id.return_value = "p2"
        get_settings.return_value = settings
        handler.handle("next_page", "")
        settings.set_active_page_id.assert_called_once_with("p1")

    @patch("src.settings.service.get_settings_service")
    @patch("src.pages.service.get_page_service")
    def test_previous_page_goes_back(self, get_page, get_settings, handler_with_publisher):
        handler, publisher = handler_with_publisher
        page_svc = MagicMock()
        page1 = MagicMock()
        page1.name = "Weather"
        page1.id = "p1"
        page2 = MagicMock()
        page2.name = "Sports"
        page2.id = "p2"
        page3 = MagicMock()
        page3.name = "News"
        page3.id = "p3"
        page_svc.list_pages.return_value = [page1, page2, page3]
        get_page.return_value = page_svc
        settings = MagicMock()
        settings.get_active_page_id.return_value = "p2"
        get_settings.return_value = settings
        handler.handle("previous_page", "")
        settings.set_active_page_id.assert_called_once_with("p1")
        publisher.publish_event.assert_called_once()
        args = publisher.publish_event.call_args[0]
        assert args[2]["direction"] == "previous"
        assert args[2]["page_name"] == "Weather"

    @patch("src.settings.service.get_settings_service")
    @patch("src.pages.service.get_page_service")
    def test_previous_page_wraps_around(self, get_page, get_settings, handler):
        """At the first page, previous should wrap to the last."""
        page_svc = MagicMock()
        page1 = MagicMock()
        page1.name = "A"
        page1.id = "p1"
        page2 = MagicMock()
        page2.name = "B"
        page2.id = "p2"
        page_svc.list_pages.return_value = [page1, page2]
        get_page.return_value = page_svc
        settings = MagicMock()
        settings.get_active_page_id.return_value = "p1"
        get_settings.return_value = settings
        handler.handle("previous_page", "")
        settings.set_active_page_id.assert_called_once_with("p2")

    @patch("src.pages.service.get_page_service")
    def test_next_page_no_pages(self, get_page, handler):
        """next_page with empty page list should not error."""
        page_svc = MagicMock()
        page_svc.list_pages.return_value = []
        get_page.return_value = page_svc
        handler.handle("next_page", "")
        # Should not raise
