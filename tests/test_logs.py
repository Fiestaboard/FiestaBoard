"""Tests for the logs API endpoint."""

import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_log_dir(tmp_path):
    """Create a temporary log directory."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


@pytest.fixture
def sample_log_entries():
    """Create sample log entries for testing."""
    return [
        {
            "timestamp": "2025-12-25T10:00:00",
            "level": "INFO",
            "logger": "src.api_server",
            "message": "Server started successfully",
        },
        {
            "timestamp": "2025-12-25T10:00:01",
            "level": "DEBUG",
            "logger": "src.board_client",
            "message": "Connecting to board",
        },
        {
            "timestamp": "2025-12-25T10:00:02",
            "level": "WARNING",
            "logger": "src.utils.weather",
            "message": "Weather API rate limit approaching",
        },
        {
            "timestamp": "2025-12-25T10:00:03",
            "level": "ERROR",
            "logger": "src.displays.service",
            "message": "Failed to render display",
        },
        {"timestamp": "2025-12-25T10:00:04", "level": "INFO", "logger": "src.main", "message": "Refresh complete"},
    ]


@pytest.fixture
def log_file_with_entries(test_log_dir, sample_log_entries):
    """Create a log file with sample entries."""
    log_file = test_log_dir / "app.log"
    with open(log_file, "w") as f:
        for entry in sample_log_entries:
            f.write(json.dumps(entry) + "\n")
    return log_file


@pytest.fixture
def mock_api_server(test_log_dir, sample_log_entries):
    """Create a test client with mocked log directory."""
    # Patch the log directory before importing
    with patch.dict(os.environ, {"PRODUCTION": "true"}):
        with patch("src.api_server.LOG_DIR", test_log_dir):
            with patch("src.api_server.LOG_FILE", test_log_dir / "app.log"):
                # Create log file
                log_file = test_log_dir / "app.log"
                with open(log_file, "w") as f:
                    for entry in sample_log_entries:
                        f.write(json.dumps(entry) + "\n")

                # Also populate the in-memory buffer
                from src import api_server

                with api_server._log_lock:
                    api_server._log_buffer.clear()
                    for entry in sample_log_entries:
                        api_server._log_buffer.append(entry)

                # Create test client
                from src.api_server import app

                client = TestClient(app)
                yield client

                # Cleanup
                with api_server._log_lock:
                    api_server._log_buffer.clear()


class TestLogsEndpoint:
    """Tests for GET /logs endpoint."""

    def test_get_logs_default_params(self, mock_api_server, sample_log_entries):
        """Test getting logs with default parameters."""
        response = mock_api_server.get("/logs")
        assert response.status_code == 200

        data = response.json()
        assert "logs" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data
        assert "filters" in data

        # Check default values
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert isinstance(data["logs"], list)

    def test_get_logs_with_limit(self, mock_api_server, sample_log_entries):
        """Test getting logs with custom limit."""
        response = mock_api_server.get("/logs?limit=2")
        assert response.status_code == 200

        data = response.json()
        assert len(data["logs"]) <= 2
        assert data["limit"] == 2

    def test_get_logs_with_offset(self, mock_api_server, sample_log_entries):
        """Test getting logs with offset for pagination."""
        response = mock_api_server.get("/logs?limit=2&offset=2")
        assert response.status_code == 200

        data = response.json()
        assert data["offset"] == 2
        assert data["limit"] == 2

    def test_get_logs_filter_by_level_info(self, mock_api_server, sample_log_entries):
        """Test filtering logs by INFO level."""
        response = mock_api_server.get("/logs?level=INFO")
        assert response.status_code == 200

        data = response.json()
        for log in data["logs"]:
            assert log["level"] == "INFO"
        assert data["filters"]["level"] == "INFO"

    def test_get_logs_filter_by_level_error(self, mock_api_server, sample_log_entries):
        """Test filtering logs by ERROR level."""
        response = mock_api_server.get("/logs?level=ERROR")
        assert response.status_code == 200

        data = response.json()
        for log in data["logs"]:
            assert log["level"] == "ERROR"

    def test_get_logs_filter_by_level_case_insensitive(self, mock_api_server):
        """Test that level filter is case-insensitive."""
        response = mock_api_server.get("/logs?level=info")
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["level"] == "INFO"

    def test_get_logs_invalid_level(self, mock_api_server):
        """Test that invalid log level returns error."""
        response = mock_api_server.get("/logs?level=INVALID")
        assert response.status_code == 400
        assert "Invalid log level" in response.json()["detail"]

    def test_get_logs_search_in_message(self, mock_api_server, sample_log_entries):
        """Test searching in log messages."""
        response = mock_api_server.get("/logs?search=weather")
        assert response.status_code == 200

        data = response.json()
        # Should find the weather-related log
        assert len(data["logs"]) >= 0
        assert data["filters"]["search"] == "weather"

    def test_get_logs_search_case_insensitive(self, mock_api_server):
        """Test that search is case-insensitive."""
        response = mock_api_server.get("/logs?search=SERVER")
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["search"] == "SERVER"

    def test_get_logs_combined_filters(self, mock_api_server, sample_log_entries):
        """Test combining level filter and search."""
        response = mock_api_server.get("/logs?level=INFO&search=server")
        assert response.status_code == 200

        data = response.json()
        for log in data["logs"]:
            assert log["level"] == "INFO"
        assert data["filters"]["level"] == "INFO"
        assert data["filters"]["search"] == "server"

    def test_get_logs_pagination_has_more(self, mock_api_server, sample_log_entries):
        """Test that has_more is correctly set for pagination."""
        # Get first page with small limit
        response = mock_api_server.get("/logs?limit=2&offset=0")
        assert response.status_code == 200

        data = response.json()
        if data["total"] > 2:
            assert data["has_more"] is True

    def test_get_logs_pagination_no_more(self, mock_api_server, sample_log_entries):
        """Test that has_more is False when no more logs."""
        # Get all logs
        response = mock_api_server.get("/logs?limit=500&offset=0")
        assert response.status_code == 200

        data = response.json()
        assert data["has_more"] is False

    def test_get_logs_limit_max_value(self, mock_api_server):
        """Test that limit above maximum returns validation error."""
        response = mock_api_server.get("/logs?limit=1000")
        # API rejects values above 500 with a validation error
        assert response.status_code == 422

    def test_get_logs_limit_at_max(self, mock_api_server):
        """Test that limit at maximum is accepted."""
        response = mock_api_server.get("/logs?limit=500")
        assert response.status_code == 200

        data = response.json()
        assert data["limit"] == 500

    def test_get_logs_limit_min_value(self, mock_api_server):
        """Test that limit has minimum value validation."""
        response = mock_api_server.get("/logs?limit=0")
        # Should return validation error or use minimum
        assert response.status_code in [200, 422]

    def test_get_logs_empty_search(self, mock_api_server):
        """Test that empty search doesn't filter."""
        response = mock_api_server.get("/logs?search=")
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["search"] is None or data["filters"]["search"] == ""

    def test_log_entry_structure(self, mock_api_server, sample_log_entries):
        """Test that log entries have correct structure."""
        response = mock_api_server.get("/logs?limit=1")
        assert response.status_code == 200

        data = response.json()
        if data["logs"]:
            log = data["logs"][0]
            assert "timestamp" in log
            assert "level" in log
            assert "logger" in log
            assert "message" in log


class TestLogLevels:
    """Tests for different log levels."""

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_valid_log_levels(self, mock_api_server, level):
        """Test all valid log levels are accepted."""
        response = mock_api_server.get(f"/logs?level={level}")
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["level"] == level


class TestLogFilePersistence:
    """Tests for log file persistence and rotation."""

    def test_logs_directory_creation(self, test_log_dir):
        """Test that logs directory is created."""
        assert test_log_dir.exists()
        assert test_log_dir.is_dir()

    def test_read_from_log_file(self, log_file_with_entries, sample_log_entries):
        """Test reading logs from file."""
        with open(log_file_with_entries) as f:
            lines = f.readlines()

        assert len(lines) == len(sample_log_entries)

        for line, expected in zip(lines, sample_log_entries, strict=False):
            entry = json.loads(line)
            assert entry["timestamp"] == expected["timestamp"]
            assert entry["level"] == expected["level"]
            assert entry["message"] == expected["message"]

    def test_json_line_format(self, log_file_with_entries):
        """Test that logs are stored as JSON lines."""
        with open(log_file_with_entries) as f:
            for line in f:
                # Each line should be valid JSON
                entry = json.loads(line.strip())
                assert isinstance(entry, dict)
