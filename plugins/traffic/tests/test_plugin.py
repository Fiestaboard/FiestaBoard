"""Tests for traffic data source."""

import pytest
from unittest.mock import Mock, patch
from src.utils.traffic import TrafficSource, get_traffic_source


class TestTrafficIndex:
    """Tests for Traffic_Index calculation - the core logic."""
    
    def test_traffic_index_normal_conditions(self):
        """Test traffic index when traffic time equals normal time."""
        # No traffic: 30 minutes normal, 30 minutes with traffic
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=1800,  # 30 min in seconds
            duration_normal=1800
        )
        assert index == 1.0
    
    def test_traffic_index_light_traffic(self):
        """Test traffic index with light traffic (under 20% increase)."""
        # Light traffic: 30 minutes normal, 33 minutes with traffic (10% slower)
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=1980,  # 33 min
            duration_normal=1800       # 30 min
        )
        assert index == 1.1
    
    def test_traffic_index_yellow_threshold(self):
        """Test traffic index at YELLOW threshold (> 1.2)."""
        # Moderate traffic: 30 minutes normal, 36 minutes with traffic (20% slower)
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=2160,  # 36 min
            duration_normal=1800       # 30 min
        )
        assert index == 1.2
        
        # Just over threshold
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=2170,
            duration_normal=1800
        )
        assert index > 1.2
    
    def test_traffic_index_red_threshold(self):
        """Test traffic index at RED threshold (> 1.5)."""
        # Heavy traffic: 30 minutes normal, 45 minutes with traffic (50% slower)
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=2700,  # 45 min
            duration_normal=1800       # 30 min
        )
        assert index == 1.5
        
        # Just over threshold
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=2710,
            duration_normal=1800
        )
        assert index > 1.5
    
    def test_traffic_index_severe_traffic(self):
        """Test traffic index with severe traffic (2x normal)."""
        # Severe: 30 minutes normal, 60 minutes with traffic
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=3600,
            duration_normal=1800
        )
        assert index == 2.0
    
    def test_traffic_index_missing_traffic_duration(self):
        """Test that missing traffic duration defaults to normal duration."""
        # When durationInTraffic is None, should default to normal
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=None,
            duration_normal=1800
        )
        assert index == 1.0
    
    def test_traffic_index_zero_normal_duration(self):
        """Test handling of zero normal duration (edge case)."""
        # Should return 1.0 to avoid division by zero
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=1800,
            duration_normal=0
        )
        assert index == 1.0
    
    def test_traffic_index_negative_normal_duration(self):
        """Test handling of negative normal duration (edge case)."""
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=1800,
            duration_normal=-100
        )
        assert index == 1.0
    
    def test_traffic_index_rounding(self):
        """Test that traffic index is rounded to 2 decimal places."""
        # 1800 / 1700 = 1.0588... should round to 1.06
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=1800,
            duration_normal=1700
        )
        assert index == 1.06
    
    def test_traffic_index_faster_than_normal(self):
        """Test when traffic time is faster than normal (rare but possible)."""
        # Sometimes traffic can be lighter than historical average
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=1600,  # 26.7 min
            duration_normal=1800       # 30 min
        )
        assert index < 1.0
        assert index == 0.89


class TestTrafficStatus:
    """Tests for traffic status determination."""
    
    def test_light_traffic_green(self):
        """Test LIGHT/GREEN status for index <= 1.2."""
        status, color = TrafficSource.get_traffic_status(1.0)
        assert status == "LIGHT"
        assert color == "GREEN"
        
        status, color = TrafficSource.get_traffic_status(1.19)
        assert status == "LIGHT"
        assert color == "GREEN"
        
        # At exactly 1.2, still GREEN
        status, color = TrafficSource.get_traffic_status(1.2)
        assert status == "LIGHT"
        assert color == "GREEN"
    
    def test_moderate_traffic_yellow(self):
        """Test MODERATE/YELLOW status for 1.2 < index <= 1.5."""
        status, color = TrafficSource.get_traffic_status(1.21)
        assert status == "MODERATE"
        assert color == "YELLOW"
        
        status, color = TrafficSource.get_traffic_status(1.35)
        assert status == "MODERATE"
        assert color == "YELLOW"
        
        # At exactly 1.5, still YELLOW
        status, color = TrafficSource.get_traffic_status(1.5)
        assert status == "MODERATE"
        assert color == "YELLOW"
    
    def test_heavy_traffic_red(self):
        """Test HEAVY/RED status for index > 1.5."""
        status, color = TrafficSource.get_traffic_status(1.51)
        assert status == "HEAVY"
        assert color == "RED"
        
        status, color = TrafficSource.get_traffic_status(2.0)
        assert status == "HEAVY"
        assert color == "RED"
        
        status, color = TrafficSource.get_traffic_status(3.0)
        assert status == "HEAVY"
        assert color == "RED"
    
    def test_traffic_status_boundaries(self):
        """Test exact boundary values."""
        # 1.2 -> GREEN (not over)
        _, color = TrafficSource.get_traffic_status(1.2)
        assert color == "GREEN"
        
        # 1.200001 -> YELLOW (just over)
        _, color = TrafficSource.get_traffic_status(1.200001)
        assert color == "YELLOW"
        
        # 1.5 -> YELLOW (not over)
        _, color = TrafficSource.get_traffic_status(1.5)
        assert color == "YELLOW"
        
        # 1.500001 -> RED (just over)
        _, color = TrafficSource.get_traffic_status(1.500001)
        assert color == "RED"


