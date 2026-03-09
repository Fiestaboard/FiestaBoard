"""Unit tests for Spacecraft Launches plugin."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from plugins.spacecraft_launches import SpacecraftLaunchesPlugin


@pytest.fixture
def plugin(sample_manifest):
    """Create plugin instance for testing."""
    return SpacecraftLaunchesPlugin(sample_manifest)


class TestPluginInitialization:
    """Test plugin initialization."""

    def test_plugin_id(self, plugin):
        """Test plugin ID."""
        assert plugin.plugin_id == "spacecraft_launches"

    def test_plugin_initialization(self, plugin):
        """Test plugin initializes correctly."""
        assert plugin._cache is None


class TestConfigurationValidation:
    """Test configuration validation."""

    def test_validate_config_valid(self, plugin, sample_config):
        """Test validation with valid configuration."""
        errors = plugin.validate_config(sample_config)
        assert errors == []

    def test_validate_config_defaults(self, plugin):
        """Test validation with empty config uses defaults."""
        errors = plugin.validate_config({})
        assert errors == []

    def test_validate_config_invalid_max_launches_too_high(self, plugin):
        """Test validation fails with max_launches > 10."""
        config = {"max_launches": 11}
        errors = plugin.validate_config(config)
        assert any("Max launches" in e for e in errors)

    def test_validate_config_invalid_max_launches_too_low(self, plugin):
        """Test validation fails with max_launches < 1."""
        config = {"max_launches": 0}
        errors = plugin.validate_config(config)
        assert any("Max launches" in e for e in errors)

    def test_validate_refresh_too_low(self, plugin):
        """Test base validation fails with refresh < 240 (manifest minimum)."""
        config = {"refresh_seconds": 100}
        errors = plugin._validate_refresh_seconds(config)
        assert any("at least 240 seconds" in e for e in errors)

    def test_validate_config_invalid_max_launches_type(self, plugin):
        """Test validation fails with non-integer max_launches."""
        config = {"max_launches": "four"}
        errors = plugin.validate_config(config)
        assert any("Max launches" in e for e in errors)

    def test_validate_refresh_non_numeric(self, plugin):
        """Test base validation fails with non-numeric refresh_seconds."""
        config = {"refresh_seconds": "fast"}
        errors = plugin._validate_refresh_seconds(config)
        assert any("must be a number" in e for e in errors)


class TestCountdown:
    """Test countdown computation."""

    def test_countdown_future_launch(self, plugin):
        """Test countdown for a future launch."""
        future = datetime.now(timezone.utc) + timedelta(days=2, hours=5, minutes=30, seconds=15)
        net_str = future.isoformat()
        countdown = plugin._compute_countdown(net_str)
        assert countdown.startswith("2d")

    def test_countdown_today_launch(self, plugin):
        """Test countdown for a launch today (no days)."""
        future = datetime.now(timezone.utc) + timedelta(hours=3, minutes=15, seconds=45)
        net_str = future.isoformat()
        countdown = plugin._compute_countdown(net_str)
        assert "d" not in countdown
        assert countdown.startswith("03:")

    def test_countdown_past_launch(self, plugin):
        """Test countdown for a past launch."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        net_str = past.isoformat()
        countdown = plugin._compute_countdown(net_str)
        assert countdown == "LAUNCHED"

    def test_countdown_invalid_date(self, plugin):
        """Test countdown with invalid date string."""
        countdown = plugin._compute_countdown("not-a-date")
        assert countdown == "TBD"

    def test_countdown_empty_string(self, plugin):
        """Test countdown with empty string."""
        countdown = plugin._compute_countdown("")
        assert countdown == "TBD"

    def test_countdown_z_suffix(self, plugin):
        """Test countdown handles Z-terminated dates."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        net_str = future.strftime("%Y-%m-%dT%H:%M:%SZ")
        countdown = plugin._compute_countdown(net_str)
        assert countdown != "TBD"


class TestParseLaunch:
    """Test launch parsing."""

    def test_parse_launch_valid(self, plugin, mock_launches_response):
        """Test parsing a valid launch."""
        launch = mock_launches_response["results"][0]
        parsed = plugin._parse_launch(launch)

        assert parsed is not None
        assert "Crew-12" in parsed["mission"]
        assert parsed["status"] == "Go for Launch"
        assert parsed["status_abbrev"] == "Go"
        assert parsed["provider"] == "SpaceX"
        assert parsed["rocket"] == "Falcon 9"
        assert parsed["net_date"] == "03/15"
        assert parsed["net_time"] == "14:30"
        assert parsed["pad"] == "Space Launch Complex"[:20]

    def test_parse_launch_no_mission(self, plugin, mock_launch_no_mission):
        """Test parsing a launch with no mission data."""
        launch = mock_launch_no_mission["results"][0]
        parsed = plugin._parse_launch(launch)

        assert parsed is not None
        assert parsed["mission"] == "Mystery Payload"
        assert parsed["rocket"] == "Unknown Vehicle"

    def test_parse_launch_null_fields(self, plugin):
        """Test parsing a launch with null optional fields."""
        launch = {
            "name": "Test Launch",
            "status": None,
            "net": "",
            "pad": None,
            "launch_service_provider": None,
            "rocket": None,
            "mission": None,
        }
        parsed = plugin._parse_launch(launch)
        assert parsed is not None
        assert parsed["status"] == "Unknown"
        assert parsed["provider"] == "Unknown"

    def test_parse_launch_all_fields_present(self, plugin, mock_launches_response):
        """Test that all expected fields are present in parsed data."""
        launch = mock_launches_response["results"][0]
        parsed = plugin._parse_launch(launch)

        expected_fields = [
            "name", "status", "status_abbrev", "net", "net_date",
            "net_time", "countdown", "pad", "pad_location", "provider",
            "rocket", "mission", "formatted"
        ]
        for field in expected_fields:
            assert field in parsed, f"Missing field: {field}"


class TestFormatting:
    """Test display formatting."""

    def test_format_launch_line(self, plugin):
        """Test launch line formatting."""
        formatted = plugin._format_launch_line("03/15", "14:30", "CREW-12", "SLC-40")
        assert len(formatted) <= 22
        assert "03/15" in formatted
        assert "14:30" in formatted
        assert "CREW-12" in formatted

    def test_format_launch_line_long_mission(self, plugin):
        """Test formatting truncates long mission names."""
        formatted = plugin._format_launch_line("03/15", "14:30", "VERY LONG MISSION NAME HERE", "SLC-40")
        assert len(formatted) <= 22

    def test_format_launch_line_no_date(self, plugin):
        """Test formatting with no date/time."""
        formatted = plugin._format_launch_line("", "", "CREW-12", "SLC-40")
        assert len(formatted) <= 22
        assert "CREW-12" in formatted


class TestFetchData:
    """Test data fetching."""

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_success(self, mock_get, plugin, sample_config, mock_launches_response):
        """Test successful data fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_launches_response
        mock_get.return_value = mock_response

        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data is not None
        assert result.data["launch_count"] == 3
        assert len(result.data["launches"]) == 3
        assert result.data["name"] is not None

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_empty_results(self, mock_get, plugin, sample_config, mock_empty_response):
        """Test fetch with empty results."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_empty_response
        mock_get.return_value = mock_response

        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["launch_count"] == 0
        assert result.data["launches"] == []

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_rate_limit(self, mock_get, plugin, sample_config):
        """Test rate limit handling without cache."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert "rate limit" in result.error.lower()

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_rate_limit_with_cache(self, mock_get, plugin, sample_config):
        """Test rate limit returns cached data."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        plugin.config = sample_config
        plugin._cache = {
            "launches": [{"name": "Cached Launch"}],
            "launch_count": 1,
        }

        result = plugin.fetch_data()
        assert result.available is True

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_api_error(self, mock_get, plugin, sample_config):
        """Test API error handling."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert "500" in result.error

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_api_error_with_cache(self, mock_get, plugin, sample_config):
        """Test API error returns cached data."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        plugin.config = sample_config
        plugin._cache = {
            "launches": [{"name": "Cached Launch"}],
            "launch_count": 1,
        }

        result = plugin.fetch_data()
        assert result.available is True

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_network_error(self, mock_get, plugin, sample_config):
        """Test network error handling."""
        mock_get.side_effect = Exception("Connection refused")

        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_network_error_with_cache(self, mock_get, plugin, sample_config):
        """Test network error returns cached data."""
        mock_get.side_effect = Exception("Connection refused")

        plugin.config = sample_config
        plugin._cache = {
            "launches": [{"name": "Cached Launch"}],
            "launch_count": 1,
        }

        result = plugin.fetch_data()
        assert result.available is True

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_uses_cache(self, mock_get, plugin, sample_config):
        """Test that fresh cache is used instead of API call."""
        plugin.config = sample_config
        plugin._cache = {
            "launches": [{"name": "Cached Launch"}],
            "launch_count": 1,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        result = plugin.fetch_data()
        assert result.available is True
        mock_get.assert_not_called()

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_respects_max_launches(self, mock_get, plugin, mock_launches_response):
        """Test max_launches limits results."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_launches_response
        mock_get.return_value = mock_response

        plugin.config = {"max_launches": 2, "refresh_seconds": 300}
        result = plugin.fetch_data()

        assert result.available is True
        assert len(result.data["launches"]) == 2

    @patch("plugins.spacecraft_launches.requests.get")
    def test_fetch_data_primary_launch_fields(self, mock_get, plugin, sample_config, mock_launches_response):
        """Test primary launch fields are set from first launch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_launches_response
        mock_get.return_value = mock_response

        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.data["provider"] == "SpaceX"
        assert result.data["rocket"] == "Falcon 9"
        assert result.data["status"] == "Go for Launch"


class TestFormattedDisplay:
    """Test formatted display output."""

    @patch("plugins.spacecraft_launches.requests.get")
    def test_get_formatted_display(self, mock_get, plugin, sample_config, mock_launches_response):
        """Test formatted display output."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_launches_response
        mock_get.return_value = mock_response

        plugin.config = sample_config
        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6
        assert "EARTH DEPARTURES" in lines[0]

    def test_get_formatted_display_no_data(self, plugin, sample_config):
        """Test formatted display with no data returns None."""
        plugin.config = sample_config
        # Force fetch to fail by not mocking
        with patch("plugins.spacecraft_launches.requests.get") as mock_get:
            mock_get.side_effect = Exception("No connection")
            lines = plugin.get_formatted_display()
            assert lines is None


