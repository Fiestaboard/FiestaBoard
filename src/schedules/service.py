"""Schedule service for managing time-based page rotation.

Handles schedule CRUD operations, active page resolution,
and validation (overlap and gap detection).
"""

import logging
from datetime import date, time

from src.settings.service import get_settings_service

from .models import (
    DEFAULT_BOARD_ID,
    VALID_DAYS,
    Gap,
    Overlap,
    ScheduleCreate,
    ScheduleEntry,
    ScheduleUpdate,
    ScheduleValidationResult,
)
from .storage import ScheduleStorage
from .sun_times import (
    get_effective_timezone,
    get_today_in_timezone,
    resolve_schedule_sun_times,
)

logger = logging.getLogger(__name__)


class ScheduleService:
    """Service for schedule operations.

    Handles:
    - CRUD operations on schedules
    - Active page resolution based on current time/day
    - Overlap and gap detection for validation
    """

    def __init__(self, storage: ScheduleStorage | None = None):
        """Initialize schedule service.

        Args:
            storage: Schedule storage instance. Created if not provided.
        """
        self.storage = storage or ScheduleStorage()
        logger.info("ScheduleService initialized")

    # CRUD operations

    def list_schedules(self, board_id: str | None = None) -> list[ScheduleEntry]:
        """List schedules, optionally filtered by board_id."""
        if board_id == "*":
            return self.storage.list_all(board_id="*")

        schedules = self.storage.list_all(board_id=board_id)

        # Legacy schedules use board_id "" (DEFAULT_BOARD_ID) for the default board
        # slot. When the UI requests the first board by its concrete id (multi-board
        # mode), include those rows so pre-migration and API-created entries still
        # appear for the primary board.
        if board_id:
            boards = get_settings_service().get_board_settings().boards or []
            first_id = boards[0].get("id") if boards else None
            if first_id and board_id == first_id:
                legacy = self.storage.list_all(board_id=None)
                seen = {s.id for s in schedules}
                for s in legacy:
                    if s.id not in seen:
                        schedules.append(s)
                schedules.sort(key=lambda s: s.created_at)

        return schedules

    def get_schedule(self, schedule_id: str) -> ScheduleEntry | None:
        """Get a schedule by ID."""
        return self.storage.get(schedule_id)

    def create_schedule(self, data: ScheduleCreate) -> ScheduleEntry:
        """Create a new schedule.

        Args:
            data: Schedule creation data

        Returns:
            Created schedule

        Raises:
            ValueError: If schedule configuration is invalid
        """
        schedule = ScheduleEntry(
            board_id=getattr(data, "board_id", None) or DEFAULT_BOARD_ID,
            page_id=data.page_id,
            start_time=data.start_time,
            end_time=data.end_time,
            day_pattern=data.day_pattern,
            custom_days=data.custom_days,
            enabled=data.enabled,
            recurrence_type=data.recurrence_type,
            annual_date=data.annual_date,
            annual_end_date=data.annual_end_date,
            one_off_date=data.one_off_date,
            one_off_end_date=data.one_off_end_date,
            start_type=data.start_type,
            start_sun_offset=data.start_sun_offset,
            end_type=data.end_type,
            end_sun_offset=data.end_sun_offset,
        )
        return self.storage.create(schedule)

    def update_schedule(self, schedule_id: str, data: ScheduleUpdate) -> ScheduleEntry | None:
        """Update an existing schedule.

        Args:
            schedule_id: Schedule ID
            data: Update data

        Returns:
            Updated schedule or None if not found
        """
        updates = data.model_dump(exclude_unset=True)
        return self.storage.update(schedule_id, updates)

    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a schedule.

        Args:
            schedule_id: Schedule ID

        Returns:
            True if deleted, False if not found
        """
        return self.storage.delete(schedule_id)

    # Active page resolution

    def get_active_page_id(
        self,
        current_time: time,
        current_day: str,
        board_id: str | None = None,
    ) -> str | None:
        """Determine which page should be displayed based on schedules for the given board.

        Sun-based schedules (start_type/end_type of "sunrise" or "sunset") have
        their times dynamically resolved using the configured location settings.

        Priority order (highest wins):
        1. one_off_date matches (most specific — single calendar date or range)
        2. annual_date matches (recurs each year on MM-DD)
        3. weekly matches (existing day-of-week behavior)
        Within a priority tier, the most recently created entry wins.
        """
        bid = board_id or DEFAULT_BOARD_ID
        schedules = [s for s in self.list_schedules(board_id=bid) if s.enabled]
        time_str = current_time.strftime("%H:%M")

        # Pre-fetch location once for sun-time resolution. "today" is computed
        # in the configured timezone so that schedules anchored to sunset don't
        # skew when the server clock runs in a different zone than the user.
        location = self._get_location()
        today = get_today_in_timezone(location[2])

        tiers: dict[str, list[ScheduleEntry]] = {
            "one_off_date": [],
            "annual_date": [],
            "weekly": [],
        }
        for schedule in schedules:
            effective_schedule = self._resolve_effective_times(schedule, today, location)
            if not effective_schedule.applies_to_date(today):
                continue
            if effective_schedule.recurrence_type == "weekly" and not effective_schedule.applies_to_day(current_day):
                continue
            if not effective_schedule.applies_to_time(time_str):
                continue
            tiers[schedule.recurrence_type].append(schedule)

        for tier_name in ("one_off_date", "annual_date", "weekly"):
            tier_matches = tiers[tier_name]
            if tier_matches:
                tier_matches.sort(key=lambda s: s.created_at, reverse=True)
                logger.debug(
                    f"Active schedule: {tier_matches[0].id} ({tier_name}) "
                    f"for {today.isoformat()} {time_str} (board={bid})"
                )
                return tier_matches[0].page_id

        default_page_id = self.storage.get_default_page_id(board_id=bid)
        if default_page_id:
            logger.debug(f"No schedule match for {current_day} {time_str}, using default: {default_page_id}")
        else:
            logger.debug(f"No schedule match for {current_day} {time_str}, no default set")
        return default_page_id

    def _get_location(self) -> tuple[float | None, float | None, str]:
        """Get the configured location and timezone for sun time resolution.

        Returns:
            Tuple of (latitude, longitude, timezone_str).
        """
        settings = get_settings_service()
        loc = settings.get_location_settings()
        return (loc.latitude, loc.longitude, get_effective_timezone())

    def _resolve_effective_times(
        self,
        schedule: ScheduleEntry,
        target_date: date,
        location: tuple[float | None, float | None, str],
    ) -> ScheduleEntry:
        """Return a schedule with sun-based times resolved for the given date.

        If the schedule uses only fixed times, returns it unchanged.
        Otherwise creates a shallow copy with resolved start/end times.
        """
        if schedule.start_type == "fixed" and schedule.end_type == "fixed":
            return schedule

        lat, lon, tz = location
        resolved_start, resolved_end = resolve_schedule_sun_times(
            start_type=schedule.start_type,
            start_sun_offset=schedule.start_sun_offset,
            start_time_fallback=schedule.start_time,
            end_type=schedule.end_type,
            end_sun_offset=schedule.end_sun_offset,
            end_time_fallback=schedule.end_time,
            latitude=lat,
            longitude=lon,
            target_date=target_date,
            timezone_str=tz,
        )

        # Build a copy with resolved times (model_copy available in Pydantic v2)
        return schedule.model_copy(
            update={
                "start_time": resolved_start,
                "end_time": resolved_end,
            }
        )

    # Default page management

    def get_default_page(self, board_id: str | None = None) -> str | None:
        """Get the default page ID for schedule gaps for the given board."""
        return self.storage.get_default_page_id(board_id=board_id)

    def set_default_page(self, page_id: str | None, board_id: str | None = None) -> None:
        """Set the default page ID for schedule gaps for the given board."""
        self.storage.set_default_page_id(page_id, board_id=board_id)

    # Validation

    def validate_schedules(self, board_id: str | None = None) -> ScheduleValidationResult:
        """Validate schedules for overlaps and gaps (optionally for one board).

        Date-specific recurrences (annual_date / one_off_date) are intentional
        overrides and are excluded from overlap/gap detection in v1: they're
        expected to "overlap" the weekly schedule and we don't want to surface
        that as a conflict.
        """
        weekly_schedules = [
            s for s in self.list_schedules(board_id=board_id) if s.enabled and s.recurrence_type == "weekly"
        ]

        # Resolve sun-based start/end times before checking for overlaps and
        # gaps so validation reflects what the user actually scheduled (e.g.
        # "sunset until 22:00") rather than the placeholder fallback HH:MM
        # values stored on disk (see #924).
        location = self._get_location()
        today = get_today_in_timezone(location[2])
        resolved_schedules = [self._resolve_effective_times(s, today, location) for s in weekly_schedules]

        # Preserve original schedule IDs on overlaps so the UI can highlight
        # the right rows; _resolve_effective_times copies the entry so ids
        # already round-trip, but we pass resolved copies explicitly here.
        overlaps = self._detect_overlaps(resolved_schedules)
        gaps = self._detect_gaps(resolved_schedules)

        return ScheduleValidationResult(valid=len(overlaps) == 0, overlaps=overlaps, gaps=gaps)

    def _detect_overlaps(self, schedules: list[ScheduleEntry]) -> list[Overlap]:
        """Detect overlapping schedules.

        Two schedules overlap if they have:
        1. Overlapping day patterns
        2. Overlapping time ranges

        Args:
            schedules: List of enabled schedules to check

        Returns:
            List of overlaps found
        """
        overlaps = []

        # Check each pair of schedules
        for i, schedule1 in enumerate(schedules):
            for schedule2 in schedules[i + 1 :]:
                # Get days each schedule applies to
                days1 = set(schedule1.get_days())
                days2 = set(schedule2.get_days())

                # Check if days overlap
                common_days = days1 & days2
                if not common_days:
                    continue  # No day overlap

                # Check if times overlap
                if self._times_overlap(
                    schedule1.start_time, schedule1.end_time, schedule2.start_time, schedule2.end_time
                ):
                    # Build description
                    days_str = ", ".join(sorted(common_days))
                    end1_str = schedule1.end_time or "open"
                    end2_str = schedule2.end_time or "open"
                    conflict_desc = (
                        f"Schedules overlap on {days_str}: "
                        f"{schedule1.start_time}-{end1_str} and "
                        f"{schedule2.start_time}-{end2_str}"
                    )

                    overlaps.append(
                        Overlap(
                            schedule1_id=schedule1.id, schedule2_id=schedule2.id, conflict_description=conflict_desc
                        )
                    )

        return overlaps

    def _times_overlap(self, start1: str, end1: str | None, start2: str, end2: str | None) -> bool:
        """Check if two time ranges overlap.

        Handles midnight rollover schedules where end_time < start_time,
        and open-ended schedules where end_time is None.

        Args:
            start1: Start time of first range (HH:MM)
            end1: End time of first range (HH:MM, exclusive) or None (open-ended)
            start2: Start time of second range (HH:MM)
            end2: End time of second range (HH:MM, exclusive) or None (open-ended)

        Returns:
            True if times overlap
        """
        TOTAL_MINUTES = 24 * 60  # 1440
        s1 = self._time_to_minutes(start1)
        s2 = self._time_to_minutes(start2)

        # Treat None end_time as end-of-day (open-ended → runs to 23:59 = 1440)
        e1 = self._time_to_minutes(end1) if end1 is not None else TOTAL_MINUTES
        e2 = self._time_to_minutes(end2) if end2 is not None else TOTAL_MINUTES

        wrap1 = end1 is not None and e1 <= s1  # Schedule 1 crosses midnight
        wrap2 = end2 is not None and e2 <= s2  # Schedule 2 crosses midnight

        if not wrap1 and not wrap2:
            # Both normal ranges (or open-ended): standard overlap check
            return s1 < e2 and s2 < e1
        if wrap1 and wrap2:
            # Both cross midnight: they always overlap (both cover midnight)
            return True
        # One wraps, one doesn't. Check if the normal range intersects
        # either part of the wraparound range.
        # Normalize: make range1 the wrapping one, range2 the normal one
        if wrap2:
            s1, e1, s2, e2 = s2, e2, s1, e1
        # range1 wraps: covers [s1, 1440) and [0, e1)
        # range2 is normal: covers [s2, e2)
        # Overlap if range2 intersects [s1, 1440) or [0, e1)
        return s2 < e1 or e2 > s1

    def _detect_gaps(self, schedules: list[ScheduleEntry]) -> list[Gap]:
        """Detect gaps in schedule coverage.

        For each day of the week, find time periods with no scheduled page.
        Only report gaps larger than 15 minutes (single time slot).
        Handles midnight rollover schedules and open-ended schedules
        (end_time=None treated as running to end-of-day).

        Args:
            schedules: List of enabled schedules

        Returns:
            List of gaps found
        """
        TOTAL_MINUTES = 24 * 60  # 1440 minutes in a day
        gaps = []

        # Check each day of the week
        for day in VALID_DAYS:
            # Get all schedules for this day
            day_schedules = [s for s in schedules if s.applies_to_day(day)]

            if not day_schedules:
                # Entire day is a gap
                gaps.append(Gap(start_time="00:00", end_time="23:59", days=[day]))
                continue

            # Build a coverage bitmap for the day (True = covered)
            covered = [False] * TOTAL_MINUTES
            for sched in day_schedules:
                s = self._time_to_minutes(sched.start_time)
                if sched.end_time is None:
                    # Open-ended: covers from start to end of day
                    for m in range(s, TOTAL_MINUTES):
                        covered[m] = True
                else:
                    e = self._time_to_minutes(sched.end_time)
                    if e <= s:
                        # Wraparound: covers [s, 1440) and [0, e)
                        for m in range(s, TOTAL_MINUTES):
                            covered[m] = True
                        for m in range(e):
                            covered[m] = True
                    else:
                        # Normal: covers [s, e)
                        for m in range(s, e):
                            covered[m] = True

            # Find uncovered ranges
            gap_start = None
            for m in range(TOTAL_MINUTES):
                if not covered[m] and gap_start is None:
                    gap_start = m
                elif covered[m] and gap_start is not None:
                    gap_minutes = m - gap_start
                    if gap_minutes > 15:
                        gaps.append(
                            Gap(
                                start_time=self._minutes_to_time(gap_start),
                                end_time=self._minutes_to_time(m),
                                days=[day],
                            )
                        )
                    gap_start = None

            # Handle gap at end of day
            if gap_start is not None:
                gap_minutes = TOTAL_MINUTES - gap_start
                if gap_minutes > 15:
                    gaps.append(Gap(start_time=self._minutes_to_time(gap_start), end_time="23:59", days=[day]))

        # Merge gaps across multiple days with same times
        return self._merge_gaps_by_time(gaps)

    def _merge_gaps_by_time(self, gaps: list[Gap]) -> list[Gap]:
        """Merge gaps with same start/end times across multiple days.

        Args:
            gaps: List of gaps (one per day)

        Returns:
            List of merged gaps
        """
        if not gaps:
            return []

        # Group by time range
        time_groups = {}
        for gap in gaps:
            key = (gap.start_time, gap.end_time)
            if key not in time_groups:
                time_groups[key] = []
            time_groups[key].extend(gap.days)

        # Create merged gaps
        merged = []
        for (start_time, end_time), days in time_groups.items():
            merged.append(
                Gap(
                    start_time=start_time,
                    end_time=end_time,
                    days=sorted(set(days)),  # Remove duplicates and sort
                )
            )

        return merged

    def _time_to_minutes(self, time_str: str) -> int:
        """Convert HH:MM time string to minutes since midnight."""
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    def _minutes_to_time(self, minutes: int) -> str:
        """Convert minutes since midnight to HH:MM time string."""
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"

    def _time_diff_minutes(self, start_time: str, end_time: str) -> int:
        """Calculate difference between two times in minutes."""
        return self._time_to_minutes(end_time) - self._time_to_minutes(start_time)


# Singleton instance
_schedule_service: ScheduleService | None = None


def get_schedule_service() -> ScheduleService:
    """Get or create the schedule service singleton."""
    global _schedule_service
    if _schedule_service is None:
        _schedule_service = ScheduleService()
    return _schedule_service
