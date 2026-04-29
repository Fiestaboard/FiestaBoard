"""Tests for system management endpoints (update check)."""

from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock


def _host_is(url, expected_host):
    """Return True if the URL's host equals (or is a subdomain of) ``expected_host``.

    Used in place of ``"host" in url`` substring checks, which CodeQL flags
    as "Incomplete URL substring sanitization" because they can be tricked
    by URLs like ``https://evil.com/?x=hub.docker.com``.
    """
    host = (urlparse(url).hostname or "").lower()
    expected = expected_host.lower()
    return host == expected or host.endswith("." + expected)


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
            if _host_is(url, "hub.docker.com"):
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
        assert any(_host_is(url, "hub.docker.com") for url in call_order)

    def test_update_check_falls_back_to_github_releases(self, client):
        """Test fallback to GitHub Releases when Docker Hub fails."""
        releases_resp = Mock()
        releases_resp.status_code = 200
        releases_resp.json.return_value = {"tag_name": "v99.0.0"}
        releases_resp.raise_for_status = Mock()

        call_count = {"dockerhub": 0, "github": 0}

        def mock_get(url, **kwargs):
            if _host_is(url, "hub.docker.com"):
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


# =============================================================================
# Tests for self-update sidecar endpoints
# (/system/update/status, /system/update, /system/update/auto)
# =============================================================================

class TestSystemUpdateStatus:
    """Tests for /system/update/status."""

    def test_no_token_means_unavailable(self, client, tmp_path, monkeypatch):
        """Without FIESTAUPDATER_TOKEN we never even probe the sidecar."""
        monkeypatch.delenv("FIESTAUPDATER_TOKEN", raising=False)
        monkeypatch.setattr(
            "src.api_server.SYSTEM_UPDATE_STATE_FILE",
            tmp_path / "state.json",
        )
        response = client.get("/system/update/status")
        assert response.status_code == 200
        data = response.json()
        assert data["updater_available"] is False
        assert "auto_update_enabled" in data
        assert data["profile"] in ("docker", "pi")

    def test_probe_succeeds(self, client, tmp_path, monkeypatch):
        """When the sidecar /healthz returns 200, we report it available."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        monkeypatch.setattr(
            "src.api_server.SYSTEM_UPDATE_STATE_FILE",
            tmp_path / "state.json",
        )
        ok = Mock(status_code=200)
        with patch("src.api_server.requests.get", return_value=ok):
            response = client.get("/system/update/status")
        assert response.status_code == 200
        assert response.json()["updater_available"] is True

    def test_probe_fails_gracefully(self, client, tmp_path, monkeypatch):
        """A network error during the probe must not 500."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        monkeypatch.setattr(
            "src.api_server.SYSTEM_UPDATE_STATE_FILE",
            tmp_path / "state.json",
        )
        with patch("src.api_server.requests.get", side_effect=Exception("boom")):
            response = client.get("/system/update/status")
        assert response.status_code == 200
        assert response.json()["updater_available"] is False


class TestSystemUpdateApply:
    """Tests for POST /system/update."""

    def test_no_token_returns_503_manual(self, client, monkeypatch):
        """When no token is configured, fall back to manual instructions."""
        monkeypatch.delenv("FIESTAUPDATER_TOKEN", raising=False)
        response = client.post("/system/update")
        assert response.status_code == 503
        body = response.json()["detail"]
        assert body["mode"] == "manual"
        assert "docker compose" in body["hint"]

    def test_sidecar_unreachable_returns_503(self, client, monkeypatch):
        """When the sidecar host is unreachable, we surface a manual fallback."""
        import requests as _requests
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        with patch(
            "src.api_server.requests.post",
            side_effect=_requests.exceptions.ConnectionError("nope"),
        ):
            response = client.post("/system/update")
        assert response.status_code == 503
        assert response.json()["detail"]["mode"] == "manual"

    def test_sidecar_rejects_token(self, client, monkeypatch):
        """A 401 from the sidecar means our shared token is misconfigured."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        bad = Mock(status_code=401, text="invalid_token")
        with patch("src.api_server.requests.post", return_value=bad):
            response = client.post("/system/update")
        assert response.status_code == 500
        assert "FIESTAUPDATER_TOKEN" in response.json()["detail"]["error"]

    def test_happy_path_returns_queued(self, client, tmp_path, monkeypatch):
        """A 202 from the sidecar yields {status: queued, mode: sidecar}."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        monkeypatch.setattr(
            "src.api_server.SYSTEM_UPDATE_STATE_FILE",
            tmp_path / "state.json",
        )
        ok = Mock(status_code=202)
        ok.json.return_value = {"previous_digest": "sha256:abc"}
        with patch("src.api_server.requests.post", return_value=ok):
            response = client.post("/system/update")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["mode"] == "sidecar"
        assert data["previous_digest"] == "sha256:abc"


