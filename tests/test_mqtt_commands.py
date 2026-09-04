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


class TestCommandHandlerPerBoardRouting:
    """Issue #1244: JSON payloads may name a target board (id or name)."""

    @staticmethod
    def _settings_with_boards():
        settings = MagicMock()
        board_settings = MagicMock()
        board_settings.boards = [
            {"id": "b1", "name": "Lobby", "device_type": "flagship", "notes_wide": 1, "notes_tall": 1},
            {"id": "b2", "name": "Kitchen", "device_type": "note", "notes_wide": 1, "notes_tall": 1},
        ]
        settings.get_board_settings.return_value = board_settings
        settings.get_primary_board_id.return_value = "b1"
        settings.should_send_to_board.return_value = True
        settings.is_paused.return_value = False
        settings.get_transition_settings.return_value = MagicMock(strategy="column", step_interval_ms=100, step_size=1)
        return settings

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_send_message_routes_to_board_by_name(self, mock_config, get_settings, get_service, handler):
        mock_config.is_silence_mode_active.return_value = False
        get_settings.return_value = self._settings_with_boards()
        service = MagicMock()
        b2_client = MagicMock()
        b2_client.send_characters.return_value = (True, True)
        service.get_board_client.return_value = b2_client
        get_service.return_value = service

        handler.handle("send_message", '{"message": "HELLO", "board": "Kitchen"}')

        service.get_board_client.assert_called_once_with("b2")
        b2_client.send_characters.assert_called_once()
        service.vb_client.send_characters.assert_not_called()
        # Grid sized to the note board (3x15), not the flagship default
        board_array = b2_client.send_characters.call_args[0][0]
        assert len(board_array) == 3
        assert len(board_array[0]) == 15

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_send_message_unknown_board_skips_send(self, mock_config, get_settings, get_service, handler):
        mock_config.is_silence_mode_active.return_value = False
        get_settings.return_value = self._settings_with_boards()
        service = MagicMock()
        get_service.return_value = service

        handler.handle("send_message", '{"message": "HELLO", "board_id": "nope"}')

        service.get_board_client.assert_not_called()
        service.vb_client.send_characters.assert_not_called()

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_send_message_plain_payload_uses_primary_client(self, mock_config, get_settings, get_service, handler):
        """Back-compat: a plain-text payload still goes to service.vb_client."""
        mock_config.is_silence_mode_active.return_value = False
        get_settings.return_value = self._settings_with_boards()
        service = MagicMock()
        get_service.return_value = service

        handler.handle("send_message", "Hello World")

        service.vb_client.send_characters.assert_called_once()
        service.get_board_client.assert_not_called()

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    def test_blank_board_routes_and_sizes_to_target_board(self, get_settings, get_service, handler):
        get_settings.return_value = self._settings_with_boards()
        service = MagicMock()
        b2_client = MagicMock()
        service.get_board_client.return_value = b2_client
        get_service.return_value = service

        handler.handle("blank_board", '{"board_id": "b2"}')

        service.get_board_client.assert_called_once_with("b2")
        board_array = b2_client.send_characters.call_args[0][0]
        assert len(board_array) == 3
        assert len(board_array[0]) == 15
        assert all(code == 0 for row in board_array for code in row)

    @patch("src.api_server._get_board_client")
    @patch("src.settings.service.get_settings_service")
    def test_blank_board_default_sizes_to_primary_board(self, get_settings, get_board, handler):
        """Without a board ref the blank grid uses the primary board's dims."""
        settings = self._settings_with_boards()
        settings.get_board_settings.return_value.boards = [
            {"id": "b1", "name": "Solo", "device_type": "note", "notes_wide": 1, "notes_tall": 1},
        ]
        get_settings.return_value = settings
        board_client = MagicMock()
        get_board.return_value = board_client

        handler.handle("blank_board", "")

        board_array = board_client.send_characters.call_args[0][0]
        assert len(board_array) == 3
        assert len(board_array[0]) == 15

    @patch("src.settings.service.get_settings_service")
    @patch("src.api_server.get_service")
    def test_refresh_display_with_board_id_drives_single_board(self, get_service, get_settings, handler):
        get_settings.return_value = self._settings_with_boards()
        service = MagicMock()
        rt = MagicMock()
        service.get_runtime.return_value = rt
        get_service.return_value = service

        handler.handle("refresh_display", '{"board_id": "b2"}')

        service.get_runtime.assert_called_once_with("b2")
        service.check_and_send_for_board.assert_called_once()
        args, kwargs = service.check_and_send_for_board.call_args
        assert args[0] == "b2"
        assert args[1] is rt
        assert kwargs["is_primary"] is False
        assert kwargs["board"]["id"] == "b2"
        service.check_and_send_active_page.assert_not_called()

    @patch("src.settings.service.get_settings_service")
    @patch("src.api_server.get_service")
    def test_refresh_display_plain_payload_refreshes_all(self, get_service, get_settings, handler):
        """Back-compat: no board ref keeps the legacy all-boards refresh."""
        get_settings.return_value = self._settings_with_boards()
        service = MagicMock()
        get_service.return_value = service

        handler.handle("refresh_display", "PRESS")

        service.check_and_send_active_page.assert_called_once()
        service.check_and_send_for_board.assert_not_called()

    @patch("src.settings.service.get_settings_service")
    @patch("src.pages.service.get_page_service")
    def test_active_page_json_targets_board(self, get_page, get_settings, handler):
        page_svc = MagicMock()
        page = MagicMock()
        page.name = "Weather"
        page.id = "page-weather-id"
        page_svc.list_pages.return_value = [page]
        get_page.return_value = page_svc
        settings = self._settings_with_boards()
        get_settings.return_value = settings

        handler.handle("active_page", '{"page": "Weather", "board": "Kitchen"}')

        settings.set_active_page_id.assert_called_once_with("page-weather-id", board_id="b2")

    @patch("src.settings.service.get_settings_service")
    @patch("src.pages.service.get_page_service")
    def test_active_page_plain_payload_unchanged(self, get_page, get_settings, handler):
        """Back-compat: a plain page-name payload keeps the single-arg setter call."""
        page_svc = MagicMock()
        page = MagicMock()
        page.name = "Weather"
        page.id = "page-weather-id"
        page_svc.list_pages.return_value = [page]
        get_page.return_value = page_svc
        settings = self._settings_with_boards()
        get_settings.return_value = settings

        handler.handle("active_page", "Weather")

        settings.set_active_page_id.assert_called_once_with("page-weather-id")


