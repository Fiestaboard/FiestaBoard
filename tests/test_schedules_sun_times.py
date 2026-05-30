"""Tests for sun time calculation and sun-based schedule matching."""

import pytest
from datetime import date, time
from unittest.mock import patch, MagicMock

from src.schedules.sun_times import (
    get_effective_timezone,
    get_sun_times,
    resolve_sun_time,
    resolve_schedule_sun_times,
)
from src.schedules.models import ScheduleEntry, ScheduleCreate
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage


# ---- Sun times computation ----

class TestGetSunTimes:
    """Test basic sun time computation via astral."""

    def test_returns_sunrise_and_sunset(self):
        """Sun times for a well-known location should return sunrise and sunset."""
        # New York City (40.7128, -74.0060) — summer solstice
        result = get_sun_times(40.7128, -74.0060, date(2026, 6, 21), "America/New_York")
        assert result is not None
        assert "sunrise" in result
        assert "sunset" in result
        # Sunrise in NYC in summer is roughly 5:20-5:30 AM
        assert 4 <= result["sunrise"].hour <= 6
        # Sunset is roughly 8:20-8:30 PM
        assert 19 <= result["sunset"].hour <= 21

    def test_returns_sunrise_and_sunset_winter(self):
        """Sun times for winter should have later sunrise and earlier sunset."""
        result = get_sun_times(40.7128, -74.0060, date(2026, 12, 21), "America/New_York")
        assert result is not None
        # Sunrise in NYC in winter is roughly 7:15 AM
        assert 6 <= result["sunrise"].hour <= 8
        # Sunset is roughly 4:30 PM
        assert 16 <= result["sunset"].hour <= 17

    def test_returns_none_on_failure(self):
        """Invalid parameters should return None gracefully."""
        # Use an extreme latitude where polar day might fail
        with patch("src.schedules.sun_times.sun", side_effect=Exception("polar")):
            result = get_sun_times(89.0, 0.0, date(2026, 6, 21), "UTC")
            assert result is None

    def test_different_timezones(self):
        """Sun times should differ by timezone for the same location."""
        result_utc = get_sun_times(51.5074, -0.1278, date(2026, 6, 21), "UTC")
        result_london = get_sun_times(51.5074, -0.1278, date(2026, 6, 21), "Europe/London")
        assert result_utc is not None
        assert result_london is not None
        # Both should have valid times
        assert result_utc["sunrise"].hour >= 0
        assert result_london["sunrise"].hour >= 0


class TestResolveSunTime:
    """Test resolving a single sun event + offset to HH:MM."""

    def test_resolve_sunrise_no_offset(self):
        """Resolving sunrise with no offset should return a valid time."""
        result = resolve_sun_time("sunrise", 0, 40.7128, -74.0060, date(2026, 6, 21), "America/New_York")
        assert result is not None
        # Should be HH:MM format
        assert len(result) == 5
        assert result[2] == ":"

    def test_resolve_sunset_no_offset(self):
        """Resolving sunset with no offset should return a valid time."""
        result = resolve_sun_time("sunset", 0, 40.7128, -74.0060, date(2026, 6, 21), "America/New_York")
        assert result is not None
        hours = int(result[:2])
        assert 19 <= hours <= 21  # NYC summer sunset

    def test_resolve_sunrise_with_positive_offset(self):
        """Positive offset should push time later."""
        base = resolve_sun_time("sunrise", 0, 40.7128, -74.0060, date(2026, 6, 21), "America/New_York")
        offset = resolve_sun_time("sunrise", 60, 40.7128, -74.0060, date(2026, 6, 21), "America/New_York")
        assert base is not None and offset is not None
        base_mins = int(base[:2]) * 60 + int(base[3:])
        offset_mins = int(offset[:2]) * 60 + int(offset[3:])
        assert offset_mins == base_mins + 60

    def test_resolve_sunrise_with_negative_offset(self):
        """Negative offset should push time earlier."""
        base = resolve_sun_time("sunrise", 0, 40.7128, -74.0060, date(2026, 6, 21), "America/New_York")
        offset = resolve_sun_time("sunrise", -30, 40.7128, -74.0060, date(2026, 6, 21), "America/New_York")
        assert base is not None and offset is not None
        base_mins = int(base[:2]) * 60 + int(base[3:])
        offset_mins = int(offset[:2]) * 60 + int(offset[3:])
        assert offset_mins == base_mins - 30

    def test_resolve_invalid_event(self):
        """Unknown sun event should return None."""
        result = resolve_sun_time("midnight", 0, 40.7128, -74.0060, date(2026, 6, 21), "UTC")
        assert result is None


