"""Muni transit data source using 511.org regional transit cache.

This module provides real-time arrival predictions for SF Muni transit.
Uses the regional transit cache to avoid rate limiting (fetches all Bay Area
transit data once every 90 seconds, then serves Muni data from cache).
Supports multiple stop monitoring.
"""

import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from ..config import Config
from .transit_cache import get_transit_cache

logger = logging.getLogger(__name__)


# Board color codes
COLOR_RED = 63    # Delay indicator
COLOR_ORANGE = 64  # Full occupancy indicator


class MuniSource:
    """Fetches real-time transit data from regional transit cache."""
    
    AGENCY = "SF"  # San Francisco Muni
    
    # Legacy API URLs (kept for reference, no longer used directly)
    API_BASE_URL = "http://api.511.org/transit/StopMonitoring"
    STOPS_API_URL = "http://api.511.org/transit/stops"
    
    def __init__(self, api_key: str, stop_codes: List[str], line_name: Optional[str] = None):
        """
        Initialize Muni source.
        
        Args:
            api_key: 511.org API key
            stop_codes: List of stop codes to monitor (e.g., ["15726", "15727"])
            line_name: Optional line name filter (e.g., "N" for N-Judah)
        """
        self.api_key = api_key
        # Support both single string (backward compatibility) and list
        if isinstance(stop_codes, str):
            self.stop_codes = [stop_codes]
        else:
            self.stop_codes = stop_codes if stop_codes else []
        self.line_name = line_name
        
        # For backward compatibility
        self.stop_code = self.stop_codes[0] if self.stop_codes else ""
    
    
    def fetch_arrivals(self) -> Optional[Dict[str, Any]]:
        """
        Fetch arrival predictions from 511.org StopMonitoring API (backward compatibility).
        Returns data for first configured stop.
        
        Returns:
            Dictionary with parsed arrival data, or None if failed:
            {
                "line": str,           # Line name (e.g., "N-JUDAH")
                "stop_name": str,      # Stop name
                "stop_code": str,      # Stop code
                "arrivals": [          # List of next arrivals
                    {
                        "minutes": int,
                        "occupancy": str,      # EMPTY, MANY_SEATS, FEW_SEATS, STANDING, FULL
                        "is_full": bool,
                    },
                    ...
                ],
                "is_delayed": bool,        # Any vehicle delayed
                "delay_description": str,  # Delay reason text
                "formatted": str,          # Pre-formatted display string
                "color_code": int,         # Board color code (63=red, 64=orange, 0=none)
            }
        """
        if not self.stop_codes:
            return None
        
        # For backward compatibility, return data for first stop
        results = self.fetch_multiple_stops()
        if results and len(results) > 0:
            return results[0]
        return None
    
    def fetch_multiple_stops(self) -> List[Dict[str, Any]]:
        """
        Fetch arrival predictions for all configured stops from regional transit cache.
        
        Returns:
            List of dictionaries with arrival data for each stop
        """
        if not self.stop_codes:
            return []
        
        results = []
        
        try:
            # Get transit cache instance
            cache = get_transit_cache()
            
            # Check if cache is ready
            if not cache.is_ready():
                logger.warning("Regional transit cache not ready yet. Waiting for first refresh...")
                return []
            
            # Get cached data for all our stops at once
            cached_stops_data = cache.get_stops_data(self.AGENCY, self.stop_codes)
            
            # Parse each stop's data
            for stop_code in self.stop_codes:
                visits = cached_stops_data.get(stop_code, [])
                
                if not visits:
                    logger.debug(f"No arrivals in cache for stop {stop_code}")
                    continue
                
                # Build a mock StopMonitoring response structure from cached visits
                mock_response = {
                    "ServiceDelivery": {
                        "StopMonitoringDelivery": {
                            "MonitoredStopVisit": visits
                        }
                    }
                }
                
                # Parse using existing parser
                parsed = self._parse_response(mock_response, stop_code)
                if parsed:
                    results.append(parsed)
                    logger.debug(f"Parsed Muni data for stop {stop_code} from regional cache")
            
            return results
            
        except Exception as e:
            logger.error(f"Error fetching Muni data from regional cache: {e}", exc_info=True)
            return []
    
    def get_next_arrival(self) -> Optional[Dict[str, Any]]:
        """
        Get the stop with the soonest arrival across all configured stops.
        
        Returns:
            Dictionary with stop data for stop with soonest arrival, or None if no stops
        """
        stops = self.fetch_multiple_stops()
        
        if not stops:
            return None
        
        # Find stop with soonest arrival
        best = min(stops, key=lambda s: s.get("arrivals", [{}])[0].get("minutes", 999) if s.get("arrivals") else 999)
        return best
    
    def _parse_response(self, data: Dict[str, Any], stop_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Parse the StopMonitoring API response.
        
        Args:
            data: Raw JSON response from 511.org
            stop_code: The stop code being queried (optional, for logging)
            
        Returns:
            Parsed arrival data dictionary, or None if no data
        """
        try:
            # Use provided stop_code or fall back to instance variable
            if stop_code is None:
                stop_code = self.stop_code
            
            # Navigate to the monitored stop visits
            service_delivery = data.get("ServiceDelivery", {})
            stop_monitoring = service_delivery.get("StopMonitoringDelivery", {})
            
            # Handle both list and single object responses
            if isinstance(stop_monitoring, list):
                stop_monitoring = stop_monitoring[0] if stop_monitoring else {}
            
            monitored_visits = stop_monitoring.get("MonitoredStopVisit", [])
            
            if not monitored_visits:
                logger.warning(f"No arrivals found for stop {stop_code}")
                return None
            
            # Group arrivals by line
            arrivals_by_line = {}  # Dict[line_code, List[arrival_dict]]
            stop_name = ""
            all_arrivals = []  # For all_lines combined view
            
            for visit in monitored_visits:
                journey = visit.get("MonitoredVehicleJourney", {})
                
                # Get line info
                published_line = journey.get("PublishedLineName", "")
                if isinstance(published_line, list):
                    published_line = published_line[0] if published_line else ""
                
                if not published_line:
                    continue
                
                # Normalize line code (JUDAH -> N, J-CHURCH -> J, etc.)
                line_code = self._normalize_line_code(published_line)
                
                # Get stop name from first valid entry
                monitored_call = journey.get("MonitoredCall", {})
                if not stop_name:
                    stop_point_name = monitored_call.get("StopPointName", "")
                    if isinstance(stop_point_name, list):
                        stop_point_name = stop_point_name[0] if stop_point_name else ""
                    stop_name = stop_point_name
                
                # Calculate minutes until arrival
                expected_arrival = monitored_call.get("ExpectedArrivalTime") or \
                                   monitored_call.get("ExpectedDepartureTime") or \
                                   monitored_call.get("AimedArrivalTime")
                
                if expected_arrival:
                    minutes = self._calculate_minutes_until(expected_arrival)
                    if minutes is not None and minutes >= 0:
                        # Get occupancy status
                        occupancy = journey.get("Occupancy", "UNKNOWN")
                        if isinstance(occupancy, list):
                            occupancy = occupancy[0] if occupancy else "UNKNOWN"
                        
                        # Handle None occupancy
                        if occupancy is None:
                            occupancy = "UNKNOWN"
                        
                        is_full = str(occupancy).upper() == "FULL"
                        
                        # Check delay info
                        delay_info = journey.get("Delay")
                        situation_refs = journey.get("SituationRef", [])
                        is_arrival_delayed = bool(delay_info or situation_refs)
                        delay_text = ""
                        if delay_info:
                            delay_text = self._format_delay(delay_info)
                        elif situation_refs:
                            delay_text = "Service disruption"
                        
                        arrival_data = {
                            "minutes": minutes,
                            "occupancy": str(occupancy).upper(),
                            "is_full": is_full,
                            "is_delayed": is_arrival_delayed,
                            "delay_description": delay_text,
                            "line_code": line_code,
                        }
                        
                        # Add to line-specific list
                        if line_code not in arrivals_by_line:
                            arrivals_by_line[line_code] = []
                        arrivals_by_line[line_code].append(arrival_data)
                        
                        # Add to all arrivals
                        all_arrivals.append(arrival_data)
            
            if not arrivals_by_line and not all_arrivals:
                return None
            
            # Build lines dict with data for each line
            lines = {}
            for line_code, line_arrivals in arrivals_by_line.items():
                # Sort and take top 3 for this line
                line_arrivals.sort(key=lambda x: x["minutes"])
                top_arrivals = line_arrivals[:3]
                
                # Check if any are delayed or full
                is_delayed = any(a.get("is_delayed", False) for a in top_arrivals)
                has_full = any(a.get("is_full", False) for a in top_arrivals)
                
                # Color code
                color_code = 0
                if is_delayed:
                    color_code = COLOR_RED
                elif has_full:
                    color_code = COLOR_ORANGE
                
                # Format display
                display_line = self._get_display_line_name(line_code)
                formatted = self._format_display(display_line, top_arrivals, is_delayed)
                
                lines[line_code] = {
                    "line": display_line,
                    "line_code": line_code,
                    "arrivals": top_arrivals,
                    "next_arrival": top_arrivals[0]["minutes"] if top_arrivals else None,
                    "is_delayed": is_delayed,
                    "delay_description": top_arrivals[0].get("delay_description", "") if is_delayed and top_arrivals else "",
                    "formatted": formatted,
                    "color_code": color_code,
                }
            
            # Build all_lines combined view
            all_arrivals.sort(key=lambda x: x["minutes"])
            top_all = all_arrivals[:3]
            
            # Get all line codes for display
            all_line_codes = sorted(arrivals_by_line.keys())
            combined_line_display = "/".join([self._get_display_line_name(lc) for lc in all_line_codes])
            
            # Check if any are delayed
            is_any_delayed = any(a.get("is_delayed", False) for a in top_all)
            has_any_full = any(a.get("is_full", False) for a in top_all)
            
            all_color_code = 0
            if is_any_delayed:
                all_color_code = COLOR_RED
            elif has_any_full:
                all_color_code = COLOR_ORANGE
            
            all_lines_formatted = self._format_display(combined_line_display, top_all, is_any_delayed)
            
            all_lines = {
                "formatted": all_lines_formatted,
                "next_arrival": top_all[0]["minutes"] if top_all else None,
                "is_delayed": is_any_delayed,
                "arrivals": top_all,
                "color_code": all_color_code,
            }
            
            # Backward compatibility: use first line data at top level
            first_line_code = all_line_codes[0] if all_line_codes else ""
            first_line_data = lines.get(first_line_code, {})
            
            return {
                "stop_code": stop_code,
                "stop_name": stop_name,
                "lines": lines,
                "all_lines": all_lines,
                # Backward compatibility fields
                "line": first_line_data.get("line", ""),
                "arrivals": first_line_data.get("arrivals", []),
                "is_delayed": first_line_data.get("is_delayed", False),
                "delay_description": first_line_data.get("delay_description", ""),
                "formatted": first_line_data.get("formatted", ""),
                "color_code": first_line_data.get("color_code", 0),
            }
            
        except Exception as e:
            logger.error(f"Error parsing 511.org response: {e}", exc_info=True)
            return None
    
    def _calculate_minutes_until(self, iso_timestamp: str) -> Optional[int]:
        """
        Calculate minutes until the given ISO timestamp.
        
        Args:
            iso_timestamp: ISO 8601 timestamp string
            
        Returns:
            Minutes until arrival, or None if parsing fails
        """
        try:
            # Parse ISO timestamp (511.org uses ISO 8601 with timezone)
            # Handle various formats: 2024-12-24T10:30:00-08:00 or 2024-12-24T18:30:00Z
            arrival_time = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            
            delta = arrival_time - now
            minutes = int(delta.total_seconds() / 60)
            
            return max(0, minutes)  # Don't return negative minutes
            
        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to parse timestamp {iso_timestamp}: {e}")
            return None
    
    def _format_delay(self, delay_str: str) -> str:
        """
        Format PT duration string to human-readable delay.
        
        Args:
            delay_str: ISO 8601 duration (e.g., "PT2M30S")
            
        Returns:
            Human-readable delay string
        """
        try:
            # Simple parsing for PT format
            if delay_str.startswith("PT"):
                delay_str = delay_str[2:]
                minutes = 0
                seconds = 0
                
                if "M" in delay_str:
                    parts = delay_str.split("M")
                    minutes = int(parts[0])
                    delay_str = parts[1] if len(parts) > 1 else ""
                
                if "S" in delay_str:
                    seconds = int(delay_str.replace("S", ""))
                
                total_minutes = minutes + (seconds // 60)
                if total_minutes > 0:
                    return f"{total_minutes} min delay"
            
            return "Delayed"
        except (ValueError, IndexError):
            return "Delayed"
    
    def _format_display(self, line: str, arrivals: List[Dict], is_delayed: bool) -> str:
        """
        Format arrival data for board display.
        
        Format: "N-JUDAH: 4, 12, 19 MIN (DELAY)"
        
        Args:
            line: Line name
            arrivals: List of arrival dictionaries
            is_delayed: Whether there's a delay
            
        Returns:
            Formatted display string
        """
        if not arrivals:
            return f"{line}: No arrivals"
        
        # Format arrival times, marking full trains with color
        times = []
        for arr in arrivals:
            mins = arr["minutes"]
            if arr["is_full"]:
                # Orange color marker for full trains
                times.append(f"{{64}}{mins}")
            else:
                times.append(str(mins))
        
        time_str = ", ".join(times)
        
        # Add delay indicator
        suffix = ""
        if is_delayed:
            suffix = " (DELAY)"
        
        # Format: "N-JUDAH: 4, 12, 19 MIN (DELAY)"
        # If line name contains "-" already (like "N-OWL"), use as-is
        # Otherwise append common names if we know them
        display_line = self._get_display_line_name(line)
        
        result = f"{display_line}: {time_str} MIN{suffix}"
        
        # Apply delay color to entire line if delayed
        if is_delayed:
            result = f"{{63}}{result}"
        
        return result
    
    def _normalize_line_code(self, line: str) -> str:
        """
        Normalize line code to single letter format.
        
        Args:
            line: Raw line name (e.g., "JUDAH", "N-JUDAH", "N")
            
        Returns:
            Normalized line code (e.g., "N")
        """
        line_upper = line.upper()
        
        # Map full names to single letters
        line_map = {
            "JUDAH": "N",
            "N-JUDAH": "N",
            "CHURCH": "J",
            "J-CHURCH": "J",
            "INGLESIDE": "K",
            "K-INGLESIDE": "K",
            "TARAVAL": "L",
            "L-TARAVAL": "L",
            "OCEAN VIEW": "M",
            "M-OCEAN VIEW": "M",
            "THIRD": "T",
            "T-THIRD": "T",
            "SHUTTLE": "S",
            "S-SHUTTLE": "S",
            "MARKET": "F",
            "F-MARKET": "F",
        }
        
        # Try direct lookup
        if line_upper in line_map:
            return line_map[line_upper]
        
        # If already single letter, return it
        if len(line_upper) == 1:
            return line_upper
        
        # Extract first letter if format like "N-JUDAH"
        if "-" in line_upper:
            return line_upper.split("-")[0]
        
        # Default: return as-is
        return line_upper
    
    def _get_display_line_name(self, line: str) -> str:
        """
        Get display-friendly line name.
        
        Args:
            line: Raw line code
            
        Returns:
            Display-friendly line name
        """
        # Known Muni line names
        line_names = {
            "N": "N-JUDAH",
            "J": "J-CHURCH",
            "K": "K-INGLESIDE",
            "L": "L-TARAVAL",
            "M": "M-OCEAN VIEW",
            "T": "T-THIRD",
            "S": "S-SHUTTLE",
            "F": "F-MARKET",
        }
        
        return line_names.get(line.upper(), line.upper())


def get_muni_source() -> Optional[MuniSource]:
    """Get configured Muni source instance and initialize transit cache."""
    if not Config.MUNI_API_KEY:
        logger.debug("Muni API key not configured")
        return None
    
    # Initialize and configure the regional transit cache
    cache = get_transit_cache()
    
    # Configure cache with API key and refresh settings
    refresh_interval = getattr(Config, 'TRANSIT_CACHE_REFRESH_SECONDS', 90)
    cache_enabled = getattr(Config, 'TRANSIT_CACHE_ENABLED', True)
    cache.configure(
        api_key=Config.MUNI_API_KEY,
        refresh_interval=refresh_interval,
        enabled=cache_enabled
    )
    
    # Start cache if not already running
    if cache_enabled and not cache.is_ready():
        cache.start()
    
    # Support both new (MUNI_STOP_CODES list) and old (MUNI_STOP_CODE string) config
    stop_codes = getattr(Config, 'MUNI_STOP_CODES', None)
    
    if not stop_codes:
        # Fall back to single stop code (backward compatibility)
        stop_code = Config.MUNI_STOP_CODE
        if stop_code:
            stop_codes = [stop_code]
        else:
            # No stops configured yet, but return source anyway so variables show in UI
            stop_codes = []
    
    # Return source even with empty stop_codes so template variables are available
    return MuniSource(
        api_key=Config.MUNI_API_KEY,
        stop_codes=stop_codes,
        line_name=Config.MUNI_LINE_NAME if Config.MUNI_LINE_NAME else None
    )

