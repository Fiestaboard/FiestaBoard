"""Tests for the date_time plugin."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from plugins.date_time import DateTimePlugin, _time_to_english


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

    def test_validate_config_empty_string_timezone(self, sample_manifest):
        """Test that an empty string timezone is rejected (regression: partial search text)."""
        plugin = DateTimePlugin(sample_manifest)
        errors = plugin.validate_config({"timezone": ""})
        assert len(errors) > 0

    def test_validate_config_none_timezone(self, sample_manifest):
        """Test that a None timezone value is rejected gracefully."""
        plugin = DateTimePlugin(sample_manifest)
        errors = plugin.validate_config({"timezone": None})
        assert len(errors) > 0

    def test_validate_config_default_timezone(self, sample_manifest):
        """Test config validation with default timezone."""
        plugin = DateTimePlugin(sample_manifest)
        config = {"enabled": True}  # No timezone specified
        errors = plugin.validate_config(config)
        # Should use default and be valid
        assert len(errors) == 0

    @patch("plugins.date_time.datetime")
    def test_fetch_data_all_variables(self, mock_datetime, sample_manifest, sample_config):
        """Test fetch_data returns all expected variables."""
        # Mock datetime to return a specific date/time
        mock_now = datetime(2025, 1, 15, 14, 30, 0)  # Wednesday, Jan 15, 2025, 2:30 PM
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = mock_now.replace(tzinfo=tz)
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
        assert "day_of_week_abbr" in data
        assert "day_of_week_num" in data
        assert "day_of_year" in data
        assert "day" in data
        assert "month" in data
        assert "week_of_year" in data
        assert "quarter" in data
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

    @patch("plugins.date_time.datetime")
    def test_fetch_data_time_formats(self, mock_datetime, sample_manifest, sample_config):
        """Test time format variables."""
        # Test at 2:30 PM (14:30)
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = mock_now.replace(tzinfo=tz)
        mock_datetime.now.return_value = mock_now

        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.data["time_24h"] == "14:30"
        assert result.data["time"] == "14:30"  # Should match time_24h
        assert result.data["time_12h"] == "2:30 PM"  # Leading zero removed

    @patch("plugins.date_time.datetime")
    def test_fetch_data_time_formats_midnight(self, mock_datetime, sample_manifest, sample_config):
        """Test time formats at midnight (12:00 AM)."""
        mock_now = datetime(2025, 1, 15, 0, 0, 0)
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = mock_now.replace(tzinfo=tz)
        mock_datetime.now.return_value = mock_now

        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.data["time_24h"] == "00:00"
        assert result.data["time_12h"] == "12:00 AM"

    @patch("plugins.date_time.datetime")
    def test_fetch_data_time_formats_noon(self, mock_datetime, sample_manifest, sample_config):
        """Test time formats at noon (12:00 PM)."""
        mock_now = datetime(2025, 1, 15, 12, 0, 0)
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = mock_now.replace(tzinfo=tz)
        mock_datetime.now.return_value = mock_now

        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.data["time_24h"] == "12:00"
        assert result.data["time_12h"] == "12:00 PM"

    @patch("plugins.date_time.datetime")
    def test_fetch_data_date_formats(self, mock_datetime, sample_manifest, sample_config):
        """Test US date format variables."""
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = mock_now.replace(tzinfo=tz)
        mock_datetime.now.return_value = mock_now

        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.data["date"] == "2025-01-15"
        assert result.data["date_us"] == "01/15/2025"
        assert result.data["date_us_short"] == "01/15/25"

    @patch("plugins.date_time.datetime")
    def test_fetch_data_month_formats(self, mock_datetime, sample_manifest, sample_config):
        """Test month format variables."""
        # Test January (month 1)
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = mock_now.replace(tzinfo=tz)
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
        mock_now = mock_now.replace(tzinfo=tz)
        mock_datetime.now.return_value = mock_now

        result = plugin.fetch_data()
        assert result.data["month"] == "December"
        assert result.data["month_number"] == "12"
        assert result.data["month_number_padded"] == "12"
        assert result.data["month_abbr"] == "Dec"

    @patch("plugins.date_time.datetime")
    def test_fetch_data_timezone_info(self, mock_datetime, sample_manifest, sample_config):
        """Test timezone-related variables."""
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = ZoneInfo("America/New_York")
        mock_now = mock_now.replace(tzinfo=tz)
        mock_datetime.now.return_value = mock_now

        config = sample_config.copy()
        config["timezone"] = "America/New_York"

        plugin = DateTimePlugin(sample_manifest)
        plugin.config = config
        result = plugin.fetch_data()

        assert result.data["timezone"] == "America/New_York"
        assert "timezone_abbr" in result.data  # Should have abbreviation like "EST" or "EDT"

    @patch("plugins.date_time.datetime")
    def test_fetch_data_day_of_week(self, mock_datetime, sample_manifest, sample_config):
        """Test day of week variable."""
        # Wednesday
        mock_now = datetime(2025, 1, 15, 14, 30, 0)  # Jan 15, 2025 is a Wednesday
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = mock_now.replace(tzinfo=tz)
        mock_datetime.now.return_value = mock_now

        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.data["day_of_week"] == "Wednesday"
        assert result.data["day_of_week_abbr"] == "Wed"
        assert result.data["day_of_week_num"] == "3"
        assert result.data["day_of_year"] == "15"
        assert result.data["day"] == "15"
        assert result.data["week_of_year"] == "3"
        assert result.data["quarter"] == "1"
        assert result.data["year"] == "2025"

    @patch("plugins.date_time.datetime")
    def test_fetch_data_variables_match_manifest(self, mock_datetime, sample_manifest, sample_config):
        """Test that fetch_data() output keys match the manifest-declared variables."""
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = mock_now.replace(tzinfo=tz)
        mock_datetime.now.return_value = mock_now

        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        assert result.available is True

        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        simple = manifest["variables"]["simple"]
        var_names = list(simple.keys()) if isinstance(simple, dict) else list(simple)
        for var in var_names:
            assert var in result.data, f"Variable '{var}' declared in manifest but not in data"

    def test_fetch_data_invalid_timezone(self, sample_manifest):
        """Test fetch_data handles invalid timezone gracefully."""
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = {"timezone": "Invalid/Timezone", "enabled": True}

        result = plugin.fetch_data()

        # Should fail but return gracefully
        assert result.available is False
        assert result.error is not None

    def test_fetch_data_default_timezone(self, sample_manifest):
        """Test fetch_data falls back to LA when neither plugin nor general timezone is set."""
        with patch("src.config.Config") as mock_config:
            mock_config.GENERAL_TIMEZONE = ""
            plugin = DateTimePlugin(sample_manifest)
            plugin.config = {"enabled": True}  # No timezone in config
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data is not None
        assert result.data["timezone"] == "America/Los_Angeles"  # Final fallback

    def test_fetch_data_uses_general_timezone(self, sample_manifest):
        """Test fetch_data falls back to general/profile timezone when plugin timezone is not set."""
        with patch("src.config.Config") as mock_config:
            mock_config.GENERAL_TIMEZONE = "America/Denver"
            plugin = DateTimePlugin(sample_manifest)
            plugin.config = {"enabled": True}  # No plugin-specific timezone
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data is not None
        assert result.data["timezone"] == "America/Denver"

    @patch("plugins.date_time.datetime")
    def test_get_formatted_display(self, mock_datetime, sample_manifest, sample_config):
        """Test formatted display output."""
        mock_now = datetime(2025, 1, 15, 14, 30, 0)
        tz = ZoneInfo("America/Los_Angeles")
        mock_now = mock_now.replace(tzinfo=tz)
        mock_datetime.now.return_value = mock_now

        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6  # Board has 6 lines
        assert "WEDNESDAY" in lines[1].upper()  # Day of week should be centered
        assert "2025-01-15" in lines[2]  # Date should be centered
        assert "14:30" in lines[3]  # Time should be centered

    @patch("plugins.date_time.datetime")
    def test_get_formatted_display_fetch_fails(self, mock_datetime, sample_manifest):
        """Test formatted display when fetch_data fails."""
        mock_datetime.now.side_effect = Exception("Test error")

        plugin = DateTimePlugin(sample_manifest)
        plugin.config = {"enabled": True}
        lines = plugin.get_formatted_display()

        assert lines is None  # Should return None when fetch fails


class TestDateTimeManifestMetadata:
    """Tests for the rich metadata format in the date_time manifest."""

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

    def test_all_19_variables_present(self):
        """All 19 date_time variables are declared in the manifest."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        simple = manifest["variables"]["simple"]
        expected = [
            "time",
            "date",
            "datetime",
            "day",
            "day_of_week",
            "day_of_week_abbr",
            "day_of_week_num",
            "day_of_year",
            "week_of_year",
            "month",
            "quarter",
            "year",
            "hour",
            "minute",
            "timezone_abbr",
            "time_12h",
            "time_24h",
            "date_us",
            "date_us_short",
            "month_number",
            "month_number_padded",
            "month_abbr",
            "timezone",
            "time_english",
        ]
        for var in expected:
            assert var in simple, f"Expected variable '{var}' not in manifest"


