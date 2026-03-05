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

    @patch("src.network_diagnostics.run_full_diagnostics")
    def test_partial_failure(self, mock_diag, client):
        """Test diagnostics where board is unreachable."""
        mock_diag.return_value = {
            "dns": {"ok": True, "hostname": "google.com", "ip": "1.2.3.4"},
            "internet": {"ok": True, "url": "https://www.google.com", "status_code": 200, "latency_ms": 42},
            "vestaboard": {"ok": False, "mode": "local", "steps": {"dns": {"ok": False}}},
            "overall_ok": False,
        }

        response = client.get("/debug/network-diagnostics")

        assert response.status_code == 200
        data = response.json()
        assert data["diagnostics"]["overall_ok"] is False

    @patch("src.network_diagnostics.run_full_diagnostics")
    def test_exception_returns_500(self, mock_diag, client):
        """Test that an unexpected error returns 500."""
        mock_diag.side_effect = RuntimeError("boom")

        response = client.get("/debug/network-diagnostics")

        assert response.status_code == 500
