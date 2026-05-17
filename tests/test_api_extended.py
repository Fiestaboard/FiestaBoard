"""Extended tests for api_server.py to increase coverage.

Covers config endpoints, plugin endpoints, template endpoints, settings endpoints,
pages endpoints, schedule endpoints, cache, service lifecycle, and error paths.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from src.api_server import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_config_manager():
    """Mock the config manager."""
    with patch("src.api_server.get_config_manager") as mock_get:
        cm = Mock()
        cm.get_all_masked.return_value = {"board": {}, "general": {}}
        cm.get_board.return_value = {
            "api_mode": "local",
            "local_api_key": "test_key",
            "host": "192.168.1.100",
        }
        cm._mask_sensitive.side_effect = lambda d: d
        cm.validate.return_value = (True, [])
        cm.get_general.return_value = {"timezone": "UTC", "refresh_interval_seconds": 60}
        cm.set_general.return_value = True
        cm.get_feature.return_value = {"enabled": False, "start_time": "20:00+00:00", "end_time": "07:00+00:00"}
        cm.get_plugin_config.return_value = {"enabled": True}
        cm.set_plugin_config.return_value = None
        cm.enable_plugin.return_value = None
        cm.disable_plugin.return_value = None
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
        transition.to_dict.return_value = {"strategy": "column", "step_interval_ms": 100, "step_size": 1}
        ss.get_transition_settings.return_value = transition

        output = Mock()
        output.target = "ui"
        output.to_dict.return_value = {"target": "ui"}
        ss.get_output_settings.return_value = output

        board_settings = Mock()
        board_settings.boards = [{"id": "b1", "device_type": "flagship"}]
        board_settings.to_dict.return_value = {"board_type": "black", "boards": [{"id": "b1", "device_type": "flagship"}]}
        ss.get_board_settings.return_value = board_settings

        polling = Mock()
        polling.interval_seconds = 60
        polling.board_read_interval_local = 30
        polling.board_read_interval_cloud = 180
        polling.to_dict.return_value = {
            "interval_seconds": 60,
            "board_read_interval_local": 30,
            "board_read_interval_cloud": 180,
        }
        ss.get_polling_settings.return_value = polling

        ss.get_active_page_id.return_value = "page1"
        ss.should_send_to_board.return_value = False
        ss.is_schedule_enabled.return_value = False
        ss.set_output_target.return_value = output
        ss.set_polling_interval.return_value = polling
        ss.set_board_read_intervals.return_value = polling
        ss.set_board_type.return_value = board_settings
        ss.set_devices.return_value = board_settings
        ss.set_boards.return_value = board_settings
        ss.add_board.return_value = board_settings
        ss.remove_board.return_value = board_settings
        ss.update_transition_settings.return_value = transition

        mqtt = Mock()
        mqtt.enabled = False
        mqtt.broker_host = "localhost"
        mqtt.broker_port = 1883
        mqtt.username = ""
        mqtt.password = ""
        mqtt.external_url = ""
        mqtt.to_dict.return_value = {
            "enabled": False,
            "broker_host": "localhost",
            "broker_port": 1883,
            "username": "",
            "password": "",
            "external_url": "",
        }
        ss.get_mqtt_settings.return_value = mqtt

        display = Mock()
        display.to_dict.return_value = {"reduce_motion": False}
        ss.get_display_settings.return_value = display

        location = Mock()
        location.latitude = None
        location.longitude = None
        location.to_dict.return_value = {"latitude": None, "longitude": None}
        ss.get_location_settings.return_value = location

        beta = Mock()
        beta.https_enabled = False
        beta.to_dict.return_value = {"https_enabled": False}
        ss.get_beta_settings.return_value = beta
        ss.update_beta_settings.return_value = beta

        plugin_settings = Mock()
        plugin_settings.to_dict.return_value = {"auto_update": True}
        ss.get_plugin_settings.return_value = plugin_settings
        ss.update_plugin_settings.return_value = plugin_settings

        mock_get.return_value = ss
        yield ss


@pytest.fixture
def mock_page_service():
    """Mock the page service."""
    with patch("src.api_server.get_page_service") as mock_get:
        ps = Mock()
        mock_page = Mock()
        mock_page.model_dump.return_value = {
            "id": "page1",
            "name": "Test Page",
            "type": "template",
            "template": ["Hello"],
            "device_type": "flagship",
        }
        mock_page.transition_strategy = None
        mock_page.transition_interval_ms = None
        mock_page.transition_step_size = None
        mock_page.device_type = "flagship"

        ps.list_pages.return_value = [mock_page]
        ps.get_page.return_value = mock_page
        ps.create_page.return_value = mock_page
        ps.update_page.return_value = mock_page

        delete_result = Mock()
        delete_result.deleted = True
        delete_result.default_page_created = False
        delete_result.active_page_updated = False
        delete_result.new_page_id = None
        delete_result.new_active_page_id = None
        ps.delete_page.return_value = delete_result

        preview_result = Mock()
        preview_result.available = True
        preview_result.formatted = "Hello World"
        preview_result.display_type = "template"
        preview_result.raw = {}
        preview_result.error = None
        ps.preview_page.return_value = preview_result

        # Batch preview returns a dict mapping page_id to DisplayResult
        ps.preview_pages_batch.return_value = {"page1": preview_result}

        ps.get_cache_stats.return_value = {"size": 0, "cached_pages": [], "ttl_seconds": 30}
        ps._invalidate_cache.return_value = None

        mock_get.return_value = ps
        yield ps


@pytest.fixture
def mock_schedule_service():
    """Mock the schedule service."""
    with patch("src.api_server.get_schedule_service") as mock_get:
        ss = Mock()
        mock_schedule = Mock()
        mock_schedule.model_dump.return_value = {
            "id": "sched1",
            "page_id": "page1",
            "start_time": "09:00",
            "end_time": "17:00",
            "days": ["monday"],
        }
        ss.list_schedules.return_value = [mock_schedule]
        ss.get_schedule.return_value = mock_schedule
        ss.create_schedule.return_value = mock_schedule
        ss.update_schedule.return_value = mock_schedule
        ss.delete_schedule.return_value = True
        ss.get_default_page.return_value = "page1"
        ss.get_active_page_id.return_value = "page1"
        validate_result = Mock()
        validate_result.model_dump.return_value = {"valid": True, "errors": [], "warnings": []}
        ss.validate_schedules.return_value = validate_result

        mock_get.return_value = ss
        yield ss


@pytest.fixture
def mock_display_service():
    """Mock the display service."""
    with patch("src.api_server.get_display_service") as mock_get:
        ds = Mock()
        ds.get_available_displays.return_value = [
            {"type": "weather", "available": True, "description": "Weather", "source": "plugin"},
        ]
        from src.displays.service import DisplayResult
        ds.get_display.return_value = DisplayResult(
            display_type="weather",
            formatted="Sunny 72F",
            raw={"temp": 72},
            available=True,
        )
        mock_get.return_value = ds
        yield ds


@pytest.fixture
def mock_template_engine():
    """Mock the template engine."""
    with patch("src.api_server.get_template_engine") as mock_get:
        te = Mock()
        te.get_available_variables.return_value = {"weather": ["temperature", "condition"]}
        te.get_variable_max_lengths.return_value = {"weather": {"temperature": 5}}
        te.validate_template.return_value = []
        te.render.return_value = "Rendered output"
        te.render_lines.return_value = "Rendered lines"
        mock_get.return_value = te
        yield te


@pytest.fixture
def mock_plugin_registry():
    """Mock the plugin registry."""
    with patch("src.api_server.get_plugin_registry") as mock_get, \
         patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True):
        reg = Mock()
        reg.list_plugins.return_value = [
            {"id": "weather", "name": "Weather", "enabled": True},
        ]
        manifest = Mock()
        manifest.name = "Weather"
        manifest.version = "1.0.0"
        manifest.description = "Weather plugin"
        manifest.author = "Test"
        manifest.icon = "cloud"
        manifest.category = "weather"
        manifest.settings_schema = {}
        manifest.raw = {"variables": {"temperature": "number"}}
        manifest.max_lengths = {"temperature": 5}
        manifest.env_vars = []
        manifest.documentation = ""
        reg.get_manifest.return_value = manifest
        reg.get_plugin.return_value = Mock()
        reg.is_enabled.return_value = True
        reg.parse_instance_key.return_value = ("weather", None)
        reg.list_instances.return_value = []
        reg.enable_plugin.return_value = True
        reg.disable_plugin.return_value = True
        reg.set_plugin_config.return_value = []
        from src.plugins.base import PluginResult
        reg.fetch_plugin_data.return_value = PluginResult(
            available=True,
            data={"temperature": 72},
            formatted_lines=["72F"],
        )
        reg.get_all_variables.return_value = {"weather": {"temperature": "number"}}
        reg.get_all_max_lengths.return_value = {"weather": {"temperature": 5}}
        reg.get_load_errors.return_value = {}
        mock_get.return_value = reg
        yield reg


@pytest.fixture
def mock_service():
    """Mock the global service."""
    with patch("src.api_server.get_service") as mock_get:
        svc = Mock()
        svc.vb_client = Mock()
        svc.vb_client.send_characters.return_value = (True, True)
        svc.vb_client.get_cache_status.return_value = {"has_cached_text": False}
        svc.vb_client.clear_cache.return_value = None
        svc.vb_client.use_cloud = False
        svc.vb_client._last_characters = None
        svc.running = True
        svc.initialize.return_value = True
        # Board-state poll cache starts empty so tests hit the live-call fallback
        svc._polled_characters = None
        svc._polled_at = None
        mock_get.return_value = svc
        yield svc


# ============================================================
# Root / Health / Version / Status
# ============================================================

class TestRootAndHealth:
    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "FiestaBoard Display API"

    def test_health_get(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_head(self, client):
        response = client.head("/health")
        assert response.status_code == 200

    def test_version(self, client):
        response = client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert "package_version" in data
        assert "build_version" in data
        assert "is_dev" in data

    def test_status_success(self, client, mock_service, mock_settings_service):
        with patch("src.api_server._service_running", True):
            response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "config_summary" in data

    def test_status_no_service(self, client):
        with patch("src.api_server.get_service", return_value=None):
            response = client.get("/status")
        assert response.status_code == 503


# ============================================================
# Config Endpoints
# ============================================================

class TestConfigEndpoints:
    def test_get_config(self, client):
        response = client.get("/config")
        assert response.status_code == 200

    def test_get_full_config(self, client, mock_config_manager):
        response = client.get("/config/full")
        assert response.status_code == 200
        mock_config_manager.get_all_masked.assert_called_once()

    def test_get_board_config(self, client, mock_config_manager):
        response = client.get("/config/board")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert "api_modes" in data

    def test_update_board_config(self, client, mock_config_manager, mock_service):
        response = client.put("/config/board", json={"api_mode": "local", "host": "10.0.0.1"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        mock_config_manager.set_board.assert_called_once()

    def test_validate_config_valid(self, client, mock_config_manager):
        response = client.get("/config/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_validate_config_first_run(self, client, mock_config_manager, mock_settings_service):
        mock_config_manager.get_board.return_value = {"api_mode": "local", "local_api_key": "", "host": ""}
        response = client.get("/config/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["is_first_run"] is True

    def test_validate_config_cloud_missing_key(self, client, mock_config_manager, mock_settings_service):
        mock_config_manager.get_board.return_value = {"api_mode": "cloud", "cloud_key": ""}
        response = client.get("/config/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["is_first_run"] is True
        assert "board.cloud_key" in data["missing_fields"]

    def test_get_general_config(self, client, mock_config_manager):
        response = client.get("/config/general")
        assert response.status_code == 200
        data = response.json()
        assert "timezone" in data

    def test_update_general_config(self, client, mock_config_manager):
        response = client.put("/config/general", json={"timezone": "America/New_York"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_update_general_config_failure(self, client, mock_config_manager):
        mock_config_manager.set_general.return_value = False
        response = client.put("/config/general", json={"timezone": "Invalid/TZ"})
        assert response.status_code == 500


class TestBoardConnectionTest:
    def test_test_board_local_missing_key(self, client):
        response = client.post("/config/board/test", json={
            "api_mode": "local",
            "host": "192.168.1.100",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "API key is required" in data["message"]

    def test_test_board_local_missing_host(self, client):
        response = client.post("/config/board/test", json={
            "api_mode": "local",
            "local_api_key": "test_key_123",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "host" in data["message"].lower()

    def test_test_board_cloud_missing_key(self, client):
        response = client.post("/config/board/test", json={
            "api_mode": "cloud",
        })
        assert response.status_code == 200
        assert response.json()["success"] is False


# ============================================================
# Settings Endpoints
# ============================================================

class TestSettingsEndpoints:
    def test_get_transition_settings(self, client, mock_settings_service):
        response = client.get("/settings/transitions")
        assert response.status_code == 200
        data = response.json()
        assert "strategy" in data
        assert "available_strategies" in data

    def test_update_transition_settings(self, client, mock_settings_service):
        response = client.put("/settings/transitions", json={"strategy": "column"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_update_transition_settings_invalid(self, client, mock_settings_service):
        mock_settings_service.update_transition_settings.side_effect = ValueError("Invalid strategy")
        response = client.put("/settings/transitions", json={"strategy": "bad_strategy"})
        assert response.status_code == 400

    def test_get_output_settings(self, client, mock_settings_service):
        response = client.get("/settings/output")
        assert response.status_code == 200
        data = response.json()
        assert "target" in data
        assert "available_targets" in data

    def test_update_output_settings(self, client, mock_settings_service):
        response = client.put("/settings/output", json={"target": "board"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_update_output_settings_missing_target(self, client, mock_settings_service):
        response = client.put("/settings/output", json={})
        assert response.status_code == 400

    def test_update_output_settings_invalid_target(self, client, mock_settings_service):
        mock_settings_service.set_output_target.side_effect = ValueError("Invalid target")
        response = client.put("/settings/output", json={"target": "invalid"})
        assert response.status_code == 400

    def test_get_active_page(self, client, mock_settings_service):
        response = client.get("/settings/active-page")
        assert response.status_code == 200
        assert response.json()["page_id"] == "page1"

    def test_set_active_page(self, client, mock_settings_service, mock_page_service):
        response = client.put("/settings/active-page", json={"page_id": "page1"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_set_active_page_not_found(self, client, mock_settings_service, mock_page_service):
        mock_page_service.get_page.return_value = None
        response = client.put("/settings/active-page", json={"page_id": "nonexistent"})
        assert response.status_code == 404

    def test_set_active_page_null(self, client, mock_settings_service, mock_page_service):
        response = client.put("/settings/active-page", json={"page_id": None})
        assert response.status_code == 200

    def test_get_polling_settings(self, client, mock_settings_service):
        response = client.get("/settings/polling")
        assert response.status_code == 200
        data = response.json()
        assert data["interval_seconds"] == 60
        assert data["board_read_interval_local"] == 30
        assert data["board_read_interval_cloud"] == 180

    def test_update_polling_interval_seconds(self, client, mock_settings_service):
        response = client.put("/settings/polling", json={"interval_seconds": 120})
        assert response.status_code == 200
        assert response.json()["requires_restart"] is True

    def test_update_polling_board_read_local(self, client, mock_settings_service):
        response = client.put("/settings/polling", json={"board_read_interval_local": 45})
        assert response.status_code == 200
        assert response.json()["requires_restart"] is False
        mock_settings_service.set_board_read_intervals.assert_called_once_with(local_seconds=45, cloud_seconds=None)

    def test_update_polling_board_read_cloud(self, client, mock_settings_service):
        response = client.put("/settings/polling", json={"board_read_interval_cloud": 300})
        assert response.status_code == 200
        assert response.json()["requires_restart"] is False
        mock_settings_service.set_board_read_intervals.assert_called_once_with(local_seconds=None, cloud_seconds=300)

    def test_update_polling_empty_body_is_noop(self, client, mock_settings_service):
        """Empty body is valid — returns current settings without modifying anything."""
        response = client.put("/settings/polling", json={})
        assert response.status_code == 200
        assert response.json()["requires_restart"] is False
        mock_settings_service.set_polling_interval.assert_not_called()
        mock_settings_service.set_board_read_intervals.assert_not_called()

    def test_update_polling_invalid_value(self, client, mock_settings_service):
        mock_settings_service.set_polling_interval.side_effect = ValueError("Must be >= 10")
        response = client.put("/settings/polling", json={"interval_seconds": 1})
        assert response.status_code == 400

    def test_update_polling_board_read_invalid_value(self, client, mock_settings_service):
        mock_settings_service.set_board_read_intervals.side_effect = ValueError("Must be >= 20")
        response = client.put("/settings/polling", json={"board_read_interval_local": 5})
        assert response.status_code == 400

    def test_get_board_settings(self, client, mock_settings_service):
        response = client.get("/settings/board")
        assert response.status_code == 200

    def test_update_board_settings_type(self, client, mock_settings_service):
        response = client.put("/settings/board", json={"board_type": "white"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_update_board_settings_devices(self, client, mock_settings_service):
        response = client.put("/settings/board", json={"devices": ["flagship"]})
        assert response.status_code == 200

    def test_update_board_settings_devices_not_list(self, client, mock_settings_service):
        response = client.put("/settings/board", json={"devices": "flagship"})
        assert response.status_code == 400

    def test_update_board_settings_boards(self, client, mock_settings_service):
        response = client.put("/settings/board", json={"boards": [{"id": "b1", "device_type": "flagship"}]})
        assert response.status_code == 200

    def test_update_board_settings_boards_not_list(self, client, mock_settings_service):
        response = client.put("/settings/board", json={"boards": "bad"})
        assert response.status_code == 400

    def test_update_board_settings_no_param(self, client, mock_settings_service):
        response = client.put("/settings/board", json={"foo": "bar"})
        assert response.status_code == 400

    def test_update_board_settings_value_error(self, client, mock_settings_service):
        mock_settings_service.set_board_type.side_effect = ValueError("Invalid type")
        response = client.put("/settings/board", json={"board_type": "bad"})
        assert response.status_code == 400

    def test_add_board_instance(self, client, mock_settings_service):
        response = client.post("/settings/board/add", json={"device_type": "flagship"})
        assert response.status_code == 200

    def test_add_board_instance_missing_type(self, client, mock_settings_service):
        response = client.post("/settings/board/add", json={})
        assert response.status_code == 400

    def test_add_board_instance_value_error(self, client, mock_settings_service):
        mock_settings_service.add_board.side_effect = ValueError("Invalid")
        response = client.post("/settings/board/add", json={"device_type": "bad"})
        assert response.status_code == 400

    def test_remove_board_instance(self, client, mock_settings_service):
        response = client.delete("/settings/board/b1")
        assert response.status_code == 200

    def test_remove_board_instance_not_found(self, client, mock_settings_service):
        mock_settings_service.remove_board.side_effect = ValueError("Not found")
        response = client.delete("/settings/board/nonexistent")
        assert response.status_code == 400

    def test_get_all_settings(self, client, mock_settings_service, mock_config_manager):
        with patch("src.api_server._service_running", True):
            response = client.get("/settings/all")
        assert response.status_code == 200
        data = response.json()
        assert "general" in data
        assert "polling" in data
        assert "transitions" in data
        assert "output" in data
        assert "board" in data
        assert "mqtt" in data
        assert "display" in data
        assert data["display"] == {"reduce_motion": False}
        assert "status" in data


# ============================================================
# Plugin Endpoints
# ============================================================

class TestPluginEndpoints:
    def test_list_plugins(self, client, mock_plugin_registry, mock_config_manager):
        response = client.get("/plugins")
        assert response.status_code == 200
        data = response.json()
        assert "plugins" in data
        assert data["plugin_system_enabled"] is True

    def test_list_plugins_system_unavailable(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            response = client.get("/plugins")
        assert response.status_code == 503

    def test_get_plugin(self, client, mock_plugin_registry, mock_config_manager):
        response = client.get("/plugins/weather")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "weather"
        assert data["name"] == "Weather"

    def test_get_plugin_not_found(self, client, mock_plugin_registry, mock_config_manager):
        mock_plugin_registry.get_manifest.return_value = None
        response = client.get("/plugins/nonexistent")
        assert response.status_code == 404

    def test_get_plugin_manifest(self, client, mock_plugin_registry):
        response = client.get("/plugins/weather/manifest")
        assert response.status_code == 200

    def test_get_plugin_manifest_not_found(self, client, mock_plugin_registry):
        mock_plugin_registry.get_manifest.return_value = None
        response = client.get("/plugins/nonexistent/manifest")
        assert response.status_code == 404

    def test_update_plugin_config(self, client, mock_plugin_registry, mock_config_manager):
        with patch("src.api_server.reset_display_service"), \
             patch("src.api_server.reset_template_engine"):
            response = client.put("/plugins/weather/config", json={
                "config": {"api_key": "test_key_abc123"}
            })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_update_plugin_config_not_found(self, client, mock_plugin_registry, mock_config_manager):
        mock_plugin_registry.get_plugin.return_value = None
        response = client.put("/plugins/nonexistent/config", json={"config": {}})
        assert response.status_code == 404

    def test_update_plugin_config_validation_error(self, client, mock_plugin_registry, mock_config_manager):
        mock_plugin_registry.set_plugin_config.return_value = ["api_key is required"]
        response = client.put("/plugins/weather/config", json={"config": {}})
        assert response.status_code == 400

    def test_update_plugin_config_system_unavailable(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            response = client.put("/plugins/weather/config", json={"config": {}})
        assert response.status_code == 503

    def test_enable_plugin(self, client, mock_plugin_registry, mock_config_manager):
        with patch("src.api_server.reset_display_service"), \
             patch("src.api_server.reset_template_engine"):
            response = client.post("/plugins/weather/enable")
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_enable_plugin_not_found(self, client, mock_plugin_registry):
        mock_plugin_registry.get_plugin.return_value = None
        response = client.post("/plugins/nonexistent/enable")
        assert response.status_code == 404

    def test_enable_plugin_failure(self, client, mock_plugin_registry, mock_config_manager):
        mock_plugin_registry.enable_plugin.return_value = False
        response = client.post("/plugins/weather/enable")
        assert response.status_code == 400

    def test_disable_plugin(self, client, mock_plugin_registry, mock_config_manager):
        with patch("src.api_server.reset_display_service"), \
             patch("src.api_server.reset_template_engine"):
            response = client.post("/plugins/weather/disable")
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_disable_plugin_not_found(self, client, mock_plugin_registry):
        mock_plugin_registry.get_plugin.return_value = None
        response = client.post("/plugins/nonexistent/disable")
        assert response.status_code == 404

    def test_disable_plugin_failure(self, client, mock_plugin_registry, mock_config_manager):
        mock_plugin_registry.disable_plugin.return_value = False
        response = client.post("/plugins/weather/disable")
        assert response.status_code == 400

    def test_get_plugin_data_not_found(self, client, mock_plugin_registry):
        mock_plugin_registry.get_plugin.return_value = None
        response = client.get("/plugins/nonexistent/data")
        assert response.status_code == 404

    def test_get_plugin_data_not_enabled(self, client, mock_plugin_registry):
        mock_plugin_registry.is_enabled.return_value = False
        response = client.get("/plugins/weather/data")
        assert response.status_code == 400

    def test_get_plugin_variables(self, client, mock_plugin_registry):
        response = client.get("/plugins/weather/variables")
        assert response.status_code == 200
        data = response.json()
        assert "variables" in data
        assert "max_lengths" in data

    def test_get_plugin_variables_not_found(self, client, mock_plugin_registry):
        mock_plugin_registry.get_manifest.return_value = None
        response = client.get("/plugins/nonexistent/variables")
        assert response.status_code == 404

    def test_get_all_plugin_variables(self, client, mock_plugin_registry):
        response = client.get("/plugins/variables/all")
        assert response.status_code == 200
        data = response.json()
        assert data["plugin_system_enabled"] is True

    def test_get_all_plugin_variables_system_unavailable(self, client, mock_template_engine):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            response = client.get("/plugins/variables/all")
        assert response.status_code == 200
        data = response.json()
        assert data["plugin_system_enabled"] is False

    def test_receive_plugin_payload(self, client, mock_plugin_registry):
        response = client.post("/plugins/weather/receive", json={"message": "hello"})
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_plugin_registry.get_plugin.return_value.receive_payload.assert_called_once()

    def test_receive_plugin_payload_not_found(self, client, mock_plugin_registry):
        mock_plugin_registry.get_plugin.return_value = None
        response = client.post("/plugins/nonexistent/receive", json={"message": "hello"})
        assert response.status_code == 404

    def test_receive_plugin_payload_not_enabled(self, client, mock_plugin_registry):
        mock_plugin_registry.is_enabled.return_value = False
        response = client.post("/plugins/weather/receive", json={"message": "hello"})
        assert response.status_code == 400

    def test_receive_plugin_payload_invalid_json(self, client, mock_plugin_registry):
        response = client.post(
            "/plugins/weather/receive",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_receive_plugin_payload_not_supported(self, client, mock_plugin_registry):
        mock_plugin_registry.get_plugin.return_value.receive_payload.side_effect = NotImplementedError
        response = client.post("/plugins/weather/receive", json={"message": "hello"})
        assert response.status_code == 405

    def test_receive_plugin_payload_bad_signature(self, client, mock_plugin_registry):
        mock_plugin_registry.get_plugin.return_value.receive_payload.side_effect = PermissionError("Invalid signature")
        response = client.post("/plugins/weather/receive", json={"message": "hello"})
        assert response.status_code == 403

    def test_receive_plugin_payload_system_unavailable(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            response = client.post("/plugins/weather/receive", json={"message": "hello"})
        assert response.status_code == 503

# ============================================================
# Template Endpoints
# ============================================================

class TestTemplateEndpoints:
    def test_get_template_variables(self, client, mock_template_engine):
        response = client.get("/templates/variables")
        assert response.status_code == 200
        data = response.json()
        assert "variables" in data
        assert "colors" in data
        assert "symbols" in data
        assert "filters" in data

    def test_validate_template_valid(self, client, mock_template_engine):
        response = client.post("/templates/validate", json={"template": "Hello {{weather.temp}}"})
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_template_with_list(self, client, mock_template_engine):
        response = client.post("/templates/validate", json={"template": ["Line 1", "Line 2"]})
        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_validate_template_with_errors(self, client, mock_template_engine):
        error = Mock()
        error.line = 1
        error.column = 5
        error.message = "Unknown variable"
        mock_template_engine.validate_template.return_value = [error]
        response = client.post("/templates/validate", json={"template": "{{bad.var}}"})
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) == 1

    def test_validate_template_missing_param(self, client, mock_template_engine):
        response = client.post("/templates/validate", json={})
        assert response.status_code == 400

    def test_render_template_string(self, client, mock_template_engine):
        response = client.post("/templates/render", json={"template": "Hello"})
        assert response.status_code == 200
        data = response.json()
        assert "rendered" in data
        assert "lines" in data

    def test_render_template_list(self, client, mock_template_engine):
        response = client.post("/templates/render", json={"template": ["Line 1", "Line 2"]})
        assert response.status_code == 200

    def test_render_template_empty_string(self, client, mock_template_engine):
        response = client.post("/templates/render", json={"template": ""})
        assert response.status_code == 200
        data = response.json()
        assert data["line_count"] == 6

    def test_render_template_empty_list(self, client, mock_template_engine):
        response = client.post("/templates/render", json={"template": []})
        assert response.status_code == 200
        data = response.json()
        assert data["line_count"] == 6

    def test_render_template_whitespace_only_list(self, client, mock_template_engine):
        response = client.post("/templates/render", json={"template": ["  ", "  "]})
        assert response.status_code == 200
        data = response.json()
        assert data["line_count"] == 6

    def test_render_template_missing_param(self, client, mock_template_engine):
        response = client.post("/templates/render", json={})
        assert response.status_code == 400

    def test_render_template_error(self, client, mock_template_engine):
        mock_template_engine.render.side_effect = Exception("Render failed")
        response = client.post("/templates/render", json={"template": "{{bad}}"})
        assert response.status_code == 400

    def test_render_template_live_success(self, client, mock_template_engine, mock_settings_service):
        with patch("src.api_server.board_client_from_board_dict") as mock_bcfbd:
            mock_board_client = Mock()
            mock_board_client.send_characters.return_value = (True, True)
            mock_bcfbd.return_value = mock_board_client
            response = client.post("/templates/render/live", json={
                "template": "Hello World",
            })
        assert response.status_code == 200
        data = response.json()
        assert "rendered" in data
        assert "sent_to_board" in data

    def test_render_template_live_empty(self, client, mock_template_engine, mock_settings_service):
        response = client.post("/templates/render/live", json={"template": ""})
        assert response.status_code == 200
        data = response.json()
        assert data["sent_to_board"] is False

    def test_render_template_live_empty_list(self, client, mock_template_engine, mock_settings_service):
        response = client.post("/templates/render/live", json={"template": []})
        assert response.status_code == 200
        data = response.json()
        assert data["sent_to_board"] is False

    def test_render_template_live_missing_param(self, client, mock_template_engine):
        response = client.post("/templates/render/live", json={})
        assert response.status_code == 400

    def test_render_template_live_board_not_found(self, client, mock_template_engine, mock_settings_service):
        mock_settings_service.get_board_settings.return_value = Mock(boards=[{"id": "b1", "device_type": "flagship"}])
        with patch("src.api_server.board_client_from_board_dict", return_value=None):
            response = client.post("/templates/render/live", json={
                "template": "Hello",
                "board_id": "b1",
            })
        assert response.status_code == 200

    def test_render_template_live_specified_board_id_not_found(self, client, mock_template_engine, mock_settings_service):
        mock_settings_service.get_board_settings.return_value = Mock(boards=[])
        response = client.post("/templates/render/live", json={
            "template": "Hello",
            "board_id": "nonexistent",
        })
        assert response.status_code == 404

    def test_render_template_live_render_error(self, client, mock_template_engine, mock_settings_service):
        mock_template_engine.render.side_effect = Exception("Render error")
        response = client.post("/templates/render/live", json={"template": "{{bad}}"})
        assert response.status_code == 400


# ============================================================
# Pages Endpoints
# ============================================================

class TestPagesEndpoints:
    def test_list_pages(self, client, mock_page_service):
        response = client.get("/pages")
        assert response.status_code == 200
        data = response.json()
        assert "pages" in data
        assert data["total"] == 1

    def test_create_page(self, client, mock_page_service):
        response = client.post("/pages", json={
            "name": "Test Page",
            "type": "template",
            "template": ["Hello"],
        })
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_get_page(self, client, mock_page_service):
        response = client.get("/pages/page1")
        assert response.status_code == 200

    def test_get_page_not_found(self, client, mock_page_service):
        mock_page_service.get_page.return_value = None
        response = client.get("/pages/nonexistent")
        assert response.status_code == 404

    def test_update_page(self, client, mock_page_service):
        response = client.put("/pages/page1", json={"name": "Updated"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_update_page_not_found(self, client, mock_page_service):
        mock_page_service.update_page.return_value = None
        response = client.put("/pages/nonexistent", json={"name": "Updated"})
        assert response.status_code == 404

    def test_update_page_value_error(self, client, mock_page_service):
        mock_page_service.update_page.side_effect = ValueError("Invalid field")
        response = client.put("/pages/page1", json={"name": "Bad"})
        assert response.status_code == 400

    def test_delete_page(self, client, mock_page_service):
        response = client.delete("/pages/page1")
        assert response.status_code == 200

    def test_delete_page_not_found(self, client, mock_page_service):
        delete_result = Mock()
        delete_result.deleted = False
        mock_page_service.delete_page.return_value = delete_result
        response = client.delete("/pages/nonexistent")
        assert response.status_code == 404

    def test_delete_page_default_created(self, client, mock_page_service):
        delete_result = Mock()
        delete_result.deleted = True
        delete_result.default_page_created = True
        delete_result.active_page_updated = True
        delete_result.new_page_id = "new_default"
        delete_result.new_active_page_id = "new_default"
        mock_page_service.delete_page.return_value = delete_result
        response = client.delete("/pages/page1")
        assert response.status_code == 200
        data = response.json()
        assert data["default_page_created"] is True
        assert "new_page_id" in data

    def test_preview_page(self, client, mock_page_service, mock_settings_service):
        response = client.post("/pages/page1/preview")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "lines" in data

    def test_preview_page_not_found(self, client, mock_page_service, mock_settings_service):
        mock_page_service.preview_page.return_value = None
        response = client.post("/pages/page1/preview")
        assert response.status_code == 404

    def test_preview_page_unavailable(self, client, mock_page_service, mock_settings_service):
        result = Mock()
        result.available = False
        result.error = "Plugin not configured"
        mock_page_service.preview_page.return_value = result
        response = client.post("/pages/page1/preview")
        assert response.status_code == 503

    def test_preview_pages_batch(self, client, mock_page_service, mock_settings_service):
        response = client.post("/pages/preview/batch", json={
            "page_ids": ["page1"],
        })
        assert response.status_code == 200
        data = response.json()
        assert "previews" in data
        assert data["total"] == 1

    def test_preview_pages_batch_invalid_input(self, client, mock_page_service, mock_settings_service):
        response = client.post("/pages/preview/batch", json={"page_ids": "not_a_list"})
        assert response.status_code == 400

    def test_preview_pages_batch_page_not_found(self, client, mock_page_service, mock_settings_service):
        mock_page_service.preview_pages_batch.return_value = {"gone": None}
        response = client.post("/pages/preview/batch", json={"page_ids": ["gone"]})
        assert response.status_code == 200
        data = response.json()
        assert data["previews"]["gone"]["available"] is False

    def test_preview_pages_batch_exception(self, client, mock_page_service, mock_settings_service):
        error_result = Mock()
        error_result.available = False
        error_result.error = "Boom"
        error_result.formatted = ""
        error_result.raw = {}
        mock_page_service.preview_pages_batch.return_value = {"page1": error_result}
        response = client.post("/pages/preview/batch", json={"page_ids": ["page1"]})
        assert response.status_code == 200
        data = response.json()
        assert data["previews"]["page1"]["available"] is False

    def test_get_page_cache_stats(self, client, mock_page_service):
        response = client.get("/pages/cache/stats")
        assert response.status_code == 200

    def test_clear_page_cache_all(self, client, mock_page_service):
        response = client.post("/pages/cache/clear", json={})
        assert response.status_code == 200
        assert "all" in response.json()["message"].lower()

    def test_clear_page_cache_specific(self, client, mock_page_service):
        response = client.post("/pages/cache/clear", json={"page_id": "page1"})
        assert response.status_code == 200
        assert "page1" in response.json()["message"]

    def test_clear_page_cache_no_body(self, client, mock_page_service):
        response = client.post("/pages/cache/clear")
        assert response.status_code == 200

    def test_send_page(self, client, mock_page_service, mock_settings_service, mock_service):
        response = client.post("/pages/page1/send")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_send_page_not_found(self, client, mock_page_service, mock_settings_service, mock_service):
        mock_page_service.get_page.return_value = None
        response = client.post("/pages/nonexistent/send")
        assert response.status_code == 404

    def test_send_page_no_service(self, client, mock_page_service, mock_settings_service):
        with patch("src.api_server.get_service", return_value=None):
            response = client.post("/pages/page1/send")
        assert response.status_code == 503

    def test_send_page_invalid_target(self, client, mock_page_service, mock_settings_service, mock_service):
        response = client.post("/pages/page1/send?target=invalid")
        assert response.status_code == 400


# ============================================================
# Schedule Endpoints
# ============================================================

class TestScheduleEndpoints:
    def test_list_schedules(self, client, mock_schedule_service, mock_settings_service):
        response = client.get("/schedules")
        assert response.status_code == 200
        data = response.json()
        assert "schedules" in data
        assert data["total"] == 1

    def test_list_schedules_all_boards(self, client, mock_schedule_service, mock_settings_service):
        response = client.get("/schedules?board_id=*")
        assert response.status_code == 200
        data = response.json()
        assert data["default_page_id"] is None

    def test_get_schedule(self, client, mock_schedule_service):
        response = client.get("/schedules/sched1")
        assert response.status_code == 200

    def test_get_schedule_not_found(self, client, mock_schedule_service):
        mock_schedule_service.get_schedule.return_value = None
        response = client.get("/schedules/nonexistent")
        assert response.status_code == 404

    def test_update_schedule(self, client, mock_schedule_service):
        response = client.put("/schedules/sched1", json={"page_id": "page2"})
        assert response.status_code == 200

    def test_update_schedule_not_found(self, client, mock_schedule_service):
        mock_schedule_service.update_schedule.return_value = None
        response = client.put("/schedules/nonexistent", json={"page_id": "page2"})
        assert response.status_code == 404

    def test_update_schedule_value_error(self, client, mock_schedule_service):
        mock_schedule_service.update_schedule.side_effect = ValueError("Invalid")
        response = client.put("/schedules/sched1", json={"page_id": "bad"})
        assert response.status_code == 400

    def test_delete_schedule(self, client, mock_schedule_service):
        response = client.delete("/schedules/sched1")
        assert response.status_code == 200

    def test_delete_schedule_not_found(self, client, mock_schedule_service):
        mock_schedule_service.delete_schedule.return_value = False
        response = client.delete("/schedules/nonexistent")
        assert response.status_code == 404

    def test_get_active_schedule_page_manual(self, client, mock_schedule_service, mock_settings_service):
        response = client.get("/schedules/active/page")
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "manual"
        assert data["schedule_enabled"] is False

    def test_validate_schedules(self, client, mock_schedule_service):
        response = client.post("/schedules/validate", json={})
        assert response.status_code == 200

    def test_get_default_page(self, client, mock_schedule_service):
        response = client.get("/schedules/default-page")
        assert response.status_code == 200
        assert response.json()["default_page_id"] == "page1"

    def test_set_default_page(self, client, mock_schedule_service, mock_page_service):
        response = client.put("/schedules/default-page", json={"page_id": "page1"})
        assert response.status_code == 200

    def test_set_default_page_missing_param(self, client, mock_schedule_service):
        response = client.put("/schedules/default-page", json={})
        assert response.status_code == 400

    def test_set_default_page_not_found(self, client, mock_schedule_service, mock_page_service):
        mock_page_service.get_page.return_value = None
        response = client.put("/schedules/default-page", json={"page_id": "nonexistent"})
        assert response.status_code == 404

    def test_set_default_page_null(self, client, mock_schedule_service, mock_page_service):
        response = client.put("/schedules/default-page", json={"page_id": None})
        assert response.status_code == 200

    def test_get_schedule_enabled(self, client, mock_settings_service):
        response = client.get("/schedules/enabled")
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_set_schedule_enabled(self, client, mock_settings_service):
        response = client.put("/schedules/enabled", json={"enabled": True})
        assert response.status_code == 200

    def test_set_schedule_enabled_missing_param(self, client, mock_settings_service):
        response = client.put("/schedules/enabled", json={})
        assert response.status_code == 400

    def test_set_schedule_enabled_not_bool(self, client, mock_settings_service):
        response = client.put("/schedules/enabled", json={"enabled": "yes"})
        assert response.status_code == 400


# ============================================================
# Cache / Force Refresh
# ============================================================

class TestCacheEndpoints:
    def test_get_cache_status(self, client, mock_service):
        response = client.get("/cache-status")
        assert response.status_code == 200

    def test_get_cache_status_no_service(self, client):
        with patch("src.api_server.get_service", return_value=None):
            response = client.get("/cache-status")
        assert response.status_code == 503

    def test_get_cache_status_no_client(self, client):
        svc = Mock()
        svc.vb_client = None
        with patch("src.api_server.get_service", return_value=svc):
            response = client.get("/cache-status")
        assert response.status_code == 503

    def test_clear_cache(self, client, mock_service):
        response = client.post("/clear-cache")
        assert response.status_code == 200
        assert "cleared" in response.json()["message"].lower()

    def test_clear_cache_no_service(self, client):
        with patch("src.api_server.get_service", return_value=None):
            response = client.post("/clear-cache")
        assert response.status_code == 503

    def test_force_refresh_no_service(self, client):
        with patch("src.api_server.get_service", return_value=None):
            response = client.post("/force-refresh")
        assert response.status_code == 503

    def test_force_refresh_success(self, client, mock_service):
        response = client.post("/force-refresh")
        assert response.status_code == 200

    def test_force_refresh_error(self, client, mock_service):
        mock_service.check_and_send_active_page.side_effect = Exception("Refresh failed")
        response = client.post("/force-refresh")
        assert response.status_code == 500


# ============================================================
# Service Start / Stop / Refresh / Send Message
# ============================================================

class TestServiceLifecycle:
    def test_start_already_running(self, client, mock_service):
        with patch("src.api_server._service_running", True):
            response = client.post("/start")
        assert response.status_code == 200
        assert response.json()["status"] == "already_running"

    def test_stop_not_running(self, client):
        with patch("src.api_server._service_running", False):
            response = client.post("/stop")
        assert response.status_code == 200
        assert response.json()["status"] == "not_running"

    def test_stop_running(self, client, mock_service):
        with patch("src.api_server._service_running", True):
            response = client.post("/stop")
        assert response.status_code == 200
        assert response.json()["status"] == "stopped"

    def test_refresh_no_service(self, client):
        with patch("src.api_server.get_service", return_value=None):
            response = client.post("/refresh")
        assert response.status_code == 503

    def test_refresh_error(self, client, mock_service):
        mock_service.check_and_send_active_page.side_effect = Exception("Display error")
        response = client.post("/refresh")
        assert response.status_code == 500

    def test_send_message_no_service(self, client):
        with patch("src.api_server.get_service", return_value=None):
            response = client.post("/send-message", json={"text": "Hello"})
        assert response.status_code == 503

    def test_send_message_silence_mode(self, client, mock_service):
        with patch("src.api_server.Config.is_silence_mode_active", return_value=True):
            response = client.post("/send-message", json={"text": "Hello"})
        assert response.status_code == 200
        assert response.json()["silence_mode"] is True

    def test_send_message_no_board_client(self, client, mock_service, mock_settings_service):
        mock_service.vb_client = None
        with patch("src.api_server.Config.is_silence_mode_active", return_value=False):
            response = client.post("/send-message", json={"text": "Hello"})
        assert response.status_code == 503

    def test_send_message_success(self, client, mock_service, mock_settings_service):
        with patch("src.api_server.Config.is_silence_mode_active", return_value=False):
            response = client.post("/send-message", json={"text": "Hello"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_send_message_skipped(self, client, mock_service, mock_settings_service):
        mock_service.vb_client.send_characters.return_value = (True, False)
        with patch("src.api_server.Config.is_silence_mode_active", return_value=False):
            response = client.post("/send-message", json={"text": "Hello"})
        assert response.status_code == 200
        assert response.json()["skipped"] is True

    def test_send_message_failure(self, client, mock_service, mock_settings_service):
        mock_service.vb_client.send_characters.return_value = (False, False)
        with patch("src.api_server.Config.is_silence_mode_active", return_value=False):
            response = client.post("/send-message", json={"text": "Hello"})
        assert response.status_code == 500


# ============================================================
# Board Current Message
# ============================================================

class TestBoardCurrentMessage:
    def test_no_service(self, client):
        with patch("src.api_server.get_service", return_value=None):
            response = client.get("/board/current-message")
        assert response.status_code == 503

    def test_no_board_client(self, client, mock_service):
        mock_service.vb_client = None
        response = client.get("/board/current-message")
        assert response.status_code == 503

    def test_read_failure(self, client, mock_service):
        # _polled_characters is None → falls back to live call → returns None → 503
        mock_service.vb_client.read_current_message.return_value = None
        response = client.get("/board/current-message")
        assert response.status_code == 503

    def test_success_live_call(self, client, mock_service):
        """When no cached state, falls back to a live read and primes the cache."""
        grid = [[0] * 22 for _ in range(6)]
        grid[0][0:5] = [8, 5, 12, 12, 15]  # H E L L O
        mock_service.vb_client.read_current_message.return_value = grid
        response = client.get("/board/current-message")
        assert response.status_code == 200
        data = response.json()
        assert data["rows"] == 6
        assert data["cols"] == 22
        assert data["characters"] == grid
        assert data["message"].startswith("HELLO")
        assert data["cached_at"] is None  # live call → no cached_at
        assert data["api_mode"] == "local"
        assert data["expected_characters"] is None  # nothing sent yet

    def test_success_cached(self, client, mock_service):
        """When polled cache is populated, serves from it without calling read_current_message."""
        import time
        grid = [[0] * 22 for _ in range(6)]
        grid[0][0:3] = [8, 9, 10]
        mock_service._polled_characters = grid
        mock_service._polled_at = time.time()
        response = client.get("/board/current-message")
        assert response.status_code == 200
        data = response.json()
        assert data["characters"] == grid
        assert data["cached_at"] is not None
        mock_service.vb_client.read_current_message.assert_not_called()

    def test_force_bypasses_cache(self, client, mock_service):
        """?force=true makes a live call even when cache is populated."""
        import time
        cached_grid = [[1] * 22 for _ in range(6)]
        fresh_grid = [[2] * 22 for _ in range(6)]
        mock_service._polled_characters = cached_grid
        mock_service._polled_at = time.time()
        mock_service.vb_client.read_current_message.return_value = fresh_grid
        response = client.get("/board/current-message?force=true")
        assert response.status_code == 200
        data = response.json()
        assert data["characters"] == fresh_grid
        assert data["cached_at"] is None  # force call returns null cached_at
        mock_service.vb_client.read_current_message.assert_called_once()

    def test_expected_characters_included(self, client, mock_service):
        """expected_characters reflects what FiestaBoard last sent."""
        grid = [[0] * 22 for _ in range(6)]
        expected = [[5] * 22 for _ in range(6)]
        mock_service.vb_client.read_current_message.return_value = grid
        mock_service.vb_client._last_characters = expected
        response = client.get("/board/current-message")
        assert response.status_code == 200
        assert response.json()["expected_characters"] == expected

    def test_cloud_api_mode(self, client, mock_service):
        """api_mode reflects the board client's connection type."""
        grid = [[0] * 22 for _ in range(6)]
        mock_service.vb_client.read_current_message.return_value = grid
        mock_service.vb_client.use_cloud = True
        response = client.get("/board/current-message")
        assert response.status_code == 200
        assert response.json()["api_mode"] == "cloud"

    def test_color_tiles_in_message(self, client, mock_service):
        grid = [[0] * 22 for _ in range(6)]
        grid[0][0] = 63   # RED tile
        grid[0][1] = 64   # ORANGE tile
        mock_service.vb_client.read_current_message.return_value = grid
        response = client.get("/board/current-message")
        assert response.status_code == 200
        msg = response.json()["message"]
        assert "{63}" in msg
        assert "{64}" in msg