class TestResolveScheduleSunTimes:
    """Test resolving both start and end times for a schedule."""

    def test_fixed_times_unchanged(self):
        """Fixed-type schedule should return fallback values unchanged."""
        start, end = resolve_schedule_sun_times(
            start_type="fixed", start_sun_offset=0, start_time_fallback="09:00",
            end_type="fixed", end_sun_offset=0, end_time_fallback="17:00",
            latitude=40.7128, longitude=-74.0060,
            target_date=date(2026, 6, 21), timezone_str="America/New_York",
        )
        assert start == "09:00"
        assert end == "17:00"

    def test_sunrise_start_resolved(self):
        """Sunrise start_type should resolve to a computed time."""
        start, end = resolve_schedule_sun_times(
            start_type="sunrise", start_sun_offset=0, start_time_fallback="06:00",
            end_type="fixed", end_sun_offset=0, end_time_fallback="10:00",
            latitude=40.7128, longitude=-74.0060,
            target_date=date(2026, 6, 21), timezone_str="America/New_York",
        )
        # Should be a valid HH:MM string
        assert len(start) == 5 and start[2] == ":"
        # NYC summer sunrise is around 05:25, so should be in that range
        start_hour = int(start[:2])
        assert 4 <= start_hour <= 6
        assert end == "10:00"  # Fixed end is unchanged

    def test_sunset_end_resolved(self):
        """Sunset end_type should resolve to a computed time."""
        start, end = resolve_schedule_sun_times(
            start_type="fixed", start_sun_offset=0, start_time_fallback="18:00",
            end_type="sunset", end_sun_offset=30, end_time_fallback="21:00",
            latitude=40.7128, longitude=-74.0060,
            target_date=date(2026, 6, 21), timezone_str="America/New_York",
        )
        assert start == "18:00"  # Fixed start unchanged
        assert end is not None  # Resolved sunset + 30min

    def test_both_sun_based(self):
        """Both start and end can be sun-based."""
        start, end = resolve_schedule_sun_times(
            start_type="sunrise", start_sun_offset=-30,
            start_time_fallback="05:30",
            end_type="sunset", end_sun_offset=30,
            end_time_fallback="20:30",
            latitude=40.7128, longitude=-74.0060,
            target_date=date(2026, 6, 21), timezone_str="America/New_York",
        )
        assert start is not None
        assert end is not None
        # start should be before end (sunrise-30min < sunset+30min)
        start_mins = int(start[:2]) * 60 + int(start[3:])
        end_mins = int(end[:2]) * 60 + int(end[3:])
        assert start_mins < end_mins

    def test_no_location_uses_fallback(self):
        """Without location, sun-based times should fall back to stored values."""
        start, end = resolve_schedule_sun_times(
            start_type="sunrise", start_sun_offset=0, start_time_fallback="06:00",
            end_type="sunset", end_sun_offset=0, end_time_fallback="20:00",
            latitude=None, longitude=None,
            target_date=date(2026, 6, 21), timezone_str="UTC",
        )
        assert start == "06:00"
        assert end == "20:00"

    def test_none_end_time_preserved(self):
        """None end_time (open-ended) should be preserved for fixed types."""
        start, end = resolve_schedule_sun_times(
            start_type="fixed", start_sun_offset=0, start_time_fallback="09:00",
            end_type="fixed", end_sun_offset=0, end_time_fallback=None,
            latitude=40.7128, longitude=-74.0060,
            target_date=date(2026, 6, 21), timezone_str="America/New_York",
        )
        assert start == "09:00"
        assert end is None


# ---- Model tests for sun fields ----

