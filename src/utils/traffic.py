"""Traffic data source using Google Routes API.

Supports multiple route monitoring with indexed template access.
"""

import logging
import requests
from typing import Optional, Dict, Tuple, List

from ..config import Config

logger = logging.getLogger(__name__)


class TrafficSource:
    """Fetches traffic/drive time data from Google Routes API."""
    
    # Traffic index thresholds
    TRAFFIC_INDEX_YELLOW = 1.2  # 20% slower than normal
    TRAFFIC_INDEX_RED = 1.5    # 50% slower than normal
    
    def __init__(
        self,
        api_key: str,
        routes: List[Dict[str, str]]
    ):
        """
        Initialize traffic source.
        
        Args:
            api_key: Google Maps API key with Routes API enabled
            routes: List of route dictionaries with keys:
                    - origin: Origin address or lat,lng
                    - destination: Destination address or lat,lng
                    - destination_name: Display name (e.g., "DOWNTOWN", "WORK")
                    - travel_mode: Optional. One of "DRIVE", "BICYCLE", "TRANSIT", "WALK" (default: "DRIVE")
        """
        self.api_key = api_key
        # Support both new (list of routes) and old (single route) format
        if isinstance(routes, list):
            self.routes = routes if routes else []
        else:
            # Backward compatibility - treat as dict with origin/destination
            self.routes = [routes]
        
        # For backward compatibility
        if self.routes:
            self.origin = self.routes[0].get("origin", "")
            self.destination = self.routes[0].get("destination", "")
            self.destination_name = self.routes[0].get("destination_name", "DOWNTOWN")
    
    @staticmethod
    def calculate_traffic_index(
        duration_in_traffic: Optional[int],
        duration_normal: int
    ) -> float:
        """
        Calculate traffic index as ratio of traffic time to normal time.
        
        Traffic_Index = durationInTraffic / duration
        
        Args:
            duration_in_traffic: Duration with traffic in seconds (may be None)
            duration_normal: Normal/static duration in seconds
            
        Returns:
            Traffic index (1.0 = normal, >1.0 = slower due to traffic)
        """
        if duration_normal <= 0:
            return 1.0
        
        # If traffic duration is missing, default to normal duration
        if duration_in_traffic is None:
            duration_in_traffic = duration_normal
        
        return round(duration_in_traffic / duration_normal, 2)
    
    @staticmethod
    def get_traffic_status(traffic_index: float) -> Tuple[str, str]:
        """
        Get traffic status and color based on traffic index.
        
        Index > 1.2 -> YELLOW
        Index > 1.5 -> RED
        
        Args:
            traffic_index: Calculated traffic index
            
        Returns:
            Tuple of (status, color)
        """
        if traffic_index > TrafficSource.TRAFFIC_INDEX_RED:
            return "HEAVY", "RED"
        elif traffic_index > TrafficSource.TRAFFIC_INDEX_YELLOW:
            return "MODERATE", "YELLOW"
        else:
            return "LIGHT", "GREEN"
    
    @staticmethod
    def format_message(
        destination_name: str,
        duration_minutes: int,
        delay_minutes: int
    ) -> str:
        """
        Format traffic message for display.
        
        Format: "DOWNTOWN: [Time]m (+[Delay]m delay)"
        
        Args:
            destination_name: Name of destination
            duration_minutes: Total travel time in minutes
            delay_minutes: Delay due to traffic in minutes
            
        Returns:
            Formatted message string
        """
        if delay_minutes > 0:
            return f"{destination_name}: {duration_minutes}m (+{delay_minutes}m delay)"
        else:
            return f"{destination_name}: {duration_minutes}m"
    
    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        """
        Parse duration string from Google API (e.g., "1234s") to seconds.
        
        Args:
            duration_str: Duration string like "1234s"
            
        Returns:
            Duration in seconds
        """
        if not duration_str:
            return 0
        # Remove 's' suffix and convert to int
        return int(duration_str.rstrip('s'))
    
    def fetch_traffic_data(self) -> Optional[Dict[str, any]]:
        """
        Fetch traffic data from Google Routes API (backward compatibility).
        Returns data for first configured route.
        
        Returns:
            Dictionary with traffic data, or None if failed
        """
        if not self.routes:
            return None
        
        # For backward compatibility, return data for first route
        results = self.fetch_multiple_routes()
        if results and len(results) > 0:
            return results[0]
        return None
    
    def fetch_multiple_routes(self) -> List[Dict[str, any]]:
        """
        Fetch traffic data for all configured routes.
        
        Returns:
            List of dictionaries with traffic data for each route
        """
        if not self.routes:
            return []
        
        results = []
        for route in self.routes:
            try:
                data = self._fetch_single_route(
                    origin=route.get("origin", ""),
                    destination=route.get("destination", ""),
                    destination_name=route.get("destination_name", "DESTINATION"),
                    travel_mode=route.get("travel_mode", "DRIVE")
                )
                if data:
                    results.append(data)
            except Exception as e:
                logger.error(f"Error fetching traffic for route to {route.get('destination_name', 'unknown')}: {e}")
        
        return results
    
    def get_worst_delay(self) -> Optional[Dict[str, any]]:
        """
        Get the route with the worst delay across all configured routes.
        
        Returns:
            Dictionary with route data for route with worst delay, or None if no routes
        """
        routes = self.fetch_multiple_routes()
        
        if not routes:
            return None
        
        # Find route with highest delay
        worst = max(routes, key=lambda r: r.get("delay_minutes", 0))
        return worst
    
    def _fetch_single_route(
        self,
        origin: str,
        destination: str,
        destination_name: str,
        travel_mode: str = "DRIVE"
    ) -> Optional[Dict[str, any]]:
        """
        Fetch traffic data for a single route from Google Routes API.
        
        Uses ComputeRoutes with TRAFFIC_AWARE_OPTIMAL routing preference.
        
        Args:
            origin: Origin address or lat,lng
            destination: Destination address or lat,lng
            destination_name: Display name for destination
            travel_mode: Travel mode - one of "DRIVE", "BICYCLE", "TRANSIT", "WALK" (default: "DRIVE")
        
        Returns:
            Dictionary with traffic data, or None if failed
        """
        url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.routeToken"
        }
        
        # Validate travel mode
        valid_modes = ["DRIVE", "BICYCLE", "TRANSIT", "WALK", "TWO_WHEELER"]
        if travel_mode.upper() not in valid_modes:
            logger.warning(f"Invalid travel mode '{travel_mode}', defaulting to DRIVE")
            travel_mode = "DRIVE"
        
        # Build request body
        body = {
            "origin": self._build_waypoint(origin),
            "destination": self._build_waypoint(destination),
            "travelMode": travel_mode.upper(),
            "computeAlternativeRoutes": False,
            "languageCode": "en-US",
            "units": "IMPERIAL"
        }
        
        # Only add routing preference for DRIVE and TWO_WHEELER
        # BICYCLE, WALK, and TRANSIT don't support routing preferences
        if travel_mode.upper() in ["DRIVE", "TWO_WHEELER"]:
            body["routingPreference"] = "TRAFFIC_AWARE_OPTIMAL"
        
        try:
            response = requests.post(url, json=body, headers=headers, timeout=10)
            
            # Handle specific HTTP errors with helpful messages
            if response.status_code == 403:
                logger.error(f"Google Routes API returned 403 Forbidden. Check: 1) Routes API is enabled, 2) Billing is set up, 3) API key has proper restrictions")
                logger.error(f"Response: {response.text}")
                return None
            elif response.status_code == 400:
                logger.error(f"Google Routes API returned 400 Bad Request. The addresses may be invalid or improperly formatted.")
                logger.error(f"Response: {response.text}")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            if not data.get("routes"):
                logger.error("No routes returned from Google Routes API")
                return None
            
            route = data["routes"][0]
            
            # Parse durations (format: "1234s")
            duration_in_traffic = self._parse_duration(route.get("duration", "0s"))
            static_duration = self._parse_duration(route.get("staticDuration", "0s"))
            route_token = route.get("routeToken", "")
            
            # If static duration is 0, use duration as fallback
            if static_duration == 0:
                static_duration = duration_in_traffic
            
            # Calculate traffic index
            traffic_index = self.calculate_traffic_index(duration_in_traffic, static_duration)
            traffic_status, traffic_color = self.get_traffic_status(traffic_index)
            
            # Calculate delay
            delay_seconds = max(0, duration_in_traffic - static_duration)
            delay_minutes = round(delay_seconds / 60)
            
            # Convert to minutes
            duration_minutes = round(duration_in_traffic / 60)
            static_duration_minutes = round(static_duration / 60)
            
            # Format message
            formatted_message = self.format_message(
                destination_name,
                duration_minutes,
                delay_minutes
            )
            
            return {
                # Raw durations (seconds)
                "duration": duration_in_traffic,
                "static_duration": static_duration,
                "route_token": route_token,
                
                # Calculated values
                "traffic_index": traffic_index,
                "traffic_status": traffic_status,
                "traffic_color": traffic_color,
                
                # Friendly formats
                "duration_minutes": duration_minutes,
                "static_duration_minutes": static_duration_minutes,
                "delay_minutes": delay_minutes,
                "formatted_message": formatted_message,
                "formatted": formatted_message,  # Alias for template compatibility
                
                # Route info
                "origin": origin,
                "destination": destination,
                "destination_name": destination_name,
                "travel_mode": travel_mode.upper(),
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch traffic from Google Routes API: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Unexpected response format from Google Routes API: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching traffic data: {e}")
            return None
    
    def _build_waypoint(self, location: str) -> Dict:
        """
        Build a waypoint object for the Routes API.
        
        Args:
            location: Address string or "lat,lng" format
            
        Returns:
            Waypoint dictionary for API request
        """
        # Check if location is lat,lng format
        if "," in location:
            parts = location.split(",")
            if len(parts) == 2:
                try:
                    lat = float(parts[0].strip())
                    lng = float(parts[1].strip())
                    return {
                        "location": {
                            "latLng": {
                                "latitude": lat,
                                "longitude": lng
                            }
                        }
                    }
                except ValueError:
                    pass
        
        # Default to address
        return {
            "address": location
        }


def get_traffic_source() -> Optional[TrafficSource]:
    """Get configured traffic source instance."""
    api_key = Config.GOOGLE_ROUTES_API_KEY if hasattr(Config, 'GOOGLE_ROUTES_API_KEY') else ""
    
    if not api_key:
        logger.warning("Google Routes API key not configured")
        return None
    
    # Support both new (TRAFFIC_ROUTES list) and old (TRAFFIC_ORIGIN/DESTINATION) config
    routes = getattr(Config, 'TRAFFIC_ROUTES', None)
    
    if not routes:
        # Fall back to single route (backward compatibility)
        origin = Config.TRAFFIC_ORIGIN if hasattr(Config, 'TRAFFIC_ORIGIN') else ""
        destination = Config.TRAFFIC_DESTINATION if hasattr(Config, 'TRAFFIC_DESTINATION') else ""
        destination_name = Config.TRAFFIC_DESTINATION_NAME if hasattr(Config, 'TRAFFIC_DESTINATION_NAME') else "DOWNTOWN"
        
        if origin and destination:
            routes = [{
                "origin": origin,
                "destination": destination,
                "destination_name": destination_name
            }]
        else:
            # No routes configured yet, but return source anyway so variables show in UI
            routes = []
    
    # Return source even with empty routes so template variables are available
    return TrafficSource(
        api_key=api_key,
        routes=routes
    )
