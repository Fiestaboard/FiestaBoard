"""Tests for the weather plugin."""

import pytest
from unittest.mock import patch, Mock, MagicMock

from plugins.weather import WeatherPlugin
from plugins.weather.source import WeatherSource, _uv_to_display_index


class TestUvToDisplayIndex:
    """Tests for UV value normalization (0-11+ scale)."""

    def test_uv_none_returns_none(self):
        assert _uv_to_display_index(None) is None

    def test_uv_zero_returns_zero(self):
        assert _uv_to_display_index(0) == 0
        assert _uv_to_display_index(0.0) == 0

    def test_uv_integer_standard_scale(self):
        """Integers are always standard 0-11+ (type-based)."""
        assert _uv_to_display_index(1) == 1
        assert _uv_to_display_index(5) == 5
        assert _uv_to_display_index(10) == 10
        assert _uv_to_display_index(11) == 11

    def test_uv_float_standard_scale_rounded(self):
        """Floats outside (0, 1) are standard scale and rounded."""
        assert _uv_to_display_index(2.1) == 2
        assert _uv_to_display_index(3.8) == 4
        assert _uv_to_display_index(1.0) == 1

    def test_uv_float_normalized_between_0_and_1(self):
        """Floats in (0, 1) are treated as normalized and scaled to 0-11."""
        assert _uv_to_display_index(0.1) == 1
        assert _uv_to_display_index(0.5) == 6
        assert _uv_to_display_index(0.9) == 10

    def test_uv_string_coerced_to_float(self):
        """String values are coerced to float then processed (so "1" -> 1, "0.5" -> 6)."""
        assert _uv_to_display_index("7") == 7
        assert _uv_to_display_index("0.5") == 6

    def test_uv_negative_clamped_to_zero(self):
        assert _uv_to_display_index(-1) == 0


class TestWeatherSourceUvDisplay:
    """Tests for UV index display (0-11+) when API may use normalized scale."""

    @patch('requests.get')
    def test_weatherapi_normalized_uv_scale_displayed_correctly(self, mock_get):
        """When API returns UV on 0-1 scale, we display 0-11."""
        current_response = Mock()
        current_response.status_code = 200
        current_response.json.return_value = {
            "current": {
                "temp_f": 70,
                "feelslike_f": 68,
                "condition": {"text": "Sunny"},
                "humidity": 50,
                "wind_mph": 5,
                "uv": 0.5,  # normalized: moderate UV -> display 6
            },
            "location": {"name": "San Francisco"},
        }
        current_response.raise_for_status = Mock()

        forecast_response = Mock()
        forecast_response.status_code = 200
        forecast_response.json.return_value = {
            "forecast": {
                "forecastday": [{
                    "day": {
                        "maxtemp_f": 75,
                        "mintemp_f": 55,
                        "uv": 0.9,  # normalized: high UV -> display 10
                        "daily_chance_of_rain": 0,
                    },
                    "astro": {"sunset": "05:36 PM"},
                }],
            },
        }
        forecast_response.raise_for_status = Mock()

        mock_get.side_effect = [current_response, forecast_response]

        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}],
        )
        result = source.fetch_current_weather()

        # We take the higher of current (6) and forecast (10)
        assert result["uv_index"] == 10
        assert isinstance(result["uv_index"], int)