class TestSystemUpdateAutoToggle:
    """Tests for POST /system/update/auto."""

    def test_persists_enabled_flag(self, client, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("src.api_server.SYSTEM_UPDATE_STATE_FILE", state_file)

        r1 = client.post("/system/update/auto", json={"enabled": True})
        assert r1.status_code == 200
        assert r1.json()["enabled"] is True
        import json as _json
        assert _json.loads(state_file.read_text())["auto_update_enabled"] is True

        r2 = client.post("/system/update/auto", json={"enabled": False})
        assert r2.status_code == 200
        assert r2.json()["enabled"] is False
        assert _json.loads(state_file.read_text())["auto_update_enabled"] is False


# =============================================================================
# Tests for /system/restart
# =============================================================================

class TestSystemRestart:
    """Tests for POST /system/restart."""

    def test_no_token_returns_503(self, client, monkeypatch):
        monkeypatch.delenv("FIESTAUPDATER_TOKEN", raising=False)
        response = client.post("/system/restart")
        assert response.status_code == 503
        assert "hint" in response.json()["detail"]

    def test_sidecar_unreachable_returns_503(self, client, monkeypatch):
        import requests as _requests
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        with patch(
            "src.api_server.requests.post",
            side_effect=_requests.exceptions.ConnectionError("nope"),
        ):
            response = client.post("/system/restart")
        assert response.status_code == 503

    def test_sidecar_rejects_token_returns_500(self, client, monkeypatch):
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        bad = Mock(status_code=401, text="invalid_token")
        with patch("src.api_server.requests.post", return_value=bad):
            response = client.post("/system/restart")
        assert response.status_code == 500
        assert "FIESTAUPDATER_TOKEN" in response.json()["detail"]["error"]

    def test_happy_path_returns_queued(self, client, monkeypatch):
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        ok = Mock(status_code=202)
        ok.json.return_value = {"status": "queued", "action": "restart"}
        with patch("src.api_server.requests.post", return_value=ok):
            response = client.post("/system/restart")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["action"] == "restart"


# =============================================================================
# Tests for /system/shutdown
# =============================================================================

class TestSystemShutdown:
    """Tests for POST /system/shutdown."""

    def test_no_token_returns_503(self, client, monkeypatch):
        monkeypatch.delenv("FIESTAUPDATER_TOKEN", raising=False)
        response = client.post("/system/shutdown")
        assert response.status_code == 503
        assert "hint" in response.json()["detail"]

    def test_sidecar_unreachable_returns_503(self, client, monkeypatch):
        import requests as _requests
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        with patch(
            "src.api_server.requests.post",
            side_effect=_requests.exceptions.ConnectionError("nope"),
        ):
            response = client.post("/system/shutdown")
        assert response.status_code == 503

    def test_sidecar_rejects_token_returns_500(self, client, monkeypatch):
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        bad = Mock(status_code=401, text="invalid_token")
        with patch("src.api_server.requests.post", return_value=bad):
            response = client.post("/system/shutdown")
        assert response.status_code == 500
        assert "FIESTAUPDATER_TOKEN" in response.json()["detail"]["error"]

    def test_happy_path_returns_queued(self, client, monkeypatch):
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        ok = Mock(status_code=202)
        ok.json.return_value = {"status": "queued", "action": "shutdown"}
        with patch("src.api_server.requests.post", return_value=ok):
            response = client.post("/system/shutdown")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["action"] == "shutdown"
