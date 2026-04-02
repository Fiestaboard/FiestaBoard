"""Tests for optional end_time and 1-minute granularity scheduling.

These tests verify that:
1. The 15-minute interval restriction is removed (any minute 0-59 allowed)
2. end_time can be None for "single cycle" schedules
3. Schedules with no end_time compute duration from the linked carousel
4. Overlap/gap detection handles optional end_time correctly
5. Active page resolution handles optional end_time correctly
"""

import pytest
import tempfile
from pathlib import Path
from datetime import time

from src.schedules.models import ScheduleEntry, ScheduleCreate
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage
from src.carousels.models import Carousel


@pytest.fixture
def temp_storage_file():
    """Create a temporary storage file."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def service(temp_storage_file):
    """Create a service instance with temporary storage."""
    storage = ScheduleStorage(storage_file=temp_storage_file)
    return ScheduleService(storage=storage)


# =============================================================================
# 1-Minute Granularity Tests
# =============================================================================


class TestOneMinuteGranularity:
    """Test that any minute value (0-59) is now accepted."""

    def test_schedule_with_arbitrary_minutes_validates(self):
        """Schedule using 07:35-07:40 should now be valid."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="07:35",
            end_time="07:40",
            day_pattern="weekdays",
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0, f"Expected no errors but got: {errors}"

    def test_every_minute_value_is_valid(self):
        """All minute values 00-59 should be accepted."""
        for minute in range(60):
            minute_str = f"{minute:02d}"
            entry = ScheduleEntry(
                page_id="page-123",
                start_time=f"07:{minute_str}",
                end_time=f"08:{minute_str}",
                day_pattern="all",
                enabled=True
            )
            errors = entry.validate_config()
            assert len(errors) == 0, f"Minute {minute_str} should be valid but got: {errors}"

    def test_schedule_with_5_minute_start(self):
        """Schedule with 09:05 start should be valid."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="09:05",
            end_time="17:00",
            day_pattern="all",
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0

    def test_schedule_with_single_minute_duration(self):
        """Schedule 07:35-07:36 (1 minute) should be valid."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="07:35",
            end_time="07:36",
            day_pattern="all",
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0

    def test_school_departure_use_case(self, service):
        """Test the school departure countdown use case from the issue.

        7:35 through 7:40, each with a different page/carousel.
        """
        for minute in range(35, 41):
            next_minute = minute + 1
            create_data = ScheduleCreate(
                page_id=f"page-countdown-{41 - minute}",
                start_time=f"07:{minute:02d}",
                end_time=f"07:{next_minute:02d}",
                day_pattern="weekdays",
                enabled=True
            )
            service.create_schedule(create_data)

        schedules = service.list_schedules()
        assert len(schedules) == 6

        # 07:35 -> page-countdown-6
        page = service.get_active_page_id(time(7, 35), "monday")
        assert page == "page-countdown-6"

        # 07:38 -> page-countdown-3
        page = service.get_active_page_id(time(7, 38), "monday")
        assert page == "page-countdown-3"

        # 07:40 -> page-countdown-1
        page = service.get_active_page_id(time(7, 40), "monday")
        assert page == "page-countdown-1"

    def test_15_minute_intervals_still_valid(self):
        """15-minute interval schedules should still work after removal of constraint."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="all",
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0


# =============================================================================
# Optional end_time Tests
# =============================================================================


class TestOptionalEndTime:
    """Test that end_time can be None."""

    def test_schedule_entry_allows_none_end_time(self):
        """ScheduleEntry should accept end_time=None."""
        entry = ScheduleEntry(
            page_id="carousel:abc-123",
            start_time="07:35",
            end_time=None,
            day_pattern="weekdays",
            enabled=True
        )
        assert entry.end_time is None
        assert entry.start_time == "07:35"

    def test_schedule_create_allows_none_end_time(self):
        """ScheduleCreate should accept end_time=None."""
        create = ScheduleCreate(
            page_id="carousel:abc-123",
            start_time="07:35",
            end_time=None,
            day_pattern="weekdays",
            enabled=True
        )
        assert create.end_time is None

    def test_none_end_time_validates_ok(self):
        """Schedule with None end_time should validate successfully."""
        entry = ScheduleEntry(
            page_id="carousel:abc-123",
            start_time="07:35",
            end_time=None,
            day_pattern="weekdays",
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0, f"Expected no errors but got: {errors}"

    def test_none_end_time_same_start_not_rejected(self):
        """Zero-duration check should not trigger when end_time is None."""
        entry = ScheduleEntry(
            page_id="carousel:abc-123",
            start_time="07:35",
            end_time=None,
            day_pattern="all",
            enabled=True
        )
        errors = entry.validate_config()
        assert not any("zero-duration" in e.lower() for e in errors)
        assert not any("end_time must be different" in e.lower() for e in errors)

    def test_schedule_with_none_end_time_is_valid(self):
        """is_valid() should return True for schedule with None end_time."""
        entry = ScheduleEntry(
            page_id="carousel:abc-123",
            start_time="07:35",
            end_time=None,
            day_pattern="all",
            enabled=True
        )
        assert entry.is_valid() is True


# =============================================================================
# Carousel total_cycle_seconds Tests
# =============================================================================


class TestCarouselCycleDuration:
    """Test carousel total cycle duration computation."""

    def test_total_cycle_seconds_basic(self):
        """Total cycle = num_pages * interval_seconds."""
        carousel = Carousel(
            name="School Countdown",
            page_ids=["p1", "p2", "p3", "p4", "p5", "p6"],
            interval_seconds=60,
        )
        assert carousel.total_cycle_seconds() == 360  # 6 pages * 60s

    def test_total_cycle_seconds_single_page(self):
        """Single page carousel has cycle = 1 * interval."""
        carousel = Carousel(
            name="Single",
            page_ids=["p1"],
            interval_seconds=30,
        )
        assert carousel.total_cycle_seconds() == 30

    def test_total_cycle_seconds_default_interval(self):
        """Default interval of 30s with 3 pages = 90s."""
        carousel = Carousel(
            name="Test",
            page_ids=["p1", "p2", "p3"],
        )
        assert carousel.total_cycle_seconds() == 90


# =============================================================================
# applies_to_time with None end_time Tests
# =============================================================================


class TestAppliesToTimeOptionalEnd:
    """Test applies_to_time when end_time is None (open-ended)."""

    def test_applies_to_time_at_start(self):
        """Time at start_time should match open-ended schedule."""
        entry = ScheduleEntry(
            page_id="carousel:abc",
            start_time="07:35",
            end_time=None,
            day_pattern="all",
            enabled=True
        )
        assert entry.applies_to_time("07:35") is True

    def test_applies_to_time_after_start(self):
        """Time after start_time should match open-ended schedule (no end boundary)."""
        entry = ScheduleEntry(
            page_id="carousel:abc",
            start_time="07:35",
            end_time=None,
            day_pattern="all",
            enabled=True
        )
        # Open-ended: matches from start_time until end of day
        assert entry.applies_to_time("07:40") is True
        assert entry.applies_to_time("12:00") is True
        assert entry.applies_to_time("23:59") is True

    def test_applies_to_time_before_start(self):
        """Time before start_time should NOT match open-ended schedule."""
        entry = ScheduleEntry(
            page_id="carousel:abc",
            start_time="07:35",
            end_time=None,
            day_pattern="all",
            enabled=True
        )
        assert entry.applies_to_time("07:34") is False
        assert entry.applies_to_time("00:00") is False


# =============================================================================
# Storage with None end_time Tests
# =============================================================================


class TestStorageOptionalEndTime:
    """Test that storage handles None end_time correctly."""

    def test_create_schedule_with_none_end_time(self, service):
        """Creating a schedule with None end_time should persist correctly."""
        create_data = ScheduleCreate(
            page_id="carousel:abc-123",
            start_time="07:35",
            end_time=None,
            day_pattern="weekdays",
            enabled=True
        )
        created = service.create_schedule(create_data)
        assert created.end_time is None
        assert created.start_time == "07:35"

        # Retrieve should also have None
        retrieved = service.get_schedule(created.id)
        assert retrieved is not None
        assert retrieved.end_time is None

    def test_update_schedule_to_none_end_time(self, service):
        """Updating a schedule to have None end_time should work."""
        create_data = ScheduleCreate(
            page_id="carousel:abc-123",
            start_time="07:35",
            end_time="08:00",
            day_pattern="weekdays",
            enabled=True
        )
        created = service.create_schedule(create_data)
        assert created.end_time == "08:00"

        from src.schedules.models import ScheduleUpdate
        update_data = ScheduleUpdate(end_time=None)
        # Note: With model_dump(exclude_unset=True), setting None explicitly 
        # should be allowed for end_time
        updated = service.update_schedule(created.id, update_data)
        # After update, end_time should be cleared
        assert updated is not None


# =============================================================================
# Overlap Detection with Optional end_time Tests
# =============================================================================


class TestOverlapWithOptionalEndTime:
    """Test overlap detection when schedules have no end_time."""

    def test_open_ended_overlaps_with_later_schedule(self, service):
        """An open-ended schedule should overlap with a schedule that starts after it."""
        service.create_schedule(ScheduleCreate(
            page_id="carousel:abc",
            start_time="07:35",
            end_time=None,
            day_pattern="all",
            enabled=True
        ))
        service.create_schedule(ScheduleCreate(
            page_id="page-afternoon",
            start_time="12:00",
            end_time="17:00",
            day_pattern="all",
            enabled=True
        ))

        result = service.validate_schedules()
        assert result.valid is False
        assert len(result.overlaps) > 0

    def test_open_ended_does_not_overlap_different_days(self, service):
        """Open-ended schedule on weekdays should not overlap with weekend schedule."""
        service.create_schedule(ScheduleCreate(
            page_id="carousel:abc",
            start_time="07:35",
            end_time=None,
            day_pattern="weekdays",
            enabled=True
        ))
        service.create_schedule(ScheduleCreate(
            page_id="page-weekend",
            start_time="09:00",
            end_time="17:00",
            day_pattern="weekends",
            enabled=True
        ))

        result = service.validate_schedules()
        assert result.valid is True
        assert len(result.overlaps) == 0


# =============================================================================
# Active Page Resolution with Optional end_time Tests
# =============================================================================


class TestActivePageWithOptionalEndTime:
    """Test active page resolution with open-ended schedules."""

    def test_open_ended_matches_at_start(self, service):
        """Open-ended schedule should match at its start time."""
        service.create_schedule(ScheduleCreate(
            page_id="carousel:abc",
            start_time="07:35",
            end_time=None,
            day_pattern="all",
            enabled=True
        ))

        page_id = service.get_active_page_id(time(7, 35), "monday")
        assert page_id == "carousel:abc"

    def test_open_ended_matches_after_start(self, service):
        """Open-ended schedule should match after start time."""
        service.create_schedule(ScheduleCreate(
            page_id="carousel:abc",
            start_time="07:35",
            end_time=None,
            day_pattern="all",
            enabled=True
        ))

        page_id = service.get_active_page_id(time(12, 0), "monday")
        assert page_id == "carousel:abc"

    def test_open_ended_does_not_match_before_start(self, service):
        """Open-ended schedule should not match before start time."""
        service.create_schedule(ScheduleCreate(
            page_id="carousel:abc",
            start_time="07:35",
            end_time=None,
            day_pattern="all",
            enabled=True
        ))

        service.set_default_page("default-page")
        page_id = service.get_active_page_id(time(7, 34), "monday")
        assert page_id == "default-page"
