"""Tests for regional transit cache service."""

import pytest
import time
import json
import threading
from unittest.mock import Mock, patch
from src.utils.transit_cache import TransitCache, get_transit_cache


@pytest.fixture(autouse=True)
def reset_transit_cache():
    """Reset TransitCache singleton before each test to ensure test isolation."""
    # Import the module-level variable
    import src.utils.transit_cache as transit_cache_module
    
    # Stop any running threads
    if TransitCache._instance is not None:
        cache = TransitCache._instance
        if hasattr(cache, '_stop_event'):
            cache._stop_event.set()
        if hasattr(cache, '_refresh_thread') and cache._refresh_thread:
            cache._refresh_thread.join(timeout=1)
    
    # Reset both class-level and module-level singletons
    TransitCache._instance = None
    TransitCache._lock = threading.Lock()
    transit_cache_module._cache_instance = None
    
    yield
    
    # Cleanup after test
    if TransitCache._instance is not None:
        cache = TransitCache._instance
        if hasattr(cache, '_stop_event'):
            cache._stop_event.set()
        if hasattr(cache, '_refresh_thread') and cache._refresh_thread:
            cache._refresh_thread.join(timeout=1)
        TransitCache._instance = None
        transit_cache_module._cache_instance = None


@pytest.fixture
def mock_regional_response():
    """Mock 511.org regional StopMonitoring API response."""
    return {
        "ServiceDelivery": {
            "StopMonitoringDelivery": {
                "MonitoredStopVisit": [
                    {
                        "MonitoredVehicleJourney": {
                            "OperatorRef": "SF",
                            "PublishedLineName": "N-JUDAH",
                            "MonitoredCall": {
                                "StopPointRef": "SF_15210",
                                "StopPointName": "Judah St & 34th Ave",
                                "ExpectedArrivalTime": "2024-12-26T10:05:00-08:00"
                            }
                        }
                    },
                    {
                        "MonitoredVehicleJourney": {
                            "OperatorRef": "SF",
                            "PublishedLineName": "N-JUDAH",
                            "MonitoredCall": {
                                "StopPointRef": "SF_15210",
                                "StopPointName": "Judah St & 34th Ave",
                                "ExpectedArrivalTime": "2024-12-26T10:12:00-08:00"
                            }
                        }
                    },
                    {
                        "MonitoredVehicleJourney": {
                            "OperatorRef": "BA",
                            "PublishedLineName": "RED",
                            "MonitoredCall": {
                                "StopPointRef": "BA_12TH",
                                "StopPointName": "12th St Oakland City Center",
                                "ExpectedArrivalTime": "2024-12-26T10:03:00-08:00"
                            }
                        }
                    }
                ]
            }
        }
    }


