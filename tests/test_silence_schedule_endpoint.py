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

        cm.set_feature.assert_called_once_with(
            "silence_schedule",
            {
                "enabled": True,
                "start_time": "04:00+00:00",
                "end_time": "15:00+00:00",
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
