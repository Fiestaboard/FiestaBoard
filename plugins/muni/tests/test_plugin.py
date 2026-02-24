"""Tests for Muni transit data source."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import json

from src.utils.muni import MuniSource, get_muni_source, COLOR_RED, COLOR_ORANGE


class TestMuniSourceParsing:
    """Tests for Muni API response parsing."""
    
    @pytest.fixture
    def muni_source(self):
        """Create a MuniSource instance for testing."""
        return MuniSource(
            api_key="test_api_key",
            stop_codes=["15726"],
            line_name="N"
        )
    
    @pytest.fixture
    def sample_api_response(self):
        """Sample 511.org StopMonitoring API response."""
        # Calculate future times for arrivals
        now = datetime.now(timezone.utc)
        arrival1 = (now + timedelta(minutes=4)).isoformat()
        arrival2 = (now + timedelta(minutes=12)).isoformat()
        arrival3 = (now + timedelta(minutes=19)).isoformat()
        
        return {
            "ServiceDelivery": {
                "StopMonitoringDelivery": {
                    "MonitoredStopVisit": [
                        {
                            "MonitoredVehicleJourney": {
                                "PublishedLineName": "N",
                                "Occupancy": "MANY_SEATS",
                                "MonitoredCall": {
                                    "StopPointName": "Church St & Duboce Ave",
                                    "ExpectedArrivalTime": arrival1,
                                }
                            }
                        },
                        {
                            "MonitoredVehicleJourney": {
                                "PublishedLineName": "N",
                                "Occupancy": "FEW_SEATS",
                                "MonitoredCall": {
                                    "StopPointName": "Church St & Duboce Ave",
                                    "ExpectedArrivalTime": arrival2,
                                }
                            }
                        },
                        {
                            "MonitoredVehicleJourney": {
                                "PublishedLineName": "N",
                                "Occupancy": "STANDING",
                                "MonitoredCall": {
                                    "StopPointName": "Church St & Duboce Ave",
                                    "ExpectedArrivalTime": arrival3,
                                }
                            }
                        },
                    ]
                }
            }
        }
    
    @pytest.fixture
    def delayed_api_response(self):
        """Sample API response with delay status."""
        now = datetime.now(timezone.utc)
        arrival1 = (now + timedelta(minutes=7)).isoformat()
        arrival2 = (now + timedelta(minutes=15)).isoformat()
        
        return {
            "ServiceDelivery": {
                "StopMonitoringDelivery": {
                    "MonitoredStopVisit": [
                        {
                            "MonitoredVehicleJourney": {
                                "PublishedLineName": "N",
                                "Occupancy": "MANY_SEATS",
                                "Delay": "PT5M",  # 5 minute delay
                                "MonitoredCall": {
                                    "StopPointName": "Church St & Duboce Ave",
                                    "ExpectedArrivalTime": arrival1,
                                }
                            }
                        },
                        {
                            "MonitoredVehicleJourney": {
                                "PublishedLineName": "N",
                                "Occupancy": "STANDING",
                                "MonitoredCall": {
                                    "StopPointName": "Church St & Duboce Ave",
                                    "ExpectedArrivalTime": arrival2,
                                }
                            }
                        },
                    ]
                }
            }
        }
    
    @pytest.fixture
    def full_occupancy_response(self):
        """Sample API response with FULL occupancy."""
        now = datetime.now(timezone.utc)
        arrival1 = (now + timedelta(minutes=3)).isoformat()
        arrival2 = (now + timedelta(minutes=10)).isoformat()
        
        return {
            "ServiceDelivery": {
                "StopMonitoringDelivery": {
                    "MonitoredStopVisit": [
                        {
                            "MonitoredVehicleJourney": {
                                "PublishedLineName": "N",
                                "Occupancy": "FULL",
                                "MonitoredCall": {
                                    "StopPointName": "Church St & Duboce Ave",
                                    "ExpectedArrivalTime": arrival1,
                                }
                            }
                        },
                        {
                            "MonitoredVehicleJourney": {
                                "PublishedLineName": "N",
                                "Occupancy": "FEW_SEATS",
                                "MonitoredCall": {
                                    "StopPointName": "Church St & Duboce Ave",
                                    "ExpectedArrivalTime": arrival2,
                                }
                            }
                        },
                    ]
                }
            }
        }
    
    def test_parse_normal_response(self, muni_source, sample_api_response):
        """Test parsing a normal API response without delays."""
        result = muni_source._parse_response(sample_api_response)
        
        assert result is not None
        assert result["line"] == "N-JUDAH"  # Display name, not raw code
        assert result["stop_name"] == "Church St & Duboce Ave"
        assert len(result["arrivals"]) == 3
        assert result["is_delayed"] is False
        assert result["color_code"] == 0  # No special color
        
        # Check arrival times are reasonable (within a few minutes of expected)
        for arrival in result["arrivals"]:
            assert "minutes" in arrival
            assert "occupancy" in arrival
            assert "is_full" in arrival
            assert arrival["is_full"] is False
    
    def test_parse_delayed_response(self, muni_source, delayed_api_response):
        """Test parsing a response with delay status."""
        result = muni_source._parse_response(delayed_api_response)
        
        assert result is not None
        assert result["is_delayed"] is True
        assert result["delay_description"] == "5 min delay"
        assert result["color_code"] == COLOR_RED  # Red for delay
        
        # Formatted string should contain DELAY indicator
        assert "(DELAY)" in result["formatted"]
        assert "{63}" in result["formatted"]  # Red color code
    
    def test_parse_full_occupancy_response(self, muni_source, full_occupancy_response):
        """Test parsing a response with FULL occupancy."""
        result = muni_source._parse_response(full_occupancy_response)
        
        assert result is not None
        assert len(result["arrivals"]) == 2
        
        # First arrival should be marked as full
        assert result["arrivals"][0]["is_full"] is True
        assert result["arrivals"][0]["occupancy"] == "FULL"
        
        # Second arrival should not be full
        assert result["arrivals"][1]["is_full"] is False
        
        # Color should be orange for full (when no delay)
        assert result["color_code"] == COLOR_ORANGE
        
        # Formatted string should have orange marker for full train
        assert "{64}" in result["formatted"]  # Orange color code
    
    def test_parse_empty_response(self, muni_source):
        """Test parsing an empty response."""
        empty_response = {
            "ServiceDelivery": {
                "StopMonitoringDelivery": {
                    "MonitoredStopVisit": []
                }
            }
        }
        
        result = muni_source._parse_response(empty_response)
        assert result is None
    
    def test_parse_list_format_response(self, muni_source, sample_api_response):
        """Test parsing when StopMonitoringDelivery is a list."""
        # Wrap in list format (511.org sometimes returns this)
        sample_api_response["ServiceDelivery"]["StopMonitoringDelivery"] = [
            sample_api_response["ServiceDelivery"]["StopMonitoringDelivery"]
        ]
        
        result = muni_source._parse_response(sample_api_response)
        assert result is not None
        assert result["line"] == "N-JUDAH"
    
    def test_parse_list_field_values(self, muni_source):
        """Test parsing when field values are lists (511.org quirk)."""
        now = datetime.now(timezone.utc)
        arrival1 = (now + timedelta(minutes=5)).isoformat()
        
        response = {
            "ServiceDelivery": {
                "StopMonitoringDelivery": {
                    "MonitoredStopVisit": [
                        {
                            "MonitoredVehicleJourney": {
                                "PublishedLineName": ["N"],  # List instead of string
                                "Occupancy": ["MANY_SEATS"],  # List instead of string
                                "MonitoredCall": {
                                    "StopPointName": ["Church St & Duboce Ave"],
                                    "ExpectedArrivalTime": arrival1,
                                }
                            }
                        },
                    ]
                }
            }
        }
        
        result = muni_source._parse_response(response)
        assert result is not None
        assert result["line"] == "N-JUDAH"
        assert result["stop_name"] == "Church St & Duboce Ave"
    
    def test_line_name_filter(self):
        """Test line_name is stored on source.
        
        Note: The line_name filter is used for configuration but _parse_response
        returns all lines for flexibility. Filtering can be done by callers
        using the 'lines' dict in the result.
        """
        source_n = MuniSource(api_key="test", stop_codes=["15726"], line_name="N")
        source_j = MuniSource(api_key="test", stop_codes=["15726"], line_name="J")
        
        assert source_n.line_name == "N"
        assert source_j.line_name == "J"
        
        now = datetime.now(timezone.utc)
        arrival = (now + timedelta(minutes=5)).isoformat()
        
        response = {
            "ServiceDelivery": {
                "StopMonitoringDelivery": {
                    "MonitoredStopVisit": [
                        {
                            "MonitoredVehicleJourney": {
                                "PublishedLineName": "N",
                                "Occupancy": "MANY_SEATS",
                                "MonitoredCall": {
                                    "StopPointName": "Test Stop",
                                    "ExpectedArrivalTime": arrival,
                                }
                            }
                        },
                    ]
                }
            }
        }
        
        # parse_response returns all lines (filtering is done at higher level)
        result_n = source_n._parse_response(response)
        assert result_n is not None
        assert result_n["line"] == "N-JUDAH"
        
        # Callers can use the 'lines' dict to filter by specific line
        assert "N" in result_n["lines"]


class TestMuniSourceFormatting:
    """Tests for Muni display formatting."""
    
    @pytest.fixture
    def muni_source(self):
        return MuniSource(api_key="test", stop_codes=["15726"])
    
    def test_format_display_basic(self, muni_source):
        """Test basic display formatting."""
        arrivals = [
            {"minutes": 4, "occupancy": "MANY_SEATS", "is_full": False},
            {"minutes": 12, "occupancy": "FEW_SEATS", "is_full": False},
            {"minutes": 19, "occupancy": "STANDING", "is_full": False},
        ]
        
        result = muni_source._format_display("N", arrivals, is_delayed=False)
        
        assert "N-JUDAH" in result
        assert "4" in result
        assert "12" in result
        assert "19" in result
        assert "MIN" in result
        assert "(DELAY)" not in result
    
    def test_format_display_with_delay(self, muni_source):
        """Test display formatting with delay."""
        arrivals = [
            {"minutes": 7, "occupancy": "MANY_SEATS", "is_full": False},
        ]
        
        result = muni_source._format_display("N", arrivals, is_delayed=True)
        
        assert "(DELAY)" in result
        assert "{63}" in result  # Red color code
    
    def test_format_display_with_full_train(self, muni_source):
        """Test display formatting with full train."""
        arrivals = [
            {"minutes": 3, "occupancy": "FULL", "is_full": True},
            {"minutes": 10, "occupancy": "FEW_SEATS", "is_full": False},
        ]
        
        result = muni_source._format_display("N", arrivals, is_delayed=False)
        
        # Full train time should have orange marker
        assert "{64}3" in result
        # Non-full train time should not have marker
        assert ", 10 " in result or ", 10 MIN" in result
    
    def test_get_display_line_name(self, muni_source):
        """Test line name display mapping."""
        assert muni_source._get_display_line_name("N") == "N-JUDAH"
        assert muni_source._get_display_line_name("J") == "J-CHURCH"
        assert muni_source._get_display_line_name("K") == "K-INGLESIDE"
        assert muni_source._get_display_line_name("L") == "L-TARAVAL"
        assert muni_source._get_display_line_name("M") == "M-OCEAN VIEW"
        assert muni_source._get_display_line_name("T") == "T-THIRD"
        assert muni_source._get_display_line_name("F") == "F-MARKET"
        # Unknown line should return as-is
        assert muni_source._get_display_line_name("X") == "X"
    
    def test_format_delay_duration(self, muni_source):
        """Test delay duration formatting."""
        assert muni_source._format_delay("PT5M") == "5 min delay"
        assert muni_source._format_delay("PT2M30S") == "2 min delay"
        assert muni_source._format_delay("PT10M") == "10 min delay"
        assert muni_source._format_delay("PT0M") == "Delayed"
        assert muni_source._format_delay("invalid") == "Delayed"


class TestMuniSourceAPI:
    """Tests for Muni API interactions with transit cache."""
    
    @pytest.fixture
    def muni_source(self):
        return MuniSource(api_key="test_key", stop_codes=["15726"], line_name="N")
    
    @pytest.fixture
    def mock_cache_visits(self):
        """Mock transit cache visits for testing."""
        now = datetime.now(timezone.utc)
        arrival = (now + timedelta(minutes=5)).isoformat()
        
        return [
            {
                "MonitoredVehicleJourney": {
                    "PublishedLineName": "N",
                    "Occupancy": "MANY_SEATS",
                    "MonitoredCall": {
                        "StopPointName": "Test Stop",
                        "ExpectedArrivalTime": arrival,
                    }
                }
            }
        ]
    
    @patch('src.utils.muni.get_transit_cache')
    def test_fetch_arrivals_success(self, mock_get_cache, muni_source, mock_cache_visits):
        """Test successful fetch from transit cache."""
        # Mock cache
        mock_cache = Mock()
        mock_cache.is_ready.return_value = True
        mock_cache.get_stops_data.return_value = {"15726": mock_cache_visits}
        mock_get_cache.return_value = mock_cache
        
        result = muni_source.fetch_arrivals()
        
        assert result is not None
        assert result["line"] == "N-JUDAH"
        mock_cache.get_stops_data.assert_called_once_with("SF", ["15726"])
    
    @patch('src.utils.muni.get_transit_cache')
    def test_fetch_arrivals_cache_not_ready(self, mock_get_cache, muni_source):
        """Test handling when cache is not ready."""
        # Mock cache not ready
        mock_cache = Mock()
        mock_cache.is_ready.return_value = False
        mock_get_cache.return_value = mock_cache
        
        result = muni_source.fetch_arrivals()
        
        assert result is None
    
    @patch('src.utils.muni.get_transit_cache')
    def test_fetch_arrivals_no_data_in_cache(self, mock_get_cache, muni_source):
        """Test handling when stop has no data in cache."""
        # Mock cache with no data for stop
        mock_cache = Mock()
        mock_cache.is_ready.return_value = True
        mock_cache.get_stops_data.return_value = {"15726": []}
        mock_get_cache.return_value = mock_cache
        
        result = muni_source.fetch_arrivals()
        
        assert result is None
    
    @patch('src.utils.muni.get_transit_cache')
    def test_fetch_multiple_stops(self, mock_get_cache, mock_cache_visits):
        """Test fetching multiple stops from cache."""
        now = datetime.now(timezone.utc)
        arrival2 = (now + timedelta(minutes=8)).isoformat()
        
        mock_cache_visits_stop2 = [
            {
                "MonitoredVehicleJourney": {
                    "PublishedLineName": "N",
                    "Occupancy": "FEW_SEATS",
                    "MonitoredCall": {
                        "StopPointName": "Test Stop 2",
                        "ExpectedArrivalTime": arrival2,
                    }
                }
            }
        ]
        
        # Mock cache with multiple stops
        mock_cache = Mock()
        mock_cache.is_ready.return_value = True
        mock_cache.get_stops_data.return_value = {
            "15726": mock_cache_visits,
            "15727": mock_cache_visits_stop2
        }
        mock_get_cache.return_value = mock_cache
        
        source = MuniSource(api_key="test", stop_codes=["15726", "15727"])
        results = source.fetch_multiple_stops()
        
        assert len(results) == 2
        assert results[0]["stop_code"] == "15726"
        assert results[1]["stop_code"] == "15727"


class TestGetMuniSource:
    """Tests for get_muni_source factory function."""
    
    @patch('src.utils.muni.Config')
    def test_get_muni_source_configured(self, mock_config):
        """Test getting source when properly configured."""
        mock_config.MUNI_API_KEY = "test_key"
        mock_config.MUNI_STOP_CODES = ["15726"]
        mock_config.MUNI_STOP_CODE = ""  # Empty fallback
        mock_config.MUNI_LINE_NAME = "N"
        mock_config.TRANSIT_CACHE_REFRESH_SECONDS = 90
        mock_config.TRANSIT_CACHE_ENABLED = False  # Disable cache for test
        
        source = get_muni_source()
        
        assert source is not None
        assert source.api_key == "test_key"
        assert source.stop_codes == ["15726"]
        assert source.line_name == "N"
    
    @patch('src.utils.muni.Config')
    def test_get_muni_source_no_api_key(self, mock_config):
        """Test getting source without API key."""
        mock_config.MUNI_API_KEY = ""
        mock_config.MUNI_STOP_CODES = ["15726"]
        mock_config.MUNI_STOP_CODE = ""
        
        source = get_muni_source()
        
        assert source is None
    
    @patch('src.utils.muni.Config')
    def test_get_muni_source_no_stop_code(self, mock_config):
        """Test getting source without stop code returns source with empty stops.
        
        The source is returned even without stops so template variables
        are available in the UI.
        """
        mock_config.MUNI_API_KEY = "test_key"
        mock_config.MUNI_STOP_CODES = []
        mock_config.MUNI_STOP_CODE = ""
        mock_config.MUNI_LINE_NAME = ""
        mock_config.TRANSIT_CACHE_REFRESH_SECONDS = 90
        mock_config.TRANSIT_CACHE_ENABLED = False
        
        source = get_muni_source()
        
        # Source is returned even without stops for UI template variable access
        assert source is not None
        assert source.stop_codes == []
    
    @patch('src.utils.muni.Config')
    def test_get_muni_source_no_line_filter(self, mock_config):
        """Test getting source without line filter."""
        mock_config.MUNI_API_KEY = "test_key"
        mock_config.MUNI_STOP_CODES = ["15726"]
        mock_config.MUNI_STOP_CODE = ""
        mock_config.MUNI_LINE_NAME = ""
        mock_config.TRANSIT_CACHE_REFRESH_SECONDS = 90
        mock_config.TRANSIT_CACHE_ENABLED = False
        
        source = get_muni_source()
        
        assert source is not None
        assert source.line_name is None


class TestMuniTimeParsing:
    """Tests for time parsing and calculation."""
    
    @pytest.fixture
    def muni_source(self):
        return MuniSource(api_key="test", stop_codes=["15726"])
    
    def test_calculate_minutes_until_future(self, muni_source):
        """Test calculating minutes for future arrival."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(minutes=10)
        
        minutes = muni_source._calculate_minutes_until(future.isoformat())
        
        # Allow some margin for test execution time
        assert 9 <= minutes <= 11
    
    def test_calculate_minutes_until_past(self, muni_source):
        """Test calculating minutes for past time (should return 0)."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=5)
        
        minutes = muni_source._calculate_minutes_until(past.isoformat())
        
        assert minutes == 0
    
    def test_calculate_minutes_until_with_z_timezone(self, muni_source):
        """Test parsing ISO timestamp with Z timezone."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(minutes=15)
        # Format with Z instead of +00:00
        timestamp = future.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        minutes = muni_source._calculate_minutes_until(timestamp)
        
        assert 14 <= minutes <= 16
    
    def test_calculate_minutes_until_invalid(self, muni_source):
        """Test handling invalid timestamp."""
        minutes = muni_source._calculate_minutes_until("not a timestamp")
        
        assert minutes is None


