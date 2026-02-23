"""Tests for system management endpoints (update check and restart)."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, MagicMock


@pytest.fixture
def client():
    """Create a test client."""
    from src.api_server import app
    return TestClient(app)


class TestUpdateCheck:
    """Tests for /system/update-check endpoint."""

    def test_update_available(self, client):
        """Test when a newer version is available."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tag_name": "v99.0.0"}
        mock_response.raise_for_status = Mock()

        with patch("src.api_server.requests.get", return_value=mock_response):
            response = client.get("/system/update-check")
        
        assert response.status_code == 200
        data = response.json()
        assert data["update_available"] is True
        assert data["latest_version"] == "99.0.0"
        assert data["current_version"] is not None
        assert data["package_url"] == "https://github.com/Fiestaboard/FiestaBoard/pkgs/container/fiestaboard"

    def test_up_to_date(self, client):
        """Test when current version matches latest."""
        from src import __version__
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tag_name": f"v{__version__}"}
        mock_response.raise_for_status = Mock()

        with patch("src.api_server.requests.get", return_value=mock_response):
            response = client.get("/system/update-check")
        
        assert response.status_code == 200
        data = response.json()
        assert data["update_available"] is False
        assert data["latest_version"] == __version__
        assert data["current_version"] == __version__

    def test_github_api_failure(self, client):
        """Test graceful handling when GitHub API is unreachable."""
        with patch("src.api_server.requests.get", side_effect=Exception("Network error")):
            response = client.get("/system/update-check")
        
        assert response.status_code == 200
        data = response.json()
        assert data["update_available"] is False
        assert data["latest_version"] is None
        assert data["error"] is not None
        assert "Could not check for updates" in data["error"]

    def test_production_flag(self, client):
        """Test is_production flag is correctly set."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tag_name": "v1.0.0"}
        mock_response.raise_for_status = Mock()

        with patch("src.api_server.requests.get", return_value=mock_response), \
             patch.dict("os.environ", {"PRODUCTION": "true"}):
            response = client.get("/system/update-check")
        
        assert response.status_code == 200
        assert response.json()["is_production"] is True

    def test_tag_name_without_v_prefix(self, client):
        """Test parsing tag names without 'v' prefix."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tag_name": "99.0.0"}
        mock_response.raise_for_status = Mock()

        with patch("src.api_server.requests.get", return_value=mock_response):
            response = client.get("/system/update-check")
        
        assert response.status_code == 200
        data = response.json()
        assert data["latest_version"] == "99.0.0"
        assert data["update_available"] is True


class TestSystemRestart:
    """Tests for /system/restart endpoint."""

    def test_restart_blocked_in_dev_mode(self, client):
        """Test restart is rejected in non-production mode."""
        with patch.dict("os.environ", {"PRODUCTION": "false"}):
            response = client.post("/system/restart")
        
        assert response.status_code == 400
        assert "production" in response.json()["detail"].lower()

    def test_restart_in_production(self, client):
        """Test restart succeeds in production mode."""
        mock_docker = Mock()
        mock_docker.restart_container = Mock()

        with patch.dict("os.environ", {"PRODUCTION": "true"}), \
             patch("src.system.docker_manager.get_docker_manager", return_value=mock_docker):
            response = client.post("/system/restart")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "restart" in data["message"].lower()


class TestIsNewerVersion:
    """Tests for _is_newer_version helper."""

    def test_newer_major(self):
        from src.api_server import _is_newer_version
        assert _is_newer_version("3.0.0", "2.0.0") is True

    def test_newer_minor(self):
        from src.api_server import _is_newer_version
        assert _is_newer_version("2.1.0", "2.0.0") is True

    def test_newer_patch(self):
        from src.api_server import _is_newer_version
        assert _is_newer_version("2.0.1", "2.0.0") is True

    def test_same_version(self):
        from src.api_server import _is_newer_version
        assert _is_newer_version("2.0.0", "2.0.0") is False

    def test_older_version(self):
        from src.api_server import _is_newer_version
        assert _is_newer_version("1.9.0", "2.0.0") is False

    def test_invalid_version(self):
        from src.api_server import _is_newer_version
        assert _is_newer_version("invalid", "2.0.0") is False

    def test_empty_string(self):
        from src.api_server import _is_newer_version
        assert _is_newer_version("", "2.0.0") is False
