"""Tests for network diagnostics module."""

import socket
from unittest.mock import Mock, patch

import requests

from src.network_diagnostics import (
    check_dns_resolution,
    check_internet_connectivity,
    check_port_reachable,
    check_vestaboard_connection,
    run_full_diagnostics,
)

# ---------------------------------------------------------------------------
# check_dns_resolution
# ---------------------------------------------------------------------------

class TestCheckDnsResolution:
    """Tests for check_dns_resolution."""

    @patch("src.network_diagnostics.socket.gethostbyname")
    def test_success(self, mock_resolve):
        mock_resolve.return_value = "142.250.80.46"

        result = check_dns_resolution("google.com")

        assert result["ok"] is True
        assert result["hostname"] == "google.com"
        assert result["ip"] == "142.250.80.46"
        assert "error" not in result

    @patch("src.network_diagnostics.socket.gethostbyname")
    def test_failure_gaierror(self, mock_resolve):
        mock_resolve.side_effect = socket.gaierror("Name or service not known")

        result = check_dns_resolution("nonexistent.invalid")

        assert result["ok"] is False
        assert result["ip"] is None
        assert "error" in result

    @patch("src.network_diagnostics.socket.gethostbyname")
    def test_failure_generic_exception(self, mock_resolve):
        mock_resolve.side_effect = OSError("network unreachable")

        result = check_dns_resolution("google.com")

        assert result["ok"] is False
        assert "error" in result

    @patch("src.network_diagnostics.socket.gethostbyname")
    def test_custom_hostname(self, mock_resolve):
        mock_resolve.return_value = "10.0.0.1"

        result = check_dns_resolution("myboard.local")

        mock_resolve.assert_called_with("myboard.local")
        assert result["hostname"] == "myboard.local"


# ---------------------------------------------------------------------------
# check_internet_connectivity
# ---------------------------------------------------------------------------

