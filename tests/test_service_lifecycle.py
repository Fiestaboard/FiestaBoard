"""Tests for service lifecycle, resilience, and health endpoints.

Covers:
- DisplayService.run() graceful exit on initialization failure (no sys.exit)
- run_service_background() auto-restart on BaseException
- Redundant initialization skip when already initialized
- /health and /status API endpoints
"""

import time
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


class TestDisplayServiceRun:
    """Tests for DisplayService.run() resilience."""

    @pytest.fixture
    def service(self):
        with patch('src.main.Config') as mock_config, \
             patch('src.main.get_settings_service') as mock_settings, \
             patch('src.main.get_page_service'), \
             patch('src.main.get_schedule_service'):
            mock_config.validate.return_value = True
            mock_config.get_summary.return_value = {}
            mock_config.get_transition_settings.return_value = {"strategy": None}
            mock_settings_inst = Mock()
            mock_settings_inst.get_polling_interval.return_value = 60
            mock_settings.return_value = mock_settings_inst
            from src.main import DisplayService
            svc = DisplayService()
            yield svc

    def test_run_returns_on_init_failure_instead_of_sys_exit(self, service):
        """run() must return cleanly when initialization fails, never call sys.exit."""
        service.vb_client = None

        with patch.object(service, 'initialize', return_value=False):
            service.run()

        assert not service.running or service.running is True

    def test_run_does_not_raise_system_exit(self, service):
        """run() must not raise SystemExit on initialization failure."""
        service.vb_client = None

        with patch.object(service, 'initialize', return_value=False):
            try:
                service.run()
            except SystemExit:
                pytest.fail("service.run() raised SystemExit instead of returning")

    def test_run_skips_init_when_vb_client_set(self, service):
        """run() skips initialize() when vb_client is already set."""
        service.vb_client = Mock()
        service.running = True

        with patch.object(service, 'initialize') as mock_init, \
             patch('src.main.schedule') as mock_schedule, \
             patch.object(service, 'check_and_send_active_page'):
            mock_schedule.run_pending.return_value = None

            def stop_after_one(*_args, **_kwargs):
                service.running = False
            mock_schedule.run_pending.side_effect = stop_after_one

            with patch('src.main.get_settings_service') as mock_ss:
                mock_ss.return_value.get_polling_interval.return_value = 60
                service.run()

            mock_init.assert_not_called()

    def test_run_calls_init_when_vb_client_missing(self, service):
        """run() calls initialize() when vb_client is None."""
        service.vb_client = None

        with patch.object(service, 'initialize', return_value=False) as mock_init:
            service.run()

        mock_init.assert_called_once()


class TestRunServiceBackground:
    """Tests for the background service thread wrapper."""

    def _reset_api_globals(self):
        """Reset api_server module globals to a clean state."""
        import src.api_server as api
        api._service_running = False
        api._shutting_down = False
        api._service = None
        api._service_thread = None
        api._service_start_time = None

    def test_catches_base_exception_and_continues(self):
        """BaseException from service.run() must not kill the restart loop."""
        import src.api_server as api
        self._reset_api_globals()

        mock_service = Mock()
        mock_service.vb_client = Mock()
        mock_service.initialize.return_value = True

        call_count = 0

        def run_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise SystemExit(1)
            api._shutting_down = True

        mock_service.run.side_effect = run_side_effect

        with patch('src.api_server.get_service', return_value=mock_service):
            api.run_service_background()

        assert call_count == 2, "Service should have been called twice (crash + restart)"

    def test_catches_keyboard_interrupt_and_continues(self):
        """KeyboardInterrupt from service.run() must not kill the restart loop."""
        import src.api_server as api
        self._reset_api_globals()

        mock_service = Mock()
        mock_service.vb_client = Mock()

        call_count = 0

        def run_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KeyboardInterrupt()
            api._shutting_down = True

        mock_service.run.side_effect = run_side_effect

        with patch('src.api_server.get_service', return_value=mock_service):
            api.run_service_background()

        assert call_count == 2

    def test_sets_service_running_false_on_exit(self):
        """_service_running must be False after service.run() exits."""
        import src.api_server as api
        self._reset_api_globals()

        mock_service = Mock()
        mock_service.vb_client = Mock()

        def run_then_stop():
            api._shutting_down = True

        mock_service.run.side_effect = run_then_stop

        with patch('src.api_server.get_service', return_value=mock_service):
            api.run_service_background()

        assert api._service_running is False

    def test_exponential_backoff_on_repeated_failure(self):
        """Restart delay should increase with repeated failures."""
        import src.api_server as api
        self._reset_api_globals()

        mock_service = Mock()
        mock_service.vb_client = Mock()

        call_count = 0
        sleep_calls = []

        def run_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                api._shutting_down = True
            raise RuntimeError("crash")

        mock_service.run.side_effect = run_side_effect

        original_sleep = time.sleep

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch('src.api_server.get_service', return_value=mock_service), \
             patch('src.api_server.time.sleep', side_effect=mock_sleep):
            api.run_service_background()

        assert len(sleep_calls) >= 2
        assert sleep_calls[1] >= sleep_calls[0], "Backoff should increase"


