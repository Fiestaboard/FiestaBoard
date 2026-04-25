"""Contract tests for the /schedules API endpoints.

Validates that the Python backend returns responses that conform to the
schema the Next.js frontend expects.

Issue: #502
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from src.api_server import app
from tests.contract.schemas import (
    SchedulesEnabledResponse,
    DefaultPageResponse,
)
from src.schedules.models import ScheduleEntry as Schedule


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_schedule():
    return Schedule(
        id="contract-sched-1",
        page_id="contract-page-1",
        start_time="08:00",
        end_time="17:00",
        day_pattern="weekdays",
    )


# ---------------------------------------------------------------------------
# GET /schedules
# ---------------------------------------------------------------------------


class TestListSchedulesContract:
    def test_returns_200(self, client):
        with patch("src.api_server.get_schedule_service") as mock_svc, \
             patch("src.api_server.get_settings_service") as mock_settings:
            svc = Mock()
            svc.list_schedules.return_value = []
            svc.get_default_page.return_value = None
            mock_svc.return_value = svc

            ss = Mock()
            ss.is_schedule_enabled.return_value = False
            mock_settings.return_value = ss

            resp = client.get("/schedules")

        assert resp.status_code == 200

    def test_response_has_required_keys(self, client):
        with patch("src.api_server.get_schedule_service") as mock_svc, \
             patch("src.api_server.get_settings_service") as mock_settings:
            svc = Mock()
            svc.list_schedules.return_value = []
            svc.get_default_page.return_value = None
            mock_svc.return_value = svc

            ss = Mock()
            ss.is_schedule_enabled.return_value = False
            mock_settings.return_value = ss

            resp = client.get("/schedules")

        data = resp.json()
        assert "schedules" in data
        assert "total" in data

    def test_schedules_is_list(self, client):
        with patch("src.api_server.get_schedule_service") as mock_svc, \
             patch("src.api_server.get_settings_service") as mock_settings:
            svc = Mock()
            svc.list_schedules.return_value = []
            svc.get_default_page.return_value = None
            mock_svc.return_value = svc

            ss = Mock()
            ss.is_schedule_enabled.return_value = False
            mock_settings.return_value = ss

            resp = client.get("/schedules")

        assert isinstance(resp.json()["schedules"], list)

    def test_total_matches_schedules_length(self, client, sample_schedule):
        with patch("src.api_server.get_schedule_service") as mock_svc, \
             patch("src.api_server.get_settings_service") as mock_settings:
            svc = Mock()
            svc.list_schedules.return_value = [sample_schedule]
            svc.get_default_page.return_value = None
            mock_svc.return_value = svc

            ss = Mock()
            ss.is_schedule_enabled.return_value = True
            mock_settings.return_value = ss

            resp = client.get("/schedules")

        data = resp.json()
        assert data["total"] == len(data["schedules"])

    def test_schedule_item_has_required_fields(self, client, sample_schedule):
        with patch("src.api_server.get_schedule_service") as mock_svc, \
             patch("src.api_server.get_settings_service") as mock_settings:
            svc = Mock()
            svc.list_schedules.return_value = [sample_schedule]
            svc.get_default_page.return_value = None
            mock_svc.return_value = svc

            ss = Mock()
            ss.is_schedule_enabled.return_value = True
            mock_settings.return_value = ss

            resp = client.get("/schedules")

        sched = resp.json()["schedules"][0]
        assert "id" in sched
        assert "page_id" in sched
        assert "start_time" in sched
        assert "end_time" in sched
        assert "day_pattern" in sched

    def test_schedule_time_format_is_hhmm(self, client, sample_schedule):
        with patch("src.api_server.get_schedule_service") as mock_svc, \
             patch("src.api_server.get_settings_service") as mock_settings:
            svc = Mock()
            svc.list_schedules.return_value = [sample_schedule]
            svc.get_default_page.return_value = None
            mock_svc.return_value = svc

            ss = Mock()
            ss.is_schedule_enabled.return_value = True
            mock_settings.return_value = ss

            resp = client.get("/schedules")

        sched = resp.json()["schedules"][0]
        import re
        assert re.match(r"^\d{2}:\d{2}$", sched["start_time"]), \
            f"start_time format unexpected: {sched['start_time']}"
        assert re.match(r"^\d{2}:\d{2}$", sched["end_time"]), \
            f"end_time format unexpected: {sched['end_time']}"

    def test_wildcard_board_id_returns_no_default_or_enabled(self, client, sample_schedule):
        """board_id=* returns schedules without enabled/default_page_id semantics."""
        with patch("src.api_server.get_schedule_service") as mock_svc, \
             patch("src.api_server.get_settings_service") as mock_settings:
            svc = Mock()
            svc.list_schedules.return_value = [sample_schedule]
            mock_svc.return_value = svc

            ss = Mock()
            mock_settings.return_value = ss

            resp = client.get("/schedules?board_id=*")

        data = resp.json()
        assert "schedules" in data
        assert "total" in data
        assert data["enabled"] is False  # wildcard sets enabled=False
        assert data["default_page_id"] is None


# ---------------------------------------------------------------------------
# POST /schedules
# ---------------------------------------------------------------------------


class TestCreateScheduleContract:
    def test_returns_200_on_valid_input(self, client, sample_schedule):
        with patch("src.api_server.get_schedule_service") as mock_svc:
            svc = Mock()
            svc.create_schedule.return_value = sample_schedule
            mock_svc.return_value = svc

            resp = client.post(
                "/schedules",
                json={
                    "page_id": "contract-page-1",
                    "start_time": "08:00",
                    "end_time": "17:00",
                    "day_pattern": "weekdays",
                },
            )

        assert resp.status_code == 200

    def test_created_schedule_has_required_fields(self, client, sample_schedule):
        with patch("src.api_server.get_schedule_service") as mock_svc:
            svc = Mock()
            svc.create_schedule.return_value = sample_schedule
            mock_svc.return_value = svc

            resp = client.post(
                "/schedules",
                json={
                    "page_id": "contract-page-1",
                    "start_time": "08:00",
                    "end_time": "17:00",
                    "day_pattern": "weekdays",
                },
            )

        data = resp.json()
        assert "id" in data
        assert "page_id" in data
        assert "start_time" in data
        assert "end_time" in data
        assert "day_pattern" in data

    def test_returns_400_on_invalid_input(self, client):
        with patch("src.api_server.get_schedule_service") as mock_svc:
            svc = Mock()
            svc.create_schedule.side_effect = ValueError("Missing page_id")
            mock_svc.return_value = svc

            resp = client.post(
                "/schedules",
                json={"start_time": "08:00", "end_time": "17:00"},
            )

        assert resp.status_code in (400, 422)

    def test_midnight_spanning_schedule_accepted(self, client):
        """API must accept start_time > end_time for overnight schedules."""
        overnight = Schedule(
            id="overnight-1",
            page_id="p1",
            start_time="22:00",
            end_time="06:00",
            day_pattern="all",
        )
        with patch("src.api_server.get_schedule_service") as mock_svc:
            svc = Mock()
            svc.create_schedule.return_value = overnight
            mock_svc.return_value = svc

            resp = client.post(
                "/schedules",
                json={
                    "page_id": "p1",
                    "start_time": "22:00",
                    "end_time": "06:00",
                    "day_pattern": "all",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["start_time"] == "22:00"
        assert data["end_time"] == "06:00"


# ---------------------------------------------------------------------------
# GET /schedules/enabled
# ---------------------------------------------------------------------------


class TestSchedulesEnabledContract:
    def test_returns_200(self, client):
        with patch("src.api_server.get_settings_service") as mock_settings:
            ss = Mock()
            ss.is_schedule_enabled.return_value = False
            mock_settings.return_value = ss

            resp = client.get("/schedules/enabled")

        assert resp.status_code == 200

    def test_response_has_enabled_field(self, client):
        with patch("src.api_server.get_settings_service") as mock_settings:
            ss = Mock()
            ss.is_schedule_enabled.return_value = True
            mock_settings.return_value = ss

            resp = client.get("/schedules/enabled")

        data = resp.json()
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)

    def test_enabled_false_validates(self, client):
        with patch("src.api_server.get_settings_service") as mock_settings:
            ss = Mock()
            ss.is_schedule_enabled.return_value = False
            mock_settings.return_value = ss

            resp = client.get("/schedules/enabled")

        parsed = SchedulesEnabledResponse(**resp.json())
        assert parsed.enabled is False

    def test_enabled_true_validates(self, client):
        with patch("src.api_server.get_settings_service") as mock_settings:
            ss = Mock()
            ss.is_schedule_enabled.return_value = True
            mock_settings.return_value = ss

            resp = client.get("/schedules/enabled")

        parsed = SchedulesEnabledResponse(**resp.json())
        assert parsed.enabled is True


# ---------------------------------------------------------------------------
# GET /schedules/default-page
# ---------------------------------------------------------------------------


class TestDefaultPageContract:
    def test_returns_200(self, client):
        with patch("src.api_server.get_schedule_service") as mock_svc:
            svc = Mock()
            svc.get_default_page.return_value = None
            mock_svc.return_value = svc

            resp = client.get("/schedules/default-page")

        assert resp.status_code == 200

    def test_response_has_default_page_id(self, client):
        with patch("src.api_server.get_schedule_service") as mock_svc:
            svc = Mock()
            svc.get_default_page.return_value = None
            mock_svc.return_value = svc

            resp = client.get("/schedules/default-page")

        data = resp.json()
        assert "default_page_id" in data

    def test_null_default_page_is_valid(self, client):
        with patch("src.api_server.get_schedule_service") as mock_svc:
            svc = Mock()
            svc.get_default_page.return_value = None
            mock_svc.return_value = svc

            resp = client.get("/schedules/default-page")

        parsed = DefaultPageResponse(**resp.json())
        assert parsed.page_id is None

    def test_set_default_page_id_reflects_in_response(self, client):
        with patch("src.api_server.get_schedule_service") as mock_svc:
            svc = Mock()
            svc.get_default_page.return_value = "my-default-page"
            mock_svc.return_value = svc

            resp = client.get("/schedules/default-page")

        data = resp.json()
        assert data["default_page_id"] == "my-default-page"
