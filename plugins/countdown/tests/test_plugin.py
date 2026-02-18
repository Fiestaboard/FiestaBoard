"""Tests for the countdown plugin."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import json
from pathlib import Path
import pytz

from plugins.countdown import CountdownPlugin
from src.plugins.base import PluginResult


class TestCountdownPlugin:
    """Test suite for CountdownPlugin."""

    def test_plugin_id(self, sample_manifest):
        """Test plugin ID matches directory name and manifest."""
        plugin = CountdownPlugin(sample_manifest)
        assert plugin.plugin_id == "countdown"

    def test_validate_config_valid(self, sample_manifest):
        """Test config validation with valid config."""
        plugin = CountdownPlugin(sample_manifest)
        config = {
            "event_name": "Test Event",
            "target_datetime": "2025-06-15T00:00:00",
            "timezone": "America/New_York",
        }
        errors = plugin.validate_config(config)
        assert len(errors) == 0

    def test_validate_config_invalid_timezone(self, sample_manifest):
        """Test config validation detects invalid timezone."""
        plugin = CountdownPlugin(sample_manifest)
        config = {
            "target_datetime": "2025-06-15T00:00:00",
            "timezone": "Invalid/Timezone",
        }
        errors = plugin.validate_config(config)
        assert len(errors) > 0
        assert any("timezone" in e.lower() for e in errors)

    def test_validate_config_missing_target(self, sample_manifest):
        """Test config validation detects missing target datetime."""
        plugin = CountdownPlugin(sample_manifest)
        config = {"event_name": "Test"}
        errors = plugin.validate_config(config)
        assert len(errors) > 0
        assert any("target" in e.lower() or "required" in e.lower() for e in errors)

    def test_validate_config_invalid_datetime(self, sample_manifest):
        """Test config validation detects invalid datetime format."""
        plugin = CountdownPlugin(sample_manifest)
        config = {"target_datetime": "not-a-date"}
        errors = plugin.validate_config(config)
        assert len(errors) > 0
        assert any("invalid" in e.lower() for e in errors)

    def test_validate_config_default_timezone(self, sample_manifest):
        """Test config validation with default timezone."""
        plugin = CountdownPlugin(sample_manifest)
        config = {"target_datetime": "2025-06-15T00:00:00"}
        errors = plugin.validate_config(config)
        assert len(errors) == 0

    @patch("plugins.countdown.datetime")
    def test_fetch_data_future_event(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data with a future target date."""
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(datetime(2025, 5, 24, 20, 50, 0))
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data is not None

        data = result.data
        assert data["event_name"] == "Last Day of School"
        assert data["is_expired"] == "false"
        assert int(data["days"]) >= 0
        assert int(data["hours"]) >= 0
        assert int(data["minutes"]) >= 0
        assert int(data["seconds"]) >= 0
        assert int(data["total_seconds"]) > 0

    @patch("plugins.countdown.datetime")
    def test_fetch_data_exact_values(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data returns correct countdown values."""
        tz = pytz.timezone("America/Los_Angeles")
        # 21 days, 3 hours, 10 minutes before target
        mock_now = tz.localize(datetime(2025, 5, 24, 20, 50, 0))
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        data = result.data
        assert data["days"] == "21"
        assert data["hours"] == "3"
        assert data["minutes"] == "10"
        assert data["seconds"] == "0"

    @patch("plugins.countdown.datetime")
    def test_fetch_data_expired_event(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data when the event has already passed."""
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(datetime(2025, 7, 1, 0, 0, 0))
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        data = result.data
        assert data["is_expired"] == "true"
        assert data["days"] == "0"
        assert data["hours"] == "0"
        assert data["minutes"] == "0"
        assert data["seconds"] == "0"
        assert data["total_seconds"] == "0"

    def test_fetch_data_missing_target(self, sample_manifest):
        """Test fetch_data handles missing target datetime."""
        plugin = CountdownPlugin(sample_manifest)
        plugin.config = {"enabled": True}
        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None
        assert "not configured" in result.error.lower()

    def test_fetch_data_invalid_target(self, sample_manifest):
        """Test fetch_data handles invalid target datetime."""
        plugin = CountdownPlugin(sample_manifest)
        plugin.config = {"target_datetime": "not-a-date"}
        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    def test_fetch_data_invalid_timezone(self, sample_manifest):
        """Test fetch_data handles invalid timezone gracefully."""
        plugin = CountdownPlugin(sample_manifest)
        plugin.config = {
            "target_datetime": "2025-06-15T00:00:00",
            "timezone": "Invalid/Timezone",
        }
        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    @patch("plugins.countdown.datetime")
    def test_fetch_data_all_variables(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data returns all expected variables from manifest."""
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(datetime(2025, 5, 24, 20, 50, 0))
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        data = result.data

        # All variables declared in manifest should be present
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        for var in manifest["variables"]["simple"]:
            assert var in data, f"Variable '{var}' declared in manifest but not in data"

    @patch("plugins.countdown.datetime")
    def test_fetch_data_formatted_lines(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data returns formatted lines for the board."""
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(datetime(2025, 5, 24, 20, 50, 0))
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.formatted_lines is not None
        assert len(result.formatted_lines) == 6

    @patch("plugins.countdown.datetime")
    def test_get_formatted_display(self, mock_datetime, sample_manifest, sample_config):
        """Test get_formatted_display returns 6 lines."""
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(datetime(2025, 5, 24, 20, 50, 0))
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = sample_config
        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6
        assert "COUNTDOWN" in lines[0].upper()
        assert "DAYS" in lines[3].upper()
        assert "HOURS" in lines[4].upper()
        assert "MINUTES" in lines[5].upper()

    @patch("plugins.countdown.datetime")
    def test_get_formatted_display_expired(self, mock_datetime, sample_manifest, sample_config):
        """Test formatted display when event has passed."""
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(datetime(2025, 7, 1, 0, 0, 0))
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = sample_config
        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6
        assert any("PASSED" in line.upper() for line in lines)

    def test_get_formatted_display_fetch_fails(self, sample_manifest):
        """Test formatted display when fetch_data fails."""
        plugin = CountdownPlugin(sample_manifest)
        plugin.config = {"enabled": True}
        lines = plugin.get_formatted_display()

        assert lines is None

    @patch("plugins.countdown.datetime")
    def test_fetch_data_formatted_string(self, mock_datetime, sample_manifest, sample_config):
        """Test the formatted countdown string."""
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(datetime(2025, 5, 24, 20, 50, 0))
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.data["formatted"] == "21D 3H 10M"

    @patch("plugins.countdown.datetime")
    def test_fetch_data_default_event_name(self, mock_datetime, sample_manifest):
        """Test default event name when not configured."""
        tz = pytz.timezone("America/Los_Angeles")
        mock_now = tz.localize(datetime(2025, 5, 24, 20, 50, 0))
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = {
            "target_datetime": "2025-06-15T00:00:00",
            "timezone": "America/Los_Angeles",
        }
        result = plugin.fetch_data()

        assert result.data["event_name"] == "Event"
