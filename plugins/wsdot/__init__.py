"""WSDOT plugin for FiestaBoard.

Integrates with Washington State Department of Transportation APIs.
Initial feature: Washington State Ferries (schedules, vessels, sailing space, alerts).
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# WSF REST API base URLs (HTTPS)
WSF_SCHEDULE_BASE = "https://www.wsdot.wa.gov/Ferries/API/Schedule/rest"
WSF_TERMINALS_BASE = "https://www.wsdot.wa.gov/Ferries/API/Terminals/rest"
WSF_VESSELS_BASE = "https://www.wsdot.wa.gov/Ferries/API/Vessels/rest"

# Request timeout seconds
REQUEST_TIMEOUT = 15

# Well-known WSF route IDs for display names (can be extended)
ROUTE_NAMES: Dict[int, str] = {
    1: "Seattle-Bainbridge",
    2: "Seattle-Bremerton",
    3: "Fauntleroy-Vashon-Southworth",
    4: "Point Defiance-Tahlequah",
    5: "Anacortes-San Juan",
    6: "Anacortes-Sidney BC",
    7: "Mukilteo-Clinton",
    8: "Port Townsend-Keystone",
    9: "Edmonds-Kingston",
}

# Header line describing formatted fields (Route, Time, Spots) for display above data
FORMATTED_HEADERS = "Route Time Spots"[:22]

# Short abbreviations for board display (≤22 chars per line). Max ~8 chars for route.
ROUTE_ABBREVS: Dict[int, str] = {
    1: "Sea-Bain",
    2: "Sea-Brem",
    3: "Fau-Vash",
    4: "PtDef-Tah",
    5: "Anac-SJ",
    6: "Anac-Sid",
    7: "Muk-Clin",
    8: "PT-Keyst",
    9: "Edm-King",
}

# Route ID -> (terminal_id_a, terminal_id_b) for fallback when primary terminal has no space data
ROUTE_TERMINALS: Dict[int, tuple] = {
    1: (7, 3),    # Seattle-Bainbridge
    2: (7, 4),    # Seattle-Bremerton
    3: (9, 22),   # Fauntleroy-Vashon-Southworth (Fauntleroy, Vashon)
    4: (16, 21),  # Point Defiance-Tahlequah
    7: (14, 5),   # Mukilteo-Clinton
    8: (17, 11),  # Port Townsend-Keystone (Coupeville)
    9: (8, 12),   # Edmonds-Kingston
}

def _get(obj: Dict, *keys: str, default: Any = None) -> Any:
    """Get value from dict trying multiple key names (PascalCase / camelCase)."""
    for key in keys:
        if key in obj:
            return obj[key]
        # Try lowercase first letter
        alt = key[:1].lower() + key[1:] if key else key
        if alt in obj:
            return obj[alt]
    return default


def _parse_time(s: Any) -> str:
    """Parse API time to HH:MM string. Handles .NET /Date(ms-offset)/ and ISO."""
    if s is None:
        return ""
    if isinstance(s, str):
        # .NET JSON: "/Date(1770212100000-0800)/"
        import re
        m = re.match(r"/Date\((\d+)([+-]\d{4})?\)/", s.strip())
        if m:
            try:
                ms = int(m.group(1))
                # ms is UTC; offset e.g. -0800 means local = UTC - 8 hours (Pacific)
                offset_str = (m.group(2) or "+0000").strip()
                sign = -1 if offset_str[0] == "-" else 1
                hours = int(offset_str[1:3]) * sign
                minutes = int(offset_str[3:5]) * sign
                utc = datetime.utcfromtimestamp(ms / 1000.0).replace(tzinfo=timezone.utc)
                tz = timezone(timedelta(hours=hours, minutes=minutes))
                local = utc.astimezone(tz)
                return local.strftime("%H:%M")
            except (ValueError, OverflowError):
                pass
        # ISO or "HH:MM"
        if "T" in s:
            s = s.split("T")[1][:5]
        return s[:5] if len(s) >= 5 else str(s)
    return str(s)


def _format_route_line(
    route_id: int,
    scheduled_time: str,
    spots_remaining: str,
    max_len: int = 22,
) -> str:
    """Build one abbreviated line for the board (route + time + spots)."""
    route_abbrev = ROUTE_ABBREVS.get(route_id, ROUTE_NAMES.get(route_id, f"R{route_id}")[:8])
    route_abbrev = route_abbrev[:8]
    time_str = (scheduled_time or "--").strip()[:5]
    parts = [route_abbrev, time_str or "--"]
    parts.append(spots_remaining.strip()[:3] if spots_remaining else "--")
    line = " ".join(parts)
    out = line[:max_len]
    # Defensive: if we somehow only have the route, append time placeholder
    if out.strip() == route_abbrev:
        out = f"{route_abbrev} --"[:max_len]
    return out


class WsdotPlugin(PluginBase):
    """WSDOT plugin: Washington State Ferries schedules, vessels, and alerts."""

    def __init__(self, manifest: Dict[str, Any]):
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._vessel_names: Dict[int, str] = {}
        self._sailing_space: Dict[int, Any] = {}
        self._wait_times: Dict[int, Any] = {}

    @property
    def plugin_id(self) -> str:
        return "wsdot"

    def _get_access_code(self) -> Optional[str]:
        code = self.config.get("api_access_code")
        if not code:
            code = os.getenv("WSDOT_API_ACCESS_CODE")
        return code or None

    def _get(self, base: str, path: str, params: Optional[Dict[str, str]] = None) -> Optional[Any]:
        """GET JSON from WSF API."""
        code = self._get_access_code()
        if not code:
            return None
        url = f"{base.rstrip('/')}/{path.lstrip('/')}"
        p = dict(params or {})
        p["apiaccesscode"] = code
        headers = {"Accept": "application/json"}
        try:
            r = requests.get(url, params=p, headers=headers, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning("WSF API request failed %s: %s", url, e)
            return None

    def _fetch_schedule_today(self, route_id: int) -> Optional[Dict[str, Any]]:
        """Fetch today's schedule for a route. OnlyRemainingTimes=false for full day."""
        path = f"scheduletoday/{route_id}/false"
        return self._get(WSF_SCHEDULE_BASE, path)

    def _fetch_vessel_names(self) -> Dict[int, str]:
        """Fetch vessel ID -> name map."""
        if self._vessel_names:
            return self._vessel_names
        data = self._get(WSF_VESSELS_BASE, "vesselbasics")
        if not data:
            return {}
        # Response may be list or dict with list
        items = data if isinstance(data, list) else _get(data, "VesselBasics", "vesselbasics") or data
        if not isinstance(items, list):
            items = [items]
        for item in items:
            vid = _get(item, "VesselID", "vesselId")
            name = _get(item, "VesselName", "vesselName") or _get(item, "Abbrev", "abbrev")
            if vid is not None and name:
                self._vessel_names[int(vid)] = str(name)[:12]
        return self._vessel_names

    def _fetch_terminal_sailing_space(self) -> None:
        """Fetch sailing space (car spots) per terminal."""
        data = self._get(WSF_TERMINALS_BASE, "terminalsailingspace")
        if not data:
            return
        items = data if isinstance(data, list) else _get(data, "TerminalSailingSpaces", "terminalSailingSpaces") or []
        if not isinstance(items, list):
            items = [items] if items else []
        self._sailing_space = {}
        for item in items:
            tid = _get(item, "TerminalID", "terminalId")
            if tid is not None:
                self._sailing_space[int(tid)] = item

    def _get_drive_up_space(
        self,
        terminal_id: int,
        departure_date_str: Any,
        vessel_id: Any,
        route_id: Optional[int] = None,
    ) -> str:
        """Get drive-up space count for a sailing from terminalsailingspace data.
        Match by terminal and vessel; use exact departure time if found, else closest by timestamp.
        If no space found for this terminal and route_id is known, try the route's other terminal.
        """
        terminal_id = int(terminal_id)
        result = self._get_drive_up_space_for_terminal(terminal_id, departure_date_str, vessel_id)
        if result:
            return result
        if route_id is not None:
            pair = ROUTE_TERMINALS.get(route_id)
            if pair:
                other = pair[1] if pair[0] == terminal_id else pair[0]
                if other != terminal_id:
                    result = self._get_drive_up_space_for_terminal(
                        other, departure_date_str, vessel_id
                    )
                    if result:
                        return result
        return ""

    def _get_drive_up_space_for_terminal(
        self, terminal_id: int, departure_date_str: Any, vessel_id: Any
    ) -> str:
        """Resolve drive-up space for a single terminal from terminalsailingspace data."""
        terminal_id = int(terminal_id)
        if terminal_id not in self._sailing_space:
            return ""
        term = self._sailing_space[terminal_id]
        departing = _get(term, "DepartingSpaces", "departingSpaces") or []
        if not isinstance(departing, list):
            departing = [departing]
        try:
            vid = int(vessel_id) if vessel_id is not None else None
        except (TypeError, ValueError):
            vid = None
        dep_str = str(departure_date_str).strip() if departure_date_str is not None else ""

        def _ms_from_date(s: Any) -> Optional[int]:
            if s is None:
                return None
            m = re.match(r"/Date\((\d+)([+-]\d{4})?\)/", str(s).strip())
            return int(m.group(1)) if m else None

        def _item_vessel_id(it: Dict[str, Any]) -> Optional[int]:
            raw = _get(it, "VesselID", "vesselId")
            if raw is None:
                return None
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        def _extract_count(it: Dict[str, Any]) -> Optional[str]:
            spaces = _get(it, "SpaceForArrivalTerminals", "spaceForArrivalTerminals") or []
            if not isinstance(spaces, list):
                spaces = [spaces] if spaces else []
            for sp in spaces:
                count = _get(sp, "DriveUpSpaceCount", "driveUpSpaceCount")
                if count is not None:
                    return str(count)[:3]
            count = _get(it, "DriveUpSpaceCount", "driveUpSpaceCount")
            if count is not None:
                return str(count)[:3]
            return None

        target_ms = _ms_from_date(departure_date_str)
        best_count: Optional[str] = None
        best_diff: Optional[float] = None

        for item in departing:
            item_vid = _item_vessel_id(item)
            if vid is not None and item_vid is not None and item_vid != vid:
                continue
            if vid is not None and item_vid is None:
                continue
            dep = _get(item, "Departure", "departure")
            count_str = _extract_count(item)
            if str(dep).strip() == dep_str:
                if count_str is not None:
                    return count_str
            if target_ms is not None and count_str is not None:
                item_ms = _ms_from_date(dep)
                if item_ms is not None:
                    diff = abs(item_ms - target_ms)
                    if best_diff is None or diff < best_diff:
                        best_diff = diff
                        best_count = count_str

        return best_count or ""

    def _fetch_terminal_wait_times(self) -> None:
        """Fetch wait times per terminal."""
        data = self._get(WSF_TERMINALS_BASE, "terminalwaittimes")
        if not data:
            return
        items = data if isinstance(data, list) else _get(data, "TerminalWaitTimes", "terminalWaitTimes") or []
        if not isinstance(items, list):
            items = [items] if items else []
        self._wait_times = {}
        for item in items:
            tid = _get(item, "TerminalID", "terminalId")
            if tid is not None:
                self._wait_times[int(tid)] = item

    def _fetch_alerts(self) -> List[Dict[str, Any]]:
        """Fetch ferry alerts."""
        data = self._get(WSF_SCHEDULE_BASE, "alerts")
        if not data:
            return []
        items = data if isinstance(data, list) else _get(data, "Alerts", "alerts") or []
        if not isinstance(items, list):
            items = [items] if items else []
        out = []
        for item in items[:10]:
            headline = _get(item, "Headline", "headline") or _get(item, "AlertFullTitle", "alertFullTitle") or "Alert"
            body = _get(item, "AlertFullDescription", "alertFullDescription") or _get(item, "Description", "description") or ""
            out.append({
                "headline": str(headline)[:22],
                "alert_text": str(body)[:22] if body else str(headline)[:22],
            })
        return out

    def _parse_schedule_response(self, raw: Any, route_id: int) -> Dict[str, Any]:
        """Parse schedule API response into departures_ab and departures_ba with vessel names and spots."""
        vessels = self._fetch_vessel_names()
        departures_ab: List[Dict[str, Any]] = []
        departures_ba: List[Dict[str, Any]] = []

        # API may return array of sailings or wrapped object.
        # Real WSF API returns { "TerminalCombos": [ { "DepartingTerminalID", "Times": [ {...}, ... ] } ] }
        sailings: List[Dict[str, Any]] = []
        if isinstance(raw, list):
            sailings = raw
        else:
            combos = _get(raw, "TerminalCombos", "terminalCombos")
            if isinstance(combos, list):
                for combo in combos:
                    times = _get(combo, "Times", "times")
                    departing_tid = _get(combo, "DepartingTerminalID", "departingTerminalId")
                    if isinstance(times, list):
                        for t in times:
                            s_copy = dict(t)
                            if departing_tid is not None:
                                s_copy["_departing_terminal_id"] = int(departing_tid)
                            sailings.append(s_copy)
            if not sailings:
                sailings = (
                    _get(raw, "Schedule", "schedule")
                    or _get(raw, "Sailings", "sailings")
                    or _get(raw, "Departures", "departures")
                    or []
                )
            if not isinstance(sailings, list):
                sailings = [sailings] if sailings else []

        for s in sailings[:20]:
            dep_time = _get(
                s,
                "DepartingTime", "departingTime",
                "DepartureTime", "departureTime",
                "LeavingTime", "leavingTime",
                "Time", "time",
                "SailingTime", "sailingTime",
            )
            vessel_id = _get(s, "VesselID", "vesselId", "VesselId")
            vessel_name = _get(s, "VesselName", "vesselName", "Vessel") or ""
            if not vessel_name and vessel_id is not None:
                vessel_name = vessels.get(int(vessel_id), "") or str(vessel_id)
            scheduled_time = _parse_time(dep_time)
            actual_time = _parse_time(_get(s, "ActualDepartureTime", "actualDepartureTime")) or ""
            # Sailing space: from schedule object or from Terminals API (terminalsailingspace)
            spaces = _get(s, "SpacesLeft", "spacesLeft")
            if spaces is None:
                spaces = _get(s, "VehicleCapacityRemaining", "vehicleCapacityRemaining")
            spots = str(spaces) if spaces is not None else ""
            if not spots and s.get("_departing_terminal_id") is not None:
                spots = self._get_drive_up_space(
                    s["_departing_terminal_id"],
                    dep_time,
                    vessel_id,
                    route_id=route_id,
                )

            dep = {
                "scheduled_time": scheduled_time[:5],
                "actual_time": actual_time[:5] if actual_time else "",
                "vessel_name": vessel_name[:12],
                "spots_remaining": spots[:3],
            }
            direction = _get(s, "Direction", "direction")
            if isinstance(direction, str) and "b" in direction.lower():
                departures_ba.append(dep)
            else:
                departures_ab.append(dep)

        # If no direction in data, put all in departures_ab
        if not departures_ba and departures_ab:
            half = len(departures_ab) // 2
            departures_ba = departures_ab[half:]
            departures_ab = departures_ab[:half]

        route_name = ROUTE_NAMES.get(route_id, f"Route {route_id}")
        wait_min = ""
        if self._wait_times:
            # Wait time is per terminal; use first available
            for wt in self._wait_times.values():
                m = _get(wt, "WaitTimeMinutes", "waitTimeMinutes") or _get(wt, "CurrentWaitTime", "currentWaitTime")
                if m is not None:
                    wait_min = str(m)[:2]
                    break

        # Build abbreviated formatted line for board (≤22 chars, like sports plugin)
        next_dep = (departures_ab or departures_ba or [{}])[0]
        formatted = _format_route_line(
            route_id=route_id,
            scheduled_time=next_dep.get("scheduled_time") or "",
            spots_remaining=next_dep.get("spots_remaining") or "",
            max_len=22,
        )

        return {
            "route_id": route_id,
            "route_name": route_name[:22],
            "formatted": formatted,
            "headers": FORMATTED_HEADERS,
            "departures_ab": departures_ab[:6],
            "departures_ba": departures_ba[:6],
            "wait_time_minutes": wait_min,
            "alerts": [],
        }

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors = []
        if not config.get("api_access_code") and not os.getenv("WSDOT_API_ACCESS_CODE"):
            errors.append("WSDOT API access code is required (free at https://www.wsdot.wa.gov/traffic/api/)")
        routes = config.get("routes", [])
        if not routes:
            errors.append("At least one ferry route is required")
        for i, r in enumerate(routes):
            if not isinstance(r, dict) or r.get("route_id") is None:
                errors.append(f"Route {i + 1} must have a route_id")
        refresh = config.get("refresh_seconds", 120)
        if refresh < 60:
            errors.append("Refresh interval must be at least 60 seconds")
        return errors

    def fetch_data(self) -> PluginResult:
        code = self._get_access_code()
        if not code:
            return PluginResult(
                available=False,
                error="WSDOT API access code not configured. Get a free code at https://www.wsdot.wa.gov/traffic/api/"
            )

        routes_config = self.config.get("routes", [])[:4]
        if not routes_config:
            return PluginResult(available=False, error="No ferry routes configured")

        try:
            self._fetch_vessel_names()
            self._fetch_terminal_sailing_space()
            self._fetch_terminal_wait_times()
            alerts_list = self._fetch_alerts()
        except Exception as e:
            logger.exception("WSF API error during fetch")
            return PluginResult(available=False, error=str(e))

        routes_data: List[Dict[str, Any]] = []
        for r in routes_config:
            route_id = r.get("route_id")
            if route_id is None:
                continue
            try:
                route_id = int(route_id)
            except (TypeError, ValueError):
                continue
            raw = self._fetch_schedule_today(route_id)
            if raw is None:
                abbrev = ROUTE_ABBREVS.get(route_id, ROUTE_NAMES.get(route_id, f"R{route_id}")[:8])[:8]
                routes_data.append({
                    "route_id": route_id,
                    "route_name": ROUTE_NAMES.get(route_id, f"Route {route_id}")[:22],
                    "formatted": f"{abbrev} No data"[:22],
                    "headers": FORMATTED_HEADERS,
                    "departures_ab": [],
                    "departures_ba": [],
                    "wait_time_minutes": "",
                    "alerts": [],
                })
                continue
            parsed = self._parse_schedule_response(raw, route_id)
            routes_data.append(parsed)

        if not routes_data:
            return PluginResult(
                available=False,
                error="Could not load any ferry route data"
            )

        data: Dict[str, Any] = {
            "route_count": len(routes_data),
            "has_alerts": bool(alerts_list),
            "headers": FORMATTED_HEADERS,
            "routes": routes_data,
            "alerts": alerts_list,
        }
        primary = routes_data[0]
        data["formatted"] = primary.get("formatted", "WSF")[:22]

        lines = self._build_formatted_lines(data)
        self._cache = data
        return PluginResult(available=True, data=data, formatted_lines=lines)

    def _build_formatted_lines(self, data: Dict[str, Any]) -> List[str]:
        """Build 6-line default display."""
        lines: List[str] = []
        lines.append("WSF FERRIES".center(22))
        for route in data.get("routes", [])[:3]:
            lines.append(route.get("formatted", "")[:22])
        if data.get("has_alerts"):
            lines.append("Alerts active".ljust(22))
        while len(lines) < 6:
            lines.append("")
        return lines[:6]

    def get_formatted_display(self) -> Optional[List[str]]:
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None
        return self._build_formatted_lines(self._cache or {})

    def cleanup(self) -> None:
        self._cache = None
        self._vessel_names = {}
        self._sailing_space = {}
        self._wait_times = {}
        logger.info("%s cleanup", self.plugin_id)


Plugin = WsdotPlugin
