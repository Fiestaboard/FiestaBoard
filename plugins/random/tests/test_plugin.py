"""Tests for the random plugin."""

import json
import re
from pathlib import Path

import pytest

from plugins.random import RandomPlugin, BOARD_COLORS


@pytest.fixture
def random_manifest():
    manifest_path = Path(__file__).parent.parent / "manifest.json"
    with open(manifest_path) as f:
        return json.load(f)


class TestRandomPlugin:
    """Test suite for RandomPlugin."""

    def test_plugin_id(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        assert plugin.plugin_id == "random"

    def test_plugin_id_matches_manifest(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        assert plugin.plugin_id == sample_manifest["id"]

    # --- validate_config ---

    def test_validate_config_valid(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        assert plugin.validate_config(sample_config) == []

    def test_validate_config_two_choices(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        assert plugin.validate_config({"choices": ["Yes", "No"]}) == []

    def test_validate_config_ten_choices(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        choices = [str(i) for i in range(10)]
        assert plugin.validate_config({"choices": choices}) == []

    def test_validate_config_empty_choices(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        errors = plugin.validate_config({"choices": []})
        assert len(errors) > 0
        assert any("2" in e for e in errors)

    def test_validate_config_too_few_choices(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        errors = plugin.validate_config({"choices": ["Only one"]})
        assert len(errors) > 0
        assert any("2" in e for e in errors)

    def test_validate_config_too_many_choices(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        choices = [str(i) for i in range(11)]
        errors = plugin.validate_config({"choices": choices})
        assert len(errors) > 0
        assert any("10" in e for e in errors)

    def test_validate_config_choices_not_a_list(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        errors = plugin.validate_config({"choices": "not a list"})
        assert len(errors) > 0

    def test_validate_config_empty_string_in_choices(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        errors = plugin.validate_config({"choices": ["Valid", ""]})
        assert len(errors) > 0

    def test_validate_config_whitespace_only_choice(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        errors = plugin.validate_config({"choices": ["Valid", "   "]})
        assert len(errors) > 0

    def test_validate_config_non_string_choice(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        errors = plugin.validate_config({"choices": ["Valid", 42]})
        assert len(errors) > 0

    def test_validate_config_refresh_seconds_too_low(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        errors = plugin.validate_config({"choices": ["A", "B"], "refresh_seconds": 10})
        assert len(errors) > 0

    def test_validate_config_refresh_seconds_valid(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        errors = plugin.validate_config({"choices": ["A", "B"], "refresh_seconds": 60})
        assert errors == []

    # --- fetch_data ---

    def test_fetch_data_returns_available(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        assert result.available is True
        assert result.error is None

    def test_fetch_data_has_all_variables(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        assert "choice" in result.data
        assert "coin_flip" in result.data
        assert "color" in result.data
        assert "color_name" in result.data

    def test_fetch_data_choice_from_configured_list(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        choices = sample_config["choices"]
        for _ in range(20):
            result = plugin.fetch_data()
            assert result.data["choice"] in choices

    def test_fetch_data_coin_flip_values(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        seen = set()
        for _ in range(50):
            result = plugin.fetch_data()
            seen.add(result.data["coin_flip"])
        assert seen == {"Heads", "Tails"}

    def test_fetch_data_color_name_values(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        for _ in range(20):
            result = plugin.fetch_data()
            assert result.data["color_name"] in BOARD_COLORS

    def test_fetch_data_color_name_not_filled(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        for _ in range(50):
            result = plugin.fetch_data()
            assert result.data["color_name"] != "filled"

    def test_fetch_data_color_tile_format(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        for _ in range(20):
            result = plugin.fetch_data()
            tile = result.data["color"]
            assert re.match(r'^\{\d+\}$', tile), f"color {tile!r} not in {{N}} format"

    def test_fetch_data_color_tile_valid_code(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        for _ in range(20):
            result = plugin.fetch_data()
            code = int(result.data["color"][1:-1])
            assert 63 <= code <= 70, f"color tile code {code} out of valid range 63–70"

    def test_fetch_data_color_tile_matches_color_name(self, sample_manifest, sample_config):
        from plugins.random import _COLOR_TILE_CODES
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        for _ in range(20):
            result = plugin.fetch_data()
            color_name = result.data["color_name"]
            expected_tile = f"{{{_COLOR_TILE_CODES[color_name]}}}"
            assert result.data["color"] == expected_tile

    def test_fetch_data_all_board_colors_reachable_via_name(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        seen = set()
        for _ in range(500):
            result = plugin.fetch_data()
            seen.add(result.data["color_name"])
        assert seen == set(BOARD_COLORS)

    def test_fetch_data_color_excludes_white_and_black(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        for _ in range(100):
            result = plugin.fetch_data()
            assert result.data["color_name"] not in ("white", "black")

    def test_fetch_data_default_choices_when_not_configured(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = {"enabled": True}
        for _ in range(20):
            result = plugin.fetch_data()
            assert result.data["choice"] in ["Heads", "Tails"]

    def test_fetch_data_default_choices_when_list_too_short(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = {"choices": ["Solo"]}
        for _ in range(10):
            result = plugin.fetch_data()
            assert result.data["choice"] in ["Heads", "Tails"]

    def test_fetch_data_variables_match_manifest(self, sample_manifest, sample_config):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        assert result.available is True

        simple = sample_manifest["variables"]["simple"]
        for var in simple:
            assert var in result.data, f"Variable '{var}' declared in manifest but missing from data"

    def test_fetch_data_all_configured_choices_reachable(self, sample_manifest):
        plugin = RandomPlugin(sample_manifest)
        plugin.config = {"choices": ["A", "B", "C"]}
        seen = set()
        for _ in range(200):
            result = plugin.fetch_data()
            seen.add(result.data["choice"])
        assert seen == {"A", "B", "C"}


class TestRandomManifest:
    """Tests for manifest structure."""

    def test_manifest_id(self, random_manifest):
        assert random_manifest["id"] == "random"

    def test_manifest_has_required_fields(self, random_manifest):
        for field in ["id", "name", "version", "settings_schema", "variables"]:
            assert field in random_manifest, f"Manifest missing required field: {field}"

    def test_manifest_variables_have_descriptions(self, random_manifest):
        simple = random_manifest["variables"]["simple"]
        for var_name, meta in simple.items():
            assert "description" in meta and meta["description"], \
                f"Variable '{var_name}' missing description"

    def test_manifest_variables_reference_valid_groups(self, random_manifest):
        groups = set(random_manifest["variables"].get("groups", {}).keys())
        simple = random_manifest["variables"]["simple"]
        for var_name, meta in simple.items():
            group = meta.get("group", "")
            if group:
                assert group in groups, \
                    f"Variable '{var_name}' references undefined group '{group}'"

    def test_manifest_has_demo(self, random_manifest):
        assert "demo" in random_manifest
        assert len(random_manifest["demo"]["template"]) == 6
        assert len(random_manifest["demo"]["line_metadata"]) == 6

    def test_manifest_has_screenshot(self, random_manifest):
        screenshots = random_manifest.get("screenshots", [])
        assert len(screenshots) > 0
        assert any(s.get("primary") for s in screenshots)
