"""Tests for the debug monitor enabled endpoint and Prometheus metrics."""

import os
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

    @patch.dict("os.environ", {"LOCAL_MONITORING": "true"})
    def test_enabled_returns_true_when_set(self, client):
        """Monitoring should be enabled when LOCAL_MONITORING=true."""
        response = client.get("/debug/monitor/enabled")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True

    @patch.dict("os.environ", {"LOCAL_MONITORING": "1"})
    def test_enabled_returns_true_for_1(self, client):
        """Monitoring should be enabled when LOCAL_MONITORING=1."""
        response = client.get("/debug/monitor/enabled")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True


class TestPrometheusMetrics:
    """Tests for /metrics Prometheus endpoint (only active with LOCAL_MONITORING)."""

    _monitoring_active = os.getenv("LOCAL_MONITORING", "false").lower() in ("true", "1", "yes")

    @pytest.mark.skipif(
        not _monitoring_active,
        reason="Prometheus instrumentation only loaded when LOCAL_MONITORING is enabled",
    )
    def test_metrics_endpoint_returns_prometheus_format(self, client):
        """The /metrics endpoint should return Prometheus text format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    @pytest.mark.skipif(
        not _monitoring_active,
        reason="Prometheus instrumentation only loaded when LOCAL_MONITORING is enabled",
    )
    def test_metrics_include_system_gauges(self, client):
        """The /metrics endpoint should include FiestaBoard system gauges."""
        response = client.get("/metrics")
        body = response.text
        assert "fiestaboard_system_cpu_percent" in body
        assert "fiestaboard_system_memory_percent" in body
        assert "fiestaboard_system_disk_percent" in body

    def test_metrics_endpoint_absent_when_monitoring_disabled(self, client):
        """When LOCAL_MONITORING is off, /metrics should not be registered."""
        if self._monitoring_active:
            pytest.skip("LOCAL_MONITORING is enabled; endpoint exists")
        response = client.get("/metrics")
        assert response.status_code == 404
