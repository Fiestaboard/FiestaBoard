"""Tests for the weather plugin."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import requests

from plugins.weather import WeatherPlugin
from src.plugins.base import PluginResult


class TestWeatherPlugin:
    """Test suite for WeatherPlugin."""

    def test_plugin_id(self, sample_manifest):
        """Test plugin ID matches directory name and manifest."""
        plugin = WeatherPlugin(sample_manifest)
        assert plugin.plugin_id == "weather"

    # --- validate_config ---

    def test_validate_config_valid(self, sample_manifest):
        """Test config validation passes with all required fields."""
        plugin = WeatherPlugin(sample_manifest)
        config = {
            "api_key": "abc123",
            "provider": "weatherapi",
            "location": "New York",
        }
        errors = plugin.validate_config(config)
        assert len(errors) == 0

    def test_validate_config_missing_api_key(self, sample_manifest):
        """Test config validation detects missing API key."""
        plugin = WeatherPlugin(sample_manifest)
        config = {"provider": "weatherapi", "location": "New York"}
        errors = plugin.validate_config(config)
        assert len(errors) > 0
        assert any("api key" in e.lower() for e in errors)

    def test_validate_config_empty_api_key(self, sample_manifest):
        """Test config validation detects blank API key."""
        plugin = WeatherPlugin(sample_manifest)
        config = {"api_key": "   ", "provider": "weatherapi", "location": "New York"}
        errors = plugin.validate_config(config)
        assert len(errors) > 0

    def test_validate_config_invalid_provider(self, sample_manifest):
        """Test config validation detects unsupported provider."""
        plugin = WeatherPlugin(sample_manifest)
        config = {"api_key": "abc123", "provider": "badprovider", "location": "NY"}
        errors = plugin.validate_config(config)
        assert len(errors) > 0
        assert any("provider" in e.lower() for e in errors)

    def test_validate_config_missing_location(self, sample_manifest):
        """Test config validation detects missing location."""
        plugin = WeatherPlugin(sample_manifest)
        config = {"api_key": "abc123", "provider": "weatherapi"}
        errors = plugin.validate_config(config)
        assert len(errors) > 0
        assert any("location" in e.lower() for e in errors)

    def test_validate_config_empty_location(self, sample_manifest):
        """Test config validation detects blank location."""
        plugin = WeatherPlugin(sample_manifest)
        config = {"api_key": "abc123", "provider": "weatherapi", "location": "  "}
        errors = plugin.validate_config(config)
        assert len(errors) > 0

    def test_validate_config_openweathermap_valid(self, sample_manifest):
        """Test config validation with openweathermap provider."""
        plugin = WeatherPlugin(sample_manifest)
        config = {
            "api_key": "abc123",
            "provider": "openweathermap",
            "location": "London",
        }
        errors = plugin.validate_config(config)
        assert len(errors) == 0

    def test_validate_config_default_provider(self, sample_manifest):
        """Test validate_config with no provider defaults to valid."""
        plugin = WeatherPlugin(sample_manifest)
        # provider defaults to "weatherapi" in validate_config
        config = {"api_key": "abc123", "location": "Tokyo"}
        errors = plugin.validate_config(config)
        assert len(errors) == 0

    # --- fetch_data: missing config ---

    def test_fetch_data_missing_api_key(self, sample_manifest):
        """Test fetch_data returns unavailable when API key not set."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = {"location": "SF"}
        result = plugin.fetch_data()
        assert result.available is False
        assert result.error is not None

    def test_fetch_data_missing_location(self, sample_manifest):
        """Test fetch_data returns unavailable when location not set."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = {"api_key": "abc123"}
        result = plugin.fetch_data()
        assert result.available is False
        assert result.error is not None

    # --- fetch_data: WeatherAPI ---

    def test_fetch_data_weatherapi_success(
        self, sample_manifest, sample_config, sample_weatherapi_response
    ):
        """Test fetch_data returns correct data from WeatherAPI.com."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = sample_config

        mock_resp = MagicMock()
        mock_resp.json.return_value = sample_weatherapi_response
        mock_resp.raise_for_status = MagicMock()

        with patch("plugins.weather.requests.get", return_value=mock_resp):
            result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data is not None

        data = result.data
        assert data["temperature"] == "72"
        assert data["feels_like"] == "68"
        assert data["condition"] == "Partly Cloudy"
        assert data["humidity"] == "65"
        assert data["wind_speed"] == "12"
        assert data["location"] == "San Francisco"
        assert data["temp_f"] == "72F"
        assert "Partly Cloudy" in data["summary"]
        assert "72" in data["summary"]

    def test_fetch_data_weatherapi_all_manifest_variables(
        self, sample_manifest, sample_config, sample_weatherapi_response
    ):
        """Test fetch_data returns every variable declared in the manifest."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = sample_config

        mock_resp = MagicMock()
        mock_resp.json.return_value = sample_weatherapi_response
        mock_resp.raise_for_status = MagicMock()

        with patch("plugins.weather.requests.get", return_value=mock_resp):
            result = plugin.fetch_data()

        assert result.available is True
        data = result.data

        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        simple = manifest["variables"]["simple"]
        for var_name in simple:
            assert var_name in data, f"Variable '{var_name}' declared in manifest but missing from data"

    def test_fetch_data_weatherapi_formatted_lines(
        self, sample_manifest, sample_config, sample_weatherapi_response
    ):
        """Test fetch_data returns 6 formatted display lines."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = sample_config

        mock_resp = MagicMock()
        mock_resp.json.return_value = sample_weatherapi_response
        mock_resp.raise_for_status = MagicMock()

        with patch("plugins.weather.requests.get", return_value=mock_resp):
            result = plugin.fetch_data()

        assert result.formatted_lines is not None
        assert isinstance(result.formatted_lines, list)
        assert len(result.formatted_lines) == 6

    def test_fetch_data_weatherapi_http_error(self, sample_manifest, sample_config):
        """Test fetch_data handles WeatherAPI HTTP errors gracefully."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = sample_config

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("401")

        with patch("plugins.weather.requests.get", return_value=mock_resp):
            result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    def test_fetch_data_weatherapi_request_exception(self, sample_manifest, sample_config):
        """Test fetch_data handles network errors from WeatherAPI."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = sample_config

        with patch(
            "plugins.weather.requests.get",
            side_effect=requests.exceptions.ConnectionError("network error"),
        ):
            result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    def test_fetch_data_weatherapi_malformed_response(self, sample_manifest, sample_config):
        """Test fetch_data handles unexpected/malformed WeatherAPI response."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = sample_config

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"unexpected": "structure"}
        mock_resp.raise_for_status = MagicMock()

        with patch("plugins.weather.requests.get", return_value=mock_resp):
            result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    # --- fetch_data: OpenWeatherMap ---

    def test_fetch_data_openweathermap_success(
        self, sample_manifest, sample_openweathermap_response
    ):
        """Test fetch_data returns correct data from OpenWeatherMap."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = {
            "api_key": "test_key",
            "provider": "openweathermap",
            "location": "San Francisco",
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = sample_openweathermap_response
        mock_resp.raise_for_status = MagicMock()

        with patch("plugins.weather.requests.get", return_value=mock_resp):
            result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        data = result.data
        assert data["temperature"] == "72"
        assert data["feels_like"] == "68"
        assert data["condition"] == "Partly Cloudy"  # title-cased
        assert data["humidity"] == "65"
        assert data["wind_speed"] == "12"
        assert data["location"] == "San Francisco"

    def test_fetch_data_openweathermap_http_error(self, sample_manifest):
        """Test fetch_data handles OpenWeatherMap HTTP errors gracefully."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = {
            "api_key": "test_key",
            "provider": "openweathermap",
            "location": "London",
        }

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("401")

        with patch("plugins.weather.requests.get", return_value=mock_resp):
            result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    def test_fetch_data_openweathermap_request_exception(self, sample_manifest):
        """Test fetch_data handles network errors from OpenWeatherMap."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = {
            "api_key": "test_key",
            "provider": "openweathermap",
            "location": "London",
        }

        with patch(
            "plugins.weather.requests.get",
            side_effect=requests.exceptions.Timeout("timed out"),
        ):
            result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    def test_fetch_data_openweathermap_malformed_response(self, sample_manifest):
        """Test fetch_data handles malformed OpenWeatherMap response."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = {
            "api_key": "test_key",
            "provider": "openweathermap",
            "location": "London",
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()

        with patch("plugins.weather.requests.get", return_value=mock_resp):
            result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    # --- unknown provider ---

    def test_fetch_data_unknown_provider(self, sample_manifest):
        """Test fetch_data handles unknown provider."""
        plugin = WeatherPlugin(sample_manifest)
        plugin.config = {
            "api_key": "test_key",
            "provider": "unknownprovider",
            "location": "NYC",
        }
        result = plugin.fetch_data()
        assert result.available is False
        assert result.error is not None


class TestWeatherManifestMetadata:
    """Tests for the rich metadata format in the weather manifest."""

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
            assert "description" in meta and meta["description"], \
                f"Variable '{var_name}' missing description"

    def test_all_variables_reference_valid_groups(self):
        """Every variable references a group that is defined."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        groups = set(manifest["variables"].get("groups", {}).keys())
        simple = manifest["variables"]["simple"]
        for var_name, meta in simple.items():
            group = meta.get("group", "")
            if group:
                assert group in groups, \
                    f"Variable '{var_name}' references undefined group '{group}'"

    def test_groups_are_defined(self):
        """Manifest defines variable groups."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        groups = manifest["variables"].get("groups", {})
        assert len(groups) > 0, "Manifest should define at least one group"
        for group_id, group_def in groups.items():
            assert "label" in group_def, f"Group '{group_id}' missing label"

    def test_manifest_required_fields(self):
        """Manifest has required top-level fields."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        for field in ("id", "name", "version", "description"):
            assert field in manifest, f"Manifest missing required field '{field}'"

    def test_manifest_id_matches_plugin_id(self):
        """Manifest id matches the plugin directory name."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["id"] == "weather"
