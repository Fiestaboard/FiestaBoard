"""Tests for the per-board pause feature (issue #970).

When a board is paused, FiestaBoard must not push anything to it from
any code path: polling loop, schedule, manual sends, plugin triggers,
MQTT commands, debug sends, welcome message, etc. The board is left
untouched until the user resumes it.

These tests cover three load-bearing paths:

1. The DisplayService polling loop short-circuits when the board is
   paused (the regression that opened the issue: an active page kept
   getting re-sent every tick to a board the user explicitly paused).
2. The new POST /settings/board/{board_id}/pause endpoint round-trips
   the paused flag through SettingsService.
3. The MQTT send_message handler refuses to send when the board is
   paused (the other "user surprised us" path: paused boards must not
   wake up from a Home Assistant automation either).
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.mqtt.client import MQTTClient
from src.mqtt.commands import CommandHandler
from src.mqtt.config import MQTTConfig

# ---------------------------------------------------------------------------
# 1. DisplayService polling loop guard
# ---------------------------------------------------------------------------


@pytest.fixture
def paused_service_factory():
    """Build a DisplayService with mocked services. Caller controls the
    return value of SettingsService.is_paused per test.

    Modelled after tests/test_silence_schedule_polling.py::service_factory
    so the two short-circuit features are validated the same way.
    """

    def _make(is_paused: bool):
        patches = {
            "config": patch("src.main.Config"),
            "settings": patch("src.main.get_settings_service"),
            "page": patch("src.main.get_page_service"),
            "schedule": patch("src.main.get_schedule_service"),
            "collection": patch("src.main.get_collection_service"),
            "trigger": patch("src.main.get_trigger_service"),
        }
        mocks = {name: p.start() for name, p in patches.items()}

        mocks["config"].is_silence_mode_active.return_value = False

        settings_service = Mock()
        settings_service.is_paused.return_value = is_paused
        settings_service.is_schedule_enabled.return_value = False
        settings_service.get_active_page_id.return_value = "page-1"
        settings_service.get_polling_interval.return_value = 60
        board_settings = Mock()
        board_settings.boards = [{"id": "board-1", "device_type": "flagship"}]
        settings_service.get_board_settings.return_value = board_settings
        transition = Mock()
        transition.strategy = None
        transition.step_interval_ms = 0
        transition.step_size = 1
        settings_service.get_transition_settings.return_value = transition
        mocks["settings"].return_value = settings_service

        page_service = Mock()
        mock_page = Mock()
        mock_page.id = "page-1"
        mock_page.device_type = "flagship"
        mock_page.transition_strategy = None
        mock_page.transition_interval_ms = None
        mock_page.transition_step_size = None
        page_service.get_page.return_value = mock_page
        preview = Mock()
        preview.available = True
        preview.formatted = "Hello World"
        page_service.preview_page.return_value = preview
        mocks["page"].return_value = page_service

        from src.main import DisplayService

        svc = DisplayService()
        svc.vb_client = Mock()
        svc.vb_client.send_characters.return_value = (True, True)
        svc.vb_client.render.return_value = (True, True)

        return svc, mocks, page_service, patches

    started = []

    def factory(is_paused: bool):
        svc, mocks, page_service, patches = _make(is_paused)
        started.append(patches)
        return svc, mocks, page_service

    yield factory

    for patches in started:
        for p in patches.values():
            p.stop()


class TestPolicyPolling:
    """The regression from issue #970: a paused board kept receiving the
    active page on every polling tick."""

    def test_paused_board_skips_send(self, paused_service_factory):
        """Polling loop must not render or send when the board is paused."""
        svc, _mocks, page_service = paused_service_factory(is_paused=True)

        result = svc.check_and_send_active_page()

        assert result is False
        page_service.preview_page.assert_not_called()
        svc.vb_client.send_characters.assert_not_called()

    def test_unpaused_board_still_sends(self, paused_service_factory):
        """Sanity check — when not paused the normal send path still runs."""
        svc, _mocks, page_service = paused_service_factory(is_paused=False)

        with patch.object(svc, "_check_trigger_override", return_value=None):
            svc.check_and_send_active_page()

        page_service.preview_page.assert_called()
        svc.vb_client.render.assert_called_once()


# ---------------------------------------------------------------------------
# 2. POST /settings/board/{board_id}/pause endpoint round-trip
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_paused_settings_service():
    """Mock SettingsService with a single board and an in-memory paused
    flag so set_paused/is_paused round-trip realistically."""
    with patch("src.api_server.get_settings_service") as mock_get:
        ss = Mock()
        state = {"paused": False}

        board_settings = Mock()
        board_settings.boards = [{"id": "board-1", "device_type": "flagship", "paused": False}]
        board_settings.to_dict.return_value = {
            "board_type": "black",
            "boards": board_settings.boards,
            "devices": ["flagship"],
        }
        ss.get_board_settings.return_value = board_settings

        def _is_paused(board_id=None):
            return state["paused"]

        def _set_paused(paused, board_id=None):
            state["paused"] = bool(paused)
            board_settings.boards[0]["paused"] = bool(paused)
            return bool(paused)

        ss.is_paused.side_effect = _is_paused
        ss.set_paused.side_effect = _set_paused

        mock_get.return_value = ss
        yield ss


class TestPauseEndpoint:
    """POST /settings/board/{board_id}/pause must round-trip the flag."""

    def test_pause_round_trips_through_settings_service(self, client, mock_paused_settings_service):
        resp = client.post("/settings/board/board-1/pause", json={"paused": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["board_id"] == "board-1"
        assert data["paused"] is True
        mock_paused_settings_service.set_paused.assert_called_with(True, board_id="board-1")

        # Now resume it.
        resp2 = client.post("/settings/board/board-1/pause", json={"paused": False})
        assert resp2.status_code == 200
        assert resp2.json()["paused"] is False

    def test_pause_missing_body_field_400s(self, client, mock_paused_settings_service):
        resp = client.post("/settings/board/board-1/pause", json={})
        assert resp.status_code == 400

    def test_pause_non_bool_body_400s(self, client, mock_paused_settings_service):
        resp = client.post("/settings/board/board-1/pause", json={"paused": "yes"})
        assert resp.status_code == 400

    def test_pause_unknown_board_404s(self, client, mock_paused_settings_service):
        resp = client.post("/settings/board/no-such-board/pause", json={"paused": True})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. MQTT send_message + blank_board paused guard
# ---------------------------------------------------------------------------


@pytest.fixture
def mqtt_handler():
    mock_client = MagicMock(spec=MQTTClient)
    mock_client._state_publisher = None
    mock_client.config = MQTTConfig(enabled=True, base_topic="fiestaboard")
    return CommandHandler(
        mock_client,
        start_display_service=MagicMock(return_value=True),
        stop_display_service=MagicMock(return_value=True),
    )


class TestMQTTPausedGuard:
    """Paused boards must not get woken up by MQTT commands either."""

    @patch("src.settings.service.get_settings_service")
    @patch("src.api_server.get_service")
    def test_send_message_blocked_when_paused(self, get_service, get_settings, mqtt_handler):
        service = MagicMock()
        service.vb_client = MagicMock()
        get_service.return_value = service
        settings = MagicMock()
        settings.is_paused.return_value = True
        get_settings.return_value = settings

        mqtt_handler.handle("send_message", "Hello World")

        # The board client must not be touched.
        service.vb_client.send_characters.assert_not_called()

    @patch("src.settings.service.get_settings_service")
    @patch("src.api_server._get_board_client")
    def test_blank_board_blocked_when_paused(self, get_board, get_settings, mqtt_handler):
        board_client = MagicMock()
        get_board.return_value = board_client
        settings = MagicMock()
        settings.should_send_to_board.return_value = True
        settings.is_paused.return_value = True
        get_settings.return_value = settings

        mqtt_handler.handle("blank_board", "")

        board_client.send_characters.assert_not_called()
