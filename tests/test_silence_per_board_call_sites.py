"""Every send guard must resolve silence for the board it is about to touch.

Issue #1788 made the silence schedule per board, but the manual-send guards
kept calling ``Config.is_silence_mode_active()`` with no board.  Scenario the
review caught: install-wide silence disabled, the bedroom Note overridden to
22:00-07:00 — at 2am a manual send from the web UI or Home Assistant went
straight through to the bedroom board.

Each test pins one guard.  ``is_silence_mode_active`` is replaced by a
board-aware stub so a guard that still passes ``None`` sees "not silent" and
lets the send through, which is exactly the production bug.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.config import Config
from src.mqtt.client import MQTTClient
from src.mqtt.commands import CommandHandler
from src.mqtt.config import MQTTConfig
from src.mqtt.state import StatePublisher

SILENCED_BOARD = "bedroom-note"
LOUD_BOARD = "kitchen-flagship"

BOARDS = [
    {"id": SILENCED_BOARD, "name": "Bedroom", "device_type": "note", "enabled": True},
    {"id": LOUD_BOARD, "name": "Kitchen", "device_type": "flagship", "enabled": True},
]


def _board_aware_silence(silenced: str = SILENCED_BOARD):
    """Patch ``Config.is_silence_mode_active`` so only ``silenced`` is quiet.

    The install-wide layer (``board_id=None``) is explicitly NOT silent, which
    is what makes a guard that forgets to pass a board fail this test.
    """
    return patch.object(
        Config,
        "is_silence_mode_active",
        classmethod(lambda cls, board_id=None: board_id == silenced),
    )


def _settings(primary: str = SILENCED_BOARD):
    settings = MagicMock()
    settings.get_board_settings.return_value = MagicMock(boards=BOARDS)
    settings.get_primary_board_id.return_value = primary
    settings.is_paused.return_value = False
    settings.should_send_to_board.return_value = True
    settings.get_transition_settings.return_value = MagicMock(strategy="column", step_interval_ms=100, step_size=1)
    settings.get_active_page_id.return_value = "page-1"
    settings.is_schedule_enabled.return_value = False
    settings.get_polling_interval.return_value = 300
    settings.get_output_settings.return_value = MagicMock(target="both")
    return settings


@pytest.fixture
def client():
    return TestClient(app)


# ==================== api_server manual-send guards ====================


class TestApiSendGuards:
    def test_send_message_respects_the_primary_boards_window(self, client):
        """POST /send-message drives the primary board's client (issue #1788)."""
        service = MagicMock()
        service.vb_client.render.return_value = (True, True)
        with (
            _board_aware_silence(),
            patch("src.api_server.get_service", return_value=service),
            patch("src.api_server.get_settings_service", return_value=_settings()),
        ):
            response = client.post("/send-message", json={"text": "HELLO"})

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "blocked"
        assert response.json()["silence_mode"] is True
        service.vb_client.render.assert_not_called()

    def test_send_welcome_message_respects_the_primary_boards_window(self, client):
        with (
            _board_aware_silence(),
            patch("src.api_server.get_settings_service", return_value=_settings()),
            patch("src.board_client.BoardClient") as board_client,
        ):
            board_client.return_value.render.return_value = (True, True)
            response = client.post("/send-welcome-message")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "blocked"
        board_client.return_value.render.assert_not_called()

    def test_page_send_respects_the_target_boards_window(self, client):
        """POST /pages/{id}/send?board_id= must use that board's window."""
        page = MagicMock(transition_strategy=None, transition_interval_ms=None, transition_step_size=None)
        page_service = MagicMock()
        page_service.get_page.return_value = page
        page_service.preview_page.return_value = MagicMock(available=True, error=None)
        service = MagicMock()
        board_client = MagicMock()
        board_client.render.return_value = (True, True)
        service.get_board_client.return_value = board_client

        with (
            _board_aware_silence(),
            patch("src.api_server.get_page_service", return_value=page_service),
            patch("src.api_server.get_settings_service", return_value=_settings(primary=LOUD_BOARD)),
            patch("src.api_server.get_service", return_value=service),
            patch("src.api_server._find_board", return_value=BOARDS[0]),
        ):
            response = client.post(f"/pages/page-1/send?board_id={SILENCED_BOARD}")

        assert response.status_code == 200, response.text
        assert response.json()["sent_to_board"] is False
        board_client.render.assert_not_called()

    def test_live_transition_test_respects_the_target_boards_window(self, client):
        registry = MagicMock()
        registry.get_transition_plugin.return_value = MagicMock()

        with (
            _board_aware_silence(),
            patch("src.api_server._ensure_transition_plugins_beta"),
            patch("src.plugins.registry.get_plugin_registry", return_value=registry),
            patch("src.api_server._resolve_live_board_client", return_value=(BOARDS[0], MagicMock())),
            patch("src.api_server.get_settings_service", return_value=_settings(primary=LOUD_BOARD)),
        ):
            response = client.post(
                "/transitions/test-live",
                json={"plugin_id": "wipe", "to_page_id": "page-1", "board_id": SILENCED_BOARD},
            )

        # The silence guard is the first thing after the board client is
        # resolved, so any other status means it did not fire.
        assert response.status_code == 409, response.text
        assert "Silence" in response.json()["detail"]

    def test_transition_restore_respects_the_target_boards_window(self, client):
        with (
            _board_aware_silence(),
            patch("src.api_server._ensure_transition_plugins_beta"),
            patch("src.api_server._resolve_live_board_client", return_value=(BOARDS[0], MagicMock())),
            patch("src.api_server.get_settings_service", return_value=_settings(primary=LOUD_BOARD)),
        ):
            response = client.post("/transitions/restore", json={"board_id": SILENCED_BOARD})

        # Same ordering as /transitions/test-live: anything but 409 means the
        # guard resolved the wrong board and let the restore through.
        assert response.status_code == 409, response.text
        assert "Silence" in response.json()["detail"]


