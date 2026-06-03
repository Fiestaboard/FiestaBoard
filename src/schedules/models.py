"""Data models for schedule entries.

Schedules allow automatic time-based page rotation with day-of-week patterns,
annually-recurring specific dates (e.g. birthdays, holidays), or one-off dates.
"""

import re
import uuid
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DayPattern = Literal["all", "weekdays", "weekends", "custom"]
TimeType = Literal["fixed", "sunrise", "sunset"]
RecurrenceType = Literal["weekly", "annual_date", "one_off_date"]

MMDD_PATTERN = r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"
YYYYMMDD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"

VALID_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

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
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")  # HH:MM format or None
    day_pattern: DayPattern = "all"
    custom_days: list[str] | None = None
    enabled: bool = True

    # Recurrence: "weekly" (default, uses day_pattern/custom_days),
    # "annual_date" (MM-DD, repeats annually), or "one_off_date" (YYYY-MM-DD).
    # Date-specific recurrences override weekly entries during their window.
    recurrence_type: RecurrenceType = "weekly"
    annual_date: str | None = Field(default=None, pattern=MMDD_PATTERN)
    annual_end_date: str | None = Field(default=None, pattern=MMDD_PATTERN)
    one_off_date: str | None = Field(default=None, pattern=YYYYMMDD_PATTERN)
    one_off_end_date: str | None = Field(default=None, pattern=YYYYMMDD_PATTERN)

    # Sun schedule fields
    start_type: TimeType = "fixed"
    start_sun_offset: int = 0  # minutes (positive = after, negative = before)
    end_type: TimeType = "fixed"
    end_sun_offset: int = 0  # minutes (positive = after, negative = before)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime | None = None

    model_config = ConfigDict()

    def validate_config(self) -> list[str]:
        """Validate that schedule configuration is complete and consistent.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Validate time format (HH:MM)
        time_pattern = re.compile(r"^([0-1]\d|2[0-3]):[0-5]\d$")
        if not time_pattern.match(self.start_time):
            errors.append("start_time must be in HH:MM format (00:00 to 23:59)")
        if self.end_time is not None and not time_pattern.match(self.end_time):
            errors.append("end_time must be in HH:MM format (00:00 to 23:59)")

        # Validate times are not identical (zero-duration schedule)
        # Note: end_time < start_time is valid (midnight rollover, e.g. 23:00-03:00)
        # When end_time is None, the schedule is open-ended (no zero-duration issue)
        if (
            self.end_time is not None
            and time_pattern.match(self.start_time)
            and time_pattern.match(self.end_time)
            and self.start_time == self.end_time
        ):
            errors.append("end_time must be different from start_time (zero-duration schedule)")

        # Validate custom_days when pattern is custom (weekly recurrence only)
        if self.recurrence_type == "weekly" and self.day_pattern == "custom":
            if self.custom_days is None:
                errors.append("custom_days is required when day_pattern is 'custom'")
            elif len(self.custom_days) == 0:
                errors.append("custom_days must contain at least one day")
            else:
                for day in self.custom_days:
                    if day not in VALID_DAYS:
                        errors.append(f"Invalid day name: {day}. Must be one of {VALID_DAYS}")

        # Validate date-specific recurrence fields
        if self.recurrence_type == "annual_date":
            if not self.annual_date:
                errors.append("annual_date (MM-DD) is required when recurrence_type is 'annual_date'")
            elif not _valid_mmdd(self.annual_date):
                errors.append(f"annual_date must be a real MM-DD calendar date: {self.annual_date}")
            if self.annual_end_date and not _valid_mmdd(self.annual_end_date):
                errors.append(f"annual_end_date must be a real MM-DD calendar date: {self.annual_end_date}")
        elif self.recurrence_type == "one_off_date":
            if not self.one_off_date:
                errors.append("one_off_date (YYYY-MM-DD) is required when recurrence_type is 'one_off_date'")
            elif not _valid_iso_date(self.one_off_date):
                errors.append(f"one_off_date must be a real YYYY-MM-DD calendar date: {self.one_off_date}")
            if self.one_off_end_date:
                if not _valid_iso_date(self.one_off_end_date):
                    errors.append(f"one_off_end_date must be a real YYYY-MM-DD calendar date: {self.one_off_end_date}")
                elif (
                    self.one_off_date
                    and _valid_iso_date(self.one_off_date)
                    and self.one_off_end_date < self.one_off_date
                ):
                    errors.append("one_off_end_date must be on or after one_off_date")

        return errors

    def is_valid(self) -> bool:
        """Check if schedule configuration is valid."""
        return len(self.validate_config()) == 0

    def _time_to_minutes(self, time_str: str) -> int:
        """Convert HH:MM time string to minutes since midnight."""
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    def get_days(self) -> list[str]:
        """Get the list of days this schedule applies to.

        Returns:
            List of day names (lowercase)
        """
        if self.day_pattern == "all":
            return VALID_DAYS.copy()
        if self.day_pattern == "weekdays":
            return WEEKDAYS.copy()
        if self.day_pattern == "weekends":
            return WEEKENDS.copy()
        if self.day_pattern == "custom":
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

    def applies_to_date(self, today: date) -> bool:
        """Check if this schedule applies on the given calendar date.

        - "weekly" recurrence always returns True (date is not constrained;
          callers also check applies_to_day).
        - "annual_date" matches today's MM-DD against annual_date / annual_end_date,
          handling year-boundary ranges (e.g. Dec 30 - Jan 02).
        - "one_off_date" matches the full YYYY-MM-DD, optionally as a range.
        """
        if self.recurrence_type == "weekly":
            return True
        if self.recurrence_type == "annual_date":
            if not self.annual_date:
                return False
            return _mmdd_in_range(
                f"{today.month:02d}-{today.day:02d}",
                self.annual_date,
                self.annual_end_date,
            )
        if self.recurrence_type == "one_off_date":
            if not self.one_off_date:
                return False
            today_iso = today.isoformat()
            start = self.one_off_date
            end = self.one_off_end_date or self.one_off_date
            return start <= today_iso <= end
        return False

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
        # Normal range: active if start <= time < end
        return start_minutes <= time_minutes < end_minutes


class ScheduleCreate(BaseModel):
    """Request model for creating a new schedule entry."""

    board_id: str = Field(default=DEFAULT_BOARD_ID, min_length=0)
    page_id: str = Field(min_length=1)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    day_pattern: DayPattern = "all"
    custom_days: list[str] | None = None
    enabled: bool = True
    recurrence_type: RecurrenceType = "weekly"
    annual_date: str | None = Field(default=None, pattern=MMDD_PATTERN)
    annual_end_date: str | None = Field(default=None, pattern=MMDD_PATTERN)
    one_off_date: str | None = Field(default=None, pattern=YYYYMMDD_PATTERN)
    one_off_end_date: str | None = Field(default=None, pattern=YYYYMMDD_PATTERN)
    start_type: TimeType = "fixed"
    start_sun_offset: int = 0
    end_type: TimeType = "fixed"
    end_sun_offset: int = 0


class ScheduleUpdate(BaseModel):
    """Request model for updating an existing schedule entry."""

    board_id: str | None = Field(default=None, min_length=0)
    page_id: str | None = Field(default=None, min_length=1)
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    day_pattern: DayPattern | None = None
    custom_days: list[str] | None = None
    enabled: bool | None = None
    recurrence_type: RecurrenceType | None = None
    annual_date: str | None = Field(default=None, pattern=MMDD_PATTERN)
    annual_end_date: str | None = Field(default=None, pattern=MMDD_PATTERN)
    one_off_date: str | None = Field(default=None, pattern=YYYYMMDD_PATTERN)
    one_off_end_date: str | None = Field(default=None, pattern=YYYYMMDD_PATTERN)
    start_type: TimeType | None = None
    start_sun_offset: int | None = None
    end_type: TimeType | None = None
    end_sun_offset: int | None = None


class Overlap(BaseModel):
    """Represents an overlap between two schedule entries."""

    schedule1_id: str
    schedule2_id: str
    conflict_description: str


class Gap(BaseModel):
    """Represents a gap in the schedule."""

    start_time: str
    end_time: str
    days: list[str]


class ScheduleValidationResult(BaseModel):
    """Result of schedule validation."""

    valid: bool
    overlaps: list[Overlap]
    gaps: list[Gap]


def _valid_mmdd(value: str) -> bool:
    """Validate MM-DD against the real calendar (uses leap year 2024 so 02-29 is allowed)."""
    if not re.match(MMDD_PATTERN, value):
        return False
    try:
        month, day = (int(p) for p in value.split("-"))
        date(2024, month, day)
        return True
    except ValueError:
        return False


def _valid_iso_date(value: str) -> bool:
    """Validate YYYY-MM-DD against the real calendar."""
    if not re.match(YYYYMMDD_PATTERN, value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _mmdd_in_range(today_mmdd: str, start_mmdd: str, end_mmdd: str | None) -> bool:
    """Check if today's MM-DD falls in [start_mmdd, end_mmdd], handling year-boundary ranges.

    When end_mmdd is None or equals start_mmdd, matches only on start_mmdd.
    When end_mmdd < start_mmdd lexicographically, the range wraps the year boundary
    (e.g. start=12-30, end=01-02 matches Dec 30, 31, Jan 1, Jan 2).
    """
    if not end_mmdd or end_mmdd == start_mmdd:
        return today_mmdd == start_mmdd
    if start_mmdd <= end_mmdd:
        return start_mmdd <= today_mmdd <= end_mmdd
    # Year-boundary wrap
    return today_mmdd >= start_mmdd or today_mmdd <= end_mmdd
