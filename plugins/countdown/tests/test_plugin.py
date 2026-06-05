"""Tests for the countdown plugin."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from plugins.countdown import CountdownPlugin


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
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = datetime(2025, 5, 24, 20, 50, 0, tzinfo=tz)
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
        tz = ZoneInfo("America/Los_Angeles")
        # 21 days, 3 hours, 10 minutes before target
        mock_now = datetime(2025, 5, 24, 20, 50, 0, tzinfo=tz)
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
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = datetime(2025, 7, 1, 0, 0, 0, tzinfo=tz)
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
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = datetime(2025, 5, 24, 20, 50, 0, tzinfo=tz)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        data = result.data

        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        simple = manifest["variables"]["simple"]
        var_names = list(simple.keys()) if isinstance(simple, dict) else list(simple)
        for var in var_names:
            assert var in data, f"Variable '{var}' declared in manifest but not in data"

    @patch("plugins.countdown.datetime")
    def test_fetch_data_formatted_lines(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data returns formatted lines for the board."""
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = datetime(2025, 5, 24, 20, 50, 0, tzinfo=tz)
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
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = datetime(2025, 5, 24, 20, 50, 0, tzinfo=tz)
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
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = datetime(2025, 7, 1, 0, 0, 0, tzinfo=tz)
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
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = datetime(2025, 5, 24, 20, 50, 0, tzinfo=tz)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.data["formatted"] == "21D 3H 10M"

    @patch("plugins.countdown.datetime")
    def test_fetch_data_default_event_name(self, mock_datetime, sample_manifest):
        """Test default event name when not configured."""
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = datetime(2025, 5, 24, 20, 50, 0, tzinfo=tz)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        plugin = CountdownPlugin(sample_manifest)
        plugin.config = {
            "target_datetime": "2025-06-15T00:00:00",
            "timezone": "America/Los_Angeles",
        }
        result = plugin.fetch_data()

        assert result.data["event_name"] == "Event"


class TestCountdownManifestMetadata:
    """Tests for the rich metadata format in the countdown manifest."""

    def test_manifest_uses_dict_simple_format(self):
        """Manifest uses the dict format for simple variables with metadata."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        simple = manifest["variables"]["simple"]
        assert isinstance(simple, dict), "simple should use the rich dict format"

    def test_all_variables_have_descriptions(self):
        """Every variable in the manifest has a description."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        simple = manifest["variables"]["simple"]
        for var_name, meta in simple.items():
            assert meta.get("description"), f"Variable '{var_name}' missing description"

    def test_all_variables_have_valid_groups(self):
        """Every variable references a group that is defined."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        groups = set(manifest["variables"].get("groups", {}).keys())
        simple = manifest["variables"]["simple"]
        for var_name, meta in simple.items():
            group = meta.get("group", "")
            if group:
                assert group in groups, f"Variable '{var_name}' references undefined group '{group}'"

    def test_groups_are_defined(self):
        """Manifest defines variable groups."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        groups = manifest["variables"].get("groups", {})
        assert len(groups) > 0, "Manifest should define at least one group"
        for group_id, group_def in groups.items():
            assert "label" in group_def, f"Group '{group_id}' missing label"
