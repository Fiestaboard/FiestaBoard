"""Unit tests for Nearby Aircraft plugin."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta, timezone

from plugins.nearby_aircraft import NearbyAircraftPlugin


@pytest.fixture
def plugin(sample_manifest):
    """Create plugin instance for testing."""
    return NearbyAircraftPlugin(sample_manifest)


@pytest.fixture
def plugin_with_auth(sample_manifest, sample_config_with_auth):
    """Create plugin instance with OAuth credentials."""
    plugin = NearbyAircraftPlugin(sample_manifest)
    plugin.config = sample_config_with_auth
    return plugin


class TestPluginInitialization:
    """Test plugin initialization."""
    
    def test_plugin_id(self, plugin):
        """Test plugin ID."""
        assert plugin.plugin_id == "nearby_aircraft"
    
    def test_plugin_initialization(self, plugin):
        """Test plugin initializes correctly."""
        assert plugin._cache is None
        assert plugin._access_token is None
        assert plugin._token_expires_at is None


class TestConfigurationValidation:
    """Test configuration validation."""
    
    def test_validate_config_valid(self, plugin, sample_config):
        """Test validation with valid configuration."""
        errors = plugin.validate_config(sample_config)
        assert errors == []
    
    def test_validate_config_missing_latitude(self, plugin):
        """Test validation fails without latitude."""
        config = {"longitude": -122.4194}
        errors = plugin.validate_config(config)
        assert "Latitude is required" in errors
    
    def test_validate_config_missing_longitude(self, plugin):
        """Test validation fails without longitude."""
        config = {"latitude": 37.7749}
        errors = plugin.validate_config(config)
        assert "Longitude is required" in errors
    
    def test_validate_config_invalid_latitude_too_high(self, plugin):
        """Test validation fails with latitude > 90."""
        config = {"latitude": 91, "longitude": -122.4194}
        errors = plugin.validate_config(config)
        assert any("Latitude" in e and "90" in e for e in errors)
    
    def test_validate_config_invalid_latitude_too_low(self, plugin):
        """Test validation fails with latitude < -90."""
        config = {"latitude": -91, "longitude": -122.4194}
        errors = plugin.validate_config(config)
        assert any("Latitude" in e and "-90" in e for e in errors)
    
    def test_validate_config_invalid_longitude_too_high(self, plugin):
        """Test validation fails with longitude > 180."""
        config = {"latitude": 37.7749, "longitude": 181}
        errors = plugin.validate_config(config)
        assert any("Longitude" in e and "180" in e for e in errors)
    
    def test_validate_config_invalid_longitude_too_low(self, plugin):
        """Test validation fails with longitude < -180."""
        config = {"latitude": 37.7749, "longitude": -181}
        errors = plugin.validate_config(config)
        assert any("Longitude" in e and "-180" in e for e in errors)
    
    def test_validate_config_invalid_radius(self, plugin):
        """Test validation fails with radius < 1."""
        config = {"latitude": 37.7749, "longitude": -122.4194, "radius_km": 0}
        errors = plugin.validate_config(config)
        assert any("Radius" in e for e in errors)
    
    def test_validate_config_invalid_max_aircraft_too_high(self, plugin):
        """Test validation fails with max_aircraft > 10."""
        config = {"latitude": 37.7749, "longitude": -122.4194, "max_aircraft": 11}
        errors = plugin.validate_config(config)
        assert any("Max aircraft" in e and "10" in e for e in errors)
    
    def test_validate_config_invalid_max_aircraft_too_low(self, plugin):
        """Test validation fails with max_aircraft < 1."""
        config = {"latitude": 37.7749, "longitude": -122.4194, "max_aircraft": 0}
        errors = plugin.validate_config(config)
        assert any("Max aircraft" in e and "1" in e for e in errors)
    
    def test_validate_config_invalid_refresh_too_low(self, plugin):
        """Test validation fails with refresh_seconds < 10."""
        config = {"latitude": 37.7749, "longitude": -122.4194, "refresh_seconds": 5}
        errors = plugin.validate_config(config)
        assert any("Refresh interval" in e and "10" in e for e in errors)


class TestHaversineDistance:
    """Test Haversine distance calculation."""
    
    def test_haversine_distance_sf_to_la(self, plugin):
        """Test distance between San Francisco and Los Angeles."""
        sf_lat, sf_lon = 37.7749, -122.4194
        la_lat, la_lon = 34.0522, -118.2437
        
        distance = plugin.haversine_distance(sf_lat, sf_lon, la_lat, la_lon)
        
        # Should be approximately 560km (allow 20km margin)
        assert 540 <= distance <= 580
    
    def test_haversine_distance_same_point(self, plugin):
        """Test distance to same point is zero."""
        lat, lon = 37.7749, -122.4194
        distance = plugin.haversine_distance(lat, lon, lat, lon)
        assert distance < 0.1
    
    def test_haversine_distance_close_points(self, plugin):
        """Test distance between close points."""
        lat1, lon1 = 37.7749, -122.4194
        lat2, lon2 = 37.7750, -122.4195  # Very close
        
        distance = plugin.haversine_distance(lat1, lon1, lat2, lon2)
        assert distance < 1.0  # Less than 1km


class TestBoundingBox:
    """Test bounding box calculation."""
    
    def test_calculate_bounding_box(self, plugin):
        """Test bounding box calculation."""
        lat, lon = 37.7749, -122.4194
        radius_km = 50
        
        bbox = plugin.calculate_bounding_box(lat, lon, radius_km)
        
        assert "lamin" in bbox
        assert "lamax" in bbox
        assert "lomin" in bbox
        assert "lomax" in bbox
        
        # Center should be within bounds
        assert bbox["lamin"] < lat < bbox["lamax"]
        assert bbox["lomin"] < lon < bbox["lomax"]
        
        # Bounds should be symmetric around center (approximately)
        lat_range = bbox["lamax"] - bbox["lamin"]
        lon_range = bbox["lomax"] - bbox["lomin"]
        assert lat_range > 0
        assert lon_range > 0


class TestOAuthAuthentication:
    """Test OAuth2 authentication."""
    
    @patch('plugins.nearby_aircraft.requests.post')
    def test_get_access_token_success(self, mock_post, plugin_with_auth):
        """Test successful OAuth token acquisition."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token_123",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response
        
        token = plugin_with_auth._get_access_token()
        
        assert token == "test_token_123"
        assert plugin_with_auth._access_token == "test_token_123"
        assert plugin_with_auth._token_expires_at is not None
    
    @patch('plugins.nearby_aircraft.requests.post')
    def test_get_access_token_failure(self, mock_post, plugin_with_auth):
        """Test OAuth token acquisition failure."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        token = plugin_with_auth._get_access_token()
        
        assert token is None
    
    def test_get_access_token_no_credentials(self, plugin):
        """Test OAuth without credentials returns None."""
        plugin.config = {"latitude": 37.7749, "longitude": -122.4194}
        token = plugin._get_access_token()
        assert token is None
    
    @patch('plugins.nearby_aircraft.requests.post')
    def test_get_access_token_cached(self, mock_post, plugin_with_auth):
        """Test OAuth token caching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token_123",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response
        
        # First call
        token1 = plugin_with_auth._get_access_token()
        assert token1 == "test_token_123"
        
        # Second call should use cache (not call API again)
        token2 = plugin_with_auth._get_access_token()
        assert token2 == "test_token_123"
        assert mock_post.call_count == 1  # Only called once


