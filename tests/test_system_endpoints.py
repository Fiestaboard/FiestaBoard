"""Tests for system management endpoints (update check)."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock


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
        assert data["package_url"] == "https://github.com/Fiestaboard/FiestaBoard/releases/latest"

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


class TestDockerHubCheck:
    """Tests for Docker Hub version checking."""

    def test_dockerhub_check_returns_latest_version(self):
        """Test Docker Hub check correctly finds the highest semver tag."""
        from src.api_server import _check_dockerhub_for_latest

        tags_resp = Mock()
        tags_resp.status_code = 200
        tags_resp.json.return_value = {
            "results": [
                {"name": "latest"},
                {"name": "2.0.0"},
                {"name": "2.0.1"},
                {"name": "2.1.0"},
                {"name": "main"}
            ]
        }
        tags_resp.raise_for_status = Mock()

        with patch("src.api_server.requests.get", return_value=tags_resp):
            result = _check_dockerhub_for_latest()

        assert result == "2.1.0"

    def test_dockerhub_check_no_version_tags(self):
        """Test Docker Hub check returns None when no semver tags exist."""
        from src.api_server import _check_dockerhub_for_latest

        tags_resp = Mock()
        tags_resp.status_code = 200
        tags_resp.json.return_value = {
            "results": [
                {"name": "latest"},
                {"name": "main"},
                {"name": "dev"}
            ]
        }
        tags_resp.raise_for_status = Mock()

        with patch("src.api_server.requests.get", return_value=tags_resp):
            result = _check_dockerhub_for_latest()

        assert result is None

    def test_dockerhub_check_network_failure(self):
        """Test Docker Hub check returns None on network error."""
        from src.api_server import _check_dockerhub_for_latest

        with patch("src.api_server.requests.get", side_effect=Exception("Connection refused")):
            result = _check_dockerhub_for_latest()

        assert result is None

    def test_dockerhub_check_empty_results(self):
        """Test Docker Hub check returns None when results array is empty."""
        from src.api_server import _check_dockerhub_for_latest

        tags_resp = Mock()
        tags_resp.status_code = 200
        tags_resp.json.return_value = {"results": []}
        tags_resp.raise_for_status = Mock()

        with patch("src.api_server.requests.get", return_value=tags_resp):
            result = _check_dockerhub_for_latest()

        assert result is None

    def test_update_check_uses_dockerhub_first(self, client):
        """Test that update-check tries Docker Hub before falling back to GitHub Releases."""
        from src import __version__

        call_order = []

        tags_resp = Mock()
        tags_resp.status_code = 200
        tags_resp.json.return_value = {
            "results": [
                {"name": "99.0.0"},
                {"name": "2.0.0"}
            ]
        }
        tags_resp.raise_for_status = Mock()

        def mock_get(url, **kwargs):
            call_order.append(url)
            if "hub.docker.com" in url:
                return tags_resp
            # GitHub Releases should NOT be called
            raise AssertionError("Should not reach GitHub Releases API")

        with patch("src.api_server.requests.get", side_effect=mock_get):
            response = client.get("/system/update-check")

        assert response.status_code == 200
        data = response.json()
        assert data["latest_version"] == "99.0.0"
        assert data["update_available"] is True
        # Verify Docker Hub was called
        assert any("hub.docker.com" in url for url in call_order)

    def test_update_check_falls_back_to_github_releases(self, client):
        """Test fallback to GitHub Releases when Docker Hub fails."""
        releases_resp = Mock()
        releases_resp.status_code = 200
        releases_resp.json.return_value = {"tag_name": "v99.0.0"}
        releases_resp.raise_for_status = Mock()

        call_count = {"dockerhub": 0, "github": 0}

        def mock_get(url, **kwargs):
            if "hub.docker.com" in url:
                call_count["dockerhub"] += 1
                raise Exception("Docker Hub unavailable")
            call_count["github"] += 1
            return releases_resp

        with patch("src.api_server.requests.get", side_effect=mock_get):
            response = client.get("/system/update-check")

        assert response.status_code == 200
        data = response.json()
        assert data["latest_version"] == "99.0.0"
        assert data["update_available"] is True
        assert call_count["dockerhub"] > 0  # Docker Hub was attempted
        assert call_count["github"] > 0  # GitHub was used as fallback


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
