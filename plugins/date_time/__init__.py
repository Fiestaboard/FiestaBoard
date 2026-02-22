"""Date & Time plugin for FiestaBoard.

Displays current date and time in various formats.
"""

from typing import Any, Dict, List, Optional
import logging
from datetime import datetime
import pytz

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class DateTimePlugin(PluginBase):
    """Date and time data plugin.
    
    Provides current date/time information in the configured timezone.
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the datetime plugin."""
        super().__init__(manifest)
    
    @property
    def plugin_id(self) -> str:
        """Return plugin identifier."""
        return "date_time"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate datetime configuration."""
        errors = []
        
        timezone = config.get("timezone", "America/Los_Angeles")
        try:
            pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            errors.append(f"Invalid timezone: {timezone}")
        
        return errors
    
    def fetch_data(self) -> PluginResult:
        """Fetch current date and time data."""
        try:
            timezone_str = self.config.get("timezone", "America/Los_Angeles")
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)
            
            data = {
                # Existing variables (backward compatible)
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M"),
                "datetime": now.strftime("%Y-%m-%d %H:%M"),
                "day_of_week": now.strftime("%A"),
                "timezone_abbr": now.strftime("%Z"),
                "day": str(now.day),
                "month": now.strftime("%B"),
                "year": str(now.year),
                "hour": str(now.hour),
                "minute": str(now.minute).zfill(2),
                
                # New time formats
                "time_12h": now.strftime("%I:%M %p").lstrip("0"),  # 12-hour format without leading zero from hour, e.g., "2:30 PM"
                "time_24h": now.strftime("%H:%M"),  # Same as "time" but explicit
                
                # New date formats (US format)
                "date_us": now.strftime("%m/%d/%Y"),  # MM/DD/YYYY
                "date_us_short": now.strftime("%m/%d/%y"),  # MM/DD/YY
                
                # New month formats
                "month_number": str(now.month),  # 1-12 (unpadded)
                "month_number_padded": now.strftime("%m"),  # 01-12 (zero-padded)
                "month_abbr": now.strftime("%b"),  # 3-letter abbreviation (Jan, Feb, etc.)
                
                # Additional timezone info
                "timezone": timezone_str,  # Full timezone name from config
            }
            
            return PluginResult(
                available=True,
                data=data
            )
            
        except Exception as e:
            logger.exception("Error fetching datetime data")
            return PluginResult(
                available=False,
                error=str(e)
            )
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted datetime display."""
        result = self.fetch_data()
        if not result.available or not result.data:
            return None
        
        data = result.data
        lines = [
            "",
            data["day_of_week"].upper().center(22),
            data["date"].center(22),
            data["time"].center(22),
            "",
            "",
        ]
        
        return lines


# Export the plugin class
Plugin = DateTimePlugin

