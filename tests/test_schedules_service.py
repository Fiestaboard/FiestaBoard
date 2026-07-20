"""Tests for schedule service."""

import tempfile
from datetime import time, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.schedules.models import ScheduleCreate
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage


@pytest.fixture
def temp_storage_file():
    """Create a temporary storage file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def service(temp_storage_file):
    """Create a service instance with temporary storage."""
    storage = ScheduleStorage(storage_file=temp_storage_file)
    return ScheduleService(storage=storage)


class TestScheduleServiceCRUD:
    """Test CRUD operations."""

    def test_list_schedules_empty(self, service):
        """Test listing schedules when empty."""
        schedules = service.list_schedules()
        assert len(schedules) == 0

    def test_list_schedules_by_first_board_id_includes_legacy_default_board(self, service, monkeypatch):
        """Schedules with board_id '' must show when UI filters by first board id."""
        create_data = ScheduleCreate(
            page_id="page-legacy",
            start_time="09:00",
            end_time="10:00",
            day_pattern="all",
            enabled=True,
        )
        created = service.create_schedule(create_data)

        mock_gs = MagicMock()
        mock_gs.get_board_settings.return_value.boards = [
            {"id": "first-board-uuid", "name": "A"},
            {"id": "second-board-uuid", "name": "B"},
        ]
        # list_schedules() resolves the primary board via get_primary_board_id().
        mock_gs.get_primary_board_id.return_value = "first-board-uuid"
        monkeypatch.setattr(
            "src.schedules.service.get_settings_service",
            lambda: mock_gs,
        )

        by_first = service.list_schedules(board_id="first-board-uuid")
        assert len(by_first) == 1
        assert by_first[0].id == created.id

        by_second = service.list_schedules(board_id="second-board-uuid")
        assert len(by_second) == 0

    def test_create_schedule(self, service):
        """Test creating a schedule."""
        create_data = ScheduleCreate(
            page_id="page-123", start_time="09:00", end_time="17:00", day_pattern="weekdays", enabled=True
        )

        created = service.create_schedule(create_data)

        assert created.page_id == "page-123"
        assert created.start_time == "09:00"
        assert created.end_time == "17:00"
        assert created.id is not None

    def test_get_schedule(self, service):
        """Test getting a schedule by ID."""
        create_data = ScheduleCreate(
            page_id="page-123", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True
        )
        created = service.create_schedule(create_data)

        retrieved = service.get_schedule(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_update_schedule(self, service):
        """Test updating a schedule."""
        create_data = ScheduleCreate(
            page_id="page-123", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True
        )
        created = service.create_schedule(create_data)

        from src.schedules.models import ScheduleUpdate

        update_data = ScheduleUpdate(start_time="10:00", enabled=False)

        updated = service.update_schedule(created.id, update_data)
        assert updated is not None
        assert updated.start_time == "10:00"
        assert updated.enabled is False

    def test_delete_schedule(self, service):
        """Test deleting a schedule."""
        create_data = ScheduleCreate(
            page_id="page-123", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True
        )
        created = service.create_schedule(create_data)

        result = service.delete_schedule(created.id)
        assert result is True

        assert service.get_schedule(created.id) is None


class TestActivePageResolution:
    """Test active page resolution logic."""

    def test_get_active_page_id_no_schedules(self, service):
        """Test active page when no schedules exist."""
        # Monday 09:00
        page_id = service.get_active_page_id(time(9, 0), "monday")
        assert page_id is None

    def test_get_active_page_id_with_default(self, service):
        """Test active page falls back to default when no match."""
        service.set_default_page("default-page")

        # No schedules, should return default
        page_id = service.get_active_page_id(time(9, 0), "monday")
        assert page_id == "default-page"

    def test_get_active_page_id_matches_schedule(self, service):
        """Test active page when schedule matches."""
        create_data = ScheduleCreate(
            page_id="work-page", start_time="09:00", end_time="17:00", day_pattern="weekdays", enabled=True
        )
        service.create_schedule(create_data)

        # Monday 12:00 - should match weekdays schedule
        page_id = service.get_active_page_id(time(12, 0), "monday")
        assert page_id == "work-page"

    def test_get_active_page_id_disabled_schedule_ignored(self, service):
        """Test that disabled schedules are ignored."""
        create_data = ScheduleCreate(
            page_id="work-page",
            start_time="09:00",
            end_time="17:00",
            day_pattern="all",
            enabled=False,  # Disabled
        )
        service.create_schedule(create_data)

        service.set_default_page("default-page")

        # Should use default, not disabled schedule
        page_id = service.get_active_page_id(time(12, 0), "monday")
        assert page_id == "default-page"

    def test_get_active_page_id_before_schedule(self, service):
        """Test active page before schedule starts."""
        create_data = ScheduleCreate(
            page_id="work-page", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True
        )
        service.create_schedule(create_data)

        service.set_default_page("default-page")

        # 06:00 - before schedule
        page_id = service.get_active_page_id(time(6, 0), "monday")
        assert page_id == "default-page"

    def test_get_active_page_id_after_schedule(self, service):
        """Test active page after schedule ends."""
        create_data = ScheduleCreate(
            page_id="work-page", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True
        )
        service.create_schedule(create_data)

        service.set_default_page("default-page")

        # 18:00 - after schedule (17:00 is exclusive)
        page_id = service.get_active_page_id(time(18, 0), "monday")
        assert page_id == "default-page"

    def test_get_active_page_id_at_exact_start_time(self, service):
        """Test active page at exact start time (inclusive)."""
        create_data = ScheduleCreate(
            page_id="work-page", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True
        )
        service.create_schedule(create_data)

        # 09:00 - exact start (inclusive)
        page_id = service.get_active_page_id(time(9, 0), "monday")
        assert page_id == "work-page"

    def test_get_active_page_id_at_exact_end_time(self, service):
        """Test active page at exact end time (exclusive)."""
        create_data = ScheduleCreate(
            page_id="work-page", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True
        )
        service.create_schedule(create_data)

        service.set_default_page("default-page")

        # 17:00 - exact end (exclusive)
        page_id = service.get_active_page_id(time(17, 0), "monday")
        assert page_id == "default-page"

    def test_get_active_page_id_weekdays_only(self, service):
        """Test schedule applies only to weekdays."""
        create_data = ScheduleCreate(
            page_id="work-page", start_time="09:00", end_time="17:00", day_pattern="weekdays", enabled=True
        )
        service.create_schedule(create_data)

        service.set_default_page("default-page")

        # Monday (weekday) - should match
        page_id = service.get_active_page_id(time(12, 0), "monday")
        assert page_id == "work-page"

        # Saturday (weekend) - should not match
        page_id = service.get_active_page_id(time(12, 0), "saturday")
        assert page_id == "default-page"

    def test_get_active_page_id_weekends_only(self, service):
        """Test schedule applies only to weekends."""
        create_data = ScheduleCreate(
            page_id="leisure-page", start_time="10:00", end_time="18:00", day_pattern="weekends", enabled=True
        )
        service.create_schedule(create_data)

        service.set_default_page("default-page")

        # Saturday (weekend) - should match
        page_id = service.get_active_page_id(time(12, 0), "saturday")
        assert page_id == "leisure-page"

        # Monday (weekday) - should not match
        page_id = service.get_active_page_id(time(12, 0), "monday")
        assert page_id == "default-page"

    def test_get_active_page_id_custom_days(self, service):
        """Test schedule with custom days."""
        create_data = ScheduleCreate(
            page_id="custom-page",
            start_time="09:00",
            end_time="17:00",
            day_pattern="custom",
            custom_days=["monday", "wednesday", "friday"],
            enabled=True,
        )
        service.create_schedule(create_data)

        service.set_default_page("default-page")

        # Monday - should match
        page_id = service.get_active_page_id(time(12, 0), "monday")
        assert page_id == "custom-page"

        # Tuesday - should not match
        page_id = service.get_active_page_id(time(12, 0), "tuesday")
        assert page_id == "default-page"

        # Wednesday - should match
        page_id = service.get_active_page_id(time(12, 0), "wednesday")
        assert page_id == "custom-page"


class TestWeeklyConflictTiebreaker:
    """Within the weekly tier, the schedule that started most recently wins."""

    def test_later_start_time_wins_over_earlier(self, service):
        # 08:00–13:00 and 10:00–13:00 both cover Monday at 10:30. The 10:00
        # window began more recently, so its page should display.
        service.create_schedule(
            ScheduleCreate(
                page_id="morning-page",
                start_time="08:00",
                end_time="13:00",
                day_pattern="all",
            )
        )
        service.create_schedule(
            ScheduleCreate(
                page_id="late-morning-page",
                start_time="10:00",
                end_time="13:00",
                day_pattern="all",
            )
        )
        assert service.get_active_page_id(time(10, 30), "monday") == "late-morning-page"

    def test_later_start_wins_regardless_of_created_at_order(self, service):
        # Create the later-starting schedule first, then the earlier-starting
        # one. The later start_time must still win even though it is older.
        later = service.create_schedule(
            ScheduleCreate(
                page_id="late-morning-page",
                start_time="10:00",
                end_time="13:00",
                day_pattern="all",
            )
        )
        later.created_at = later.created_at - timedelta(hours=1)
        service.storage._schedules[later.id] = later

        service.create_schedule(
            ScheduleCreate(
                page_id="morning-page",
                start_time="08:00",
                end_time="13:00",
                day_pattern="all",
            )
        )
        assert service.get_active_page_id(time(10, 30), "monday") == "late-morning-page"

    def test_identical_start_time_falls_back_to_created_at(self, service):
        # Two schedules with the same start_time tie on the primary key, so the
        # more recently created one wins.
        first = service.create_schedule(
            ScheduleCreate(
                page_id="first-page",
                start_time="09:00",
                end_time="17:00",
                day_pattern="all",
            )
        )
        first.created_at = first.created_at - timedelta(seconds=5)
        service.storage._schedules[first.id] = first

        service.create_schedule(
            ScheduleCreate(
                page_id="second-page",
                start_time="09:00",
                end_time="17:00",
                day_pattern="all",
            )
        )
        assert service.get_active_page_id(time(12, 0), "monday") == "second-page"

    def test_midnight_rollover_respects_actual_elapsed(self, service):
        # Two overnight schedules both active at 02:00:
        #   23:00–04:00 started 3h ago (yesterday at 23:00)
        #   01:00–04:00 started 1h ago (today at 01:00)
        # The 01:00 one started more recently and must win.
        service.create_schedule(
            ScheduleCreate(
                page_id="late-night-page",
                start_time="23:00",
                end_time="04:00",
                day_pattern="all",
            )
        )
        service.create_schedule(
            ScheduleCreate(
                page_id="early-morning-page",
                start_time="01:00",
                end_time="04:00",
                day_pattern="all",
            )
        )
        assert service.get_active_page_id(time(2, 0), "monday") == "early-morning-page"


class TestValidation:
    """Test schedule validation."""

    def test_validate_schedules_no_overlaps(self, service):
        """Test validation with no overlaps."""
        # Create non-overlapping schedules
        service.create_schedule(
            ScheduleCreate(
                page_id="morning-page", start_time="06:00", end_time="12:00", day_pattern="all", enabled=True
            )
        )

        service.create_schedule(
            ScheduleCreate(
                page_id="afternoon-page", start_time="12:00", end_time="18:00", day_pattern="all", enabled=True
            )
        )

        result = service.validate_schedules()
        assert result.valid is True
        assert len(result.overlaps) == 0

    def test_validate_schedules_with_time_overlap(self, service):
        """Test validation detects time overlaps."""
        # Create overlapping schedules (same day pattern, overlapping times)
        service.create_schedule(
            ScheduleCreate(page_id="page-1", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True)
        )

        service.create_schedule(
            ScheduleCreate(
                page_id="page-2",
                start_time="15:00",  # Overlaps with previous
                end_time="20:00",
                day_pattern="all",
                enabled=True,
            )
        )

        result = service.validate_schedules()
        assert result.valid is False
        assert len(result.overlaps) > 0

    def test_validate_schedules_different_days_no_overlap(self, service):
        """Test schedules on different days don't overlap."""
        # Same times but different days
        service.create_schedule(
            ScheduleCreate(
                page_id="weekday-page", start_time="09:00", end_time="17:00", day_pattern="weekdays", enabled=True
            )
        )

        service.create_schedule(
            ScheduleCreate(
                page_id="weekend-page", start_time="09:00", end_time="17:00", day_pattern="weekends", enabled=True
            )
        )

        result = service.validate_schedules()
        assert result.valid is True
        assert len(result.overlaps) == 0

    def test_validate_schedules_partial_day_overlap(self, service):
        """Test overlaps when days partially overlap."""
        # "all" includes weekdays, so these overlap on weekdays
        service.create_schedule(
            ScheduleCreate(
                page_id="weekday-page", start_time="09:00", end_time="17:00", day_pattern="weekdays", enabled=True
            )
        )

        service.create_schedule(
            ScheduleCreate(page_id="all-page", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True)
        )

        result = service.validate_schedules()
        assert result.valid is False
        assert len(result.overlaps) > 0

    def test_validate_schedules_ignores_disabled(self, service):
        """Test validation ignores disabled schedules."""
        service.create_schedule(
            ScheduleCreate(page_id="page-1", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True)
        )

        service.create_schedule(
            ScheduleCreate(
                page_id="page-2",
                start_time="15:00",
                end_time="20:00",
                day_pattern="all",
                enabled=False,  # Disabled - should be ignored
            )
        )

        result = service.validate_schedules()
        assert result.valid is True
        assert len(result.overlaps) == 0

    def test_detect_gaps_full_day(self, service):
        """Test gap detection for a full day."""
        # Only schedule 9-17, leaves gaps before and after
        service.create_schedule(
            ScheduleCreate(page_id="work-page", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True)
        )

        result = service.validate_schedules()

        # Should have gaps: 00:00-09:00 and 17:00-24:00 (represented as 23:59)
        assert len(result.gaps) > 0

    def test_detect_gaps_no_gaps(self, service):
        """Test no gaps when day is fully covered."""
        service.create_schedule(
            ScheduleCreate(
                page_id="all-day-page",
                start_time="00:00",
                end_time="23:45",  # Last 15-min slot
                day_pattern="all",
                enabled=True,
            )
        )

        result = service.validate_schedules()

        # Should have no significant gaps
        # (might have tiny gap for 23:45-24:00)
        gaps_larger_than_15min = [g for g in result.gaps if service._time_diff_minutes(g.start_time, g.end_time) > 15]
        assert len(gaps_larger_than_15min) == 0

    def test_detect_gaps_entire_day_uncovered(self, service):
        """Days with zero schedules produce an all-day gap entry."""
        # Weekdays-only schedule leaves Saturday and Sunday fully uncovered
        service.create_schedule(
            ScheduleCreate(
                page_id="work-page",
                start_time="00:00",
                end_time="23:59",
                day_pattern="weekdays",
                enabled=True,
            )
        )

        result = service.validate_schedules()
        gap_days = {day for gap in result.gaps for day in gap.days}
        assert "saturday" in gap_days
        assert "sunday" in gap_days

    def test_validate_uses_resolved_sun_times_not_fallbacks(self, service, monkeypatch):
        """Regression test for #924: validation must resolve sun-based times
        before checking for overlaps. Otherwise two non-overlapping sunset
        schedules with shared placeholder fallbacks are wrongly reported as
        conflicts."""
        # Configure a location so sun resolution runs
        mock_settings = MagicMock()
        mock_settings.get_location_settings.return_value.latitude = 40.7128
        mock_settings.get_location_settings.return_value.longitude = -74.0060
        mock_settings.get_board_settings.return_value.boards = []
        monkeypatch.setattr(
            "src.schedules.service.get_settings_service",
            lambda: mock_settings,
        )
        monkeypatch.setattr(
            "src.schedules.service.get_effective_timezone",
            lambda: "America/New_York",
        )

        # Stub the sun-time resolver so the test is deterministic. The two
        # schedules below both have stored fallback start_time="00:00", but
        # after sun resolution one runs sunset to 22:00 and the other runs
        # 06:00 until sunset — so they do not actually overlap.
        def fake_resolver(*, start_type, end_type, start_time_fallback, end_time_fallback, **kwargs):
            start = "20:00" if start_type == "sunset" else start_time_fallback
            end = "20:00" if end_type == "sunset" else end_time_fallback
            return start, end

        monkeypatch.setattr(
            "src.schedules.service.resolve_schedule_sun_times",
            fake_resolver,
        )

        # Schedule A: sunset (~20:00) until 22:00
        service.create_schedule(
            ScheduleCreate(
                page_id="evening-page",
                start_time="00:00",  # placeholder fallback for sunset
                end_time="22:00",
                day_pattern="all",
                enabled=True,
                start_type="sunset",
            )
        )
        # Schedule B: 06:00 until sunset (~20:00)
        service.create_schedule(
            ScheduleCreate(
                page_id="daytime-page",
                start_time="06:00",
                end_time="00:00",  # placeholder fallback for sunset
                day_pattern="all",
                enabled=True,
                end_type="sunset",
            )
        )

        result = service.validate_schedules()
        assert result.valid is True, (
            f"Sun-based schedules should not conflict once resolved, "
            f"got overlaps: {[o.conflict_description for o in result.overlaps]}"
        )
        assert len(result.overlaps) == 0


