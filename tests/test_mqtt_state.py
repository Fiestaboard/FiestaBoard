"""Tests for MQTT state publisher."""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.mqtt.config import MQTTConfig
from src.mqtt.client import MQTTClient
from src.mqtt.state import StatePublisher


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
    client.publish_state = MagicMock()
    client.publish_attributes = MagicMock()
    client.config = MQTTConfig(enabled=True, base_topic="fiestaboard")
    return client


class TestStatePublisherGather:
    """Tests for StatePublisher.gather_and_publish."""

    @patch("src.config_manager.ConfigManager")
    @patch("src.api_server._get_board_client")
    @patch("src.api_server._service_start_time", 1000000.0)
    @patch("src.pages.service.get_page_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_gather_publishes_schedule_enabled(
        self, mock_config, get_settings, get_page, mock_board, mock_cm, mock_client
    ):
        mock_config.is_silence_mode_active.return_value = False
        settings = MagicMock()
        settings.is_schedule_enabled.return_value = True
        settings.get_active_page_id.return_value = "page-1"
        settings.get_transition_settings.return_value = MagicMock(strategy="column")
        settings.get_polling_interval.return_value = 300
        get_settings.return_value = settings
        page_svc = MagicMock()
        page_svc.get_page.return_value = MagicMock(name="Weather")
        page_svc.list_pages.return_value = []
        get_page.return_value = page_svc
        mock_board.return_value = None
        mock_cm.return_value._config = {"plugins": {}}
        pub = StatePublisher(
            mock_client,
            get_display_running=lambda: True,
            get_current_message=lambda: "Hello",
        )
        pub.gather_and_publish()
        calls = mock_client.publish_state.call_args_list
        topics = [c[0][0] for c in calls]
        assert "schedule_enabled" in topics
        idx = topics.index("schedule_enabled")
        assert calls[idx][0][1] == "ON"

    @patch("src.config_manager.ConfigManager")
    @patch("src.api_server._get_board_client")
    @patch("src.api_server._service_start_time", 1000000.0)
    @patch("src.pages.service.get_page_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_gather_dedup_does_not_republish_unchanged(
        self, mock_config, get_settings, get_page, mock_board, mock_cm, mock_client
    ):
        mock_config.is_silence_mode_active.return_value = False
        settings = MagicMock()
        settings.is_schedule_enabled.return_value = False
        settings.get_active_page_id.return_value = None
        settings.get_transition_settings.return_value = MagicMock(strategy="")
        settings.get_polling_interval.return_value = 60
        get_settings.return_value = settings
        page_svc = MagicMock()
        page_svc.get_page.return_value = None
        page_svc.list_pages.return_value = []
        get_page.return_value = page_svc
        mock_board.return_value = None
        mock_cm.return_value._config = {"plugins": {}}
        pub = StatePublisher(
            mock_client,
            get_display_running=lambda: False,
            get_current_message=lambda: "—",
        )
        pub.gather_and_publish()
        first_state_count = mock_client.publish_state.call_count
        first_attrs_count = mock_client.publish_attributes.call_count
        pub.gather_and_publish()
        second_state_count = mock_client.publish_state.call_count
        second_attrs_count = mock_client.publish_attributes.call_count
        assert second_state_count == first_state_count
        assert second_attrs_count == first_attrs_count

    @patch("src.pages.service.get_page_service")
    @patch("src.settings.service.get_settings_service")
    def test_gather_handles_exception(self, get_settings, get_page, mock_client):
        get_settings.side_effect = RuntimeError("service unavailable")
        pub = StatePublisher(mock_client)
        pub.gather_and_publish()
        mock_client.publish_state.assert_not_called()


