"""Tests for the debug monitor enabled endpoint and Prometheus metrics."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestDebugMonitorEnabled:
    """Tests for /debug/monitor/enabled endpoint."""

    def test_enabled_returns_false_by_default(self, client):
        """Debug mode should be disabled by default."""
        response = client.get("/debug/monitor/enabled")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False

    @patch.dict("os.environ", {"DEBUG_MODE": "true"})
    def test_enabled_returns_true_when_set(self, client):
        """Debug mode should be enabled when DEBUG_MODE=true."""
        response = client.get("/debug/monitor/enabled")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True

    @patch.dict("os.environ", {"DEBUG_MODE": "1"})
    def test_enabled_returns_true_for_1(self, client):
        """Debug mode should be enabled when DEBUG_MODE=1."""
        response = client.get("/debug/monitor/enabled")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True


class TestPrometheusMetrics:
    """Tests for /metrics Prometheus endpoint."""

    def test_metrics_endpoint_returns_prometheus_format(self, client):
        """The /metrics endpoint should return Prometheus text format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_include_system_gauges(self, client):
        """The /metrics endpoint should include FiestaBoard system gauges."""
        response = client.get("/metrics")
        body = response.text
        assert "fiestaboard_system_cpu_percent" in body
        assert "fiestaboard_system_memory_percent" in body
        assert "fiestaboard_system_disk_percent" in body