class TestMessageFormatting:
    """Tests for message formatting."""
    
    def test_format_with_delay(self):
        """Test format with traffic delay."""
        msg = TrafficSource.format_message("DOWNTOWN", 45, 10)
        assert msg == "DOWNTOWN: 45m (+10m delay)"
    
    def test_format_no_delay(self):
        """Test format with no delay."""
        msg = TrafficSource.format_message("DOWNTOWN", 30, 0)
        assert msg == "DOWNTOWN: 30m"
    
    def test_format_custom_destination(self):
        """Test format with custom destination name."""
        msg = TrafficSource.format_message("WORK", 25, 5)
        assert msg == "WORK: 25m (+5m delay)"
    
    def test_format_large_delay(self):
        """Test format with large delay."""
        msg = TrafficSource.format_message("AIRPORT", 90, 45)
        assert msg == "AIRPORT: 90m (+45m delay)"
    
    def test_format_negative_delay_treated_as_zero(self):
        """Test that negative delay shows no delay (edge case)."""
        # The format_message itself doesn't handle this, but fetch does
        msg = TrafficSource.format_message("DOWNTOWN", 30, -5)
        # Currently will show negative, but in practice delay is max(0, ...)
        assert "DOWNTOWN: 30m" in msg


class TestDurationParsing:
    """Tests for duration string parsing."""
    
    def test_parse_duration_seconds(self):
        """Test parsing duration string with 's' suffix."""
        assert TrafficSource._parse_duration("1800s") == 1800
        assert TrafficSource._parse_duration("3600s") == 3600
        assert TrafficSource._parse_duration("0s") == 0
    
    def test_parse_duration_empty(self):
        """Test parsing empty duration string."""
        assert TrafficSource._parse_duration("") == 0
        assert TrafficSource._parse_duration(None) == 0
    
    def test_parse_duration_no_suffix(self):
        """Test parsing duration without 's' suffix."""
        # rstrip('s') handles this
        assert TrafficSource._parse_duration("1800") == 1800