class TestCheckInternetConnectivity:
    """Tests for check_internet_connectivity."""

    @patch("src.network_diagnostics.requests.head")
    def test_success(self, mock_head):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_head.return_value = mock_resp

        result = check_internet_connectivity()

        assert result["ok"] is True
        assert result["status_code"] == 200
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], int)

    @patch("src.network_diagnostics.requests.head")
    def test_server_error(self, mock_head):
        mock_resp = Mock()
        mock_resp.status_code = 503
        mock_head.return_value = mock_resp

        result = check_internet_connectivity()

        assert result["ok"] is False
        assert result["status_code"] == 503

    @patch("src.network_diagnostics.requests.head")
    def test_connection_error(self, mock_head):
        mock_head.side_effect = requests.exceptions.ConnectionError("no route")

        result = check_internet_connectivity()

        assert result["ok"] is False
        assert result["status_code"] is None
        assert "error" in result

    @patch("src.network_diagnostics.requests.head")
    def test_timeout_error(self, mock_head):
        mock_head.side_effect = requests.exceptions.Timeout("timed out")

        result = check_internet_connectivity()

        assert result["ok"] is False
        assert "error" in result

    @patch("src.network_diagnostics.requests.head")
    def test_custom_url(self, mock_head):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_head.return_value = mock_resp

        check_internet_connectivity(url="https://example.com")

        mock_head.assert_called_once()
        assert mock_head.call_args[0][0] == "https://example.com"

    @patch("src.network_diagnostics.requests.head")
    def test_redirect_followed(self, mock_head):
        """Redirects (3xx) are followed; a resulting 200 is ok."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_head.return_value = mock_resp

        result = check_internet_connectivity()

        assert result["ok"] is True
        # allow_redirects should be True
        assert mock_head.call_args[1]["allow_redirects"] is True


# ---------------------------------------------------------------------------
# check_port_reachable
# ---------------------------------------------------------------------------

class TestCheckPortReachable:
    """Tests for check_port_reachable."""

    @patch("src.network_diagnostics.socket.create_connection")
    def test_port_open(self, mock_conn):
        mock_sock = Mock()
        mock_conn.return_value = mock_sock

        result = check_port_reachable("192.168.1.10", 7000)

        assert result["ok"] is True
        assert result["host"] == "192.168.1.10"
        assert result["port"] == 7000
        assert "latency_ms" in result
        mock_sock.close.assert_called_once()

    @patch("src.network_diagnostics.socket.create_connection")
    def test_port_closed(self, mock_conn):
        mock_conn.side_effect = OSError("Connection refused")

        result = check_port_reachable("192.168.1.10", 7000)

        assert result["ok"] is False
        assert "error" in result

    @patch("src.network_diagnostics.socket.create_connection")
    def test_timeout(self, mock_conn):
        mock_conn.side_effect = TimeoutError("timed out")

        result = check_port_reachable("192.168.1.10", 7000, timeout=1)

        assert result["ok"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# check_vestaboard_connection
# ---------------------------------------------------------------------------

class TestCheckVestaboardConnection:
    """Tests for check_vestaboard_connection."""

    @patch("src.network_diagnostics.requests.get")
    @patch("src.network_diagnostics.check_port_reachable")
    @patch("src.network_diagnostics.check_dns_resolution")
    def test_local_all_ok(self, mock_dns, mock_port, mock_get):
        mock_dns.return_value = {"ok": True, "hostname": "board.local", "ip": "10.0.0.5"}
        mock_port.return_value = {"ok": True, "host": "board.local", "port": 7000, "latency_ms": 5}
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = check_vestaboard_connection("board.local", api_key="key123")

        assert result["ok"] is True
        assert result["mode"] == "local"
        assert "dns" in result["steps"]
        assert "port" in result["steps"]
        assert "api" in result["steps"]

    @patch("src.network_diagnostics.check_dns_resolution")
    def test_local_dns_failure_short_circuits(self, mock_dns):
        mock_dns.return_value = {"ok": False, "hostname": "bad.local", "ip": None, "error": "fail"}

        result = check_vestaboard_connection("bad.local")

        assert result["ok"] is False
        assert "dns" in result["steps"]
        assert "port" not in result["steps"]
        assert "api" not in result["steps"]

    @patch("src.network_diagnostics.check_port_reachable")
    @patch("src.network_diagnostics.check_dns_resolution")
    def test_local_port_failure_short_circuits(self, mock_dns, mock_port):
        mock_dns.return_value = {"ok": True, "hostname": "board.local", "ip": "10.0.0.5"}
        mock_port.return_value = {"ok": False, "host": "board.local", "port": 7000, "error": "refused"}

        result = check_vestaboard_connection("board.local")

        assert result["ok"] is False
        assert "dns" in result["steps"]
        assert "port" in result["steps"]
        assert "api" not in result["steps"]

    @patch("src.network_diagnostics.requests.get")
    @patch("src.network_diagnostics.check_port_reachable")
    @patch("src.network_diagnostics.check_dns_resolution")
    def test_local_api_failure(self, mock_dns, mock_port, mock_get):
        mock_dns.return_value = {"ok": True, "hostname": "board.local", "ip": "10.0.0.5"}
        mock_port.return_value = {"ok": True, "host": "board.local", "port": 7000, "latency_ms": 5}
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")

        result = check_vestaboard_connection("board.local")

        assert result["ok"] is False
        assert result["steps"]["api"]["ok"] is False

    @patch("src.network_diagnostics.requests.get")
    def test_cloud_success(self, mock_get):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = check_vestaboard_connection(
            host="", use_cloud=True, cloud_key="rw-key-123"
        )

        assert result["ok"] is True
        assert result["mode"] == "cloud"
        assert "cloud_api" in result["steps"]

    @patch("src.network_diagnostics.requests.get")
    def test_cloud_failure(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("no route")

        result = check_vestaboard_connection(
            host="", use_cloud=True, cloud_key="rw-key-123"
        )

        assert result["ok"] is False
        assert result["mode"] == "cloud"

    @patch("src.network_diagnostics.requests.get")
    def test_cloud_server_error(self, mock_get):
        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        result = check_vestaboard_connection(
            host="", use_cloud=True, cloud_key="rw-key-123"
        )

        assert result["ok"] is False


# ---------------------------------------------------------------------------
# run_full_diagnostics
# ---------------------------------------------------------------------------

class TestRunFullDiagnostics:
    """Tests for run_full_diagnostics."""

    @patch("src.network_diagnostics.check_vestaboard_connection")
    @patch("src.network_diagnostics.check_internet_connectivity")
    @patch("src.network_diagnostics.check_dns_resolution")
    def test_all_ok_local(self, mock_dns, mock_internet, mock_vb):
        mock_dns.return_value = {"ok": True, "hostname": "google.com", "ip": "1.2.3.4"}
        mock_internet.return_value = {"ok": True, "url": "https://www.google.com", "status_code": 200, "latency_ms": 50}
        mock_vb.return_value = {"ok": True, "mode": "local", "steps": {}}

        result = run_full_diagnostics(board_host="board.local", board_api_key="key")

        assert result["overall_ok"] is True
        assert "dns" in result
        assert "internet" in result
        assert "vestaboard" in result

    @patch("src.network_diagnostics.check_vestaboard_connection")
    @patch("src.network_diagnostics.check_internet_connectivity")
    @patch("src.network_diagnostics.check_dns_resolution")
    def test_dns_failure(self, mock_dns, mock_internet, mock_vb):
        mock_dns.return_value = {"ok": False, "hostname": "google.com", "ip": None, "error": "fail"}
        mock_internet.return_value = {"ok": True, "url": "https://www.google.com", "status_code": 200, "latency_ms": 50}
        mock_vb.return_value = {"ok": True, "mode": "local", "steps": {}}

        result = run_full_diagnostics(board_host="board.local", board_api_key="key")

        assert result["overall_ok"] is False

    @patch("src.network_diagnostics.check_internet_connectivity")
    @patch("src.network_diagnostics.check_dns_resolution")
    def test_no_board_configured(self, mock_dns, mock_internet):
        mock_dns.return_value = {"ok": True, "hostname": "google.com", "ip": "1.2.3.4"}
        mock_internet.return_value = {"ok": True, "url": "https://www.google.com", "status_code": 200, "latency_ms": 50}

        result = run_full_diagnostics()

        assert result["overall_ok"] is False
        assert "No board host" in result["vestaboard"].get("error", "")

    @patch("src.network_diagnostics.check_vestaboard_connection")
    @patch("src.network_diagnostics.check_internet_connectivity")
    @patch("src.network_diagnostics.check_dns_resolution")
    def test_cloud_mode(self, mock_dns, mock_internet, mock_vb):
        mock_dns.return_value = {"ok": True, "hostname": "google.com", "ip": "1.2.3.4"}
        mock_internet.return_value = {"ok": True, "url": "https://www.google.com", "status_code": 200, "latency_ms": 50}
        mock_vb.return_value = {"ok": True, "mode": "cloud", "steps": {}}

        result = run_full_diagnostics(use_cloud=True, cloud_key="rw-key")

        assert result["overall_ok"] is True
        mock_vb.assert_called_once_with(host="", use_cloud=True, cloud_key="rw-key")

    @patch("src.network_diagnostics.check_vestaboard_connection")
    @patch("src.network_diagnostics.check_internet_connectivity")
    @patch("src.network_diagnostics.check_dns_resolution")
    def test_vestaboard_failure_marks_overall_false(self, mock_dns, mock_internet, mock_vb):
        mock_dns.return_value = {"ok": True, "hostname": "google.com", "ip": "1.2.3.4"}
        mock_internet.return_value = {"ok": True, "url": "https://www.google.com", "status_code": 200, "latency_ms": 50}
        mock_vb.return_value = {"ok": False, "mode": "local", "steps": {"dns": {"ok": False}}}

        result = run_full_diagnostics(board_host="board.local", board_api_key="key")

        assert result["overall_ok"] is False