def _row_text(row):
    """Decode a board row of character codes back to letters/spaces."""
    return "".join(chr(ord("A") + code - 1) if 1 <= code <= 26 else " " for code in row).rstrip()


class TestCommandHandlerSendMessageWrapping:
    """Issue #1793: send_message must use the target board's real geometry
    and word-wrap long text instead of running off the first row."""

    @staticmethod
    def _settings_with_note_primary():
        settings = MagicMock()
        board_settings = MagicMock()
        board_settings.boards = [
            {"id": "b1", "name": "Desk", "device_type": "note", "notes_wide": 1, "notes_tall": 1},
        ]
        settings.get_board_settings.return_value = board_settings
        settings.get_primary_board_id.return_value = "b1"
        settings.should_send_to_board.return_value = True
        settings.is_paused.return_value = False
        settings.get_transition_settings.return_value = MagicMock(strategy="column", step_interval_ms=100, step_size=1)
        return settings

    def _send(self, handler, get_settings, get_service, mock_config, payload):
        mock_config.is_silence_mode_active.return_value = False
        get_settings.return_value = self._settings_with_note_primary()
        service = MagicMock()
        get_service.return_value = service
        handler.handle("send_message", payload)
        service.vb_client.send_characters.assert_called_once()
        return service.vb_client.send_characters.call_args[0][0]

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_plain_payload_sized_to_primary_note_board(self, mock_config, get_settings, get_service, handler):
        """A plain-string payload gets a 3x15 grid on a Note, not flagship 6x22."""
        board_array = self._send(handler, get_settings, get_service, mock_config, "HELLO")
        assert len(board_array) == 3
        assert len(board_array[0]) == 15

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_long_message_wraps_at_word_boundaries(self, mock_config, get_settings, get_service, handler):
        board_array = self._send(handler, get_settings, get_service, mock_config, "TACO TUESDAY PARTY TIME")
        assert _row_text(board_array[0]) == "TACO TUESDAY"
        assert _row_text(board_array[1]) == "PARTY TIME"

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_explicit_newline_breaks_line(self, mock_config, get_settings, get_service, handler):
        board_array = self._send(handler, get_settings, get_service, mock_config, "HI\nTHERE")
        assert _row_text(board_array[0]) == "HI"
        assert _row_text(board_array[1]) == "THERE"

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_literal_backslash_n_breaks_line(self, mock_config, get_settings, get_service, handler):
        """The two-character sequence backslash-n acts as a line break so
        single-line clients (HA text entities) can request one."""
        board_array = self._send(handler, get_settings, get_service, mock_config, "HI\\nTHERE")
        assert _row_text(board_array[0]) == "HI"
        assert _row_text(board_array[1]) == "THERE"

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_text_beyond_rows_truncates_predictably(self, mock_config, get_settings, get_service, handler):
        board_array = self._send(
            handler, get_settings, get_service, mock_config, "AAAA BBBB CCCC DDDD EEEE FFFF GGGG HHHH IIII JJJJ"
        )
        assert len(board_array) == 3
        assert _row_text(board_array[0]) == "AAAA BBBB CCCC"
        assert _row_text(board_array[1]) == "DDDD EEEE FFFF"
        assert _row_text(board_array[2]) == "GGGG HHHH IIII"

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_json_payload_to_named_board_also_wraps(self, mock_config, get_settings, get_service, handler):
        """The board-targeted JSON path wraps too, at that board's width."""
        mock_config.is_silence_mode_active.return_value = False
        get_settings.return_value = self._settings_with_note_primary()
        service = MagicMock()
        b1_client = MagicMock()
        service.get_board_client.return_value = b1_client
        get_service.return_value = service
        handler.handle("send_message", '{"message": "TACO TUESDAY PARTY TIME", "board": "Desk"}')
        board_array = b1_client.send_characters.call_args[0][0]
        assert _row_text(board_array[0]) == "TACO TUESDAY"
        assert _row_text(board_array[1]) == "PARTY TIME"

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_colour_marker_costs_one_tile_when_wrapping(self, mock_config, get_settings, get_service, handler):
        """Wrapping counts flaps: "{red} TACO TUESDAY" is 14 tiles and fits
        one 15-wide Note row even though it is 18 characters."""
        board_array = self._send(handler, get_settings, get_service, mock_config, "{red} TACO TUESDAY")
        assert board_array[0][0] == 63  # red tile
        assert _row_text(board_array[0]) == "  TACO TUESDAY"
        assert _row_text(board_array[1]) == ""

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_escaped_backslash_n_stays_literal(self, mock_config, get_settings, get_service, handler):
        """``\\\\n`` is the escape hatch for text that really contains a
        backslash before an N (issue #1793 review)."""
        board_array = self._send(handler, get_settings, get_service, mock_config, "C:\\\\new")
        # One row: "C:" + an unmappable backslash (space) + "NEW" — the N survives.
        assert _row_text(board_array[0]) == "C  NEW"
        assert _row_text(board_array[1]) == ""

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_json_payload_does_not_unescape_backslash_n(self, mock_config, get_settings, get_service, handler):
        """JSON payloads can already carry a real newline, so the escape
        substitution is confined to the plain-string (HA text entity) path."""
        mock_config.is_silence_mode_active.return_value = False
        get_settings.return_value = self._settings_with_note_primary()
        service = MagicMock()
        b1_client = MagicMock()
        service.get_board_client.return_value = b1_client
        get_service.return_value = service
        # Raw MQTT payload: {"message": "HI\\nTHERE", "board": "Desk"}
        handler.handle("send_message", '{"message": "HI\\\\nTHERE", "board": "Desk"}')
        board_array = b1_client.send_characters.call_args[0][0]
        assert _row_text(board_array[0]) == "HI NTHERE"
        assert _row_text(board_array[1]) == ""

    @patch("src.api_server.get_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_long_word_hard_breaks_instead_of_vanishing(self, mock_config, get_settings, get_service, handler):
        board_array = self._send(handler, get_settings, get_service, mock_config, "SUPERCALIFRAGILISTIC")
        assert _row_text(board_array[0]) == "SUPERCALIFRAGIL"
        assert _row_text(board_array[1]) == "ISTIC"


class TestResolveBoardByName:
    """``_resolve_board`` matches a board ref by id first, then by display name.

    Board names became user-editable in Settings → Boards (issue #1792), so a
    rename silently breaks any automation that targets a board by name. Nothing
    can migrate those payloads for us, so resolving by name warns.
    """

    @staticmethod
    def _settings(boards):
        settings = MagicMock()
        settings.get_board_settings.return_value = MagicMock(boards=boards)
        return settings

    def test_name_match_still_resolves(self):
        boards = [{"id": "b1", "name": "Kitchen"}, {"id": "b2", "name": "Office"}]
        with patch("src.settings.service.get_settings_service", return_value=self._settings(boards)):
            assert CommandHandler._resolve_board("Office")[0] == "b2"

    def test_name_match_warns_that_a_rename_will_break_it(self, caplog):
        boards = [{"id": "b1", "name": "Kitchen"}]
        with patch("src.settings.service.get_settings_service", return_value=self._settings(boards)):
            with caplog.at_level("WARNING"):
                CommandHandler._resolve_board("Kitchen")
        messages = [r.getMessage() for r in caplog.records]
        assert any("renaming this board will break it" in m for m in messages), messages
        # The warning must name the stable id the user should switch to.
        assert any("'b1'" in m for m in messages), messages

    def test_id_match_does_not_warn(self, caplog):
        boards = [{"id": "b1", "name": "Kitchen"}]
        with patch("src.settings.service.get_settings_service", return_value=self._settings(boards)):
            with caplog.at_level("WARNING"):
                assert CommandHandler._resolve_board("b1")[0] == "b1"
        assert caplog.records == []
