"""Tests for air quality and fog data source."""

import pytest
from unittest.mock import Mock, patch
from src.utils.air_fog import (
    AirFogSource,
    get_air_fog_source,
    DEFAULT_LAT,
    DEFAULT_LON,
)


class TestDewPointCalculation:
    """Tests for dew point calculation - the core fog prediction logic."""
    
    def test_dew_point_at_100_percent_humidity(self):
        """At 100% humidity, dew point equals temperature."""
        temp_f = 68.0
        humidity = 100.0
        dew_point = AirFogSource.calculate_dew_point(temp_f, humidity)
        # At 100% humidity, dew point should equal temperature
        assert abs(dew_point - temp_f) < 0.5
    
    def test_dew_point_at_50_percent_humidity(self):
        """At 50% humidity, dew point is significantly below temperature."""
        temp_f = 70.0
        humidity = 50.0
        dew_point = AirFogSource.calculate_dew_point(temp_f, humidity)
        # Dew point should be lower than temperature
        assert dew_point < temp_f
        # At 70°F and 50% humidity, dew point is approximately 50°F
        assert 48 < dew_point < 52
    
    def test_dew_point_at_low_humidity(self):
        """At low humidity, dew point is much lower than temperature."""
        temp_f = 80.0
        humidity = 20.0
        dew_point = AirFogSource.calculate_dew_point(temp_f, humidity)
        # At 20% humidity, dew point should be very low
        assert dew_point < 40
    
    def test_dew_point_cold_conditions(self):
        """Test dew point calculation in cold conditions."""
        temp_f = 32.0  # Freezing
        humidity = 80.0
        dew_point = AirFogSource.calculate_dew_point(temp_f, humidity)
        # Dew point should be below temperature
        assert dew_point < temp_f
        assert dew_point > 20  # But not unreasonably low
    
    def test_dew_point_hot_conditions(self):
        """Test dew point calculation in hot conditions."""
        temp_f = 100.0
        humidity = 70.0
        dew_point = AirFogSource.calculate_dew_point(temp_f, humidity)
        assert dew_point < temp_f
        # High humidity at 100F should have dew point around 88F
        assert 85 < dew_point < 92
    
    def test_dew_point_fog_condition(self):
        """When temp approaches dew point, fog can form."""
        temp_f = 55.0
        humidity = 95.0
        dew_point = AirFogSource.calculate_dew_point(temp_f, humidity)
        # At 95% humidity, dew point should be very close to temperature
        assert temp_f - dew_point < 3
    
    def test_dew_point_returns_float(self):
        """Dew point should return a rounded float."""
        dew_point = AirFogSource.calculate_dew_point(70.0, 60.0)
        assert isinstance(dew_point, float)
    
    def test_dew_point_typical_san_francisco(self):
        """Test typical San Francisco marine layer conditions."""
        # Cool, humid morning - typical fog conditions
        temp_f = 58.0
        humidity = 92.0
        dew_point = AirFogSource.calculate_dew_point(temp_f, humidity)
        # Dew point very close to temperature = fog likely
        assert temp_f - dew_point < 5


