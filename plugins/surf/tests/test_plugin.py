"""Tests for surf data source."""

import pytest
from unittest.mock import Mock, patch
from src.utils.surf import SurfSource, get_surf_source, OCEAN_BEACH_LAT, OCEAN_BEACH_LON


class TestSurfQuality:
    """Tests for surf quality calculation - the core logic."""
    
    def test_excellent_surf_high_period_low_wind(self):
        """Test EXCELLENT rating: swell_period > 12s AND wind_speed < 12mph."""
        # Perfect conditions: 15 second period, 5 mph wind
        quality, color = SurfSource._calculate_surf_quality(swell_period=15, wind_speed=5)
        assert quality == "EXCELLENT"
        assert color == "GREEN"
    
    def test_excellent_surf_at_thresholds(self):
        """Test EXCELLENT rating just above thresholds."""
        # Just above period threshold (12.1s) and just below wind threshold (11.9mph)
        quality, color = SurfSource._calculate_surf_quality(swell_period=12.1, wind_speed=11.9)
        assert quality == "EXCELLENT"
        assert color == "GREEN"
    
    def test_not_excellent_when_period_at_threshold(self):
        """Test that exactly 12s period doesn't qualify as EXCELLENT (must be > 12)."""
        quality, color = SurfSource._calculate_surf_quality(swell_period=12.0, wind_speed=5)
        # At threshold (not above), should fall to GOOD
        assert quality == "GOOD"
        assert color == "YELLOW"
    
    def test_not_excellent_when_wind_at_threshold(self):
        """Test that exactly 12mph wind doesn't qualify as EXCELLENT (must be < 12)."""
        quality, color = SurfSource._calculate_surf_quality(swell_period=15, wind_speed=12.0)
        # At threshold (not below), should fall to GOOD
        assert quality == "GOOD"
        assert color == "YELLOW"
    
    def test_good_surf_moderate_conditions(self):
        """Test GOOD rating: swell_period > 10s AND wind_speed < 15mph."""
        # Good conditions: 11 second period, 14 mph wind
        quality, color = SurfSource._calculate_surf_quality(swell_period=11, wind_speed=14)
        assert quality == "GOOD"
        assert color == "YELLOW"
    
    def test_good_surf_just_above_period_threshold(self):
        """Test GOOD rating with period just above 10s."""
        quality, color = SurfSource._calculate_surf_quality(swell_period=10.1, wind_speed=14)
        assert quality == "GOOD"
        assert color == "YELLOW"
    
    def test_fair_surf_decent_swell(self):
        """Test FAIR rating: swell_period > 8s (even with higher wind)."""
        # Decent swell (9s) but windy (18 mph)
        quality, color = SurfSource._calculate_surf_quality(swell_period=9, wind_speed=18)
        assert quality == "FAIR"
        assert color == "ORANGE"
    
    def test_fair_surf_low_wind(self):
        """Test FAIR rating: wind_speed < 20mph (even with short period)."""
        # Short period (5s) but calm winds (15 mph)
        quality, color = SurfSource._calculate_surf_quality(swell_period=5, wind_speed=15)
        assert quality == "FAIR"
        assert color == "ORANGE"
    
    def test_poor_surf_bad_conditions(self):
        """Test POOR rating: short period AND high wind."""
        # Bad conditions: 5 second period, 25 mph wind
        quality, color = SurfSource._calculate_surf_quality(swell_period=5, wind_speed=25)
        assert quality == "POOR"
        assert color == "RED"
    
    def test_poor_surf_very_short_period_high_wind(self):
        """Test POOR rating with very bad conditions."""
        # Terrible conditions: 3 second period, 30 mph wind
        quality, color = SurfSource._calculate_surf_quality(swell_period=3, wind_speed=30)
        assert quality == "POOR"
        assert color == "RED"
    
    def test_poor_surf_at_boundaries(self):
        """Test POOR rating at exact boundary values."""
        # At thresholds: 8s period, 20 mph wind (neither condition met for FAIR)
        quality, color = SurfSource._calculate_surf_quality(swell_period=8, wind_speed=20)
        assert quality == "POOR"
        assert color == "RED"
    
    def test_zero_values(self):
        """Test handling of zero values (flat ocean, no wind)."""
        quality, color = SurfSource._calculate_surf_quality(swell_period=0, wind_speed=0)
        # Zero period with zero wind should be FAIR (wind < 20)
        assert quality == "FAIR"
        assert color == "ORANGE"


