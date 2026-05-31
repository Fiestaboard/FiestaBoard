"""Additional tests for api_server.py to boost coverage on untested endpoint groups.

Covers: service start/stop, welcome message, board config reset, config validation,
general config updates, board scan, MQTT status/discovery, active page setting,
display settings, silence status, display send, page send, force refresh,
debug endpoints (error paths), plugin endpoints, stocks, and transit cache.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from src.api_server import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_service():
    """Mock the get_service() return and related globals."""
    service = Mock()
    service.vb_client = Mock()
    service.vb_client.send_characters.return_value = (True, True)
    service.vb_client.clear_cache.return_value = None
    service.vb_client.test_connection.return_value = True
    service.vb_client.get_cache_status.return_value = {"has_cached_text": False}
    service.running = True
    service.initialize.return_value = True
    service.reinitialize_board_client.return_value = None
    service.check_and_send_active_page.return_value = None
    with patch("src.api_server.get_service", return_value=service):
        yield service


@pytest.fixture
def mock_config_manager():
    """Mock the config manager."""
    with patch("src.api_server.get_config_manager") as mock_get:
        cm = Mock()
        cm.get_board.return_value = {
            "api_mode": "local",
            "local_api_key": "test_key_12345",
            "host": "192.168.1.100",
        }
        cm.validate.return_value = (True, [])
        cm.get_general.return_value = {"timezone": "UTC", "refresh_interval_seconds": 60}
        cm.set_general.return_value = True
        cm.get_feature.return_value = {
            "enabled": False,
            "start_time": "20:00+00:00",
            "end_time": "07:00+00:00",
        }
        cm.reset_board_config.return_value = None
        cm.migrate_silence_schedule_to_utc.return_value = None
        mock_get.return_value = cm
        yield cm


@pytest.fixture
def mock_settings_service():
    """Mock the settings service."""
    with patch("src.api_server.get_settings_service") as mock_get:
        ss = Mock()
        transition = Mock()
        transition.strategy = "column"
        transition.step_interval_ms = 100
        transition.step_size = 1
        ss.get_transition_settings.return_value = transition

        output = Mock()
        output.target = "ui"
        output.to_dict.return_value = {"target": "ui"}
        ss.get_output_settings.return_value = output

        board_settings = Mock()
        board_settings.boards = [{"id": "b1", "device_type": "flagship"}]
        board_settings.to_dict.return_value = {"boards": [{"id": "b1"}]}
        ss.get_board_settings.return_value = board_settings

        display = Mock()
        display.to_dict.return_value = {
            "reduce_motion": False,
            "board_animations": "on",
            "site_animations": "on",
        }
        ss.get_display_settings.return_value = display
        ss.update_display_settings.return_value = display

        ss.get_active_page_id.return_value = "page1"
        ss.should_send_to_board.return_value = False
        ss.set_active_page_id.return_value = None
        mock_get.return_value = ss
        yield ss


@pytest.fixture
def mock_page_service():
    """Mock the page service."""
    with patch("src.api_server.get_page_service") as mock_get:
        ps = Mock()
        page = Mock()
        page.transition_strategy = None
        page.transition_interval_ms = None
        page.transition_step_size = None
        page.device_type = "flagship"
        ps.get_page.return_value = page

        preview = Mock()
        preview.available = True
        preview.formatted = "HELLO WORLD"
        preview.error = None
        ps.preview_page.return_value = preview

        mock_get.return_value = ps
        yield ps


@pytest.fixture
def mock_carousel_service():
    """Mock the carousel service."""
    with patch("src.api_server.get_carousel_service") as mock_get:
        cs = Mock()
        cs.get_carousel.return_value = None
        cs.resolve_page_id.return_value = None
        mock_get.return_value = cs
        yield cs


# ===========================================================================
# Priority 1 – Service & Board Operations
# ===========================================================================

class TestStartService:
    """Tests for POST /start."""

    def test_start_already_running(self, client):
        """When service is already running, return status already_running."""
        with patch("src.api_server._service_running", True), \
             patch("src.api_server.get_service", return_value=Mock()):
            response = client.post("/start")
            assert response.status_code == 200
            assert response.json()["status"] == "already_running"

    def test_start_no_service(self, client):
        """When service cannot be created, return 503."""
        with patch("src.api_server._service_running", False), \
             patch("src.api_server.get_service", return_value=None):
            response = client.post("/start")
            assert response.status_code == 503

    def test_start_service_needs_reinit(self, client):
        """When service.vb_client is None, retry initialization."""
        service = Mock()
        service.vb_client = None
        service.initialize.return_value = False
        with patch("src.api_server._service_running", False), \
             patch("src.api_server.get_service", return_value=service):
            response = client.post("/start")
            assert response.status_code == 503
            assert "initialization failed" in response.json()["detail"].lower()

    def test_start_service_success(self, client):
        """Successful service start."""
        service = Mock()
        service.vb_client = Mock()

        def fake_start():
            import src.api_server as mod
            mod._service_running = True

        with patch("src.api_server._service_running", False), \
             patch("src.api_server.get_service", return_value=service), \
             patch("src.api_server.threading") as mock_threading, \
             patch("src.api_server.asyncio") as mock_asyncio:
            thread = Mock()
            mock_threading.Thread.return_value = thread
            thread.start.side_effect = fake_start
            # mock asyncio.sleep to be a coroutine
            import asyncio
            mock_asyncio.sleep = asyncio.sleep
            response = client.post("/start")
            assert response.status_code == 200
            assert response.json()["status"] == "started"

    def test_start_service_fails_to_start(self, client):
        """Service thread starts but _service_running stays False."""
        service = Mock()
        service.vb_client = Mock()
        with patch("src.api_server._service_running", False), \
             patch("src.api_server.get_service", return_value=service), \
             patch("src.api_server.threading") as mock_threading:
            thread = Mock()
            mock_threading.Thread.return_value = thread
            response = client.post("/start")
            assert response.status_code == 500


class TestStopService:
    """Tests for POST /stop."""

    def test_stop_not_running(self, client):
        """Stopping when not running returns not_running."""
        with patch("src.api_server._service_running", False):
            response = client.post("/stop")
            assert response.status_code == 200
            assert response.json()["status"] == "not_running"

    def test_stop_success(self, client):
        """Stopping a running service."""
        service = Mock()
        with patch("src.api_server._service_running", True), \
             patch("src.api_server._service", service):
            response = client.post("/stop")
            assert response.status_code == 200
            assert response.json()["status"] == "stopped"


class TestSendWelcomeMessage:
    """Tests for POST /send-welcome-message."""

    def test_welcome_silence_mode(self, client):
        """Welcome is blocked during silence mode."""
        with patch("src.api_server.Config") as mock_config:
            mock_config.is_silence_mode_active.return_value = True
            response = client.post("/send-welcome-message")
            assert response.status_code == 200
            assert response.json()["status"] == "blocked"

    def test_welcome_board_not_configured(self, client):
        """Welcome fails when board client cannot be created."""
        with patch("src.api_server.Config") as mock_config, \
             patch("src.board_client.BoardClient", side_effect=ValueError("no key")):
            mock_config.is_silence_mode_active.return_value = False
            mock_config.BOARD_API_MODE = "local"
            mock_config.get_board_api_key.return_value = "test_key_12345"
            mock_config.BOARD_HOST = "192.168.1.100"
            response = client.post("/send-welcome-message")
            assert response.status_code == 503

    def test_welcome_success(self, client):
        """Welcome message sent successfully."""
        with patch("src.api_server.Config") as mock_config, \
             patch("src.board_client.BoardClient") as MockBoardClient, \
             patch("src.api_server.text_to_board_array") as mock_ttba, \
             patch("src.api_server.get_settings_service") as mock_ss:
            mock_config.is_silence_mode_active.return_value = False
            mock_config.BOARD_API_MODE = "local"
            mock_config.get_board_api_key.return_value = "test_key_12345"
            mock_config.BOARD_HOST = "192.168.1.100"

            board_client = Mock()
            board_client.send_characters.return_value = (True, True)
            MockBoardClient.return_value = board_client

            mock_ttba.return_value = [[0] * 22 for _ in range(6)]

            ss = Mock()
            transition = Mock()
            transition.strategy = "column"
            transition.step_interval_ms = 100
            transition.step_size = 1
            ss.get_transition_settings.return_value = transition
            mock_ss.return_value = ss

            response = client.post("/send-welcome-message")
            assert response.status_code == 200
            assert response.json()["status"] == "success"

    def test_welcome_send_failure(self, client):
        """Welcome message fails to send."""
        with patch("src.api_server.Config") as mock_config, \
             patch("src.board_client.BoardClient") as MockBoardClient, \
             patch("src.api_server.text_to_board_array") as mock_ttba, \
             patch("src.api_server.get_settings_service") as mock_ss:
            mock_config.is_silence_mode_active.return_value = False
            mock_config.BOARD_API_MODE = "local"
            mock_config.get_board_api_key.return_value = "test_key_12345"
            mock_config.BOARD_HOST = "192.168.1.100"

            board_client = Mock()
            board_client.send_characters.return_value = (False, False)
            MockBoardClient.return_value = board_client

            mock_ttba.return_value = [[0] * 22 for _ in range(6)]

            ss = Mock()
            transition = Mock()
            transition.strategy = "column"
            transition.step_interval_ms = 100
            transition.step_size = 1
            ss.get_transition_settings.return_value = transition
            mock_ss.return_value = ss

            response = client.post("/send-welcome-message")
            assert response.status_code == 500

    def test_welcome_unchanged(self, client):
        """Welcome message unchanged (was_sent=False, success=True)."""
        with patch("src.api_server.Config") as mock_config, \
             patch("src.board_client.BoardClient") as MockBoardClient, \
             patch("src.api_server.text_to_board_array") as mock_ttba, \
             patch("src.api_server.get_settings_service") as mock_ss:
            mock_config.is_silence_mode_active.return_value = False
            mock_config.BOARD_API_MODE = "cloud"
            mock_config.get_board_api_key.return_value = "test_cloud_key"
            mock_config.BOARD_HOST = "192.168.1.100"

            board_client = Mock()
            board_client.send_characters.return_value = (True, False)
            MockBoardClient.return_value = board_client

            mock_ttba.return_value = [[0] * 22 for _ in range(6)]

            ss = Mock()
            transition = Mock()
            transition.strategy = "column"
            transition.step_interval_ms = 100
            transition.step_size = 1
            ss.get_transition_settings.return_value = transition
            mock_ss.return_value = ss

            response = client.post("/send-welcome-message")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data.get("skipped") is True

    def test_welcome_uses_note_template_for_note_board(self, client):
        """When the configured board is a Note, render the 3x15 template."""
        with patch("src.api_server.Config") as mock_config, \
             patch("src.board_client.BoardClient") as MockBoardClient, \
             patch("src.api_server.text_to_board_array") as mock_ttba, \
             patch("src.api_server.get_settings_service") as mock_ss:
            mock_config.is_silence_mode_active.return_value = False
            mock_config.BOARD_API_MODE = "local"
            mock_config.get_board_api_key.return_value = "test_key_12345"
            mock_config.BOARD_HOST = "192.168.1.100"

            board_client = Mock()
            board_client.send_characters.return_value = (True, True)
            MockBoardClient.return_value = board_client

            mock_ttba.return_value = [[0] * 15 for _ in range(3)]

            ss = Mock()
            transition = Mock()
            transition.strategy = "column"
            transition.step_interval_ms = 100
            transition.step_size = 1
            ss.get_transition_settings.return_value = transition
            board_settings = Mock()
            board_settings.boards = [{"device_type": "note"}]
            ss.get_board_settings.return_value = board_settings
            mock_ss.return_value = ss

            response = client.post("/send-welcome-message")
            assert response.status_code == 200
            assert response.json()["status"] == "success"

            # Verify text_to_board_array was called with Note dimensions
            assert mock_ttba.call_count == 1
            kwargs = mock_ttba.call_args.kwargs
            assert kwargs.get("rows") == 3
            assert kwargs.get("cols") == 15
            # And that the rendered welcome text has 3 lines; the center row
            # (plain text, not color markers) fits in the 15-column Note width.
            welcome_text = mock_ttba.call_args.args[0]
            lines = welcome_text.split("\n")
            assert len(lines) == 3
            # Center line is the only one without color markers
            center = lines[1]
            assert "{" not in center
            assert len(center) <= 15

    def test_welcome_uses_flagship_template_for_flagship_board(self, client):
        """When the configured board is a Flagship, render the 6x22 template."""
        with patch("src.api_server.Config") as mock_config, \
             patch("src.board_client.BoardClient") as MockBoardClient, \
             patch("src.api_server.text_to_board_array") as mock_ttba, \
             patch("src.api_server.get_settings_service") as mock_ss:
            mock_config.is_silence_mode_active.return_value = False
            mock_config.BOARD_API_MODE = "local"
            mock_config.get_board_api_key.return_value = "test_key_12345"
            mock_config.BOARD_HOST = "192.168.1.100"

            board_client = Mock()
            board_client.send_characters.return_value = (True, True)
            MockBoardClient.return_value = board_client

            mock_ttba.return_value = [[0] * 22 for _ in range(6)]

            ss = Mock()
            transition = Mock()
            transition.strategy = "column"
            transition.step_interval_ms = 100
            transition.step_size = 1
            ss.get_transition_settings.return_value = transition
            board_settings = Mock()
            board_settings.boards = [{"device_type": "flagship"}]
            ss.get_board_settings.return_value = board_settings
            mock_ss.return_value = ss

            response = client.post("/send-welcome-message")
            assert response.status_code == 200
            assert response.json()["status"] == "success"

            assert mock_ttba.call_count == 1
            kwargs = mock_ttba.call_args.kwargs
            assert kwargs.get("rows") == 6
            assert kwargs.get("cols") == 22
            welcome_text = mock_ttba.call_args.args[0]
            assert "HIYA FROM FIESTABOARD" in welcome_text


class TestBuildWelcomeTemplate:
    """Unit tests for _build_welcome_template helper."""

    def test_flagship_default_message(self):
        from src.api_server import _build_welcome_template

        template = _build_welcome_template("flagship", "")
        assert len(template) == 6
        # Center row (index 2) carries the default Flagship message
        assert template[2] == "HIYA FROM FIESTABOARD"

    def test_note_default_message(self):
        from src.api_server import _build_welcome_template

        template = _build_welcome_template("note", "")
        assert len(template) == 3
        # Center row (index 1) carries the default Note message
        assert template[1] == "HIYA FIESTA!"
        # Center text fits in 15 cols
        assert len(template[1]) <= 15

    def test_note_custom_message_truncated_to_15(self):
        from src.api_server import _build_welcome_template

        template = _build_welcome_template(
            "note", "this message is way too long for a note"
        )
        assert len(template) == 3
        assert template[1] == "THIS MESSAGE IS"
        assert len(template[1]) == 15

    def test_flagship_custom_message_truncated_to_22(self):
        from src.api_server import _build_welcome_template

        template = _build_welcome_template(
            "flagship", "this message is much longer than twenty two cols"
        )
        assert len(template) == 6
        assert template[2] == "THIS MESSAGE IS MUCH L"
        assert len(template[2]) == 22

    def test_unknown_device_falls_back_to_flagship(self):
        from src.api_server import _build_welcome_template

        template = _build_welcome_template("unknown", "")
        assert len(template) == 6
        assert template[2] == "HIYA FROM FIESTABOARD"


# ===========================================================================
# Priority 2 – Configuration Endpoints
# ===========================================================================

class TestResetBoardConfig:
    """Tests for DELETE /config/board."""

    def test_reset_board_config(self, client, mock_config_manager, mock_service, mock_settings_service):
        """Reset board config clears legacy config, settings boards, and reinitializes."""
        response = client.delete("/config/board")
        assert response.status_code == 200
        assert response.json()["status"] == "reset"
        mock_config_manager.reset_board_config.assert_called_once()
        mock_service.reinitialize_board_client.assert_called_once()
        # Settings service boards should be reset to a single unconfigured board
        mock_settings_service.set_boards.assert_called_once()
        boards_arg = mock_settings_service.set_boards.call_args[0][0]
        assert len(boards_arg) == 1
        assert boards_arg[0]["local_api_key"] == ""
        assert boards_arg[0]["cloud_key"] == ""
        assert boards_arg[0]["host"] == ""

    def test_reset_board_config_no_service(self, client, mock_config_manager, mock_settings_service):
        """Reset when service is None still succeeds."""
        with patch("src.api_server.get_service", return_value=None):
            response = client.delete("/config/board")
            assert response.status_code == 200
            mock_config_manager.reset_board_config.assert_called_once()


class TestValidateConfig:
    """Tests for GET /config/validate."""

    def test_validate_config_valid_local(self, client, mock_config_manager):
        """Valid local config returns valid=True, is_first_run=False."""
        response = client.get("/config/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["is_first_run"] is False
        assert data["missing_fields"] == []

    def test_validate_config_first_run_local_no_key(self, client, mock_config_manager, mock_settings_service):
        """Local mode with missing key is first-run."""
        mock_config_manager.get_board.return_value = {
            "api_mode": "local",
            "local_api_key": "",
            "host": "",
        }
        response = client.get("/config/validate")
        data = response.json()
        assert data["is_first_run"] is True
        assert "board.local_api_key" in data["missing_fields"]
        assert "board.host" in data["missing_fields"]

    def test_validate_config_first_run_cloud(self, client, mock_config_manager, mock_settings_service):
        """Cloud mode with missing key is first-run."""
        mock_config_manager.get_board.return_value = {
            "api_mode": "cloud",
            "cloud_key": "",
        }
        response = client.get("/config/validate")
        data = response.json()
        assert data["is_first_run"] is True
        assert "board.cloud_key" in data["missing_fields"]

    def test_validate_config_multi_board_overrides_first_run(
        self, client, mock_config_manager, mock_settings_service
    ):
        """A configured board instance in multi-board settings clears first-run state.

        When a user sets up a board via Settings (rather than the wizard),
        the legacy single-board config remains empty but the new
        ``settings.boards`` list contains a configured board. The
        validate endpoint must report ``is_first_run=False`` and
        ``valid=True`` so the home page does not nag the user to run
        the wizard.
        """
        # Legacy board config is empty (would normally trigger first-run)
        mock_config_manager.get_board.return_value = {
            "api_mode": "local",
            "local_api_key": "",
            "host": "",
        }
        mock_config_manager.validate.return_value = (
            False,
            [
                "Board local_api_key is required when api_mode is 'local'",
                "Board host is required when api_mode is 'local'",
            ],
        )
        # But the multi-board settings has a fully configured local board
        board_settings = Mock()
        board_settings.boards = [
            {
                "id": "b1",
                "name": "My Board",
                "device_type": "flagship",
                "board_color": "black",
                "enabled": True,
                "api_mode": "local",
                "host": "192.168.1.100",
                "local_api_key": "configured-key",
                "cloud_key": "",
            }
        ]
        mock_settings_service.get_board_settings.return_value = board_settings

        response = client.get("/config/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["is_first_run"] is False
        assert data["valid"] is True
        assert data["missing_fields"] == []
        # Board-related errors should be removed
        assert not any(e.startswith("Board ") for e in data["errors"])

    def test_validate_config_multi_board_unconfigured_still_first_run(
        self, client, mock_config_manager, mock_settings_service
    ):
        """Multi-board settings with no credentials does NOT clear first-run state."""
        mock_config_manager.get_board.return_value = {
            "api_mode": "local",
            "local_api_key": "",
            "host": "",
        }
        board_settings = Mock()
        board_settings.boards = [
            {
                "id": "b1",
                "name": "My Board",
                "device_type": "flagship",
                "api_mode": "local",
                "host": "",
                "local_api_key": "",
                "cloud_key": "",
            }
        ]
        mock_settings_service.get_board_settings.return_value = board_settings

        response = client.get("/config/validate")
        data = response.json()
        assert data["is_first_run"] is True
        assert "board.local_api_key" in data["missing_fields"]
        assert "board.host" in data["missing_fields"]


class TestUpdateGeneralConfig:
    """Tests for PUT /config/general."""

    def test_update_timezone(self, client, mock_config_manager):
        """Update timezone."""
        response = client.put("/config/general", json={"timezone": "America/New_York"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_update_refresh_interval(self, client, mock_config_manager):
        """Update refresh interval."""
        response = client.put("/config/general", json={"refresh_interval_seconds": 120})
        assert response.status_code == 200

    def test_update_output_target(self, client, mock_config_manager):
        """Update output target."""
        response = client.put("/config/general", json={"output_target": "board"})
        assert response.status_code == 200

    def test_update_general_failure(self, client, mock_config_manager):
        """set_general returns False → 500."""
        mock_config_manager.set_general.return_value = False
        response = client.put("/config/general", json={"timezone": "X"})
        assert response.status_code == 500


class TestBoardScan:
    """Tests for POST /config/board/scan."""

    def test_scan_default_timeout(self, client):
        """Scan with default timeout."""
        with patch("src.system.mdns.scan_for_boards", return_value=[{"ip": "192.168.1.50"}]):
            response = client.post("/config/board/scan")
            assert response.status_code == 200
            assert "boards" in response.json()

    def test_scan_custom_timeout(self, client):
        """Scan with custom timeout."""
        with patch("src.system.mdns.scan_for_boards", return_value=[]) as mock_scan:
            response = client.post("/config/board/scan", json={"timeout": 2.0})
            assert response.status_code == 200
            assert response.json()["boards"] == []
            mock_scan.assert_called_once_with(timeout=2.0)

    def test_scan_timeout_clamped(self, client):
        """Timeout is clamped to [1, 15]."""
        with patch("src.system.mdns.scan_for_boards", return_value=[]) as mock_scan:
            response = client.post("/config/board/scan", json={"timeout": 100})
            assert response.status_code == 200
            mock_scan.assert_called_once_with(timeout=15.0)


# ===========================================================================
# Priority 3 – MQTT Operations
# ===========================================================================

class TestMQTTStatus:
    """Tests for GET /mqtt/status."""

    def test_mqtt_status_no_client(self, client):
        """No MQTT client returns disabled."""
        with patch("src.mqtt.get_mqtt_client", return_value=None):
            response = client.get("/mqtt/status")
            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] is False

    def test_mqtt_status_connected(self, client):
        """Connected MQTT client."""
        mqtt = Mock()
        mqtt.is_connected.return_value = True
        mqtt.is_running.return_value = True
        with patch("src.mqtt.get_mqtt_client", return_value=mqtt):
            response = client.get("/mqtt/status")
            data = response.json()
            assert data["enabled"] is True
            assert data["connected"] is True
            assert data["running"] is True

    def test_mqtt_status_exception(self, client):
        """Exception returns disabled."""
        with patch("src.mqtt.get_mqtt_client", side_effect=Exception("boom")):
            response = client.get("/mqtt/status")
            data = response.json()
            assert data["enabled"] is False


class TestMQTTRepublishDiscovery:
    """Tests for POST /mqtt/republish-discovery."""

    def test_republish_success(self, client):
        """Successful republish."""
        mqtt = Mock()
        mqtt.is_connected.return_value = True
        with patch("src.mqtt.get_mqtt_client", return_value=mqtt):
            response = client.post("/mqtt/republish-discovery")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            mqtt._publish_discovery.assert_called_once()

    def test_republish_not_connected(self, client):
        """MQTT not connected → 503."""
        with patch("src.mqtt.get_mqtt_client", return_value=None):
            response = client.post("/mqtt/republish-discovery")
            assert response.status_code == 503

    def test_republish_client_disconnected(self, client):
        """Client exists but disconnected → 503."""
        mqtt = Mock()
        mqtt.is_connected.return_value = False
        with patch("src.mqtt.get_mqtt_client", return_value=mqtt):
            response = client.post("/mqtt/republish-discovery")
            assert response.status_code == 503

    def test_republish_exception(self, client):
        """Internal error → 500."""
        mqtt = Mock()
        mqtt.is_connected.return_value = True
        mqtt._publish_discovery.side_effect = RuntimeError("oops")
        with patch("src.mqtt.get_mqtt_client", return_value=mqtt):
            response = client.post("/mqtt/republish-discovery")
            assert response.status_code == 500


# ===========================================================================
# Priority 4 – Settings
# ===========================================================================

class TestSetActivePage:
    """Tests for PUT /settings/active-page."""

    def test_set_active_page_with_board_send(
        self, client, mock_settings_service, mock_page_service, mock_service, mock_carousel_service
    ):
        """Setting an active page also sends to board when enabled."""
        mock_settings_service.should_send_to_board.return_value = True
        page = mock_page_service.get_page.return_value
        preview = mock_page_service.preview_page.return_value
        with patch("src.api_server.get_dimensions") as mock_dims, \
             patch("src.api_server.text_to_board_array") as mock_ttba:
            mock_dims.return_value = Mock(rows=6, cols=22)
            mock_ttba.return_value = [[0] * 22 for _ in range(6)]
            response = client.put("/settings/active-page", json={"page_id": "page1"})
            assert response.status_code == 200
            assert response.json()["sent_to_board"] is True

    def test_set_active_page_carousel(
        self, client, mock_settings_service, mock_page_service, mock_service, mock_carousel_service
    ):
        """Setting a carousel ID as active page."""
        mock_carousel_service.get_carousel.return_value = Mock()
        mock_carousel_service.resolve_page_id.return_value = "resolved_page"
        with patch("src.api_server.is_carousel_id", return_value=True):
            response = client.put("/settings/active-page", json={"page_id": "carousel:abc"})
            assert response.status_code == 200
            mock_carousel_service.get_carousel.assert_called_once()

    def test_set_active_page_carousel_not_found(
        self, client, mock_settings_service, mock_page_service, mock_service, mock_carousel_service
    ):
        """Carousel not found → 404."""
        mock_carousel_service.get_carousel.return_value = None
        with patch("src.api_server.is_carousel_id", return_value=True):
            response = client.put("/settings/active-page", json={"page_id": "carousel:nope"})
            assert response.status_code == 404

    def test_set_active_page_send_fails(
        self, client, mock_settings_service, mock_page_service, mock_service, mock_carousel_service
    ):
        """Board send failure still returns success but sent_to_board is False."""
        mock_settings_service.should_send_to_board.return_value = True
        mock_service.vb_client.send_characters.return_value = (False, False)
        with patch("src.api_server.get_dimensions") as mock_dims, \
             patch("src.api_server.text_to_board_array") as mock_ttba:
            mock_dims.return_value = Mock(rows=6, cols=22)
            mock_ttba.return_value = [[0] * 22 for _ in range(6)]
            response = client.put("/settings/active-page", json={"page_id": "page1"})
            # send_characters returns (False, False), the endpoint logs a warning
            assert response.status_code == 200


class TestDisplaySettings:
    """Tests for PUT /settings/display."""

    def test_update_display_settings(self, client, mock_settings_service):
        """Update display settings."""
        response = client.put("/settings/display", json={"reduce_motion": True})
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        mock_settings_service.update_display_settings.assert_called_once()

    def test_get_display_settings(self, client, mock_settings_service):
        """Get display settings."""
        response = client.get("/settings/display")
        assert response.status_code == 200


class TestSilenceStatus:
    """Tests for GET /silence-status."""

    def test_silence_disabled(self, client, mock_config_manager):
        """Silence disabled returns active=False."""
        with patch("src.time_service.get_time_service") as mock_ts:
            ts = Mock()
            ts.get_current_utc.return_value = Mock(strftime=Mock(return_value="12:00+00:00"))
            mock_ts.return_value = ts
            response = client.get("/silence-status")
            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] is False
            assert data["active"] is False

    def test_silence_enabled_active(self, client, mock_config_manager):
        """Silence enabled and currently active."""
        mock_config_manager.get_feature.return_value = {
            "enabled": True,
            "start_time": "22:00+00:00",
            "end_time": "06:00+00:00",
        }
        with patch("src.time_service.get_time_service") as mock_ts:
            ts = Mock()
            ts.is_time_in_window.return_value = True
            ts.get_current_utc.return_value = Mock(strftime=Mock(return_value="23:00+00:00"))
            mock_ts.return_value = ts
            response = client.get("/silence-status")
            data = response.json()
            assert data["enabled"] is True
            assert data["active"] is True
            assert data["next_change_utc"] == "06:00+00:00"

    def test_silence_enabled_inactive(self, client, mock_config_manager):
        """Silence enabled but not currently active."""
        mock_config_manager.get_feature.return_value = {
            "enabled": True,
            "start_time": "22:00+00:00",
            "end_time": "06:00+00:00",
        }
        with patch("src.time_service.get_time_service") as mock_ts:
            ts = Mock()
            ts.is_time_in_window.return_value = False
            ts.get_current_utc.return_value = Mock(strftime=Mock(return_value="12:00+00:00"))
            mock_ts.return_value = ts
            response = client.get("/silence-status")
            data = response.json()
            assert data["enabled"] is True
            assert data["active"] is False
            assert data["next_change_utc"] == "22:00+00:00"


# ===========================================================================
# Priority 5 – Content Operations
# ===========================================================================

class TestSendDisplay:
    """Tests for POST /displays/{display_type}/send."""

    def test_send_display_invalid_target(self, client):
        """Invalid target returns 400."""
        response = client.post("/displays/weather/send?target=invalid")
        assert response.status_code == 400

    def test_send_display_no_service(self, client):
        """No service returns 503."""
        with patch("src.api_server.get_display_service"), \
             patch("src.api_server.get_settings_service"), \
             patch("src.api_server.get_service", return_value=None):
            response = client.post("/displays/weather/send")
            assert response.status_code == 503

    def test_send_display_no_vb_client(self, client):
        """Service without vb_client returns 503."""
        svc = Mock()
        svc.vb_client = None
        with patch("src.api_server.get_display_service"), \
             patch("src.api_server.get_settings_service"), \
             patch("src.api_server.get_service", return_value=svc):
            response = client.post("/displays/weather/send")
            assert response.status_code == 503

    def test_send_display_unknown_type(self, client, mock_service, mock_settings_service):
        """Unknown display type → 400."""
        with patch("src.api_server.get_display_service") as mock_ds:
            display_service = Mock()
            result = Mock()
            result.available = False
            result.error = "Unknown display type: fake_display"
            display_service.get_display.return_value = result
            mock_ds.return_value = display_service
            response = client.post("/displays/fake_display/send")
            assert response.status_code == 400

    def test_send_display_not_available(self, client, mock_service, mock_settings_service):
        """Display not available → 503."""
        with patch("src.api_server.get_display_service") as mock_ds:
            display_service = Mock()
            result = Mock()
            result.available = False
            result.error = "Plugin not configured"
            display_service.get_display.return_value = result
            mock_ds.return_value = display_service
            response = client.post("/displays/weather/send")
            assert response.status_code == 503

    def test_send_display_to_board(self, client, mock_service, mock_settings_service):
        """Send display to board successfully."""
        mock_settings_service.should_send_to_board.return_value = True
        with patch("src.api_server.get_display_service") as mock_ds, \
             patch("src.api_server.text_to_board_array") as mock_ttba, \
             patch("src.api_server.get_dimensions") as mock_dims:
            display_service = Mock()
            result = Mock()
            result.available = True
            result.formatted = "WEATHER DATA"
            result.error = None
            display_service.get_display.return_value = result
            mock_ds.return_value = display_service

            mock_dims.return_value = Mock(rows=6, cols=22)
            mock_ttba.return_value = [[0] * 22 for _ in range(6)]

            response = client.post("/displays/weather/send")
            assert response.status_code == 200
            assert response.json()["sent_to_board"] is True

    def test_send_display_board_failure(self, client, mock_service, mock_settings_service):
        """Board send failure → 500."""
        mock_settings_service.should_send_to_board.return_value = True
        mock_service.vb_client.send_characters.return_value = (False, False)
        with patch("src.api_server.get_display_service") as mock_ds, \
             patch("src.api_server.text_to_board_array") as mock_ttba, \
             patch("src.api_server.get_dimensions") as mock_dims:
            display_service = Mock()
            result = Mock()
            result.available = True
            result.formatted = "DATA"
            result.error = None
            display_service.get_display.return_value = result
            mock_ds.return_value = display_service

            mock_dims.return_value = Mock(rows=6, cols=22)
            mock_ttba.return_value = [[0] * 22 for _ in range(6)]

            response = client.post("/displays/weather/send")
            assert response.status_code == 500

    def test_send_display_target_override(self, client, mock_service, mock_settings_service):
        """Explicit target=ui skips board send."""
        with patch("src.api_server.get_display_service") as mock_ds:
            display_service = Mock()
            result = Mock()
            result.available = True
            result.formatted = "DATA"
            result.error = None
            display_service.get_display.return_value = result
            mock_ds.return_value = display_service

            response = client.post("/displays/weather/send?target=ui")
            assert response.status_code == 200
            assert response.json()["sent_to_board"] is False


class TestSendPage:
    """Tests for POST /pages/{page_id}/send."""

    def test_send_page_no_service(self, client):
        """No service → 503."""
        with patch("src.api_server.get_page_service"), \
             patch("src.api_server.get_settings_service"), \
             patch("src.api_server.get_service", return_value=None):
            response = client.post("/pages/page1/send")
            assert response.status_code == 503

    def test_send_page_not_found(self, client, mock_service, mock_settings_service):
        """Page not found → 404."""
        with patch("src.api_server.get_page_service") as mock_ps:
            ps = Mock()
            ps.get_page.return_value = None
            mock_ps.return_value = ps
            response = client.post("/pages/nonexistent/send")
            assert response.status_code == 404

    def test_send_page_render_none(self, client, mock_service, mock_settings_service, mock_page_service):
        """Preview returns None → 404."""
        mock_page_service.preview_page.return_value = None
        response = client.post("/pages/page1/send")
        assert response.status_code == 404

    def test_send_page_render_unavailable(self, client, mock_service, mock_settings_service, mock_page_service):
        """Preview not available → 503."""
        preview = Mock()
        preview.available = False
        preview.error = "Template error"
        mock_page_service.preview_page.return_value = preview
        response = client.post("/pages/page1/send")
        assert response.status_code == 503

    def test_send_page_success_ui_only(self, client, mock_service, mock_settings_service, mock_page_service):
        """Send page with output target UI only (default)."""
        response = client.post("/pages/page1/send")
        assert response.status_code == 200
        assert response.json()["sent_to_board"] is False

    def test_send_page_to_board(self, client, mock_service, mock_settings_service, mock_page_service):
        """Send page to board successfully."""
        mock_settings_service.should_send_to_board.return_value = True
        with patch("src.api_server.Config") as mock_config, \
             patch("src.api_server.get_dimensions") as mock_dims, \
             patch("src.api_server.text_to_board_array") as mock_ttba:
            mock_config.is_silence_mode_active.return_value = False
            mock_dims.return_value = Mock(rows=6, cols=22)
            mock_ttba.return_value = [[0] * 22 for _ in range(6)]

            response = client.post("/pages/page1/send")
            assert response.status_code == 200
            assert response.json()["sent_to_board"] is True

    def test_send_page_silence_mode_blocks(self, client, mock_service, mock_settings_service, mock_page_service):
        """Silence mode blocks board send but does not error."""
        mock_settings_service.should_send_to_board.return_value = True
        with patch("src.api_server.Config") as mock_config:
            mock_config.is_silence_mode_active.return_value = True
            response = client.post("/pages/page1/send")
            assert response.status_code == 200
            assert response.json()["sent_to_board"] is False

    def test_send_page_board_failure(self, client, mock_service, mock_settings_service, mock_page_service):
        """Board send failure → 500."""
        mock_settings_service.should_send_to_board.return_value = True
        mock_service.vb_client.send_characters.return_value = (False, False)
        with patch("src.api_server.Config") as mock_config, \
             patch("src.api_server.get_dimensions") as mock_dims, \
             patch("src.api_server.text_to_board_array") as mock_ttba:
            mock_config.is_silence_mode_active.return_value = False
            mock_dims.return_value = Mock(rows=6, cols=22)
            mock_ttba.return_value = [[0] * 22 for _ in range(6)]
            response = client.post("/pages/page1/send")
            assert response.status_code == 500

    def test_send_page_invalid_target(self, client):
        """Invalid target → 400."""
        response = client.post("/pages/page1/send?target=invalid")
        assert response.status_code == 400

    def test_send_page_target_board(self, client, mock_service, mock_settings_service, mock_page_service):
        """Explicit target=board sends to board."""
        with patch("src.api_server.Config") as mock_config, \
             patch("src.api_server.get_dimensions") as mock_dims, \
             patch("src.api_server.text_to_board_array") as mock_ttba:
            mock_config.is_silence_mode_active.return_value = False
            mock_dims.return_value = Mock(rows=6, cols=22)
            mock_ttba.return_value = [[0] * 22 for _ in range(6)]
            response = client.post("/pages/page1/send?target=board")
            assert response.status_code == 200
            assert response.json()["sent_to_board"] is True


class TestForceRefresh:
    """Tests for POST /force-refresh."""

    def test_force_refresh_no_service(self, client):
        """No service → 503."""
        with patch("src.api_server.get_service", return_value=None):
            response = client.post("/force-refresh")
            assert response.status_code == 503

    def test_force_refresh_success(self, client, mock_service):
        """Successful force refresh."""
        response = client.post("/force-refresh")
        assert response.status_code == 200
        mock_service.vb_client.clear_cache.assert_called_once()
        mock_service.check_and_send_active_page.assert_called_once()

    def test_force_refresh_no_vb_client(self, client):
        """Force refresh when vb_client is None still works."""
        service = Mock()
        service.vb_client = None
        service.check_and_send_active_page.return_value = None
        with patch("src.api_server.get_service", return_value=service):
            response = client.post("/force-refresh")
            assert response.status_code == 200

    def test_force_refresh_exception(self, client, mock_service):
        """Exception during refresh → 500."""
        mock_service.check_and_send_active_page.side_effect = RuntimeError("boom")
        response = client.post("/force-refresh")
        assert response.status_code == 500


# ===========================================================================
# Priority 6 – Debug Endpoints (error paths not covered elsewhere)
# ===========================================================================

class TestDebugBlankErrorPaths:
    """Additional error-path tests for POST /debug/blank."""

    def test_blank_ui_only(self, client):
        """When output target is UI only, blank returns success without sending."""
        with patch("src.api_server._get_board_client") as mock_bc, \
             patch("src.api_server.get_settings_service") as mock_ss:
            mock_bc.return_value = Mock()
            ss = Mock()
            ss.should_send_to_board.return_value = False
            mock_ss.return_value = ss
            response = client.post("/debug/blank")
            assert response.status_code == 200
            assert "ui only" in response.json()["message"].lower()

    def test_blank_send_failure(self, client):
        """Board send failure → 500."""
        with patch("src.api_server._get_board_client") as mock_bc, \
             patch("src.api_server.get_settings_service") as mock_ss:
            bc = Mock()
            bc.send_characters.return_value = (False, False)
            mock_bc.return_value = bc
            ss = Mock()
            ss.should_send_to_board.return_value = True
            mock_ss.return_value = ss
            response = client.post("/debug/blank")
            assert response.status_code == 500

    def test_blank_exception(self, client):
        """Exception during send → 500."""
        with patch("src.api_server._get_board_client") as mock_bc, \
             patch("src.api_server.get_settings_service") as mock_ss:
            bc = Mock()
            bc.send_characters.side_effect = RuntimeError("network error")
            mock_bc.return_value = bc
            ss = Mock()
            ss.should_send_to_board.return_value = True
            mock_ss.return_value = ss
            response = client.post("/debug/blank")
            assert response.status_code == 500


class TestDebugFillErrorPaths:
    """Additional error-path tests for POST /debug/fill."""

    def test_fill_ui_only(self, client):
        """When output target is UI only, fill returns success without sending."""
        with patch("src.api_server._get_board_client") as mock_bc, \
             patch("src.api_server.get_settings_service") as mock_ss:
            mock_bc.return_value = Mock()
            ss = Mock()
            ss.should_send_to_board.return_value = False
            mock_ss.return_value = ss
            response = client.post("/debug/fill", json={"character_code": 10})
            assert response.status_code == 200
            assert "ui only" in response.json()["message"].lower()

    def test_fill_send_failure(self, client):
        """Board send failure → 500."""
        with patch("src.api_server._get_board_client") as mock_bc, \
             patch("src.api_server.get_settings_service") as mock_ss:
            bc = Mock()
            bc.send_characters.return_value = (False, False)
            mock_bc.return_value = bc
            ss = Mock()
            ss.should_send_to_board.return_value = True
            mock_ss.return_value = ss
            response = client.post("/debug/fill", json={"character_code": 5})
            assert response.status_code == 500

    def test_fill_exception(self, client):
        """Exception during send → 500."""
        with patch("src.api_server._get_board_client") as mock_bc, \
             patch("src.api_server.get_settings_service") as mock_ss:
            bc = Mock()
            bc.send_characters.side_effect = RuntimeError("error")
            mock_bc.return_value = bc
            ss = Mock()
            ss.should_send_to_board.return_value = True
            mock_ss.return_value = ss
            response = client.post("/debug/fill", json={"character_code": 5})
            assert response.status_code == 500


class TestDebugInfoErrorPaths:
    """Additional error-path tests for POST /debug/info."""

    def test_info_ui_only(self, client):
        """UI-only mode returns debug info without sending."""
        with patch("src.api_server._get_board_client") as mock_bc, \
             patch("src.api_server.get_settings_service") as mock_ss, \
             patch("src.api_server.Config") as mock_config, \
             patch("src.api_server._get_server_ip", return_value="10.0.0.1"), \
             patch("src.api_server._get_service_uptime", return_value=3600), \
             patch("src.api_server._format_uptime", return_value="1h"), \
             patch("src.api_server.__version__", "1.0.0"), \
             patch("src.time_service.get_time_service") as mock_ts:
            mock_bc.return_value = Mock()
            ss = Mock()
            ss.should_send_to_board.return_value = False
            mock_ss.return_value = ss
            mock_config.BOARD_HOST = "192.168.1.1"
            mock_config.BOARD_API_MODE = "LOCAL"

            ts = Mock()
            ts.get_current_time.return_value = Mock(strftime=Mock(return_value="12:00"))
            mock_ts.return_value = ts

            response = client.post("/debug/info")
            assert response.status_code == 200
            assert "debug_info" in response.json()

    def test_info_send_failure(self, client):
        """Board send failure → 500."""
        with patch("src.api_server._get_board_client") as mock_bc, \
             patch("src.api_server.get_settings_service") as mock_ss, \
             patch("src.api_server.Config") as mock_config, \
             patch("src.api_server._get_server_ip", return_value="10.0.0.1"), \
             patch("src.api_server._get_service_uptime", return_value=3600), \
             patch("src.api_server._format_uptime", return_value="1h"), \
             patch("src.api_server.__version__", "1.0.0"), \
             patch("src.time_service.get_time_service") as mock_ts, \
             patch("src.api_server.text_to_board_array") as mock_ttba:
            bc = Mock()
            bc.send_characters.return_value = (False, False)
            mock_bc.return_value = bc
            ss = Mock()
            ss.should_send_to_board.return_value = True
            mock_ss.return_value = ss
            mock_config.BOARD_HOST = "192.168.1.1"
            mock_config.BOARD_API_MODE = "LOCAL"
            mock_ttba.return_value = [[0] * 22 for _ in range(6)]

            ts = Mock()
            ts.get_current_time.return_value = Mock(strftime=Mock(return_value="12:00"))
            mock_ts.return_value = ts

            response = client.post("/debug/info")
            assert response.status_code == 500

    def test_info_exception(self, client):
        """Exception during send → 500."""
        with patch("src.api_server._get_board_client") as mock_bc, \
             patch("src.api_server.get_settings_service") as mock_ss, \
             patch("src.api_server.Config") as mock_config, \
             patch("src.api_server._get_server_ip", return_value="10.0.0.1"), \
             patch("src.api_server._get_service_uptime", return_value=3600), \
             patch("src.api_server._format_uptime", return_value="1h"), \
             patch("src.api_server.__version__", "1.0.0"), \
             patch("src.time_service.get_time_service") as mock_ts, \
             patch("src.api_server.text_to_board_array") as mock_ttba:
            bc = Mock()
            bc.send_characters.side_effect = Exception("error")
            mock_bc.return_value = bc
            ss = Mock()
            ss.should_send_to_board.return_value = True
            mock_ss.return_value = ss
            mock_config.BOARD_HOST = "192.168.1.1"
            mock_config.BOARD_API_MODE = "LOCAL"
            mock_ttba.return_value = [[0] * 22 for _ in range(6)]

            ts = Mock()
            ts.get_current_time.return_value = Mock(strftime=Mock(return_value="12:00"))
            mock_ts.return_value = ts

            response = client.post("/debug/info")
            assert response.status_code == 500


class TestDebugTestConnectionErrorPaths:
    """Additional tests for POST /debug/test-connection."""

    def test_connection_failed(self, client):
        """Connection test returns disconnected."""
        with patch("src.api_server._get_board_client") as mock_bc:
            bc = Mock()
            bc.test_connection.return_value = False
            mock_bc.return_value = bc
            response = client.post("/debug/test-connection")
            data = response.json()
            assert data["connected"] is False
            assert data["status"] == "error"

    def test_connection_exception(self, client):
        """Exception during connection test."""
        with patch("src.api_server._get_board_client") as mock_bc:
            bc = Mock()
            bc.test_connection.side_effect = RuntimeError("timeout")
            mock_bc.return_value = bc
            response = client.post("/debug/test-connection")
            data = response.json()
            assert data["connected"] is False
            # Generic message — exception details are logged, not leaked.
            assert data["status"] == "error"
            assert data["message"]


class TestDebugClearCacheErrorPaths:
    """Additional tests for POST /debug/clear-cache."""

    def test_clear_cache_exception(self, client):
        """Exception during cache clear → 500."""
        with patch("src.api_server._get_board_client") as mock_bc:
            bc = Mock()
            bc.clear_cache.side_effect = RuntimeError("err")
            mock_bc.return_value = bc
            response = client.post("/debug/clear-cache")
            assert response.status_code == 500


class TestDebugCacheStatusErrorPaths:
    """Additional tests for GET /debug/cache-status."""

    def test_cache_status_exception(self, client):
        """Exception during cache status → 500."""
        with patch("src.api_server._get_board_client") as mock_bc:
            bc = Mock()
            bc.get_cache_status.side_effect = RuntimeError("err")
            mock_bc.return_value = bc
            response = client.get("/debug/cache-status")
            assert response.status_code == 500


# ===========================================================================
# Priority 7 – Plugin System
# ===========================================================================

class TestPluginErrors:
    """Tests for GET /plugins/errors."""

    def test_plugin_errors_system_available(self, client):
        """Plugin errors when system is available."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry") as mock_reg:
            registry = Mock()
            registry.get_load_errors.return_value = {"bad_plugin": "ImportError"}
            mock_reg.return_value = registry
            response = client.get("/plugins/errors")
            assert response.status_code == 200
            data = response.json()
            assert data["plugin_system_enabled"] is True
            assert "bad_plugin" in data["errors"]

    def test_plugin_errors_system_unavailable(self, client):
        """Plugin errors when system is unavailable."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            response = client.get("/plugins/errors")
            assert response.status_code == 200
            data = response.json()
            assert data["plugin_system_enabled"] is False
            assert data["errors"] == {}


class TestPluginRegistry:
    """Tests for GET /plugins/registry."""

    def test_registry_list(self, client):
        """List registry plugins."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry") as mock_reg:
            registry = Mock()
            registry.get_registry_entries.return_value = [
                {"id": "weather", "name": "Weather", "installed": True}
            ]
            mock_reg.return_value = registry
            response = client.get("/plugins/registry")
            assert response.status_code == 200
            assert len(response.json()["entries"]) == 1

    def test_registry_unavailable(self, client):
        """Plugin system unavailable → 503."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            response = client.get("/plugins/registry")
            assert response.status_code == 503


class TestPluginUpdates:
    """Tests for GET /plugins/updates."""

    def test_get_updates(self, client):
        """Get cached update status."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry") as mock_reg:
            registry = Mock()
            registry.get_update_status.return_value = {"my_plugin": True}
            mock_reg.return_value = registry
            response = client.get("/plugins/updates")
            assert response.status_code == 200
            assert response.json()["updates"]["my_plugin"] is True

    def test_get_updates_unavailable(self, client):
        """Plugin system unavailable → 503."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            response = client.get("/plugins/updates")
            assert response.status_code == 503


class TestTriggerPluginUpdateCheck:
    """Tests for POST /plugins/updates/check."""

    def test_trigger_check(self, client):
        """Trigger update check."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry") as mock_reg:
            registry = Mock()
            registry.check_for_updates.return_value = {"plugin_a": True, "plugin_b": False}
            mock_reg.return_value = registry
            response = client.post("/plugins/updates/check")
            assert response.status_code == 200
            data = response.json()
            assert data["checked"] == 2
            assert "plugin_a" in data["updates_available"]
            assert "plugin_b" not in data["updates_available"]

    def test_trigger_check_unavailable(self, client):
        """Plugin system unavailable → 503."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            response = client.post("/plugins/updates/check")
            assert response.status_code == 503


# ===========================================================================
# Priority 8 – External Data APIs
# ===========================================================================

class TestStocksSearch:
    """Tests for GET /stocks/search."""

    def test_search_success(self, client):
        """Search stock symbols successfully."""
        with patch("src.utils.stocks.StocksSource") as MockStocks, \
             patch("src.api_server.Config") as mock_config:
            mock_config.FINNHUB_API_KEY = "test_finnhub_key"
            MockStocks.search_symbols.return_value = [
                {"symbol": "GOOG", "name": "Alphabet Inc."}
            ]
            response = client.get("/stocks/search?query=GOOG")
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert data["symbols"][0]["symbol"] == "GOOG"

    def test_search_no_api_key(self, client):
        """Search without API key uses fallback."""
        with patch("src.utils.stocks.StocksSource") as MockStocks, \
             patch("src.api_server.Config") as mock_config:
            mock_config.FINNHUB_API_KEY = None
            MockStocks.search_symbols.return_value = []
            response = client.get("/stocks/search?query=XYZ&limit=5")
            assert response.status_code == 200
            assert response.json()["count"] == 0

    def test_search_exception(self, client):
        """Exception during search → 500."""
        with patch("src.utils.stocks.StocksSource") as MockStocks, \
             patch("src.api_server.Config") as mock_config:
            mock_config.FINNHUB_API_KEY = None
            MockStocks.search_symbols.side_effect = RuntimeError("API down")
            response = client.get("/stocks/search?query=GOOG")
            assert response.status_code == 500


class TestStocksValidate:
    """Tests for POST /stocks/validate."""

    def test_validate_missing_symbol(self, client):
        """Missing symbol → 400."""
        response = client.post("/stocks/validate", json={})
        assert response.status_code == 400

    def test_validate_success(self, client):
        """Valid symbol returns result."""
        with patch("src.utils.stocks.StocksSource") as MockStocks:
            MockStocks.validate_symbol.return_value = {
                "valid": True,
                "symbol": "AAPL",
                "name": "Apple Inc.",
            }
            response = client.post("/stocks/validate", json={"symbol": "AAPL"})
            assert response.status_code == 200
            assert response.json()["valid"] is True

    def test_validate_exception(self, client):
        """Exception during validation → 500."""
        with patch("src.utils.stocks.StocksSource") as MockStocks:
            MockStocks.validate_symbol.side_effect = RuntimeError("err")
            response = client.post("/stocks/validate", json={"symbol": "BAD"})
            assert response.status_code == 500


class TestTransitCacheStatus:
    """Tests for GET /transit/cache/status."""

    def test_cache_status_success(self, client):
        """Get transit cache status successfully."""
        with patch("src.utils.transit_cache.get_transit_cache") as mock_cache:
            cache = Mock()
            cache.get_status.return_value = {
                "last_refresh": 1700000000,
                "last_success": 1700000000,
                "agencies": 5,
                "stops": 100,
                "refresh_count": 10,
                "error_count": 0,
                "is_stale": False,
            }
            mock_cache.return_value = cache
            response = client.get("/transit/cache/status")
            assert response.status_code == 200
            data = response.json()
            assert data["agencies"] == 5
            assert data["last_refresh_iso"] is not None

    def test_cache_status_no_refresh(self, client):
        """Cache never refreshed returns null timestamps."""
        with patch("src.utils.transit_cache.get_transit_cache") as mock_cache:
            cache = Mock()
            cache.get_status.return_value = {
                "last_refresh": 0,
                "last_success": 0,
                "agencies": 0,
                "stops": 0,
                "refresh_count": 0,
                "error_count": 0,
                "is_stale": True,
            }
            mock_cache.return_value = cache
            response = client.get("/transit/cache/status")
            assert response.status_code == 200
            data = response.json()
            assert data["last_refresh_iso"] is None
            assert data["last_success_iso"] is None

    def test_cache_status_exception(self, client):
        """Exception → 500."""
        with patch("src.utils.transit_cache.get_transit_cache") as mock_cache:
            mock_cache.side_effect = RuntimeError("no cache")
            response = client.get("/transit/cache/status")
            assert response.status_code == 500
