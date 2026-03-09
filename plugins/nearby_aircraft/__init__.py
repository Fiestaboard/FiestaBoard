"""Nearby Aircraft plugin for FiestaBoard.

Displays real-time nearby aircraft information using the OpenSky Network API.
Shows call sign, altitude, ground speed, and squawk code for aircraft within
a user-defined radius.
"""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
import logging
import requests
from math import radians, cos, sin, asin, sqrt

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# OpenSky API endpoints
OPENSKY_BASE_URL = "https://opensky-network.org/api"
OPENSKY_OAUTH_URL = f"{OPENSKY_BASE_URL}/v1/oauth/token"
OPENSKY_STATES_URL = f"{OPENSKY_BASE_URL}/states/all"

# State vector field indices (OpenSky API returns arrays)
# See: https://openskynetwork.github.io/opensky-api/rest.html#response
STATE_VECTOR_INDICES = {
    "icao24": 0,
    "callsign": 1,
    "origin_country": 2,
    "time_position": 3,
    "last_contact": 4,
    "longitude": 5,
    "latitude": 6,
    "baro_altitude": 7,
    "on_ground": 8,
    "velocity": 9,
    "true_track": 10,
    "vertical_rate": 11,
    "sensors": 12,
    "geo_altitude": 13,
    "squawk": 14,
    "spi": 15,
    "position_source": 16,
}


