"""Tests for Traffic multi-route support and backward compatibility."""

import pytest
from src.utils.traffic import TrafficSource


class TestTrafficMultiRoute:
    """Test Traffic multi-route functionality."""
    
    def test_single_route_backward_compatibility(self):
        """Test that single route dict still works."""
        source = TrafficSource(
            api_key="test_key",
            routes=[{
                "origin": "123 Main St",
                "destination": "456 Market St",
                "destination_name": "WORK"
            }]
        )
        
        assert len(source.routes) == 1
        assert source.origin == "123 Main St"
        assert source.destination == "456 Market St"
        assert source.destination_name == "WORK"
    
    def test_multiple_routes(self):
        """Test that multiple routes work."""
        source = TrafficSource(
            api_key="test_key",
            routes=[
                {
                    "origin": "Home",
                    "destination": "Work",
                    "destination_name": "WORK"
                },
                {
                    "origin": "Home",
                    "destination": "Airport",
                    "destination_name": "AIRPORT"
                }
            ]
        )
        
        assert len(source.routes) == 2
        assert source.origin == "Home"  # First route for backward compat
        assert source.routes[1]["destination_name"] == "AIRPORT"
    
    def test_empty_routes(self):
        """Test handling of empty routes."""
        source = TrafficSource(
            api_key="test_key",
            routes=[]
        )
        
        assert source.routes == []
    
    def test_traffic_index_calculation(self):
        """Test traffic index calculation."""
        # Normal traffic (1.0)
        assert TrafficSource.calculate_traffic_index(1000, 1000) == 1.0
        
        # 20% slower (1.2)
        assert TrafficSource.calculate_traffic_index(1200, 1000) == 1.2
        
        # 50% slower (1.5)
        assert TrafficSource.calculate_traffic_index(1500, 1000) == 1.5
    
    def test_traffic_status(self):
        """Test traffic status determination."""
        # Light traffic
        status, color = TrafficSource.get_traffic_status(1.0)
        assert status == "LIGHT"
        assert color == "GREEN"
        
        # Moderate traffic
        status, color = TrafficSource.get_traffic_status(1.3)
        assert status == "MODERATE"
        assert color == "YELLOW"
        
        # Heavy traffic
        status, color = TrafficSource.get_traffic_status(1.6)
        assert status == "HEAVY"
        assert color == "RED"



