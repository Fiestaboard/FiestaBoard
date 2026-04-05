"""Calendar Subscription plugin for FiestaBoard.

Fetches a public iCalendar (.ics) URL and displays upcoming events.
Supports both normal template variables and event-based triggers that
interrupt the board display a configurable number of minutes before
each event starts.
"""

import hashlib
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytz
import recurring_ical_events
import requests
from icalendar import Calendar

from src.plugins.base import PluginBase, PluginResult, TriggerResult

logger = logging.getLogger(__name__)

# How far ahead to scan for upcoming events when building template variables
_LOOK_AHEAD_DAYS = 30

# Duration used when display_duration_minutes is 0 ("stay until overwritten")
_INDEFINITE_DURATION_SECONDS = 86400


def _normalize_url(url: str) -> str:
    """Rewrite webcal:// to https:// for HTTP transport."""
    if url.startswith("webcal://"):
        return "https://" + url[len("webcal://"):]
    if url.startswith("webcal:"):
        return "https:" + url[len("webcal:"):]
    return url


def _dt_to_aware(dt: Any, tz: Any) -> datetime:
    """Convert a date or datetime to a timezone-aware datetime.

    All-day events come back as ``date`` objects; we treat them as
    midnight in the configured timezone.
    """
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return tz.localize(dt)
        return dt.astimezone(tz)
    # Plain date (all-day event) — treat as midnight local time
    return tz.localize(datetime(dt.year, dt.month, dt.day, 0, 0, 0))


def _format_time(dt: datetime) -> str:
    """Return a short human-readable time string, e.g. '3:30 PM'."""
    return dt.strftime("%-I:%M %p").lstrip("0") if dt.hour != 0 or dt.minute != 0 else "All Day"


def _format_date(dt: datetime) -> str:
    """Return a short human-readable date string, e.g. 'Apr 3'."""
    return dt.strftime("%b %-d")


def _event_trigger_id(event: Dict[str, Any]) -> str:
    """Build a stable dedup key from the event UID and start time."""
    uid = str(event.get("uid", ""))
    start = str(event.get("start_raw", ""))
    return "cal_" + hashlib.md5(f"{uid}:{start}".encode(), usedforsecurity=False).hexdigest()[:12]


