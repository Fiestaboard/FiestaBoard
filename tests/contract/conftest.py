"""Shared fixtures for API contract tests.

These tests validate that the FastAPI backend returns responses that match
the schemas the Next.js frontend expects to consume. Using Pydantic models
as the source of truth for schema validation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from src.api_server import app


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_page_service():
    """Mock the page service for isolated contract testing."""
    with patch("src.api_server.get_page_service") as mock_get:
        svc = Mock()

        # Default list_pages returns an empty list
        svc.list_pages.return_value = []

        # create_page returns a minimal valid Page object
        from src.pages.models import Page
        sample_page = Page(
            id="contract-page-1",
            name="Contract Test Page",
            type="template",
            template=["HELLO WORLD", "", "", "", "", ""],
        )
        svc.create_page.return_value = sample_page
        svc.get_page.return_value = sample_page

        mock_get.return_value = svc
        yield svc


@pytest.fixture
def mock_schedule_service():
    """Mock the schedule service for isolated contract testing."""
    with patch("src.api_server.get_schedule_service") as mock_get:
        svc = Mock()

        from src.schedules.models import ScheduleEntry as Schedule
        sample_schedule = Schedule(
            id="contract-schedule-1",
            page_id="contract-page-1",
            start_time="08:00",
            end_time="17:00",
            day_pattern="weekdays",
        )
        svc.list_schedules.return_value = []
        svc.create_schedule.return_value = sample_schedule
        svc.get_schedule.return_value = sample_schedule

        svc.get_schedules_enabled.return_value = True
        svc.get_active_page_id.return_value = None
        svc.get_default_page_id.return_value = None
        svc.validate_schedule_data.return_value = {"valid": True, "errors": []}

        mock_get.return_value = svc
        yield svc


@pytest.fixture
def mock_settings_service():
    """Mock the settings service for isolated contract testing."""
    with patch("src.api_server.get_settings_service") as mock_get:
        svc = Mock()

        transition = Mock()
        transition.strategy = "column"
        transition.step_interval_ms = 100
        transition.step_size = 1
        transition.to_dict.return_value = {
            "strategy": "column",
            "step_interval_ms": 100,
            "step_size": 1,
        }
        svc.get_transition_settings.return_value = transition

        output = Mock()
        output.target = "ui"
        output.to_dict.return_value = {"target": "ui"}
        svc.get_output_settings.return_value = output

        svc.get_active_page_id.return_value = None
        svc.get_polling_settings.return_value = Mock(to_dict=lambda: {"enabled": True})

        mock_get.return_value = svc
        yield svc


@pytest.fixture
def mock_config_manager():
    """Mock config manager for settings endpoints."""
    with patch("src.api_server.get_config_manager") as mock_get:
        cm = Mock()
        cm.get_all_masked.return_value = {}
        cm.get_board.return_value = {
            "api_mode": "local",
            "local_api_key": "test",
            "host": "192.168.1.100",
        }
        cm._mask_sensitive.side_effect = lambda d: d
        cm.validate.return_value = (True, [])
        cm.get_general.return_value = {"timezone": "UTC", "refresh_interval_seconds": 60}
        cm.get_feature.return_value = {
            "enabled": False,
            "start_time": "20:00+00:00",
            "end_time": "07:00+00:00",
        }
        cm.get_plugin_config.return_value = {"enabled": False}
        mock_get.return_value = cm
        yield cm
