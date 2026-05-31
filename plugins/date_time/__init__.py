"""Date & Time plugin for FiestaBoard.

Displays current date and time in various formats.
"""

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

_HOUR_WORDS = {
    1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE", 6: "SIX",
    7: "SEVEN", 8: "EIGHT", 9: "NINE", 10: "TEN", 11: "ELEVEN", 12: "TWELVE",
}

_ONES = [
    "", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT",
    "NINE", "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN",
    "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN",
]
_TENS = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY"]


def _minute_word(n: int) -> str:
    """Convert a minute count (1–29) to English words, with A QUARTER for 15."""
    if n == 15:
        return "A QUARTER"
    if n < 20:
        return _ONES[n]
    tens = _TENS[n // 10]
    ones = _ONES[n % 10]
    return f"{tens}-{ones}" if ones else tens


def _time_to_english(hour: int, minute: int) -> str:
    """Convert hour (0–23) and minute (0–59) to a spoken English expression."""
    if hour == 0 and minute == 0:
        return "IT'S MIDNIGHT."
    if hour == 12 and minute == 0:
        return "IT'S NOON."

    if 5 <= hour <= 11:
        period = "IN THE MORNING"
    elif 12 <= hour <= 17:
        period = "IN THE AFTERNOON"
    elif 18 <= hour <= 20:
        period = "IN THE EVENING"
    else:
        period = "AT NIGHT"

    h12 = hour % 12 or 12

    if minute == 0:
        return f"IT'S {_HOUR_WORDS[h12]} O'CLOCK {period}."
    elif minute == 30:
        return f"IT'S HALF PAST {_HOUR_WORDS[h12]} {period}."
    elif minute < 30:
        return f"IT'S {_minute_word(minute)} PAST {_HOUR_WORDS[h12]} {period}."
    else:
        minutes_to = 60 - minute
        next_h12 = h12 % 12 + 1
        return f"IT'S {_minute_word(minutes_to)} TO {_HOUR_WORDS[next_h12]} {period}."


class DateTimePlugin(PluginBase):
    """Date and time data plugin.

    Provides current date/time information in the configured timezone.
    """

    def __init__(self, manifest: dict[str, Any]):
        """Initialize the datetime plugin."""
        super().__init__(manifest)

    @property
    def plugin_id(self) -> str:
        return "date_time"

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """Validate datetime configuration."""
        errors = []

        timezone = config.get("timezone", "America/Los_Angeles")
        if not isinstance(timezone, str) or not timezone.strip():
            errors.append(f"Invalid timezone: {timezone!r}")
            return errors
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError, AttributeError, KeyError):
            errors.append(f"Invalid timezone: {timezone}")

        return errors

    def fetch_data(self) -> PluginResult:
        """Fetch current date and time data."""
        try:
            timezone_str = self.config.get("timezone")
            if not timezone_str:
                from src.config import Config
                timezone_str = Config.GENERAL_TIMEZONE or "America/Los_Angeles"
            tz = ZoneInfo(timezone_str)
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

                # Spoken English time expression
                "time_english": _time_to_english(now.hour, now.minute),
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

    def get_formatted_display(self) -> list[str] | None:
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

