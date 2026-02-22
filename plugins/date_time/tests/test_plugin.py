"""Tests for the date_time plugin."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import json
from pathlib import Path
import pytz

from plugins.date_time import DateTimePlugin
from src.plugins.base import PluginResult


class TestDateTimePlugin:
    """Test suite for DateTimePlugin."""
    
    def test_plugin_id(self, sample_manifest):
        """Test plugin ID matches directory name and manifest."""
        plugin = DateTimePlugin(sample_manifest)
        assert plugin.plugin_id == "date_time"
    
    def test_validate_config_valid_timezone(self, sample_manifest):
        """Test config validation with valid timezone."""
        plugin = DateTimePlugin(sample_manifest)
        config = {"timezone": "America/New_York", "enabled": True}
        errors = plugin.validate_config(config)
        assert len(errors) == 0
    
    def test_validate_config_invalid_timezone(self, sample_manifest):
        """Test config validation detects invalid timezone."""
        plugin = DateTimePlugin(sample_manifest)
        config = {"timezone": "Invalid/Timezone", "enabled": True}
        errors = plugin.validate_config(config)
        assert len(errors) > 0
        assert any("timezone" in e.lower() for e in errors)
    
    def test_validate_config_default_timezone(self, sample_manifest):
        """Test config validation with default timezone."""
        plugin = DateTimePlugin(sample_manifest)
        config = {"enabled": True}  # No timezone specified
        errors = plugin.validate_config(config)
        # Should use default and be valid
        assert len(errors) == 0
    
    @patch('plugins.date_time.datetime')
    def test_fetch_data_all_variables(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data returns all expected variables."""
        # Mock datetime to return a specific date/time
        mock_now = datetime(2025, 1, 15, 14, 30, 0)  # Wednesday, Jan 15, 2025, 2:30 PM
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now
        
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.error is None
        assert result.data is not None
        
        data = result.data
        
        # Existing variables
        assert "date" in data
        assert "time" in data
        assert "datetime" in data
        assert "day_of_week" in data
        assert "day" in data
        assert "month" in data
        assert "year" in data
        assert "hour" in data
        assert "minute" in data
        assert "timezone_abbr" in data
        
        # New variables
        assert "time_12h" in data
        assert "time_24h" in data
        assert "date_us" in data
        assert "date_us_short" in data
        assert "month_number" in data
        assert "month_number_padded" in data
        assert "month_abbr" in data
        assert "timezone" in data
    
    @patch('plugins.date_time.datetime')
    def test_fetch_data_time_formats(self, mock_datetime, sample_manifest, sample_config):
        """Test time format variables."""
        # Test at 2:30 PM (14:30)
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now
        
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.data["time_24h"] == "14:30"
        assert result.data["time"] == "14:30"  # Should match time_24h
        assert result.data["time_12h"] == "2:30 PM"  # Leading zero removed
    
    @patch('plugins.date_time.datetime')
    def test_fetch_data_time_formats_midnight(self, mock_datetime, sample_manifest, sample_config):
        """Test time formats at midnight (12:00 AM)."""
        mock_now = datetime(2025, 1, 15, 0, 0, 0)
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now
        
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.data["time_24h"] == "00:00"
        assert result.data["time_12h"] == "12:00 AM"
    
    @patch('plugins.date_time.datetime')
    def test_fetch_data_time_formats_noon(self, mock_datetime, sample_manifest, sample_config):
        """Test time formats at noon (12:00 PM)."""
        mock_now = datetime(2025, 1, 15, 12, 0, 0)
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now
        
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.data["time_24h"] == "12:00"
        assert result.data["time_12h"] == "12:00 PM"
    
    @patch('plugins.date_time.datetime')
    def test_fetch_data_date_formats(self, mock_datetime, sample_manifest, sample_config):
        """Test US date format variables."""
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now
        
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.data["date"] == "2025-01-15"
        assert result.data["date_us"] == "01/15/2025"
        assert result.data["date_us_short"] == "01/15/25"
    
    @patch('plugins.date_time.datetime')
    def test_fetch_data_month_formats(self, mock_datetime, sample_manifest, sample_config):
        """Test month format variables."""
        # Test January (month 1)
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now
        
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.data["month"] == "January"
        assert result.data["month_number"] == "1"
        assert result.data["month_number_padded"] == "01"
        assert result.data["month_abbr"] == "Jan"
        
        # Test December (month 12)
        mock_now = datetime(2025, 12, 25, 14, 30, 0)
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now
        
        result = plugin.fetch_data()
        assert result.data["month"] == "December"
        assert result.data["month_number"] == "12"
        assert result.data["month_number_padded"] == "12"
        assert result.data["month_abbr"] == "Dec"
    
    @patch('plugins.date_time.datetime')
    def test_fetch_data_timezone_info(self, mock_datetime, sample_manifest, sample_config):
        """Test timezone-related variables."""
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = pytz.timezone("America/New_York")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now
        
        config = sample_config.copy()
        config["timezone"] = "America/New_York"
        
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = config
        result = plugin.fetch_data()
        
        assert result.data["timezone"] == "America/New_York"
        assert "timezone_abbr" in result.data  # Should have abbreviation like "EST" or "EDT"
    
    @patch('plugins.date_time.datetime')
    def test_fetch_data_day_of_week(self, mock_datetime, sample_manifest, sample_config):
        """Test day of week variable."""
        # Wednesday
        mock_now = datetime(2025, 1, 15, 14, 30, 0)  # Jan 15, 2025 is a Wednesday
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now
        
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.data["day_of_week"] == "Wednesday"
        assert result.data["day"] == "15"
        assert result.data["year"] == "2025"
    
    def test_fetch_data_invalid_timezone(self, sample_manifest):
        """Test fetch_data handles invalid timezone gracefully."""
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = {"timezone": "Invalid/Timezone", "enabled": True}
        
        result = plugin.fetch_data()
        
        # Should fail but return gracefully
        assert result.available is False
        assert result.error is not None
    
    def test_fetch_data_default_timezone(self, sample_manifest):
        """Test fetch_data uses default timezone when not configured."""
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = {"enabled": True}  # No timezone in config
        
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.data is not None
        assert result.data["timezone"] == "America/Los_Angeles"  # Default
    
    @patch('plugins.date_time.datetime')
    def test_get_formatted_display(self, mock_datetime, sample_manifest, sample_config):
        """Test formatted display output."""
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now
        
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        lines = plugin.get_formatted_display()
        
        assert lines is not None
        assert len(lines) == 6  # Board has 6 lines
        assert "WEDNESDAY" in lines[1].upper()  # Day of week should be centered
        assert "2025-01-15" in lines[2]  # Date should be centered
        assert "14:30" in lines[3]  # Time should be centered
    
    @patch('plugins.date_time.datetime')
    def test_get_formatted_display_fetch_fails(self, mock_datetime, sample_manifest):
        """Test formatted display when fetch_data fails."""
        mock_datetime.now.side_effect = Exception("Test error")
        
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = {"enabled": True}
        lines = plugin.get_formatted_display()
        
        assert lines is None  # Should return None when fetch fails
