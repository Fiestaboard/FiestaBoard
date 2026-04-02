"""Tests for schedule data models."""

import pytest
from datetime import datetime
from src.schedules.models import (
    ScheduleEntry,
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleValidationResult,
    Overlap,
    Gap,
    DayPattern,
)


class TestScheduleEntry:
    """Test ScheduleEntry model."""
    
    def test_create_schedule_entry_all_days(self):
        """Test creating a schedule entry for all days."""
        entry = ScheduleEntry(
            id="test-id",
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="all",
            enabled=True
        )
        
        assert entry.id == "test-id"
        assert entry.page_id == "page-123"
        assert entry.start_time == "09:00"
        assert entry.end_time == "17:00"
        assert entry.day_pattern == "all"
        assert entry.custom_days is None
        assert entry.enabled is True
    
    def test_create_schedule_entry_weekdays(self):
        """Test creating a schedule entry for weekdays."""
        entry = ScheduleEntry(
            id="test-id",
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="weekdays",
            enabled=True
        )
        
        assert entry.day_pattern == "weekdays"
        assert entry.custom_days is None
    
    def test_create_schedule_entry_weekends(self):
        """Test creating a schedule entry for weekends."""
        entry = ScheduleEntry(
            id="test-id",
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="weekends",
            enabled=True
        )
        
        assert entry.day_pattern == "weekends"
    
    def test_create_schedule_entry_custom_days(self):
        """Test creating a schedule entry with custom days."""
        entry = ScheduleEntry(
            id="test-id",
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="custom",
            custom_days=["monday", "wednesday", "friday"],
            enabled=True
        )
        
        assert entry.day_pattern == "custom"
        assert entry.custom_days == ["monday", "wednesday", "friday"]
    
    def test_schedule_entry_generates_id(self):
        """Test that schedule entry generates UUID if not provided."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="all",
            enabled=True
        )
        
        assert entry.id is not None
        assert len(entry.id) == 36  # UUID length
    
    def test_schedule_entry_has_timestamps(self):
        """Test that schedule entry has created_at timestamp."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="all",
            enabled=True
        )
        
        assert entry.created_at is not None
        assert isinstance(entry.created_at, datetime)
        assert entry.updated_at is None
    
    def test_validate_time_format(self):
        """Test validation of time format (HH:MM)."""
        # Valid times
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="09:00",
            end_time="17:45",
            day_pattern="all",
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0
    
    def test_validate_time_format_invalid(self):
        """Test validation fails with invalid time format."""
        # Pydantic validates the pattern before our custom validation
        with pytest.raises(Exception):  # Pydantic ValidationError
            entry = ScheduleEntry(
                page_id="page-123",
                start_time="9:00",  # Should be 09:00
                end_time="17:00",
                day_pattern="all",
                enabled=True
            )
    
    def test_validate_any_minute_value(self):
        """Test validation accepts any minute value (0-59)."""
        # All minutes should now be valid (15-min restriction removed)
        for minute in [0, 5, 10, 15, 22, 30, 37, 45, 59]:
            entry = ScheduleEntry(
                page_id="page-123",
                start_time=f"09:{minute:02d}",
                end_time="17:00",
                day_pattern="all",
                enabled=True
            )
            errors = entry.validate_config()
            assert len(errors) == 0, f"Minute {minute} should be valid but got: {errors}"
    
    def test_validate_end_after_start_allows_midnight_rollover(self):
        """Test that end_time before start_time is valid (midnight rollover)."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="17:00",
            end_time="09:00",
            day_pattern="all",
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) == 0, f"Midnight rollover should be valid, got: {errors}"
    
    def test_validate_same_start_end_invalid(self):
        """Test validation rejects zero-duration schedule (same start and end)."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="12:00",
            end_time="12:00",
            day_pattern="all",
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) > 0
        assert any("end_time" in err.lower() for err in errors)
    
    def test_validate_custom_days_required(self):
        """Test validation requires custom_days when pattern is custom."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="custom",
            custom_days=None,
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) > 0
        assert any("custom_days" in err.lower() for err in errors)
    
    def test_validate_custom_days_not_empty(self):
        """Test validation requires at least one custom day."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="custom",
            custom_days=[],
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) > 0
        assert any("at least one" in err.lower() or "must contain" in err.lower() for err in errors)
    
    def test_validate_custom_days_valid_names(self):
        """Test validation checks day names are valid."""
        entry = ScheduleEntry(
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="custom",
            custom_days=["monday", "invalid_day"],
            enabled=True
        )
        errors = entry.validate_config()
        assert len(errors) > 0
        assert any("invalid day" in err.lower() for err in errors)
    
    def test_is_valid(self):
        """Test is_valid helper method."""
        valid_entry = ScheduleEntry(
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="all",
            enabled=True
        )
        assert valid_entry.is_valid() is True
        
        # Midnight rollover is valid (not an error)
        rollover_entry = ScheduleEntry(
            page_id="page-123",
            start_time="17:00",
            end_time="09:00",
            day_pattern="all",
            enabled=True
        )
        assert rollover_entry.is_valid() is True
        
        # Zero-duration is invalid
        invalid_entry = ScheduleEntry(
            page_id="page-123",
            start_time="12:00",
            end_time="12:00",
            day_pattern="all",
            enabled=True
        )
        assert invalid_entry.is_valid() is False


