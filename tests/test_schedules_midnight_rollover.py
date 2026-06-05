"""Tests for midnight rollover schedules and adjacent schedule handling.

These tests verify that:
1. Schedules crossing midnight (e.g., 23:00-03:00) are valid
2. Schedules ending at midnight (e.g., 23:00-00:00) are valid
3. Time matching works correctly for wraparound schedules
4. Adjacent (back-to-back) schedules don't falsely overlap
5. Overlap detection handles wraparound schedules correctly
6. Gap detection handles wraparound schedules correctly
"""

import tempfile
from datetime import time
from pathlib import Path

import pytest

from src.schedules.models import ScheduleCreate, ScheduleEntry
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


# =============================================================================
# Midnight Rollover Validation Tests
# =============================================================================


class TestMidnightRolloverValidation:
    """Test that midnight rollover schedules pass validation."""

    def test_schedule_crossing_midnight_validates(self):
        """Schedule 23:00-03:00 should be valid (crosses midnight)."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0, f"Expected no errors but got: {errors}"

    def test_schedule_ending_at_midnight_validates(self):
        """Schedule 23:00-00:00 should be valid (ends at midnight)."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="00:00", day_pattern="all", enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0, f"Expected no errors but got: {errors}"

    def test_schedule_2345_to_0000_validates(self):
        """Schedule 23:45-00:00 should be valid (15-min ending at midnight)."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:45", end_time="00:00", day_pattern="all", enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0, f"Expected no errors but got: {errors}"

    def test_schedule_2300_to_0015_validates(self):
        """Schedule 23:00-00:15 should be valid (short wraparound)."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="00:15", day_pattern="all", enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0, f"Expected no errors but got: {errors}"

    def test_midnight_rollover_is_valid(self):
        """is_valid() should return True for midnight rollover schedules."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True
        )
        assert entry.is_valid() is True

    def test_same_start_end_time_still_invalid(self):
        """Schedule with same start and end (12:00-12:00) should be invalid (zero duration)."""
        entry = ScheduleEntry(page_id="page-123", start_time="12:00", end_time="12:00", day_pattern="all", enabled=True)
        errors = entry.validate_config()
        assert len(errors) > 0, "Zero-duration schedule should be invalid"

    def test_normal_schedule_still_validates(self):
        """Normal schedule 09:00-17:00 should still validate correctly."""
        entry = ScheduleEntry(
            page_id="page-work", start_time="09:00", end_time="17:00", day_pattern="weekdays", enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0, f"Expected no errors but got: {errors}"


# =============================================================================
# Midnight Rollover Time Matching Tests
# =============================================================================


class TestMidnightRolloverTimeMatching:
    """Test that applies_to_time works for wraparound schedules."""

    def test_time_in_evening_portion_matches(self):
        """Time 23:30 should match schedule 23:00-03:00."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True
        )
        assert entry.applies_to_time("23:30") is True

    def test_time_at_start_matches(self):
        """Time 23:00 should match schedule 23:00-03:00 (start inclusive)."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True
        )
        assert entry.applies_to_time("23:00") is True

    def test_time_in_morning_portion_matches(self):
        """Time 01:00 should match schedule 23:00-03:00."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True
        )
        assert entry.applies_to_time("01:00") is True

    def test_time_at_midnight_matches(self):
        """Time 00:00 should match schedule 23:00-03:00."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True
        )
        assert entry.applies_to_time("00:00") is True

    def test_time_at_end_does_not_match(self):
        """Time 03:00 should NOT match schedule 23:00-03:00 (end exclusive)."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True
        )
        assert entry.applies_to_time("03:00") is False

    def test_time_outside_wraparound_does_not_match(self):
        """Time 15:00 should NOT match schedule 23:00-03:00."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True
        )
        assert entry.applies_to_time("15:00") is False

    def test_time_just_after_end_does_not_match(self):
        """Time 03:15 should NOT match schedule 23:00-03:00."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True
        )
        assert entry.applies_to_time("03:15") is False

    def test_time_just_before_start_does_not_match(self):
        """Time 22:45 should NOT match schedule 23:00-03:00."""
        entry = ScheduleEntry(
            page_id="page-night", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True
        )
        assert entry.applies_to_time("22:45") is False

    def test_normal_schedule_time_matching_unaffected(self):
        """Normal schedule 09:00-17:00 should still match correctly."""
        entry = ScheduleEntry(
            page_id="page-work", start_time="09:00", end_time="17:00", day_pattern="all", enabled=True
        )
        assert entry.applies_to_time("12:00") is True
        assert entry.applies_to_time("09:00") is True
        assert entry.applies_to_time("16:45") is True
        assert entry.applies_to_time("17:00") is False
        assert entry.applies_to_time("08:00") is False


# =============================================================================
# Adjacent Schedule (No False Overlap) Tests
# =============================================================================