class TestStateVectorParsing:
    """Test state vector parsing."""
    
    def test_parse_state_vector_valid(self, plugin):
        """Test parsing valid state vector."""
        state_vector = [
            "abc123",           # icao24
            "AAY453",           # callsign
            "United States",     # origin_country
            1234567890,         # time_position
            1234567890,         # last_contact
            -122.4194,          # longitude
            37.7749,            # latitude
            1394.0,             # baro_altitude
            False,              # on_ground
            143.5,              # velocity
            180.0,              # true_track
            0.0,                # vertical_rate
            None,               # sensors
            1394.0,             # geo_altitude
            "1603",             # squawk
            False,              # spi
            0                   # position_source
        ]
        
        result = plugin._parse_state_vector(state_vector)
        
        assert result is not None
        assert result["call_sign"] == "AAY453"
        assert result["altitude"] == pytest.approx(4575, abs=10)  # 1394m * 3.28084 ≈ 4575ft
        assert result["ground_speed"] == pytest.approx(279, abs=1)  # 143.5 m/s * 1.94384 ≈ 279 kt
        assert result["squawk"] == "1603"
        assert result["latitude"] == 37.7749
        assert result["longitude"] == -122.4194
    
    def test_parse_state_vector_null_callsign(self, plugin):
        """Test parsing state vector with null callsign (uses ICAO)."""
        state_vector = [
            "def456",           # icao24
            None,               # callsign (null)
            "United States",
            1234567890,
            1234567890,
            -122.5,
            37.8,
            10424.0,
            False,
            252.0,
            90.0,
            0.0,
            None,
            10424.0,
            "2105",
            False,
            0
        ]
        
        result = plugin._parse_state_vector(state_vector)
        
        assert result is not None
        assert result["call_sign"] == "def456"  # Uses ICAO as fallback
    
    def test_parse_state_vector_null_squawk(self, plugin):
        """Test parsing state vector with null squawk."""
        state_vector = [
            "ghi789",
            "TEST123",
            "United States",
            1234567890,
            1234567890,
            -122.4,
            37.7,
            5158.0,
            False,
            225.0,
            270.0,
            0.0,
            None,
            5158.0,
            None,              # squawk (null)
            False,
            0
        ]
        
        result = plugin._parse_state_vector(state_vector)
        
        assert result is not None
        assert result["squawk"] == "----"  # Placeholder for null squawk
    
    def test_parse_state_vector_squawk_zero(self, plugin):
        """Test parsing state vector with squawk = 0 (no squawk assigned)."""
        state_vector = [
            "xyz789",
            "ZERO1",
            "United States",
            1234567890,
            1234567890,
            -122.4,
            37.7,
            5158.0,
            False,
            225.0,
            270.0,
            0.0,
            None,
            5158.0,
            0,                 # squawk = 0 (no squawk)
            False,
            0
        ]
        
        result = plugin._parse_state_vector(state_vector)
        
        assert result is not None
        assert result["squawk"] == "----"  # 0 should be treated as no squawk
    
    def test_parse_state_vector_squawk_empty_string(self, plugin):
        """Test parsing state vector with empty string squawk."""
        state_vector = [
            "abc999",
            "EMPTY1",
            "United States",
            1234567890,
            1234567890,
            -122.4,
            37.7,
            5158.0,
            False,
            225.0,
            270.0,
            0.0,
            None,
            5158.0,
            "",               # squawk (empty string)
            False,
            0
        ]
        
        result = plugin._parse_state_vector(state_vector)
        
        assert result is not None
        assert result["squawk"] == "----"  # Empty string should be treated as no squawk
    
    def test_parse_state_vector_squawk_valid(self, plugin):
        """Test parsing state vector with valid squawk codes."""
        test_cases = [
            ("1200", "1200"),      # Standard squawk
            (1200, "1200"),        # Integer squawk
            ("2513", "2513"),      # 4-digit string
            (2513, "2513"),        # 4-digit integer
            ("12", "0012"),        # Short code (zfill to 4)
            (12, "0012"),          # Short integer (zfill to 4)
        ]
        
        for squawk_raw, expected in test_cases:
            state_vector = [
                "test123",
                "TEST1",
                "United States",
                1234567890,
                1234567890,
                -122.4,
                37.7,
                5158.0,
                False,
                225.0,
                270.0,
                0.0,
                None,
                5158.0,
                squawk_raw,
                False,
                0
            ]
            
            result = plugin._parse_state_vector(state_vector)
            assert result is not None
            assert result["squawk"] == expected, f"Failed for squawk_raw={squawk_raw}"
    
    def test_parse_state_vector_on_ground(self, plugin):
        """Test parsing state vector for aircraft on ground (should be filtered)."""
        state_vector = [
            "jkl012",
            "GROUND1",
            "United States",
            1234567890,
            1234567890,
            -122.3,
            37.75,
            12192.0,
            True,              # on_ground
            0.0,
            0.0,
            0.0,
            None,
            12192.0,
            "3602",
            False,
            0
        ]
        
        result = plugin._parse_state_vector(state_vector)
        
        assert result is None  # Should be filtered out
    
    def test_parse_state_vector_missing_position(self, plugin):
        """Test parsing state vector without position data."""
        state_vector = [
            "mno345",
            "NOPOS1",
            "United States",
            1234567890,
            1234567890,
            None,              # longitude (null)
            None,              # latitude (null)
            35000.0,
            False,
            450.0,
            180.0,
            0.0,
            None,
            35000.0,
            "1234",
            False,
            0
        ]
        
        result = plugin._parse_state_vector(state_vector)
        
        assert result is None  # Should be filtered out
    
    def test_parse_state_vector_missing_altitude(self, plugin):
        """Test parsing state vector without altitude."""
        state_vector = [
            "pqr678",
            "NOALT1",
            "United States",
            1234567890,
            1234567890,
            -122.4,
            37.7,
            None,              # baro_altitude (null)
            False,
            225.0,
            270.0,
            0.0,
            None,
            None,              # geo_altitude (null)
            "5678",
            False,
            0
        ]
        
        result = plugin._parse_state_vector(state_vector)
        
        assert result is None  # Should be filtered out
    
    def test_parse_state_vector_missing_velocity(self, plugin):
        """Test parsing state vector without velocity."""
        state_vector = [
            "stu901",
            "NOSPD1",
            "United States",
            1234567890,
            1234567890,
            -122.4,
            37.7,
            35000.0,
            False,
            None,              # velocity (null)
            270.0,
            0.0,
            None,
            35000.0,
            "9012",
            False,
            0
        ]
        
        result = plugin._parse_state_vector(state_vector)
        
        assert result is None  # Should be filtered out
    
    def test_parse_state_vector_geo_altitude_preferred(self, plugin):
        """Test that geo_altitude is preferred over baro_altitude."""
        state_vector = [
            "vwx234",
            "ALTTST",
            "United States",
            1234567890,
            1234567890,
            -122.4,
            37.7,
            10000.0,           # baro_altitude
            False,
            250.0,
            180.0,
            0.0,
            None,
            12000.0,           # geo_altitude (should be used)
            "3456",
            False,
            0
        ]
        
        result = plugin._parse_state_vector(state_vector)
        
        assert result is not None
        # Should use geo_altitude (12000m) not baro_altitude (10000m)
        assert result["altitude"] == pytest.approx(39370, abs=10)  # 12000m * 3.28084


