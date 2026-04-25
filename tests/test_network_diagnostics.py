"""Tests for network diagnostics module."""

import re
import socket
from unittest.mock import Mock, patch
from urllib.parse import urlparse

import requests

from src.network_diagnostics import (
    _build_recommendations,
    check_dns_resolution,
    check_internet_connectivity,
    check_port_reachable,
    check_vestaboard_connection,
    run_full_diagnostics,
)


_URL_RE = re.compile(r"https?://[^\s'\"<>]+")


def _mentions_host(text, expected_host):
    """Check whether ``text`` contains a URL whose host equals ``expected_host``.

    Used in place of ``"host" in text`` substring checks, which CodeQL
    flags as incomplete URL substring sanitization.
    """
    expected = expected_host.lower()
    for match in _URL_RE.finditer(text):
        host = (urlparse(match.group(0)).hostname or "").lower()
        if host == expected or host.endswith("." + expected):
            return True
    return False

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
# _build_recommendations
# ---------------------------------------------------------------------------

class TestBuildRecommendations:
    """Tests for _build_recommendations troubleshooting output."""

    def test_all_ok_returns_healthy_message(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {"ok": True, "mode": "local", "steps": {}},
        }
        recs = _build_recommendations(results)
        assert len(recs) == 1
        assert "healthy" in recs[0]["summary"].lower()
        assert recs[0]["steps"] == []

    def test_dns_failure_recommends_dns_check(self):
        results = {
            "dns": {"ok": False, "error": "fail"},
            "internet": {"ok": True},
            "vestaboard": {"ok": True, "mode": "local", "steps": {}},
        }
        recs = _build_recommendations(results)
        assert any("cannot look up" in r["summary"].lower() for r in recs)
        # Should suggest common DNS servers
        assert any(
            any("8.8.8.8" in s or "1.1.1.1" in s for s in r["steps"])
            for r in recs
        )

    def test_internet_failure_with_dns_ok_recommends_router(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": False, "error": "timeout"},
            "vestaboard": {"ok": True, "mode": "local", "steps": {}},
        }
        recs = _build_recommendations(results)
        assert any("cannot reach the internet" in r["summary"].lower() for r in recs)
        assert any(
            any("router" in s.lower() for s in r["steps"])
            for r in recs
        )

    def test_internet_failure_with_dns_down_points_to_dns(self):
        results = {
            "dns": {"ok": False, "error": "fail"},
            "internet": {"ok": False, "error": "fail"},
            "vestaboard": {"ok": True, "mode": "local", "steps": {}},
        }
        recs = _build_recommendations(results)
        # Should tell user to fix DNS first
        assert any(
            any("dns" in s.lower() and "fix" in s.lower() for s in r["steps"])
            for r in recs
        )

    def test_no_board_configured_no_extra_recommendation(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {"ok": False, "mode": None, "steps": {}},
        }
        recs = _build_recommendations(results)
        # No board configured should NOT produce a recommendation
        assert len(recs) == 0

    def test_local_dns_failure_recommends_hostname_check(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {
                "ok": False, "mode": "local",
                "steps": {"dns": {"ok": False, "hostname": "myboard.local"}},
            },
        }
        recs = _build_recommendations(results)
        assert any("myboard.local" in r["summary"] for r in recs)
        # Should suggest using IP address
        assert any(
            any("ip" in s.lower() for s in r["steps"])
            for r in recs
        )

    def test_local_port_failure_recommends_local_api(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {
                "ok": False, "mode": "local",
                "steps": {
                    "dns": {"ok": True},
                    "port": {"ok": False, "port": 7000, "error": "refused"},
                },
            },
        }
        recs = _build_recommendations(results)
        assert any("cannot connect" in r["summary"].lower() for r in recs)
        assert any(
            any("local api" in s.lower() for s in r["steps"])
            for r in recs
        )

    def test_local_api_auth_failure_recommends_key_check(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {
                "ok": False, "mode": "local",
                "steps": {
                    "dns": {"ok": True},
                    "port": {"ok": True},
                    "api": {"ok": False, "status_code": 401},
                },
            },
        }
        recs = _build_recommendations(results)
        assert any("api key" in r["summary"].lower() for r in recs)
        # Docs copy points users to enablement token flow (not app Settings)
        assert any(
            any(
                "enablement token" in s.lower()
                or "vestaboard.com/local-api" in s.lower()
                for s in r["steps"]
            )
            for r in recs
        )

    def test_local_api_server_error_recommends_power_cycle(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {
                "ok": False, "mode": "local",
                "steps": {
                    "dns": {"ok": True},
                    "port": {"ok": True},
                    "api": {"ok": False, "status_code": 502},
                },
            },
        }
        recs = _build_recommendations(results)
        assert any(
            any("unplug" in s.lower() for s in r["steps"])
            for r in recs
        )

    def test_local_api_no_response_recommends_retry(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {
                "ok": False, "mode": "local",
                "steps": {
                    "dns": {"ok": True},
                    "port": {"ok": True},
                    "api": {"ok": False, "status_code": None, "error": "timeout"},
                },
            },
        }
        recs = _build_recommendations(results)
        assert any(
            any("starting up" in s.lower() or "try again" in s.lower() for s in r["steps"])
            for r in recs
        )

    def test_cloud_auth_failure_recommends_key_check(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {
                "ok": False, "mode": "cloud",
                "steps": {"cloud_api": {"ok": False, "status_code": 403}},
            },
        }
        recs = _build_recommendations(results)
        assert any("rejected" in r["summary"].lower() for r in recs)
        assert any(
            any(_mentions_host(s, "web.vestaboard.com") for s in r["steps"])
            for r in recs
        )

    def test_cloud_server_error_recommends_wait(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {
                "ok": False, "mode": "cloud",
                "steps": {"cloud_api": {"ok": False, "status_code": 500}},
            },
        }
        recs = _build_recommendations(results)
        assert any("temporarily down" in r["summary"].lower() for r in recs)
        assert any(
            any("wait" in s.lower() for s in r["steps"])
            for r in recs
        )

    def test_cloud_connection_error_recommends_internet(self):
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {
                "ok": False, "mode": "cloud",
                "steps": {"cloud_api": {"ok": False, "status_code": None, "error": "no route"}},
            },
        }
        recs = _build_recommendations(results)
        assert any("cannot reach" in r["summary"].lower() for r in recs)
        assert any(
            any(_mentions_host(s, "rw.vestaboard.com") for s in r["steps"])
            for r in recs
        )

    def test_cloud_fallback_recommends_check(self):
        """Cloud mode with no specific error triggers the fallback recommendation."""
        results = {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {
                "ok": False, "mode": "cloud",
                "steps": {"cloud_api": {"ok": False, "status_code": None}},
            },
        }
        recs = _build_recommendations(results)
        assert len(recs) >= 1
        assert any("BOARD_READ_WRITE_KEY" in s for r in recs for s in r["steps"])

    def test_recommendations_have_summary_and_steps(self):
        """Every recommendation must have a summary string and a steps list."""
        results = {
            "dns": {"ok": False},
            "internet": {"ok": False},
            "vestaboard": {
                "ok": False, "mode": "local",
                "steps": {"dns": {"ok": False, "hostname": "board.local"}},
            },
        }
        recs = _build_recommendations(results)
        assert len(recs) >= 2
        for rec in recs:
            assert isinstance(rec["summary"], str)
            assert isinstance(rec["steps"], list)
            assert len(rec["summary"]) > 0


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
        assert "recommendations" in result
        assert any("healthy" in r["summary"].lower() for r in result["recommendations"])

    @patch("src.network_diagnostics.check_vestaboard_connection")
    @patch("src.network_diagnostics.check_internet_connectivity")
    @patch("src.network_diagnostics.check_dns_resolution")
    def test_dns_failure(self, mock_dns, mock_internet, mock_vb):
        mock_dns.return_value = {"ok": False, "hostname": "google.com", "ip": None, "error": "fail"}
        mock_internet.return_value = {"ok": True, "url": "https://www.google.com", "status_code": 200, "latency_ms": 50}
        mock_vb.return_value = {"ok": True, "mode": "local", "steps": {}}

        result = run_full_diagnostics(board_host="board.local", board_api_key="key")

        assert result["overall_ok"] is False
        assert any("cannot look up" in r["summary"].lower() for r in result["recommendations"])

    @patch("src.network_diagnostics.check_internet_connectivity")
    @patch("src.network_diagnostics.check_dns_resolution")
    def test_no_board_configured(self, mock_dns, mock_internet):
        mock_dns.return_value = {"ok": True, "hostname": "google.com", "ip": "1.2.3.4"}
        mock_internet.return_value = {"ok": True, "url": "https://www.google.com", "status_code": 200, "latency_ms": 50}

        result = run_full_diagnostics()

        assert result["overall_ok"] is False
        assert "No board host" in result["vestaboard"].get("error", "")
        # No specific recommendation for "no board configured" (not useful at this point)

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
        assert len(result["recommendations"]) >= 1