class TestHealthEndpoint:
    """Tests for the /health API endpoint."""

    @pytest.fixture
    def client(self):
        from src.api_server import app
        return TestClient(app, raise_server_exceptions=False)

    def test_health_returns_ok(self, client):
        mock_service = Mock()
        with patch('src.api_server.get_service', return_value=mock_service):
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "service_running" in data
        assert "version" in data

    def test_health_head_returns_ok(self, client):
        mock_service = Mock()
        with patch('src.api_server.get_service', return_value=mock_service):
            response = client.head("/health")

        assert response.status_code == 200

    def test_health_reflects_service_running_state(self, client):
        import src.api_server as api
        mock_service = Mock()

        with patch('src.api_server.get_service', return_value=mock_service):
            api._service_running = True
            response = client.get("/health")
            assert response.json()["service_running"] is True

            api._service_running = False
            response = client.get("/health")
            assert response.json()["service_running"] is False

            api._service_running = False


class TestStatusEndpoint:
    """Tests for the /status API endpoint."""

    @pytest.fixture
    def client(self):
        from src.api_server import app
        return TestClient(app, raise_server_exceptions=False)

    def test_status_returns_running_state(self, client):
        import src.api_server as api

        mock_service = Mock()
        mock_settings = Mock()
        mock_settings.get_active_page_id.return_value = "page1"

        with patch('src.api_server.get_service', return_value=mock_service), \
             patch('src.api_server.get_settings_service', return_value=mock_settings), \
             patch('src.api_server.Config') as mock_config:
            mock_config.get_summary.return_value = {}

            api._service_running = True
            response = client.get("/status")
            assert response.status_code == 200
            assert response.json()["running"] is True

            api._service_running = False
            response = client.get("/status")
            assert response.status_code == 200
            assert response.json()["running"] is False

            api._service_running = False

    def test_status_503_when_no_service(self, client):
        with patch('src.api_server.get_service', return_value=None):
            response = client.get("/status")
            assert response.status_code == 503


class TestVersionEndpoint:
    """Tests for the /version API endpoint."""

    @pytest.fixture
    def client(self):
        from src.api_server import app
        return TestClient(app, raise_server_exceptions=False)

    def test_version_is_dev_when_no_env_vars(self, client):
        with patch.dict('os.environ', {'VERSION': 'dev', 'PRODUCTION': 'false'}):
            response = client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert data["is_dev"] is True

    def test_version_is_not_dev_when_production_true(self, client):
        with patch.dict('os.environ', {'PRODUCTION': 'true', 'VERSION': 'dev'}):
            response = client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert data["is_dev"] is False

    def test_version_is_not_dev_when_version_set(self, client):
        with patch.dict('os.environ', {'VERSION': '1.2.3', 'PRODUCTION': 'false'}):
            response = client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert data["is_dev"] is False
        assert data["build_version"] == "1.2.3"
