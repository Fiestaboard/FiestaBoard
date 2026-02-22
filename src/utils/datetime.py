"""Date and time data source."""

import logging
from typing import Dict
from ..config import Config
from ..time_service import get_time_service

logger = logging.getLogger(__name__)


class DateTimeSource:
    """Provides current date and time information using TimeService."""
    
    def __init__(self, timezone: str = "America/Los_Angeles"):
        """
        Initialize datetime source.
        
        Args:
            timezone: Timezone name (e.g., "America/Los_Angeles")
        """
        self.timezone = timezone
        self.time_service = get_time_service()
    
    def get_current_datetime(self) -> Dict[str, str]:
        """
        Get current date and time information.
        
        Returns:
            Dictionary with formatted date and time strings
        """
        # Use TimeService to get current time in configured timezone
        now = self.time_service.get_current_time(self.timezone)
        
        return {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "datetime": now.strftime("%Y-%m-%d %H:%M"),
            "day_of_week": now.strftime("%A"),
            "timezone_abbr": now.strftime("%Z"),
            # Individual date components
            "day": str(now.day),  # Day of month (1-31)
            "month": now.strftime("%B"),  # Full month name (January, February, etc.)
            "year": str(now.year),  # Year (2025, etc.)
            "hour": str(now.hour),  # Hour (0-23)
            "minute": str(now.minute),  # Minute (0-59)
        }
    
    def format_for_display(self, format_string: str = "%Y-%m-%d %H:%M %Z") -> str:
        """
        Format current datetime for display.
        
        Args:
            format_string: strftime format string
            
        Returns:
            Formatted datetime string
        """
        now = self.time_service.get_current_time(self.timezone)
        return now.strftime(format_string)


def get_datetime_source() -> DateTimeSource:
    """Get configured datetime source instance."""
    return DateTimeSource(timezone=Config.TIMEZONE)