class TestScheduleCreate:
    """Test ScheduleCreate model."""
    
    def test_create_request(self):
        """Test creating a schedule create request."""
        create = ScheduleCreate(
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="weekdays",
            enabled=True
        )
        
        assert create.page_id == "page-123"
        assert create.start_time == "09:00"
        assert create.end_time == "17:00"
        assert create.day_pattern == "weekdays"
        assert create.enabled is True
    
    def test_create_defaults_enabled_true(self):
        """Test that enabled defaults to True."""
        create = ScheduleCreate(
            page_id="page-123",
            start_time="09:00",
            end_time="17:00",
            day_pattern="all"
        )
        
        assert create.enabled is True


class TestScheduleUpdate:
    """Test ScheduleUpdate model."""
    
    def test_update_request_partial(self):
        """Test that update request allows partial updates."""
        update = ScheduleUpdate(
            start_time="10:00"
        )
        
        assert update.start_time == "10:00"
        assert update.end_time is None
        assert update.page_id is None


class TestValidationModels:
    """Test validation result models."""
    
    def test_overlap(self):
        """Test Overlap model."""
        overlap = Overlap(
            schedule1_id="sched-1",
            schedule2_id="sched-2",
            conflict_description="Both active Monday 9:00-10:00"
        )
        
        assert overlap.schedule1_id == "sched-1"
        assert overlap.schedule2_id == "sched-2"
        assert "Monday" in overlap.conflict_description
    
    def test_gap(self):
        """Test Gap model."""
        gap = Gap(
            start_time="12:00",
            end_time="13:00",
            days=["monday", "tuesday"]
        )
        
        assert gap.start_time == "12:00"
        assert gap.end_time == "13:00"
        assert "monday" in gap.days
    
    def test_validation_result_valid(self):
        """Test validation result when valid."""
        result = ScheduleValidationResult(
            valid=True,
            overlaps=[],
            gaps=[]
        )
        
        assert result.valid is True
        assert len(result.overlaps) == 0
        assert len(result.gaps) == 0
    
    def test_validation_result_with_overlaps(self):
        """Test validation result with overlaps."""
        overlap = Overlap(
            schedule1_id="sched-1",
            schedule2_id="sched-2",
            conflict_description="Conflict"
        )
        
        result = ScheduleValidationResult(
            valid=False,
            overlaps=[overlap],
            gaps=[]
        )
        
        assert result.valid is False
        assert len(result.overlaps) == 1
    
    def test_validation_result_with_gaps(self):
        """Test validation result with gaps."""
        gap = Gap(
            start_time="12:00",
            end_time="13:00",
            days=["monday"]
        )
        
        result = ScheduleValidationResult(
            valid=True,
            overlaps=[],
            gaps=[gap]
        )
        
        assert result.valid is True
        assert len(result.gaps) == 1
