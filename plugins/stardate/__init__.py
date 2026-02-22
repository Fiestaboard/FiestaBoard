"""Stardate plugin for FiestaBoard.

Displays the current TNG-style stardate.
"""

from typing import Any, Dict, List, Optional
import logging
from datetime import datetime
import calendar
import pytz

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class StardatePlugin(PluginBase):
    """Stardate plugin.

    Provides the current TNG-era stardate.
    """

    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the stardate plugin."""
        super().__init__(manifest)

    @property
    def plugin_id(self) -> str:
        """Return plugin identifier."""
        return "stardate"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate stardate configuration."""
        errors = []

        timezone = config.get("timezone", "America/Los_Angeles")
        try:
            pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            errors.append(f"Invalid timezone: {timezone}")

        return errors

    def fetch_data(self) -> PluginResult:
        """Fetch current stardate."""
        try:
            timezone_str = self.config.get("timezone", "America/Los_Angeles")
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)

            days_in_year = 366 if calendar.isleap(now.year) else 365
            stardate = f"{70000 + (now.year - 2020) * 1000 + (now.timetuple().tm_yday / days_in_year * 1000):.1f}"

            return PluginResult(
                available=True,
                data={"stardate": stardate}
            )

        except Exception as e:
            logger.exception("Error fetching stardate")
            return PluginResult(
                available=False,
                error=str(e)
            )

    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted stardate display."""
        result = self.fetch_data()
        if not result.available or not result.data:
            return None

        lines = [
            "",
            "STARDATE".center(22),
            result.data["stardate"].center(22),
            "",
            "",
            "",
        ]

        return lines


# Export the plugin class
Plugin = StardatePlugin