class TestCardinalDirections:
    """Tests for wind direction conversion."""
    
    def test_north(self):
        """Test 0 degrees = North."""
        assert SurfSource._degrees_to_cardinal(0) == "N"
        assert SurfSource._degrees_to_cardinal(360) == "N"
    
    def test_northeast(self):
        """Test 45 degrees = Northeast."""
        assert SurfSource._degrees_to_cardinal(45) == "NE"
    
    def test_east(self):
        """Test 90 degrees = East."""
        assert SurfSource._degrees_to_cardinal(90) == "E"
    
    def test_southeast(self):
        """Test 135 degrees = Southeast."""
        assert SurfSource._degrees_to_cardinal(135) == "SE"
    
    def test_south(self):
        """Test 180 degrees = South."""
        assert SurfSource._degrees_to_cardinal(180) == "S"
    
    def test_southwest(self):
        """Test 225 degrees = Southwest."""
        assert SurfSource._degrees_to_cardinal(225) == "SW"
    
    def test_west(self):
        """Test 270 degrees = West."""
        assert SurfSource._degrees_to_cardinal(270) == "W"
    
    def test_northwest(self):
        """Test 315 degrees = Northwest."""
        assert SurfSource._degrees_to_cardinal(315) == "NW"
    
    def test_rounding_to_nearest(self):
        """Test that degrees round to nearest cardinal direction."""
        # 22 degrees should round to N (closest to 0)
        assert SurfSource._degrees_to_cardinal(22) == "N"
        # 23 degrees should round to NE (closest to 45)
        assert SurfSource._degrees_to_cardinal(23) == "NE"


class TestMessageFormatting:
    """Tests for message formatting."""
    
    def test_format_message_standard(self):
        """Test standard message format."""
        result = SurfSource._format_message(wave_height=4.5, swell_period=12)
        assert result == "OB SURF: 4.5ft @ 12s"
    
    def test_format_message_rounds_period(self):
        """Test that period is rounded to integer."""
        result = SurfSource._format_message(wave_height=3.2, swell_period=10.6)
        assert result == "OB SURF: 3.2ft @ 11s"
    
    def test_format_message_small_waves(self):
        """Test message with small waves."""
        result = SurfSource._format_message(wave_height=1.5, swell_period=8)
        assert result == "OB SURF: 1.5ft @ 8s"
    
    def test_format_message_zero_values(self):
        """Test message with zero values."""
        result = SurfSource._format_message(wave_height=0, swell_period=0)
        assert result == "OB SURF: 0ft @ 0s"