class TestTransitCache:
    """Test cases for TransitCache singleton service."""
    
    def test_singleton_pattern(self):
        """Test that TransitCache is a singleton."""
        cache1 = TransitCache()
        cache2 = TransitCache()
        assert cache1 is cache2
        
        cache3 = get_transit_cache()
        assert cache3 is cache1
    
    def test_configure(self):
        """Test cache configuration."""
        cache = TransitCache()
        cache.configure(
            api_key="test-key",
            refresh_interval=60,
            enabled=True
        )
        
        status = cache.get_status()
        assert status["enabled"] is True
        assert status["refresh_interval"] == 60
    
    def test_parse_and_index(self, mock_regional_response):
        """Test parsing and indexing of regional transit data."""
        cache = TransitCache()
        cache._parse_and_index(mock_regional_response)
        
        # Check SF stops are indexed
        sf_stops = cache.get_all_stops_for_agency("SF")
        assert "15210" in sf_stops
        assert len(sf_stops["15210"]) == 2  # Two N-Judah arrivals
        
        # Check BA (BART) stops are indexed
        ba_stops = cache.get_all_stops_for_agency("BA")
        assert "12TH" in ba_stops
        assert len(ba_stops["12TH"]) == 1
    
    def test_get_stops_data(self, mock_regional_response):
        """Test retrieving data for specific stops."""
        cache = TransitCache()
        cache._parse_and_index(mock_regional_response)
        cache._last_success = time.time()  # Mark as successful
        
        # Get specific SF stops
        result = cache.get_stops_data("SF", ["15210", "99999"])
        
        assert "15210" in result
        assert len(result["15210"]) == 2
        assert "99999" in result
        assert len(result["99999"]) == 0  # No data for non-existent stop
    
    @patch('src.utils.transit_cache.requests.get')
    def test_refresh_data_success(self, mock_get, mock_regional_response):
        """Test successful data refresh."""
        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(mock_regional_response)
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        cache = TransitCache()
        cache.configure(api_key="test-key", enabled=True)
        cache._refresh_data()
        
        # Check cache was updated
        status = cache.get_status()
        assert status["refresh_count"] == 1
        assert status["last_success"] > 0
        assert cache.is_ready()
        
        # Check data is available
        sf_stops = cache.get_all_stops_for_agency("SF")
        assert "15210" in sf_stops
    
    @patch('src.utils.transit_cache.requests.get')
    def test_refresh_data_rate_limit(self, mock_get):
        """Test handling of rate limit errors."""
        # Mock HTTP 429 response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.raise_for_status = Mock(
            side_effect=Exception("Rate limited")
        )
        mock_get.return_value = mock_response
        
        cache = TransitCache()
        cache.configure(api_key="test-key", enabled=True)
        cache._refresh_data()
        
        # Check error was recorded
        status = cache.get_status()
        assert status["error_count"] > 0
    
    def test_get_status(self):
        """Test cache status reporting."""
        cache = TransitCache()
        cache.configure(api_key="test-key", refresh_interval=90, enabled=True)
        
        status = cache.get_status()
        
        # Check required fields
        assert "enabled" in status
        assert "refresh_interval" in status
        assert "last_refresh" in status
        assert "last_success" in status
        assert "cache_age_seconds" in status
        assert "is_stale" in status
        assert "refresh_count" in status
        assert "error_count" in status
        assert "cache_hits" in status
        assert "agencies_cached" in status
        assert "total_stops_cached" in status
        assert "thread_alive" in status
    
    def test_is_ready(self):
        """Test cache ready state."""
        cache = TransitCache()
        
        # Cache not ready initially
        assert not cache.is_ready()
        
        # Mark as successful
        with cache._data_lock:
            cache._last_success = time.time()
        
        # Now should be ready
        assert cache.is_ready()
    
    def test_stale_warning(self, mock_regional_response):
        """Test warning for stale cache."""
        cache = TransitCache()
        cache._parse_and_index(mock_regional_response)
        
        # Set last success to 10 minutes ago
        with cache._data_lock:
            cache._last_success = time.time() - 600
        
        status = cache.get_status()
        assert status["is_stale"] is True
        assert status["cache_age_seconds"] > cache.STALE_WARNING_THRESHOLD
    
    def test_cache_hits_tracking(self, mock_regional_response):
        """Test that cache hits are tracked."""
        cache = TransitCache()
        cache._parse_and_index(mock_regional_response)
        cache._last_success = time.time()
        
        initial_hits = cache.get_status()["cache_hits"]
        
        # Access cache multiple times
        cache.get_stops_data("SF", ["15210"])
        cache.get_stops_data("SF", ["15210"])
        cache.get_stops_data("BA", ["12TH"])
        
        final_hits = cache.get_status()["cache_hits"]
        assert final_hits == initial_hits + 3


class TestTransitCacheIntegration:
    """Integration tests for transit cache with real-ish scenarios."""
    
    @patch('src.utils.transit_cache.requests.get')
    def test_multiple_agencies(self, mock_get):
        """Test caching data from multiple transit agencies."""
        response_data = {
            "ServiceDelivery": {
                "StopMonitoringDelivery": {
                    "MonitoredStopVisit": [
                        # Muni
                        {
                            "MonitoredVehicleJourney": {
                                "OperatorRef": "SF",
                                "PublishedLineName": "N-JUDAH",
                                "MonitoredCall": {
                                    "StopPointRef": "SF_15210",
                                    "StopPointName": "Judah St",
                                    "ExpectedArrivalTime": "2024-12-26T10:05:00-08:00"
                                }
                            }
                        },
                        # BART
                        {
                            "MonitoredVehicleJourney": {
                                "OperatorRef": "BA",
                                "PublishedLineName": "YELLOW",
                                "MonitoredCall": {
                                    "StopPointRef": "BA_EMBR",
                                    "StopPointName": "Embarcadero",
                                    "ExpectedArrivalTime": "2024-12-26T10:03:00-08:00"
                                }
                            }
                        },
                        # Caltrain
                        {
                            "MonitoredVehicleJourney": {
                                "OperatorRef": "CT",
                                "PublishedLineName": "LOCAL",
                                "MonitoredCall": {
                                    "StopPointRef": "CT_SF",
                                    "StopPointName": "San Francisco",
                                    "ExpectedArrivalTime": "2024-12-26T10:15:00-08:00"
                                }
                            }
                        }
                    ]
                }
            }
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(response_data)
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        cache = TransitCache()
        cache.configure(api_key="test-key", enabled=True)
        cache._refresh_data()
        
        # Verify all agencies are cached
        status = cache.get_status()
        assert "SF" in status["agencies_cached"]
        assert "BA" in status["agencies_cached"]
        assert "CT" in status["agencies_cached"]
        
        # Verify we can access each agency's data
        sf_data = cache.get_stops_data("SF", ["15210"])
        assert len(sf_data["15210"]) == 1
        
        ba_data = cache.get_stops_data("BA", ["EMBR"])
        assert len(ba_data["EMBR"]) == 1
        
        ct_data = cache.get_stops_data("CT", ["SF"])
        assert len(ct_data["SF"]) == 1



