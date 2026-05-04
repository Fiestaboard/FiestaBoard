"""Tests for the dedicated silence schedule settings endpoint.

`silence_schedule` is a system feature (not a plugin), so it has its own
endpoint at `PUT /settings/silence-schedule` backed by
`config_manager.set_feature("silence_schedule", ...)`. These tests cover the
happy path, validation errors, round-trip via `get_feature`, and that
`/silence-status` reflects writes made through this endpoint.
"""
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_config_manager_for_silence():
    """Mock config manager with a working silence_schedule feature."""
    with patch("src.api_server.get_config_manager") as mock_get:
        cm = Mock()
        store = {"enabled": False, "start_time": "04:00+00:00", "end_time": "15:00+00:00"}

        def _get_feature(name):
            if name == "silence_schedule":
                return dict(store)
            return {}

        def _set_feature(name, value):
            if name == "silence_schedule":
                store.clear()
                store.update(value)
                return True
            return False

        cm.get_feature.side_effect = _get_feature
        cm.set_feature.side_effect = _set_feature
        cm.migrate_silence_schedule_to_utc.return_value = False
        mock_get.return_value = cm
        yield cm, store


class TestUpdateSilenceScheduleEndpoint:
    def test_update_success(self, client, mock_config_manager_for_silence):
        cm, store = mock_config_manager_for_silence
        response = client.put(
            "/settings/silence-schedule",
            json={
                "enabled": True,
                "start_time": "04:00+00:00",
                "end_time": "15:00+00:00",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["config"]["enabled"] is True
        assert data["config"]["start_time"] == "04:00+00:00"
        assert data["config"]["end_time"] == "15:00+00:00"
        # New optional fields default to indicator/None
        assert data["config"]["mode"] == "indicator"
        assert data["config"]["page_id"] is None

        cm.set_feature.assert_called_once_with(
            "silence_schedule",
            {
                "enabled": True,
                "start_time": "04:00+00:00",
                "end_time": "15:00+00:00",
                "mode": "indicator",
                "page_id": None,
            },
        )

    def test_update_roundtrip_via_get_feature(self, client, mock_config_manager_for_silence):
        cm, store = mock_config_manager_for_silence
        client.put(
            "/settings/silence-schedule",
            json={
                "enabled": True,
                "start_time": "05:30+00:00",
                "end_time": "13:15+00:00",
            },
        )

        # Feature dict should reflect the write
        assert store == {
            "enabled": True,
            "start_time": "05:30+00:00",
            "end_time": "13:15+00:00",
            "mode": "indicator",
            "page_id": None,
        }

    def test_update_missing_fields_returns_422(self, client, mock_config_manager_for_silence):
        response = client.put(
            "/settings/silence-schedule",
            json={"enabled": True},
        )
        assert response.status_code == 422

    def test_update_wrong_types_returns_422(self, client, mock_config_manager_for_silence):
        response = client.put(
            "/settings/silence-schedule",
            json={
                "enabled": "yes",
                "start_time": 0,
                "end_time": None,
            },
        )
        assert response.status_code == 422

    def test_update_persist_failure_returns_500(self, client):
        with patch("src.api_server.get_config_manager") as mock_get:
            cm = Mock()
            cm.set_feature.return_value = False
            cm.get_feature.return_value = {}
            mock_get.return_value = cm

            response = client.put(
                "/settings/silence-schedule",
                json={
                    "enabled": True,
                    "start_time": "04:00+00:00",
                    "end_time": "15:00+00:00",
                },
            )
            assert response.status_code == 500

    def test_silence_status_reflects_write(self, client, mock_config_manager_for_silence):
        """After writing via the endpoint, /silence-status should see the new values."""
        client.put(
            "/settings/silence-schedule",
            json={
                "enabled": True,
                "start_time": "04:00+00:00",
                "end_time": "15:00+00:00",
            },
        )

        response = client.get("/silence-status")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["start_time_utc"] == "04:00+00:00"
        assert data["end_time_utc"] == "15:00+00:00"
        # New silence-mode fields are surfaced
        assert data["mode"] == "indicator"
        assert data["page_id"] is None


class TestSilenceScheduleModes:
    """Tests for the silence-mode options (indicator/freeze/page)."""

    def test_freeze_mode_persists(self, client, mock_config_manager_for_silence):
        _, store = mock_config_manager_for_silence
        response = client.put(
            "/settings/silence-schedule",
            json={
                "enabled": True,
                "start_time": "04:00+00:00",
                "end_time": "15:00+00:00",
                "mode": "freeze",
            },
        )
        assert response.status_code == 200
        assert response.json()["config"]["mode"] == "freeze"
        assert store["mode"] == "freeze"

    def test_page_mode_requires_page_id(self, client, mock_config_manager_for_silence):
        response = client.put(
            "/settings/silence-schedule",
            json={
                "enabled": True,
                "start_time": "04:00+00:00",
                "end_time": "15:00+00:00",
                "mode": "page",
            },
        )
        assert response.status_code == 400

    def test_page_mode_with_page_id(self, client, mock_config_manager_for_silence):
        _, store = mock_config_manager_for_silence
        response = client.put(
            "/settings/silence-schedule",
            json={
                "enabled": True,
                "start_time": "04:00+00:00",
                "end_time": "15:00+00:00",
                "mode": "page",
                "page_id": "page-abc",
            },
        )
        assert response.status_code == 200
        config = response.json()["config"]
        assert config["mode"] == "page"
        assert config["page_id"] == "page-abc"
        assert store["page_id"] == "page-abc"

    def test_invalid_mode_falls_back_to_indicator(self, client, mock_config_manager_for_silence):
        response = client.put(
            "/settings/silence-schedule",
            json={
                "enabled": True,
                "start_time": "04:00+00:00",
                "end_time": "15:00+00:00",
                "mode": "garbage",
            },
        )
        assert response.status_code == 200
        assert response.json()["config"]["mode"] == "indicator"

    def test_silence_status_exposes_mode_and_page_id(self, client, mock_config_manager_for_silence):
        client.put(
            "/settings/silence-schedule",
            json={
                "enabled": True,
                "start_time": "04:00+00:00",
                "end_time": "15:00+00:00",
                "mode": "page",
                "page_id": "page-xyz",
            },
        )
        response = client.get("/silence-status")
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "page"
        assert data["page_id"] == "page-xyz"