class TestCharactersToMessage:
    """Unit tests for the _characters_to_message helper."""

    def _call(self, grid):
        from src.api_server import _characters_to_message
        return _characters_to_message(grid)

    def test_blank_board(self):
        grid = [[0] * 22 for _ in range(6)]
        result = self._call(grid)
        lines = result.split("\n")
        assert len(lines) == 6
        assert all(line == " " * 22 for line in lines)

    def test_letters(self):
        grid = [[0] * 22 for _ in range(6)]
        grid[0][0:4] = [1, 2, 3, 26]  # A B C Z
        result = self._call(grid)
        assert result.split("\n")[0].startswith("ABCZ")

    def test_numbers(self):
        grid = [[0] * 22 for _ in range(6)]
        grid[0][0:3] = [27, 36, 35]  # 1 0 9
        result = self._call(grid)
        assert result.split("\n")[0].startswith("109")

    def test_color_codes(self):
        grid = [[0] * 22 for _ in range(6)]
        grid[0][0] = 63
        grid[0][1] = 71
        result = self._call(grid)
        first_line = result.split("\n")[0]
        assert first_line.startswith("{63}{71}")

    def test_degree_symbol(self):
        grid = [[0] * 22 for _ in range(6)]
        grid[0][0] = 62
        result = self._call(grid)
        assert result.split("\n")[0][0] == "°"

    def test_punctuation(self):
        grid = [[0] * 22 for _ in range(6)]
        grid[0][0] = 37  # !
        grid[0][1] = 56  # .
        grid[0][2] = 60  # ?
        result = self._call(grid)
        assert result.split("\n")[0].startswith("!.?")


