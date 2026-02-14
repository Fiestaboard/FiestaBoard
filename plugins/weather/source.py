"""Weather data fetching logic.

Supports WeatherAPI.com and OpenWeatherMap providers.
"""

import logging
import requests
import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _uv_to_display_index(uv: Any) -> Optional[int]:
    """Convert API UV value to display index 0-11+.

    Some APIs return UV on a normalized 0-1 scale; others use 0-11+.
    Values in (0, 1] are treated as normalized and scaled to 0-11.
    """
    if uv is None:
        return None
    try:
        v = float(uv)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return 0
    if 0 <= v <= 1:
        # Normalized 0-1 scale: 0 -> 0, 1 -> 11
        return round(v * 11)
    return round(v)


class WeatherSource:
    """Fetches current weather data from weather APIs."""
    
    def __init__(self, provider: str, api_key: str, locations: List[Dict[str, str]]):
        """Initialize weather source.
        
        Args:
            provider: "weatherapi" or "openweathermap"
            api_key: API key for the weather service
            locations: List of location dicts with keys:
                      - location: Location string (city name or lat/lon)
                      - name: Display name (e.g., "HOME", "OFFICE")
        """
        self.provider = provider
        self.api_key = api_key
        self.locations = locations if locations else []
        
        # For backward compatibility
        if self.locations:
            self.location = self.locations[0].get("location", "")
    
    def fetch_current_weather(self) -> Optional[Dict[str, Any]]:
        """Fetch current weather data (returns first location).
        
        Returns:
            Dictionary with weather data for first location, or None if failed
        """
        results = self.fetch_multiple_locations()
        if results and len(results) > 0:
            return results[0]
        return None
    
    def fetch_multiple_locations(self) -> List[Dict[str, Any]]:
        """Fetch weather for all configured locations.
        
        Returns:
            List of dictionaries with weather data for each location
        """
        if not self.locations:
            return []
        
        results = []
        for loc_config in self.locations:
            try:
                data = self._fetch_single_location(
                    location=loc_config.get("location", ""),
                    location_name=loc_config.get("name", "LOCATION")
                )
                if data:
                    results.append(data)
            except Exception as e:
                logger.error(f"Error fetching weather for {loc_config.get('name', 'unknown')}: {e}")
        
        return results
    
    def _fetch_single_location(self, location: str, location_name: str) -> Optional[Dict[str, Any]]:
        """Fetch weather for a single location.
        
        Args:
            location: Location string (city name or lat/lon)
            location_name: Display name for the location
            
        Returns:
            Dictionary with weather data, or None if failed
        """
        if self.provider == "weatherapi":
            return self._fetch_weatherapi_for_location(location, location_name)
        elif self.provider == "openweathermap":
            return self._fetch_openweathermap_for_location(location, location_name)
        else:
            logger.error(f"Unknown weather provider: {self.provider}")
            return None
    
    def _fetch_weatherapi_for_location(self, location: str, location_name: str) -> Optional[Dict[str, Any]]:
        """Fetch weather from WeatherAPI.com for a specific location."""
        # Fetch current weather
        current_url = "http://api.weatherapi.com/v1/current.json"
        current_params = {
            "key": self.api_key,
            "q": location,
            "aqi": "no"
        }
        
        # Fetch forecast (1 day for today's high/low, UV, sunset)
        forecast_url = "http://api.weatherapi.com/v1/forecast.json"
        forecast_params = {
            "key": self.api_key,
            "q": location,
            "days": 1,
            "aqi": "no",
            "alerts": "no"
        }
        
        try:
            # Fetch current weather
            current_response = requests.get(current_url, params=current_params, timeout=10)
            current_response.raise_for_status()
            current_data = current_response.json()
            
            # Build base data from current weather
            # Round temperatures to whole numbers for display
            temp_f = current_data["current"]["temp_f"]
            feels_like_f = current_data["current"]["feelslike_f"]
            
            # Convert to Celsius: C = (F - 32) * 5/9
            temp_c = (temp_f - 32) * 5 / 9 if isinstance(temp_f, (int, float)) else None
            feels_like_c = (feels_like_f - 32) * 5 / 9 if isinstance(feels_like_f, (int, float)) else None
            
            result = {
                "temperature": round(temp_f) if isinstance(temp_f, (int, float)) else temp_f,
                "temperature_c": round(temp_c) if temp_c is not None else None,
                "feels_like": round(feels_like_f) if isinstance(feels_like_f, (int, float)) else feels_like_f,
                "feels_like_c": round(feels_like_c) if feels_like_c is not None else None,
                "condition": current_data["current"]["condition"]["text"],
                "humidity": current_data["current"]["humidity"],
                "wind_mph": current_data["current"]["wind_mph"],
                "wind_speed": current_data["current"]["wind_mph"],  # Alias for template compatibility
                "location": current_data["location"]["name"],
                "location_name": location_name,
                "uv_index": _uv_to_display_index(current_data["current"].get("uv")),
            }
            
            # Try to fetch forecast data (non-blocking if it fails)
            try:
                forecast_response = requests.get(forecast_url, params=forecast_params, timeout=10)
                forecast_response.raise_for_status()
                forecast_data = forecast_response.json()
                
                # Extract forecast data for today
                if "forecast" in forecast_data and "forecastday" in forecast_data["forecast"]:
                    if len(forecast_data["forecast"]["forecastday"]) > 0:
                        today = forecast_data["forecast"]["forecastday"][0]
                        day_data = today.get("day", {})
                        astro_data = today.get("astro", {})
                        
                        # High and low temperatures (round to whole numbers)
                        high_temp = day_data.get("maxtemp_f")
                        low_temp = day_data.get("mintemp_f")
                        result["high_temp"] = round(high_temp) if isinstance(high_temp, (int, float)) else high_temp
                        result["low_temp"] = round(low_temp) if isinstance(low_temp, (int, float)) else low_temp
                        
                        # Convert high/low to Celsius
                        if isinstance(high_temp, (int, float)):
                            result["high_temp_c"] = round((high_temp - 32) * 5 / 9)
                        if isinstance(low_temp, (int, float)):
                            result["low_temp_c"] = round((low_temp - 32) * 5 / 9)
                        
                        # UV index (use daily max from forecast, or keep current if higher)
                        forecast_uv = day_data.get("uv")
                        if forecast_uv is not None:
                            forecast_uv_index = _uv_to_display_index(forecast_uv)
                            if forecast_uv_index is not None and (
                                result["uv_index"] is None or forecast_uv_index > result["uv_index"]
                            ):
                                result["uv_index"] = forecast_uv_index
                        
                        # Precipitation chance
                        result["precipitation_chance"] = day_data.get("daily_chance_of_rain", 0)
                        
                        # Sunset time
                        sunset_str = astro_data.get("sunset", "")
                        if sunset_str:
                            result["sunset"] = self._format_sunset_time(sunset_str)
            except Exception as e:
                logger.warning(f"Failed to fetch forecast data from WeatherAPI for {location_name}: {e}")
                # Continue with current weather data only
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch weather from WeatherAPI for {location_name}: {e}")
            return None
        except KeyError as e:
            logger.error(f"Unexpected response format from WeatherAPI for {location_name}: {e}")
            return None
    
    def _format_sunset_time(self, sunset_str: str) -> str:
        """Format sunset time from API format to '8:36 PM' format.
        
        Args:
            sunset_str: Time string from API (e.g., "05:34 PM" or "17:34")
            
        Returns:
            Formatted time string like "8:36 PM" (hour without leading zero)
        """
        try:
            # Handle formats like "05:34 PM" or "5:34 PM"
            if "AM" in sunset_str.upper() or "PM" in sunset_str.upper():
                # Already has AM/PM, just remove leading zero from hour
                match = re.match(r'0?(\d+):(\d+)\s*(AM|PM)', sunset_str, re.IGNORECASE)
                if match:
                    hour = int(match.group(1))
                    minute = match.group(2)
                    period = match.group(3).upper()
                    return f"{hour}:{minute} {period}"
            
            # Handle 24-hour format
            match = re.match(r'(\d+):(\d+)', sunset_str)
            if match:
                hour = int(match.group(1))
                minute = match.group(2)
                
                if hour == 0:
                    return f"12:{minute} AM"
                elif hour < 12:
                    return f"{hour}:{minute} AM"
                elif hour == 12:
                    return f"12:{minute} PM"
                else:
                    return f"{hour - 12}:{minute} PM"
        except Exception as e:
            logger.warning(f"Failed to parse sunset time '{sunset_str}': {e}")
        
        # Return original if parsing fails
        return sunset_str
    
    def _fetch_openweathermap_for_location(self, location: str, location_name: str) -> Optional[Dict[str, Any]]:
        """Fetch weather from OpenWeatherMap for a specific location."""
        # Fetch current weather
        current_url = "https://api.openweathermap.org/data/2.5/weather"
        current_params = {
            "q": location,
            "appid": self.api_key,
            "units": "imperial"
        }
        
        try:
            # Fetch current weather
            current_response = requests.get(current_url, params=current_params, timeout=10)
            current_response.raise_for_status()
            current_data = current_response.json()
            
            # Build base data from current weather
            # Round temperatures to whole numbers for display
            # Note: OpenWeatherMap with units=imperial returns Fahrenheit
            temp = current_data["main"]["temp"]
            feels_like = current_data["main"]["feels_like"]
            
            # Convert to Celsius: C = (F - 32) * 5/9
            temp_c = (temp - 32) * 5 / 9 if isinstance(temp, (int, float)) else None
            feels_like_c = (feels_like - 32) * 5 / 9 if isinstance(feels_like, (int, float)) else None
            
            result = {
                "temperature": round(temp) if isinstance(temp, (int, float)) else temp,
                "temperature_c": round(temp_c) if temp_c is not None else None,
                "feels_like": round(feels_like) if isinstance(feels_like, (int, float)) else feels_like,
                "feels_like_c": round(feels_like_c) if feels_like_c is not None else None,
                "condition": current_data["weather"][0]["main"],
                "description": current_data["weather"][0]["description"],
                "humidity": current_data["main"]["humidity"],
                "wind_mph": current_data["wind"]["speed"],
                "wind_speed": current_data["wind"]["speed"],  # Alias for template compatibility
                "location": current_data.get("name", location),
                "location_name": location_name
            }
            
            # Try to fetch forecast data (non-blocking if it fails)
            try:
                forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
                forecast_params = {
                    "q": location,
                    "appid": self.api_key,
                    "units": "imperial",
                    "cnt": 8  # Get next 8 periods (24 hours)
                }
                
                forecast_response = requests.get(forecast_url, params=forecast_params, timeout=10)
                forecast_response.raise_for_status()
                forecast_data = forecast_response.json()
                
                if "list" in forecast_data and len(forecast_data["list"]) > 0:
                    # Find min/max temps from forecast periods (round to whole numbers)
                    temps = [item["main"]["temp"] for item in forecast_data["list"]]
                    high_temp = round(max(temps)) if temps else None
                    low_temp = round(min(temps)) if temps else None
                    result["high_temp"] = high_temp
                    result["low_temp"] = low_temp
                    
                    # Convert high/low to Celsius
                    if high_temp is not None:
                        result["high_temp_c"] = round((high_temp - 32) * 5 / 9)
                    if low_temp is not None:
                        result["low_temp_c"] = round((low_temp - 32) * 5 / 9)
                    
                    # Get precipitation probability from first forecast period
                    # OpenWeatherMap uses 0-1 range, convert to 0-100
                    pop = forecast_data["list"][0].get("pop", 0)
                    result["precipitation_chance"] = int(pop * 100) if pop is not None else 0
                    
                    # Calculate sunset time from sys data
                    if "sys" in current_data and "sunset" in current_data["sys"]:
                        sunset_timestamp = current_data["sys"]["sunset"]
                        # Get timezone offset if available (in seconds)
                        timezone_offset = current_data.get("timezone", 0)
                        # Sunset timestamp is UTC, add timezone offset for local time
                        local_timestamp = sunset_timestamp + timezone_offset
                        sunset_dt = datetime.fromtimestamp(local_timestamp, tz=timezone.utc)
                        # Format as "8:36 PM" (remove leading zero from hour)
                        hour = sunset_dt.strftime("%I").lstrip("0") or "12"
                        minute = sunset_dt.strftime("%M")
                        period = sunset_dt.strftime("%p")
                        result["sunset"] = f"{hour}:{minute} {period}"
                    
                    # Note: UV index not available in free tier forecast API
                    # Would require One Call API v3.0 (paid)
                    result["uv_index"] = None
            except Exception as e:
                logger.warning(f"Failed to fetch forecast data from OpenWeatherMap for {location_name}: {e}")
                # Continue with current weather data only
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch weather from OpenWeatherMap for {location_name}: {e}")
            return None
        except KeyError as e:
            logger.error(f"Unexpected response format from OpenWeatherMap for {location_name}: {e}")
            return None