class TestStatePublisherDiagnostics:
    """Tests for diagnostic state values (uptime, board_api_mode, active_plugins)."""

    @patch("src.config_manager.ConfigManager")
    @patch("src.api_server._get_board_client")
    @patch("src.api_server._service_start_time", 1000000.0)
    @patch("src.pages.service.get_page_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_gather_publishes_uptime(
        self, mock_config, get_settings, get_page, mock_board, mock_cm, mock_client
    ):
        mock_config.is_silence_mode_active.return_value = False
        settings = MagicMock()
        settings.is_schedule_enabled.return_value = False
        settings.get_active_page_id.return_value = None
        settings.get_transition_settings.return_value = MagicMock(strategy="")
        settings.get_polling_interval.return_value = 60
        get_settings.return_value = settings
        page_svc = MagicMock()
        page_svc.get_page.return_value = None
        page_svc.list_pages.return_value = []
        get_page.return_value = page_svc
        mock_board.return_value = None
        mock_cm.return_value._config = {"plugins": {}}
        pub = StatePublisher(mock_client)
        pub.gather_and_publish()
        calls = mock_client.publish_state.call_args_list
        topics = [c[0][0] for c in calls]
        assert "uptime" in topics

    @patch("src.config_manager.ConfigManager")
    @patch("src.api_server._get_board_client")
    @patch("src.api_server._service_start_time", 1000000.0)
    @patch("src.pages.service.get_page_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_gather_publishes_board_api_mode(
        self, mock_config, get_settings, get_page, mock_board, mock_cm, mock_client
    ):
        mock_config.is_silence_mode_active.return_value = False
        settings = MagicMock()
        settings.is_schedule_enabled.return_value = False
        settings.get_active_page_id.return_value = None
        settings.get_transition_settings.return_value = MagicMock(strategy="")
        settings.get_polling_interval.return_value = 60
        get_settings.return_value = settings
        page_svc = MagicMock()
        page_svc.get_page.return_value = None
        page_svc.list_pages.return_value = []
        get_page.return_value = page_svc
        mock_board_client = MagicMock()
        mock_board_client.use_cloud = False
        mock_board.return_value = mock_board_client
        mock_cm.return_value._config = {"plugins": {}}
        pub = StatePublisher(mock_client)
        pub.gather_and_publish()
        calls = mock_client.publish_state.call_args_list
        topics = [c[0][0] for c in calls]
        assert "board_api_mode" in topics
        idx = topics.index("board_api_mode")
        assert calls[idx][0][1] == "Local API"

    @patch("src.config_manager.ConfigManager")
    @patch("src.api_server._get_board_client")
    @patch("src.api_server._service_start_time", 1000000.0)
    @patch("src.pages.service.get_page_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_gather_publishes_active_plugins(
        self, mock_config, get_settings, get_page, mock_board, mock_cm, mock_client
    ):
        mock_config.is_silence_mode_active.return_value = False
        settings = MagicMock()
        settings.is_schedule_enabled.return_value = False
        settings.get_active_page_id.return_value = None
        settings.get_transition_settings.return_value = MagicMock(strategy="")
        settings.get_polling_interval.return_value = 60
        get_settings.return_value = settings
        page_svc = MagicMock()
        page_svc.get_page.return_value = None
        page_svc.list_pages.return_value = []
        get_page.return_value = page_svc
        mock_board.return_value = None
        mock_cm.return_value._config = {
            "plugins": {
                "weather": {"enabled": True},
                "stocks": {"enabled": True},
                "date_time": {"enabled": False},
            }
        }
        pub = StatePublisher(mock_client)
        pub.gather_and_publish()
        calls = mock_client.publish_state.call_args_list
        topics = [c[0][0] for c in calls]
        assert "active_plugins" in topics
        idx = topics.index("active_plugins")
        assert calls[idx][0][1] == "2"


class TestStatePublisherAttributes:
    """Tests for JSON attributes publishing."""

    @patch("src.pages.service.get_page_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_gather_publishes_current_page_attributes(
        self, mock_config, get_settings, get_page, mock_client
    ):
        mock_config.is_silence_mode_active.return_value = False
        settings = MagicMock()
        settings.is_schedule_enabled.return_value = False
        settings.get_active_page_id.return_value = "page-42"
        settings.get_transition_settings.return_value = MagicMock(strategy="")
        settings.get_polling_interval.return_value = 60
        get_settings.return_value = settings
        page = MagicMock()
        page.id = "page-42"
        page.name = "Weather"
        page_svc = MagicMock()
        page_svc.get_page.return_value = page
        page_svc.list_pages.return_value = [page]
        get_page.return_value = page_svc
        pub = StatePublisher(mock_client)
        pub.gather_and_publish()
        # Verify publish_attributes was called for current_page
        mock_client.publish_attributes.assert_called()
        attrs_calls = mock_client.publish_attributes.call_args_list
        attrs_topics = [c[0][0] for c in attrs_calls]
        assert "current_page" in attrs_topics
        idx = attrs_topics.index("current_page")
        attrs_json = attrs_calls[idx][0][1]
        attrs = json.loads(attrs_json)
        assert attrs["page_id"] == "page-42"
        assert attrs["page_index"] == 0


class TestStatePublisherEvents:
    """Tests for event publishing."""

    def test_publish_event_sends_json(self, mock_client):
        """publish_event should publish JSON with event_type key."""
        pub = StatePublisher(mock_client)
        pub.publish_event("display_updated", "message_sent")
        mock_client.publish_state.assert_called_once()
        args = mock_client.publish_state.call_args[0]
        assert args[0] == "display_updated"
        event_data = json.loads(args[1])
        assert event_data["event_type"] == "message_sent"

    def test_publish_event_with_attributes(self, mock_client):
        """publish_event should include extra attributes in the JSON payload."""
        pub = StatePublisher(mock_client)
        pub.publish_event("page_changed", "page_switched", {"page_name": "Weather"})
        args = mock_client.publish_state.call_args[0]
        event_data = json.loads(args[1])
        assert event_data["event_type"] == "page_switched"
        assert event_data["page_name"] == "Weather"