class TestTimeToEnglish:
    """Unit tests for _time_to_english()."""

    def test_midnight(self):
        assert _time_to_english(0, 0) == "IT'S MIDNIGHT."

    def test_noon(self):
        assert _time_to_english(12, 0) == "IT'S NOON."

    def test_on_the_hour_morning(self):
        assert _time_to_english(9, 0) == "IT'S NINE O'CLOCK IN THE MORNING."

    def test_on_the_hour_afternoon(self):
        assert _time_to_english(13, 0) == "IT'S ONE O'CLOCK IN THE AFTERNOON."

    def test_on_the_hour_evening(self):
        assert _time_to_english(19, 0) == "IT'S SEVEN O'CLOCK IN THE EVENING."

    def test_on_the_hour_night(self):
        assert _time_to_english(22, 0) == "IT'S TEN O'CLOCK AT NIGHT."

    def test_quarter_past(self):
        assert _time_to_english(12, 15) == "IT'S A QUARTER PAST TWELVE IN THE AFTERNOON."

    def test_half_past(self):
        assert _time_to_english(8, 30) == "IT'S HALF PAST EIGHT IN THE MORNING."

    def test_quarter_to(self):
        assert _time_to_english(12, 45) == "IT'S A QUARTER TO ONE IN THE AFTERNOON."

    def test_exact_minutes_past(self):
        assert _time_to_english(14, 23) == "IT'S TWENTY-THREE PAST TWO IN THE AFTERNOON."

    def test_exact_minutes_to(self):
        assert _time_to_english(14, 47) == "IT'S THIRTEEN TO THREE IN THE AFTERNOON."

    def test_one_past(self):
        assert _time_to_english(10, 1) == "IT'S ONE PAST TEN IN THE MORNING."

    def test_one_to(self):
        assert _time_to_english(10, 59) == "IT'S ONE TO ELEVEN IN THE MORNING."

    def test_twenty_past(self):
        assert _time_to_english(6, 20) == "IT'S TWENTY PAST SIX IN THE MORNING."

    def test_period_boundaries(self):
        assert "IN THE MORNING" in _time_to_english(5, 0)
        assert "IN THE MORNING" in _time_to_english(11, 30)
        assert "IN THE AFTERNOON" in _time_to_english(12, 1)
        assert "IN THE AFTERNOON" in _time_to_english(17, 59)
        assert "IN THE EVENING" in _time_to_english(18, 0)
        assert "IN THE EVENING" in _time_to_english(20, 59)
        assert "AT NIGHT" in _time_to_english(21, 0)
        assert "AT NIGHT" in _time_to_english(23, 59)
        assert "AT NIGHT" in _time_to_english(0, 1)
        assert "AT NIGHT" in _time_to_english(4, 59)

    def test_twelve_oclock_night(self):
        # 12:30 AM — half past twelve at night
        assert _time_to_english(0, 30) == "IT'S HALF PAST TWELVE AT NIGHT."

    def test_time_english_in_fetch_data(self, sample_manifest, sample_config):
        """time_english is present in fetch_data output."""
        plugin = DateTimePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        assert result.available is True
        assert "time_english" in result.data
        assert result.data["time_english"].startswith("IT'S ")

    @pytest.fixture
    def sample_manifest(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            return json.load(f)

    @pytest.fixture
    def sample_config(self):
        return {"timezone": "America/Los_Angeles", "enabled": True}
