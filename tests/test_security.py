"""Security tests for the FiestaBoard API.

Covers:
- Path traversal attempts on plugin_id path parameters
- Sensitive data masking in config responses
- Input validation and oversized payload handling
- Log endpoint safety (invalid levels, large search strings)
- Plugin config boundary validation via the API
- refresh_seconds rate-limit bypass attempts
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from src.api_server import app


def _make_addr_info(ip: str, port: int = 80):
    """Build a minimal getaddrinfo-like return value for tests."""
    return [(None, None, None, None, (ip, port))]


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_plugin_registry_secure():
    """Mock plugin registry that returns None for unknown/traversal plugin IDs."""
    with patch("src.api_server.get_plugin_registry") as mock_get, \
         patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True):
        reg = Mock()
        reg.get_manifest.return_value = None
        reg.get_plugin.return_value = None
        reg.parse_instance_key.return_value = (None, None)
        reg.list_instances.return_value = []
        reg.list_plugins.return_value = []
        reg.get_load_errors.return_value = {}
        mock_get.return_value = reg
        yield reg


@pytest.fixture
def mock_plugin_with_sensitive_config():
    """Mock plugin registry with a plugin that has sensitive config fields."""
    with patch("src.api_server.get_plugin_registry") as mock_get, \
         patch("src.api_server.get_config_manager") as mock_cm_get, \
         patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True):
        reg = Mock()
        manifest = Mock()
        manifest.name = "Test Plugin"
        manifest.version = "1.0.0"
        manifest.description = "A plugin"
        manifest.author = "Test"
        manifest.icon = "puzzle"
        manifest.category = "utility"
        manifest.settings_schema = {
            "type": "object",
            "properties": {
                "api_key": {"type": "string"},
                "location": {"type": "string"},
            },
        }
        manifest.raw = {"variables": {}}
        manifest.max_lengths = {}
        manifest.env_vars = []
        manifest.documentation = ""
        reg.get_manifest.return_value = manifest
        reg.get_plugin.return_value = Mock()
        reg.is_enabled.return_value = False
        reg.parse_instance_key.return_value = ("test_plugin", None)
        reg.list_instances.return_value = []
        reg.get_all_variables_with_metadata.return_value = {}

        cm = Mock()
        raw_config = {"api_key": "super-secret-key-abc123", "location": "New York"}
        masked_config = {"api_key": "***", "location": "New York"}
        cm.get_plugin_config.return_value = raw_config
        cm._mask_sensitive.return_value = masked_config

        mock_get.return_value = reg
        mock_cm_get.return_value = cm
        yield reg, cm


# ===========================================================================
# Path Traversal Tests
# ===========================================================================

class TestPathTraversal:
    """Tests that unusual/malicious plugin_id values are safely rejected."""

    TRAVERSAL_PLUGIN_IDS = [
        "unknown_plugin",
        "a" * 300,
        "plugin with spaces",
        "__pycache__",
    ]

    @pytest.mark.parametrize("plugin_id", TRAVERSAL_PLUGIN_IDS)
    def test_get_plugin_unknown_ids_return_404_or_422(self, client, mock_plugin_registry_secure, plugin_id):
        """Requesting an unknown plugin_id (including suspicious ones) returns 404, not a server error."""
        response = client.get(f"/plugins/{plugin_id}")
        assert response.status_code in (400, 404, 422, 503), (
            f"Expected 4xx for plugin_id={plugin_id!r}, got {response.status_code}"
        )

    @pytest.mark.parametrize("plugin_id", TRAVERSAL_PLUGIN_IDS)
    def test_enable_plugin_unknown_ids_return_404_or_422(self, client, mock_plugin_registry_secure, plugin_id):
        """POST /plugins/{id}/enable with unknown plugin_id returns 404, not a server error."""
        response = client.post(f"/plugins/{plugin_id}/enable")
        assert response.status_code in (400, 404, 422, 503), (
            f"Expected 4xx for plugin_id={plugin_id!r}, got {response.status_code}"
        )

    @pytest.mark.parametrize("plugin_id", TRAVERSAL_PLUGIN_IDS)
    def test_put_plugin_config_unknown_ids_return_404_or_422(self, client, mock_plugin_registry_secure, plugin_id):
        """PUT /plugins/{id}/config with unknown plugin_id returns 404, not a server error."""
        response = client.put(
            f"/plugins/{plugin_id}/config",
            json={"config": {"setting": "value"}},
        )
        assert response.status_code in (400, 404, 422, 503), (
            f"Expected 4xx for plugin_id={plugin_id!r}, got {response.status_code}"
        )

    @pytest.mark.parametrize("plugin_id", TRAVERSAL_PLUGIN_IDS)
    def test_get_plugin_manifest_unknown_ids_return_404_or_422(self, client, mock_plugin_registry_secure, plugin_id):
        """GET /plugins/{id}/manifest with unknown plugin_id returns 404, not a server error."""
        response = client.get(f"/plugins/{plugin_id}/manifest")
        assert response.status_code in (400, 404, 422, 503), (
            f"Expected 4xx for plugin_id={plugin_id!r}, got {response.status_code}"
        )

    def test_response_body_does_not_contain_stack_trace(self, client, mock_plugin_registry_secure):
        """Error responses must not leak Python stack traces."""
        response = client.get("/plugins/nonexistent_plugin_xyz")
        body = response.text
        assert "Traceback" not in body
        assert "File \"" not in body


# ===========================================================================
# Sensitive Data Masking Tests
# ===========================================================================

class TestSensitiveDataMasking:
    """Tests that sensitive config fields are masked in API responses."""

    def test_get_plugin_masks_api_key(self, client, mock_plugin_with_sensitive_config):
        """GET /plugins/{id} must not return the raw api_key value."""
        reg, cm = mock_plugin_with_sensitive_config
        response = client.get("/plugins/test_plugin")
        assert response.status_code == 200
        data = response.json()
        config = data.get("config", {})
        assert config.get("api_key") != "super-secret-key-abc123", (
            "Raw api_key must not appear in GET /plugins/{id} response"
        )
        assert config.get("api_key") == "***", (
            "api_key should be masked as '***'"
        )
        assert config.get("location") == "New York", (
            "Non-sensitive fields should pass through unmasked"
        )

    def test_mask_sensitive_called_on_plugin_get(self, client, mock_plugin_with_sensitive_config):
        """Verify that _mask_sensitive() is called when returning plugin config."""
        reg, cm = mock_plugin_with_sensitive_config
        client.get("/plugins/test_plugin")
        cm._mask_sensitive.assert_called()


# ===========================================================================
# Input Validation Tests
# ===========================================================================

class TestInputValidation:
    """Tests for input validation and malformed request handling."""

    def test_put_plugin_config_malformed_json_returns_422(self, client):
        """PUT /plugins/{id}/config with malformed JSON returns 422."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True):
            response = client.put(
                "/plugins/some_plugin/config",
                content=b"not valid json {{{",
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code == 422

    def test_put_plugin_config_missing_config_field_returns_422(self, client):
        """PUT /plugins/{id}/config without 'config' key returns 422."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True):
            response = client.put(
                "/plugins/some_plugin/config",
                json={"wrong_key": {"setting": "value"}},
            )
            assert response.status_code == 422

    def test_logs_endpoint_rejects_invalid_level(self, client):
        """GET /logs with an invalid level value returns 400."""
        response = client.get("/logs?level=INVALID_LEVEL")
        assert response.status_code == 400

    def test_logs_endpoint_rejects_level_too_large_limit(self, client):
        """GET /logs with limit exceeding max (500) returns 422."""
        response = client.get("/logs?limit=9999")
        assert response.status_code == 422

    def test_logs_endpoint_rejects_negative_offset(self, client):
        """GET /logs with negative offset returns 422."""
        response = client.get("/logs?offset=-1")
        assert response.status_code == 422

    def test_logs_endpoint_rejects_zero_limit(self, client):
        """GET /logs with limit=0 (below minimum of 1) returns 422."""
        response = client.get("/logs?limit=0")
        assert response.status_code == 422

    def test_logs_endpoint_with_valid_level_does_not_crash(self, client):
        """GET /logs with a valid level does not return a 5xx error."""
        with patch("src.api_server._read_logs_from_files", return_value=([], 0, False)):
            for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                response = client.get(f"/logs?level={level}")
                assert response.status_code == 200, f"Level={level} returned {response.status_code}"


# ===========================================================================
# Log Endpoint Safety Tests
# ===========================================================================

class TestLogEndpointSafety:
    """Tests that the log endpoint handles edge cases gracefully."""

    def test_logs_with_large_search_string_does_not_crash(self, client):
        """GET /logs with a very long search string must not return 5xx."""
        large_search = "A" * 5000
        with patch("src.api_server._read_logs_from_files", return_value=([], 0, False)):
            response = client.get(f"/logs?search={large_search}")
        assert response.status_code in (200, 400, 422), (
            f"Large search string caused unexpected status: {response.status_code}"
        )

    def test_logs_with_empty_search_returns_ok(self, client):
        """GET /logs with an empty search string returns 200."""
        with patch("src.api_server._read_logs_from_files", return_value=([], 0, False)):
            response = client.get("/logs?search=")
        assert response.status_code == 200

    def test_logs_with_special_chars_in_search(self, client):
        """GET /logs with special characters in search does not crash."""
        with patch("src.api_server._read_logs_from_files", return_value=([], 0, False)):
            response = client.get("/logs?search=<script>alert('xss')</script>")
        assert response.status_code in (200, 400, 422)

    def test_logs_response_structure(self, client):
        """GET /logs returns the expected response shape."""
        with patch("src.api_server._read_logs_from_files", return_value=(
            [{"level": "INFO", "message": "test"}], 1, False
        )):
            response = client.get("/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data
        assert "filters" in data


# ===========================================================================
# Plugin Enable/Disable Tests (via API)
# ===========================================================================

class TestPluginEnableDisableAPI:
    """Tests for plugin enable/disable state transitions through the API."""

    def test_enable_unknown_plugin_returns_404(self, client, mock_plugin_registry_secure):
        """POST /plugins/{id}/enable for unknown plugin returns 404."""
        response = client.post("/plugins/totally_unknown_plugin/enable")
        assert response.status_code == 404

    def test_disable_unknown_plugin_returns_404(self, client, mock_plugin_registry_secure):
        """POST /plugins/{id}/disable for unknown plugin returns 404."""
        response = client.post("/plugins/totally_unknown_plugin/disable")
        assert response.status_code == 404

    def test_enable_plugin_success_returns_correct_shape(self, client):
        """POST /plugins/{id}/enable for known plugin returns success shape."""
        with patch("src.api_server.get_plugin_registry") as mock_reg_get, \
             patch("src.api_server.get_config_manager") as mock_cm_get, \
             patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.reset_display_service"), \
             patch("src.api_server.reset_template_engine"):
            reg = Mock()
            reg.get_plugin.return_value = Mock()
            reg.enable_plugin.return_value = True
            mock_reg_get.return_value = reg
            mock_cm_get.return_value = Mock()

            response = client.post("/plugins/date_time/enable")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["plugin_id"] == "date_time"
            assert data["enabled"] is True

    def test_disable_plugin_success_returns_correct_shape(self, client):
        """POST /plugins/{id}/disable for known plugin returns success shape."""
        with patch("src.api_server.get_plugin_registry") as mock_reg_get, \
             patch("src.api_server.get_config_manager") as mock_cm_get, \
             patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.reset_display_service"), \
             patch("src.api_server.reset_template_engine"):
            reg = Mock()
            reg.get_plugin.return_value = Mock()
            reg.disable_plugin.return_value = True
            mock_reg_get.return_value = reg
            mock_cm_get.return_value = Mock()

            response = client.post("/plugins/date_time/disable")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["plugin_id"] == "date_time"
            assert data["enabled"] is False

    def test_enable_plugin_registry_failure_returns_400(self, client):
        """POST /plugins/{id}/enable when registry returns False gives 400."""
        with patch("src.api_server.get_plugin_registry") as mock_reg_get, \
             patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True):
            reg = Mock()
            reg.get_plugin.return_value = Mock()
            reg.enable_plugin.return_value = False
            mock_reg_get.return_value = reg

            response = client.post("/plugins/date_time/enable")
            assert response.status_code == 400


# ===========================================================================
# Debug Endpoint Shape Tests
# ===========================================================================

class TestDebugEndpoints:
    """Tests that debug endpoints return expected shapes without exposing secrets."""

    def test_debug_system_info_returns_expected_keys(self, client):
        """GET /debug/system-info returns a dict with expected structure."""
        mock_ts_instance = Mock()
        mock_ts_instance.create_utc_timestamp.return_value = "2026-03-22T00:00:00Z"

        with patch("src.api_server._get_server_ip", return_value="192.0.2.1"), \
             patch("src.api_server._get_service_uptime", return_value=3600.0), \
             patch("src.api_server._format_uptime", return_value="1h 0m"), \
             patch("src.api_server._get_board_client", return_value=None), \
             patch("src.time_service.get_time_service", return_value=mock_ts_instance):

            response = client.get("/debug/system-info")

        assert response.status_code == 200
        data = response.json()
        expected_keys = {
            "board_ip", "server_ip", "uptime_seconds", "uptime_formatted",
            "connection_mode", "version", "timestamp", "board_configured",
            "service_running",
        }
        missing = expected_keys - set(data.keys())
        assert not missing, f"Missing keys in /debug/system-info response: {missing}"

    def test_debug_system_info_does_not_expose_api_key(self, client):
        """GET /debug/system-info must not include raw API keys in the response."""
        mock_ts_instance = Mock()
        mock_ts_instance.create_utc_timestamp.return_value = "2026-03-22T00:00:00Z"

        with patch("src.api_server._get_server_ip", return_value="192.0.2.1"), \
             patch("src.api_server._get_service_uptime", return_value=0.0), \
             patch("src.api_server._format_uptime", return_value="0m"), \
             patch("src.api_server._get_board_client", return_value=None), \
             patch("src.time_service.get_time_service", return_value=mock_ts_instance):

            response = client.get("/debug/system-info")

        body = response.text
        assert "local_api_key" not in body
        assert "cloud_key" not in body
        assert "access_token" not in body


# ===========================================================================
# Config Boundary (Rate-Limit Bypass) Tests
# ===========================================================================

class TestRefreshSecondsBypass:
    """Tests that the API rejects refresh_seconds values below the manifest minimum."""

    def test_put_config_with_below_minimum_refresh_returns_400(self, client):
        """PUT /plugins/{id}/config with refresh_seconds below minimum returns 400."""
        with patch("src.api_server.get_plugin_registry") as mock_reg_get, \
             patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True):
            reg = Mock()
            reg.get_plugin.return_value = Mock()
            reg.set_plugin_config.return_value = ["Refresh interval must be at least 30 seconds"]
            mock_reg_get.return_value = reg

            response = client.put(
                "/plugins/some_plugin/config",
                json={"config": {"refresh_seconds": 1}},
            )
            assert response.status_code == 400
            data = response.json()
            assert "errors" in data.get("detail", {})

    def test_put_config_with_valid_refresh_succeeds(self, client):
        """PUT /plugins/{id}/config with valid refresh_seconds returns 200."""
        with patch("src.api_server.get_plugin_registry") as mock_reg_get, \
             patch("src.api_server.get_config_manager") as mock_cm_get, \
             patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.reset_display_service"), \
             patch("src.api_server.reset_template_engine"):
            reg = Mock()
            reg.get_plugin.return_value = Mock()
            reg.set_plugin_config.return_value = []
            mock_reg_get.return_value = reg

            cm = Mock()
            cm.get_plugin_config.return_value = {"refresh_seconds": 60}
            cm._mask_sensitive.return_value = {"refresh_seconds": 60}
            mock_cm_get.return_value = cm

            response = client.put(
                "/plugins/some_plugin/config",
                json={"config": {"refresh_seconds": 60}},
            )
            assert response.status_code == 200


# ===========================================================================
# SSRF Protection Tests
# ===========================================================================

class TestSSRFProtection:
    """Tests that _validate_request_url blocks SSRF targets via /generic-data/test-fetch."""

    # Public IP used in DNS mocks: 93.184.216.34 is the well-known example.com address.
    # socket.getaddrinfo() entry structure: (family, type, proto, canonname, sockaddr)
    _GETADDRINFO_PUBLIC_HTTPS_ENTRY = (None, None, None, None, ("93.184.216.34", 443))
    _PUBLIC_ADDR_INFO = [_GETADDRINFO_PUBLIC_HTTPS_ENTRY]

    @pytest.fixture
    def mock_cm(self):
        cm = Mock()
        cm.get_general.return_value = {}
        return cm

    def _post(self, client, url: str, mock_cm):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm):
            return client.post("/generic-data/test-fetch", json={"url": url})

    # --- Blocked: non-http(s) schemes ---

    def test_rejects_ftp_scheme(self, client, mock_cm):
        resp = self._post(client, "ftp://example.com/file", mock_cm)
        assert resp.status_code == 400

    def test_rejects_file_scheme(self, client, mock_cm):
        resp = self._post(client, "file:///etc/passwd", mock_cm)
        assert resp.status_code == 400

    # --- Blocked: credentials in URL ---

    def test_rejects_url_with_credentials(self, client, mock_cm):
        resp = self._post(client, "https://user:pass@example.com/data", mock_cm)
        assert resp.status_code == 400

    # --- Blocked: localhost-like names ---

    def test_rejects_localhost(self, client, mock_cm):
        resp = self._post(client, "http://localhost/api", mock_cm)
        assert resp.status_code == 400

    def test_rejects_localhost_subdomain(self, client, mock_cm):
        resp = self._post(client, "http://anything.localhost/api", mock_cm)
        assert resp.status_code == 400

    def test_rejects_dot_local_domain(self, client, mock_cm):
        resp = self._post(client, "http://mydevice.local/api", mock_cm)
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "Test & Preview" in detail
        assert "mydevice.local" in detail
        assert "plugin will still fetch" in detail

    # --- Blocked: loopback IP ---

    def test_rejects_loopback_ipv4(self, client, mock_cm):
        resp = self._post(client, "http://127.0.0.1/api", mock_cm)
        assert resp.status_code == 400

    def test_rejects_loopback_127_x(self, client, mock_cm):
        resp = self._post(client, "http://127.1.2.3/api", mock_cm)
        assert resp.status_code == 400

    # --- Blocked: private/RFC-1918 IPs ---

    def test_rejects_private_10_x(self, client, mock_cm):
        resp = self._post(client, "http://10.0.0.1/api", mock_cm)
        assert resp.status_code == 400

    def test_rejects_private_192_168(self, client, mock_cm):
        resp = self._post(client, "http://192.168.1.1/api", mock_cm)
        assert resp.status_code == 400

    def test_rejects_private_172_16(self, client, mock_cm):
        resp = self._post(client, "http://172.16.0.1/api", mock_cm)
        assert resp.status_code == 400

    # --- Blocked: link-local ---

    def test_rejects_link_local_169_254(self, client, mock_cm):
        resp = self._post(client, "http://169.254.169.254/latest/meta-data/", mock_cm)
        assert resp.status_code == 400

    # --- Blocked: DNS resolves to private IP ---

    def test_rejects_domain_resolving_to_private_ip(self, client, mock_cm):
        private_addr_info = _make_addr_info("10.0.0.5", 80)
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("socket.getaddrinfo", return_value=private_addr_info):
            resp = client.post("/generic-data/test-fetch", json={"url": "https://internal.corp/api"})
        assert resp.status_code == 400

    # --- Blocked: DNS failure ---

    def test_rejects_unresolvable_domain(self, client, mock_cm):
        import socket
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("socket.getaddrinfo", side_effect=socket.gaierror("no such host")):
            resp = client.post("/generic-data/test-fetch", json={"url": "https://no-such-host.invalid/api"})
        assert resp.status_code == 400

    # --- Allowed: public IP and domain ---

    def test_allows_public_ip(self, client, mock_cm):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = b'{"ok": true}'
        mock_resp.json.return_value = {"ok": True}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server._get_generic_data_allowed_hosts", return_value=["93.184.216.34"]), \
             patch("requests.request", return_value=mock_resp):
            resp = client.post("/generic-data/test-fetch", json={"url": "https://93.184.216.34/api"})
        assert resp.status_code == 200

    def test_allows_public_domain(self, client, mock_cm):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = b'{"ok": true}'
        mock_resp.json.return_value = {"ok": True}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server._get_generic_data_allowed_hosts", return_value=["example.com"]), \
             patch("socket.getaddrinfo", return_value=self._PUBLIC_ADDR_INFO), \
             patch("requests.request", return_value=mock_resp):
            resp = client.post("/generic-data/test-fetch", json={"url": "https://api.example.com/data"})
        assert resp.status_code == 200

    def test_allows_public_domain_when_no_allowlist_configured(self, client, mock_cm):
        """When GENERIC_DATA_ALLOWED_HOSTS is unset, any public host should be allowed."""
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = b'{"ok": true}'
        mock_resp.json.return_value = {"ok": True}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server._get_generic_data_allowed_hosts", return_value=[]), \
             patch("socket.getaddrinfo", return_value=self._PUBLIC_ADDR_INFO), \
             patch("requests.request", return_value=mock_resp):
            resp = client.post("/generic-data/test-fetch", json={"url": "https://api.example.com/data"})
        assert resp.status_code == 200

    def test_rejects_host_not_in_allowlist(self, client, mock_cm):
        """When GENERIC_DATA_ALLOWED_HOSTS is set, hosts outside the list are rejected."""
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server._get_generic_data_allowed_hosts", return_value=["myapi.com"]), \
             patch("socket.getaddrinfo", return_value=self._PUBLIC_ADDR_INFO):
            resp = client.post("/generic-data/test-fetch", json={"url": "https://api.example.com/data"})
        assert resp.status_code == 400
        assert "allowlist" in resp.json()["detail"]