class TestMuniFormatter:
    """Tests for Muni message formatter."""
    
    def test_format_muni_basic(self):
        """Test basic muni formatting."""
        from src.formatters.message_formatter import MessageFormatter
        
        formatter = MessageFormatter()
        muni_data = {
            "line": "N-JUDAH",
            "stop_name": "Church & Duboce",
            "arrivals": [
                {"minutes": 4, "occupancy": "MANY_SEATS", "is_full": False},
                {"minutes": 12, "occupancy": "FEW_SEATS", "is_full": False},
            ],
            "is_delayed": False,
            "delay_description": "",
        }
        
        result = formatter.format_muni(muni_data)
        
        assert "MUNI" in result
        assert "N-JUDAH" in result
        assert "4" in result
        assert "12" in result
    
    def test_format_muni_with_delay(self):
        """Test muni formatting with delay."""
        from src.formatters.message_formatter import MessageFormatter
        
        formatter = MessageFormatter()
        muni_data = {
            "line": "N-JUDAH",
            "stop_name": "Church & Duboce",
            "arrivals": [
                {"minutes": 7, "occupancy": "MANY_SEATS", "is_full": False},
            ],
            "is_delayed": True,
            "delay_description": "5 min delay",
        }
        
        result = formatter.format_muni(muni_data)
        
        assert "{red}" in result
        assert "(DELAY)" in result
    
    def test_format_muni_with_full_train(self):
        """Test muni formatting with full occupancy."""
        from src.formatters.message_formatter import MessageFormatter
        
        formatter = MessageFormatter()
        muni_data = {
            "line": "N-JUDAH",
            "stop_name": "Church & Duboce",
            "arrivals": [
                {"minutes": 3, "occupancy": "FULL", "is_full": True},
            ],
            "is_delayed": False,
            "delay_description": "",
        }
        
        result = formatter.format_muni(muni_data)
        
        assert "{orange}" in result
    
    def test_format_muni_empty(self):
        """Test formatting empty muni data."""
        from src.formatters.message_formatter import MessageFormatter
        
        formatter = MessageFormatter()
        
        result = formatter.format_muni(None)
        
        assert "No arrivals" in result