# ============================================================
# Display Batch Operations
# ============================================================

class TestDisplayBatchEndpoints:
    def test_displays_raw_batch(self, client, mock_display_service):
        response = client.post("/displays/raw/batch", json={
            "display_types": ["weather"],
        })
        assert response.status_code == 200
        data = response.json()
        assert "displays" in data
        assert data["total"] == 1

    def test_displays_raw_batch_empty(self, client, mock_display_service):
        response = client.post("/displays/raw/batch", json={"display_types": []})
        assert response.status_code == 400

    def test_displays_raw_batch_not_list(self, client, mock_display_service):
        response = client.post("/displays/raw/batch", json={"display_types": "weather"})
        assert response.status_code == 400

    def test_displays_raw_batch_exception_handling(self, client, mock_display_service):
        mock_display_service.get_display.side_effect = Exception("Plugin error")
        response = client.post("/displays/raw/batch", json={
            "display_types": ["weather"],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["displays"]["weather"]["available"] is False

    def test_send_display_invalid_target(self, client, mock_display_service, mock_settings_service, mock_service):
        response = client.post("/displays/weather/send?target=invalid")
        assert response.status_code == 400

    def test_send_display_no_service(self, client, mock_display_service, mock_settings_service):
        with patch("src.api_server.get_service", return_value=None):
            response = client.post("/displays/weather/send")
        assert response.status_code == 503

    def test_send_display_unknown_type(self, client, mock_display_service, mock_settings_service, mock_service):
        from src.displays.service import DisplayResult
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="fake",
            formatted="",
            raw={},
            available=False,
            error="Unknown display type: fake",
        )
        response = client.post("/displays/fake/send")
        assert response.status_code == 400


# ============================================================
# Welcome Message
# ============================================================

class TestWelcomeMessage:
    def test_send_welcome_silence_mode(self, client):
        with patch("src.api_server.Config.is_silence_mode_active", return_value=True):
            response = client.post("/send-welcome-message")
        assert response.status_code == 200
        assert response.json()["silence_mode"] is True

# ============================================================
# Enable Local API
# ============================================================

class TestEnableLocalAPI:
    def test_missing_host(self, client):
        response = client.post("/config/board/enable-local-api", json={
            "host": "",
            "enablement_token": "test_token_xyz",
        })
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_missing_token(self, client):
        response = client.post("/config/board/enable-local-api", json={
            "host": "192.168.1.100",
            "enablement_token": "",
        })
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_success(self, client):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"apiKey": "generated_api_key_abc"}
        with patch("src.api_server.requests.post", return_value=mock_resp) as mock_post:
            response = client.post("/config/board/enable-local-api", json={
                "host": "192.168.1.100",
                "enablement_token": "test_enablement_token_xyz",
            })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["api_key"] == "generated_api_key_abc"

    def test_success_no_key_in_response(self, client):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        with patch("src.api_server.requests.post", return_value=mock_resp):
            response = client.post("/config/board/enable-local-api", json={
                "host": "192.168.1.100",
                "enablement_token": "test_token_xyz",
            })
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_unauthorized(self, client):
        mock_resp = Mock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        with patch("src.api_server.requests.post", return_value=mock_resp):
            response = client.post("/config/board/enable-local-api", json={
                "host": "192.168.1.100",
                "enablement_token": "test_bad_token",
            })
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_other_http_error(self, client):
        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch("src.api_server.requests.post", return_value=mock_resp):
            response = client.post("/config/board/enable-local-api", json={
                "host": "192.168.1.100",
                "enablement_token": "test_token_xyz",
            })
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_connection_error(self, client):
        import requests as http_requests
        with patch("src.api_server.requests.post",
                    side_effect=http_requests.exceptions.ConnectionError("refused")):
            response = client.post("/config/board/enable-local-api", json={
                "host": "192.168.1.100",
                "enablement_token": "test_token_xyz",
            })
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_timeout_error(self, client):
        import requests as http_requests
        with patch("src.api_server.requests.post",
                    side_effect=http_requests.exceptions.Timeout("timed out")):
            response = client.post("/config/board/enable-local-api", json={
                "host": "192.168.1.100",
                "enablement_token": "test_token_xyz",
            })
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_generic_error(self, client):
        with patch("src.api_server.requests.post", side_effect=RuntimeError("unexpected")):
            response = client.post("/config/board/enable-local-api", json={
                "host": "192.168.1.100",
                "enablement_token": "test_token_xyz",
            })
        assert response.status_code == 200
        assert response.json()["success"] is False