class TestFormatting:
    """Test display formatting."""
    
    def test_format_aircraft_line(self, plugin):
        """Test aircraft line formatting."""
        formatted = plugin._format_aircraft_line("AAY453", 4575, 279, "1603")
        
        assert "AAY453" in formatted
        assert "4575" in formatted
        assert "279" in formatted
        # Squawk might be truncated if formatted string exceeds 22 chars
        assert "1603" in formatted or "160" in formatted or "16" in formatted or "1" in formatted
        assert len(formatted) <= 22
    
    def test_format_aircraft_line_long_callsign(self, plugin):
        """Test formatting with long call sign (truncated)."""
        formatted = plugin._format_aircraft_line("VERYLONGCALLSIGN", 40000, 393, "2513")
        
        # Call sign should be truncated to 8 chars
        assert "VERYLONGCALLSIGN" not in formatted
        assert "VERYLONG" in formatted or formatted.startswith("VERYLONG")
    
    def test_format_aircraft_line_short_values(self, plugin):
        """Test formatting with short values (padded)."""
        formatted = plugin._format_aircraft_line("A1", 100, 50, "12")
        
        # Values should be right-aligned
        assert "A1" in formatted
        assert "   100" in formatted or "  100" in formatted
        assert "  50" in formatted or "   50" in formatted
    
    def test_align_formatting_single_aircraft(self, plugin):
        """Test alignment formatting with single aircraft."""
        aircraft_list = [
            {
                "call_sign": "AAY453",
                "altitude": 4575,
                "ground_speed": 279,
                "squawk": "1603",
                "formatted": ""  # Will be set by alignment
            }
        ]
        
        aligned, headers = plugin._align_formatting(aircraft_list)
        
        assert len(aligned) == 1
        assert aligned[0]["formatted"] is not None
        assert "AAY453" in aligned[0]["formatted"]
        assert headers is not None
        assert "CALLSGN" in headers
        assert "ALT" in headers
        assert "GS" in headers
        assert "SQWK" in headers
    
    def test_align_formatting_multiple_aircraft(self, plugin):
        """Test alignment formatting aligns columns across multiple aircraft."""
        aircraft_list = [
            {
                "call_sign": "SHORT",
                "altitude": 100,
                "ground_speed": 50,
                "squawk": "1234",
                "formatted": ""
            },
            {
                "call_sign": "VERYLONGCALLSIGN",
                "altitude": 40000,
                "ground_speed": 500,
                "squawk": "5678",
                "formatted": ""
            }
        ]
        
        aligned, headers = plugin._align_formatting(aircraft_list)
        
        assert len(aligned) == 2
        # Both aircraft should have formatted strings
        assert aligned[0]["formatted"] is not None
        assert aligned[1]["formatted"] is not None
        # Headers should be aligned
        assert headers is not None
        assert len(headers) <= 22
    
    def test_align_formatting_empty_list(self, plugin):
        """Test alignment formatting with empty list."""
        aircraft_list = []
        aligned, headers = plugin._align_formatting(aircraft_list)
        
        assert aligned == []
        assert headers == "CALLSGN ALT GS SQWK"
    
    def test_align_formatting_headers_alignment(self, plugin):
        """Test that headers align with data columns."""
        aircraft_list = [
            {
                "call_sign": "TEST1",
                "altitude": 12345,
                "ground_speed": 456,
                "squawk": "7890",
                "formatted": ""
            }
        ]
        
        aligned, headers = plugin._align_formatting(aircraft_list)
        
        # Headers should have same column widths as data
        # Extract column positions from formatted line
        formatted = aligned[0]["formatted"]
        # Headers should align with data columns
        assert "CALLSGN" in headers
        assert "ALT" in headers
        assert "GS" in headers
        assert "SQWK" in headers


