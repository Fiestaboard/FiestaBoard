"""Weather data source using WeatherAPI.com or OpenWeatherMap."""

import logging
import requests
from typing import Optional, Dict, List
from ..config import Config

logger = logging.getLogger(__name__)


class WeatherSource:
    """Fetches current weather data from weather APIs."""
    
    def __init__(self, provider: str, api_key: str, locations: List[Dict[str, str]]):
        """
        Initialize weather source.
        
        Args:
            provider: "weatherapi" or "openweathermap"
            api_key: API key for the weather service
            locations: List of location dicts with keys:
                      - location: Location string (city name or lat/lon)
                      - name: Display name (e.g., "HOME", "OFFICE")
        """
        self.provider = provider
        self.api_key = api_key
        # Support both new (list of locations) and old (single location) format
        if isinstance(locations, list):
            self.locations = locations if locations else []
        else:
            # Backward compatibility - single location dict or string
            if isinstance(locations, dict):
                self.locations = [locations]
            else:
                # String location (old format)
                self.locations = [{"location": locations, "name": "HOME"}]
        
        # For backward compatibility
        if self.locations:
            self.location = self.locations[0].get("location", "")
    
    def fetch_current_weather(self) -> Optional[Dict[str, any]]:
        """
        Fetch current weather data (backward compatibility - returns first location).
        
        Returns:
            Dictionary with weather data for first location, or None if failed
        """
        results = self.fetch_multiple_locations()
        if results and len(results) > 0:
            return results[0]
        return None
    
    def fetch_multiple_locations(self) -> List[Dict[str, any]]:
        """
        Fetch weather for all configured locations.
        
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
    
    def _fetch_single_location(self, location: str, location_name: str) -> Optional[Dict[str, any]]:
        """
        Fetch weather for a single location.
        
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
    
    def _fetch_weatherapi_for_location(self, location: str, location_name: str) -> Optional[Dict[str, any]]:
        """Fetch weather from WeatherAPI.com for a specific location."""
        url = "http://api.weatherapi.com/v1/current.json"
        params = {
            "key": self.api_key,
            "q": location,
            "aqi": "no"
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return {
                "temperature": data["current"]["temp_f"],
                "feels_like": data["current"]["feelslike_f"],
                "condition": data["current"]["condition"]["text"],
                "humidity": data["current"]["humidity"],
                "wind_mph": data["current"]["wind_mph"],
                "wind_speed": data["current"]["wind_mph"],  # Alias for template compatibility
                "location": data["location"]["name"],
                "location_name": location_name  # Add display name
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch weather from WeatherAPI for {location_name}: {e}")
            return None
        except KeyError as e:
            logger.error(f"Unexpected response format from WeatherAPI for {location_name}: {e}")
            return None
    
    def _fetch_openweathermap_for_location(self, location: str, location_name: str) -> Optional[Dict[str, any]]:
        """Fetch weather from OpenWeatherMap for a specific location."""
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": location,
            "appid": self.api_key,
            "units": "imperial"
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return {
                "temperature": data["main"]["temp"],
                "feels_like": data["main"]["feels_like"],
                "condition": data["weather"][0]["main"],
                "description": data["weather"][0]["description"],
                "humidity": data["main"]["humidity"],
                "wind_mph": data["wind"]["speed"],
                "wind_speed": data["wind"]["speed"],  # Alias for template compatibility
                "location_name": location_name  # Add display name
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch weather from OpenWeatherMap for {location_name}: {e}")
            return None
        except KeyError as e:
            logger.error(f"Unexpected response format from OpenWeatherMap for {location_name}: {e}")
            return None


def get_weather_source() -> Optional[WeatherSource]:
    """Get configured weather source instance."""
    if not Config.WEATHER_API_KEY:
        logger.warning("Weather API key not configured")
        return None
    
    # Support both new (WEATHER_LOCATIONS list) and old (WEATHER_LOCATION) config
    locations = getattr(Config, 'WEATHER_LOCATIONS', None)
    
    if not locations:
        # Fall back to single location (backward compatibility)
        location = Config.WEATHER_LOCATION
        if location:
            locations = [{
                "location": location,
                "name": "HOME"
            }]
        else:
            locations = []
    
    return WeatherSource(
        provider=Config.WEATHER_PROVIDER,
        api_key=Config.WEATHER_API_KEY,
        locations=locations
    )

