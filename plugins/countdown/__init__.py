"""Countdown plugin for FiestaBoard.

Displays the remaining time to an event timestamp in real time.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class CountdownPlugin(PluginBase):
    """Countdown timer plugin.

    Provides remaining days, hours, minutes, and seconds until a
    configured target date/time.
    """

    def __init__(self, manifest: dict[str, Any]):
        """Initialize the countdown plugin."""
        super().__init__(manifest)

    @property
    def plugin_id(self) -> str:
        return "countdown"

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """Validate countdown configuration."""
        errors = []

        timezone = config.get("timezone", "America/Los_Angeles")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            errors.append(f"Invalid timezone: {timezone}")

        target = config.get("target_datetime") or os.getenv("COUNTDOWN_TARGET")
        if not target:
            errors.append("Target date/time is required")
        else:
            try:
                datetime.fromisoformat(target)
            except (ValueError, TypeError):
                errors.append(f"Invalid target datetime format: {target}. Use ISO format (e.g., 2025-06-15T00:00:00)")

        return errors

    def fetch_data(self) -> PluginResult:
        """Fetch countdown data."""
        try:
            timezone_str = self.config.get("timezone", "America/Los_Angeles")
            tz = ZoneInfo(timezone_str)
            now = datetime.now(tz)

            target_str = self.config.get("target_datetime") or os.getenv("COUNTDOWN_TARGET")
            if not target_str:
                return PluginResult(
                    available=False,
                    error="Target date/time not configured",
                )

            try:
                target_naive = datetime.fromisoformat(target_str)
            except (ValueError, TypeError):
                return PluginResult(
                    available=False,
                    error=f"Invalid target datetime: {target_str}",
                )

            # Attach timezone info if the target is naive (zoneinfo uses replace).
            if target_naive.tzinfo is None:
                target = target_naive.replace(tzinfo=tz)
            else:
                target = target_naive

            event_name = self.config.get("event_name") or os.getenv("COUNTDOWN_EVENT_NAME") or "Event"

            # Convert both sides to UTC before subtracting. When two aware
            # datetimes share the same tzinfo, Python returns the wall-clock
            # delta and silently drops DST transitions — so a "1 day" target
            # straddling spring-forward would report 24h instead of 23h (#926).
            delta = target.astimezone(timezone.utc) - now.astimezone(timezone.utc)
            total_seconds = int(delta.total_seconds())

            if total_seconds <= 0:
                data = {
                    "event_name": event_name,
                    "target_datetime": target_str,
                    "days": "0",
                    "hours": "0",
                    "minutes": "0",
                    "seconds": "0",
                    "total_seconds": "0",
                    "is_expired": "true",
                    "formatted": "Event has passed",
                }
            else:
                days = total_seconds // 86400
                hours = (total_seconds % 86400) // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60

                data = {
                    "event_name": event_name,
                    "target_datetime": target_str,
                    "days": str(days),
                    "hours": str(hours),
                    "minutes": str(minutes),
                    "seconds": str(seconds),
                    "total_seconds": str(total_seconds),
                    "is_expired": "false",
                    "formatted": f"{days}D {hours}H {minutes}M",
                }

            return PluginResult(
                available=True,
                data=data,
                formatted_lines=self._format_display(data),
            )

        except Exception as e:
            logger.exception("Error fetching countdown data")
            return PluginResult(
                available=False,
                error=str(e),
            )

    def get_formatted_display(self) -> list[str] | None:
        """Return default formatted countdown display."""
        result = self.fetch_data()
        if not result.available or not result.data:
            return None
        return self._format_display(result.data)

    def _format_display(self, data: dict[str, Any]) -> list[str]:
        """Format countdown data for the 6-line board display."""
        event_name = data.get("event_name", "Event")
        is_expired = data.get("is_expired") == "true"

        if is_expired:
            lines = [
                "COUNTDOWN",
                event_name[:22].upper().center(22),
                "",
                "EVENT HAS PASSED".center(22),
                "",
                "",
            ]
        else:
            days = data.get("days", "0")
            hours = data.get("hours", "0")
            minutes = data.get("minutes", "0")

            lines = [
                "COUNTDOWN UNTIL".center(22),
                event_name[:22].upper().center(22),
                "",
                f"{days} DAYS".center(22),
                f"{hours} HOURS".center(22),
                f"{minutes} MINUTES".center(22),
            ]

        return lines


# Export the plugin class
Plugin = CountdownPlugin