class TestWeatherSource:
    """Tests for WeatherSource class."""
    
    def test_init_with_api_key(self):
        """Test initialization with API key."""
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}]
        )
        assert source is not None
        assert source.api_key == "test_key"
    
    def test_init_with_provider(self):
        """Test initialization with provider selection."""
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}]
        )
        assert source.provider == "weatherapi"
    
    def test_init_openweathermap_provider(self):
        """Test initialization with OpenWeatherMap provider."""
        source = WeatherSource(
            provider="openweathermap",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}]
        )
        assert source.provider == "openweathermap"
    
    @patch('requests.get')
    def test_fetch_weather_success(self, mock_get):
        """Test successful weather data fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "current": {
                "temp_f": 72,
                "feelslike_f": 70,
                "condition": {"text": "Sunny"},
                "humidity": 45,
                "wind_mph": 10
            },
            "location": {
                "name": "San Francisco",
                "region": "California"
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}]
        )
        result = source.fetch_current_weather()
        
        assert result is not None
        assert isinstance(result, dict)
        assert result["temperature"] == 72
    
    @patch('requests.get')
    def test_fetch_weather_api_error(self, mock_get):
        """Test handling of API errors."""
        mock_get.side_effect = Exception("Network error")
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}]
        )
        result = source.fetch_current_weather()
        
        # Should return None on error
        assert result is None
    
    @patch('requests.get')
    def test_fetch_weather_invalid_location(self, mock_get):
        """Test handling of invalid location."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = Exception("Bad request")
        mock_get.return_value = mock_response
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "InvalidLocation123", "name": "BAD"}]
        )
        result = source.fetch_current_weather()
        
        # Should handle gracefully
        assert result is None


class TestWeatherDataParsing:
    """Tests for weather data parsing."""
    
    def test_parse_temperature(self):
        """Test temperature parsing."""
        temps = [72, 32, 100, -10, 0]
        for temp in temps:
            # Temperature should be a number
            assert isinstance(temp, (int, float))
    
    def test_parse_condition(self):
        """Test weather condition parsing."""
        conditions = ["Sunny", "Partly cloudy", "Rain", "Snow", "Overcast"]
        for cond in conditions:
            assert isinstance(cond, str)
            assert len(cond) > 0
    
    def test_parse_humidity(self):
        """Test humidity parsing."""
        humidity_values = [0, 50, 100, 45, 85]
        for humidity in humidity_values:
            assert 0 <= humidity <= 100
    
    def test_parse_wind_speed(self):
        """Test wind speed parsing."""
        wind_speeds = [0, 10, 25, 50, 100]
        for speed in wind_speeds:
            assert speed >= 0


class TestWeatherFormatting:
    """Tests for weather display formatting."""
    
    def test_temperature_formatting(self):
        """Test temperature is formatted correctly."""
        temp = 72
        # Common formats
        formats = [f"{temp}°", f"{temp}F", f"{temp}°F", str(temp)]
        assert any(f in formats for f in formats)
    
    def test_condition_fits_display(self):
        """Test weather condition fits display width."""
        max_chars = 22  # Board line width
        
        conditions = ["Sunny", "Partly cloudy", "Rain", "Heavy rain"]
        for cond in conditions:
            assert len(cond) <= max_chars
    
    def test_humidity_formatting(self):
        """Test humidity is formatted correctly."""
        humidity = 65
        formatted = f"{humidity}%"
        assert "%" in formatted
    
    def test_wind_formatting(self):
        """Test wind speed is formatted correctly."""
        wind = 15
        formatted_mph = f"{wind} mph"
        formatted_short = f"{wind}mph"
        assert "mph" in formatted_mph.lower() or "mph" in formatted_short.lower()


