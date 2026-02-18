"""Spacecraft Launches plugin for FiestaBoard.

Displays upcoming spacecraft launch countdowns and statuses using
the Launch Library 2 API from The Space Devs.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import logging
import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# Launch Library 2 API
LL2_BASE_URL = "https://ll.thespacedevs.com/2.3.0"
LL2_LAUNCHES_URL = f"{LL2_BASE_URL}/launches/upcoming/"


class SpacecraftLaunchesPlugin(PluginBase):
    """Spacecraft launches tracker plugin.

    Fetches upcoming launch data from the Launch Library 2 API and displays
    launch name, status, countdown, pad, and provider information.
    """

    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the spacecraft launches plugin."""
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None

    @property
    def plugin_id(self) -> str:
        """Return plugin identifier."""
        return "spacecraft_launches"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate spacecraft launches configuration."""
        errors = []

        max_launches = config.get("max_launches", 4)
        if not isinstance(max_launches, int) or not (1 <= max_launches <= 10):
            errors.append("Max launches must be between 1 and 10")

        refresh_seconds = config.get("refresh_seconds", 300)
        if not isinstance(refresh_seconds, int) or refresh_seconds < 240:
            errors.append("Refresh interval must be at least 240 seconds")

        return errors

    @staticmethod
    def _compute_countdown(net_str: str) -> str:
        """Compute countdown string from a NET datetime string.

        Args:
            net_str: ISO 8601 datetime string for the launch NET.

        Returns:
            Human-readable countdown string (e.g., "2d 05:30:00").
        """
        try:
            net_dt = datetime.fromisoformat(net_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = net_dt - now

            if delta.total_seconds() <= 0:
                return "LAUNCHED"

            total_seconds = int(delta.total_seconds())
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60

            if days > 0:
                return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except (ValueError, TypeError):
            return "TBD"

    def _parse_launch(self, launch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single launch object from the API response.

        Args:
            launch: Launch dictionary from the API.

        Returns:
            Parsed launch data dictionary, or None if invalid.
        """
        try:
            name = launch.get("name", "Unknown")

            # Status
            status_obj = launch.get("status") or {}
            status_name = status_obj.get("name", "Unknown")
            status_abbrev = status_obj.get("abbrev", "UNK")

            # NET (No Earlier Than) datetime
            net_str = launch.get("net", "")
            net_date = ""
            net_time = ""
            if net_str:
                try:
                    net_dt = datetime.fromisoformat(net_str.replace("Z", "+00:00"))
                    net_date = net_dt.strftime("%m/%d")
                    net_time = net_dt.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass

            # Countdown
            countdown = self._compute_countdown(net_str) if net_str else "TBD"

            # Pad
            pad_obj = launch.get("pad") or {}
            pad_name = pad_obj.get("name", "")
            pad_location_obj = pad_obj.get("location") or {}
            pad_location = pad_location_obj.get("name", "")

            # Provider
            provider_obj = launch.get("launch_service_provider") or {}
            provider = provider_obj.get("name", "Unknown")

            # Rocket
            rocket_obj = launch.get("rocket") or {}
            rocket_config = rocket_obj.get("configuration") or {}
            rocket = rocket_config.get("name", "")
            if not rocket:
                # Fallback: extract rocket name from launch name (before " | ")
                if " | " in name:
                    rocket = name.split(" | ")[0].strip()

            # Mission
            mission_obj = launch.get("mission") or {}
            mission = mission_obj.get("name", "")
            if not mission:
                # Fallback: extract mission from launch name (after " | ")
                if " | " in name:
                    mission = name.split(" | ", 1)[1].strip()

            # Format display line
            formatted = self._format_launch_line(net_date, net_time, mission or name, pad_name)

            return {
                "name": name[:22],
                "status": status_name[:15],
                "status_abbrev": status_abbrev[:7],
                "net": net_str[:20] if net_str else "",
                "net_date": net_date,
                "net_time": net_time,
                "countdown": countdown,
                "pad": pad_name[:20],
                "pad_location": pad_location[:22],
                "provider": provider[:15],
                "rocket": rocket[:15],
                "mission": (mission or name)[:22],
                "formatted": formatted,
            }

        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing launch: {e}")
            return None

    @staticmethod
    def _format_launch_line(date: str, time: str, mission: str, pad: str) -> str:
        """Format launch data for display line.

        Format: MM/DD HH:MM MISSION
        Example: 03/15 14:30 CREW-12

        Args:
            date: Date string (MM/DD).
            time: Time string (HH:MM).
            mission: Mission name.
            pad: Pad name.

        Returns:
            Formatted string (max 22 chars).
        """
        prefix = f"{date} {time} " if date and time else ""
        remaining = 22 - len(prefix)
        mission_display = mission[:remaining] if remaining > 0 else ""
        formatted = f"{prefix}{mission_display}"
        return formatted[:22]

    def fetch_data(self) -> PluginResult:
        """Fetch upcoming spacecraft launch data from Launch Library 2 API."""
        max_launches = self.config.get("max_launches", 4)
        refresh_seconds = self.config.get("refresh_seconds", 300)

        # Check cache first
        if self._cache and self._cache.get("launches"):
            last_updated = self._cache.get("last_updated", "")
            if last_updated:
                try:
                    cache_time = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                    age_seconds = (datetime.now(timezone.utc) - cache_time).total_seconds()
                    if age_seconds < refresh_seconds:
                        logger.debug(f"Using cached data (age: {age_seconds:.0f}s < {refresh_seconds}s)")
                        return PluginResult(available=True, data=self._cache)
                except Exception:
                    pass

        try:
            params = {
                "limit": max_launches,
                "mode": "detailed",
            }

            response = requests.get(LL2_LAUNCHES_URL, params=params, timeout=15)

            # Handle rate limiting
            if response.status_code == 429:
                logger.warning("Launch Library 2 API rate limit exceeded, using cached data if available")
                if self._cache and self._cache.get("launches"):
                    return PluginResult(available=True, data=self._cache)
                return PluginResult(
                    available=False,
                    error="API rate limit exceeded (15 req/hr). Please wait."
                )

            if response.status_code != 200:
                logger.error(f"Launch Library 2 API error: {response.status_code}")
                if self._cache and self._cache.get("launches"):
                    return PluginResult(available=True, data=self._cache)
                return PluginResult(
                    available=False,
                    error=f"API error: {response.status_code}"
                )

            data = response.json()
            results = data.get("results", [])

            if not results:
                return PluginResult(
                    available=True,
                    data={
                        "launch_count": 0,
                        "launches": [],
                        "name": "",
                        "status": "No launches",
                        "net": "",
                        "countdown": "",
                        "pad": "",
                        "provider": "",
                        "rocket": "",
                        "mission": "",
                        "formatted": "NO UPCOMING LAUNCHES",
                        "headers": "DATE TIME MISSION",
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    }
                )

            # Parse launches
            launches = []
            for launch_data in results:
                parsed = self._parse_launch(launch_data)
                if parsed:
                    launches.append(parsed)

            launches = launches[:max_launches]

            if not launches:
                return PluginResult(
                    available=True,
                    data={
                        "launch_count": 0,
                        "launches": [],
                        "name": "",
                        "status": "No launches",
                        "net": "",
                        "countdown": "",
                        "pad": "",
                        "provider": "",
                        "rocket": "",
                        "mission": "",
                        "formatted": "NO UPCOMING LAUNCHES",
                        "headers": "DATE TIME MISSION",
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    }
                )

            # Primary launch (next upcoming)
            primary = launches[0]

            result_data = {
                # Primary launch fields
                "name": primary["name"],
                "status": primary["status"],
                "net": primary["net"],
                "countdown": primary["countdown"],
                "pad": primary["pad"],
                "provider": primary["provider"],
                "rocket": primary["rocket"],
                "mission": primary["mission"],
                "formatted": primary["formatted"],
                # Headers
                "headers": "DATE TIME MISSION",
                # Aggregate
                "launch_count": len(launches),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                # Array of all launches
                "launches": launches,
            }

            self._cache = result_data
            return PluginResult(available=True, data=result_data)

        except requests.exceptions.RequestException as e:
            logger.exception("Error fetching launch data")
            if self._cache and self._cache.get("launches"):
                return PluginResult(available=True, data=self._cache)
            return PluginResult(available=False, error=f"Network error: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error fetching launch data")
            if self._cache and self._cache.get("launches"):
                return PluginResult(available=True, data=self._cache)
            return PluginResult(available=False, error=str(e))

    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted launch display."""
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None

        data = self._cache
        if not data:
            return None

        launches = data.get("launches", [])
        lines = [
            "EARTH DEPARTURES".center(22),
            "DATE TIME MISSION",
        ]

        for launch in launches[:4]:
            lines.append(launch.get("formatted", "")[:22])

        while len(lines) < 6:
            lines.append("")

        return lines[:6]

    def cleanup(self) -> None:
        """Cleanup when plugin is disabled."""
        self._cache = None


# Export the plugin class
Plugin = SpacecraftLaunchesPlugin