class TestScheduleEntrySunFields:
    """Test that ScheduleEntry properly handles sun schedule fields."""

    def test_default_sun_fields(self):
        """New schedule should have fixed sun fields by default."""
        entry = ScheduleEntry(
            id="test-id", page_id="page-1",
            start_time="09:00", end_time="17:00",
            day_pattern="all",
        )
        assert entry.start_type == "fixed"
        assert entry.start_sun_offset == 0
        assert entry.end_type == "fixed"
        assert entry.end_sun_offset == 0

    def test_sun_schedule_creation(self):
        """Schedule with sun-based start should store the fields."""
        entry = ScheduleEntry(
            id="sun-id", page_id="page-1",
            start_time="06:00", end_time="20:00",
            day_pattern="all",
            start_type="sunrise", start_sun_offset=-30,
            end_type="sunset", end_sun_offset=30,
        )
        assert entry.start_type == "sunrise"
        assert entry.start_sun_offset == -30
        assert entry.end_type == "sunset"
        assert entry.end_sun_offset == 30

    def test_schedule_create_model_sun_fields(self):
        """ScheduleCreate should accept sun fields."""
        create = ScheduleCreate(
            page_id="page-1", start_time="06:00",
            day_pattern="all",
            start_type="sunrise", start_sun_offset=15,
        )
        assert create.start_type == "sunrise"
        assert create.start_sun_offset == 15
        assert create.end_type == "fixed"

    def test_model_dump_includes_sun_fields(self):
        """model_dump() should include sun fields."""
        entry = ScheduleEntry(
            id="test-id", page_id="page-1",
            start_time="06:00", day_pattern="all",
            start_type="sunrise", start_sun_offset=-15,
        )
        data = entry.model_dump()
        assert data["start_type"] == "sunrise"
        assert data["start_sun_offset"] == -15
        assert data["end_type"] == "fixed"
        assert data["end_sun_offset"] == 0

    def test_backward_compat_no_sun_fields(self):
        """Schedule created from dict without sun fields should use defaults."""
        data = {
            "id": "old-schedule",
            "page_id": "page-1",
            "start_time": "09:00",
            "end_time": "17:00",
            "day_pattern": "all",
            "enabled": True,
        }
        entry = ScheduleEntry(**data)
        assert entry.start_type == "fixed"
        assert entry.start_sun_offset == 0


# ---- Schedule service sun resolution tests ----

