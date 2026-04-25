"""Tests for the template plugin.

Validates the plugin template showcases the new rich metadata format
correctly and that the formatted_lines bug fix is in place.
"""

import json
import pytest
from pathlib import Path

from plugins._template import MyPlugin
from src.plugins.manifest import PluginManifest


MANIFEST_PATH = Path(__file__).parent.parent / "manifest.json"


@pytest.fixture
def manifest_data():
    with open(MANIFEST_PATH) as f:
        return json.load(f)


@pytest.fixture
def manifest(manifest_data):
    return PluginManifest.from_dict(manifest_data)


class TestTemplatePlugin:
    """Core plugin functionality tests."""

    def test_plugin_id(self, manifest):
        plugin = MyPlugin(manifest)
        assert plugin.plugin_id == "my_plugin"

    def test_fetch_data_missing_api_key(self, manifest):
        plugin = MyPlugin(manifest)
        plugin.config = {}
        result = plugin.fetch_data()
        assert result.available is False
        assert result.error is not None

    def test_fetch_data_returns_formatted_lines_list(self, manifest):
        """The bug fix: formatted_lines must be a list, not a string."""
        plugin = MyPlugin(manifest)
        plugin.config = {"api_key": "test_key_123"}
        result = plugin.fetch_data()
        assert result.available is True
        assert isinstance(result.formatted_lines, list)
        assert len(result.formatted_lines) == 6

    def test_fetch_data_returns_expected_data_keys(self, manifest):
        plugin = MyPlugin(manifest)
        plugin.config = {"api_key": "test_key_123"}
        result = plugin.fetch_data()
        assert result.available is True
        assert "value" in result.data
        assert "status" in result.data
        assert "formatted" in result.data
        assert "items" in result.data

    def test_validate_config_missing_api_key(self, manifest):
        plugin = MyPlugin(manifest)
        errors = plugin.validate_config({})
        assert len(errors) > 0

    def test_validate_config_valid(self, manifest):
        plugin = MyPlugin(manifest)
        errors = plugin.validate_config({"api_key": "test_key_123"})
        assert len(errors) == 0


class TestTemplateManifestMetadata:
    """Tests for the rich metadata format in the template manifest."""

    def test_manifest_uses_dict_simple_format(self, manifest_data):
        simple = manifest_data["variables"]["simple"]
        assert isinstance(simple, dict), "simple should use the rich dict format"

    def test_all_variables_have_descriptions(self, manifest_data):
        simple = manifest_data["variables"]["simple"]
        for var_name, meta in simple.items():
            assert "description" in meta and meta["description"], \
                f"Variable '{var_name}' missing description"

    def test_groups_are_defined(self, manifest_data):
        groups = manifest_data["variables"].get("groups", {})
        assert len(groups) > 0
        for group_id, group_def in groups.items():
            assert "label" in group_def, f"Group '{group_id}' missing label"

    def test_all_variables_have_valid_groups(self, manifest_data):
        groups = set(manifest_data["variables"].get("groups", {}).keys())
        simple = manifest_data["variables"]["simple"]
        for var_name, meta in simple.items():
            group = meta.get("group", "")
            if group:
                assert group in groups, \
                    f"Variable '{var_name}' references undefined group '{group}'"

    def test_manifest_has_arrays(self, manifest_data):
        arrays = manifest_data["variables"].get("arrays", {})
        assert "items" in arrays

    def test_manifest_parses_successfully(self, manifest_data):
        manifest = PluginManifest.from_dict(manifest_data)
        assert manifest.id == "my_plugin"
        assert len(manifest.variables.simple) == 3
        assert "value" in manifest.variables.metadata
        assert manifest.variables.metadata["value"].type == "number"
        assert manifest.variables.groups["main"].label == "Main Data"

    def test_max_lengths_merged_from_metadata(self, manifest_data):
        manifest = PluginManifest.from_dict(manifest_data)
        assert manifest.max_lengths.get("value") == 10
        assert manifest.max_lengths.get("status") == 15