class TestMuniPluginClass:
    """Tests for MuniPlugin class (plugins/muni/__init__.py)."""

    @pytest.fixture
    def plugin(self):
        from plugins.muni import MuniPlugin
        manifest = {"id": "muni", "name": "SF Muni", "version": "1.0.0"}
        return MuniPlugin(manifest)

    def test_plugin_id(self, plugin):
        assert plugin.plugin_id == "muni"

    def test_validate_config_valid(self, plugin):
        assert plugin.validate_config({"api_key": "k", "stop_codes": ["1"]}) == []

    def test_validate_config_missing_key(self, plugin):
        errors = plugin.validate_config({"stop_codes": ["1"]})
        assert len(errors) == 1

    def test_validate_config_missing_stops(self, plugin):
        errors = plugin.validate_config({"api_key": "k"})
        assert len(errors) == 1

    def test_validate_config_empty(self, plugin):
        errors = plugin.validate_config({})
        assert len(errors) == 2

    def test_normalize_line_code_known(self, plugin):
        assert plugin._normalize_line_code("JUDAH") == "N"
        assert plugin._normalize_line_code("N-JUDAH") == "N"
        assert plugin._normalize_line_code("CHURCH") == "J"
        assert plugin._normalize_line_code("TARAVAL") == "L"
        assert plugin._normalize_line_code("OCEAN VIEW") == "M"
        assert plugin._normalize_line_code("THIRD") == "T"
        assert plugin._normalize_line_code("SHUTTLE") == "S"
        assert plugin._normalize_line_code("MARKET") == "F"

    def test_normalize_line_code_single_letter(self, plugin):
        assert plugin._normalize_line_code("N") == "N"
        assert plugin._normalize_line_code("J") == "J"

    def test_normalize_line_code_dash(self, plugin):
        assert plugin._normalize_line_code("KT-OTHER") == "KT"

    def test_normalize_line_code_unknown(self, plugin):
        assert plugin._normalize_line_code("XY") == "XY"

    def test_get_display_line_name(self, plugin):
        assert plugin._get_display_line_name("N") == "N-JUDAH"
        assert plugin._get_display_line_name("Z") == "Z"

    def test_calculate_minutes_until_future(self, plugin):
        ts = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        assert 9 <= plugin._calculate_minutes_until(ts) <= 11

    def test_calculate_minutes_until_past(self, plugin):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        assert plugin._calculate_minutes_until(ts) == 0

    def test_calculate_minutes_until_z_suffix(self, plugin):
        future = datetime.now(timezone.utc) + timedelta(minutes=15)
        ts = future.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert 14 <= plugin._calculate_minutes_until(ts) <= 16

    def test_calculate_minutes_until_invalid(self, plugin):
        assert plugin._calculate_minutes_until("bad") is None

    def test_parse_stop_data_empty(self, plugin):
        assert plugin._parse_stop_data([], "123") is None

    def test_parse_stop_data_basic(self, plugin):
        now = datetime.now(timezone.utc)
        visits = [
            {
                "MonitoredVehicleJourney": {
                    "PublishedLineName": "N",
                    "Occupancy": "MANY_SEATS",
                    "MonitoredCall": {
                        "StopPointName": "Church St & Duboce",
                        "ExpectedArrivalTime": (now + timedelta(minutes=5)).isoformat(),
                    }
                }
            },
            {
                "MonitoredVehicleJourney": {
                    "PublishedLineName": "N",
                    "Occupancy": "FEW_SEATS",
                    "MonitoredCall": {
                        "StopPointName": "Church St & Duboce",
                        "ExpectedArrivalTime": (now + timedelta(minutes=12)).isoformat(),
                    }
                }
            },
        ]
        result = plugin._parse_stop_data(visits, "15726")
        assert result is not None
        assert result["stop_code"] == "15726"
        assert "N" in result["lines"]
        assert result["lines"]["N"]["line"] == "N-JUDAH"
        assert result["all_lines"]["next_arrival"] is not None
        assert result["line"] == "N-JUDAH"

    def test_parse_stop_data_list_fields(self, plugin):
        now = datetime.now(timezone.utc)
        visits = [{
            "MonitoredVehicleJourney": {
                "PublishedLineName": ["N"],
                "Occupancy": None,
                "MonitoredCall": {
                    "StopPointName": ["Test Stop"],
                    "ExpectedArrivalTime": (now + timedelta(minutes=5)).isoformat(),
                }
            }
        }]
        result = plugin._parse_stop_data(visits, "15726")
        assert result is not None

    def test_parse_stop_data_delayed(self, plugin):
        now = datetime.now(timezone.utc)
        visits = [{
            "MonitoredVehicleJourney": {
                "PublishedLineName": "N",
                "Delay": "PT5M",
                "MonitoredCall": {
                    "StopPointName": "Test",
                    "ExpectedArrivalTime": (now + timedelta(minutes=5)).isoformat(),
                }
            }
        }]
        result = plugin._parse_stop_data(visits, "15726")
        assert result is not None
        assert result["is_delayed"] is True
        assert "{63}" in result["formatted"]

    def test_parse_stop_data_no_published_line(self, plugin):
        now = datetime.now(timezone.utc)
        visits = [{
            "MonitoredVehicleJourney": {
                "MonitoredCall": {
                    "StopPointName": "Test",
                    "ExpectedArrivalTime": (now + timedelta(minutes=5)).isoformat(),
                }
            }
        }]
        assert plugin._parse_stop_data(visits, "15726") is None

    def test_parse_stop_data_full_occupancy(self, plugin):
        now = datetime.now(timezone.utc)
        visits = [{
            "MonitoredVehicleJourney": {
                "PublishedLineName": "N",
                "Occupancy": "FULL",
                "MonitoredCall": {
                    "StopPointName": "Test",
                    "ExpectedArrivalTime": (now + timedelta(minutes=5)).isoformat(),
                }
            }
        }]
        result = plugin._parse_stop_data(visits, "15726")
        assert result is not None

    def test_fetch_data_no_stops(self, plugin):
        plugin._config = {}
        result = plugin.fetch_data()
        assert not result.available

    def test_fetch_data_no_cache(self, plugin):
        plugin._config = {"api_key": "k", "stop_codes": ["1"]}
        with patch.object(plugin, '_get_transit_cache', return_value=None):
            result = plugin.fetch_data()
            assert not result.available

    def test_fetch_data_cache_not_ready(self, plugin):
        plugin._config = {"api_key": "k", "stop_codes": ["1"]}
        mock_cache = Mock()
        mock_cache.is_ready.return_value = False
        with patch.object(plugin, '_get_transit_cache', return_value=mock_cache):
            result = plugin.fetch_data()
            assert not result.available

    def test_fetch_data_no_arrivals(self, plugin):
        plugin._config = {"api_key": "k", "stop_codes": ["1"]}
        mock_cache = Mock()
        mock_cache.is_ready.return_value = True
        mock_cache.get_stops_data.return_value = {"1": []}
        with patch.object(plugin, '_get_transit_cache', return_value=mock_cache):
            result = plugin.fetch_data()
            assert result.available
            assert result.data["formatted"] == "NO ARRIVALS"

    def test_fetch_data_success(self, plugin):
        plugin._config = {"api_key": "k", "stop_codes": ["15726"]}
        now = datetime.now(timezone.utc)
        visits = [{
            "MonitoredVehicleJourney": {
                "PublishedLineName": "N",
                "Occupancy": "MANY_SEATS",
                "MonitoredCall": {
                    "StopPointName": "Test Stop",
                    "ExpectedArrivalTime": (now + timedelta(minutes=5)).isoformat(),
                }
            }
        }]
        mock_cache = Mock()
        mock_cache.is_ready.return_value = True
        mock_cache.get_stops_data.return_value = {"15726": visits}
        with patch.object(plugin, '_get_transit_cache', return_value=mock_cache):
            result = plugin.fetch_data()
            assert result.available
            assert result.data["stop_count"] == 1
            assert result.data["stop_name"] == "Test Stop"

    def test_fetch_data_exception(self, plugin):
        plugin._config = {"api_key": "k", "stop_codes": ["1"]}
        mock_cache = Mock()
        mock_cache.is_ready.return_value = True
        mock_cache.get_stops_data.side_effect = RuntimeError("fail")
        with patch.object(plugin, '_get_transit_cache', return_value=mock_cache):
            result = plugin.fetch_data()
            assert not result.available

    def test_cleanup(self, plugin):
        plugin._cache = {"a": 1}
        plugin._transit_cache = "something"
        plugin.cleanup()
        assert plugin._cache is None
        assert plugin._transit_cache is None

