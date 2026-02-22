"""Surf data source using Open-Meteo Marine API.

Fetches marine/surf conditions for Ocean Beach, San Francisco.
"""

import logging
import requests
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Ocean Beach, San Francisco coordinates
OCEAN_BEACH_LAT = 37.7599
OCEAN_BEACH_LON = -122.5121


class SurfSource:
    """Fetches surf/marine conditions from Open-Meteo Marine API."""
    
    # Surf quality thresholds
    EXCELLENT_PERIOD_THRESHOLD = 12  # seconds
    EXCELLENT_WIND_THRESHOLD = 12  # mph
    
    # Additional thresholds for quality ratings
    GOOD_PERIOD_THRESHOLD = 10  # seconds
    GOOD_WIND_THRESHOLD = 15  # mph
    
    def __init__(self, latitude: float = OCEAN_BEACH_LAT, longitude: float = OCEAN_BEACH_LON):
        """
        Initialize surf source.
        
        Args:
            latitude: Location latitude (default: Ocean Beach, SF)
            longitude: Location longitude (default: Ocean Beach, SF)
        """
        self.latitude = latitude
        self.longitude = longitude
    
    def fetch_surf_data(self) -> Optional[Dict[str, any]]:
        """
        Fetch current surf conditions from Open-Meteo Marine API.
        
        Returns:
            Dictionary with surf data including:
            - wave_height: Maximum wave height in feet
            - wave_height_m: Maximum wave height in meters
            - swell_period: Swell wave period in seconds
            - wind_speed: Wind speed in mph
            - wind_speed_kmh: Wind speed in km/h
            - wind_direction: Wind direction in degrees
            - wind_direction_cardinal: Wind direction (N, NE, E, etc.)
            - quality: Surf quality rating (EXCELLENT, GOOD, FAIR, POOR)
            - quality_color: Color indicator (GREEN, YELLOW, ORANGE, RED)
            - formatted_message: Pre-formatted display message
        """
        url = "https://marine-api.open-meteo.com/v1/marine"
        
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current": "wave_height,swell_wave_period,wind_wave_direction",
            "hourly": "wave_height,swell_wave_period,swell_wave_height",
            "daily": "wave_height_max,swell_wave_period_max",
            "wind_speed_unit": "mph",
            "timezone": "America/Los_Angeles",
            "forecast_days": 1
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            marine_data = response.json()
            
            # Also fetch wind data from the regular weather API (marine API doesn't include wind)
            wind_data = self._fetch_wind_data()
            
            # Get current/daily values
            current = marine_data.get("current", {})
            daily = marine_data.get("daily", {})
            
            # Extract wave height (use daily max if available, otherwise current)
            if daily.get("wave_height_max"):
                wave_height_m = daily["wave_height_max"][0] or 0
            elif current.get("wave_height"):
                wave_height_m = current["wave_height"] or 0
            else:
                wave_height_m = 0
            
            # Convert meters to feet (1 meter = 3.28084 feet)
            wave_height_ft = round(wave_height_m * 3.28084, 1)
            
            # Extract swell period (use daily max if available, otherwise current)
            if daily.get("swell_wave_period_max"):
                swell_period = daily["swell_wave_period_max"][0] or 0
            elif current.get("swell_wave_period"):
                swell_period = current["swell_wave_period"] or 0
            else:
                swell_period = 0
            
            # Get wind data
            wind_speed_mph = wind_data.get("wind_speed_mph", 0) if wind_data else 0
            wind_speed_kmh = wind_data.get("wind_speed_kmh", 0) if wind_data else 0
            wind_direction = wind_data.get("wind_direction", 0) if wind_data else 0
            
            # Calculate surf quality
            quality, quality_color = self._calculate_surf_quality(swell_period, wind_speed_mph)
            
            # Get cardinal direction
            wind_direction_cardinal = self._degrees_to_cardinal(wind_direction)
            
            # Format message
            formatted_message = self._format_message(wave_height_ft, swell_period)
            
            return {
                "wave_height": wave_height_ft,
                "wave_height_m": round(wave_height_m, 2),
                "swell_period": round(swell_period, 1),
                "wind_speed": round(wind_speed_mph, 1),
                "wind_speed_kmh": round(wind_speed_kmh, 1),
                "wind_direction": wind_direction,
                "wind_direction_cardinal": wind_direction_cardinal,
                "quality": quality,
                "quality_color": quality_color,
                "formatted_message": formatted_message,
                "location": "Ocean Beach, SF",
                "latitude": self.latitude,
                "longitude": self.longitude
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch surf data from Open-Meteo: {e}")
            return None
        except (KeyError, ValueError, IndexError, TypeError) as e:
            logger.error(f"Unexpected response format from Open-Meteo Marine API: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching surf data: {e}")
            return None
    
    def _fetch_wind_data(self) -> Optional[Dict[str, any]]:
        """
        Fetch wind data from Open-Meteo Weather API.
        
        The Marine API doesn't include wind data, so we need to fetch it separately.
        
        Returns:
            Dictionary with wind speed and direction, or None if failed
        """
        url = "https://api.open-meteo.com/v1/forecast"
        
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current": "wind_speed_10m,wind_direction_10m",
            "wind_speed_unit": "mph",
            "timezone": "America/Los_Angeles"
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            current = data.get("current", {})
            wind_speed_mph = current.get("wind_speed_10m", 0)
            wind_direction = current.get("wind_direction_10m", 0)
            
            # Also get km/h for reference
            wind_speed_kmh = wind_speed_mph * 1.60934
            
            return {
                "wind_speed_mph": wind_speed_mph,
                "wind_speed_kmh": wind_speed_kmh,
                "wind_direction": wind_direction
            }
            
        except Exception as e:
            logger.warning(f"Failed to fetch wind data: {e}")
            return None
    
    @classmethod
    def _calculate_surf_quality(cls, swell_period: float, wind_speed: float) -> tuple[str, str]:
        """
        Calculate surf quality based on swell period and wind speed.
        
        Logic:
        - EXCELLENT (GREEN): swell_period > 12s AND wind_speed < 12mph
        - GOOD (YELLOW): swell_period > 10s AND wind_speed < 15mph
        - FAIR (ORANGE): swell_period > 8s OR wind_speed < 20mph
        - POOR (RED): Otherwise
        
        Args:
            swell_period: Swell wave period in seconds
            wind_speed: Wind speed in mph
        
        Returns:
            Tuple of (quality, color)
        """
        # EXCELLENT: Long period swell with light winds
        if swell_period > cls.EXCELLENT_PERIOD_THRESHOLD and wind_speed < cls.EXCELLENT_WIND_THRESHOLD:
            return ("EXCELLENT", "GREEN")
        
        # GOOD: Decent period swell with moderate winds
        if swell_period > cls.GOOD_PERIOD_THRESHOLD and wind_speed < cls.GOOD_WIND_THRESHOLD:
            return ("GOOD", "YELLOW")
        
        # FAIR: Either decent swell OR manageable winds
        if swell_period > 8 or wind_speed < 20:
            return ("FAIR", "ORANGE")
        
        # POOR: Short period swell with strong winds
        return ("POOR", "RED")
    
    @staticmethod
    def _degrees_to_cardinal(degrees: float) -> str:
        """
        Convert wind direction in degrees to cardinal direction.
        
        Args:
            degrees: Wind direction in degrees (0-360)
        
        Returns:
            Cardinal direction string (N, NE, E, SE, S, SW, W, NW)
        """
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        # Normalize degrees and calculate index
        index = round(degrees / 45) % 8
        return directions[index]
    
    @staticmethod
    def _format_message(wave_height: float, swell_period: float) -> str:
        """
        Format surf message for display.
        
        Args:
            wave_height: Wave height in feet
            swell_period: Swell period in seconds
        
        Returns:
            Formatted message: "OB SURF: [Height]ft @ [Period]s"
        """
        # Round period to integer for cleaner display
        period_display = int(round(swell_period)) if swell_period else 0
        return f"OB SURF: {wave_height}ft @ {period_display}s"


def get_surf_source() -> Optional[SurfSource]:
    """
    Get configured surf source instance.
    
    Note: Open-Meteo is a free API that doesn't require an API key,
    so this will always return a valid source.
    
    Returns:
        SurfSource instance
    """
    return SurfSource()