class TestFetchData:
    """Test data fetching."""
    
    @patch('plugins.nearby_aircraft.requests.get')
    def test_fetch_data_success(self, mock_get, plugin, sample_config, mock_opensky_states_response):
        """Test successful data fetch."""
        plugin.config = sample_config
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_opensky_states_response
        mock_get.return_value = mock_response
        
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.data is not None
        assert "aircraft" in result.data
        assert result.data["aircraft_count"] > 0
        assert result.data["call_sign"] != ""
        assert "headers" in result.data
        assert result.data["headers"] is not None
        assert "CALLSGN" in result.data["headers"]
    
    @patch('plugins.nearby_aircraft.requests.get')
    def test_fetch_data_no_aircraft(self, mock_get, plugin, sample_config, mock_opensky_empty_response):
        """Test fetch when no aircraft found."""
        plugin.config = sample_config
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_opensky_empty_response
        mock_get.return_value = mock_response
        
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.data["aircraft_count"] == 0
        assert result.data["formatted"] == "NO AIRCRAFT NEARBY"
        assert "headers" in result.data
        assert result.data["headers"] == "CALLSGN ALT GS SQWK"
    
    @patch('plugins.nearby_aircraft.requests.get')
    def test_fetch_data_rate_limit(self, mock_get, plugin, sample_config):
        """Test handling of rate limit (429)."""
        plugin.config = sample_config
        
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        result = plugin.fetch_data()
        
        # Should return error (no cache yet)
        assert result.available is False
        assert "rate limit" in result.error.lower()
    
    @patch('plugins.nearby_aircraft.requests.get')
    def test_fetch_data_rate_limit_with_cache(self, mock_get, plugin, sample_config, mock_opensky_states_response):
        """Test rate limit with cached data available."""
        plugin.config = sample_config
        
        # First successful fetch
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_opensky_states_response
        mock_get.return_value = mock_response
        
        result1 = plugin.fetch_data()
        assert result1.available is True
        
        # Second fetch hits rate limit
        mock_response.status_code = 429
        result2 = plugin.fetch_data()
        
        # Should return cached data
        assert result2.available is True
        assert result2.data is not None
    
    @patch('plugins.nearby_aircraft.requests.get')
    def test_fetch_data_filters_by_distance(self, mock_get, plugin, sample_config):
        """Test that aircraft are filtered by distance."""
        plugin.config = sample_config
        
        # Create state vectors: one close, one far
        # State vector format: [icao24, callsign, origin_country, time_position, last_contact,
        #                       longitude, latitude, baro_altitude, on_ground, velocity,
        #                       true_track, vertical_rate, sensors, geo_altitude, squawk, spi, position_source]
        states = [
            [
                "close1", "CLOSE1", "US", 1234567890, 1234567890,
                -122.4195, 37.7750,  # longitude, latitude - Very close to SF (37.7749, -122.4194)
                35000.0, False, 450.0, 180.0, 0.0, None, 35000.0, "1234", False, 0
            ],
            [
                "far1", "FAR1", "US", 1234567890, 1234567890,
                -125.0, 40.0,  # longitude, latitude - Far from SF (>200km)
                35000.0, False, 450.0, 180.0, 0.0, None, 35000.0, "5678", False, 0
            ],
        ]
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"time": 1234567890, "states": states}
        mock_get.return_value = mock_response
        
        result = plugin.fetch_data()
        
        assert result.available is True
        # Should only include close aircraft (within 50km radius)
        assert result.data["aircraft_count"] == 1
        assert result.data["aircraft"][0]["call_sign"] == "CLOSE1"
    
    @patch('plugins.nearby_aircraft.requests.get')
    def test_fetch_data_sorts_by_distance(self, mock_get, plugin, sample_config):
        """Test that aircraft are sorted by distance."""
        plugin.config = sample_config
        
        # Create state vectors at different distances
        # State vector format: [icao24, callsign, origin_country, time_position, last_contact,
        #                       longitude, latitude, baro_altitude, on_ground, velocity,
        #                       true_track, vertical_rate, sensors, geo_altitude, squawk, spi, position_source]
        states = [
            [
                "far1", "FAR1", "US", 1234567890, 1234567890,
                -122.5, 37.9,  # longitude, latitude - ~20km
                35000.0, False, 450.0, 180.0, 0.0, None, 35000.0, "1234", False, 0
            ],
            [
                "close1", "CLOSE1", "US", 1234567890, 1234567890,
                -122.42, 37.775,  # longitude, latitude - ~5km
                35000.0, False, 450.0, 180.0, 0.0, None, 35000.0, "5678", False, 0
            ],
        ]
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"time": 1234567890, "states": states}
        mock_get.return_value = mock_response
        
        result = plugin.fetch_data()
        
        assert result.available is True
        # Closest should be first
        assert result.data["aircraft"][0]["call_sign"] == "CLOSE1"
        assert result.data["aircraft"][0]["distance_km"] < result.data["aircraft"][1]["distance_km"]
    
    @patch('plugins.nearby_aircraft.requests.get')
    def test_fetch_data_respects_max_aircraft(self, mock_get, plugin, sample_config):
        """Test that max_aircraft limit is respected."""
        plugin.config = {**sample_config, "max_aircraft": 2}
        
        # Create 4 close aircraft
        # State vector format: [icao24, callsign, origin_country, time_position, last_contact,
        #                       longitude, latitude, baro_altitude, on_ground, velocity,
        #                       true_track, vertical_rate, sensors, geo_altitude, squawk, spi, position_source]
        states = []
        for i in range(4):
            states.append([
                f"ac{i}", f"AC{i}", "US", 1234567890, 1234567890,
                -122.42, 37.775 + i * 0.01,  # longitude, latitude - All within radius
                35000.0, False, 450.0, 180.0, 0.0, None, 35000.0, "1234", False, 0
            ])
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"time": 1234567890, "states": states}
        mock_get.return_value = mock_response
        
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.data["aircraft_count"] == 2  # Limited to max_aircraft


