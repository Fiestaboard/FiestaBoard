"""Tests for the /debug/network-diagnostics API endpoint."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestNetworkDiagnosticsEndpoint:
    """Tests for /debug/network-diagnostics."""

    @patch("src.network_diagnostics.run_full_diagnostics")
    def test_success(self, mock_diag, client):
        """Test a successful diagnostics run."""
        mock_diag.return_value = {
            "dns": {"ok": True, "hostname": "google.com", "ip": "1.2.3.4"},
            "internet": {"ok": True, "url": "https://www.google.com", "status_code": 200, "latency_ms": 42},
            "vestaboard": {"ok": True, "mode": "local", "steps": {}},
            "overall_ok": True,
            "recommendations": ["All connectivity checks passed. Your Vestaboard connection is healthy."],
        }

        response = client.get("/debug/network-diagnostics")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "diagnostics" in data
        assert data["diagnostics"]["overall_ok"] is True
        assert "dns" in data["diagnostics"]
        assert "internet" in data["diagnostics"]
        assert "vestaboard" in data["diagnostics"]
        assert "recommendations" in data["diagnostics"]

    @patch("src.network_diagnostics.run_full_diagnostics")
    def test_partial_failure(self, mock_diag, client):
        """Test diagnostics where board is unreachable."""
        mock_diag.return_value = {
            "dns": {"ok": True, "hostname": "google.com", "ip": "1.2.3.4"},
            "internet": {"ok": True, "url": "https://www.google.com", "status_code": 200, "latency_ms": 42},
            "vestaboard": {"ok": False, "mode": "local", "steps": {"dns": {"ok": False}}},
            "overall_ok": False,
            "recommendations": ["Cannot resolve Vestaboard hostname."],
        }

        response = client.get("/debug/network-diagnostics")

        assert response.status_code == 200
        data = response.json()
        assert data["diagnostics"]["overall_ok"] is False
        assert len(data["diagnostics"]["recommendations"]) >= 1

    @patch("src.network_diagnostics.run_full_diagnostics")
    def test_exception_returns_500(self, mock_diag, client):
        """Test that an unexpected error returns 500."""
        mock_diag.side_effect = RuntimeError("boom")

        response = client.get("/debug/network-diagnostics")

        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Network diagnostics failed"

    @patch("src.network_diagnostics.requests.get")
    @patch("src.network_diagnostics.requests.head")
    @patch("src.network_diagnostics.socket.gethostbyname")
    def test_check_failures_do_not_leak_exception_text(self, mock_resolve, mock_head, mock_get, client):
        """Raw exception text from failed checks must never reach the HTTP
        response (CodeQL py/stack-trace-exposure, alert #63)."""
        import socket

        import requests as req

        mock_resolve.side_effect = socket.gaierror("SECRET_INTERNAL_XYZ resolver detail")
        mock_head.side_effect = req.exceptions.ConnectionError("SECRET_INTERNAL_XYZ proxy detail")
        mock_get.side_effect = req.exceptions.ConnectionError("SECRET_INTERNAL_XYZ api detail")

        response = client.get("/debug/network-diagnostics")

        assert response.status_code == 200
        assert "SECRET_INTERNAL_XYZ" not in response.text
        data = response.json()["diagnostics"]
        assert data["dns"]["error"] == "DNS lookup failed"
        assert data["internet"]["error"] == "Could not connect"