class NearbyAircraftPlugin(PluginBase):
    """Nearby aircraft plugin.
    
    Fetches real-time aircraft data from OpenSky Network API and displays
    aircraft within a specified radius showing call sign, altitude, ground
    speed, and squawk code.
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the nearby aircraft plugin."""
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
    
    @property
    def plugin_id(self) -> str:
        return "nearby_aircraft"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate nearby aircraft configuration."""
        errors = []
        
        lat = config.get("latitude")
        lon = config.get("longitude")
        
        if lat is None:
            errors.append("Latitude is required")
        elif not isinstance(lat, (int, float)) or not (-90 <= lat <= 90):
            errors.append("Latitude must be a number between -90 and 90")
        
        if lon is None:
            errors.append("Longitude is required")
        elif not isinstance(lon, (int, float)) or not (-180 <= lon <= 180):
            errors.append("Longitude must be a number between -180 and 180")
        
        radius_km = config.get("radius_km", 50)
        if not isinstance(radius_km, (int, float)) or radius_km < 1:
            errors.append("Radius must be at least 1 km")
        
        max_aircraft = config.get("max_aircraft", 4)
        if not isinstance(max_aircraft, int) or not (1 <= max_aircraft <= 10):
            errors.append("Max aircraft must be between 1 and 10")
        
        refresh_seconds = config.get("refresh_seconds", 120)
        if not isinstance(refresh_seconds, int) or refresh_seconds < 10:
            errors.append("Refresh interval must be at least 10 seconds")
        
        return errors
    
    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points on Earth in km.
        
        Uses the Haversine formula to compute great-circle distance.
        
        Args:
            lat1: Latitude of first point in degrees
            lon1: Longitude of first point in degrees
            lat2: Latitude of second point in degrees
            lon2: Longitude of second point in degrees
            
        Returns:
            Distance in kilometers
        """
        # Convert to radians
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        
        # Haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        # Earth radius in kilometers
        return 6371 * c
    
    @staticmethod
    def calculate_bounding_box(lat: float, lon: float, radius_km: float) -> Dict[str, float]:
        """Calculate bounding box from center point and radius.
        
        Args:
            lat: Center latitude in degrees
            lon: Center longitude in degrees
            radius_km: Radius in kilometers
            
        Returns:
            Dictionary with lamin, lamax, lomin, lomax
        """
        # Approximate conversion: 1 degree latitude ≈ 111 km
        # For longitude, adjust by latitude (cos(lat))
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * abs(cos(radians(lat))))
        
        return {
            "lamin": lat - lat_delta,
            "lamax": lat + lat_delta,
            "lomin": lon - lon_delta,
            "lomax": lon + lon_delta,
        }
    
    def _get_access_token(self) -> Optional[str]:
        """Get OAuth2 access token for authenticated requests.
        
        Returns:
            Access token string, or None if authentication fails
        """
        client_id = self.config.get("client_id", "").strip()
        client_secret = self.config.get("client_secret", "").strip()
        
        # If no credentials, return None (use unauthenticated)
        if not client_id or not client_secret:
            return None
        
        # Check if we have a valid cached token
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at:
                return self._access_token
        
        # Request new token
        try:
            response = requests.post(
                OPENSKY_OAUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=10
            )
            
            if response.status_code != 200:
                logger.warning(f"Failed to get OAuth token: {response.status_code}")
                return None
            
            data = response.json()
            self._access_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)  # Default 1 hour
            
            # Set expiration time (subtract 60 seconds for safety margin)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
            
            logger.debug("Successfully obtained OAuth access token")
            return self._access_token
            
        except Exception as e:
            logger.error(f"Error getting OAuth token: {e}")
            return None
    
    def _get_api_headers(self) -> Dict[str, str]:
        """Get headers for API requests, including auth if available."""
        headers = {}
        token = self._get_access_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers
    
    def _parse_state_vector(self, state_vector: List[Any]) -> Optional[Dict[str, Any]]:
        """Parse a single state vector from OpenSky API.
        
        Args:
            state_vector: Array of state vector values from API
            
        Returns:
            Parsed aircraft data dictionary, or None if invalid
        """
        try:
            if not state_vector or len(state_vector) < 17:
                return None
            
            # Extract fields using indices
            icao24 = state_vector[STATE_VECTOR_INDICES["icao24"]]
            callsign_raw = state_vector[STATE_VECTOR_INDICES["callsign"]]
            latitude = state_vector[STATE_VECTOR_INDICES["latitude"]]
            longitude = state_vector[STATE_VECTOR_INDICES["longitude"]]
            baro_altitude = state_vector[STATE_VECTOR_INDICES["baro_altitude"]]
            geo_altitude = state_vector[STATE_VECTOR_INDICES["geo_altitude"]]
            velocity = state_vector[STATE_VECTOR_INDICES["velocity"]]
            squawk_raw = state_vector[STATE_VECTOR_INDICES["squawk"]]
            on_ground = state_vector[STATE_VECTOR_INDICES["on_ground"]]
            
            # Skip aircraft on ground
            if on_ground:
                return None
            
            # Skip if no position data
            if latitude is None or longitude is None:
                return None
            
            # Get callsign - use ICAO address if missing
            if callsign_raw:
                callsign = str(callsign_raw).strip()
            else:
                # Use ICAO 24-bit address as fallback
                callsign = str(icao24) if icao24 else "UNKNOWN"
            
            # Get altitude - prefer geo_altitude, fallback to baro_altitude
            altitude_m = None
            if geo_altitude is not None:
                altitude_m = float(geo_altitude)
            elif baro_altitude is not None:
                altitude_m = float(baro_altitude)
            
            if altitude_m is None:
                return None  # Skip aircraft without altitude
            
            # Convert altitude from meters to feet
            altitude_ft = int(altitude_m * 3.28084)
            
            # Get velocity (ground speed) in m/s, convert to knots
            if velocity is None:
                return None  # Skip aircraft without velocity
            
            velocity_ms = float(velocity)
            ground_speed_knots = int(velocity_ms * 1.94384)
            
            # Get squawk code
            # Squawk can be None, empty string, 0, or a valid 4-digit code
            if squawk_raw is not None and squawk_raw != "":
                try:
                    squawk_int = int(float(squawk_raw))  # Handle string numbers
                    if squawk_int == 0:
                        # 0 means no squawk code assigned
                        squawk = "----"
                    else:
                        squawk = str(squawk_int).zfill(4)
                except (ValueError, TypeError):
                    squawk = "----"
            else:
                squawk = "----"
            
            # Format display line
            formatted = self._format_aircraft_line(callsign, altitude_ft, ground_speed_knots, squawk)
            
            return {
                "icao24": str(icao24) if icao24 else "",
                "call_sign": callsign,
                "altitude": altitude_ft,
                "ground_speed": ground_speed_knots,
                "squawk": squawk,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "formatted": formatted,
            }
            
        except (ValueError, TypeError, IndexError) as e:
            logger.debug(f"Error parsing state vector: {e}")
            return None
    
    def _align_formatting(self, aircraft_list: List[Dict]) -> Tuple[List[Dict], str]:
        """Align formatting across all aircraft for consistent column alignment.
        
        Calculates maximum widths for each field across all aircraft,
        then applies consistent padding to ensure columns align properly.
        Also generates aligned headers string.
        
        Args:
            aircraft_list: List of aircraft dictionaries
            
        Returns:
            Tuple of (aligned aircraft list, headers string)
        """
        if not aircraft_list:
            return aircraft_list, "CALLSGN ALT GS SQWK"
        
        # Calculate max widths for each field
        max_call_sign_width = 0
        max_altitude_width = 0
        max_speed_width = 0
        max_squawk_width = 0
        
        for aircraft in aircraft_list:
            call_sign = str(aircraft.get("call_sign", ""))
            altitude = str(aircraft.get("altitude", 0))
            ground_speed = str(aircraft.get("ground_speed", 0))
            squawk = str(aircraft.get("squawk", "----"))
            
            max_call_sign_width = max(max_call_sign_width, len(call_sign))
            max_altitude_width = max(max_altitude_width, len(altitude))
            max_speed_width = max(max_speed_width, len(ground_speed))
            max_squawk_width = max(max_squawk_width, len(squawk))
        
        # Cap call sign at 8 chars, ensure minimum widths for alignment
        max_call_sign_width = min(max_call_sign_width, 8)
        max_altitude_width = max(max_altitude_width, 5)  # At least 5 for large altitudes
        max_speed_width = max(max_speed_width, 3)  # At least 3 for speeds
        max_squawk_width = max(max_squawk_width, 4)  # Squawk is always 4
        
        # Generate aligned headers
        callsign_header = "CALLSGN".ljust(max_call_sign_width)
        altitude_header = "ALT".rjust(max_altitude_width)
        speed_header = "GS".rjust(max_speed_width)
        squawk_header = "SQWK".rjust(max_squawk_width)
        headers = f"{callsign_header} {altitude_header} {speed_header} {squawk_header}"
        headers = headers[:22]  # Ensure max 22 chars (board width)
        
        # Apply aligned formatting to all aircraft
        for aircraft in aircraft_list:
            call_sign = str(aircraft.get("call_sign", ""))[:max_call_sign_width]
            altitude = aircraft.get("altitude", 0)
            ground_speed = aircraft.get("ground_speed", 0)
            squawk = str(aircraft.get("squawk", "----"))[:4]
            
            # Format with calculated widths
            call_sign_display = call_sign.ljust(max_call_sign_width)
            altitude_str = str(altitude).rjust(max_altitude_width)
            speed_str = str(ground_speed).rjust(max_speed_width)
            squawk_str = squawk.rjust(max_squawk_width)
            
            # Combine: "CALLSGN  ALT   GS  SQWK"
            formatted = f"{call_sign_display} {altitude_str} {speed_str} {squawk_str}"
            
            # Ensure max 22 chars (board width)
            aircraft["formatted"] = formatted[:22]
        
        return aircraft_list, headers
    
    @staticmethod
    def _format_aircraft_line(call_sign: str, altitude: int, ground_speed: int, squawk: str) -> str:
        """Format aircraft data for display line (legacy method, used before alignment).
        
        Format: CALLSGN  ALT   GS  SQWK
        Example: ITY630   40000 393 2513
        
        Args:
            call_sign: Aircraft call sign (max 8 chars)
            altitude: Altitude in feet
            ground_speed: Ground speed in knots
            squawk: Squawk code (4 chars)
            
        Returns:
            Formatted string (max 22 chars)
        """
        # Truncate and pad call sign to 8 chars (left-aligned)
        call_sign_display = call_sign[:8].ljust(8)
        
        # Format altitude (right-aligned, 5-6 digits)
        altitude_str = str(altitude).rjust(6)
        
        # Format ground speed (right-aligned, 3-4 digits)
        speed_str = str(ground_speed).rjust(4)
        
        # Format squawk (right-aligned, 4 chars)
        squawk_str = squawk[:4].rjust(4)
        
        # Combine: "CALLSGN  ALT   GS  SQWK"
        formatted = f"{call_sign_display} {altitude_str} {speed_str} {squawk_str}"
        
        # Ensure max 22 chars
        return formatted[:22]
    
    def fetch_data(self) -> PluginResult:
        """Fetch nearby aircraft data from OpenSky API."""
        lat = self.config.get("latitude")
        lon = self.config.get("longitude")
        radius_km = self.config.get("radius_km", 50)
        max_aircraft = self.config.get("max_aircraft", 4)
        refresh_seconds = self.config.get("refresh_seconds", 120)
        
        if lat is None or lon is None:
            return PluginResult(
                available=False,
                error="Latitude and longitude are required"
            )
        
        # Check cache first
        if self._cache and self._cache.get("aircraft"):
            last_updated = self._cache.get("last_updated", "")
            if last_updated:
                try:
                    cache_time = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                    age_seconds = (datetime.now(cache_time.tzinfo) - cache_time).total_seconds()
                    if age_seconds < refresh_seconds:
                        logger.debug(f"Using cached data (age: {age_seconds:.0f}s < {refresh_seconds}s)")
                        return PluginResult(available=True, data=self._cache)
                except Exception:
                    pass  # If cache time parsing fails, continue to fetch
        
        try:
            # Calculate bounding box
            bbox = self.calculate_bounding_box(lat, lon, radius_km)
            
            # Fetch state vectors from OpenSky API
            headers = self._get_api_headers()
            params = {
                "lamin": bbox["lamin"],
                "lamax": bbox["lamax"],
                "lomin": bbox["lomin"],
                "lomax": bbox["lomax"],
            }
            
            response = requests.get(OPENSKY_STATES_URL, params=params, headers=headers, timeout=10)
            
            # Handle rate limiting
            if response.status_code == 429:
                logger.warning("OpenSky API rate limit exceeded, using cached data if available")
                if self._cache and self._cache.get("aircraft"):
                    return PluginResult(available=True, data=self._cache)
                return PluginResult(
                    available=False,
                    error="API rate limit exceeded. Please wait or use authentication."
                )
            
            if response.status_code != 200:
                logger.error(f"OpenSky API error: {response.status_code}")
                if self._cache and self._cache.get("aircraft"):
                    return PluginResult(available=True, data=self._cache)
                return PluginResult(
                    available=False,
                    error=f"API error: {response.status_code}"
                )
            
            data = response.json()
            states = data.get("states")
            
            if not states:
                # No aircraft found, return empty result
                return PluginResult(
                    available=True,
                    data={
                        "aircraft_count": 0,
                        "aircraft": [],
                        "call_sign": "",
                        "altitude": 0,
                        "ground_speed": 0,
                        "squawk": "----",
                        "formatted": "NO AIRCRAFT NEARBY",
                        "headers": "CALLSGN ALT GS SQWK",
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    }
                )
            
            # Parse state vectors and filter by distance
            nearby_aircraft = []
            for state_vector in states:
                aircraft = self._parse_state_vector(state_vector)
                if aircraft:
                    # Calculate actual distance
                    distance_km = self.haversine_distance(
                        lat, lon,
                        aircraft["latitude"], aircraft["longitude"]
                    )
                    
                    if distance_km <= radius_km:
                        aircraft["distance_km"] = round(distance_km, 1)
                        nearby_aircraft.append(aircraft)
            
            # Sort by distance and limit
            nearby_aircraft.sort(key=lambda a: a.get("distance_km", float('inf')))
            nearby_aircraft = nearby_aircraft[:max_aircraft]
            
            # Align formatting across all aircraft and generate headers
            aligned_headers = "CALLSGN ALT GS SQWK"  # Default headers
            if nearby_aircraft:
                nearby_aircraft, aligned_headers = self._align_formatting(nearby_aircraft)
            
            if not nearby_aircraft:
                return PluginResult(
                    available=True,
                    data={
                        "aircraft_count": 0,
                        "aircraft": [],
                        "call_sign": "",
                        "altitude": 0,
                        "ground_speed": 0,
                        "squawk": "----",
                        "formatted": "NO AIRCRAFT NEARBY",
                        "headers": "CALLSGN ALT GS SQWK",
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    }
                )
            
            # Primary aircraft (closest)
            primary = nearby_aircraft[0]
            
            result_data = {
                # Primary aircraft fields
                "call_sign": primary["call_sign"],
                "altitude": primary["altitude"],
                "ground_speed": primary["ground_speed"],
                "squawk": primary["squawk"],
                "formatted": primary["formatted"],
                # Headers aligned to match aircraft data columns
                "headers": aligned_headers,
                # Aggregate
                "aircraft_count": len(nearby_aircraft),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                # Array of all aircraft
                "aircraft": nearby_aircraft,
            }
            
            self._cache = result_data
            return PluginResult(available=True, data=result_data)
            
        except requests.exceptions.RequestException as e:
            logger.exception("Error fetching aircraft data")
            if self._cache and self._cache.get("aircraft"):
                return PluginResult(available=True, data=self._cache)
            return PluginResult(available=False, error=f"Network error: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error fetching aircraft data")
            if self._cache and self._cache.get("aircraft"):
                return PluginResult(available=True, data=self._cache)
            return PluginResult(available=False, error=str(e))
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted aircraft display matching screenshot format."""
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None
        
        data = self._cache
        if not data:
            return None
        
        aircraft = data.get("aircraft", [])
        lines = [
            "NEARBY AIRCRAFT".center(22),
            "CALLSGN  ALT   GS  SQWK",
        ]
        
        for ac in aircraft[:4]:
            lines.append(ac.get("formatted", "")[:22])
        
        while len(lines) < 6:
            lines.append("")
        
        return lines[:6]


# Export the plugin class
Plugin = NearbyAircraftPlugin