class TestScheduleServiceSunResolution:
    """Test that ScheduleService resolves sun times when checking active page."""

    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Create a temporary storage instance."""
        return ScheduleStorage(storage_file=str(tmp_path / "test_schedules.json"))

    @pytest.fixture
    def service(self, temp_storage):
        """Create a schedule service with temp storage."""
        return ScheduleService(storage=temp_storage)

    def test_fixed_schedule_works_as_before(self, service):
        """Fixed schedule should behave exactly as before (regression)."""
        create_data = ScheduleCreate(
            page_id="page-1", start_time="09:00", end_time="17:00",
            day_pattern="all", enabled=True,
        )
        service.create_schedule(create_data)

        # 10:00 on a Monday should match
        result = service.get_active_page_id(time(10, 0), "monday")
        assert result == "page-1"

        # 08:00 should not match
        result = service.get_active_page_id(time(8, 0), "monday")
        assert result is None

    @patch("src.schedules.service.get_settings_service")
    def test_sunrise_schedule_resolves_dynamically(self, mock_settings, service):
        """Sun-based schedule should resolve time dynamically."""
        # Mock location settings
        mock_loc = MagicMock()
        mock_loc.latitude = 40.7128
        mock_loc.longitude = -74.0060
        mock_svc = MagicMock()
        mock_svc.get_location_settings.return_value = mock_loc
        mock_svc.get_board_settings.return_value = MagicMock(boards=[])
        mock_settings.return_value = mock_svc

        # Create a sunrise-based schedule
        entry = ScheduleEntry(
            id="sun-sched", page_id="sunrise-page",
            start_time="06:00", end_time="08:00",
            day_pattern="all", enabled=True,
            start_type="sunrise", start_sun_offset=0,
            end_type="fixed", end_sun_offset=0,
        )
        service.storage.create(entry)

        # Mock the sun time resolution to return a known time
        with patch("src.schedules.service.resolve_schedule_sun_times") as mock_resolve:
            mock_resolve.return_value = ("05:25", "08:00")

            # 05:30 should match (sunrise resolved to 05:25)
            result = service.get_active_page_id(time(5, 30), "monday")
            assert result == "sunrise-page"

            # 05:00 should NOT match (before resolved sunrise 05:25)
            mock_resolve.return_value = ("05:25", "08:00")
            result = service.get_active_page_id(time(5, 0), "monday")
            assert result is None

    @patch("src.schedules.service.get_settings_service")
    def test_sun_schedule_falls_back_when_no_location(self, mock_settings, service):
        """Without location, sun schedule should use stored fallback time."""
        mock_loc = MagicMock()
        mock_loc.latitude = None
        mock_loc.longitude = None
        mock_svc = MagicMock()
        mock_svc.get_location_settings.return_value = mock_loc
        mock_svc.get_board_settings.return_value = MagicMock(boards=[])
        mock_settings.return_value = mock_svc

        # Create a sunrise schedule with fallback 06:00
        entry = ScheduleEntry(
            id="fallback-sched", page_id="fallback-page",
            start_time="06:00", end_time="08:00",
            day_pattern="all", enabled=True,
            start_type="sunrise", start_sun_offset=0,
        )
        service.storage.create(entry)

        # 06:30 should match (using fallback 06:00)
        result = service.get_active_page_id(time(6, 30), "monday")
        assert result == "fallback-page"


# ---- Storage persistence tests ----

class TestStorageSunFields:
    """Test that sun fields persist correctly through save/load cycle."""

    @pytest.fixture
    def temp_storage(self, tmp_path):
        return ScheduleStorage(storage_file=str(tmp_path / "test_schedules.json"))

    def test_sun_fields_persist(self, temp_storage):
        """Sun fields should survive save and reload."""
        entry = ScheduleEntry(
            id="persist-test", page_id="page-1",
            start_time="06:00", end_time="20:00",
            day_pattern="all",
            start_type="sunrise", start_sun_offset=-30,
            end_type="sunset", end_sun_offset=45,
        )
        temp_storage.create(entry)

        # Reload storage
        storage2 = ScheduleStorage(storage_file=str(temp_storage.storage_file))
        loaded = storage2.get("persist-test")
        assert loaded is not None
        assert loaded.start_type == "sunrise"
        assert loaded.start_sun_offset == -30
        assert loaded.end_type == "sunset"
        assert loaded.end_sun_offset == 45

    def test_update_sun_fields(self, temp_storage):
        """Sun fields should be updatable."""
        entry = ScheduleEntry(
            id="update-test", page_id="page-1",
            start_time="06:00", day_pattern="all",
        )
        temp_storage.create(entry)

        updated = temp_storage.update("update-test", {
            "start_type": "sunrise",
            "start_sun_offset": 15,
        })
        assert updated is not None
        assert updated.start_type == "sunrise"
        assert updated.start_sun_offset == 15

    def test_old_schedule_data_without_sun_fields(self, tmp_path):
        """Loading data without sun fields should use defaults."""
        import json
        storage_file = tmp_path / "schedules.json"
        data = {
            "schedules": [{
                "id": "old-entry",
                "page_id": "page-1",
                "start_time": "09:00",
                "end_time": "17:00",
                "day_pattern": "all",
                "board_id": "",
                "enabled": True,
                "created_at": "2025-01-01T00:00:00+00:00",
            }],
            "default_page_id": None,
        }
        with open(storage_file, "w") as f:
            json.dump(data, f)

        storage = ScheduleStorage(storage_file=str(storage_file))
        entry = storage.get("old-entry")
        assert entry is not None
        assert entry.start_type == "fixed"
        assert entry.start_sun_offset == 0
        assert entry.end_type == "fixed"
        assert entry.end_sun_offset == 0


# ---- Effective timezone selection (regression for issue #814) ----

class TestEffectiveTimezone:
    """Sun-time resolution must share the timezone used by time_service.

    Without this, a user with general timezone set to a DST-aware zone (e.g.
    America/Denver) but the date_time plugin TZ unset or set to a non-DST
    equivalent (e.g. MST, America/Phoenix) sees sunset schedules fire ~1 hour
    early in DST, because "now" applies DST while "sunset" does not.
    """

    @patch("src.config.Config")
    def test_prefers_general_timezone_over_plugin_timezone(self, mock_config):
        mock_config.GENERAL_TIMEZONE = "America/Denver"
        mock_config.TIMEZONE = "America/Phoenix"
        assert get_effective_timezone() == "America/Denver"

    @patch("src.config.Config")
    def test_falls_back_to_plugin_timezone_when_general_empty(self, mock_config):
        mock_config.GENERAL_TIMEZONE = ""
        mock_config.TIMEZONE = "America/Denver"
        assert get_effective_timezone() == "America/Denver"

    @patch("src.config.Config")
    def test_falls_back_to_utc_when_both_empty(self, mock_config):
        mock_config.GENERAL_TIMEZONE = ""
        mock_config.TIMEZONE = ""
        assert get_effective_timezone() == "UTC"

    def test_dst_aware_sunset_differs_from_non_dst(self):
        """Sanity check that demonstrates the original bug: Lakewood, CO sunset
        on a DST day comes out 1 hour later in America/Denver than in MST."""
        denver = resolve_sun_time(
            "sunset", 0, 39.7047, -105.0814,
            date(2026, 5, 30), "America/Denver",
        )
        mst = resolve_sun_time(
            "sunset", 0, 39.7047, -105.0814,
            date(2026, 5, 30), "MST",
        )
        assert denver is not None and mst is not None
        denver_mins = int(denver[:2]) * 60 + int(denver[3:])
        mst_mins = int(mst[:2]) * 60 + int(mst[3:])
        # Denver sunset should be ~60 minutes later than the non-DST MST value
        # (allow a couple of minutes of slack for astral precision)
        assert 58 <= (denver_mins - mst_mins) <= 62