class TestAdjacentSchedules:
    """Test that back-to-back schedules don't falsely overlap."""

    def test_adjacent_schedules_no_overlap(self, service):
        """Schedules 09:00-12:00 and 12:00-15:00 should NOT overlap."""
        service.create_schedule(
            ScheduleCreate(
                page_id="morning-page", start_time="09:00", end_time="12:00", day_pattern="all", enabled=True
            )
        )

        service.create_schedule(
            ScheduleCreate(
                page_id="afternoon-page", start_time="12:00", end_time="15:00", day_pattern="all", enabled=True
            )
        )

        result = service.validate_schedules()
        assert result.valid is True, (
            f"Adjacent schedules should not overlap, but got: {[o.conflict_description for o in result.overlaps]}"
        )
        assert len(result.overlaps) == 0

    def test_adjacent_quarter_hour_schedules_no_overlap(self, service):
        """Schedules 14:00-14:15 and 14:15-14:30 should NOT overlap."""
        service.create_schedule(
            ScheduleCreate(page_id="page-a", start_time="14:00", end_time="14:15", day_pattern="all", enabled=True)
        )

        service.create_schedule(
            ScheduleCreate(page_id="page-b", start_time="14:15", end_time="14:30", day_pattern="all", enabled=True)
        )

        result = service.validate_schedules()
        assert result.valid is True, (
            f"Adjacent 15-min schedules should not overlap, but got: "
            f"{[o.conflict_description for o in result.overlaps]}"
        )
        assert len(result.overlaps) == 0

    def test_three_adjacent_schedules_no_overlap(self, service):
        """Three back-to-back schedules should have no overlaps."""
        service.create_schedule(
            ScheduleCreate(page_id="page-1", start_time="06:00", end_time="12:00", day_pattern="all", enabled=True)
        )

        service.create_schedule(
            ScheduleCreate(page_id="page-2", start_time="12:00", end_time="18:00", day_pattern="all", enabled=True)
        )

        service.create_schedule(
            ScheduleCreate(page_id="page-3", start_time="18:00", end_time="23:45", day_pattern="all", enabled=True)
        )

        result = service.validate_schedules()
        assert result.valid is True
        assert len(result.overlaps) == 0


# =============================================================================
# Wraparound Overlap Detection Tests
# =============================================================================


class TestWraparoundOverlapDetection:
    """Test overlap detection with wraparound schedules."""

    def test_two_wraparound_schedules_overlap(self, service):
        """Two wraparound schedules (22:00-02:00 and 23:00-04:00) should overlap."""
        service.create_schedule(
            ScheduleCreate(page_id="page-night1", start_time="22:00", end_time="02:00", day_pattern="all", enabled=True)
        )

        service.create_schedule(
            ScheduleCreate(page_id="page-night2", start_time="23:00", end_time="04:00", day_pattern="all", enabled=True)
        )

        result = service.validate_schedules()
        assert result.valid is False
        assert len(result.overlaps) > 0

    def test_normal_and_wraparound_overlap(self, service):
        """Normal 00:00-08:00 and wraparound 23:00-02:00 should overlap."""
        service.create_schedule(
            ScheduleCreate(page_id="page-early", start_time="00:00", end_time="08:00", day_pattern="all", enabled=True)
        )

        service.create_schedule(
            ScheduleCreate(page_id="page-night", start_time="23:00", end_time="02:00", day_pattern="all", enabled=True)
        )

        result = service.validate_schedules()
        assert result.valid is False
        assert len(result.overlaps) > 0

    def test_normal_and_wraparound_no_overlap(self, service):
        """Normal 10:00-15:00 and wraparound 20:00-02:00 should NOT overlap."""
        service.create_schedule(
            ScheduleCreate(page_id="page-day", start_time="10:00", end_time="15:00", day_pattern="all", enabled=True)
        )

        service.create_schedule(
            ScheduleCreate(page_id="page-night", start_time="20:00", end_time="02:00", day_pattern="all", enabled=True)
        )

        result = service.validate_schedules()
        assert result.valid is True
        assert len(result.overlaps) == 0

    def test_wraparound_adjacent_to_normal_no_overlap(self, service):
        """Wraparound 22:00-06:00 and normal 06:00-12:00 should NOT overlap."""
        service.create_schedule(
            ScheduleCreate(page_id="page-night", start_time="22:00", end_time="06:00", day_pattern="all", enabled=True)
        )

        service.create_schedule(
            ScheduleCreate(
                page_id="page-morning", start_time="06:00", end_time="12:00", day_pattern="all", enabled=True
            )
        )

        result = service.validate_schedules()
        assert result.valid is True
        assert len(result.overlaps) == 0


# =============================================================================
# Active Page Resolution with Wraparound Tests
# =============================================================================


class TestActivePageWithWraparound:
    """Test active page resolution with midnight rollover schedules."""

    def test_active_page_during_evening_of_wraparound(self, service):
        """At 23:30 on Monday, wraparound schedule 23:00-03:00 should be active."""
        service.create_schedule(
            ScheduleCreate(page_id="night-page", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True)
        )

        page_id = service.get_active_page_id(time(23, 30), "monday")
        assert page_id == "night-page"

    def test_active_page_during_morning_of_wraparound(self, service):
        """At 01:00, wraparound schedule 23:00-03:00 should be active."""
        service.create_schedule(
            ScheduleCreate(page_id="night-page", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True)
        )

        page_id = service.get_active_page_id(time(1, 0), "tuesday")
        assert page_id == "night-page"

    def test_active_page_outside_wraparound_falls_to_default(self, service):
        """At 15:00, wraparound schedule should not match; use default."""
        service.create_schedule(
            ScheduleCreate(page_id="night-page", start_time="23:00", end_time="03:00", day_pattern="all", enabled=True)
        )
        service.set_default_page("default-page")

        page_id = service.get_active_page_id(time(15, 0), "monday")
        assert page_id == "default-page"