class TestAQICalculation:
    """Tests for AQI calculation from PM2.5 values."""
    
    def test_good_air_quality(self):
        """Test GOOD AQI (0-50) for low PM2.5."""
        aqi, category, color = AirFogSource.calculate_aqi_from_pm25(5.0)
        assert aqi < 50
        assert category == "GOOD"
        assert color == "GREEN"
    
    def test_moderate_air_quality(self):
        """Test MODERATE AQI (51-100) for moderate PM2.5."""
        aqi, category, color = AirFogSource.calculate_aqi_from_pm25(20.0)
        assert 51 <= aqi <= 100
        assert category == "MODERATE"
        assert color == "YELLOW"
    
    def test_unhealthy_sensitive_air_quality(self):
        """Test UNHEALTHY_SENSITIVE AQI (101-150)."""
        aqi, category, color = AirFogSource.calculate_aqi_from_pm25(40.0)
        assert 101 <= aqi <= 150
        assert category == "UNHEALTHY_SENSITIVE"
        assert color == "ORANGE"
    
    def test_unhealthy_air_quality(self):
        """Test UNHEALTHY AQI (151-200)."""
        aqi, category, color = AirFogSource.calculate_aqi_from_pm25(100.0)
        assert 151 <= aqi <= 200
        assert category == "UNHEALTHY"
        assert color == "RED"
    
    def test_very_unhealthy_air_quality(self):
        """Test VERY_UNHEALTHY AQI (201-300)."""
        aqi, category, color = AirFogSource.calculate_aqi_from_pm25(200.0)
        assert 201 <= aqi <= 300
        assert category == "VERY_UNHEALTHY"
        assert color == "PURPLE"
    
    def test_hazardous_air_quality(self):
        """Test HAZARDOUS AQI (301-500)."""
        aqi, category, color = AirFogSource.calculate_aqi_from_pm25(300.0)
        assert 301 <= aqi <= 500
        assert category == "HAZARDOUS"
        assert color == "MAROON"
    
    def test_extreme_pm25_values(self):
        """Test handling of extreme PM2.5 values."""
        aqi, category, color = AirFogSource.calculate_aqi_from_pm25(600.0)
        assert aqi == 500
        assert category == "HAZARDOUS"
        assert color == "MAROON"
    
    def test_zero_pm25(self):
        """Test zero PM2.5 value."""
        aqi, category, color = AirFogSource.calculate_aqi_from_pm25(0.0)
        assert aqi == 0
        assert category == "GOOD"
        assert color == "GREEN"
    
    def test_negative_pm25_handled(self):
        """Test negative PM2.5 is treated as zero."""
        aqi, category, color = AirFogSource.calculate_aqi_from_pm25(-5.0)
        assert aqi == 0
        assert category == "GOOD"
        assert color == "GREEN"
    
    def test_fire_trigger_threshold(self):
        """Test the fire trigger at AQI > 100."""
        # Just below threshold
        aqi, _, _ = AirFogSource.calculate_aqi_from_pm25(35.0)
        assert aqi <= 100
        
        # Just above threshold
        aqi, _, _ = AirFogSource.calculate_aqi_from_pm25(36.0)
        assert aqi > 100
    
    def test_aqi_breakpoint_boundaries(self):
        """Test AQI calculation at exact breakpoint boundaries."""
        # At 12.0 PM2.5 (top of GOOD)
        aqi, category, _ = AirFogSource.calculate_aqi_from_pm25(12.0)
        assert aqi == 50
        assert category == "GOOD"
        
        # At 12.1 PM2.5 (bottom of MODERATE)
        aqi, category, _ = AirFogSource.calculate_aqi_from_pm25(12.1)
        assert aqi == 51
        assert category == "MODERATE"


class TestFogStatus:
    """Tests for fog status determination."""
    
    def test_heavy_fog_low_visibility(self):
        """Test HEAVY FOG when visibility < 1600m."""
        is_foggy, status, color = AirFogSource.determine_fog_status(
            visibility_m=1000,
            humidity=70,
            temp_f=65
        )
        assert is_foggy is True
        assert status == "FOG: HEAVY"
        assert color == "ORANGE"
    
    def test_heavy_fog_at_visibility_threshold(self):
        """Test fog trigger exactly at 1600m threshold."""
        # Just below threshold
        is_foggy, status, _ = AirFogSource.determine_fog_status(
            visibility_m=1599,
            humidity=70,
            temp_f=65
        )
        assert is_foggy is True
        assert status == "FOG: HEAVY"
        
        # At threshold - not foggy
        is_foggy, status, _ = AirFogSource.determine_fog_status(
            visibility_m=1600,
            humidity=70,
            temp_f=65
        )
        assert is_foggy is False
    
    def test_heavy_fog_humidity_and_temp_condition(self):
        """Test HEAVY FOG when humidity > 95% AND temp < 60F."""
        is_foggy, status, color = AirFogSource.determine_fog_status(
            visibility_m=5000,  # Good visibility
            humidity=96,
            temp_f=55
        )
        assert is_foggy is True
        assert status == "FOG: HEAVY"
        assert color == "ORANGE"
    
    def test_no_fog_high_humidity_but_warm(self):
        """Test no fog when humidity > 95% but temp >= 60F."""
        is_foggy, status, _ = AirFogSource.determine_fog_status(
            visibility_m=5000,
            humidity=96,
            temp_f=60  # At threshold - not cold enough
        )
        assert is_foggy is False
    
    def test_no_fog_cold_but_low_humidity(self):
        """Test no fog when temp < 60F but humidity <= 95%."""
        is_foggy, status, _ = AirFogSource.determine_fog_status(
            visibility_m=5000,
            humidity=95,  # At threshold - not humid enough
            temp_f=55
        )
        assert is_foggy is False
    
    def test_light_fog_moderate_visibility(self):
        """Test LIGHT FOG when visibility between 1600m and 3000m."""
        is_foggy, status, color = AirFogSource.determine_fog_status(
            visibility_m=2500,
            humidity=70,
            temp_f=65
        )
        assert is_foggy is False
        assert status == "FOG: LIGHT"
        assert color == "YELLOW"
    
    def test_clear_conditions(self):
        """Test CLEAR when visibility >= 3000m and no humidity/temp trigger."""
        is_foggy, status, color = AirFogSource.determine_fog_status(
            visibility_m=10000,
            humidity=50,
            temp_f=70
        )
        assert is_foggy is False
        assert status == "CLEAR"
        assert color == "GREEN"
    
    def test_fog_priority_visibility_over_humidity_temp(self):
        """Visibility-based fog should trigger even with dry conditions."""
        is_foggy, status, _ = AirFogSource.determine_fog_status(
            visibility_m=500,
            humidity=30,  # Low humidity
            temp_f=80  # Warm
        )
        assert is_foggy is True
        assert status == "FOG: HEAVY"
    
    def test_typical_sf_fog_conditions(self):
        """Test typical San Francisco summer fog conditions."""
        # Morning marine layer
        is_foggy, status, color = AirFogSource.determine_fog_status(
            visibility_m=800,  # Very low visibility
            humidity=98,
            temp_f=54
        )
        assert is_foggy is True
        assert status == "FOG: HEAVY"
        assert color == "ORANGE"