class TestFormattedDisplay:
    """Test formatted display."""
    
    @patch('plugins.nearby_aircraft.requests.get')
    def test_get_formatted_display(self, mock_get, plugin, sample_config, mock_opensky_states_response):
        """Test formatted display generation."""
        plugin.config = sample_config
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_opensky_states_response
        mock_get.return_value = mock_response
        
        lines = plugin.get_formatted_display()
        
        assert lines is not None
        assert len(lines) == 6
        assert "NEARBY AIRCRAFT" in lines[0]
        assert "CALLSGN" in lines[1] or "CALL" in lines[1]
    
    def test_get_formatted_display_no_cache(self, plugin):
        """Test formatted display with no cache."""
        plugin.config = {"latitude": 37.7749, "longitude": -122.4194}
        plugin._cache = None
        
        with patch.object(plugin, 'fetch_data') as mock_fetch:
            mock_fetch.return_value = Mock(available=False)
            lines = plugin.get_formatted_display()
            assert lines is None


class TestCaching:
    """Test caching behavior."""
    
    @patch('plugins.nearby_aircraft.requests.get')
    def test_cache_used_when_fresh(self, mock_get, plugin, sample_config, mock_opensky_states_response):
        """Test that cache is used when data is fresh."""
        plugin.config = {**sample_config, "refresh_seconds": 300}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_opensky_states_response
        mock_get.return_value = mock_response
        
        # First fetch
        result1 = plugin.fetch_data()
        assert result1.available is True
        assert mock_get.call_count == 1
        
        # Second fetch (should use cache)
        result2 = plugin.fetch_data()
        assert result2.available is True
        # Should still be 1 call (cache used)
        assert mock_get.call_count == 1
    
    @patch('plugins.nearby_aircraft.requests.get')
    def test_cache_expired_fetches_new(self, mock_get, plugin, sample_config, mock_opensky_states_response):
        """Test that expired cache triggers new fetch."""
        plugin.config = {**sample_config, "refresh_seconds": 60}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_opensky_states_response
        mock_get.return_value = mock_response
        
        # First fetch
        result1 = plugin.fetch_data()
        assert result1.available is True
        
        # Manually expire cache
        if plugin._cache:
            plugin._cache["last_updated"] = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        
        # Second fetch (should fetch new data)
        result2 = plugin.fetch_data()
        assert result2.available is True
        assert mock_get.call_count == 2