# ============================================================
# Stocks Endpoints
# ============================================================

class TestStocksEndpoints:
    def test_validate_stock_missing_symbol(self, client):
        response = client.post("/stocks/validate", json={})
        assert response.status_code == 400


# ============================================================
# Traffic Geocode
# ============================================================

class TestTrafficGeocode:
    def test_geocode_success(self, client):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"lat": "40.7128", "lon": "-74.0060", "display_name": "NYC"}]
        mock_resp.raise_for_status = Mock()
        with patch("src.api_server.requests.get", return_value=mock_resp):
            response = client.post("/traffic/routes/geocode", json={"address": "NYC"})
        assert response.status_code == 200
        data = response.json()
        assert data["lat"] == 40.7128

    def test_geocode_missing_address(self, client):
        response = client.post("/traffic/routes/geocode", json={})
        assert response.status_code == 400

    def test_geocode_not_found(self, client):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = Mock()
        with patch("src.api_server.requests.get", return_value=mock_resp):
            response = client.post("/traffic/routes/geocode", json={"address": "xyznonexistent"})
        assert response.status_code == 404


# ============================================================
# Queue Times Proxy
# ============================================================

class TestQueueTimes:
    def test_list_disney_parks(self, client):
        with patch("src.api_server._queue_times_get") as mock_qt:
            mock_qt.return_value = [
                {"id": 2, "parks": [{"id": 1, "name": "Magic Kingdom", "country": "US", "timezone": "EST"}]},
            ]
            response = client.get("/queue-times/parks")
        assert response.status_code == 200

    def test_list_disney_parks_no_group(self, client):
        with patch("src.api_server._queue_times_get") as mock_qt:
            mock_qt.return_value = [{"id": 99, "parks": []}]
            response = client.get("/queue-times/parks")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_disney_parks_error(self, client):
        with patch("src.api_server._queue_times_get", side_effect=Exception("API down")):
            response = client.get("/queue-times/parks")
        assert response.status_code == 502

    def test_list_park_rides(self, client):
        with patch("src.api_server._queue_times_get") as mock_qt:
            mock_qt.return_value = {
                "lands": [{"rides": [{"id": 1, "name": "Space Mountain"}]}]
            }
            response = client.get("/queue-times/parks/1/rides")
        assert response.status_code == 200

    def test_list_park_rides_error(self, client):
        with patch("src.api_server._queue_times_get", side_effect=Exception("fail")):
            response = client.get("/queue-times/parks/1/rides")
        assert response.status_code == 502