class TestAirStatus:
    """Tests for air quality status determination."""
    
    def test_air_good(self):
        """Test GOOD air status."""
        status, color = AirFogSource.determine_air_status(aqi=40)
        assert status == "AIR: GOOD"
        assert color == "GREEN"
    
    def test_air_moderate(self):
        """Test MODERATE air status."""
        status, color = AirFogSource.determine_air_status(aqi=75)
        assert status == "AIR: MODERATE"
        assert color == "YELLOW"
    
    def test_air_unhealthy_orange(self):
        """Test UNHEALTHY (orange) when AQI > 100 but <= 150."""
        status, color = AirFogSource.determine_air_status(aqi=125)
        assert status == "AIR: UNHEALTHY"
        assert color == "ORANGE"
    
    def test_air_unhealthy_red(self):
        """Test UNHEALTHY (red) when AQI > 150 but <= 200."""
        status, color = AirFogSource.determine_air_status(aqi=175)
        assert status == "AIR: UNHEALTHY"
        assert color == "RED"
    
    def test_air_very_unhealthy(self):
        """Test VERY UNHEALTHY when AQI > 200 but <= 300."""
        status, color = AirFogSource.determine_air_status(aqi=250)
        assert status == "AIR: VERY UNHEALTHY"
        assert color == "PURPLE"
    
    def test_air_hazardous(self):
        """Test HAZARDOUS when AQI > 300."""
        status, color = AirFogSource.determine_air_status(aqi=350)
        assert status == "AIR: HAZARDOUS"
        assert color == "MAROON"
    
    def test_fire_trigger_at_boundary(self):
        """Test fire trigger exactly at AQI = 100 boundary."""
        # At 100 - still moderate
        status, color = AirFogSource.determine_air_status(aqi=100)
        assert status == "AIR: MODERATE"
        assert color == "YELLOW"
        
        # At 101 - triggers unhealthy/orange
        status, color = AirFogSource.determine_air_status(aqi=101)
        assert status == "AIR: UNHEALTHY"
        assert color == "ORANGE"


