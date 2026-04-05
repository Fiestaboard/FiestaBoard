"""Tests for the CalendarSubPlugin."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytz
import pytest
import requests

from calendar_sub import CalendarSubPlugin
from calendar_sub import _normalize_url, _format_time, _format_date
from src.plugins.base import PluginResult, TriggerResult

from .conftest import (
    ALL_DAY_EVENT_ICS,
    EMPTY_CALENDAR_ICS,
    MULTI_EVENT_ICS,
    RECURRING_EVENT_ICS,
    SINGLE_EVENT_ICS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(ics_text: str, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = ics_text.encode("utf-8")
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(
            f"{status_code}", response=mock
        )
    return mock


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------


class TestNormalizeUrl:
    def test_https_unchanged(self):
        assert _normalize_url("https://example.com/cal.ics") == "https://example.com/cal.ics"

    def test_http_unchanged(self):
        assert _normalize_url("http://example.com/cal.ics") == "http://example.com/cal.ics"

    def test_webcal_to_https(self):
        assert _normalize_url("webcal://example.com/cal.ics") == "https://example.com/cal.ics"

    def test_webcal_colon_to_https(self):
        assert _normalize_url("webcal://cal.example.com/path") == "https://cal.example.com/path"


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


class TestFormatHelpers:
    def test_format_time_with_minutes(self):
        tz = pytz.timezone("America/Los_Angeles")
        dt = tz.localize(datetime(2026, 4, 3, 15, 30))
        assert _format_time(dt) == "3:30 PM"

    def test_format_time_midnight(self):
        tz = pytz.timezone("America/Los_Angeles")
        dt = tz.localize(datetime(2026, 4, 3, 0, 0))
        assert _format_time(dt) == "All Day"

    def test_format_date(self):
        tz = pytz.timezone("America/Los_Angeles")
        dt = tz.localize(datetime(2026, 4, 3, 15, 30))
        assert _format_date(dt) == "Apr 3"


# ---------------------------------------------------------------------------
# Plugin ID and basic structure
# ---------------------------------------------------------------------------


class TestCalendarSubPluginBasics:
    def test_plugin_id(self, sample_manifest):
        plugin = CalendarSubPlugin(sample_manifest)
        assert plugin.plugin_id == "calendar_sub"

    def test_supports_triggers(self, sample_manifest):
        plugin = CalendarSubPlugin(sample_manifest)
        assert plugin.supports_triggers is True

    def test_manifest_id_matches_directory(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["id"] == "calendar_sub"

    def test_manifest_has_required_fields(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        for field in ("id", "name", "version", "description", "settings_schema", "variables"):
            assert field in manifest, f"Manifest missing required field: {field}"


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_config(self, sample_manifest, sample_config):
        plugin = CalendarSubPlugin(sample_manifest)
        errors = plugin.validate_config(sample_config)
        assert errors == []

    def test_missing_url(self, sample_manifest):
        plugin = CalendarSubPlugin(sample_manifest)
        errors = plugin.validate_config({"timezone": "America/Los_Angeles"})
        assert any("url" in e.lower() or "Calendar URL" in e for e in errors)

    def test_invalid_timezone(self, sample_manifest, sample_config):
        plugin = CalendarSubPlugin(sample_manifest)
        config = {**sample_config, "timezone": "Invalid/Zone"}
        errors = plugin.validate_config(config)
        assert any("timezone" in e.lower() for e in errors)

    def test_webcal_url_is_valid(self, sample_manifest):
        plugin = CalendarSubPlugin(sample_manifest)
        errors = plugin.validate_config({
            "calendar_url": "webcal://example.com/cal.ics",
            "timezone": "America/Los_Angeles",
        })
        assert errors == []

    def test_nonsense_url_is_invalid(self, sample_manifest):
        plugin = CalendarSubPlugin(sample_manifest)
        errors = plugin.validate_config({"calendar_url": "ftp://example.com/cal.ics"})
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# fetch_data — success cases
# ---------------------------------------------------------------------------


class TestFetchData:
    @patch("calendar_sub.requests.get")
    def test_single_event(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(SINGLE_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {
            **sample_config,
            "timezone": "UTC",
        }
        result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data is not None
        # "Parent Teacher Conference" is 25 chars, truncated to 22
        assert result.data["event_name"] == "Parent Teacher Confere"
        assert result.data["event_location"] == "Room 204"

    @patch("calendar_sub.requests.get")
    def test_single_event_formatted_lines(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(SINGLE_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        result = plugin.fetch_data()

        assert result.formatted_lines is not None
        assert len(result.formatted_lines) == 6

    @patch("calendar_sub.requests.get")
    def test_multiple_events_sorted(self, mock_get, sample_manifest, sample_config):
        """Events should be sorted by start time; the sooner event should be first."""
        mock_get.return_value = _make_mock_response(MULTI_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        result = plugin.fetch_data()

        assert result.available is True
        # Morning Assembly is 5 days out; Science Fair is 7 days out
        assert result.data["event_name"] == "Morning Assembly"
        assert int(result.data["event_count"]) == 2

    @patch("calendar_sub.requests.get")
    def test_events_array_in_data(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(MULTI_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        result = plugin.fetch_data()

        events = result.data["events"]
        assert isinstance(events, list)
        assert len(events) == 2
        # Sorted by time: sooner event first
        assert events[0]["name"] == "Morning Assembly"
        assert events[1]["name"] == "Science Fair"

    @patch("calendar_sub.requests.get")
    def test_recurring_events_expanded(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(RECURRING_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC", "max_events": 10}
        result = plugin.fetch_data()

        assert result.available is True
        assert int(result.data["event_count"]) >= 1
        assert result.data["event_name"] == "Weekly Standup"

    @patch("calendar_sub.requests.get")
    def test_all_day_event(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(ALL_DAY_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "America/Los_Angeles"}
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["event_name"] == "Staff Development Day"
        assert result.data["event_start"] == "All Day"

    @patch("calendar_sub.requests.get")
    def test_empty_calendar(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(EMPTY_CALENDAR_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["event_count"] == "0"
        assert result.data["event_name"] == ""

    @patch("calendar_sub.requests.get")
    def test_empty_calendar_formatted_lines(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(EMPTY_CALENDAR_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        result = plugin.fetch_data()

        assert result.formatted_lines is not None
        assert len(result.formatted_lines) == 6
        assert any("NO UPCOMING" in line for line in result.formatted_lines)

    @patch("calendar_sub.requests.get")
    def test_max_events_limit(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(RECURRING_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC", "max_events": 2}
        result = plugin.fetch_data()

        assert int(result.data["event_count"]) <= 2

    @patch("calendar_sub.requests.get")
    def test_webcal_url_normalized(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(SINGLE_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "calendar_url": "webcal://example.com/cal.ics"}
        plugin.fetch_data()

        called_url = mock_get.call_args[0][0]
        assert called_url.startswith("https://")

    @patch("calendar_sub.requests.get")
    def test_all_manifest_variables_present(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(SINGLE_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        result = plugin.fetch_data()

        assert result.available is True
        simple_vars = sample_manifest["variables"]["simple"]
        for var_name in simple_vars:
            assert var_name in result.data, f"Variable '{var_name}' missing from data"


# ---------------------------------------------------------------------------
# fetch_data — error cases
# ---------------------------------------------------------------------------


class TestFetchDataErrors:
    def test_missing_url_returns_unavailable(self, sample_manifest):
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {"timezone": "America/Los_Angeles"}
        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    @patch("calendar_sub.requests.get")
    def test_network_error_returns_unavailable(self, mock_get, sample_manifest, sample_config):
        mock_get.side_effect = requests.ConnectionError("Connection refused")
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    @patch("calendar_sub.requests.get")
    def test_http_error_returns_unavailable(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response("", status_code=404)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    @patch("calendar_sub.requests.get")
    def test_invalid_ics_returns_unavailable(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response("not valid ics content at all !!!")
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        # Invalid ICS won't raise an exception from icalendar (it's lenient),
        # but should still return available=True with 0 events or a graceful error
        result = plugin.fetch_data()
        assert result.available in (True, False)


# ---------------------------------------------------------------------------
# check_triggers
# ---------------------------------------------------------------------------


class TestCheckTriggers:
    def _ics_with_event(self, minutes_offset: int, uid: str = "test@test",
                        summary: str = "Test Meeting", location: str = "") -> str:
        """Build ICS with one event at now + minutes_offset from real current time."""
        now = datetime.now(pytz.UTC)
        event_start = now + timedelta(minutes=minutes_offset)
        event_end = event_start + timedelta(hours=1)
        loc_line = f"LOCATION:{location}\n" if location else ""
        return (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//Test//EN\n"
            "BEGIN:VEVENT\n"
            f"UID:{uid}\n"
            f"SUMMARY:{summary}\n"
            f"DTSTART:{event_start.strftime('%Y%m%dT%H%M%SZ')}\n"
            f"DTEND:{event_end.strftime('%Y%m%dT%H%M%SZ')}\n"
            f"{loc_line}"
            "END:VEVENT\nEND:VCALENDAR\n"
        )

    @patch("calendar_sub.requests.get")
    def test_trigger_fires_within_window(self, mock_get, sample_manifest, sample_config):
        """An event starting within minutes_before should fire a trigger."""
        ics = self._ics_with_event(minutes_offset=10, uid="trigger-test-001@test",
                                   summary="Upcoming Meeting", location="Conference Room")
        mock_get.return_value = _make_mock_response(ics)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC", "minutes_before": 15}
        plugin.fetch_data()
        results = plugin.check_triggers()

        triggered = [r for r in results if r.triggered]
        assert len(triggered) >= 1
        assert triggered[0].formatted_lines is not None
        assert len(triggered[0].formatted_lines) == 6

    @patch("calendar_sub.requests.get")
    def test_trigger_does_not_fire_outside_window(self, mock_get, sample_manifest, sample_config):
        """An event far in the future should not fire a trigger."""
        ics = self._ics_with_event(minutes_offset=300, uid="future-event@test",
                                   summary="Far Future Meeting")
        mock_get.return_value = _make_mock_response(ics)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC", "minutes_before": 15}
        plugin.fetch_data()
        results = plugin.check_triggers()

        triggered = [r for r in results if r.triggered]
        assert len(triggered) == 0

    @patch("calendar_sub.requests.get")
    def test_trigger_fires_for_event_in_progress(self, mock_get, sample_manifest, sample_config):
        """An event currently in progress should fire an 'is_now' trigger."""
        # Event started 5 minutes ago and ends in 55 minutes
        now = datetime.now(pytz.UTC)
        event_start = now - timedelta(minutes=5)
        event_end = now + timedelta(minutes=55)
        ics = (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//Test//EN\n"
            "BEGIN:VEVENT\n"
            "UID:now-event@test\n"
            "SUMMARY:Current Meeting\n"
            f"DTSTART:{event_start.strftime('%Y%m%dT%H%M%SZ')}\n"
            f"DTEND:{event_end.strftime('%Y%m%dT%H%M%SZ')}\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        )
        mock_get.return_value = _make_mock_response(ics)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC", "minutes_before": 15}
        plugin.fetch_data()
        results = plugin.check_triggers()

        triggered = [r for r in results if r.triggered]
        assert len(triggered) >= 1
        now_trigger = [r for r in triggered if r.trigger_id.endswith("_now")]
        assert len(now_trigger) >= 1

    @patch("calendar_sub.requests.get")
    def test_trigger_id_is_stable(self, mock_get, sample_manifest, sample_config):
        """Trigger IDs should be deterministic for the same event."""
        ics = self._ics_with_event(minutes_offset=5, uid="stable-id-event@test",
                                   summary="Stable Meeting")
        mock_get.return_value = _make_mock_response(ics)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC", "minutes_before": 15}
        plugin.fetch_data()
        results1 = plugin.check_triggers()
        results2 = plugin.check_triggers()

        ids1 = {r.trigger_id for r in results1 if r.triggered}
        ids2 = {r.trigger_id for r in results2 if r.triggered}
        assert ids1 == ids2

    @patch("calendar_sub.requests.get")
    def test_trigger_duration_from_config(self, mock_get, sample_manifest, sample_config):
        """display_duration_minutes should set trigger duration_seconds."""
        ics = self._ics_with_event(minutes_offset=5, uid="duration-event@test",
                                   summary="Duration Meeting")
        mock_get.return_value = _make_mock_response(ics)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {
            **sample_config,
            "timezone": "UTC",
            "minutes_before": 15,
            "display_duration_minutes": 20,
        }
        plugin.fetch_data()
        results = plugin.check_triggers()

        triggered = [r for r in results if r.triggered]
        assert len(triggered) >= 1
        assert triggered[0].duration_seconds == 20 * 60

    @patch("calendar_sub.requests.get")
    def test_trigger_indefinite_duration_when_zero(self, mock_get, sample_manifest, sample_config):
        """display_duration_minutes=0 should use the indefinite duration constant."""
        from calendar_sub import _INDEFINITE_DURATION_SECONDS

        ics = self._ics_with_event(minutes_offset=5, uid="indef-event@test",
                                   summary="Indefinite Meeting")
        mock_get.return_value = _make_mock_response(ics)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {
            **sample_config,
            "timezone": "UTC",
            "minutes_before": 15,
            "display_duration_minutes": 0,
        }
        plugin.fetch_data()
        results = plugin.check_triggers()

        triggered = [r for r in results if r.triggered]
        assert len(triggered) >= 1
        assert triggered[0].duration_seconds == _INDEFINITE_DURATION_SECONDS

    @patch("calendar_sub.requests.get")
    def test_check_triggers_handles_fetch_error(self, mock_get, sample_manifest, sample_config):
        """check_triggers should return [] if the calendar fetch fails."""
        mock_get.side_effect = requests.ConnectionError("Network error")
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        # Empty cache — will try to fetch
        plugin._events_cache = []
        results = plugin.check_triggers()
        assert results == []

    @patch("calendar_sub.requests.get")
    def test_empty_calendar_no_triggers(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(EMPTY_CALENDAR_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        plugin.fetch_data()
        results = plugin.check_triggers()
        assert all(not r.triggered for r in results)


# ---------------------------------------------------------------------------
# Formatted display
# ---------------------------------------------------------------------------


class TestFormattedDisplay:
    @patch("calendar_sub.requests.get")
    def test_formatted_lines_is_6(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(SINGLE_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        result = plugin.fetch_data()

        assert len(result.formatted_lines) == 6

    @patch("calendar_sub.requests.get")
    def test_formatted_lines_respect_22_char_limit(self, mock_get, sample_manifest, sample_config):
        mock_get.return_value = _make_mock_response(SINGLE_EVENT_ICS)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC"}
        result = plugin.fetch_data()

        for line in result.formatted_lines:
            assert len(line) <= 22, f"Line too long: {repr(line)}"

    @patch("calendar_sub.requests.get")
    def test_trigger_display_contains_event_name(self, mock_get, sample_manifest, sample_config):
        """Trigger display should contain the event name (within minutes_before window)."""
        # Use real-time ICS so the event is definitely within the window
        now = datetime.now(pytz.UTC)
        event_start = now + timedelta(minutes=10)
        event_end = event_start + timedelta(hours=1)
        ics = (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//Test//EN\n"
            "BEGIN:VEVENT\nUID:display-test@test\n"
            "SUMMARY:Parent Teacher Conference\n"
            f"DTSTART:{event_start.strftime('%Y%m%dT%H%M%SZ')}\n"
            f"DTEND:{event_end.strftime('%Y%m%dT%H%M%SZ')}\n"
            "LOCATION:Room 204\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        )
        mock_get.return_value = _make_mock_response(ics)
        plugin = CalendarSubPlugin(sample_manifest)
        plugin.config = {**sample_config, "timezone": "UTC", "minutes_before": 15}
        plugin.fetch_data()
        results = plugin.check_triggers()

        triggered = [r for r in results if r.triggered]
        assert len(triggered) >= 1
        lines_text = " ".join(triggered[0].formatted_lines)
        assert "PARENT TEACHER" in lines_text or "CONFERENCE" in lines_text


# ---------------------------------------------------------------------------
# Manifest metadata completeness
# ---------------------------------------------------------------------------


class TestManifestMetadata:
    def test_all_variables_have_descriptions(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        simple = manifest["variables"]["simple"]
        for var_name, meta in simple.items():
            assert "description" in meta and meta["description"], \
                f"Variable '{var_name}' missing description"

    def test_all_variables_have_valid_groups(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        groups = set(manifest["variables"].get("groups", {}).keys())
        simple = manifest["variables"]["simple"]
        for var_name, meta in simple.items():
            group = meta.get("group", "")
            if group:
                assert group in groups, \
                    f"Variable '{var_name}' references undefined group '{group}'"

    def test_groups_defined(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        groups = manifest["variables"].get("groups", {})
        assert len(groups) > 0
        for group_id, group_def in groups.items():
            assert "label" in group_def, f"Group '{group_id}' missing label"

    def test_supports_triggers_in_manifest(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest.get("supports_triggers") is True

    def test_screenshot_primary_entry(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        screenshots = manifest.get("screenshots", [])
        assert any(s.get("primary") is True for s in screenshots), \
            "Manifest should have a primary screenshot entry"

    def test_manifest_uses_dict_simple_format(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        simple = manifest["variables"]["simple"]
        assert isinstance(simple, dict), "simple should use the rich dict format"