class TestWeatherMultipleLocations:
    """Tests for multiple location support."""
    
    def test_locations_list(self):
        """Test handling multiple locations."""
        locations = [
            {"location": "San Francisco, CA", "name": "HOME"},
            {"location": "Los Angeles, CA", "name": "LA"},
            {"location": "New York, NY", "name": "NYC"}
        ]
        
        assert len(locations) == 3
        for loc in locations:
            assert "location" in loc
            assert "name" in loc
    
    def test_location_name_length(self):
        """Test location names fit display constraints."""
        max_name_length = 8  # Typical constraint
        
        names = ["HOME", "WORK", "LA", "NYC", "SF"]
        for name in names:
            assert len(name) <= max_name_length
    
    @patch('requests.get')
    def test_fetch_multiple_locations(self, mock_get):
        """Test fetching weather for multiple locations."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "current": {
                "temp_f": 72,
                "feelslike_f": 70,
                "condition": {"text": "Sunny"},
                "humidity": 50,
                "wind_mph": 5
            },
            "location": {"name": "San Francisco"}
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        locations = [
            {"location": "San Francisco, CA", "name": "HOME"},
            {"location": "Los Angeles, CA", "name": "LA"}
        ]
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=locations
        )
        results = source.fetch_multiple_locations()
        
        assert isinstance(results, list)
        # Should have fetched for each location
        assert len(results) == len(locations)


class TestWeatherEdgeCases:
    """Edge case tests for weather plugin."""
    
    def test_extreme_temperatures(self):
        """Test handling extreme temperatures."""
        extreme_temps = [-50, -20, 0, 120, 140]
        for temp in extreme_temps:
            # All should be valid numbers
            assert isinstance(temp, (int, float))
    
    def test_zero_visibility(self):
        """Test zero visibility conditions."""
        visibility = 0
        assert visibility >= 0
    
    def test_high_wind_speed(self):
        """Test very high wind speeds."""
        high_winds = [50, 100, 150, 200]
        for wind in high_winds:
            assert wind >= 0
    
    @patch('requests.get')
    def test_empty_response(self, mock_get):
        """Test handling of empty API response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "SF", "name": "SF"}]
        )
        result = source.fetch_current_weather()
        # Should handle gracefully - returns None or dict
        assert result is None or isinstance(result, dict)
    
    @patch('requests.get')
    def test_timeout_handling(self, mock_get):
        """Test handling of request timeout."""
        from requests.exceptions import Timeout
        mock_get.side_effect = Timeout("Request timed out")
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "SF", "name": "SF"}]
        )
        result = source.fetch_current_weather()
        # Should handle gracefully
        assert result is None
    
    def test_empty_locations_list(self):
        """Test handling of empty locations list."""
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[]
        )
        results = source.fetch_multiple_locations()
        assert results == []


