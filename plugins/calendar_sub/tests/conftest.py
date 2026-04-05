"""Plugin test fixtures for calendar_sub."""

import json
from pathlib import Path

import pytest

from src.plugins.testing import create_mock_response


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


@pytest.fixture
def mock_api_response():
    """Fixture to create mock API responses."""
    return create_mock_response


@pytest.fixture
def sample_manifest():
    """Load the plugin manifest for testing."""
    manifest_path = Path(__file__).parent.parent / "manifest.json"
    with open(manifest_path) as f:
        return json.load(f)


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "enabled": True,
        "calendar_url": "https://example.com/calendar.ics",
        "minutes_before": 15,
        "display_duration_minutes": 10,
        "timezone": "America/Los_Angeles",
        "max_events": 5,
        "refresh_seconds": 300,
    }


# ---------------------------------------------------------------------------
# Reusable ICS content builders (use future dates to remain valid over time)
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta
import pytz as _pytz

def _future_utc(days: int = 7, hour: int = 15, minute: int = 30) -> datetime:
    """Return a UTC-aware datetime in the future."""
    base = datetime.now(_pytz.UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base + timedelta(days=days)


def _ics_dt(dt: datetime) -> str:
    """Format a UTC datetime as an ICS DTSTART/DTEND string."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _build_single_event_ics() -> str:
    start = _future_utc(days=7)
    end = start + timedelta(hours=1)
    return f"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:event-001@test
SUMMARY:Parent Teacher Conference
DTSTART:{_ics_dt(start)}
DTEND:{_ics_dt(end)}
LOCATION:Room 204
DESCRIPTION:Bring report card
END:VEVENT
END:VCALENDAR
"""


def _build_recurring_event_ics() -> str:
    start = _future_utc(days=7)
    end = start + timedelta(minutes=30)
    return f"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:weekly-standup@test
SUMMARY:Weekly Standup
DTSTART:{_ics_dt(start)}
DTEND:{_ics_dt(end)}
RRULE:FREQ=WEEKLY;COUNT=4
END:VEVENT
END:VCALENDAR
"""


def _build_multi_event_ics() -> str:
    start_a = _future_utc(days=5, hour=14, minute=0)
    end_a = start_a + timedelta(minutes=30)
    start_b = _future_utc(days=7, hour=18, minute=0)
    end_b = start_b + timedelta(hours=2)
    return f"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:event-a@test
SUMMARY:Morning Assembly
DTSTART:{_ics_dt(start_a)}
DTEND:{_ics_dt(end_a)}
LOCATION:Gymnasium
END:VEVENT
BEGIN:VEVENT
UID:event-b@test
SUMMARY:Science Fair
DTSTART:{_ics_dt(start_b)}
DTEND:{_ics_dt(end_b)}
LOCATION:Main Hall
END:VEVENT
END:VCALENDAR
"""


def _build_all_day_event_ics() -> str:
    future_date = (datetime.now(_pytz.UTC) + timedelta(days=7)).date()
    next_date = future_date + timedelta(days=1)
    return f"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:allday-001@test
SUMMARY:Staff Development Day
DTSTART;VALUE=DATE:{future_date.strftime('%Y%m%d')}
DTEND;VALUE=DATE:{next_date.strftime('%Y%m%d')}
END:VEVENT
END:VCALENDAR
"""


# Eagerly-built strings (stable within a test run)
SINGLE_EVENT_ICS = _build_single_event_ics()
RECURRING_EVENT_ICS = _build_recurring_event_ics()
MULTI_EVENT_ICS = _build_multi_event_ics()
ALL_DAY_EVENT_ICS = _build_all_day_event_ics()

EMPTY_CALENDAR_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
END:VCALENDAR
"""
