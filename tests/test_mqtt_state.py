"""Tests for MQTT state publisher."""

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
    client.config = MQTTConfig(enabled=True, base_topic="fiestaboard")
    return client


class TestStatePublisherGather:
    """Tests for StatePublisher.gather_and_publish."""

    @patch("src.pages.service.get_page_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_gather_publishes_schedule_enabled(
        self, mock_config, get_settings, get_page, mock_client
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

    @patch("src.pages.service.get_page_service")
    @patch("src.settings.service.get_settings_service")
    @patch("src.config.Config")
    def test_gather_dedup_does_not_republish_unchanged(
        self, mock_config, get_settings, get_page, mock_client
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
        pub = StatePublisher(
            mock_client,
            get_display_running=lambda: False,
            get_current_message=lambda: "—",
        )
        pub.gather_and_publish()
        first_count = mock_client.publish_state.call_count
        pub.gather_and_publish()
        second_count = mock_client.publish_state.call_count
        assert second_count == first_count

    @patch("src.pages.service.get_page_service")
    @patch("src.settings.service.get_settings_service")
    def test_gather_handles_exception(self, get_settings, get_page, mock_client):
        get_settings.side_effect = RuntimeError("service unavailable")
        pub = StatePublisher(mock_client)
        pub.gather_and_publish()
        mock_client.publish_state.assert_not_called()
