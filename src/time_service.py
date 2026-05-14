"""Centralized time and timezone handling service.

This service provides a single source of truth for all time-related operations
in the application, including:
- Current time in any timezone
- Timezone conversions
- Silence mode time window checking
- Timestamp generation and formatting for logs

All time-sensitive code should use this service instead of directly using
datetime or zoneinfo to ensure consistency and testability.
"""

import logging
from datetime import datetime, timezone as _dt_timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# Public UTC singleton used throughout the service. Using datetime.timezone.utc
# (rather than ZoneInfo("UTC")) keeps equality checks simple and avoids the
# need for tzdata on any target platform.
UTC = _dt_timezone.utc


def _resolve_timezone(name: str):
    """Resolve an IANA timezone name to a ZoneInfo, falling back to UTC.

    Returns a tuple ``(tzinfo, ok)`` where ``ok`` is ``False`` when the name
    could not be resolved (the caller can decide how to log/respond).
    """
    try:
        return ZoneInfo(name), True
    except (ZoneInfoNotFoundError, ValueError):
        return UTC, False


class TimeService:
    """Centralized time and timezone handling for the entire application."""
    
    def __init__(self, default_timezone: str = "America/Los_Angeles"):
        """Initialize the time service.
        
        Args:
            default_timezone: Default IANA timezone name (e.g., "America/Los_Angeles")
        """
        self.default_timezone = default_timezone
        tz, ok = _resolve_timezone(default_timezone)
        if not ok:
            logger.warning(f"Unknown default timezone: {default_timezone}, using UTC")
        self._default_tz = tz
    
    # Core time operations
    
    def get_current_utc(self) -> datetime:
        """Get current UTC time.
        
        Returns:
            Current datetime in UTC timezone
        """
        return datetime.now(UTC)
    
    def get_current_time(self, timezone: Optional[str] = None) -> datetime:
        """Get current time in specified timezone.
        
        Args:
            timezone: IANA timezone name. If None, uses default timezone.
            
        Returns:
            Current datetime in the specified timezone
        """
        if timezone is None:
            tz = self._default_tz
        else:
            tz, ok = _resolve_timezone(timezone)
            if not ok:
                logger.warning(f"Unknown timezone: {timezone}, using default")
                tz = self._default_tz
        
        return datetime.now(tz)
    
    # Silence mode support
    
    def parse_iso_time(self, time_str: str) -> Optional[datetime]:
        """Parse ISO time string to datetime object.
        
        Handles formats like:
        - "20:00-08:00" (8pm PST)
        - "03:00+00:00" (3am UTC)
        - "14:30-05:00" (2:30pm EST)
        
        Args:
            time_str: ISO 8601 time string with timezone offset
            
        Returns:
            datetime object in UTC, or None if parsing fails
        """
        try:
            # Parse as time today in UTC with offset
            # Format: HH:MM+/-HH:MM
            if len(time_str) < 11:
                logger.warning(f"Invalid ISO time format: {time_str}")
                return None
            
            time_part = time_str[:5]  # HH:MM
            offset_part = time_str[5:]  # +/-HH:MM
            
            # Parse time
            hour, minute = map(int, time_part.split(':'))
            
            # Parse offset
            offset_sign = 1 if offset_part[0] == '+' else -1
            offset_hours, offset_minutes = map(int, offset_part[1:].split(':'))
            offset_total_minutes = offset_sign * (offset_hours * 60 + offset_minutes)
            
            # Create a datetime for today at this time in the specified timezone
            now_utc = self.get_current_utc()
            # Create naive datetime for the time
            naive_dt = datetime(now_utc.year, now_utc.month, now_utc.day, hour, minute)
            
            # Apply offset to convert to UTC
            # If time is 20:00-08:00 (PST), that's 20:00 in a timezone 8 hours behind UTC
            # So UTC time is 20:00 + 8:00 = 04:00 next day (but we handle date separately)
            from datetime import timedelta
            utc_dt = naive_dt - timedelta(minutes=offset_total_minutes)
            
            # Make it timezone aware (UTC)
            utc_dt = utc_dt.replace(tzinfo=UTC)
            
            return utc_dt
            
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse ISO time '{time_str}': {e}")
            return None
    
    def is_time_in_window(self, start_iso: str, end_iso: str) -> bool:
        """Check if current UTC time is within the specified time window.
        
        Handles windows that span midnight (e.g., 22:00 to 07:00).
        
        Args:
            start_iso: Start time in ISO format (e.g., "20:00-08:00")
            end_iso: End time in ISO format (e.g., "07:00-08:00")
            
        Returns:
            True if current UTC time is within the window
        """
        start_dt = self.parse_iso_time(start_iso)
        end_dt = self.parse_iso_time(end_iso)
        
        if start_dt is None or end_dt is None:
            logger.warning("Invalid time format in window check")
            return False
        
        current_utc = self.get_current_utc()
        current_time = current_utc.time()
        start_time = start_dt.time()
        end_time = end_dt.time()
        
        # Handle midnight-spanning window
        if start_time > end_time:
            # Window spans midnight: current must be >= start OR <= end
            return current_time >= start_time or current_time <= end_time
        else:
            # Same-day window: current must be >= start AND <= end
            return start_time <= current_time <= end_time
    
    # Timezone conversions
    
    def local_to_utc_iso(self, local_time: str, timezone: str) -> str:
        """Convert local time to UTC ISO format.
        
        Args:
            local_time: Time in HH:MM format (e.g., "20:00")
            timezone: IANA timezone name (e.g., "America/Los_Angeles")
            
        Returns:
            ISO time string in UTC (e.g., "04:00+00:00")
        """
        if not local_time or not timezone:
            logger.error("local_time and timezone are required")
            return "00:00+00:00"
        
        tz, ok = _resolve_timezone(timezone)
        if not ok:
            logger.warning(f"Unknown timezone: {timezone}, using UTC")
        
        try:
            # Parse local time
            if ':' not in local_time:
                raise ValueError(f"Invalid time format: {local_time}")
            
            parts = local_time.split(':')
            if len(parts) != 2:
                raise ValueError(f"Invalid time format: {local_time}")
            
            hour, minute = map(int, parts)
            
            # Validate hour and minute ranges
            if not (0 <= hour <= 23):
                raise ValueError(f"Hour must be 0-23, got {hour}")
            if not (0 <= minute <= 59):
                raise ValueError(f"Minute must be 0-59, got {minute}")
            
            # Create datetime for today at this time in the specified timezone
            now_utc = self.get_current_utc()
            # Attach timezone directly; zoneinfo handles DST via fold semantics
            local_dt = datetime(now_utc.year, now_utc.month, now_utc.day, hour, minute, tzinfo=tz)

            # Convert to UTC
            utc_dt = local_dt.astimezone(UTC)
            
            # Format as ISO time string
            return utc_dt.strftime("%H:%M+00:00")
            
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to convert local time '{local_time}' in {timezone}: {e}")
            return "00:00+00:00"
    
    def utc_iso_to_local(self, utc_iso: str, timezone: str) -> str:
        """Convert UTC ISO time to local time.
        
        Args:
            utc_iso: ISO time string in UTC (e.g., "04:00+00:00")
            timezone: IANA timezone name (e.g., "America/Los_Angeles")
            
        Returns:
            Local time in HH:MM format (e.g., "20:00")
        """
        if not utc_iso or not timezone:
            logger.error("utc_iso and timezone are required")
            return "00:00"
        
        tz, ok = _resolve_timezone(timezone)
        if not ok:
            logger.warning(f"Unknown timezone: {timezone}, using UTC")
        
        utc_dt = self.parse_iso_time(utc_iso)
        if utc_dt is None:
            logger.error(f"Failed to parse UTC ISO time: {utc_iso}")
            return "00:00"
        
        try:
            # Convert to target timezone
            local_dt = utc_dt.astimezone(tz)
            return local_dt.strftime("%H:%M")
        except Exception as e:
            logger.error(f"Failed to convert UTC to local time: {e}")
            return "00:00"
    
    # Timestamp handling (for logs)
    
    def create_utc_timestamp(self) -> str:
        """Create current UTC timestamp in ISO format.
        
        Returns:
            ISO 8601 timestamp with explicit UTC marker (e.g., "2025-12-26T22:30:00+00:00")
        """
        utc_now = self.get_current_utc()
        return utc_now.isoformat()
    
    def format_timestamp_local(self, utc_timestamp: str, timezone: str) -> str:
        """Format UTC timestamp for display in specified timezone.
        
        Args:
            utc_timestamp: ISO 8601 timestamp in UTC
            timezone: IANA timezone name for display
            
        Returns:
            Formatted timestamp string in local timezone
        """
        try:
            # Parse UTC timestamp
            utc_dt = datetime.fromisoformat(utc_timestamp.replace('Z', '+00:00'))
            
            # Ensure it's UTC-aware
            if utc_dt.tzinfo is None:
                utc_dt = utc_dt.replace(tzinfo=UTC)
            
            # Convert to target timezone
            tz, ok = _resolve_timezone(timezone)
            if not ok:
                logger.warning(f"Unknown timezone: {timezone}, using UTC")
            
            local_dt = utc_dt.astimezone(tz)
            
            return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
            
        except (ValueError, AttributeError) as e:
            logger.error(f"Failed to format timestamp '{utc_timestamp}': {e}")
            return utc_timestamp


# Singleton instance
_time_service: Optional[TimeService] = None


def _get_configured_timezone() -> str:
    """Read the user-configured timezone from Config, with a safe fallback.

    This is separated from get_time_service() so it can be patched in tests
    without importing Config at module level (which would create circular imports
    in some test setups).
    """
    try:
        from .config import Config
        return Config.GENERAL_TIMEZONE
    except Exception:
        return "UTC"


def get_time_service() -> TimeService:
    """Get or create the time service singleton.
    
    Uses the user-configured timezone from Config.GENERAL_TIMEZONE
    instead of hardcoding a default.
    
    Returns:
        The global TimeService instance
    """
    global _time_service
    if _time_service is None:
        tz = _get_configured_timezone()
        _time_service = TimeService(default_timezone=tz)
    return _time_service


def reset_time_service():
    """Reset the time service singleton (primarily for testing)."""
    global _time_service
    _time_service = None