class TestCleanup:
    """Test plugin cleanup."""

    def test_cleanup(self, plugin):
        """Test cleanup clears cache."""
        plugin._cache = {"some": "data"}
        plugin.cleanup()
        assert plugin._cache is None


class TestVariablesMatchManifest:
    """Test that returned data matches manifest variables."""

    @patch("plugins.spacecraft_launches.requests.get")
    def test_simple_variables_present(self, mock_get, plugin, sample_config, sample_manifest, mock_launches_response):
        """Test all simple variables from manifest are in fetch_data result."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_launches_response
        mock_get.return_value = mock_response

        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        declared_vars = sample_manifest["variables"]["simple"]
        for var in declared_vars:
            assert var in result.data, f"Variable '{var}' declared in manifest but not in data"

    @patch("plugins.spacecraft_launches.requests.get")
    def test_array_item_fields_present(self, mock_get, plugin, sample_config, sample_manifest, mock_launches_response):
        """Test all array item fields from manifest are in launch data."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_launches_response
        mock_get.return_value = mock_response

        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        assert len(result.data["launches"]) > 0

        declared_fields = sample_manifest["variables"]["arrays"]["launches"]["item_fields"]
        first_launch = result.data["launches"][0]
        for field in declared_fields:
            assert field in first_launch, f"Array field '{field}' declared in manifest but not in launch data"
