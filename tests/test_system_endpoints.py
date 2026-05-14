"""Tests for system management endpoints (update check)."""

import os
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


@pytest.fixture(autouse=True)
def _isolate_state_file(tmp_path):
    """Give every test its own state file to prevent state leaking between tests."""
    with patch("src.api_server.SYSTEM_UPDATE_STATE_FILE", tmp_path / "update_state.json"):
        yield


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
        """Test that Docker Hub is queried and its result takes priority over GitHub Releases.

        Both sources are checked in parallel; Docker Hub's version wins when it succeeds.
        """
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

        github_resp = Mock()
        github_resp.status_code = 200
        github_resp.json.return_value = {"tag_name": "v1.0.0"}  # lower — should not win
        github_resp.raise_for_status = Mock()

        def mock_get(url, **kwargs):
            call_order.append(url)
            if _host_is(url, "hub.docker.com"):
                return tags_resp
            return github_resp

        with patch("src.api_server.requests.get", side_effect=mock_get):
            response = client.get("/system/update-check")

        assert response.status_code == 200
        data = response.json()
        # Docker Hub's version (99.0.0) wins over GitHub's (1.0.0)
        assert data["latest_version"] == "99.0.0"
        assert data["update_available"] is True
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

    def test_sidecar_unreachable_returns_503(self, client, tmp_path, monkeypatch):
        """When the sidecar host is unreachable, we surface a manual fallback."""
        import requests as _requests
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        monkeypatch.setattr(
            "src.api_server.SETTINGS_SNAPSHOT_DIR", tmp_path / "snaps"
        )
        with patch(
            "src.api_server.requests.post",
            side_effect=_requests.exceptions.ConnectionError("nope"),
        ):
            response = client.post("/system/update")
        assert response.status_code == 503
        assert response.json()["detail"]["mode"] == "manual"

    def test_sidecar_rejects_token(self, client, tmp_path, monkeypatch):
        """A 401 from the sidecar means our shared token is misconfigured."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        monkeypatch.setattr(
            "src.api_server.SETTINGS_SNAPSHOT_DIR", tmp_path / "snaps"
        )
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
        monkeypatch.setattr(
            "src.api_server.SETTINGS_SNAPSHOT_DIR",
            tmp_path / "update-backups",
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
        """Legacy ``enabled`` bool: True -> default interval, False -> manual."""
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("src.api_server.SYSTEM_UPDATE_STATE_FILE", state_file)
        # Force a known profile so the default interval is deterministic.
        monkeypatch.setenv("FIESTABOARD_PROFILE", "docker")

        r1 = client.post("/system/update/auto", json={"enabled": True})
        assert r1.status_code == 200
        body1 = r1.json()
        assert body1["enabled"] is True
        # docker profile defaults to "weekly"
        assert body1["interval"] == "weekly"
        import json as _json
        persisted = _json.loads(state_file.read_text())
        assert persisted["auto_update_enabled"] is True
        assert persisted["auto_update_interval"] == "weekly"

        r2 = client.post("/system/update/auto", json={"enabled": False})
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["enabled"] is False
        assert body2["interval"] == "manual"
        persisted = _json.loads(state_file.read_text())
        assert persisted["auto_update_enabled"] is False
        assert persisted["auto_update_interval"] == "manual"

    def test_persists_interval(self, client, tmp_path, monkeypatch):
        """The ``interval`` field is persisted and echoed back."""
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("src.api_server.SYSTEM_UPDATE_STATE_FILE", state_file)
        import json as _json

        for interval, expected_enabled in [
            ("daily", True),
            ("weekly", True),
            ("monthly", True),
            ("manual", False),
        ]:
            r = client.post("/system/update/auto", json={"interval": interval})
            assert r.status_code == 200, (interval, r.json())
            body = r.json()
            assert body["interval"] == interval
            assert body["enabled"] is expected_enabled
            persisted = _json.loads(state_file.read_text())
            assert persisted["auto_update_interval"] == interval
            assert persisted["auto_update_enabled"] is expected_enabled

    def test_invalid_interval_rejected(self, client, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("src.api_server.SYSTEM_UPDATE_STATE_FILE", state_file)

        r = client.post("/system/update/auto", json={"interval": "hourly"})
        assert r.status_code == 422

    def test_empty_body_rejected(self, client, tmp_path, monkeypatch):
        """Must provide either ``interval`` or ``enabled``."""
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("src.api_server.SYSTEM_UPDATE_STATE_FILE", state_file)

        r = client.post("/system/update/auto", json={})
        assert r.status_code == 422

    def test_status_reports_default_interval_when_unset(self, client, tmp_path, monkeypatch):
        """Fresh state file -> default interval based on profile."""
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("src.api_server.SYSTEM_UPDATE_STATE_FILE", state_file)
        monkeypatch.setenv("FIESTABOARD_PROFILE", "docker")

        r = client.get("/system/update/status")
        assert r.status_code == 200
        body = r.json()
        assert body["auto_update_interval"] == "weekly"
        assert body["auto_update_enabled"] is True

    def test_status_reports_pi_default_interval(self, client, tmp_path, monkeypatch):
        """FiestaPi profile defaults to ``daily`` (matching the prior auto-update-on behavior)."""
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("src.api_server.SYSTEM_UPDATE_STATE_FILE", state_file)
        monkeypatch.setenv("FIESTABOARD_PROFILE", "pi")

        r = client.get("/system/update/status")
        assert r.status_code == 200
        body = r.json()
        assert body["auto_update_interval"] == "daily"
        assert body["auto_update_enabled"] is True

    def test_status_legacy_bool_maps_to_interval(self, client, tmp_path, monkeypatch):
        """A state file with only the legacy bool maps to a sane interval."""
        state_file = tmp_path / "state.json"
        state_file.write_text('{"auto_update_enabled": false}')
        monkeypatch.setattr("src.api_server.SYSTEM_UPDATE_STATE_FILE", state_file)

        r = client.get("/system/update/status")
        assert r.status_code == 200
        body = r.json()
        assert body["auto_update_interval"] == "manual"
        assert body["auto_update_enabled"] is False


class TestUpdateCheckDueHelper:
    """Tests for the ``_is_update_check_due`` background-loop helper."""

    def test_no_last_check_is_due(self):
        from src.api_server import _is_update_check_due
        assert _is_update_check_due({}, period_days=7) is True

    def test_recent_check_not_due(self):
        from src.api_server import _is_update_check_due
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc).isoformat()
        assert _is_update_check_due({"last_check": recent}, period_days=7) is False

    def test_old_check_is_due(self):
        from src.api_server import _is_update_check_due
        from datetime import datetime, timezone, timedelta
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        assert _is_update_check_due({"last_check": old}, period_days=7) is True

    def test_manual_period_never_due(self):
        from src.api_server import _is_update_check_due
        # period_days <= 0 means "manual"; never run regardless of last_check
        assert _is_update_check_due({}, period_days=0) is False

    def test_malformed_last_check_treated_as_due(self):
        from src.api_server import _is_update_check_due
        assert _is_update_check_due({"last_check": "not-a-date"}, period_days=7) is True


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


class TestFormulaFunctions:
    """Tests for GET /templates/formula-functions endpoint."""

    def test_returns_200(self, client):
        response = client.get("/templates/formula-functions")
        assert response.status_code == 200

    def test_has_functions_key(self, client):
        data = client.get("/templates/formula-functions").json()
        assert "functions" in data
        assert isinstance(data["functions"], dict)

    def test_contains_known_builtins(self, client):
        functions = client.get("/templates/formula-functions").json()["functions"]
        for name in ("IF", "ROUND", "UPPER", "COLOR", "IFERROR"):
            assert name in functions, f"Expected built-in {name!r} to be present"

    def test_each_entry_has_required_fields(self, client):
        functions = client.get("/templates/formula-functions").json()["functions"]
        for name, entry in functions.items():
            assert "category" in entry, f"{name} missing 'category'"
            assert "signature" in entry, f"{name} missing 'signature'"
            assert "summary" in entry, f"{name} missing 'summary'"


# =============================================================================
# Tests for the 5.1 update-rollback features:
#   * pre-update settings snapshots (5-deep retention)
#   * /system/update/status surfacing the sidecar's last-update result
#   * POST /system/update/rollback (settings + image)
# =============================================================================


class TestSettingsSnapshots:
    """Direct tests for the snapshot helper functions in api_server."""

    def test_take_snapshot_creates_file(self, tmp_path, monkeypatch):
        """A snapshot file lands in SETTINGS_SNAPSHOT_DIR with valid JSON."""
        from src import api_server as api
        snap_dir = tmp_path / "update-backups"
        monkeypatch.setattr(api, "SETTINGS_SNAPSHOT_DIR", snap_dir)

        meta = api._take_settings_snapshot()
        assert meta is not None
        assert snap_dir.exists()
        files = list(snap_dir.iterdir())
        assert len(files) == 1
        assert files[0].name.startswith("pre-update-")
        assert files[0].name.endswith(".json")
        # Snapshot is a BackupService document.
        import json as _json
        with files[0].open() as fh:
            doc = _json.load(fh)
        assert doc.get("fiestaboard_backup") is True
        assert "data" in doc

    def test_retention_keeps_only_five(self, tmp_path, monkeypatch):
        """Six snapshots → only the newest five remain after pruning."""
        from src import api_server as api
        snap_dir = tmp_path / "update-backups"
        monkeypatch.setattr(api, "SETTINGS_SNAPSHOT_DIR", snap_dir)

        # Take six snapshots, with monotonically increasing timestamps so
        # mtime ordering matches creation order.
        for i in range(6):
            meta = api._take_settings_snapshot()
            assert meta is not None
            # Bump mtime forward so each file is strictly newer than the
            # last; otherwise consecutive snapshots within the same second
            # may be retained in an unstable order on fast hardware.
            path = snap_dir / meta["name"]
            os.utime(path, (1_700_000_000 + i, 1_700_000_000 + i))

        survivors = api._list_settings_snapshots()
        assert len(survivors) == 5

    def test_resolve_rejects_path_traversal(self, tmp_path, monkeypatch):
        """``..`` and absolute paths must not escape the snapshot dir."""
        from src import api_server as api
        snap_dir = tmp_path / "update-backups"
        monkeypatch.setattr(api, "SETTINGS_SNAPSHOT_DIR", snap_dir)
        snap_dir.mkdir()
        # Plant a tempting target outside the snapshot dir.
        (tmp_path / "secret.json").write_text('{"fiestaboard_backup":true}')

        for evil in (
            "../secret.json",
            "..\\secret.json",
            "/etc/passwd",
            "pre-update-../secret.json",
            "not-a-snapshot.json",
        ):
            assert api._resolve_snapshot_name(evil) is None

    def test_resolve_returns_newest_when_name_omitted(self, tmp_path, monkeypatch):
        """Calling ``_resolve_snapshot_name(None)`` returns the latest snapshot."""
        from src import api_server as api
        snap_dir = tmp_path / "update-backups"
        monkeypatch.setattr(api, "SETTINGS_SNAPSHOT_DIR", snap_dir)
        m1 = api._take_settings_snapshot()
        os.utime(snap_dir / m1["name"], (1_700_000_000, 1_700_000_000))
        m2 = api._take_settings_snapshot()
        os.utime(snap_dir / m2["name"], (1_700_000_500, 1_700_000_500))

        latest = api._resolve_snapshot_name(None)
        assert latest is not None
        assert latest.name == m2["name"]


class TestSystemUpdateStatusRollbackFields:
    """``/system/update/status`` surfaces the sidecar's last-update result."""

    def test_status_includes_sidecar_last_update(self, client, tmp_path, monkeypatch):
        """A rolled-back attempt is reflected in the status payload."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        monkeypatch.setattr(
            "src.api_server.SYSTEM_UPDATE_STATE_FILE", tmp_path / "state.json"
        )
        monkeypatch.setattr(
            "src.api_server.SETTINGS_SNAPSHOT_DIR", tmp_path / "snaps"
        )

        # Mock both /healthz (probe) and /last-update with one fake `requests.get`.
        def _fake_get(url, **_kwargs):
            if url.endswith("/healthz"):
                return Mock(status_code=200)
            if url.endswith("/last-update"):
                last = Mock(status_code=200)
                last.json.return_value = {
                    "status": "rolled_back",
                    "action": "rollback",
                    "previous_digest": "sha256:bad",
                    "target_digest": "sha256:old",
                    "rolled_back_to": "sha256:old",
                    "completed_at": "2026-05-03T12:00:00Z",
                }
                return last
            return Mock(status_code=404)

        with patch("src.api_server.requests.get", side_effect=_fake_get):
            r = client.get("/system/update/status")
        assert r.status_code == 200
        body = r.json()
        assert body["updater_available"] is True
        assert body["last_update_status"] == "rolled_back"
        assert body["last_update_action"] == "rollback"
        assert body["last_update_previous_digest"] == "sha256:bad"
        assert body["last_update_completed_at"] == "2026-05-03T12:00:00Z"

    def test_status_skips_last_update_when_sidecar_unreachable(
        self, client, tmp_path, monkeypatch
    ):
        """If the sidecar is down, status must not pretend to know its state."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        monkeypatch.setattr(
            "src.api_server.SYSTEM_UPDATE_STATE_FILE", tmp_path / "state.json"
        )
        monkeypatch.setattr(
            "src.api_server.SETTINGS_SNAPSHOT_DIR", tmp_path / "snaps"
        )
        with patch("src.api_server.requests.get", side_effect=Exception("boom")):
            r = client.get("/system/update/status")
        assert r.status_code == 200
        body = r.json()
        assert body["updater_available"] is False
        assert body["last_update_status"] is None

    def test_status_lists_settings_snapshots(self, client, tmp_path, monkeypatch):
        """Status payload lists snapshots so the UI can offer rollback."""
        from src import api_server as api
        snap_dir = tmp_path / "snaps"
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        monkeypatch.setattr(
            "src.api_server.SYSTEM_UPDATE_STATE_FILE", tmp_path / "state.json"
        )
        monkeypatch.setattr(api, "SETTINGS_SNAPSHOT_DIR", snap_dir)
        api._take_settings_snapshot()
        api._take_settings_snapshot()

        # Sidecar unreachable so we don't try to parse last-update.
        with patch("src.api_server.requests.get", side_effect=Exception("nope")):
            r = client.get("/system/update/status")
        body = r.json()
        assert len(body["settings_snapshots"]) == 2
        for snap in body["settings_snapshots"]:
            assert snap["name"].startswith("pre-update-")
            assert snap["name"].endswith(".json")
            assert snap["bytes"] > 0