# ==================== MQTT / Home Assistant ====================


class TestMqttSilenceIsPerBoard:
    def test_state_publisher_reports_the_primary_boards_silence(self):
        """The HA ``silence_mode`` sensor mirrors the rest of the payload.

        Every other field in ``_gather_state`` is primary-board scoped
        (``get_active_page_id()``, ``get_transition_settings()``), so the
        silence sensor must be too — publishing the install-wide layer makes
        it report OFF while the board it describes is snoozing.
        """
        page_service = MagicMock()
        page_service.get_page.return_value = MagicMock(name="Weather")
        page_service.list_pages.return_value = []

        mock_client = MagicMock(spec=MQTTClient)
        mock_client.config = MQTTConfig(enabled=True, base_topic="fiestaboard")

        with (
            _board_aware_silence(),
            patch("src.settings.service.get_settings_service", return_value=_settings()),
            patch("src.pages.service.get_page_service", return_value=page_service),
            patch("src.api_server._get_board_client", return_value=None),
            patch("src.config_manager.ConfigManager") as mock_cm,
        ):
            mock_cm.return_value._config = {"plugins": {}}
            publisher = StatePublisher(mock_client)
            state = publisher._gather_state()

        assert state["silence_mode"] == "ON"

    def test_mqtt_send_message_respects_the_target_boards_window(self):
        """A Home Assistant send to a silenced board must be dropped."""
        mock_client = MagicMock(spec=MQTTClient)
        mock_client._state_publisher = None
        mock_client.config = MQTTConfig(enabled=True, base_topic="fiestaboard")
        handler = CommandHandler(mock_client)

        service = MagicMock()
        target_client = MagicMock()
        service.get_board_client.return_value = target_client

        with (
            _board_aware_silence(),
            patch("src.api_server.get_service", return_value=service),
            patch("src.settings.service.get_settings_service", return_value=_settings(primary=LOUD_BOARD)),
        ):
            handler.handle("send_message", '{"message": "HELLO", "board": "Bedroom"}')

        target_client.send_characters.assert_not_called()
        service.vb_client.send_characters.assert_not_called()
