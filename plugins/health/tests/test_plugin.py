"""Tests for Allergy & Health plugin."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from plugins.health import (
    HealthPlugin,
    DEFAULT_LAT,
    DEFAULT_LON,
    AIR_QUALITY_API_URL,
    GRASS_THRESHOLDS,
    TREE_THRESHOLDS,
    WEED_THRESHOLDS,
    MAX_RISK_SCALE,
)


def _load_manifest():
    """Load the health plugin manifest."""
    import os
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "manifest.json"
    )
    with open(manifest_path) as f:
        return json.load(f)


@pytest.fixture
def manifest():
    """Health plugin manifest fixture."""
    return _load_manifest()


@pytest.fixture
def plugin(manifest):
    """Health plugin instance fixture."""
    p = HealthPlugin(manifest)
    p._config = {"latitude": DEFAULT_LAT, "longitude": DEFAULT_LON}
    p._enabled = True
    return p


def _make_api_response(
    grass=10,
    birch=20,
    alder=5,
    ragweed=8,
    us_aqi=42,
    european_aqi=30,
    pm25=8.5,
    pm10=15.0,
):
    """Build a mock Open-Meteo Air Quality API response."""
    return {
        "current": {
            "grass_pollen": grass,
            "birch_pollen": birch,
            "alder_pollen": alder,
            "ragweed_pollen": ragweed,
            "us_aqi": us_aqi,
            "european_aqi": european_aqi,
            "pm2_5": pm25,
            "pm10": pm10,
        }
    }


# ── Allergy Risk Calculation ─────────────────────────────────────────


class TestAllergyRisk:
    """Tests for allergy risk classification from pollen counts."""

    def test_all_zero_is_low(self):
        label, color = HealthPlugin.calculate_allergy_risk(0, 0, 0)
        assert label == "LOW"
        assert color == "GREEN"

    def test_trace_pollen_is_low(self):
        """Any non-zero value below moderate threshold is LOW."""
        label, _ = HealthPlugin.calculate_allergy_risk(5, 10, 3)
        assert label == "LOW"

    def test_grass_moderate(self):
        label, color = HealthPlugin.calculate_allergy_risk(
            GRASS_THRESHOLDS[0], 0, 0
        )
        assert label == "MODERATE"
        assert color == "YELLOW"

    def test_tree_high(self):
        label, color = HealthPlugin.calculate_allergy_risk(
            0, TREE_THRESHOLDS[1], 0
        )
        assert label == "HIGH"
        assert color == "ORANGE"

    def test_weed_very_high(self):
        label, color = HealthPlugin.calculate_allergy_risk(
            0, 0, WEED_THRESHOLDS[2]
        )
        assert label == "VERY HIGH"
        assert color == "RED"

    def test_highest_category_wins(self):
        """When multiple categories differ, the highest risk wins."""
        label, _ = HealthPlugin.calculate_allergy_risk(
            5, TREE_THRESHOLDS[2], WEED_THRESHOLDS[0]
        )
        assert label == "VERY HIGH"

    def test_all_very_high(self):
        label, color = HealthPlugin.calculate_allergy_risk(
            GRASS_THRESHOLDS[2], TREE_THRESHOLDS[2], WEED_THRESHOLDS[2]
        )
        assert label == "VERY HIGH"
        assert color == "RED"

    def test_just_below_moderate(self):
        """Values just below moderate thresholds remain LOW."""
        label, _ = HealthPlugin.calculate_allergy_risk(
            GRASS_THRESHOLDS[0] - 1,
            TREE_THRESHOLDS[0] - 1,
            WEED_THRESHOLDS[0] - 1,
        )
        assert label == "LOW"


# ── Respiratory Risk Calculation ─────────────────────────────────────


class TestRespiratoryRisk:
    """Tests for respiratory risk score on 0-12 scale."""

    def test_zero_inputs(self):
        assert HealthPlugin.calculate_respiratory_risk(0, 0, 0) == 0.0

    def test_max_aqi_only(self):
        """AQI at 300 gives 6.0 points."""
        score = HealthPlugin.calculate_respiratory_risk(300, 0, 0)
        assert score == 6.0

    def test_max_pm25_only(self):
        """PM2.5 at 150 gives 3.0 points."""
        score = HealthPlugin.calculate_respiratory_risk(0, 150, 0)
        assert score == 3.0

    def test_max_pollen_only(self):
        """Total pollen at 500 gives 3.0 points."""
        score = HealthPlugin.calculate_respiratory_risk(0, 0, 500)
        assert score == 3.0

    def test_all_maxed_equals_12(self):
        score = HealthPlugin.calculate_respiratory_risk(300, 150, 500)
        assert score == MAX_RISK_SCALE

    def test_exceeding_max_is_capped(self):
        """Values above maximums still cap at 12."""
        score = HealthPlugin.calculate_respiratory_risk(600, 300, 1000)
        assert score == MAX_RISK_SCALE

    def test_moderate_values(self):
        """Moderate inputs produce a mid-range score."""
        score = HealthPlugin.calculate_respiratory_risk(100, 50, 200)
        assert 0.0 < score < MAX_RISK_SCALE

    def test_result_is_float(self):
        score = HealthPlugin.calculate_respiratory_risk(42, 8.5, 35)
        assert isinstance(score, float)


# ── Flu Risk Calculation ─────────────────────────────────────────────


class TestFluRisk:
    """Tests for flu risk score on 0-12 scale."""

    def test_zero_inputs(self):
        assert HealthPlugin.calculate_flu_risk(0, 0, 0) == 0.0

    def test_max_score(self):
        score = HealthPlugin.calculate_flu_risk(300, 150, 300)
        assert score == MAX_RISK_SCALE

    def test_capped_above_max(self):
        score = HealthPlugin.calculate_flu_risk(600, 400, 800)
        assert score == MAX_RISK_SCALE

    def test_only_pm10(self):
        """PM10 at 300 gives 3.0 points."""
        score = HealthPlugin.calculate_flu_risk(0, 0, 300)
        assert score == 3.0

    def test_moderate_values(self):
        score = HealthPlugin.calculate_flu_risk(100, 50, 100)
        assert 0.0 < score < MAX_RISK_SCALE


# ── Cough Risk Calculation ───────────────────────────────────────────


class TestCoughRisk:
    """Tests for cough risk score on 0-12 scale."""

    def test_zero_inputs(self):
        assert HealthPlugin.calculate_cough_risk(0, 0, 0) == 0.0

    def test_max_score(self):
        score = HealthPlugin.calculate_cough_risk(200, 100, 400)
        assert score == MAX_RISK_SCALE

    def test_capped_above_max(self):
        score = HealthPlugin.calculate_cough_risk(500, 300, 1000)
        assert score == MAX_RISK_SCALE

    def test_only_pollen(self):
        """Total pollen at 400 gives 4.0 points."""
        score = HealthPlugin.calculate_cough_risk(0, 0, 400)
        assert score == 4.0

    def test_only_pm25(self):
        """PM2.5 at 100 gives 4.0 points."""
        score = HealthPlugin.calculate_cough_risk(0, 100, 0)
        assert score == 4.0


# ── Plugin Class ─────────────────────────────────────────────────────


class TestHealthPlugin:
    """Tests for the HealthPlugin class itself."""

    def test_plugin_id(self, manifest):
        plugin = HealthPlugin(manifest)
        assert plugin.plugin_id == "health"

    def test_plugin_id_matches_manifest(self, manifest):
        plugin = HealthPlugin(manifest)
        assert plugin.plugin_id == manifest["id"]

    def test_validate_config_valid(self, plugin):
        errors = plugin.validate_config(
            {"latitude": 40.0, "longitude": -74.0}
        )
        assert errors == []

    def test_validate_config_defaults(self, plugin):
        """Empty config uses defaults and is valid."""
        errors = plugin.validate_config({})
        assert errors == []

    def test_validate_config_invalid_latitude(self, plugin):
        errors = plugin.validate_config({"latitude": 91})
        assert any("Latitude" in e for e in errors)

    def test_validate_config_invalid_longitude(self, plugin):
        errors = plugin.validate_config({"longitude": -181})
        assert any("Longitude" in e for e in errors)

    def test_validate_config_non_numeric_latitude(self, plugin):
        errors = plugin.validate_config({"latitude": "abc"})
        assert any("Latitude" in e for e in errors)

    def test_validate_config_non_numeric_longitude(self, plugin):
        errors = plugin.validate_config({"longitude": "xyz"})
        assert any("Longitude" in e for e in errors)

    @patch("plugins.health.requests.get")
    def test_fetch_data_success(self, mock_get, plugin):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_api_response()
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        data = result.data
        assert "grass_pollen" in data
        assert "tree_pollen" in data
        assert "weed_pollen" in data
        assert "aqi" in data
        assert "european_aqi" in data
        assert "pm25" in data
        assert "pm10" in data
        assert "allergy_risk" in data
        assert "allergy_risk_color" in data
        assert "respiratory_risk" in data
        assert "flu_risk" in data
        assert "cough_risk" in data
        assert "formatted" in data

    @patch("plugins.health.requests.get")
    def test_fetch_data_api_failure(self, mock_get, plugin):
        mock_get.side_effect = Exception("Connection timeout")

        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    @patch("plugins.health.requests.get")
    def test_fetch_data_empty_current(self, mock_get, plugin):
        mock_resp = Mock()
        mock_resp.json.return_value = {"current": {}}
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        result = plugin.fetch_data()
        assert result.available is True
        assert result.data["grass_pollen"] == 0
        assert result.data["aqi"] == 0

    @patch("plugins.health.requests.get")
    def test_fetch_data_null_values(self, mock_get, plugin):
        """API sometimes returns null for unavailable pollen data."""
        mock_resp = Mock()
        mock_resp.json.return_value = _make_api_response(
            grass=None, birch=None, alder=None, ragweed=None,
            us_aqi=None, european_aqi=None, pm25=None, pm10=None,
        )
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        result = plugin.fetch_data()
        assert result.available is True
        assert result.data["grass_pollen"] == 0
        assert result.data["tree_pollen"] == 0
        assert result.data["flu_risk"] == 0.0

    @patch("plugins.health.requests.get")
    def test_fetch_data_tree_pollen_combines_birch_and_alder(
        self, mock_get, plugin
    ):
        mock_resp = Mock()
        mock_resp.json.return_value = _make_api_response(
            birch=30, alder=15
        )
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        result = plugin.fetch_data()
        assert result.data["tree_pollen"] == 45

    @patch("plugins.health.requests.get")
    def test_fetch_data_high_pollen(self, mock_get, plugin):
        mock_resp = Mock()
        mock_resp.json.return_value = _make_api_response(
            grass=250, birch=300, alder=200, ragweed=250,
            us_aqi=180, european_aqi=120, pm25=65, pm10=95,
        )
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        result = plugin.fetch_data()
        assert result.data["allergy_risk"] == "VERY HIGH"
        assert result.data["flu_risk"] > 0
        assert result.data["cough_risk"] > 0

    @patch("plugins.health.requests.get")
    def test_fetch_data_uses_config_coordinates(self, mock_get, plugin):
        plugin._config = {"latitude": 48.8566, "longitude": 2.3522}
        mock_resp = Mock()
        mock_resp.json.return_value = _make_api_response()
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        plugin.fetch_data()

        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"]["latitude"] == 48.8566
        assert call_kwargs[1]["params"]["longitude"] == 2.3522

    @patch("plugins.health.requests.get")
    def test_fetch_data_api_url(self, mock_get, plugin):
        mock_resp = Mock()
        mock_resp.json.return_value = _make_api_response()
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        plugin.fetch_data()

        call_args = mock_get.call_args
        assert call_args[0][0] == AIR_QUALITY_API_URL

    @patch("plugins.health.requests.get")
    def test_get_formatted_display(self, mock_get, plugin):
        mock_resp = Mock()
        mock_resp.json.return_value = _make_api_response()
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        lines = plugin.get_formatted_display()

        assert lines is not None
        assert len(lines) == 6
        assert "ALLERGY" in lines[0]
        assert "HEALTH" in lines[0]

    @patch("plugins.health.requests.get")
    def test_get_formatted_display_api_failure(self, mock_get, plugin):
        mock_get.side_effect = Exception("timeout")

        lines = plugin.get_formatted_display()
        assert lines is None

    def test_manifest_variables_present(self, manifest, plugin):
        """All manifest variables are returned by fetch_data."""
        expected_vars = manifest["variables"]["simple"]

        with patch("plugins.health.requests.get") as mock_get:
            mock_resp = Mock()
            mock_resp.json.return_value = _make_api_response()
            mock_resp.raise_for_status = Mock()
            mock_get.return_value = mock_resp

            result = plugin.fetch_data()
            assert result.available is True
            for var in expected_vars:
                assert var in result.data, f"Missing variable: {var}"


# ── Color Mapping ────────────────────────────────────────────────────


class TestColorToCode:
    """Tests for color name to board code mapping."""

    def test_green(self):
        assert HealthPlugin._color_to_code("GREEN") == 66

    def test_yellow(self):
        assert HealthPlugin._color_to_code("YELLOW") == 65

    def test_orange(self):
        assert HealthPlugin._color_to_code("ORANGE") == 64

    def test_red(self):
        assert HealthPlugin._color_to_code("RED") == 63

    def test_violet(self):
        assert HealthPlugin._color_to_code("VIOLET") == 68

    def test_unknown_defaults_to_green(self):
        assert HealthPlugin._color_to_code("UNKNOWN") == 66

    def test_case_insensitive(self):
        assert HealthPlugin._color_to_code("green") == 66
        assert HealthPlugin._color_to_code("Red") == 63


# ── Edge Cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests for health plugin."""

    def test_negative_pollen_treated_as_zero(self):
        """Negative pollen shouldn't cause errors."""
        label, _ = HealthPlugin.calculate_allergy_risk(-5, -10, -3)
        assert label == "LOW"

    def test_very_large_pollen(self):
        label, color = HealthPlugin.calculate_allergy_risk(10000, 10000, 10000)
        assert label == "VERY HIGH"
        assert color == "RED"

    def test_respiratory_risk_negative_inputs(self):
        """Negative values should still produce a valid score."""
        score = HealthPlugin.calculate_respiratory_risk(-10, -5, -20)
        assert score >= 0.0
        assert score <= MAX_RISK_SCALE

    def test_flu_risk_boundary(self):
        """Exact boundary values for each component."""
        # AQI=150 gives 3.0, PM2.5=75 gives 1.5, PM10=150 gives 1.5
        score = HealthPlugin.calculate_flu_risk(150, 75, 150)
        assert score == 6.0

    def test_cough_risk_boundary(self):
        """Exact half-max values for each component."""
        # AQI=100 gives 2.0, PM2.5=50 gives 2.0, Pollen=200 gives 2.0
        score = HealthPlugin.calculate_cough_risk(100, 50, 200)
        assert score == 6.0