class CalendarSubPlugin(PluginBase):
    """Calendar Subscription plugin.

    Fetches events from a public .ics URL, exposes them as template
    variables, and fires board triggers before each event.
    """

    def __init__(self, manifest: Dict[str, Any]):
        super().__init__(manifest)
        self._events_cache: List[Dict[str, Any]] = []

    @property
    def plugin_id(self) -> str:
        return "calendar_sub"

    # ------------------------------------------------------------------
    # Config validation
    # ------------------------------------------------------------------

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors = []

        url = config.get("calendar_url") or os.getenv("CALENDAR_SUB_URL", "")
        if not url:
            errors.append("Calendar URL is required")
        else:
            normalized = _normalize_url(url)
            if not (normalized.startswith("http://") or normalized.startswith("https://")):
                errors.append("Calendar URL must be an http:// or https:// (or webcal://) URL")

        timezone_str = config.get("timezone", "America/Los_Angeles")
        try:
            pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            errors.append(f"Invalid timezone: {timezone_str}")

        errors.extend(self._validate_refresh_seconds(config))
        return errors

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def fetch_data(self) -> PluginResult:
        """Fetch calendar and return upcoming events as template variables."""
        try:
            events = self._fetch_events()
        except Exception as e:
            logger.error("Error fetching calendar data: %s", e, exc_info=True)
            return PluginResult(available=False, error=str(e))

        self._events_cache = events

        if not events:
            data = self._empty_data()
            return PluginResult(
                available=True,
                data=data,
                formatted_lines=self._format_display(data),
            )

        next_event = events[0]
        data = self._build_data(next_event, events)
        return PluginResult(
            available=True,
            data=data,
            formatted_lines=self._format_display(data),
        )

    # ------------------------------------------------------------------
    # Trigger support
    # ------------------------------------------------------------------

    def check_triggers(self) -> List[TriggerResult]:
        """Fire triggers for events starting within the configured window."""
        results: List[TriggerResult] = []

        # Use cached events if available to avoid extra HTTP calls
        if not self._events_cache:
            try:
                self._events_cache = self._fetch_events()
            except Exception:
                logger.warning("Could not fetch events for trigger check", exc_info=True)
                return results

        minutes_before = int(self.config.get("minutes_before", 15))
        display_minutes = int(self.config.get("display_duration_minutes", 0))
        duration_seconds = (
            display_minutes * 60 if display_minutes > 0 else _INDEFINITE_DURATION_SECONDS
        )

        tz_str = self.config.get("timezone", "America/Los_Angeles")
        tz = pytz.timezone(tz_str)
        now = datetime.now(tz)

        for event in self._events_cache:
            start = event["start_dt"]
            end = event["end_dt"]

            minutes_until = (start - now).total_seconds() / 60
            is_now = start <= now <= end

            if is_now:
                results.append(TriggerResult(
                    triggered=True,
                    trigger_id=_event_trigger_id(event) + "_now",
                    formatted_lines=self._format_trigger_display(event, now, is_now=True),
                    priority=5,
                    duration_seconds=duration_seconds,
                    data=self._build_data(event, self._events_cache),
                ))
            elif 0 <= minutes_until <= minutes_before:
                results.append(TriggerResult(
                    triggered=True,
                    trigger_id=_event_trigger_id(event),
                    formatted_lines=self._format_trigger_display(event, now, is_now=False),
                    priority=5,
                    duration_seconds=duration_seconds,
                    data=self._build_data(event, self._events_cache),
                ))

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_events(self) -> List[Dict[str, Any]]:
        """Fetch and parse the .ics URL, returning sorted event dicts."""
        url = self.config.get("calendar_url") or os.getenv("CALENDAR_SUB_URL", "")
        if not url:
            raise ValueError("Calendar URL not configured")

        url = _normalize_url(url)
        tz_str = self.config.get("timezone", "America/Los_Angeles")
        tz = pytz.timezone(tz_str)
        max_events = int(self.config.get("max_events", 5))

        response = requests.get(url, timeout=15)
        response.raise_for_status()

        cal = Calendar.from_ical(response.content)

        now = datetime.now(tz)
        look_ahead = now + timedelta(days=_LOOK_AHEAD_DAYS)

        raw_events = recurring_ical_events.of(cal).between(now, look_ahead)

        events = []
        for component in raw_events:
            try:
                events.append(self._parse_component(component, tz))
            except Exception:
                logger.debug("Skipping malformed event component", exc_info=True)

        events.sort(key=lambda e: e["start_dt"])
        return events[:max_events]

    def _parse_component(self, component: Any, tz: Any) -> Dict[str, Any]:
        """Extract a normalized event dict from a VEVENT component."""
        summary = str(component.get("SUMMARY", "Untitled Event"))
        uid = str(component.get("UID", ""))
        location = str(component.get("LOCATION", ""))
        description = str(component.get("DESCRIPTION", ""))

        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND") or component.get("DUE")

        start_raw = dtstart.dt if dtstart else datetime.now(tz)
        end_raw = dtend.dt if dtend else start_raw

        start_dt = _dt_to_aware(start_raw, tz)
        end_dt = _dt_to_aware(end_raw, tz)

        return {
            "uid": uid,
            "name": summary,
            "location": location,
            "description": description[:22],
            "start_dt": start_dt,
            "end_dt": end_dt,
            "start_raw": str(start_raw),
            "start": _format_time(start_dt),
            "start_date": _format_date(start_dt),
            "end": _format_time(end_dt),
        }

    def _build_data(
        self, next_event: Dict[str, Any], events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build the template variable dict from the next event and event list."""
        tz_str = self.config.get("timezone", "America/Los_Angeles")
        tz = pytz.timezone(tz_str)
        now = datetime.now(tz)

        start = next_event["start_dt"]
        end = next_event["end_dt"]
        minutes_until = int((start - now).total_seconds() / 60)
        is_now = start <= now <= end

        return {
            "event_name": next_event["name"][:22],
            "event_start": next_event["start"],
            "event_start_date": next_event["start_date"],
            "event_end": next_event["end"],
            "event_location": next_event["location"][:22],
            "event_description": next_event["description"],
            "minutes_until": str(minutes_until),
            "is_now": "true" if is_now else "false",
            "event_count": str(len(events)),
            "events": [
                {
                    "name": e["name"][:22],
                    "start": e["start"],
                    "start_date": e["start_date"],
                    "end": e["end"],
                    "location": e["location"][:22],
                }
                for e in events
            ],
        }

    def _empty_data(self) -> Dict[str, Any]:
        """Return a data dict when no upcoming events are found."""
        return {
            "event_name": "",
            "event_start": "",
            "event_start_date": "",
            "event_end": "",
            "event_location": "",
            "event_description": "",
            "minutes_until": "",
            "is_now": "false",
            "event_count": "0",
            "events": [],
        }

    def _format_display(self, data: Dict[str, Any]) -> List[str]:
        """Format template data into 6 board lines (22 chars max each)."""
        if data.get("event_count") == "0" or not data.get("event_name"):
            lines = [
                "CALENDAR".center(22),
                "",
                "NO UPCOMING EVENTS".center(22),
                "",
                "",
                "",
            ]
        else:
            name = data["event_name"].upper()
            date_str = data["event_start_date"].upper()
            time_str = data["event_start"].upper()
            location = data["event_location"].upper()
            minutes = data.get("minutes_until", "")

            date_time = f"{date_str}  {time_str}".strip()

            try:
                mins = int(minutes)
                if mins <= 0:
                    timing = "NOW"
                elif mins < 60:
                    timing = f"IN {mins} MIN"
                else:
                    hours = mins // 60
                    timing = f"IN {hours} HR"
            except (ValueError, TypeError):
                timing = ""

            lines = [
                "UPCOMING EVENT".center(22),
                name[:22].center(22),
                "",
                date_time[:22].center(22),
                location[:22].center(22) if location else "",
                timing.center(22) if timing else "",
            ]

        return lines[:6]

    def _format_trigger_display(
        self, event: Dict[str, Any], now: datetime, is_now: bool
    ) -> List[str]:
        """Format a 6-line board display for a trigger notification."""
        name = event["name"].upper()
        date_str = event["start_date"].upper()
        time_str = event["start"].upper()
        location = event["location"].upper()

        date_time = f"{date_str}  {time_str}".strip()

        if is_now:
            header = "EVENT STARTING NOW".center(22)
            timing = "HAPPENING NOW".center(22)
        else:
            header = "UPCOMING EVENT".center(22)
            start = event["start_dt"]
            minutes_until = int((start - now).total_seconds() / 60)
            if minutes_until < 60:
                timing = f"IN {minutes_until} MINUTES".center(22)
            else:
                hours = minutes_until // 60
                timing = f"IN {hours} HOURS".center(22)

        lines = [
            header,
            name[:22].center(22),
            "",
            date_time[:22].center(22),
            location[:22].center(22) if location else "",
            timing,
        ]
        return lines[:6]


# Export the plugin class
Plugin = CalendarSubPlugin
