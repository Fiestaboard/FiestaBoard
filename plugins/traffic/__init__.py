"""Traffic plugin for FiestaBoard.

Displays commute times using Google Routes API.
"""

from typing import Any, Dict, List, Optional, Tuple
import logging
import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class TrafficPlugin(PluginBase):
    """Traffic and commute time plugin.
    
    Fetches route times from Google Routes API.
    """
    
    TRAFFIC_INDEX_YELLOW = 1.2
    TRAFFIC_INDEX_RED = 1.5
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the traffic plugin."""
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
    
    @property
    def plugin_id(self) -> str:
        return "traffic"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate traffic configuration."""
        errors = []
        
        if not config.get("api_key"):
            errors.append("Google Routes API key is required")
        
        routes = config.get("routes", [])
        if not routes:
            errors.append("At least one route is required")
        
        return errors
    
    def _get_traffic_status(self, traffic_index: float) -> Tuple[str, str]:
        """Get traffic status and color."""
        if traffic_index > self.TRAFFIC_INDEX_RED:
            return "HEAVY", "{63}"  # red
        elif traffic_index > self.TRAFFIC_INDEX_YELLOW:
            return "MODERATE", "{65}"  # yellow
        else:
            return "LIGHT", "{66}"  # green
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse duration string (e.g., '1234s') to seconds."""
        if not duration_str:
            return 0
        return int(duration_str.rstrip('s'))
    
    def _build_waypoint(self, location: str) -> Dict:
        """Build waypoint for API request."""
        if "," in location:
            parts = location.split(",")
            if len(parts) == 2:
                try:
                    lat = float(parts[0].strip())
                    lng = float(parts[1].strip())
                    return {
                        "location": {
                            "latLng": {"latitude": lat, "longitude": lng}
                        }
                    }
                except ValueError:
                    pass
        return {"address": location}
    
    def _fetch_single_route(self, origin: str, destination: str, destination_name: str) -> Optional[Dict]:
        """Fetch traffic data for a single route."""
        api_key = self.config.get("api_key")
        
        url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "routes.duration,routes.staticDuration"
        }
        
        body = {
            "origin": self._build_waypoint(origin),
            "destination": self._build_waypoint(destination),
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        }
        
        try:
            response = requests.post(url, json=body, headers=headers, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Google Routes API error: {response.status_code}")
                return None
            
            data = response.json()
            if not data.get("routes"):
                return None
            
            route = data["routes"][0]
            duration = self._parse_duration(route.get("duration", "0s"))
            static_duration = self._parse_duration(route.get("staticDuration", "0s"))
            
            if static_duration == 0:
                static_duration = duration
            
            # Calculate traffic index
            traffic_index = duration / static_duration if static_duration > 0 else 1.0
            traffic_status, traffic_color = self._get_traffic_status(traffic_index)
            
            # Calculate delay
            delay_seconds = max(0, duration - static_duration)
            delay_minutes = round(delay_seconds / 60)
            duration_minutes = round(duration / 60)
            
            # Format message
            if delay_minutes > 0:
                formatted = f"{destination_name}: {duration_minutes}m (+{delay_minutes}m)"
            else:
                formatted = f"{destination_name}: {duration_minutes}m"
            
            return {
                "duration_minutes": duration_minutes,
                "delay_minutes": delay_minutes,
                "traffic_status": traffic_status,
                "traffic_color": traffic_color,
                "destination_name": destination_name,
                "formatted": formatted,
            }
            
        except Exception as e:
            logger.error(f"Error fetching traffic for {destination_name}: {e}")
            return None
    
    def fetch_data(self) -> PluginResult:
        """Fetch traffic data for all configured routes."""
        routes_config = self.config.get("routes", [])
        if not routes_config:
            return PluginResult(
                available=False,
                error="No routes configured"
            )
        
        routes_data = []
        for route in routes_config[:4]:
            route_data = self._fetch_single_route(
                origin=route.get("origin", ""),
                destination=route.get("destination", ""),
                destination_name=route.get("destination_name", "DEST")
            )
            if route_data:
                routes_data.append(route_data)
        
        if not routes_data:
            return PluginResult(
                available=False,
                error="Failed to fetch any route data"
            )
        
        # Find worst delay
        worst = max(routes_data, key=lambda r: r["delay_minutes"])
        
        # Primary route
        primary = routes_data[0]
        
        data = {
            # Primary route
            "duration_minutes": primary["duration_minutes"],
            "delay_minutes": primary["delay_minutes"],
            "traffic_status": primary["traffic_status"],
            "traffic_color": primary["traffic_color"],
            "destination_name": primary["destination_name"],
            "formatted": primary["formatted"],
            # Aggregates
            "route_count": len(routes_data),
            "worst_delay": worst["delay_minutes"],
            # Array
            "routes": routes_data,
        }
        
        self._cache = data
        return PluginResult(available=True, data=data)
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted display."""
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None
        
        data = self._cache
        if not data:
            return None
        
        routes = data.get("routes", [])
        lines = ["TRAFFIC".center(22), ""]
        
        for route in routes[:4]:
            lines.append(route["formatted"][:22])
        
        while len(lines) < 6:
            lines.append("")
        
        return lines[:6]


# Export the plugin class
Plugin = TrafficPlugin