class TestSystemUpdateApplyTakesSnapshot:
    """``POST /system/update`` snapshots settings before queuing the update."""

    def test_snapshot_returned_in_apply_response(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        monkeypatch.setattr(
            "src.api_server.SYSTEM_UPDATE_STATE_FILE", tmp_path / "state.json"
        )
        snap_dir = tmp_path / "update-backups"
        monkeypatch.setattr("src.api_server.SETTINGS_SNAPSHOT_DIR", snap_dir)

        ok = Mock(status_code=202)
        ok.json.return_value = {"previous_digest": "sha256:abc"}
        with patch("src.api_server.requests.post", return_value=ok):
            r = client.post("/system/update")
        assert r.status_code == 200
        body = r.json()
        assert body["settings_snapshot"] is not None
        assert body["settings_snapshot"]["name"].startswith("pre-update-")
        assert (snap_dir / body["settings_snapshot"]["name"]).exists()


class TestSystemUpdateRollback:
    """``POST /system/update/rollback`` rolls settings + image back."""

    def test_404_when_no_snapshots_exist(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "src.api_server.SETTINGS_SNAPSHOT_DIR", tmp_path / "empty"
        )
        r = client.post("/system/update/rollback", json={"restore_image": False})
        assert r.status_code == 404

    def test_404_for_unknown_named_snapshot(self, client, tmp_path, monkeypatch):
        snap_dir = tmp_path / "snaps"
        snap_dir.mkdir()
        monkeypatch.setattr("src.api_server.SETTINGS_SNAPSHOT_DIR", snap_dir)
        r = client.post(
            "/system/update/rollback",
            json={"snapshot": "pre-update-20260101T000000Z.json", "restore_image": False},
        )
        assert r.status_code == 404

    def test_404_rejects_path_traversal(self, client, tmp_path, monkeypatch):
        snap_dir = tmp_path / "snaps"
        snap_dir.mkdir()
        monkeypatch.setattr("src.api_server.SETTINGS_SNAPSHOT_DIR", snap_dir)
        # Plant an actual backup-shaped file outside the snap dir.
        (tmp_path / "secret.json").write_text(
            '{"fiestaboard_backup":true,"schema_version":1,"data":{}}'
        )
        r = client.post(
            "/system/update/rollback",
            json={"snapshot": "../secret.json", "restore_image": False},
        )
        assert r.status_code == 404

    def test_400_when_neither_settings_nor_image_requested(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "src.api_server.SETTINGS_SNAPSHOT_DIR", tmp_path / "snaps"
        )
        r = client.post(
            "/system/update/rollback",
            json={"restore_settings": False, "restore_image": False},
        )
        assert r.status_code == 400

    def test_settings_only_happy_path(self, client, tmp_path, monkeypatch):
        from src import api_server as api
        snap_dir = tmp_path / "snaps"
        monkeypatch.setattr(api, "SETTINGS_SNAPSHOT_DIR", snap_dir)

        # Point BackupService at an isolated data dir so the test can't
        # mutate the real repository's data/.
        from src.backup import service as backup_service
        bs = backup_service.BackupService(data_dir=tmp_path / "data")
        monkeypatch.setattr(backup_service, "_backup_service", bs)
        # Seed a settings file so the snapshot has something to capture.
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "settings.json").write_text('{"k":"v"}')

        # Take a snapshot, then mutate the on-disk file.
        meta = api._take_settings_snapshot()
        assert meta is not None
        (tmp_path / "data" / "settings.json").write_text('{"k":"NEW"}')

        # Stub the post-restore service-reload helpers — the real reloads
        # touch global singletons we don't want to mess with from tests.
        monkeypatch.setattr(backup_service, "_reload_services", lambda: [])

        # Settings-only rollback (restore_image=False so we don't need
        # to mock the sidecar's /rollback endpoint).
        r = client.post("/system/update/rollback", json={"restore_image": False})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "success"
        assert body["snapshot"] == meta["name"]
        assert body["image_rollback"] is None
        assert "settings.json" in body["settings_rollback"]["restored_files"]
        # The original value is back.
        import json as _json
        with (tmp_path / "data" / "settings.json").open() as fh:
            assert _json.load(fh) == {"k": "v"}

    def test_image_rollback_calls_sidecar_with_snapshot_metadata(
        self, client, tmp_path, monkeypatch
    ):
        """When ``restore_image=True``, the sidecar /rollback is called
        with the digest+image recorded inside the snapshot.

        Settings-restore is also enabled (the default) so we exercise the
        full end-to-end path.
        """
        from src import api_server as api
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        snap_dir = tmp_path / "snaps"
        monkeypatch.setattr(api, "SETTINGS_SNAPSHOT_DIR", snap_dir)
        from src.backup import service as backup_service
        bs = backup_service.BackupService(data_dir=tmp_path / "data")
        monkeypatch.setattr(backup_service, "_backup_service", bs)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "settings.json").write_text('{"k":"v"}')
        monkeypatch.setattr(backup_service, "_reload_services", lambda: [])

        # Take a snapshot annotated with a known digest+image.
        digest = "sha256:" + ("a" * 64)
        meta = api._take_settings_snapshot(digest, "fiestaboard/fiestaboard:latest")
        assert meta is not None

        captured: Dict[str, Any] = {}

        def _fake_post(url, json=None, **_kwargs):
            captured["url"] = url
            captured["json"] = json
            return Mock(status_code=202)

        with patch("src.api_server.requests.post", side_effect=_fake_post):
            r = client.post("/system/update/rollback", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "success"
        assert body["image_rollback"]["target_digest"] == digest
        assert body["image_rollback"]["target_image"] == "fiestaboard/fiestaboard:latest"
        # Sidecar was called with the digest+image from the snapshot.
        assert captured["url"].endswith("/rollback")
        assert captured["json"] == {
            "digest": digest,
            "image": "fiestaboard/fiestaboard:latest",
        }

    def test_image_rollback_warns_on_unannotated_snapshot(
        self, client, tmp_path, monkeypatch
    ):
        """A snapshot with no recorded digest/image cannot drive the
        sidecar's /rollback — we surface a warning rather than guess."""
        from src import api_server as api
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
        snap_dir = tmp_path / "snaps"
        monkeypatch.setattr(api, "SETTINGS_SNAPSHOT_DIR", snap_dir)
        from src.backup import service as backup_service
        bs = backup_service.BackupService(data_dir=tmp_path / "data")
        monkeypatch.setattr(backup_service, "_backup_service", bs)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "settings.json").write_text('{"k":"v"}')
        monkeypatch.setattr(backup_service, "_reload_services", lambda: [])

        # Snapshot without any digest/image annotation.
        meta = api._take_settings_snapshot()
        assert meta is not None

        # No requests.post mock — if we tried to call the sidecar the
        # test would error out.  We assert we did NOT.
        r = client.post("/system/update/rollback", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "partial"
        assert body["image_rollback"] is None
        assert any("does not record" in w for w in body["warnings"])


class TestUpdaterLastUpdateHelper:
    """``_updater_last_update`` shape contract."""

    def test_returns_dict_on_success(self, monkeypatch):
        from src import api_server as api
        ok = Mock(status_code=200)
        ok.json.return_value = {"status": "success"}
        with patch("src.api_server.requests.get", return_value=ok):
            assert api._updater_last_update() == {"status": "success"}

    def test_returns_empty_on_network_error(self, monkeypatch):
        from src import api_server as api
        with patch("src.api_server.requests.get", side_effect=Exception("nope")):
            assert api._updater_last_update() == {}

    def test_returns_empty_on_non_200(self, monkeypatch):
        from src import api_server as api
        with patch("src.api_server.requests.get", return_value=Mock(status_code=500)):
            assert api._updater_last_update() == {}
