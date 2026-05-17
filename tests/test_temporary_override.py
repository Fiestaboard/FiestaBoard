"""Integration tests for the temporary override API endpoints.

Uses FastAPI TestClient and mocks the SettingsService + PageService singletons
so no real filesystem or board connection is needed.
"""
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.settings.service import SettingsService, TemporaryOverride


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_settings_file(tmp_path):
    """Return a path to a fresh temporary settings file."""
    return tmp_path / "settings.json"


@pytest.fixture
def settings_service(tmp_settings_file):
    """Real SettingsService backed by a temp file (no board connection needed)."""
    return SettingsService(settings_file=str(tmp_settings_file))


@pytest.fixture
def client(settings_service):
    """TestClient with the settings service singleton patched."""
    with patch("src.api_server.get_settings_service", return_value=settings_service):
        with patch("src.settings.service.get_settings_service", return_value=settings_service):
            yield TestClient(app)


@pytest.fixture
def client_with_page(settings_service, tmp_path):
    """TestClient where a page with id 'page-001' exists."""
    page_mock = MagicMock()
    page_mock.id = "page-001"
    page_mock.name = "Test Page"

    page_service_mock = MagicMock()
    page_service_mock.get_page.side_effect = lambda pid: page_mock if pid == "page-001" else None

    with patch("src.api_server.get_settings_service", return_value=settings_service):
        with patch("src.settings.service.get_settings_service", return_value=settings_service):
            with patch("src.api_server.get_page_service", return_value=page_service_mock):
                with patch("src.api_server.get_carousel_service") as mock_cs:
                    mock_cs.return_value.get_carousel.return_value = None
                    yield TestClient(app), settings_service


# ---------------------------------------------------------------------------
# GET /settings/temporary-override
# ---------------------------------------------------------------------------

class TestGetTemporaryOverride:
    def test_returns_inactive_when_no_override(self, client):
        r = client.get("/settings/temporary-override")
        assert r.status_code == 200
        data = r.json()
        assert data["active"] is False
        assert data["page_id"] is None
        assert data["expires_at"] is None
        assert data["remaining_seconds"] is None
        assert data["revert_mode"] is None
        assert data["revert_page_id"] is None

    def test_returns_active_when_override_set(self, client, settings_service):
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        settings_service.set_temporary_override(
            TemporaryOverride(page_id="p1", expires_at=expires, revert_mode="schedule")
        )
        r = client.get("/settings/temporary-override")
        assert r.status_code == 200
        data = r.json()
        assert data["active"] is True
        assert data["page_id"] == "p1"
        assert data["revert_mode"] == "schedule"
        assert isinstance(data["remaining_seconds"], float)
        assert data["remaining_seconds"] > 0

    def test_returns_inactive_when_override_expired(self, client, settings_service):
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        # Set directly without the auto-clear logic on get
        settings_service._temporary_override = TemporaryOverride(
            page_id="p1", expires_at=past, revert_mode="schedule"
        )
        r = client.get("/settings/temporary-override")
        assert r.status_code == 200
        assert r.json()["active"] is False


# ---------------------------------------------------------------------------
# POST /settings/temporary-override
# ---------------------------------------------------------------------------