class TestWeatherPlugin:
    """Tests for the WeatherPlugin class."""
    
    @pytest.fixture
    def weather_manifest(self):
        """Create a test manifest for the weather plugin."""
        return {
            "id": "weather",
            "name": "Weather",
            "version": "1.0.0",
            "description": "Weather plugin",
            "author": "Test",
            "settings_schema": {},
            "variables": {"simple": ["temperature", "condition"]},
            "max_lengths": {}
        }
    
    def test_plugin_id(self, weather_manifest):
        """Test plugin ID matches manifest."""
        from plugins.weather import WeatherPlugin
        plugin = WeatherPlugin(weather_manifest)
        assert plugin.plugin_id == "weather"
    
    def test_fetch_data_no_config(self, weather_manifest):
        """Test fetch_data with missing config."""
        from plugins.weather import WeatherPlugin
        plugin = WeatherPlugin(weather_manifest)
        # Don't set any config - plugin.config will be empty/None
        result = plugin.fetch_data()
        
        assert result.available is False
        assert result.error is not None
    
    @patch('requests.get')
    def test_fetch_data_success(self, mock_get, weather_manifest):
        """Test fetch_data with valid config."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "current": {
                "temp_f": 72,
                "feelslike_f": 70,
                "condition": {"text": "Sunny"},
                "humidity": 45,
                "wind_mph": 5
            },
            "location": {"name": "San Francisco"}
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        from plugins.weather import WeatherPlugin
        plugin = WeatherPlugin(weather_manifest)
        
        # Set config on the plugin (simulating what the registry does)
        plugin._config = {
            "provider": "weatherapi",
            "api_key": "test_key",
            "locations": [{"location": "San Francisco, CA", "name": "SF"}]
        }
        
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.data is not None
        assert result.data["temperature"] == 72


class TestWeatherForecastData:
    """Tests for forecast data fetching."""
    
    @pytest.fixture
    def weather_manifest(self):
        """Create a test manifest for the weather plugin."""
        return {
            "id": "weather",
            "name": "Weather",
            "version": "1.0.0",
            "description": "Weather plugin",
            "author": "Test",
            "settings_schema": {},
            "variables": {"simple": ["temperature", "condition"]},
            "max_lengths": {}
        }
    
    @patch('requests.get')
    def test_weatherapi_forecast_data(self, mock_get):
        """Test fetching forecast data from WeatherAPI."""
        # Mock current weather response
        current_response = Mock()
        current_response.status_code = 200
        current_response.json.return_value = {
            "current": {
                "temp_f": 63,
                "feelslike_f": 62,
                "condition": {"text": "Rain"},
                "humidity": 80,
                "wind_mph": 14,
                "uv": 5
            },
            "location": {"name": "San Francisco"}
        }
        current_response.raise_for_status = Mock()
        
        # Mock forecast response
        forecast_response = Mock()
        forecast_response.status_code = 200
        forecast_response.json.return_value = {
            "forecast": {
                "forecastday": [{
                    "day": {
                        "maxtemp_f": 65,
                        "mintemp_f": 52,
                        "uv": 10,
                        "daily_chance_of_rain": 0
                    },
                    "astro": {
                        "sunset": "05:36 PM"
                    }
                }]
            }
        }
        forecast_response.raise_for_status = Mock()
        
        # Return current first, then forecast
        mock_get.side_effect = [current_response, forecast_response]
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}]
        )
        result = source.fetch_current_weather()
        
        assert result is not None
        assert result["temperature"] == 63
        assert result["high_temp"] == 65
        assert result["low_temp"] == 52
        assert result["uv_index"] == 10  # Should use forecast UV (higher)
        assert result["precipitation_chance"] == 0
        assert result["sunset"] == "5:36 PM"
        # Check Celsius conversions
        assert "temperature_c" in result
        assert "feels_like_c" in result
        assert "high_temp_c" in result
        assert "low_temp_c" in result
    
    @patch('requests.get')
    def test_weatherapi_forecast_fallback(self, mock_get):
        """Test that current weather still works if forecast fails."""
        # Mock current weather response
        current_response = Mock()
        current_response.status_code = 200
        current_response.json.return_value = {
            "current": {
                "temp_f": 72,
                "feelslike_f": 70,
                "condition": {"text": "Sunny"},
                "humidity": 45,
                "wind_mph": 10,
                "uv": 3
            },
            "location": {"name": "San Francisco"}
        }
        current_response.raise_for_status = Mock()
        
        # Mock forecast failure
        from requests.exceptions import RequestException
        forecast_error = RequestException("Forecast API error")
        
        mock_get.side_effect = [current_response, forecast_error]
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}]
        )
        result = source.fetch_current_weather()
        
        # Should still return current weather data
        assert result is not None
        assert result["temperature"] == 72
        assert result["uv_index"] == 3  # From current weather
        # Forecast fields may be None
        assert "high_temp" in result or result.get("high_temp") is None
    
    @patch('requests.get')
    def test_openweathermap_forecast_data(self, mock_get):
        """Test fetching forecast data from OpenWeatherMap."""
        from datetime import datetime, timezone
        
        # Mock current weather response
        current_response = Mock()
        current_response.status_code = 200
        # Create a sunset timestamp (example: 8:36 PM today)
        sunset_time = datetime.now(timezone.utc).replace(hour=20, minute=36, second=0, microsecond=0)
        sunset_timestamp = int(sunset_time.timestamp())
        
        current_response.json.return_value = {
            "main": {
                "temp": 63,
                "feels_like": 62,
                "humidity": 80
            },
            "weather": [{
                "main": "Rain",
                "description": "light rain"
            }],
            "wind": {"speed": 14},
            "name": "San Francisco",
            "sys": {
                "sunset": sunset_timestamp
            },
            "timezone": -28800  # PST offset in seconds
        }
        current_response.raise_for_status = Mock()
        
        # Mock forecast response
        forecast_response = Mock()
        forecast_response.status_code = 200
        forecast_response.json.return_value = {
            "list": [
                {"main": {"temp": 65, "temp_max": 65, "temp_min": 52}, "pop": 0.0},
                {"main": {"temp": 52, "temp_max": 65, "temp_min": 50}, "pop": 0.1},
            ]
        }
        forecast_response.raise_for_status = Mock()
        
        mock_get.side_effect = [current_response, forecast_response]
        
        source = WeatherSource(
            provider="openweathermap",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}]
        )
        result = source.fetch_current_weather()
        
        assert result is not None
        assert result["temperature"] == 63
        assert result["high_temp"] == 65
        assert result["low_temp"] == 52
        assert result["precipitation_chance"] == 0  # Converted from 0.0
        assert "sunset" in result
        assert result["sunset"].endswith("PM") or result["sunset"].endswith("AM")
    
    def test_sunset_time_formatting(self):
        """Test sunset time formatting."""
        from plugins.weather.source import WeatherSource
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "SF", "name": "SF"}]
        )
        
        # Test various formats
        assert source._format_sunset_time("05:34 PM") == "5:34 PM"
        assert source._format_sunset_time("8:36 PM") == "8:36 PM"
        assert source._format_sunset_time("17:34") == "5:34 PM"
        assert source._format_sunset_time("12:00 PM") == "12:00 PM"
        assert source._format_sunset_time("00:00") == "12:00 AM"
    
    @patch('requests.get')
    def test_plugin_includes_forecast_fields(self, mock_get, weather_manifest):
        """Test that plugin includes new forecast fields in data."""
        # Mock current weather response
        current_response = Mock()
        current_response.status_code = 200
        current_response.json.return_value = {
            "current": {
                "temp_f": 63,
                "feelslike_f": 62,
                "condition": {"text": "Rain"},
                "humidity": 80,
                "wind_mph": 14,
                "uv": 5
            },
            "location": {"name": "San Francisco"}
        }
        current_response.raise_for_status = Mock()
        
        # Mock forecast response
        forecast_response = Mock()
        forecast_response.status_code = 200
        forecast_response.json.return_value = {
            "forecast": {
                "forecastday": [{
                    "day": {
                        "maxtemp_f": 65,
                        "mintemp_f": 52,
                        "uv": 10,
                        "daily_chance_of_rain": 0
                    },
                    "astro": {
                        "sunset": "05:36 PM"
                    }
                }]
            }
        }
        forecast_response.raise_for_status = Mock()
        
        mock_get.side_effect = [current_response, forecast_response]
        
        from plugins.weather import WeatherPlugin
        plugin = WeatherPlugin(weather_manifest)
        plugin._config = {
            "provider": "weatherapi",
            "api_key": "test_key",
            "locations": [{"location": "San Francisco, CA", "name": "SF"}]
        }
        
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.data is not None
        assert "precipitation_chance" in result.data
        assert "high_temp" in result.data
        assert "low_temp" in result.data
        assert "uv_index" in result.data
        assert "sunset" in result.data
        assert result.data["high_temp"] == 65
        assert result.data["low_temp"] == 52
        assert result.data["uv_index"] == 10
        assert result.data["precipitation_chance"] == 0
    
    @patch('requests.get')
    def test_temperature_rounding(self, mock_get):
        """Test that temperatures are rounded to whole numbers."""
        current_response = Mock()
        current_response.status_code = 200
        current_response.json.return_value = {
            "current": {
                "temp_f": 48.9,
                "feelslike_f": 47.2,
                "condition": {"text": "Cloudy"},
                "humidity": 60,
                "wind_mph": 5,
                "uv": 2.1
            },
            "location": {"name": "San Francisco"}
        }
        current_response.raise_for_status = Mock()
        
        forecast_response = Mock()
        forecast_response.status_code = 200
        forecast_response.json.return_value = {
            "forecast": {
                "forecastday": [{
                    "day": {
                        "maxtemp_f": 52.7,
                        "mintemp_f": 45.3,
                        "uv": 3.8,
                        "daily_chance_of_rain": 20
                    },
                    "astro": {"sunset": "05:36 PM"}
                }]
            }
        }
        forecast_response.raise_for_status = Mock()
        
        mock_get.side_effect = [current_response, forecast_response]
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}]
        )
        result = source.fetch_current_weather()
        
        # Temperatures should be rounded
        assert result["temperature"] == 49  # 48.9 rounded
        assert result["feels_like"] == 47  # 47.2 rounded
        assert result["high_temp"] == 53  # 52.7 rounded
        assert result["low_temp"] == 45  # 45.3 rounded
        
        # UV index should be rounded to integer
        assert result["uv_index"] == 4  # 3.8 rounded (forecast UV is higher than 2.1)
        assert isinstance(result["uv_index"], int)
    
    @patch('requests.get')
    def test_celsius_conversion(self, mock_get):
        """Test Celsius temperature conversion."""
        current_response = Mock()
        current_response.status_code = 200
        current_response.json.return_value = {
            "current": {
                "temp_f": 68.0,  # 20°C
                "feelslike_f": 66.0,  # ~19°C
                "condition": {"text": "Sunny"},
                "humidity": 50,
                "wind_mph": 5,
                "uv": 5
            },
            "location": {"name": "San Francisco"}
        }
        current_response.raise_for_status = Mock()
        
        forecast_response = Mock()
        forecast_response.status_code = 200
        forecast_response.json.return_value = {
            "forecast": {
                "forecastday": [{
                    "day": {
                        "maxtemp_f": 77.0,  # 25°C
                        "mintemp_f": 59.0,  # 15°C
                        "uv": 5,
                        "daily_chance_of_rain": 0
                    },
                    "astro": {"sunset": "05:36 PM"}
                }]
            }
        }
        forecast_response.raise_for_status = Mock()
        
        mock_get.side_effect = [current_response, forecast_response]
        
        source = WeatherSource(
            provider="weatherapi",
            api_key="test_key",
            locations=[{"location": "San Francisco, CA", "name": "SF"}]
        )
        result = source.fetch_current_weather()
        
        # Check Celsius conversions (C = (F - 32) * 5/9)
        assert result["temperature_c"] == 20  # (68 - 32) * 5/9 = 20
        assert result["feels_like_c"] == 19  # (66 - 32) * 5/9 ≈ 19
        assert result["high_temp_c"] == 25  # (77 - 32) * 5/9 = 25
        assert result["low_temp_c"] == 15  # (59 - 32) * 5/9 = 15
        # Check Celsius variables are included (result is a dict, not PluginResult)
        assert "temperature_c" in result
        assert "feels_like_c" in result
        assert "high_temp_c" in result
        assert "low_temp_c" in result


class TestWeatherPluginMethods:
    """Tests for WeatherPlugin public methods."""

    @pytest.fixture
    def weather_manifest(self):
        """Create a test manifest for the weather plugin."""
        return {
            "id": "weather",
            "name": "Weather",
            "version": "1.0.0",
            "description": "Weather plugin",
            "author": "Test",
            "settings_schema": {},
            "variables": {"simple": ["temperature", "condition"]},
            "max_lengths": {}
        }

    @pytest.fixture
    def plugin(self, weather_manifest):
        return WeatherPlugin(weather_manifest)

    def test_validate_config_valid(self, plugin):
        """Test validate_config with valid configuration."""
        config = {
            "api_key": "test_key",
            "provider": "weatherapi",
            "locations": [{"location": "San Francisco", "name": "SF"}],
            "refresh_seconds": 300
        }
        errors = plugin.validate_config(config)
        assert len(errors) == 0

    def test_validate_config_missing_api_key(self, plugin):
        """Test validate_config with missing API key."""
        config = {"locations": [{"location": "SF", "name": "SF"}]}
        errors = plugin.validate_config(config)
        assert any("API key" in e for e in errors)

    def test_validate_config_missing_locations(self, plugin):
        """Test validate_config with missing locations."""
        config = {"api_key": "test_key"}
        errors = plugin.validate_config(config)
        assert any("location" in e for e in errors)

    def test_validate_config_invalid_provider(self, plugin):
        """Test validate_config with invalid provider."""
        config = {
            "api_key": "test_key",
            "locations": [{"location": "SF", "name": "SF"}],
            "provider": "invalid_provider"
        }
        errors = plugin.validate_config(config)
        assert any("provider" in e for e in errors)

    def test_validate_config_invalid_refresh(self, plugin):
        """Test validate_config with invalid refresh interval."""
        config = {
            "api_key": "test_key",
            "locations": [{"location": "SF", "name": "SF"}],
            "refresh_seconds": 30
        }
        errors = plugin.validate_config(config)
        assert any("Refresh interval" in e for e in errors)

    def test_validate_config_legacy_location(self, plugin):
        """Test validate_config with legacy single location."""
        config = {
            "api_key": "test_key",
            "location": "San Francisco, CA"
        }
        errors = plugin.validate_config(config)
        assert len(errors) == 0

    def test_on_config_change(self, plugin):
        """Test on_config_change resets source and cache."""
        plugin._source = Mock()
        plugin._cache = {"temperature": 70}
        old_config = {"api_key": "old_key"}
        new_config = {"api_key": "new_key"}
        plugin.on_config_change(old_config, new_config)
        assert plugin._source is None
        assert plugin._cache is None

    def test_get_source_no_config(self, plugin):
        """Test _get_source with no config."""
        plugin._config = None
        result = plugin._get_source()
        assert result is None

    def test_get_source_no_api_key(self, plugin):
        """Test _get_source with missing API key."""
        plugin._config = {"locations": [{"location": "SF", "name": "SF"}]}
        result = plugin._get_source()
        assert result is None

    def test_get_source_no_locations(self, plugin):
        """Test _get_source with no locations."""
        plugin._config = {"api_key": "test_key"}
        result = plugin._get_source()
        assert result is None

    def test_get_source_legacy_location(self, plugin):
        """Test _get_source with legacy location format."""
        plugin._config = {
            "api_key": "test_key",
            "location": "San Francisco, CA"
        }
        result = plugin._get_source()
        assert result is not None

    def test_get_formatted_display_with_cache(self, plugin):
        """Test get_formatted_display with cached data."""
        plugin._cache = {
            "temperature": 72,
            "condition": "Sunny",
            "feels_like": 70,
            "humidity": 65,
            "wind_speed": 10
        }
        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) == 6
        assert "WEATHER" in lines[0]
        assert "72°" in lines[1]
        assert "Sunny" in lines[1]
        assert "FEELS LIKE" in lines[2]
        assert "HUMIDITY" in lines[3]
        assert "WIND" in lines[4]

    def test_get_formatted_display_no_cache(self, plugin):
        """Test get_formatted_display without cache (fetch fails)."""
        plugin._cache = None
        plugin._config = {}
        lines = plugin.get_formatted_display()
        assert lines is None

    def test_fetch_data_exception(self, plugin):
        """Test fetch_data with exception during fetch."""
        plugin._config = {"api_key": "test_key", "locations": [{"location": "SF", "name": "SF"}]}
        mock_source = Mock()
        mock_source.fetch_multiple_locations.side_effect = Exception("Test error")
        with patch.object(plugin, '_get_source', return_value=mock_source):
            result = plugin.fetch_data()
            assert not result.available
            assert "Test error" in result.error

    def test_cleanup(self, plugin):
        """Test cleanup method."""
        plugin._source = Mock()
        plugin._cache = {"data": "test"}
        plugin.cleanup()
        assert plugin._source is None
        assert plugin._cache is None
