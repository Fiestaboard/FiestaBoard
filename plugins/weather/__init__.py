"""Weather plugin for FiestaBoard.

Displays current weather conditions using WeatherAPI or OpenWeatherMap.
"""

from typing import Any, Dict, List, Optional
import logging

from src.plugins.base import PluginBase, PluginResult
from .source import WeatherSource

logger = logging.getLogger(__name__)


class WeatherPlugin(PluginBase):
    """Weather data plugin.
    
    Fetches current weather data from WeatherAPI or OpenWeatherMap
    for one or more configured locations.
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the weather plugin."""
        super().__init__(manifest)
        self._source: Optional[WeatherSource] = None
        self._cache: Optional[Dict[str, Any]] = None
    
    @property
    def plugin_id(self) -> str:
        return "weather"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate weather configuration."""
        errors = []
        
        # Check required fields
        if not config.get("api_key"):
            errors.append("API key is required")
        
        locations = config.get("locations", [])
        if not locations:
            # Check for legacy single location
            if not config.get("location"):
                errors.append("At least one location is required")
        
        # Validate provider
        provider = config.get("provider", "weatherapi")
        if provider not in ("weatherapi", "openweathermap"):
            errors.append(f"Invalid provider: {provider}")
        
        # Validate refresh interval
        refresh = config.get("refresh_seconds", 300)
        if not isinstance(refresh, int) or refresh < 60:
            errors.append("Refresh interval must be at least 60 seconds")
        
        return errors
    
    def on_config_change(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> None:
        """Handle configuration changes."""
        # Reset source to pick up new config
        self._source = None
        self._cache = None
        logger.debug("Weather source reset due to config change")
    
    def _get_source(self) -> Optional[WeatherSource]:
        """Get or create the weather source."""
        if self._source is not None:
            return self._source
        
        config = self.config
        if not config:
            return None
        
        api_key = config.get("api_key")
        if not api_key:
            return None
        
        provider = config.get("provider", "weatherapi")
        
        # Build locations list (support both old and new format)
        locations = config.get("locations", [])
        if not locations:
            # Legacy single location support
            location = config.get("location")
            if location:
                locations = [{"location": location, "name": "HOME"}]
        
        if not locations:
            return None
        
        self._source = WeatherSource(
            provider=provider,
            api_key=api_key,
            locations=locations
        )
        return self._source
    
    def fetch_data(self) -> PluginResult:
        """Fetch weather data for all configured locations."""
        source = self._get_source()
        
        if source is None:
            return PluginResult(
                available=False,
                error="Weather not configured"
            )
        
        try:
            # Fetch all locations
            all_data = source.fetch_multiple_locations()
            
            if not all_data:
                return PluginResult(
                    available=False,
                    error="Failed to fetch weather data"
                )
            
            # Build response data structure
            # Primary location data (first location) for backward compatibility
            primary = all_data[0]
            
            data = {
                # Primary location fields (backward compatibility)
                "temperature": primary.get("temperature"),
                "temperature_c": primary.get("temperature_c"),
                "feels_like": primary.get("feels_like"),
                "feels_like_c": primary.get("feels_like_c"),
                "condition": primary.get("condition"),
                "humidity": primary.get("humidity"),
                "wind_speed": primary.get("wind_speed"),
                "location": primary.get("location"),
                "location_name": primary.get("location_name"),
                # New forecast fields
                "precipitation_chance": primary.get("precipitation_chance"),
                "high_temp": primary.get("high_temp"),
                "high_temp_c": primary.get("high_temp_c"),
                "low_temp": primary.get("low_temp"),
                "low_temp_c": primary.get("low_temp_c"),
                "uv_index": primary.get("uv_index"),
                "sunset": primary.get("sunset"),
                # Aggregate fields
                "location_count": len(all_data),
                # All locations array
                "locations": all_data,
                # Multi-day forecast (from primary location)
                "forecast": primary.get("forecast", []),
            }
            
            self._cache = data
            
            return PluginResult(
                available=True,
                data=data
            )
            
        except Exception as e:
            logger.exception("Error fetching weather data")
            return PluginResult(
                available=False,
                error=str(e)
            )
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted weather display."""
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None
        
        data = self._cache
        if not data:
            return None
        
        # Format for board (22 chars per line, 6 lines)
        temp = data.get("temperature", "??")
        condition = data.get("condition", "Unknown")[:12]
        feels = data.get("feels_like", "??")
        humidity = data.get("humidity", "??")
        wind = data.get("wind_speed", "??")
        
        lines = [
            "WEATHER".center(22),
            f"{temp}° {condition}".center(22),
            f"FEELS LIKE {feels}°".center(22),
            f"HUMIDITY {humidity}%".center(22),
            f"WIND {wind}MPH".center(22),
            "",
        ]
        
        return lines
    
    def get_forecast_display(self) -> Optional[List[str]]:
        """Return forecast formatted weather display for the board.
        
        Layout (6 rows x 22 cols):
        Row 0: Header "WEATHER REPORT" with color tiles
        Row 1: Empty
        Rows 2-5: Two-column forecast with day name, temp, and color tile
        
        Each forecast entry uses 11 display characters:
        DAY + spaces + tempF + {color_tile}
        """
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None
        
        data = self._cache
        if not data:
            return None
        
        forecast = data.get("forecast", [])
        if not forecast:
            return None
        
        # Row 0: Header with decorative color tiles
        lines = [
            "\u00b0{violet}{violet} WEATHER REPORT {violet}{violet}\u00b0",
            "",  # Row 1: empty
        ]
        
        # Rows 2-5: Forecast in two-column layout (up to 8 days)
        # Left column: days 0,1,2,3  Right column: days 4,5,6,7
        max_days = min(len(forecast), 8)
        half = (max_days + 1) // 2  # Number of rows needed
        
        for row_idx in range(4):  # Rows 2-5
            left_idx = row_idx
            right_idx = row_idx + half
            
            if left_idx < max_days:
                left = self._format_forecast_entry(forecast[left_idx])
            else:
                left = " " * 11
            
            if right_idx < max_days:
                right = self._format_forecast_entry(forecast[right_idx])
            else:
                right = " " * 11
            
            lines.append(left + right)
        
        return lines
    
    @staticmethod
    def _format_forecast_entry(day_data: Dict[str, Any]) -> str:
        """Format a single forecast day for the board display.
        
        Returns a string that renders as exactly 11 board tiles:
        DAY + spaces + tempF + {color_tile}
        
        Args:
            day_data: Dict with day_name, high_temp, temperature_color
        """
        day_name = str(day_data.get("day_name", "???"))[:3]
        temp = day_data.get("high_temp")
        color = day_data.get("temperature_color", "white")
        
        temp_str = f"{temp}F" if temp is not None else "??F"
        # Display tiles: 3 (day) + spaces + len(temp_str) + 1 (color) = 11
        spaces = max(1, 7 - len(temp_str))
        return f"{day_name}{' ' * spaces}{temp_str}{{{color}}}"
    
    def cleanup(self) -> None:
        """Clean up resources."""
        self._source = None
        self._cache = None


# Export the plugin class
Plugin = WeatherPlugin

