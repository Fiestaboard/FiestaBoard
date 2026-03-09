"""SF Muni plugin for FiestaBoard.

Displays Muni transit arrival times with support for multiple stops and lines.
"""

from typing import Any, Dict, List, Optional
import logging
from datetime import datetime, timezone

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# Colors
COLOR_RED = 63
COLOR_ORANGE = 64


class MuniPlugin(PluginBase):
    """SF Muni transit plugin.
    
    Fetches arrival predictions from 511.org API via regional transit cache.
    Supports multiple stops with nested line data.
    """
    
    AGENCY = "SF"
    
    LINE_NAMES = {
        "N": "N-JUDAH",
        "J": "J-CHURCH",
        "K": "K-INGLESIDE",
        "L": "L-TARAVAL",
        "M": "M-OCEAN VIEW",
        "T": "T-THIRD",
        "S": "S-SHUTTLE",
        "F": "F-MARKET",
    }
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the muni plugin."""
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._transit_cache = None
    
    @property
    def plugin_id(self) -> str:
        return "muni"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate muni configuration."""
        errors = []
        
        if not config.get("api_key"):
            errors.append("511.org API key is required")
        
        stop_codes = config.get("stop_codes", [])
        if not stop_codes:
            errors.append("At least one stop code is required")
        
        return errors
    
    def _get_transit_cache(self):
        """Get or initialize transit cache."""
        if self._transit_cache is not None:
            return self._transit_cache
        
        try:
            from src.utils.transit_cache import get_transit_cache
            cache = get_transit_cache()
            
            api_key = self.config.get("api_key")
            refresh_interval = self.config.get("refresh_seconds", 90)
            
            cache.configure(
                api_key=api_key,
                refresh_interval=refresh_interval,
                enabled=True
            )
            
            if not cache.is_ready():
                cache.start()
            
            self._transit_cache = cache
            return cache
        except Exception as e:
            logger.error(f"Failed to initialize transit cache: {e}")
            return None
    
    def _normalize_line_code(self, line: str) -> str:
        """Normalize line code to single letter."""
        line_upper = line.upper()
        
        line_map = {
            "JUDAH": "N", "N-JUDAH": "N",
            "CHURCH": "J", "J-CHURCH": "J",
            "INGLESIDE": "K", "K-INGLESIDE": "K",
            "TARAVAL": "L", "L-TARAVAL": "L",
            "OCEAN VIEW": "M", "M-OCEAN VIEW": "M",
            "THIRD": "T", "T-THIRD": "T",
            "SHUTTLE": "S", "S-SHUTTLE": "S",
            "MARKET": "F", "F-MARKET": "F",
        }
        
        if line_upper in line_map:
            return line_map[line_upper]
        if len(line_upper) == 1:
            return line_upper
        if "-" in line_upper:
            return line_upper.split("-")[0]
        return line_upper
    
    def _get_display_line_name(self, line_code: str) -> str:
        """Get display-friendly line name."""
        return self.LINE_NAMES.get(line_code.upper(), line_code.upper())
    
    def _calculate_minutes_until(self, iso_timestamp: str) -> Optional[int]:
        """Calculate minutes until timestamp."""
        try:
            arrival_time = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = arrival_time - now
            return max(0, int(delta.total_seconds() / 60))
        except Exception:
            return None
    
    def _parse_stop_data(self, visits: List[Dict], stop_code: str) -> Optional[Dict]:
        """Parse arrival data for a single stop."""
        if not visits:
            return None
        
        arrivals_by_line = {}
        stop_name = ""
        
        for visit in visits:
            journey = visit.get("MonitoredVehicleJourney", {})
            
            published_line = journey.get("PublishedLineName", "")
            if isinstance(published_line, list):
                published_line = published_line[0] if published_line else ""
            if not published_line:
                continue
            
            line_code = self._normalize_line_code(published_line)
            
            monitored_call = journey.get("MonitoredCall", {})
            if not stop_name:
                stop_point_name = monitored_call.get("StopPointName", "")
                if isinstance(stop_point_name, list):
                    stop_point_name = stop_point_name[0] if stop_point_name else ""
                stop_name = stop_point_name
            
            expected_arrival = (
                monitored_call.get("ExpectedArrivalTime") or
                monitored_call.get("ExpectedDepartureTime") or
                monitored_call.get("AimedArrivalTime")
            )
            
            if expected_arrival:
                minutes = self._calculate_minutes_until(expected_arrival)
                if minutes is not None and minutes >= 0:
                    occupancy = journey.get("Occupancy", "UNKNOWN")
                    if isinstance(occupancy, list):
                        occupancy = occupancy[0] if occupancy else "UNKNOWN"
                    if occupancy is None:
                        occupancy = "UNKNOWN"
                    
                    is_full = str(occupancy).upper() == "FULL"
                    is_delayed = bool(journey.get("Delay") or journey.get("SituationRef"))
                    
                    arrival_data = {
                        "minutes": minutes,
                        "is_full": is_full,
                        "is_delayed": is_delayed,
                        "line_code": line_code,
                    }
                    
                    if line_code not in arrivals_by_line:
                        arrivals_by_line[line_code] = []
                    arrivals_by_line[line_code].append(arrival_data)
        
        if not arrivals_by_line:
            return None
        
        # Build lines dict
        lines = {}
        for line_code, line_arrivals in arrivals_by_line.items():
            line_arrivals.sort(key=lambda x: x["minutes"])
            top_arrivals = line_arrivals[:3]
            
            is_delayed = any(a.get("is_delayed") for a in top_arrivals)
            has_full = any(a.get("is_full") for a in top_arrivals)
            
            display_line = self._get_display_line_name(line_code)
            times = [str(a["minutes"]) for a in top_arrivals]
            formatted = f"{display_line}: {', '.join(times)} MIN"
            if is_delayed:
                formatted = f"{{63}}{formatted}"
            
            lines[line_code] = {
                "line": display_line,
                "line_code": line_code,
                "formatted": formatted,
                "next_arrival": top_arrivals[0]["minutes"] if top_arrivals else None,
                "is_delayed": is_delayed,
            }
        
        # Combined all_lines view
        all_arrivals = []
        for line_arrivals in arrivals_by_line.values():
            all_arrivals.extend(line_arrivals)
        all_arrivals.sort(key=lambda x: x["minutes"])
        top_all = all_arrivals[:3]
        
        all_line_codes = sorted(arrivals_by_line.keys())
        combined_display = "/".join([self._get_display_line_name(lc) for lc in all_line_codes])
        times = [str(a["minutes"]) for a in top_all]
        all_formatted = f"{combined_display}: {', '.join(times)} MIN"
        
        is_any_delayed = any(a.get("is_delayed") for a in top_all)
        if is_any_delayed:
            all_formatted = f"{{63}}{all_formatted}"
        
        # Get first line for backward compat
        first_line_code = all_line_codes[0] if all_line_codes else ""
        first_line_data = lines.get(first_line_code, {})
        
        return {
            "stop_code": stop_code,
            "stop_name": stop_name[:15] if stop_name else stop_code,
            "lines": lines,
            "all_lines": {
                "formatted": all_formatted,
                "next_arrival": top_all[0]["minutes"] if top_all else None,
                "is_delayed": is_any_delayed,
            },
            # Backward compat
            "line": first_line_data.get("line", ""),
            "formatted": first_line_data.get("formatted", ""),
            "is_delayed": first_line_data.get("is_delayed", False),
        }
    
    def fetch_data(self) -> PluginResult:
        """Fetch Muni arrival data."""
        stop_codes = self.config.get("stop_codes", [])
        if not stop_codes:
            return PluginResult(
                available=False,
                error="No stop codes configured"
            )
        
        cache = self._get_transit_cache()
        if not cache:
            return PluginResult(
                available=False,
                error="Transit cache not available"
            )
        
        if not cache.is_ready():
            return PluginResult(
                available=False,
                error="Transit cache not ready"
            )
        
        try:
            cached_data = cache.get_stops_data(self.AGENCY, stop_codes)
            stops_data = []
            
            for stop_code in stop_codes[:4]:
                visits = cached_data.get(stop_code, [])
                if visits:
                    parsed = self._parse_stop_data(visits, stop_code)
                    if parsed:
                        stops_data.append(parsed)
            
            if not stops_data:
                return PluginResult(
                    available=True,
                    data={
                        "stop_count": 0,
                        "stops": [],
                        "stop_name": "",
                        "stop_code": "",
                        "line": "",
                        "formatted": "NO ARRIVALS",
                        "is_delayed": False,
                    }
                )
            
            # Primary stop
            primary = stops_data[0]
            
            data = {
                # Primary stop
                "stop_name": primary["stop_name"],
                "stop_code": primary["stop_code"],
                "line": primary["line"],
                "formatted": primary["formatted"],
                "is_delayed": primary["is_delayed"],
                # Aggregate
                "stop_count": len(stops_data),
                # Array
                "stops": stops_data,
            }
            
            self._cache = data
            return PluginResult(available=True, data=data)
            
        except Exception as e:
            logger.exception("Error fetching Muni data")
            return PluginResult(available=False, error=str(e))
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        self._transit_cache = None
        self._cache = None


# Export the plugin class
Plugin = MuniPlugin

