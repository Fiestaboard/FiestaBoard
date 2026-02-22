"""Air Quality and Fog data source using PurpleAir and OpenWeatherMap."""

import logging
import math
import requests
from typing import Optional, Dict, Tuple

from ..config import Config

logger = logging.getLogger(__name__)

# Default location: San Francisco
DEFAULT_LAT = 37.7749
DEFAULT_LON = -122.4194


class AirFogSource:
    """Fetches air quality from PurpleAir and visibility/fog data from OpenWeatherMap."""
    
    # AQI breakpoints for PM2.5 (US EPA standard)
    AQI_BREAKPOINTS = [
        # (PM2.5 low, PM2.5 high, AQI low, AQI high, category, color)
        (0.0, 12.0, 0, 50, "GOOD", "GREEN"),
        (12.1, 35.4, 51, 100, "MODERATE", "YELLOW"),
        (35.5, 55.4, 101, 150, "UNHEALTHY_SENSITIVE", "ORANGE"),
        (55.5, 150.4, 151, 200, "UNHEALTHY", "RED"),
        (150.5, 250.4, 201, 300, "VERY_UNHEALTHY", "PURPLE"),
        (250.5, 500.4, 301, 500, "HAZARDOUS", "MAROON"),
    ]
    
    # Fog trigger thresholds
    VISIBILITY_FOG_THRESHOLD_M = 1600  # meters
    HUMIDITY_FOG_THRESHOLD = 95  # percent
    TEMP_FOG_THRESHOLD_F = 60  # Fahrenheit
    
    # AQI fire trigger threshold
    AQI_FIRE_THRESHOLD = 100  # Unhealthy
    
    def __init__(
        self,
        purpleair_api_key: str = "",
        openweathermap_api_key: str = "",
        latitude: float = DEFAULT_LAT,
        longitude: float = DEFAULT_LON,
        purpleair_sensor_id: Optional[str] = None
    ):
        """
        Initialize air/fog source.
        
        Args:
            purpleair_api_key: PurpleAir API key (for direct sensor access)
            openweathermap_api_key: OpenWeatherMap API key
            latitude: Latitude for location-based queries
            longitude: Longitude for location-based queries
            purpleair_sensor_id: Optional specific PurpleAir sensor ID
        """
        self.purpleair_api_key = purpleair_api_key
        self.openweathermap_api_key = openweathermap_api_key
        self.latitude = latitude
        self.longitude = longitude
        self.purpleair_sensor_id = purpleair_sensor_id
    
    @staticmethod
    def calculate_dew_point(temp_f: float, humidity: float) -> float:
        """
        Calculate dew point using Magnus formula.
        
        Args:
            temp_f: Temperature in Fahrenheit
            humidity: Relative humidity (0-100)
            
        Returns:
            Dew point in Fahrenheit
        """
        # Convert to Celsius for calculation
        temp_c = (temp_f - 32) * 5 / 9
        
        # Magnus formula constants
        a = 17.27
        b = 237.7
        
        # Calculate alpha
        alpha = (a * temp_c / (b + temp_c)) + math.log(humidity / 100)
        
        # Calculate dew point in Celsius
        dew_point_c = (b * alpha) / (a - alpha)
        
        # Convert back to Fahrenheit
        dew_point_f = (dew_point_c * 9 / 5) + 32
        
        return round(dew_point_f, 1)
    
    @staticmethod
    def calculate_aqi_from_pm25(pm25: float) -> Tuple[int, str, str]:
        """
        Calculate AQI from PM2.5 concentration using US EPA formula.
        
        Args:
            pm25: PM2.5 concentration in µg/m³
            
        Returns:
            Tuple of (AQI value, category, color)
        """
        if pm25 < 0:
            pm25 = 0
        
        for bp_low, bp_high, aqi_low, aqi_high, category, color in AirFogSource.AQI_BREAKPOINTS:
            if bp_low <= pm25 <= bp_high:
                # Linear interpolation
                aqi = round(
                    ((aqi_high - aqi_low) / (bp_high - bp_low)) * (pm25 - bp_low) + aqi_low
                )
                return aqi, category, color
        
        # If above all breakpoints, return hazardous
        return 500, "HAZARDOUS", "MAROON"
    
    @staticmethod
    def determine_fog_status(
        visibility_m: float,
        humidity: float,
        temp_f: float
    ) -> Tuple[bool, str, str]:
        """
        Determine fog status based on visibility, humidity, and temperature.
        
        Fog Trigger: IF visibility < 1600m OR (humidity > 95% AND temp < 60F)
        
        Args:
            visibility_m: Visibility in meters
            humidity: Relative humidity (0-100)
            temp_f: Temperature in Fahrenheit
            
        Returns:
            Tuple of (is_foggy, status_message, color)
        """
        # Check visibility-based fog
        if visibility_m < AirFogSource.VISIBILITY_FOG_THRESHOLD_M:
            return True, "FOG: HEAVY", "ORANGE"
        
        # Check humidity + temperature fog condition
        if humidity > AirFogSource.HUMIDITY_FOG_THRESHOLD and temp_f < AirFogSource.TEMP_FOG_THRESHOLD_F:
            return True, "FOG: HEAVY", "ORANGE"
        
        # Check near-fog conditions
        if visibility_m < 3000:
            return False, "FOG: LIGHT", "YELLOW"
        
        return False, "CLEAR", "GREEN"
    
    @staticmethod
    def determine_air_status(aqi: int) -> Tuple[str, str]:
        """
        Determine air quality alert status.
        
        Fire Trigger: IF aqi > 100 -> "AIR: UNHEALTHY" (ORANGE)
        
        Args:
            aqi: Air Quality Index value
            
        Returns:
            Tuple of (status_message, color)
        """
        if aqi > 300:
            return "AIR: HAZARDOUS", "MAROON"
        elif aqi > 200:
            return "AIR: VERY UNHEALTHY", "PURPLE"
        elif aqi > 150:
            return "AIR: UNHEALTHY", "RED"
        elif aqi > AirFogSource.AQI_FIRE_THRESHOLD:
            return "AIR: UNHEALTHY", "ORANGE"
        elif aqi > 50:
            return "AIR: MODERATE", "YELLOW"
        else:
            return "AIR: GOOD", "GREEN"
    
    def fetch_purpleair_data(self) -> Optional[Dict[str, any]]:
        """
        Fetch air quality data from PurpleAir.
        
        Returns:
            Dictionary with PM2.5 and AQI data, or None if failed
        """
        if not self.purpleair_api_key:
            logger.warning("PurpleAir API key not configured")
            return None
        
        try:
            if self.purpleair_sensor_id:
                # Fetch specific sensor
                url = f"https://api.purpleair.com/v1/sensors/{self.purpleair_sensor_id}"
                params = {"fields": "pm2.5_10minute,pm2.5_30minute,pm2.5_60minute,humidity,temperature"}
            else:
                # Fetch sensors near location
                url = "https://api.purpleair.com/v1/sensors"
                params = {
                    "fields": "pm2.5_10minute,pm2.5_30minute,pm2.5_60minute,humidity,temperature",
                    "location_type": "0",  # Outside
                    "max_age": 3600,  # Data within last hour
                    "nwlat": self.latitude + 0.05,
                    "nwlng": self.longitude - 0.05,
                    "selat": self.latitude - 0.05,
                    "selng": self.longitude + 0.05,
                }
            
            headers = {"X-API-Key": self.purpleair_api_key}
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if self.purpleair_sensor_id:
                sensor_data = data.get("sensor", {})
                pm25 = sensor_data.get("pm2.5_10minute", 0)
                humidity = sensor_data.get("humidity")
                temp_f = sensor_data.get("temperature")
            else:
                # Average nearby sensors
                sensors = data.get("data", [])
                if not sensors:
                    logger.warning("No PurpleAir sensors found nearby")
                    return None
                
                # Fields order: pm2.5_10minute, pm2.5_30minute, pm2.5_60minute, humidity, temperature
                pm25_values = [s[0] for s in sensors if s[0] is not None]
                humidity_values = [s[3] for s in sensors if s[3] is not None]
                temp_values = [s[4] for s in sensors if s[4] is not None]
                
                pm25 = sum(pm25_values) / len(pm25_values) if pm25_values else 0
                humidity = sum(humidity_values) / len(humidity_values) if humidity_values else None
                temp_f = sum(temp_values) / len(temp_values) if temp_values else None
            
            aqi, category, color = self.calculate_aqi_from_pm25(pm25)
            
            return {
                "pm2_5": round(pm25, 1),
                "aqi": aqi,
                "aqi_category": category,
                "aqi_color": color,
                "humidity": round(humidity, 1) if humidity else None,
                "temperature_f": round(temp_f, 1) if temp_f else None,
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch data from PurpleAir: {e}")
            return None
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Unexpected response format from PurpleAir: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching PurpleAir data: {e}")
            return None
    
    def fetch_openweathermap_data(self) -> Optional[Dict[str, any]]:
        """
        Fetch visibility and weather data from OpenWeatherMap.
        
        Returns:
            Dictionary with visibility and weather data, or None if failed
        """
        if not self.openweathermap_api_key:
            logger.warning("OpenWeatherMap API key not configured")
            return None
        
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": self.latitude,
            "lon": self.longitude,
            "appid": self.openweathermap_api_key,
            "units": "imperial"
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            visibility_m = data.get("visibility", 10000)
            humidity = data["main"]["humidity"]
            temp_f = data["main"]["temp"]
            
            # Calculate dew point
            dew_point = self.calculate_dew_point(temp_f, humidity)
            
            return {
                "visibility_m": visibility_m,
                "humidity": humidity,
                "temperature_f": round(temp_f, 1),
                "dew_point_f": dew_point,
                "condition": data["weather"][0]["main"] if data.get("weather") else "Unknown",
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch data from OpenWeatherMap: {e}")
            return None
        except KeyError as e:
            logger.error(f"Unexpected response format from OpenWeatherMap: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching OpenWeatherMap data: {e}")
            return None
    
    def fetch_air_fog_data(self) -> Optional[Dict[str, any]]:
        """
        Fetch combined air quality and fog data.
        
        Returns:
            Dictionary with all air/fog data, or None if all sources failed
        """
        # Fetch data from both sources
        purpleair_data = self.fetch_purpleair_data()
        owm_data = self.fetch_openweathermap_data()
        
        if not purpleair_data and not owm_data:
            logger.error("Failed to fetch data from both PurpleAir and OpenWeatherMap")
            return None
        
        result = {
            "pm2_5_aqi": None,
            "pm2_5": None,
            "visibility_m": None,
            "humidity": None,
            "dew_point_f": None,
            "temperature_f": None,
            "fog_status": "UNKNOWN",
            "fog_color": "YELLOW",
            "is_foggy": False,
            "air_status": "UNKNOWN",
            "air_color": "YELLOW",
            "alert_message": None,
        }
        
        # Merge PurpleAir data
        if purpleair_data:
            result["pm2_5_aqi"] = purpleair_data["aqi"]
            result["pm2_5"] = purpleair_data["pm2_5"]
            air_status, air_color = self.determine_air_status(purpleair_data["aqi"])
            result["air_status"] = air_status
            result["air_color"] = air_color
            
            # Use PurpleAir humidity/temp as fallback
            if purpleair_data.get("humidity"):
                result["humidity"] = purpleair_data["humidity"]
            if purpleair_data.get("temperature_f"):
                result["temperature_f"] = purpleair_data["temperature_f"]
        
        # Merge OpenWeatherMap data (preferred for visibility/fog)
        if owm_data:
            result["visibility_m"] = owm_data["visibility_m"]
            result["humidity"] = owm_data["humidity"]  # Prefer OWM for accuracy
            result["temperature_f"] = owm_data["temperature_f"]
            result["dew_point_f"] = owm_data["dew_point_f"]
            
            # Determine fog status
            is_foggy, fog_status, fog_color = self.determine_fog_status(
                owm_data["visibility_m"],
                owm_data["humidity"],
                owm_data["temperature_f"]
            )
            result["is_foggy"] = is_foggy
            result["fog_status"] = fog_status
            result["fog_color"] = fog_color
        
        # Calculate dew point if we have data but it wasn't from OWM
        if result["humidity"] and result["temperature_f"] and not result["dew_point_f"]:
            result["dew_point_f"] = self.calculate_dew_point(
                result["temperature_f"],
                result["humidity"]
            )
        
        # Determine primary alert message
        result["alert_message"] = self._determine_alert_message(result)
        result["formatted_message"] = self._format_message(result)
        
        return result
    
    def _determine_alert_message(self, data: Dict) -> Optional[str]:
        """Determine the primary alert message based on conditions."""
        alerts = []
        
        # Check fog condition (higher priority)
        if data.get("is_foggy"):
            alerts.append(data["fog_status"])
        
        # Check air quality (fire smoke)
        if data.get("pm2_5_aqi") and data["pm2_5_aqi"] > self.AQI_FIRE_THRESHOLD:
            alerts.append(data["air_status"])
        
        return " | ".join(alerts) if alerts else None
    
    def _format_message(self, data: Dict) -> str:
        """Format data for board display."""
        parts = []
        
        if data.get("pm2_5_aqi"):
            parts.append(f"AQI:{data['pm2_5_aqi']}")
        
        if data.get("visibility_m"):
            vis_mi = round(data["visibility_m"] / 1609.34, 1)
            parts.append(f"VIS:{vis_mi}mi")
        
        if data.get("humidity"):
            parts.append(f"HUM:{data['humidity']}%")
        
        return " ".join(parts) if parts else "NO DATA"


def get_air_fog_source() -> Optional[AirFogSource]:
    """Get configured air/fog source instance."""
    purpleair_key = Config.PURPLEAIR_API_KEY if hasattr(Config, 'PURPLEAIR_API_KEY') else ""
    owm_key = Config.OPENWEATHERMAP_API_KEY if hasattr(Config, 'OPENWEATHERMAP_API_KEY') else ""
    
    if not purpleair_key and not owm_key:
        logger.warning("Neither PurpleAir nor OpenWeatherMap API keys configured")
        return None
    
    latitude = Config.AIR_FOG_LATITUDE if hasattr(Config, 'AIR_FOG_LATITUDE') else DEFAULT_LAT
    longitude = Config.AIR_FOG_LONGITUDE if hasattr(Config, 'AIR_FOG_LONGITUDE') else DEFAULT_LON
    sensor_id = Config.PURPLEAIR_SENSOR_ID if hasattr(Config, 'PURPLEAIR_SENSOR_ID') else None
    
    return AirFogSource(
        purpleair_api_key=purpleair_key,
        openweathermap_api_key=owm_key,
        latitude=latitude,
        longitude=longitude,
        purpleair_sensor_id=sensor_id
    )

