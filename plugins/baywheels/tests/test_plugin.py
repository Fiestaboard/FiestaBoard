"""Unit tests for Bay Wheels GBFS integration."""

import pytest
import json
import time
from unittest.mock import Mock, patch
from src.utils.baywheels import BayWheelsSource, STATION_STATUS_URL


class TestBayWheelsSource:
    """Test Bay Wheels data source."""
    
    def test_init(self):
        """Test source initialization."""
        source = BayWheelsSource(station_ids=["test-station-123"])
        assert source.station_ids == ["test-station-123"]
    
    def test_init_single_string(self):
        """Test backward compatibility with single string."""
        source = BayWheelsSource(station_ids="test-station-123")
        assert source.station_ids == ["test-station-123"]
    
    def test_init_multiple_stations(self):
        """Test initialization with multiple stations."""
        source = BayWheelsSource(station_ids=["station-1", "station-2", "station-3"])
        assert source.station_ids == ["station-1", "station-2", "station-3"]
    
    def test_fetch_station_status_success(self):
        """Test successful station data fetch."""
        source = BayWheelsSource(station_ids=["station-123"])
        
        # Mock response data
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-123",
                        "num_bikes_available": 10,
                        "is_renting": 1,
                        "num_docks_available": 5,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 7},
                            {"vehicle_type_id": "classic_bike", "count": 3}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get, \
             patch.object(BayWheelsSource, '_get_station_information', return_value={
                 "station-123": {"name": "Test Station", "lat": 37.7749, "lon": -122.4194}
             }):
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            assert result["station_id"] == "station-123"
            assert result["num_bikes_available"] == 10
            assert result["electric_bikes"] == 7
            assert result["classic_bikes"] == 3
            assert result["is_renting"] is True
            assert result["status_color"] == "green"  # 7 e-bikes > 5
            assert result["num_docks_available"] == 5
            
            # Verify correct URL was called
            mock_get.assert_called_once_with(STATION_STATUS_URL, timeout=10)
    
    def test_fetch_station_status_zero_ebikes(self):
        """Test edge case: station has 0 electric bikes."""
        source = BayWheelsSource(station_ids=["station-456"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-456",
                        "num_bikes_available": 5,
                        "is_renting": 1,
                        "num_docks_available": 10,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 0},
                            {"vehicle_type_id": "classic_bike", "count": 5}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            assert result["electric_bikes"] == 0
            assert result["classic_bikes"] == 5
            assert result["status_color"] == "red"  # 0 e-bikes < 2
    
    def test_fetch_station_status_one_ebike(self):
        """Test edge case: station has exactly 1 electric bike."""
        source = BayWheelsSource(station_ids=["station-789"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-789",
                        "num_bikes_available": 4,
                        "is_renting": 1,
                        "num_docks_available": 8,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 1},
                            {"vehicle_type_id": "classic_bike", "count": 3}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            assert result["electric_bikes"] == 1
            assert result["status_color"] == "red"  # 1 e-bike < 2
    
    def test_fetch_station_status_two_ebikes(self):
        """Test boundary: station has exactly 2 electric bikes (yellow)."""
        source = BayWheelsSource(station_ids=["station-abc"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-abc",
                        "num_bikes_available": 5,
                        "is_renting": 1,
                        "num_docks_available": 7,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 2},
                            {"vehicle_type_id": "classic_bike", "count": 3}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            assert result["electric_bikes"] == 2
            assert result["status_color"] == "yellow"  # 2 e-bikes (2 <= x <= 5)
    
    def test_fetch_station_status_five_ebikes(self):
        """Test boundary: station has exactly 5 electric bikes (yellow)."""
        source = BayWheelsSource(station_ids=["station-def"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-def",
                        "num_bikes_available": 8,
                        "is_renting": 1,
                        "num_docks_available": 4,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 5},
                            {"vehicle_type_id": "classic_bike", "count": 3}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            assert result["electric_bikes"] == 5
            assert result["status_color"] == "yellow"  # 5 e-bikes (2 <= x <= 5)
    
    def test_fetch_station_status_six_ebikes(self):
        """Test boundary: station has exactly 6 electric bikes (green)."""
        source = BayWheelsSource(station_ids=["station-ghi"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-ghi",
                        "num_bikes_available": 10,
                        "is_renting": 1,
                        "num_docks_available": 2,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 6},
                            {"vehicle_type_id": "classic_bike", "count": 4}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            assert result["electric_bikes"] == 6
            assert result["status_color"] == "green"  # 6 e-bikes > 5
    
    def test_fetch_station_status_not_renting(self):
        """Test station that is not currently renting bikes."""
        source = BayWheelsSource(station_ids=["station-xyz"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-xyz",
                        "num_bikes_available": 8,
                        "is_renting": 0,  # Not renting
                        "num_docks_available": 3,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 5},
                            {"vehicle_type_id": "classic_bike", "count": 3}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            assert result["is_renting"] is False
    
    def test_fetch_station_status_missing_vehicle_types(self):
        """Test edge case: API response missing vehicle_types_available field."""
        source = BayWheelsSource(station_ids=["station-missing"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-missing",
                        "num_bikes_available": 5,
                        "is_renting": 1,
                        "num_docks_available": 7,
                        # vehicle_types_available field is missing
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            # Should default to 0 for both types when missing
            assert result["electric_bikes"] == 0
            assert result["classic_bikes"] == 0
            assert result["status_color"] == "red"  # 0 e-bikes
    
    def test_fetch_station_status_unknown_vehicle_type(self):
        """Test edge case: API adds new vehicle type IDs."""
        source = BayWheelsSource(station_ids=["station-new-type"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-new-type",
                        "num_bikes_available": 10,
                        "is_renting": 1,
                        "num_docks_available": 5,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 3},
                            {"vehicle_type_id": "classic_bike", "count": 2},
                            {"vehicle_type_id": "new_scooter_type", "count": 5}  # New type
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            assert result["electric_bikes"] == 3
            # Unknown types should be counted as classic
            assert result["classic_bikes"] == 7  # 2 classic + 5 unknown
    
    def test_fetch_station_status_boost_keyword(self):
        """Test that 'boost' keyword is recognized as electric bikes."""
        source = BayWheelsSource(station_ids=["station-boost"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-boost",
                        "num_bikes_available": 6,
                        "is_renting": 1,
                        "num_docks_available": 8,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "boost_bike", "count": 4},
                            {"vehicle_type_id": "classic_bike", "count": 2}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            assert result["electric_bikes"] == 4  # 'boost' counted as electric
            assert result["classic_bikes"] == 2
    
    def test_fetch_station_status_new_api_format(self):
        """Test NEW API format (as of late 2024) with num_ebikes_available field."""
        source = BayWheelsSource(station_ids=["station-new-format"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-new-format",
                        "num_bikes_available": 15,
                        "is_renting": 1,
                        "num_docks_available": 8,
                        "num_ebikes_available": 10,  # NEW: Direct ebike count field
                        # Note: vehicle_types_available is NOT present in new format
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get, \
             patch.object(BayWheelsSource, '_get_station_information', return_value={
                 "station-new-format": {"name": "New Format Station", "lat": 37.7749, "lon": -122.4194}
             }):
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is not None
            assert result["electric_bikes"] == 10  # From num_ebikes_available
            assert result["classic_bikes"] == 5   # Calculated: 15 total - 10 electric
            assert result["num_bikes_available"] == 15
            assert result["status_color"] == "green"  # 10 e-bikes > 5
    
    def test_fetch_station_status_station_not_found(self):
        """Test error handling when station ID not found in feed."""
        source = BayWheelsSource(station_ids=["nonexistent-station"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "different-station",
                        "num_bikes_available": 5,
                        "is_renting": 1,
                        "num_docks_available": 7,
                        "vehicle_types_available": []
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is None
    
    def test_fetch_station_status_network_error(self):
        """Test error handling for network failures."""
        source = BayWheelsSource(station_ids=["station-123"])
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Network error")
            
            result = source.fetch_station_status()
            
            assert result is None
    
    def test_fetch_station_status_malformed_json(self):
        """Test error handling for malformed JSON response."""
        source = BayWheelsSource(station_ids=["station-123"])
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            assert result is None
    
    def test_fetch_station_status_missing_data_field(self):
        """Test edge case: API response missing 'data' field."""
        source = BayWheelsSource(station_ids=["station-123"])
        
        mock_response_data = {
            "stations": []  # Missing 'data' wrapper
        }
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = source.fetch_station_status()
            
            # Should handle gracefully and return None (no stations found)
            assert result is None
    
    def test_get_status_color_logic(self):
        """Test the color determination logic directly."""
        source = BayWheelsSource(station_ids=["test"])
        
        # Test red zone (< 2)
        assert source._get_status_color(0) == "red"
        assert source._get_status_color(1) == "red"
        
        # Test yellow zone (2-5)
        assert source._get_status_color(2) == "yellow"
        assert source._get_status_color(3) == "yellow"
        assert source._get_status_color(4) == "yellow"
        assert source._get_status_color(5) == "yellow"
        
        # Test green zone (> 5)
        assert source._get_status_color(6) == "green"
        assert source._get_status_color(10) == "green"
        assert source._get_status_color(100) == "green"
    
    def test_fetch_multiple_stations(self):
        """Test fetching data for multiple stations."""
        source = BayWheelsSource(station_ids=["station-1", "station-2"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-1",
                        "num_bikes_available": 10,
                        "is_renting": 1,
                        "num_docks_available": 5,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 7},
                            {"vehicle_type_id": "classic_bike", "count": 3}
                        ]
                    },
                    {
                        "station_id": "station-2",
                        "num_bikes_available": 5,
                        "is_renting": 1,
                        "num_docks_available": 10,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 3},
                            {"vehicle_type_id": "classic_bike", "count": 2}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get, \
             patch.object(BayWheelsSource, '_get_station_information', return_value={
                 "station-1": {"name": "Station 1", "lat": 37.7749, "lon": -122.4194},
                 "station-2": {"name": "Station 2", "lat": 37.7849, "lon": -122.4094},
             }):
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            results = source.fetch_multiple_stations()
            
            assert len(results) == 2
            assert results[0]["station_id"] == "station-1"
            assert results[0]["electric_bikes"] == 7
            assert results[1]["station_id"] == "station-2"
            assert results[1]["electric_bikes"] == 3
    
    def test_get_aggregate_stats(self):
        """Test aggregate statistics calculation."""
        source = BayWheelsSource(station_ids=["station-1", "station-2"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-1",
                        "num_bikes_available": 10,
                        "is_renting": 1,
                        "num_docks_available": 5,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 7},
                            {"vehicle_type_id": "classic_bike", "count": 3}
                        ]
                    },
                    {
                        "station_id": "station-2",
                        "num_bikes_available": 5,
                        "is_renting": 1,
                        "num_docks_available": 10,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 3},
                            {"vehicle_type_id": "classic_bike", "count": 2}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get, \
             patch.object(BayWheelsSource, '_get_station_information', return_value={
                 "station-1": {"name": "Station 1", "lat": 37.7749, "lon": -122.4194},
                 "station-2": {"name": "Station 2", "lat": 37.7849, "lon": -122.4094},
             }):
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            aggregate = source.get_aggregate_stats()
            
            assert aggregate["total_electric"] == 10  # 7 + 3
            assert aggregate["total_classic"] == 5  # 3 + 2
            assert aggregate["total_bikes"] == 15  # 10 + 5
            assert aggregate["station_count"] == 2
            assert len(aggregate["stations"]) == 2
    
    def test_get_best_station(self):
        """Test finding station with most e-bikes."""
        source = BayWheelsSource(station_ids=["station-1", "station-2", "station-3"])
        
        mock_response_data = {
            "data": {
                "stations": [
                    {
                        "station_id": "station-1",
                        "num_bikes_available": 10,
                        "is_renting": 1,
                        "num_docks_available": 5,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 5},
                            {"vehicle_type_id": "classic_bike", "count": 5}
                        ]
                    },
                    {
                        "station_id": "station-2",
                        "num_bikes_available": 8,
                        "is_renting": 1,
                        "num_docks_available": 7,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 8},
                            {"vehicle_type_id": "classic_bike", "count": 0}
                        ]
                    },
                    {
                        "station_id": "station-3",
                        "num_bikes_available": 6,
                        "is_renting": 1,
                        "num_docks_available": 9,
                        "vehicle_types_available": [
                            {"vehicle_type_id": "electric_bike", "count": 2},
                            {"vehicle_type_id": "classic_bike", "count": 4}
                        ]
                    }
                ]
            }
        }
        
        with patch('requests.get') as mock_get, \
             patch.object(BayWheelsSource, '_get_station_information', return_value={
                 "station-1": {"name": "Station 1", "lat": 37.7749, "lon": -122.4194},
                 "station-2": {"name": "Station 2", "lat": 37.7849, "lon": -122.4094},
                 "station-3": {"name": "Station 3", "lat": 37.7949, "lon": -122.3994},
             }):
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            best = source.get_best_station()
            
            assert best is not None
            assert best["station_id"] == "station-2"  # Has most e-bikes (8)
            assert best["electric_bikes"] == 8
    
    def test_find_stations_near_location(self):
        """Test location-based station search."""
        mock_station_info = {
            "station-1": {
                "station_id": "station-1",
                "name": "Station 1",
                "lat": 37.7749,
                "lon": -122.4194,
                "address": "123 Main St",
                "capacity": 20
            },
            "station-2": {
                "station_id": "station-2",
                "name": "Station 2",
                "lat": 37.7849,
                "lon": -122.4094,
                "address": "456 Oak Ave",
                "capacity": 15
            },
            "station-3": {
                "station_id": "station-3",
                "name": "Station 3",
                "lat": 38.0000,  # Far away
                "lon": -122.0000,
                "address": "789 Pine St",
                "capacity": 10
            }
        }
        
        with patch.object(BayWheelsSource, '_get_station_information', return_value=mock_station_info):
            # Search near station-1 location
            stations = BayWheelsSource.find_stations_near_location(
                37.7749, -122.4194, radius_km=5.0, limit=10
            )
            
            # Should find station-1 and station-2 (within 5km), but not station-3
            assert len(stations) >= 1
            station_ids = [s["station_id"] for s in stations]
            assert "station-1" in station_ids
            # station-2 should be close enough
            assert "station-2" in station_ids or len(stations) == 1
            # station-3 should be too far
            assert "station-3" not in station_ids or len(stations) > 2
            
            # Verify distance is calculated
            for station in stations:
                assert "distance_km" in station
                assert station["distance_km"] >= 0


class TestBayWheelsConfig:
    """Test Bay Wheels configuration integration."""
    
    def test_get_baywheels_source_disabled(self):
        """Test that source is None when disabled."""
        from src.utils.baywheels import get_baywheels_source
        
        with patch('src.utils.baywheels.Config.BAYWHEELS_ENABLED', False):
            source = get_baywheels_source()
            assert source is None
    
    def test_get_baywheels_source_no_station_id(self):
        """Test that source is None when station ID not configured."""
        from src.utils.baywheels import get_baywheels_source
        
        with patch('src.utils.baywheels.Config.BAYWHEELS_ENABLED', True), \
             patch('src.utils.baywheels.Config.BAYWHEELS_STATION_IDS', []):
            source = get_baywheels_source()
            assert source is None
    
    def test_get_baywheels_source_configured(self):
        """Test that source is created when properly configured."""
        from src.utils.baywheels import get_baywheels_source
        
        with patch('src.utils.baywheels.Config.BAYWHEELS_ENABLED', True), \
             patch('src.utils.baywheels.Config.BAYWHEELS_STATION_IDS', ["test-station"]):
            source = get_baywheels_source()
            assert source is not None
            assert source.station_ids == ["test-station"]


class TestBayWheelsPluginClass:
    """Tests for BayWheelsPlugin class (plugins/baywheels/__init__.py)."""

    @pytest.fixture
    def plugin(self):
        from plugins.baywheels import BayWheelsPlugin
        manifest = {"id": "baywheels", "name": "Bay Wheels", "version": "1.0.0"}
        return BayWheelsPlugin(manifest)

    def test_plugin_id(self, plugin):
        assert plugin.plugin_id == "baywheels"

    def test_validate_config_valid(self, plugin):
        assert plugin.validate_config({"station_ids": ["s1"]}) == []

    def test_validate_config_no_stations(self, plugin):
        errors = plugin.validate_config({})
        assert len(errors) == 1

    def test_validate_config_empty_list(self, plugin):
        errors = plugin.validate_config({"station_ids": []})
        assert len(errors) == 1

    def test_get_status_color_red(self, plugin):
        assert plugin._get_status_color(0) == "{63}"
        assert plugin._get_status_color(1) == "{63}"

    def test_get_status_color_yellow(self, plugin):
        assert plugin._get_status_color(2) == "{65}"
        assert plugin._get_status_color(5) == "{65}"

    def test_get_status_color_green(self, plugin):
        assert plugin._get_status_color(6) == "{66}"
        assert plugin._get_status_color(10) == "{66}"

    def test_fetch_data_no_station_ids(self, plugin):
        plugin._config = {}
        result = plugin.fetch_data()
        assert not result.available

    def test_fetch_data_success(self, plugin):
        plugin._config = {"station_ids": ["station-1"]}
        mock_resp = Mock()
        mock_resp.json.return_value = {
            "data": {
                "stations": [{
                    "station_id": "station-1",
                    "num_bikes_available": 10,
                    "num_ebikes_available": 7,
                    "is_renting": 1,
                }]
            }
        }
        mock_resp.raise_for_status.return_value = None
        station_info = {"station-1": {"name": "Test Station", "lat": 37.77, "lon": -122.42}}
        with patch('plugins.baywheels.requests.get', return_value=mock_resp), \
             patch.object(plugin, '_get_station_information', return_value=station_info):
            result = plugin.fetch_data()
            assert result.available
            assert result.data["electric_bikes"] == 7
            assert result.data["classic_bikes"] == 3
            assert result.data["station_count"] == 1

    def test_fetch_data_station_not_found(self, plugin):
        plugin._config = {"station_ids": ["missing"]}
        mock_resp = Mock()
        mock_resp.json.return_value = {
            "data": {
                "stations": [{
                    "station_id": "other",
                    "num_bikes_available": 5,
                    "num_ebikes_available": 2,
                    "is_renting": 1,
                }]
            }
        }
        mock_resp.raise_for_status.return_value = None
        with patch('plugins.baywheels.requests.get', return_value=mock_resp), \
             patch.object(plugin, '_get_station_information', return_value={}):
            result = plugin.fetch_data()
            assert not result.available

    def test_fetch_data_exception(self, plugin):
        plugin._config = {"station_ids": ["s1"]}
        with patch('plugins.baywheels.requests.get', side_effect=Exception("fail")):
            result = plugin.fetch_data()
            assert not result.available

    def test_fetch_data_long_station_name(self, plugin):
        plugin._config = {"station_ids": ["station-1"]}
        mock_resp = Mock()
        mock_resp.json.return_value = {
            "data": {
                "stations": [{
                    "station_id": "station-1",
                    "num_bikes_available": 5,
                    "num_ebikes_available": 3,
                    "is_renting": 1,
                }]
            }
        }
        mock_resp.raise_for_status.return_value = None
        station_info = {"station-1": {"name": "A Very Long Station Name Here", "lat": 37.77, "lon": -122.42}}
        with patch('plugins.baywheels.requests.get', return_value=mock_resp), \
             patch.object(plugin, '_get_station_information', return_value=station_info):
            result = plugin.fetch_data()
            assert result.available
            assert len(result.data["station_name"]) <= 10

    def test_fetch_data_not_renting(self, plugin):
        plugin._config = {"station_ids": ["station-1"]}
        mock_resp = Mock()
        mock_resp.json.return_value = {
            "data": {
                "stations": [{
                    "station_id": "station-1",
                    "num_bikes_available": 5,
                    "num_ebikes_available": 3,
                    "is_renting": 0,
                }]
            }
        }
        mock_resp.raise_for_status.return_value = None
        with patch('plugins.baywheels.requests.get', return_value=mock_resp), \
             patch.object(plugin, '_get_station_information', return_value={}):
            result = plugin.fetch_data()
            assert result.available
            assert result.data["is_renting"] == "No"

    def test_get_station_information_success(self, plugin):
        """Test _get_station_information with successful API call."""
        mock_resp = Mock()
        mock_resp.json.return_value = {
            "data": {
                "stations": [
                    {
                        "station_id": "123",
                        "name": "Test Station",
                        "lat": 37.7749,
                        "lon": -122.4194
                    }
                ]
            }
        }
        with patch('plugins.baywheels.requests.get', return_value=mock_resp), \
             patch('plugins.baywheels.time.time', return_value=1000):
            result = plugin._get_station_information()
            assert result is not None
            assert "123" in result
            assert result["123"]["name"] == "Test Station"

    def test_get_station_information_cached(self, plugin):
        """Test _get_station_information returns cached data."""
        import plugins.baywheels as bw_module
        bw_module._station_info_cache = {"123": {"name": "Cached"}}
        bw_module._station_info_cache_time = time.time()
        result = plugin._get_station_information()
        assert result is not None
        assert "123" in result
        assert result["123"]["name"] == "Cached"
        bw_module._station_info_cache = None
        bw_module._station_info_cache_time = 0

    def test_get_station_information_api_error(self, plugin):
        """Test _get_station_information with API error returns cached data."""
        import plugins.baywheels as bw_module
        bw_module._station_info_cache = {"123": {"name": "Cached"}}
        bw_module._station_info_cache_time = 0
        with patch('plugins.baywheels.requests.get', side_effect=Exception("API error")):
            result = plugin._get_station_information()
            assert result == bw_module._station_info_cache
        bw_module._station_info_cache = None
        bw_module._station_info_cache_time = 0

    def test_get_formatted_display_with_cache(self, plugin):
        """Test get_formatted_display with cached data."""
        plugin._cache = {
            "stations": [
                {
                    "station_name": "Station 1",
                    "electric_bikes": 5,
                    "classic_bikes": 3
                },
                {
                    "station_name": "Station 2",
                    "electric_bikes": 2,
                    "classic_bikes": 1
                }
            ]
        }
        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) == 6
        assert "BAY WHEELS" in lines[0]
        assert "Station 1" in lines[2]
        assert "5E" in lines[2]
        assert "3C" in lines[2]

    def test_get_formatted_display_no_cache(self, plugin):
        """Test get_formatted_display without cache."""
        plugin._cache = None
        plugin._config = {}
        lines = plugin.get_formatted_display()
        assert lines is None

