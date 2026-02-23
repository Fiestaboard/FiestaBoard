"""Tests for the stardate plugin."""

import pytest
from unittest.mock import patch
from datetime import datetime
import calendar
import pytz

from plugins.stardate import StardatePlugin
from src.plugins.base import PluginResult


class TestStardatePlugin:
    """Test suite for StardatePlugin."""

    def test_plugin_id(self, sample_manifest):
        """Test plugin ID matches directory name and manifest."""
        plugin = StardatePlugin(sample_manifest)
        assert plugin.plugin_id == "stardate"

    def test_validate_config_valid_timezone(self, sample_manifest):
        """Test config validation with valid timezone."""
        plugin = StardatePlugin(sample_manifest)
        errors = plugin.validate_config({"timezone": "America/New_York", "enabled": True})
        assert len(errors) == 0

    def test_validate_config_invalid_timezone(self, sample_manifest):
        """Test config validation detects invalid timezone."""
        plugin = StardatePlugin(sample_manifest)
        errors = plugin.validate_config({"timezone": "Invalid/Timezone", "enabled": True})
        assert len(errors) > 0
        assert any("timezone" in e.lower() for e in errors)

    def test_validate_config_default_timezone(self, sample_manifest):
        """Test config validation with default timezone."""
        plugin = StardatePlugin(sample_manifest)
        errors = plugin.validate_config({"enabled": True})
        assert len(errors) == 0

    @patch('plugins.stardate.datetime')
    def test_fetch_data_returns_stardate(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data returns the stardate variable."""
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now

        plugin = StardatePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data is not None
        assert "stardate" in result.data

    @patch('plugins.stardate.datetime')
    def test_fetch_data_stardate_value(self, mock_datetime, sample_manifest, sample_config):
        """Test stardate is calculated correctly (canonical TNG formula)."""
        # Jan 15, 2025: day_of_year=15, year=2025 (not a leap year)
        # Canonical TNG: (Year - 2323) × 1000 + day_fraction × 1000
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now

        plugin = StardatePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        stardate_val = float(result.data["stardate"])
        days_in_year = 366 if calendar.isleap(2025) else 365
        expected = (2025 - 2323) * 1000 + (15 / days_in_year * 1000)
        assert abs(stardate_val - expected) < 0.1

    @patch('plugins.stardate.datetime')
    def test_fetch_data_stardate_leap_year(self, mock_datetime, sample_manifest, sample_config):
        """Test stardate uses 366 days in a leap year."""
        # 2024 is a leap year; use day 60 (Feb 29)
        mock_now = datetime(2024, 2, 29, 0, 0, 0)
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now

        plugin = StardatePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        stardate_val = float(result.data["stardate"])
        expected = (2024 - 2323) * 1000 + (60 / 366 * 1000)
        assert abs(stardate_val - expected) < 0.1

    def test_fetch_data_invalid_timezone(self, sample_manifest):
        """Test fetch_data handles invalid timezone gracefully."""
        plugin = StardatePlugin(sample_manifest)
        plugin.config = {"timezone": "Invalid/Timezone", "enabled": True}

        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    def test_fetch_data_default_timezone(self, sample_manifest):
        """Test fetch_data uses default timezone when not configured."""
        plugin = StardatePlugin(sample_manifest)
        plugin.config = {"enabled": True}

        result = plugin.fetch_data()

        assert result.available is True
        assert result.data is not None
        assert "stardate" in result.data

    @patch('plugins.stardate.datetime')
    def test_get_formatted_display(self, mock_datetime, sample_manifest, sample_config):
        """Test formatted display output."""
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(mock_now)
        mock_datetime.now.return_value = mock_now

        plugin = StardatePlugin(sample_manifest)
        plugin.config = sample_config
        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6
        assert any("STARDATE" in line for line in lines)
        # For 2025-01-15, stardate should be negative (around -297959.x)
        # Check for the base value with flexible decimal
        stardate_line = next((line for line in lines if "-" in line and "STARDATE" not in line), None)
        assert stardate_line is not None
        assert "-297959" in stardate_line or "-297958" in stardate_line

    @patch('plugins.stardate.datetime')
    def test_get_formatted_display_fetch_fails(self, mock_datetime, sample_manifest):
        """Test formatted display returns None when fetch_data fails."""
        mock_datetime.now.side_effect = Exception("Test error")

        plugin = StardatePlugin(sample_manifest)
        plugin.config = {"enabled": True}
        lines = plugin.get_formatted_display()

        assert lines is None