class TestHelpers:
    """Tests for internal helper methods and module-level utilities."""

    def test_list_schedules_wildcard_returns_all_boards(self, service):
        """list_schedules('*') returns schedules from all board_ids."""
        s1 = service.create_schedule(
            ScheduleCreate(
                board_id="board-a",
                page_id="p1",
                start_time="09:00",
                end_time="17:00",
                day_pattern="all",
                enabled=True,
            )
        )
        s2 = service.create_schedule(
            ScheduleCreate(
                board_id="board-b",
                page_id="p2",
                start_time="09:00",
                end_time="17:00",
                day_pattern="all",
                enabled=True,
            )
        )
        all_schedules = service.list_schedules(board_id="*")
        ids = {s.id for s in all_schedules}
        assert s1.id in ids
        assert s2.id in ids

    def test_time_diff_minutes(self, service):
        """_time_diff_minutes returns correct minute count."""
        assert service._time_diff_minutes("09:00", "17:00") == 480
        assert service._time_diff_minutes("00:00", "23:59") == 1439
        assert service._time_diff_minutes("12:30", "12:45") == 15

    def test_get_schedule_service_singleton(self):
        """get_schedule_service() returns the same instance on repeated calls."""
        from src.schedules import service as svc_module

        svc_module._schedule_service = None  # Reset so we get a fresh one
        try:
            svc1 = svc_module.get_schedule_service()
            svc2 = svc_module.get_schedule_service()
            assert svc1 is svc2
        finally:
            svc_module._schedule_service = None  # Clean up singleton


class TestDefaultPage:
    """Test default page management."""

    def test_get_default_page_initial(self, service):
        """Test getting default page when not set."""
        assert service.get_default_page() is None

    def test_set_default_page(self, service):
        """Test setting default page."""
        service.set_default_page("page-123")
        assert service.get_default_page() == "page-123"

    def test_clear_default_page(self, service):
        """Test clearing default page."""
        service.set_default_page("page-123")
        service.set_default_page(None)
        assert service.get_default_page() is None