class TestAirFogSource:
    """Tests for AirFogSource class initialization and integration."""
    
    def test_init_default_location(self):
        """Test AirFogSource initializes with default SF coordinates."""
        source = AirFogSource()
        assert source.latitude == DEFAULT_LAT
        assert source.longitude == DEFAULT_LON
    
    def test_init_custom_location(self):
        """Test AirFogSource with custom coordinates."""
        source = AirFogSource(latitude=34.0, longitude=-118.0)
        assert source.latitude == 34.0
        assert source.longitude == -118.0
    
    def test_init_with_sensor_id(self):
        """Test AirFogSource with specific PurpleAir sensor ID."""
        source = AirFogSource(purpleair_sensor_id="12345")
        assert source.purpleair_sensor_id == "12345"
    
    @patch('src.utils.air_fog.requests.get')
    def test_fetch_openweathermap_success(self, mock_get):
        """Test successful OpenWeatherMap data fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "visibility": 5000,
            "main": {
                "humidity": 75,
                "temp": 62.5
            },
            "weather": [{"main": "Clouds"}]
        }
        mock_get.return_value = mock_response
        
        source = AirFogSource(openweathermap_api_key="test_key")
        result = source.fetch_openweathermap_data()
        
        assert result is not None
        assert result["visibility_m"] == 5000
        assert result["humidity"] == 75
        assert result["temperature_f"] == 62.5
        assert "dew_point_f" in result
    
    @patch('src.utils.air_fog.requests.get')
    def test_fetch_openweathermap_api_error(self, mock_get):
        """Test handling of OpenWeatherMap API errors."""
        mock_get.side_effect = Exception("Network error")
        
        source = AirFogSource(openweathermap_api_key="test_key")
        result = source.fetch_openweathermap_data()
        
        assert result is None
    
    @patch('src.utils.air_fog.requests.get')
    def test_fetch_purpleair_success(self, mock_get):
        """Test successful PurpleAir data fetch with sensor ID."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sensor": {
                "pm2.5_10minute": 25.5,
                "humidity": 65,
                "temperature": 70
            }
        }
        mock_get.return_value = mock_response
        
        source = AirFogSource(
            purpleair_api_key="test_key",
            purpleair_sensor_id="12345"
        )
        result = source.fetch_purpleair_data()
        
        assert result is not None
        assert result["pm2_5"] == 25.5
        assert "aqi" in result
        assert result["aqi_category"] == "MODERATE"
    
    @patch('src.utils.air_fog.requests.get')
    def test_fetch_air_fog_combined(self, mock_get):
        """Test combined air/fog data fetch."""
        # Mock both API responses
        def side_effect(url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            
            if "purpleair" in url:
                mock_response.json.return_value = {
                    "sensor": {
                        "pm2.5_10minute": 45.0,  # Unhealthy sensitive
                        "humidity": 70,
                        "temperature": 65
                    }
                }
            else:  # OpenWeatherMap
                mock_response.json.return_value = {
                    "visibility": 1200,  # Foggy
                    "main": {"humidity": 92, "temp": 55.0},
                    "weather": [{"main": "Fog"}]
                }
            
            return mock_response
        
        mock_get.side_effect = side_effect
        
        source = AirFogSource(
            purpleair_api_key="purple_key",
            openweathermap_api_key="owm_key",
            purpleair_sensor_id="12345"
        )
        result = source.fetch_air_fog_data()
        
        assert result is not None
        assert result["pm2_5_aqi"] is not None
        assert result["visibility_m"] == 1200
        assert result["is_foggy"] is True
        assert result["fog_status"] == "FOG: HEAVY"
        assert result["air_status"] == "AIR: UNHEALTHY"
    
    def test_format_message(self):
        """Test message formatting for board."""
        source = AirFogSource()
        data = {
            "pm2_5_aqi": 75,
            "visibility_m": 8000,
            "humidity": 65
        }
        message = source._format_message(data)
        
        assert "AQI:75" in message
        assert "VIS:" in message
        assert "HUM:65%" in message


class TestDewPointEdgeCases:
    """Additional edge case tests for dew point calculation."""
    
    def test_dew_point_extreme_cold(self):
        """Test dew point in extreme cold conditions."""
        # -10°F with 60% humidity
        dew_point = AirFogSource.calculate_dew_point(-10.0, 60.0)
        assert dew_point < -10.0  # Dew point should be lower than temp
    
    def test_dew_point_extreme_heat(self):
        """Test dew point in extreme heat conditions."""
        # 115°F with 30% humidity (desert)
        dew_point = AirFogSource.calculate_dew_point(115.0, 30.0)
        assert dew_point < 80  # Should be much lower due to low humidity
    
    def test_dew_point_near_100_humidity(self):
        """Test dew point at near-100% humidity."""
        dew_point = AirFogSource.calculate_dew_point(72.0, 99.0)
        # Should be very close to temperature
        assert abs(dew_point - 72.0) < 1.0
    
    def test_dew_point_very_low_humidity(self):
        """Test dew point at very low humidity."""
        dew_point = AirFogSource.calculate_dew_point(70.0, 10.0)
        # Should be extremely low
        assert dew_point < 20


class TestFogPrediction:
    """Tests for fog prediction combining dew point and visibility."""
    
    def test_fog_when_temp_near_dew_point(self):
        """Fog should be predicted when temperature approaches dew point."""
        temp_f = 55.0
        humidity = 96.0
        
        # Calculate dew point
        dew_point = AirFogSource.calculate_dew_point(temp_f, humidity)
        
        # Dew point spread should be small
        dew_point_spread = temp_f - dew_point
        assert dew_point_spread < 3  # Less than 3°F = fog likely
        
        # Verify fog status triggers
        is_foggy, status, _ = AirFogSource.determine_fog_status(
            visibility_m=2000,  # Moderate visibility
            humidity=humidity,
            temp_f=temp_f
        )
        assert is_foggy is True  # Due to humidity/temp condition
    
    def test_no_fog_large_dew_point_spread(self):
        """No fog when there's a large dew point spread."""
        temp_f = 75.0
        humidity = 40.0
        
        # Calculate dew point
        dew_point = AirFogSource.calculate_dew_point(temp_f, humidity)
        
        # Large spread
        dew_point_spread = temp_f - dew_point
        assert dew_point_spread > 20  # Large spread = no fog
        
        # Verify clear status
        is_foggy, status, _ = AirFogSource.determine_fog_status(
            visibility_m=10000,
            humidity=humidity,
            temp_f=temp_f
        )
        assert is_foggy is False
        assert status == "CLEAR"


class TestGetAirFogSource:
    """Tests for get_air_fog_source factory function."""
    
    @patch('src.utils.air_fog.Config')
    def test_get_air_fog_source_with_keys(self, mock_config):
        """Test factory returns source when API keys configured."""
        mock_config.PURPLEAIR_API_KEY = "test_purple_key"
        mock_config.OPENWEATHERMAP_API_KEY = "test_owm_key"
        mock_config.AIR_FOG_LATITUDE = 37.7749
        mock_config.AIR_FOG_LONGITUDE = -122.4194
        mock_config.PURPLEAIR_SENSOR_ID = None
        
        # Need to mock hasattr checks
        def mock_hasattr(obj, name):
            return True
        
        with patch('builtins.hasattr', mock_hasattr):
            source = get_air_fog_source()
        
        assert source is not None
        assert isinstance(source, AirFogSource)
    
    @patch('src.utils.air_fog.Config')
    def test_get_air_fog_source_no_keys(self, mock_config):
        """Test factory returns None when no API keys configured."""
        # Mock hasattr to return False (no config attributes)
        def mock_hasattr(obj, name):
            return False
        
        with patch('builtins.hasattr', mock_hasattr):
            source = get_air_fog_source()
        
        assert source is None


class TestAirFogPluginClass:
    """Tests for AirFogPlugin class (plugins/air_fog/__init__.py)."""

    @pytest.fixture
    def plugin(self):
        from plugins.air_fog import AirFogPlugin
        manifest = {"id": "air_fog", "name": "Air & Fog", "version": "1.0.0"}
        return AirFogPlugin(manifest)

    def test_plugin_id(self, plugin):
        assert plugin.plugin_id == "air_fog"

    def test_validate_config_purpleair_key(self, plugin):
        assert plugin.validate_config({"purpleair_api_key": "k"}) == []

    def test_validate_config_owm_key(self, plugin):
        assert plugin.validate_config({"openweathermap_api_key": "k"}) == []

    def test_validate_config_no_keys(self, plugin):
        errors = plugin.validate_config({})
        assert len(errors) == 1

    def test_calculate_dew_point_100_humidity(self):
        from plugins.air_fog import AirFogPlugin
        dp = AirFogPlugin.calculate_dew_point(68.0, 100.0)
        assert abs(dp - 68.0) < 0.5

    def test_calculate_dew_point_low_humidity(self):
        from plugins.air_fog import AirFogPlugin
        dp = AirFogPlugin.calculate_dew_point(70.0, 50.0)
        assert dp < 70.0

    def test_calculate_aqi_good(self):
        from plugins.air_fog import AirFogPlugin
        aqi, cat, color = AirFogPlugin.calculate_aqi_from_pm25(5.0)
        assert cat == "GOOD"
        assert color == "GREEN"

    def test_calculate_aqi_moderate(self):
        from plugins.air_fog import AirFogPlugin
        aqi, cat, _ = AirFogPlugin.calculate_aqi_from_pm25(20.0)
        assert cat == "MODERATE"

    def test_calculate_aqi_unhealthy_sensitive(self):
        from plugins.air_fog import AirFogPlugin
        aqi, cat, _ = AirFogPlugin.calculate_aqi_from_pm25(40.0)
        assert cat == "UNHEALTHY_SENSITIVE"

    def test_calculate_aqi_unhealthy(self):
        from plugins.air_fog import AirFogPlugin
        aqi, cat, _ = AirFogPlugin.calculate_aqi_from_pm25(100.0)
        assert cat == "UNHEALTHY"

    def test_calculate_aqi_very_unhealthy(self):
        from plugins.air_fog import AirFogPlugin
        aqi, cat, _ = AirFogPlugin.calculate_aqi_from_pm25(200.0)
        assert cat == "VERY_UNHEALTHY"

    def test_calculate_aqi_hazardous(self):
        from plugins.air_fog import AirFogPlugin
        aqi, cat, _ = AirFogPlugin.calculate_aqi_from_pm25(300.0)
        assert cat == "HAZARDOUS"

    def test_calculate_aqi_extreme(self):
        from plugins.air_fog import AirFogPlugin
        aqi, cat, _ = AirFogPlugin.calculate_aqi_from_pm25(600.0)
        assert aqi == 500

    def test_calculate_aqi_negative(self):
        from plugins.air_fog import AirFogPlugin
        aqi, _, _ = AirFogPlugin.calculate_aqi_from_pm25(-5.0)
        assert aqi == 0

    def test_determine_fog_status_foggy(self, plugin):
        is_foggy, status, color = plugin.determine_fog_status(1000, 70, 65)
        assert is_foggy is True
        assert status == "FOG"
        assert color == "ORANGE"

    def test_determine_fog_status_humidity_temp(self, plugin):
        is_foggy, status, _ = plugin.determine_fog_status(5000, 96, 55)
        assert is_foggy is True

    def test_determine_fog_status_haze(self, plugin):
        is_foggy, status, color = plugin.determine_fog_status(2500, 70, 65)
        assert is_foggy is False
        assert status == "HAZE"
        assert color == "YELLOW"

    def test_determine_fog_status_clear(self, plugin):
        is_foggy, status, color = plugin.determine_fog_status(10000, 50, 70)
        assert is_foggy is False
        assert status == "CLEAR"
        assert color == "GREEN"

    def test_determine_air_status_good(self, plugin):
        assert plugin.determine_air_status(40) == ("GOOD", "GREEN")

    def test_determine_air_status_moderate(self, plugin):
        assert plugin.determine_air_status(75) == ("MODERATE", "YELLOW")

    def test_determine_air_status_moderate_high(self, plugin):
        assert plugin.determine_air_status(125) == ("MODERATE HIGH", "ORANGE")

    def test_determine_air_status_unhealthy(self, plugin):
        assert plugin.determine_air_status(175) == ("UNHEALTHY", "RED")

    def test_determine_air_status_very_unhealthy(self, plugin):
        assert plugin.determine_air_status(250) == ("VERY UNHEALTHY", "PURPLE")

    def test_determine_air_status_hazardous(self, plugin):
        assert plugin.determine_air_status(350) == ("HAZARDOUS", "MAROON")

    def test_color_to_code(self, plugin):
        assert plugin._color_to_code("GREEN") == 66
        assert plugin._color_to_code("YELLOW") == 65
        assert plugin._color_to_code("ORANGE") == 64
        assert plugin._color_to_code("RED") == 63
        assert plugin._color_to_code("PURPLE") == 68
        assert plugin._color_to_code("MAROON") == 68
        assert plugin._color_to_code("UNKNOWN") == 66

    def test_fetch_data_both_sources(self, plugin):
        plugin._config = {
            "purpleair_api_key": "test",
            "openweathermap_api_key": "test",
        }
        pa_data = {"aqi": 75, "pm2_5": 20.0, "aqi_category": "MODERATE", "aqi_color": "YELLOW"}
        owm_data = {"visibility_m": 5000, "humidity": 75, "temperature_f": 62.5}
        with patch.object(plugin, '_fetch_purpleair_data', return_value=pa_data), \
             patch.object(plugin, '_fetch_openweathermap_data', return_value=owm_data):
            result = plugin.fetch_data()
            assert result.available
            assert result.data["aqi"] == 75
            assert "VIS:" in result.data["formatted"]

    def test_fetch_data_no_sources(self, plugin):
        with patch.object(plugin, '_fetch_purpleair_data', return_value=None), \
             patch.object(plugin, '_fetch_openweathermap_data', return_value=None):
            result = plugin.fetch_data()
            assert not result.available

    def test_fetch_purpleair_data_with_sensor_id(self, plugin):
        """Test _fetch_purpleair_data with specific sensor ID."""
        plugin._config = {
            "purpleair_api_key": "test_key",
            "purpleair_sensor_id": "12345"
        }
        mock_resp = Mock()
        mock_resp.json.return_value = {
            "sensor": {"pm2.5_10minute": 25.5}
        }
        with patch('plugins.air_fog.requests.get', return_value=mock_resp):
            result = plugin._fetch_purpleair_data()
            assert result is not None
            assert result["pm2_5"] == 25.5
            assert "aqi" in result

    def test_fetch_purpleair_data_no_sensor_id(self, plugin):
        """Test _fetch_purpleair_data without sensor ID (nearby search)."""
        plugin._config = {
            "purpleair_api_key": "test_key",
            "latitude": 37.7749,
            "longitude": -122.4194
        }
        mock_resp = Mock()
        mock_resp.json.return_value = {
            "data": [[30.0], [35.0], [28.0]]
        }
        with patch('plugins.air_fog.requests.get', return_value=mock_resp):
            result = plugin._fetch_purpleair_data()
            assert result is not None
            assert result["pm2_5"] == 31.0  # Average of 30, 35, 28

    def test_fetch_purpleair_data_no_api_key(self, plugin):
        """Test _fetch_purpleair_data without API key."""
        plugin._config = {}
        result = plugin._fetch_purpleair_data()
        assert result is None

    def test_fetch_purpleair_data_api_error(self, plugin):
        """Test _fetch_purpleair_data with API error."""
        plugin._config = {
            "purpleair_api_key": "test_key",
            "purpleair_sensor_id": "12345"
        }
        with patch('plugins.air_fog.requests.get', side_effect=Exception("API error")):
            result = plugin._fetch_purpleair_data()
            assert result is None

    def test_fetch_purpleair_data_no_nearby_sensors(self, plugin):
        """Test _fetch_purpleair_data with no nearby sensors."""
        plugin._config = {
            "purpleair_api_key": "test_key",
            "latitude": 37.7749,
            "longitude": -122.4194
        }
        mock_resp = Mock()
        mock_resp.json.return_value = {"data": []}
        with patch('plugins.air_fog.requests.get', return_value=mock_resp):
            result = plugin._fetch_purpleair_data()
            assert result is None

    def test_fetch_openweathermap_data_success(self, plugin):
        """Test _fetch_openweathermap_data with successful response."""
        plugin._config = {
            "openweathermap_api_key": "test_key",
            "latitude": 37.7749,
            "longitude": -122.4194
        }
        mock_resp = Mock()
        mock_resp.json.return_value = {
            "visibility": 10000,
            "main": {"humidity": 70, "temp": 293.15}
        }
        with patch('plugins.air_fog.requests.get', return_value=mock_resp):
            result = plugin._fetch_openweathermap_data()
            assert result is not None
            assert result["visibility_m"] == 10000
            assert result["humidity"] == 70

    def test_fetch_openweathermap_data_no_api_key(self, plugin):
        """Test _fetch_openweathermap_data without API key."""
        plugin._config = {}
        result = plugin._fetch_openweathermap_data()
        assert result is None

    def test_fetch_openweathermap_data_api_error(self, plugin):
        """Test _fetch_openweathermap_data with API error."""
        plugin._config = {
            "openweathermap_api_key": "test_key",
            "latitude": 37.7749,
            "longitude": -122.4194
        }
        with patch('plugins.air_fog.requests.get', side_effect=Exception("API error")):
            result = plugin._fetch_openweathermap_data()
            assert result is None

