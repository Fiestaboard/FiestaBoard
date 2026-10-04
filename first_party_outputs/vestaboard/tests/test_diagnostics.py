"""The Vestaboard diagnostics hook: DNS, TCP, then the API (local) or the RW Cloud API.

The shared checks (``check_dns_resolution``, ``check_port_reachable``) are
FiestaBoard's; they are patched where the plugin binds them.
"""

from unittest.mock import Mock, patch

import requests

from first_party_outputs.vestaboard import diagnostics

# ---------------------------------------------------------------------------
# check_vestaboard_connection
# ---------------------------------------------------------------------------


class TestCheckVestaboardConnection:
    """Tests for check_vestaboard_connection."""

    @patch("requests.get")
    @patch.object(diagnostics, "check_port_reachable")
    @patch.object(diagnostics, "check_dns_resolution")
    def test_local_all_ok(self, mock_dns, mock_port, mock_get):
        mock_dns.return_value = {"ok": True, "hostname": "board.local", "ip": "10.0.0.5"}
        mock_port.return_value = {"ok": True, "host": "board.local", "port": 7000, "latency_ms": 5}
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = diagnostics.check_vestaboard_connection("board.local", api_key="key123")

        assert result["ok"] is True
        assert result["mode"] == "local"
        assert "dns" in result["steps"]
        assert "port" in result["steps"]
        assert "api" in result["steps"]

    @patch.object(diagnostics, "check_dns_resolution")
    def test_local_dns_failure_short_circuits(self, mock_dns):
        mock_dns.return_value = {"ok": False, "hostname": "bad.local", "ip": None, "error": "fail"}

        result = diagnostics.check_vestaboard_connection("bad.local")

        assert result["ok"] is False
        assert "dns" in result["steps"]
        assert "port" not in result["steps"]
        assert "api" not in result["steps"]

    @patch.object(diagnostics, "check_port_reachable")
    @patch.object(diagnostics, "check_dns_resolution")
    def test_local_port_failure_short_circuits(self, mock_dns, mock_port):
        mock_dns.return_value = {"ok": True, "hostname": "board.local", "ip": "10.0.0.5"}
        mock_port.return_value = {"ok": False, "host": "board.local", "port": 7000, "error": "refused"}

        result = diagnostics.check_vestaboard_connection("board.local")

        assert result["ok"] is False
        assert "dns" in result["steps"]
        assert "port" in result["steps"]
        assert "api" not in result["steps"]

    @patch("requests.get")
    @patch.object(diagnostics, "check_port_reachable")
    @patch.object(diagnostics, "check_dns_resolution")
    def test_local_api_failure(self, mock_dns, mock_port, mock_get):
        mock_dns.return_value = {"ok": True, "hostname": "board.local", "ip": "10.0.0.5"}
        mock_port.return_value = {"ok": True, "host": "board.local", "port": 7000, "latency_ms": 5}
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")

        result = diagnostics.check_vestaboard_connection("board.local")

        assert result["ok"] is False
        assert result["steps"]["api"]["ok"] is False

    @patch("requests.get")
    def test_cloud_success(self, mock_get):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = diagnostics.check_vestaboard_connection(host="", use_cloud=True, cloud_key="rw-key-123")

        assert result["ok"] is True
        assert result["mode"] == "cloud"
        assert "cloud_api" in result["steps"]

    @patch("requests.get")
    def test_cloud_failure(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("no route")

        result = diagnostics.check_vestaboard_connection(host="", use_cloud=True, cloud_key="rw-key-123")

        assert result["ok"] is False
        assert result["mode"] == "cloud"

    @patch("requests.get")
    def test_cloud_server_error(self, mock_get):
        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        result = diagnostics.check_vestaboard_connection(host="", use_cloud=True, cloud_key="rw-key-123")

        assert result["ok"] is False


class TestErrorTextSanitization:
    """Every ``error`` field is a static classification, never str(exc)
    (CodeQL py/stack-trace-exposure, alert #63)."""

    SENTINEL = "SECRET_INTERNAL_XYZ"

    @patch("requests.get")
    def test_cloud_api_error_text_is_sanitized(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError(self.SENTINEL)

        result = diagnostics.check_vestaboard_connection(host="", use_cloud=True, cloud_key="rw-key")

        assert result["ok"] is False
        assert self.SENTINEL not in repr(result)
        assert result["steps"]["cloud_api"]["error"] == "Could not connect"

    @patch("requests.get")
    @patch.object(diagnostics, "check_port_reachable")
    @patch.object(diagnostics, "check_dns_resolution")
    def test_local_api_error_text_is_sanitized(self, mock_dns, mock_port, mock_get):
        mock_dns.return_value = {"ok": True, "hostname": "192.0.2.10", "ip": "192.0.2.10"}
        mock_port.return_value = {"ok": True, "host": "192.0.2.10", "port": 7000, "latency_ms": 5}
        mock_get.side_effect = requests.exceptions.Timeout(self.SENTINEL)

        result = diagnostics.check_vestaboard_connection(host="192.0.2.10", api_key="key")

        assert result["ok"] is False
        assert self.SENTINEL not in repr(result)
        assert result["steps"]["api"]["error"] == "Connection timed out"