class TestSurfSource:
    """Tests for SurfSource class initialization and methods."""
    
    def test_init_default_location(self):
        """Test SurfSource initializes with Ocean Beach coordinates by default."""
        source = SurfSource()
        assert source.latitude == OCEAN_BEACH_LAT
        assert source.longitude == OCEAN_BEACH_LON
    
    def test_init_custom_location(self):
        """Test SurfSource with custom coordinates."""
        source = SurfSource(latitude=34.0, longitude=-118.0)
        assert source.latitude == 34.0
        assert source.longitude == -118.0
    
    @patch('src.utils.surf.requests.get')
    def test_fetch_surf_data_success(self, mock_get):
        """Test successful surf data fetch."""
        # Mock marine API response
        marine_response = Mock()
        marine_response.status_code = 200
        marine_response.json.return_value = {
            "current": {
                "wave_height": 1.5,
                "swell_wave_period": 14.0
            },
            "daily": {
                "wave_height_max": [1.8],
                "swell_wave_period_max": [15.0]
            }
        }
        
        # Mock weather API response (for wind)
        weather_response = Mock()
        weather_response.status_code = 200
        weather_response.json.return_value = {
            "current": {
                "wind_speed_10m": 8.0,
                "wind_direction_10m": 270
            }
        }
        
        # Return different responses for different URLs
        def side_effect(url, **kwargs):
            if "marine-api" in url:
                return marine_response
            else:
                return weather_response
        
        mock_get.side_effect = side_effect
        
        source = SurfSource()
        result = source.fetch_surf_data()
        
        assert result is not None
        assert result["wave_height"] == 5.9  # 1.8m * 3.28084 = ~5.9ft
        assert result["wave_height_m"] == 1.8
        assert result["swell_period"] == 15.0
        assert result["wind_speed"] == 8.0
        assert result["wind_direction"] == 270
        assert result["wind_direction_cardinal"] == "W"
        assert result["quality"] == "EXCELLENT"  # 15s period, 8mph wind
        assert result["quality_color"] == "GREEN"
        assert "OB SURF:" in result["formatted_message"]
        assert "@ 15s" in result["formatted_message"]
    
    @patch('src.utils.surf.requests.get')
    def test_fetch_surf_data_bad_conditions(self, mock_get):
        """Test surf data fetch with poor conditions."""
        # Mock marine API response with short period
        marine_response = Mock()
        marine_response.status_code = 200
        marine_response.json.return_value = {
            "current": {
                "wave_height": 1.0,
                "swell_wave_period": 5.0
            },
            "daily": {
                "wave_height_max": [1.2],
                "swell_wave_period_max": [6.0]
            }
        }
        
        # Mock weather API response with high wind
        weather_response = Mock()
        weather_response.status_code = 200
        weather_response.json.return_value = {
            "current": {
                "wind_speed_10m": 25.0,
                "wind_direction_10m": 315
            }
        }
        
        def side_effect(url, **kwargs):
            if "marine-api" in url:
                return marine_response
            else:
                return weather_response
        
        mock_get.side_effect = side_effect
        
        source = SurfSource()
        result = source.fetch_surf_data()
        
        assert result is not None
        assert result["quality"] == "POOR"  # 6s period, 25mph wind
        assert result["quality_color"] == "RED"
    
    @patch('src.utils.surf.requests.get')
    def test_fetch_surf_data_api_error(self, mock_get):
        """Test handling of API errors."""
        mock_get.side_effect = Exception("Network error")
        
        source = SurfSource()
        result = source.fetch_surf_data()
        
        assert result is None
    
    @patch('src.utils.surf.requests.get')
    def test_fetch_surf_data_invalid_response(self, mock_get):
        """Test handling of invalid response format."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"invalid": "data"}
        mock_get.return_value = mock_response
        
        source = SurfSource()
        result = source.fetch_surf_data()
        
        # Should handle missing keys gracefully
        # May return None or partial data depending on implementation
        # The important thing is it doesn't raise an exception


class TestGetSurfSource:
    """Tests for get_surf_source factory function."""
    
    def test_get_surf_source_returns_instance(self):
        """Test that get_surf_source returns a valid SurfSource."""
        source = get_surf_source()
        
        assert source is not None
        assert isinstance(source, SurfSource)
        assert source.latitude == OCEAN_BEACH_LAT
        assert source.longitude == OCEAN_BEACH_LON


class TestSurfQualityEdgeCases:
    """Additional edge case tests for surf quality."""
    
    def test_excellent_with_offshore_winds(self):
        """Offshore (light) winds with long period = excellent."""
        # Offshore winds are typically best for surfing
        quality, color = SurfSource._calculate_surf_quality(swell_period=16, wind_speed=3)
        assert quality == "EXCELLENT"
        assert color == "GREEN"
    
    def test_good_to_excellent_boundary(self):
        """Test the boundary between GOOD and EXCELLENT."""
        # Just below excellent period threshold
        quality, color = SurfSource._calculate_surf_quality(swell_period=11.9, wind_speed=5)
        assert quality == "GOOD"
        assert color == "YELLOW"
        
        # Just above excellent period threshold
        quality, color = SurfSource._calculate_surf_quality(swell_period=12.1, wind_speed=5)
        assert quality == "EXCELLENT"
        assert color == "GREEN"
    
    def test_fair_to_poor_boundary(self):
        """Test the boundary between FAIR and POOR."""
        # Just above fair swell threshold (> 8s)
        quality, color = SurfSource._calculate_surf_quality(swell_period=8.1, wind_speed=25)
        assert quality == "FAIR"
        assert color == "ORANGE"
        
        # Just below fair swell threshold AND just above fair wind threshold
        quality, color = SurfSource._calculate_surf_quality(swell_period=7.9, wind_speed=20.1)
        assert quality == "POOR"
        assert color == "RED"
    
    def test_high_wind_overrides_good_swell(self):
        """Test that very high wind degrades excellent swell."""
        # Great swell but too windy for excellent
        quality, color = SurfSource._calculate_surf_quality(swell_period=18, wind_speed=13)
        assert quality == "GOOD"  # Downgrades from EXCELLENT due to wind
        assert color == "YELLOW"
    
    def test_negative_values_handled(self):
        """Test handling of negative values (shouldn't happen but be safe)."""
        # Negative values should be treated similar to zero
        quality, color = SurfSource._calculate_surf_quality(swell_period=-1, wind_speed=-1)
        # With negative/low wind, should at least be FAIR
        assert quality == "FAIR"
        assert color == "ORANGE"


class TestSurfPluginClass:
    """Tests for SurfPlugin class (plugins/surf/__init__.py)."""

    @pytest.fixture
    def plugin(self):
        from plugins.surf import SurfPlugin
        manifest = {"id": "surf", "name": "Surf", "version": "1.0.0"}
        return SurfPlugin(manifest)

    def test_plugin_id(self, plugin):
        assert plugin.plugin_id == "surf"

    def test_validate_config_defaults(self, plugin):
        assert plugin.validate_config({}) == []

    def test_validate_config_valid(self, plugin):
        assert plugin.validate_config({"latitude": 37.0, "longitude": -122.0}) == []

    def test_validate_config_bad_latitude(self, plugin):
        errors = plugin.validate_config({"latitude": 100, "longitude": 0})
        assert any("Latitude" in e for e in errors)

    def test_validate_config_bad_longitude(self, plugin):
        errors = plugin.validate_config({"latitude": 0, "longitude": 200})
        assert any("Longitude" in e for e in errors)

    def test_calculate_quality_excellent(self, plugin):
        q, c = plugin._calculate_quality(15, 5)
        assert q == "EXCELLENT"
        assert c == "GREEN"

    def test_calculate_quality_good(self, plugin):
        q, c = plugin._calculate_quality(11, 14)
        assert q == "GOOD"
        assert c == "YELLOW"

    def test_calculate_quality_fair_swell(self, plugin):
        q, c = plugin._calculate_quality(9, 18)
        assert q == "FAIR"
        assert c == "ORANGE"

    def test_calculate_quality_fair_wind(self, plugin):
        q, c = plugin._calculate_quality(5, 15)
        assert q == "FAIR"

    def test_calculate_quality_poor(self, plugin):
        q, c = plugin._calculate_quality(5, 25)
        assert q == "POOR"
        assert c == "RED"

    def test_degrees_to_cardinal(self, plugin):
        assert plugin._degrees_to_cardinal(0) == "N"
        assert plugin._degrees_to_cardinal(90) == "E"
        assert plugin._degrees_to_cardinal(180) == "S"
        assert plugin._degrees_to_cardinal(270) == "W"
        assert plugin._degrees_to_cardinal(45) == "NE"

    def test_fetch_data_success(self, plugin):
        marine = {
            "current": {"wave_height": 1.5, "swell_wave_period": 14.0},
            "daily": {"wave_height_max": [1.8], "swell_wave_period_max": [15.0]}
        }
        wind = {"wind_speed_mph": 8.0, "wind_direction": 270}
        with patch.object(plugin, '_fetch_marine_data', return_value=marine), \
             patch.object(plugin, '_fetch_wind_data', return_value=wind):
            result = plugin.fetch_data()
            assert result.available
            assert result.data["quality"] == "EXCELLENT"
            assert result.data["wind_direction"] == "W"
            assert "SURF:" in result.data["formatted"]

    def test_fetch_data_no_daily(self, plugin):
        marine = {
            "current": {"wave_height": 1.5, "swell_wave_period": 10.0},
            "daily": {}
        }
        with patch.object(plugin, '_fetch_marine_data', return_value=marine), \
             patch.object(plugin, '_fetch_wind_data', return_value=None):
            result = plugin.fetch_data()
            assert result.available
            assert result.data["wave_height"] > 0

    def test_fetch_data_no_marine(self, plugin):
        with patch.object(plugin, '_fetch_marine_data', return_value=None), \
             patch.object(plugin, '_fetch_wind_data', return_value=None):
            result = plugin.fetch_data()
            assert not result.available

    def test_fetch_data_processing_error(self, plugin):
        marine = {"current": {}, "daily": {"wave_height_max": ["not_a_number"]}}
        with patch.object(plugin, '_fetch_marine_data', return_value=marine), \
             patch.object(plugin, '_fetch_wind_data', return_value=None):
            result = plugin.fetch_data()
            assert not result.available

    def test_fetch_marine_data_success(self, plugin):
        """Test _fetch_marine_data with successful API call."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "current": {"wave_height": 1.5, "swell_wave_period": 12.0},
            "daily": {"wave_height_max": [2.0], "swell_wave_period_max": [13.0]}
        }
        with patch('plugins.surf.requests.get', return_value=mock_response):
            result = plugin._fetch_marine_data()
            assert result is not None
            assert "current" in result
            assert "daily" in result

    def test_fetch_marine_data_api_error(self, plugin):
        """Test _fetch_marine_data with API error."""
        with patch('plugins.surf.requests.get', side_effect=Exception("API error")):
            result = plugin._fetch_marine_data()
            assert result is None

    def test_fetch_wind_data_success(self, plugin):
        """Test _fetch_wind_data with successful API call."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "current": {"wind_speed_10m": 10.0, "wind_direction_10m": 180}
        }
        with patch('plugins.surf.requests.get', return_value=mock_response):
            result = plugin._fetch_wind_data()
            assert result is not None
            assert result["wind_speed_mph"] == 10.0
            assert result["wind_direction"] == 180

    def test_fetch_wind_data_api_error(self, plugin):
        """Test _fetch_wind_data with API error."""
        with patch('plugins.surf.requests.get', side_effect=Exception("API error")):
            result = plugin._fetch_wind_data()
            assert result is None

    def test_get_formatted_display_success(self, plugin):
        """Test get_formatted_display with successful data."""
        plugin._cache = {
            "wave_height": "2.0",
            "swell_period": "12.0",
            "quality": "EXCELLENT",
            "wind_speed": "8.0",
            "wind_direction": "W"
        }
        with patch.object(plugin, 'fetch_data', return_value=Mock(available=True, data=plugin._cache)):
            lines = plugin.get_formatted_display()
            assert lines is not None
            assert len(lines) == 6
            assert "SURF CONDITIONS" in lines[0]
            assert "WAVES:" in lines[2]
            assert "SWELL:" in lines[3]
            assert "QUALITY:" in lines[4]
            assert "WIND:" in lines[5]

    def test_get_formatted_display_no_data(self, plugin):
        """Test get_formatted_display when fetch fails."""
        with patch.object(plugin, 'fetch_data', return_value=Mock(available=False, data=None)):
            lines = plugin.get_formatted_display()
            assert lines is None

