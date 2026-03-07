"""Tests for debug monitor API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
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


class TestDebugMonitorSystem:
    """Tests for /debug/monitor/system endpoint."""

    def test_system_requires_debug_mode(self, client):
        """System metrics should return 403 when debug mode disabled."""
        response = client.get("/debug/monitor/system")
        assert response.status_code == 403
        assert "Debug mode" in response.json()["detail"]

    @patch.dict("os.environ", {"DEBUG_MODE": "true"})
    def test_system_returns_metrics(self, client):
        """System metrics should return CPU, memory, disk, network data."""
        response = client.get("/debug/monitor/system")
        assert response.status_code == 200
        data = response.json()

        assert "cpu" in data
        assert "percent" in data["cpu"]
        assert "count" in data["cpu"]
        assert isinstance(data["cpu"]["count"], int)

        assert "memory" in data
        assert "total_bytes" in data["memory"]
        assert "percent" in data["memory"]

        assert "disk" in data
        assert "total_bytes" in data["disk"]
        assert "percent" in data["disk"]

        assert "network" in data
        assert "bytes_sent" in data["network"]
        assert "bytes_recv" in data["network"]

        assert "system_uptime_seconds" in data


class TestDebugMonitorProcesses:
    """Tests for /debug/monitor/processes endpoint."""

    def test_processes_requires_debug_mode(self, client):
        """Process list should return 403 when debug mode disabled."""
        response = client.get("/debug/monitor/processes")
        assert response.status_code == 403

    @patch.dict("os.environ", {"DEBUG_MODE": "true"})
    def test_processes_returns_list(self, client):
        """Process list should return process data."""
        response = client.get("/debug/monitor/processes")
        assert response.status_code == 200
        data = response.json()

        assert "processes" in data
        assert "total" in data
        assert isinstance(data["processes"], list)
        assert data["total"] == len(data["processes"])


class TestDebugMonitorMetrics:
    """Tests for /debug/monitor/metrics endpoint."""

    def test_metrics_requires_debug_mode(self, client):
        """Metrics should return 403 when debug mode disabled."""
        response = client.get("/debug/monitor/metrics")
        assert response.status_code == 403

    @patch.dict("os.environ", {"DEBUG_MODE": "true"})
    def test_metrics_returns_request_data(self, client):
        """Metrics should return request tracking data."""
        response = client.get("/debug/monitor/metrics")
        assert response.status_code == 200
        data = response.json()

        assert "total_requests" in data
        assert "total_errors" in data
        assert "requests_by_method" in data
        assert "requests_by_status" in data
        assert "error_rate_percent" in data
        assert "uptime_seconds" in data
        assert "service_running" in data
        assert "version" in data
        assert isinstance(data["total_requests"], int)


class TestDebugMonitorErrors:
    """Tests for /debug/monitor/errors endpoint."""

    def test_errors_requires_debug_mode(self, client):
        """Errors should return 403 when debug mode disabled."""
        response = client.get("/debug/monitor/errors")
        assert response.status_code == 403

    @patch.dict("os.environ", {"DEBUG_MODE": "true"})
    def test_errors_returns_error_data(self, client):
        """Errors should return request and log error data."""
        response = client.get("/debug/monitor/errors")
        assert response.status_code == 200
        data = response.json()

        assert "request_errors" in data
        assert "log_errors" in data
        assert "total_request_errors" in data
        assert "total_log_errors" in data
        assert isinstance(data["request_errors"], list)
        assert isinstance(data["log_errors"], list)


class TestDebugMonitorLogs:
    """Tests for /debug/monitor/logs/stream endpoint."""

    def test_logs_requires_debug_mode(self, client):
        """Logs should return 403 when debug mode disabled."""
        response = client.get("/debug/monitor/logs/stream")
        assert response.status_code == 403

    @patch.dict("os.environ", {"DEBUG_MODE": "true"})
    def test_logs_returns_entries(self, client):
        """Logs should return log entries."""
        response = client.get("/debug/monitor/logs/stream")
        assert response.status_code == 200
        data = response.json()

        assert "logs" in data
        assert "total" in data
        assert isinstance(data["logs"], list)

    @patch.dict("os.environ", {"DEBUG_MODE": "true"})
    def test_logs_supports_level_filter(self, client):
        """Logs should support level filter parameter."""
        response = client.get("/debug/monitor/logs/stream?level=ERROR")
        assert response.status_code == 200
        data = response.json()
        assert data["filter_level"] == "ERROR"

    @patch.dict("os.environ", {"DEBUG_MODE": "true"})
    def test_logs_supports_limit(self, client):
        """Logs should support limit parameter."""
        response = client.get("/debug/monitor/logs/stream?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) <= 10