class TestSetTemporaryOverride:
    def test_success(self, client_with_page):
        client, _ = client_with_page
        r = client.post(
            "/settings/temporary-override",
            json={"page_id": "page-001", "duration_minutes": 5, "revert_mode": "schedule"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["active"] is True
        assert data["page_id"] == "page-001"
        assert data["revert_mode"] == "schedule"
        assert 280 < data["remaining_seconds"] <= 300

    def test_defaults_revert_mode_to_schedule(self, client_with_page):
        client, _ = client_with_page
        r = client.post(
            "/settings/temporary-override",
            json={"page_id": "page-001", "duration_minutes": 15},
        )
        assert r.status_code == 200
        assert r.json()["revert_mode"] == "schedule"

    def test_invalid_page_returns_404(self, client_with_page):
        client, _ = client_with_page
        r = client.post(
            "/settings/temporary-override",
            json={"page_id": "nonexistent", "duration_minutes": 5},
        )
        assert r.status_code == 404

    def test_missing_page_id_returns_422(self, client_with_page):
        client, _ = client_with_page
        r = client.post(
            "/settings/temporary-override",
            json={"duration_minutes": 5},
        )
        assert r.status_code == 422

    def test_duration_zero_returns_422(self, client_with_page):
        client, _ = client_with_page
        r = client.post(
            "/settings/temporary-override",
            json={"page_id": "page-001", "duration_minutes": 0},
        )
        assert r.status_code == 422

    def test_duration_too_large_returns_422(self, client_with_page):
        client, _ = client_with_page
        r = client.post(
            "/settings/temporary-override",
            json={"page_id": "page-001", "duration_minutes": 481},
        )
        assert r.status_code == 422

    def test_revert_page_without_revert_page_id_returns_422(self, client_with_page):
        client, _ = client_with_page
        r = client.post(
            "/settings/temporary-override",
            json={
                "page_id": "page-001",
                "duration_minutes": 5,
                "revert_mode": "page",
                # no revert_page_id
            },
        )
        assert r.status_code == 422

    def test_persists_to_settings_file(self, client_with_page):
        client, svc = client_with_page
        client.post(
            "/settings/temporary-override",
            json={"page_id": "page-001", "duration_minutes": 10, "revert_mode": "blank"},
        )
        override = svc.get_temporary_override()
        assert override is not None
        assert override.page_id == "page-001"
        assert override.revert_mode == "blank"


# ---------------------------------------------------------------------------
# DELETE /settings/temporary-override
# ---------------------------------------------------------------------------

class TestClearTemporaryOverride:
    def test_clears_active_override(self, client, settings_service):
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        settings_service.set_temporary_override(
            TemporaryOverride(page_id="p1", expires_at=expires, revert_mode="schedule")
        )
        r = client.delete("/settings/temporary-override")
        assert r.status_code == 200
        assert r.json()["status"] == "cleared"
        assert settings_service.get_temporary_override() is None

    def test_clear_when_no_override_is_safe(self, client):
        r = client.delete("/settings/temporary-override")
        assert r.status_code == 200
        assert r.json()["status"] == "cleared"

    def test_clear_sets_active_page_for_revert_page_mode(self, client, settings_service):
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        settings_service.set_temporary_override(
            TemporaryOverride(
                page_id="p1", expires_at=expires, revert_mode="page", revert_page_id="p2"
            )
        )
        client.delete("/settings/temporary-override")
        assert settings_service.get_active_page_id() == "p2"


# ---------------------------------------------------------------------------
# GET /schedules/active/page includes temporary_override field
# ---------------------------------------------------------------------------

class TestActiveScheduleIncludesOverride:
    def test_override_field_present_when_no_override(self, client, settings_service):
        r = client.get("/schedules/active/page")
        assert r.status_code == 200
        data = r.json()
        assert "temporary_override" in data
        assert data["temporary_override"]["active"] is False

    def test_override_field_active_when_override_set(self, client, settings_service):
        expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        settings_service.set_temporary_override(
            TemporaryOverride(page_id="p1", expires_at=expires, revert_mode="schedule")
        )
        r = client.get("/schedules/active/page")
        assert r.status_code == 200
        assert r.json()["temporary_override"]["active"] is True


# ---------------------------------------------------------------------------
# SettingsService unit tests
# ---------------------------------------------------------------------------

class TestSettingsServiceOverride:
    def test_set_and_get_override(self, tmp_settings_file):
        svc = SettingsService(settings_file=str(tmp_settings_file))
        expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        override = TemporaryOverride(page_id="p1", expires_at=expires, revert_mode="schedule")
        svc.set_temporary_override(override)
        result = svc.get_temporary_override()
        assert result is not None
        assert result.page_id == "p1"

    def test_get_override_returns_none_when_expired(self, tmp_settings_file):
        svc = SettingsService(settings_file=str(tmp_settings_file))
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        svc._temporary_override = TemporaryOverride(
            page_id="p1", expires_at=past, revert_mode="schedule"
        )
        result = svc.get_temporary_override()
        assert result is None
        # Also verifies auto-clear persisted
        assert svc._temporary_override is None

    def test_clear_override(self, tmp_settings_file):
        svc = SettingsService(settings_file=str(tmp_settings_file))
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        svc.set_temporary_override(
            TemporaryOverride(page_id="p1", expires_at=expires, revert_mode="blank")
        )
        svc.clear_temporary_override()
        assert svc.get_temporary_override() is None

    def test_override_survives_service_restart(self, tmp_settings_file):
        # Write override with first instance
        svc1 = SettingsService(settings_file=str(tmp_settings_file))
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        svc1.set_temporary_override(
            TemporaryOverride(page_id="p1", expires_at=expires, revert_mode="schedule")
        )
        # Reload with second instance
        svc2 = SettingsService(settings_file=str(tmp_settings_file))
        result = svc2.get_temporary_override()
        assert result is not None
        assert result.page_id == "p1"

    def test_expired_override_not_loaded_on_restart(self, tmp_settings_file):
        svc1 = SettingsService(settings_file=str(tmp_settings_file))
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        # Write expired override directly to the file
        svc1._temporary_override = TemporaryOverride(
            page_id="p1", expires_at=past, revert_mode="schedule"
        )
        svc1._save_to_file()
        # Reload — expired override should be discarded
        svc2 = SettingsService(settings_file=str(tmp_settings_file))
        assert svc2.get_temporary_override() is None
