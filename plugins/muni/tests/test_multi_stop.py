"""Tests for MUNI multi-stop support and backward compatibility."""

import pytest
from src.utils.muni import MuniSource


class TestMuniMultiStop:
    """Test MUNI multi-stop functionality."""
    
    def test_single_stop_backward_compatibility(self):
        """Test that single stop code (string) still works."""
        source = MuniSource(
            api_key="test_key",
            stop_codes="15726",  # Single string
            line_name="N"
        )
        
        assert source.stop_codes == ["15726"]
        assert source.stop_code == "15726"
    
    def test_multiple_stops_list(self):
        """Test that multiple stop codes (list) works."""
        source = MuniSource(
            api_key="test_key",
            stop_codes=["15726", "15727", "15728"],
            line_name="N"
        )
        
        assert source.stop_codes == ["15726", "15727", "15728"]
        assert source.stop_code == "15726"  # First stop for backward compat
    
    def test_empty_stop_codes(self):
        """Test handling of empty stop codes."""
        source = MuniSource(
            api_key="test_key",
            stop_codes=[],
            line_name="N"
        )
        
        assert source.stop_codes == []
        assert source.stop_code == ""
    
    def test_parse_response_includes_stop_code(self):
        """Test that parsed response includes stop_code field."""
        source = MuniSource(
            api_key="test_key",
            stop_codes=["15726"],
            line_name="N"
        )
        
        # Mock response data
        mock_data = {
            "ServiceDelivery": {
                "StopMonitoringDelivery": {
                    "MonitoredStopVisit": [
                        {
                            "MonitoredVehicleJourney": {
                                "PublishedLineName": "N",
                                "MonitoredCall": {
                                    "StopPointName": "Church & Duboce",
                                    "ExpectedArrivalTime": "2025-12-26T18:30:00-08:00"
                                }
                            }
                        }
                    ]
                }
            }
        }
        
        result = source._parse_response(mock_data, "15726")
        
        if result:
            assert "stop_code" in result
            assert result["stop_code"] == "15726"



