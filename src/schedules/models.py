"""Data models for schedule entries.

Schedules allow automatic time-based page rotation with day-of-week patterns.
"""

from datetime import datetime, timezone
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict
import uuid
import re


DayPattern = Literal["all", "weekdays", "weekends", "custom"]

VALID_DAYS = [
    "monday", "tuesday", "wednesday", "thursday", 
    "friday", "saturday", "sunday"
]

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
WEEKENDS = ["saturday", "sunday"]


# Sentinel for "default" board when board_id was not set (backward compat)
DEFAULT_BOARD_ID = ""

class ScheduleEntry(BaseModel):
    """A schedule entry defining when a page should be displayed.

    Schedules support any HH:MM start/end time and various day patterns.
    end_time is optional: when None the schedule is "open-ended" (runs from
    start_time until the end of the day or until a higher-priority schedule
    takes over).
    Each entry is scoped to a board via board_id (empty string = default/first board).
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    board_id: str = Field(default=DEFAULT_BOARD_ID, min_length=0)  # "" = default board
    page_id: str = Field(min_length=1)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")  # HH:MM format
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")  # HH:MM format or None
    day_pattern: DayPattern
    custom_days: Optional[List[str]] = None
    enabled: bool = True

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict()
    
    def validate_config(self) -> List[str]:
        """Validate that schedule configuration is complete and consistent.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Validate time format (HH:MM)
        time_pattern = re.compile(r"^([0-1]\d|2[0-3]):[0-5]\d$")
        if not time_pattern.match(self.start_time):
            errors.append(f"start_time must be in HH:MM format (00:00 to 23:59)")
        if self.end_time is not None and not time_pattern.match(self.end_time):
            errors.append(f"end_time must be in HH:MM format (00:00 to 23:59)")
        
        # Validate times are not identical (zero-duration schedule)
        # Note: end_time < start_time is valid (midnight rollover, e.g. 23:00-03:00)
        # When end_time is None, the schedule is open-ended (no zero-duration issue)
        if self.end_time is not None and time_pattern.match(self.start_time) and time_pattern.match(self.end_time):
            if self.start_time == self.end_time:
                errors.append("end_time must be different from start_time (zero-duration schedule)")
        
        # Validate custom_days when pattern is custom
        if self.day_pattern == "custom":
            if self.custom_days is None:
                errors.append("custom_days is required when day_pattern is 'custom'")
            elif len(self.custom_days) == 0:
                errors.append("custom_days must contain at least one day")
            else:
                for day in self.custom_days:
                    if day not in VALID_DAYS:
                        errors.append(f"Invalid day name: {day}. Must be one of {VALID_DAYS}")
        
        return errors
    
    def is_valid(self) -> bool:
        """Check if schedule configuration is valid."""
        return len(self.validate_config()) == 0
    
    def _time_to_minutes(self, time_str: str) -> int:
        """Convert HH:MM time string to minutes since midnight."""
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    
    def get_days(self) -> List[str]:
        """Get the list of days this schedule applies to.
        
        Returns:
            List of day names (lowercase)
        """
        if self.day_pattern == "all":
            return VALID_DAYS.copy()
        elif self.day_pattern == "weekdays":
            return WEEKDAYS.copy()
        elif self.day_pattern == "weekends":
            return WEEKENDS.copy()
        elif self.day_pattern == "custom":
            return self.custom_days.copy() if self.custom_days else []
        return []
    
    def applies_to_day(self, day_name: str) -> bool:
        """Check if this schedule applies to a given day.
        
        Args:
            day_name: Day name (lowercase, e.g., "monday")
            
        Returns:
            True if schedule applies to this day
        """
        return day_name.lower() in self.get_days()
    
    def applies_to_time(self, time_str: str) -> bool:
        """Check if this schedule applies to a given time.
        
        Handles midnight rollover schedules (e.g. 23:00-03:00).
        When end_time is None, the schedule is open-ended: it matches
        from start_time through the end of the day (23:59).
        
        Args:
            time_str: Time in HH:MM format
            
        Returns:
            True if schedule applies to this time
        """
        time_minutes = self._time_to_minutes(time_str)
        start_minutes = self._time_to_minutes(self.start_time)
        
        if self.end_time is None:
            # Open-ended schedule: active from start_time through 23:59
            return time_minutes >= start_minutes
        
        end_minutes = self._time_to_minutes(self.end_time)
        
        if end_minutes <= start_minutes:
            # Midnight rollover: active if time >= start OR time < end
            return time_minutes >= start_minutes or time_minutes < end_minutes
        else:
            # Normal range: active if start <= time < end
            return start_minutes <= time_minutes < end_minutes


class ScheduleCreate(BaseModel):
    """Request model for creating a new schedule entry."""
    board_id: str = Field(default=DEFAULT_BOARD_ID, min_length=0)
    page_id: str = Field(min_length=1)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    day_pattern: DayPattern
    custom_days: Optional[List[str]] = None
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    """Request model for updating an existing schedule entry."""
    board_id: Optional[str] = Field(default=None, min_length=0)
    page_id: Optional[str] = Field(default=None, min_length=1)
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    day_pattern: Optional[DayPattern] = None
    custom_days: Optional[List[str]] = None
    enabled: Optional[bool] = None


class Overlap(BaseModel):
    """Represents an overlap between two schedule entries."""
    schedule1_id: str
    schedule2_id: str
    conflict_description: str


class Gap(BaseModel):
    """Represents a gap in the schedule."""
    start_time: str
    end_time: str
    days: List[str]


class ScheduleValidationResult(BaseModel):
    """Result of schedule validation."""
    valid: bool
    overlaps: List[Overlap]
    gaps: List[Gap]