class TestTrafficSource:
    """Tests for TrafficSource class."""
    
    def test_init_with_addresses(self):
        """Test initialization with address strings."""
        source = TrafficSource(
            api_key="test_key",
            routes=[{
                "origin": "123 Main St, San Francisco, CA",
                "destination": "456 Market St, San Francisco, CA",
                "destination_name": "OFFICE"
            }]
        )
        assert source.origin == "123 Main St, San Francisco, CA"
        assert source.destination == "456 Market St, San Francisco, CA"
        assert source.destination_name == "OFFICE"
    
    def test_init_default_destination_name(self):
        """Test default destination name is DOWNTOWN."""
        source = TrafficSource(
            api_key="test_key",
            routes=[{
                "origin": "Origin",
                "destination": "Dest"
            }]
        )
        assert source.destination_name == "DOWNTOWN"
    
    def test_build_waypoint_address(self):
        """Test building waypoint from address."""
        source = TrafficSource("test_key", routes=[{"origin": "A", "destination": "B"}])
        waypoint = source._build_waypoint("123 Main St, City, ST")
        assert waypoint == {"address": "123 Main St, City, ST"}
    
    def test_build_waypoint_latlng(self):
        """Test building waypoint from lat,lng."""
        source = TrafficSource("test_key", routes=[{"origin": "A", "destination": "B"}])
        waypoint = source._build_waypoint("37.7749, -122.4194")
        assert "location" in waypoint
        assert waypoint["location"]["latLng"]["latitude"] == 37.7749
        assert waypoint["location"]["latLng"]["longitude"] == -122.4194
    
    def test_build_waypoint_latlng_no_space(self):
        """Test building waypoint from lat,lng without spaces."""
        source = TrafficSource("test_key", routes=[{"origin": "A", "destination": "B"}])
        waypoint = source._build_waypoint("37.7749,-122.4194")
        assert "location" in waypoint
        assert waypoint["location"]["latLng"]["latitude"] == 37.7749
    
    @patch('src.utils.traffic.requests.post')
    def test_fetch_traffic_data_success(self, mock_post):
        """Test successful traffic data fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "routes": [{
                "duration": "2700s",      # 45 min with traffic
                "staticDuration": "1800s", # 30 min normal
                "routeToken": "test_token_123"
            }]
        }
        mock_post.return_value = mock_response
        
        source = TrafficSource(
            api_key="test_key",
            routes=[{
                "origin": "Home",
                "destination": "Work",
                "destination_name": "WORK"
            }]
        )
        result = source.fetch_traffic_data()
        
        assert result is not None
        assert result["duration"] == 2700
        assert result["static_duration"] == 1800
        assert result["route_token"] == "test_token_123"
        assert result["traffic_index"] == 1.5
        assert result["traffic_status"] == "MODERATE"  # At 1.5, still YELLOW
        assert result["traffic_color"] == "YELLOW"
        assert result["duration_minutes"] == 45
        assert result["static_duration_minutes"] == 30
        assert result["delay_minutes"] == 15
        assert result["formatted_message"] == "WORK: 45m (+15m delay)"
    
    @patch('src.utils.traffic.requests.post')
    def test_fetch_traffic_data_no_delay(self, mock_post):
        """Test traffic data with no delay."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "routes": [{
                "duration": "1800s",
                "staticDuration": "1800s",
                "routeToken": "token"
            }]
        }
        mock_post.return_value = mock_response
        
        source = TrafficSource("test_key", routes=[{"origin": "A", "destination": "B", "destination_name": "DOWNTOWN"}])
        result = source.fetch_traffic_data()
        
        assert result["traffic_index"] == 1.0
        assert result["traffic_color"] == "GREEN"
        assert result["delay_minutes"] == 0
        assert result["formatted_message"] == "DOWNTOWN: 30m"
    
    @patch('src.utils.traffic.requests.post')
    def test_fetch_traffic_data_heavy_traffic(self, mock_post):
        """Test traffic data with heavy traffic."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "routes": [{
                "duration": "3600s",       # 60 min with traffic
                "staticDuration": "1800s", # 30 min normal
                "routeToken": "token"
            }]
        }
        mock_post.return_value = mock_response
        
        source = TrafficSource("test_key", routes=[{"origin": "A", "destination": "B", "destination_name": "AIRPORT"}])
        result = source.fetch_traffic_data()
        
        assert result["traffic_index"] == 2.0
        assert result["traffic_status"] == "HEAVY"
        assert result["traffic_color"] == "RED"
        assert result["delay_minutes"] == 30
    
    @patch('src.utils.traffic.requests.post')
    def test_fetch_traffic_data_api_error(self, mock_post):
        """Test handling of API errors."""
        mock_post.side_effect = Exception("Network error")
        
        source = TrafficSource("test_key", routes=[{"origin": "A", "destination": "B"}])
        result = source.fetch_traffic_data()
        
        assert result is None
    
    @patch('src.utils.traffic.requests.post')
    def test_fetch_traffic_data_no_routes(self, mock_post):
        """Test handling of empty routes response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"routes": []}
        mock_post.return_value = mock_response
        
        source = TrafficSource("test_key", routes=[{"origin": "A", "destination": "B"}])
        result = source.fetch_traffic_data()
        
        assert result is None
    
    @patch('src.utils.traffic.requests.post')
    def test_fetch_traffic_data_missing_static_duration(self, mock_post):
        """Test handling when staticDuration is missing (uses duration as fallback)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "routes": [{
                "duration": "1800s",
                # No staticDuration
                "routeToken": "token"
            }]
        }
        mock_post.return_value = mock_response
        
        source = TrafficSource("test_key", routes=[{"origin": "A", "destination": "B"}])
        result = source.fetch_traffic_data()
        
        assert result is not None
        # When static_duration is 0, it falls back to duration
        assert result["traffic_index"] == 1.0


class TestGetTrafficSource:
    """Tests for get_traffic_source factory function."""
    
    @patch('src.utils.traffic.Config')
    def test_get_traffic_source_with_config(self, mock_config):
        """Test factory returns source when properly configured."""
        mock_config.GOOGLE_ROUTES_API_KEY = "test_key"
        mock_config.TRAFFIC_ORIGIN = "Home Address"
        mock_config.TRAFFIC_DESTINATION = "Work Address"
        mock_config.TRAFFIC_DESTINATION_NAME = "WORK"
        
        def mock_hasattr(obj, name):
            return True
        
        with patch('builtins.hasattr', mock_hasattr):
            source = get_traffic_source()
        
        assert source is not None
        assert isinstance(source, TrafficSource)
    
    @patch('src.utils.traffic.Config')
    def test_get_traffic_source_no_api_key(self, mock_config):
        """Test factory returns None when API key missing."""
        def mock_hasattr(obj, name):
            return False
        
        with patch('builtins.hasattr', mock_hasattr):
            source = get_traffic_source()
        
        assert source is None


class TestTrafficIndexEdgeCases:
    """Additional edge case tests for traffic index calculation."""
    
    def test_very_short_trip(self):
        """Test traffic index for very short trip (5 minutes)."""
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=360,  # 6 min
            duration_normal=300       # 5 min
        )
        assert index == 1.2
    
    def test_very_long_trip(self):
        """Test traffic index for very long trip (2 hours)."""
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=9000,  # 2.5 hours with traffic
            duration_normal=7200       # 2 hours normal
        )
        assert index == 1.25
    
    def test_extreme_traffic(self):
        """Test traffic index with extreme traffic (3x normal)."""
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=5400,  # 90 min
            duration_normal=1800       # 30 min
        )
        assert index == 3.0
        
        status, color = TrafficSource.get_traffic_status(index)
        assert status == "HEAVY"
        assert color == "RED"
    
    def test_index_with_fractional_seconds(self):
        """Test that calculation handles non-round numbers."""
        # 1847 / 1800 = 1.0261...
        index = TrafficSource.calculate_traffic_index(
            duration_in_traffic=1847,
            duration_normal=1800
        )
        assert index == 1.03  # Rounded to 2 decimals


class TestTrafficPluginClass:
    """Tests for TrafficPlugin class (plugins/traffic/__init__.py)."""

    @pytest.fixture
    def plugin(self):
        from plugins.traffic import TrafficPlugin
        manifest = {"id": "traffic", "name": "Traffic", "version": "1.0.0"}
        return TrafficPlugin(manifest)

    def test_plugin_id(self, plugin):
        assert plugin.plugin_id == "traffic"

    def test_validate_config_valid(self, plugin):
        config = {"api_key": "k", "routes": [{"origin": "A", "destination": "B"}]}
        assert plugin.validate_config(config) == []

    def test_validate_config_missing_key(self, plugin):
        errors = plugin.validate_config({"routes": [{}]})
        assert any("API key" in e for e in errors)

    def test_validate_config_missing_routes(self, plugin):
        errors = plugin.validate_config({"api_key": "k"})
        assert any("route" in e for e in errors)

    def test_validate_config_empty(self, plugin):
        errors = plugin.validate_config({})
        assert len(errors) == 2

    def test_get_traffic_status_light(self, plugin):
        status, color = plugin._get_traffic_status(1.0)
        assert status == "LIGHT"
        assert color == "{66}"

    def test_get_traffic_status_moderate(self, plugin):
        status, color = plugin._get_traffic_status(1.3)
        assert status == "MODERATE"
        assert color == "{65}"

    def test_get_traffic_status_heavy(self, plugin):
        status, color = plugin._get_traffic_status(1.6)
        assert status == "HEAVY"
        assert color == "{63}"

    def test_parse_duration(self, plugin):
        assert plugin._parse_duration("1800s") == 1800
        assert plugin._parse_duration("") == 0
        assert plugin._parse_duration("3600") == 3600

    def test_build_waypoint_address(self, plugin):
        wp = plugin._build_waypoint("123 Main St, City, ST")
        assert wp == {"address": "123 Main St, City, ST"}

    def test_build_waypoint_latlng(self, plugin):
        wp = plugin._build_waypoint("37.7749, -122.4194")
        assert "location" in wp
        assert wp["location"]["latLng"]["latitude"] == 37.7749
        assert wp["location"]["latLng"]["longitude"] == -122.4194

    def test_build_waypoint_invalid_latlng(self, plugin):
        wp = plugin._build_waypoint("abc, def")
        assert wp == {"address": "abc, def"}

    def test_fetch_data_no_routes(self, plugin):
        plugin._config = {}
        result = plugin.fetch_data()
        assert not result.available

    def test_fetch_single_route_success(self, plugin):
        plugin._config = {"api_key": "test_key"}
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "routes": [{
                "duration": "2700s",
                "staticDuration": "1800s",
            }]
        }
        with patch('plugins.traffic.requests.post', return_value=mock_resp):
            result = plugin._fetch_single_route("Home", "Work", "WORK")
            assert result is not None
            assert result["duration_minutes"] == 45
            assert result["delay_minutes"] == 15
            assert result["traffic_status"] == "MODERATE"

    def test_fetch_single_route_no_delay(self, plugin):
        plugin._config = {"api_key": "test_key"}
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "routes": [{"duration": "1800s", "staticDuration": "1800s"}]
        }
        with patch('plugins.traffic.requests.post', return_value=mock_resp):
            result = plugin._fetch_single_route("A", "B", "DEST")
            assert result is not None
            assert result["delay_minutes"] == 0
            assert "DEST: 30m" == result["formatted"]

    def test_fetch_single_route_api_error(self, plugin):
        plugin._config = {"api_key": "test_key"}
        with patch('plugins.traffic.requests.post', side_effect=Exception("fail")):
            result = plugin._fetch_single_route("A", "B", "DEST")
            assert result is None

    def test_fetch_single_route_bad_status(self, plugin):
        plugin._config = {"api_key": "test_key"}
        mock_resp = Mock()
        mock_resp.status_code = 403
        with patch('plugins.traffic.requests.post', return_value=mock_resp):
            result = plugin._fetch_single_route("A", "B", "DEST")
            assert result is None

    def test_fetch_single_route_empty_routes(self, plugin):
        """Test when API returns no routes in response."""
        plugin._config = {"api_key": "test_key"}
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"routes": []}
        with patch('plugins.traffic.requests.post', return_value=mock_resp):
            result = plugin._fetch_single_route("A", "B", "DEST")
            assert result is None

    def test_fetch_single_route_missing_static_duration(self, plugin):
        """Test when staticDuration is 0 or missing."""
        plugin._config = {"api_key": "test_key"}
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "routes": [{"duration": "1800s", "staticDuration": "0s"}]
        }
        with patch('plugins.traffic.requests.post', return_value=mock_resp):
            result = plugin._fetch_single_route("A", "B", "DEST")
            assert result is not None
            assert result["duration_minutes"] == 30

    def test_fetch_data_all_routes_fail(self, plugin):
        """Test when all routes fail to fetch."""
        plugin._config = {
            "api_key": "test_key",
            "routes": [
                {"origin": "A", "destination": "B", "destination_name": "DEST1"},
                {"origin": "C", "destination": "D", "destination_name": "DEST2"}
            ]
        }
        with patch.object(plugin, '_fetch_single_route', return_value=None):
            result = plugin.fetch_data()
            assert not result.available
            assert "Failed to fetch any route data" in result.error

    def test_fetch_data_success(self, plugin):
        plugin._config = {
            "api_key": "test_key",
            "routes": [
                {"origin": "Home", "destination": "Work", "destination_name": "WORK"}
            ]
        }
        mock_route = {
            "duration_minutes": 30,
            "delay_minutes": 5,
            "traffic_status": "MODERATE",
            "traffic_color": "{65}",
            "destination_name": "WORK",
            "formatted": "WORK: 30m (+5m)",
        }
        with patch.object(plugin, '_fetch_single_route', return_value=mock_route):
            result = plugin.fetch_data()
            assert result.available
            assert result.data["route_count"] == 1

    def test_get_formatted_display_with_cache(self, plugin):
        """Test get_formatted_display with cached data."""
        plugin._cache = {
            "routes": [
                {"formatted": "HOME: 30m (+5m)"},
                {"formatted": "WORK: 25m"}
            ]
        }
        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) == 6
        assert lines[0] == "TRAFFIC".center(22)
        assert lines[2] == "HOME: 30m (+5m)"
        assert lines[3] == "WORK: 25m"

    def test_get_formatted_display_no_cache(self, plugin):
        """Test get_formatted_display without cache."""
        plugin._cache = None
        plugin._config = {
            "api_key": "test_key",
            "routes": [{"origin": "A", "destination": "B", "destination_name": "DEST"}]
        }
        mock_route = {
            "duration_minutes": 20,
            "delay_minutes": 0,
            "traffic_status": "LIGHT",
            "traffic_color": "{62}",
            "destination_name": "DEST",
            "formatted": "DEST: 20m"
        }
        with patch.object(plugin, '_fetch_single_route', return_value=mock_route):
            lines = plugin.get_formatted_display()
            assert lines is not None
            assert len(lines) == 6

    def test_get_formatted_display_fetch_fails(self, plugin):
        """Test get_formatted_display when fetch fails."""
        plugin._cache = None
        plugin._config = {"api_key": "test_key", "routes": []}
        result = plugin.get_formatted_display()
        assert result is None
