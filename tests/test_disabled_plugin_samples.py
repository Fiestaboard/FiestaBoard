# ruff: noqa: F811 - pytest fixtures are imported from their home modules
"""BB-E-12: Sample mode fills in a disabled integration's example values.

``GET /v1/variables`` lists only enabled plugins (the autocomplete
vocabulary). A page can still read a plugin that is installed but off — the
board then shows ``???`` — so the catalogue also names those plugins with
their declared scalar examples (``disabled_plugins``): the editor's Sample
mode uses the examples and its missing-data panel says "<plugin> is off in
Integrations". The field is additive; enabled plugins never appear in it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.plugins.base import PluginBase, PluginResult
from src.plugins.manifest import PluginManifest, VariableMetadata, VariablesSchema
from src.plugins.registry import PluginRegistry
from tests.test_v1_contract import client  # noqa: F401 - fixture


def _manifest(plugin_id: str, name: str, metadata: dict[str, VariableMetadata], arrays=None) -> MagicMock:
    manifest = MagicMock(spec=PluginManifest)
    manifest.id = plugin_id
    manifest.name = name
    manifest.version = "1.0.0"
    manifest.description = ""
    manifest.author = ""
    manifest.icon = "puzzle"
    manifest.category = "utility"
    manifest.fiestaboard_version = ""
    manifest.max_lengths = {}
    manifest.raw = {}
    manifest.color_rules_schema = {}
    manifest.variables = VariablesSchema(simple=list(metadata), auto_discover=False, metadata=metadata)
    return manifest


def _plugin(plugin_id: str) -> MagicMock:
    plugin = MagicMock(spec=PluginBase)
    plugin.plugin_id = plugin_id
    plugin.validate_config.return_value = []
    plugin._validate_refresh_seconds.return_value = []
    plugin.get_data.return_value = PluginResult(available=True, data={})
    plugin.fetch_data.return_value = PluginResult(available=True, data={})
    plugin.enabled = False
    plugin.config = {}
    return plugin


@pytest.fixture
def registry():
    manifests = {
        "date_time": _manifest(
            "date_time",
            "Date & Time",
            {
                "time": VariableMetadata(description="Time", type="string", example="7:00 AM"),
                "day_of_week": VariableMetadata(description="Day", type="string", example="MONDAY"),
                "no_example": VariableMetadata(description="None", type="string"),
                "tint": VariableMetadata(description="Tint", type="color", example="red"),
            },
        ),
        "weather": _manifest(
            "weather", "Weather", {"temperature": VariableMetadata(description="Temp", type="number", example="72")}
        ),
    }
    loader = MagicMock()
    loader.load_errors = {}
    loader.reload_plugin.return_value = None
    loader.load_all_plugins.return_value = {pid: _plugin(pid) for pid in manifests}
    loader.get_manifest.side_effect = lambda pid: manifests.get(pid)
    with patch("src.plugins.registry.PluginLoader", return_value=loader):
        reg = PluginRegistry(plugins_dir=Path("/fake/plugins"))
    with patch("src.config_manager.get_config_manager") as config:
        config.return_value.get_all_plugin_configs.return_value = {
            "date_time": {"enabled": False},
            "weather": {"enabled": True},
        }
        reg.initialize()
    return reg


def test_a_disabled_plugin_is_named_with_its_scalar_examples(registry):
    samples = registry.get_disabled_plugin_samples()
    assert samples == {
        "date_time": {"name": "Date & Time", "examples": {"time": "7:00 AM", "day_of_week": "MONDAY"}},
    }


def test_an_enabled_plugin_is_not_listed_as_disabled(registry):
    assert "weather" not in registry.get_disabled_plugin_samples()


def test_the_catalogue_carries_disabled_plugins_without_adding_them_to_autocomplete(client_with_registry):
    client, _ = client_with_registry
    body = client.get("/v1/variables").json()
    assert body["disabled_plugins"]["date_time"]["examples"]["time"] == "7:00 AM"
    assert "date_time" not in body["variables"]


@pytest.fixture
def client_with_registry(client, registry):
    with patch("src.v1.routes_meta.get_plugin_registry", return_value=registry):
        yield client, registry
