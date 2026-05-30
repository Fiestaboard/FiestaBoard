"""Sun time calculation service for sunrise/sunset-based schedules.

Uses the astral library to compute sunrise and sunset times for a given
location and date. Results are returned as HH:MM strings in the configured
timezone for direct use in schedule evaluation.
"""

import logging
from datetime import datetime, timedelta, date
from typing import Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from astral import LocationInfo
from astral.sun import sun

logger = logging.getLogger(__name__)


def get_effective_timezone() -> str:
    """Return the IANA timezone to use for sun-time resolution.

    Prefers the general (project-wide) timezone used by ``time_service`` so
    that "what time is it now" and "when is sunset" stay in the same frame.
    Falls back to the date_time plugin's timezone, then to UTC.

    Without this preference order, a user who configured only the general
    timezone (or whose date_time plugin TZ is a non-DST equivalent like
    ``MST``/``America/Phoenix``/``Etc/GMT+7``) sees sunset-based schedules
    fire ~1 hour early during DST because the sunset is computed without
    DST while "now" is computed with DST.
    """
    try:
        from ..config import Config
        return Config.GENERAL_TIMEZONE or Config.TIMEZONE or "UTC"
    except Exception:
        logger.debug("Could not read timezone from Config, using UTC", exc_info=True)
        return "UTC"


def get_today_in_timezone(timezone_str: str) -> date:
    """Return today's date in the given IANA timezone.

    Using the configured timezone (rather than the server's local date) avoids
    a one-day skew when the server clock runs in a different zone than the
    user's location.
    """
    try:
        tz = ZoneInfo(timezone_str)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()

# Sun event types that can be used in schedule start/end
SUN_EVENT_TYPES = ("sunrise", "sunset")


def get_sun_times(
    latitude: float,
    longitude: float,
    target_date: date,
    timezone_str: str = "UTC",
) -> Optional[dict]:
    """Compute sunrise and sunset times for a given location and date.

    Args:
        latitude: Location latitude (-90 to 90).
        longitude: Location longitude (-180 to 180).
        target_date: The date to compute sun times for.
        timezone_str: IANA timezone name (e.g. "America/Los_Angeles").

    Returns:
        Dictionary with "sunrise" and "sunset" as timezone-aware datetime
        objects, or None if calculation fails (e.g. polar day/night).
    """
    try:
        try:
            tz = ZoneInfo(timezone_str)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning(f"Unknown timezone '{timezone_str}', falling back to UTC")
            tz = ZoneInfo("UTC")
            timezone_str = "UTC"

        location = LocationInfo(
            name="Board",
            region="",
            timezone=timezone_str,
            latitude=latitude,
            longitude=longitude,
        )
        s = sun(location.observer, date=target_date, tzinfo=tz)
        return {
            "sunrise": s["sunrise"],
            "sunset": s["sunset"],
        }
    except Exception as e:
        logger.warning(f"Failed to compute sun times for {target_date}: {e}")
        return None


def resolve_sun_time(
    sun_event: str,
    offset_minutes: int,
    latitude: float,
    longitude: float,
    target_date: date,
    timezone_str: str = "UTC",
) -> Optional[str]:
    """Resolve a sun event + offset to an HH:MM time string.

    Args:
        sun_event: Either "sunrise" or "sunset".
        offset_minutes: Offset in minutes (positive = after, negative = before).
        latitude: Location latitude.
        longitude: Location longitude.
        target_date: The date to compute for.
        timezone_str: IANA timezone name.

    Returns:
        Time string in HH:MM format, or None if resolution fails.
    """
    if sun_event not in SUN_EVENT_TYPES:
        logger.warning(f"Unknown sun event type: {sun_event}")
        return None

    times = get_sun_times(latitude, longitude, target_date, timezone_str)
    if times is None:
        return None

    event_time = times[sun_event]
    adjusted = event_time + timedelta(minutes=offset_minutes)

    # Extract hours/minutes; if offset pushes past midnight, clamp to 00:00-23:59
    h = max(0, min(23, adjusted.hour))
    m = adjusted.minute
    # If the date changed (crossed midnight), clamp to boundary
    if adjusted.date() > event_time.date():
        h, m = 23, 59
    elif adjusted.date() < event_time.date():
        h, m = 0, 0
    return f"{h:02d}:{m:02d}"


def resolve_schedule_sun_times(
    start_type: str,
    start_sun_offset: int,
    start_time_fallback: str,
    end_type: str,
    end_sun_offset: int,
    end_time_fallback: Optional[str],
    latitude: Optional[float],
    longitude: Optional[float],
    target_date: date,
    timezone_str: str = "UTC",
) -> Tuple[str, Optional[str]]:
    """Resolve both start and end times for a schedule entry.

    For fixed-type times, returns the fallback value unchanged.
    For sun-based times, computes dynamically from location and date.
    Falls back to stored values when location is unavailable or computation fails.

    Args:
        start_type: "fixed", "sunrise", or "sunset".
        start_sun_offset: Offset minutes for start sun event.
        start_time_fallback: Stored HH:MM fallback for start time.
        end_type: "fixed", "sunrise", or "sunset".
        end_sun_offset: Offset minutes for end sun event.
        end_time_fallback: Stored HH:MM fallback for end time (or None).
        latitude: Location latitude (None if not configured).
        longitude: Location longitude (None if not configured).
        target_date: The date to compute sun times for.
        timezone_str: IANA timezone name.

    Returns:
        Tuple of (resolved_start_time, resolved_end_time) as HH:MM strings.
    """
    resolved_start = start_time_fallback
    resolved_end = end_time_fallback

    # Only attempt sun resolution if location is available
    if latitude is not None and longitude is not None:
        if start_type in SUN_EVENT_TYPES:
            computed = resolve_sun_time(
                start_type, start_sun_offset,
                latitude, longitude, target_date, timezone_str,
            )
            if computed is not None:
                resolved_start = computed
            else:
                logger.debug(
                    f"Sun time resolution failed for start ({start_type}), "
                    f"using fallback: {start_time_fallback}"
                )

        if end_type in SUN_EVENT_TYPES:
            computed = resolve_sun_time(
                end_type, end_sun_offset,
                latitude, longitude, target_date, timezone_str,
            )
            if computed is not None:
                resolved_end = computed
            else:
                logger.debug(
                    f"Sun time resolution failed for end ({end_type}), "
                    f"using fallback: {end_time_fallback}"
                )
    else:
        if start_type in SUN_EVENT_TYPES or end_type in SUN_EVENT_TYPES:
            logger.debug(
                "Location not configured; sun-based schedule times "
                "will use stored fallback values"
            )

    return resolved_start, resolved_end
