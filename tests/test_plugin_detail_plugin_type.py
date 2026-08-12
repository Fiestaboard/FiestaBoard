"""Tests that ``GET /plugins/{plugin_id}`` reports the plugin's type.

The Integrations UI hides the enable/disable toggle for transition plugins
(they run whenever selected -- ``PluginRegistry.get_transition_plugin`` never
consults the enabled flag), so the detail payload must say which kind of
plugin it is describing.  ``list_plugins`` carries ``plugin_type``; this
endpoint builds its own dict and has to carry it too or the detail view
falls back to data-plugin chrome.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app


def _manifest(plugin_type: str) -> SimpleNamespace:
    """Minimal manifest stand-in covering every field the route reads."""
    return SimpleNamespace(
        name="Typewriter",
        version="1.0.0",
        description="Reveals content left-to-right.",
        author="FiestaBoard",
        icon="type",
        category="transition",
        plugin_type=plugin_type,
        settings_schema={},
        raw={},
        max_lengths={},
        env_vars=[],
        documentation=None,
        demo=None,
    )


class _FakeRegistry:
    def __init__(self, plugin_type: str) -> None:
        self._manifest = _manifest(plugin_type)

    def get_manifest(self, plugin_id: str) -> SimpleNamespace | None:
        return self._manifest if plugin_id == "typewriter" else None

    def is_enabled(self, plugin_id: str) -> bool:
        return False

    def parse_instance_key(self, plugin_id: str) -> tuple[str, None]:
        return plugin_id, None

    def list_instances(self, base_id: str) -> list[Any]:
        return []


class _FakeConfigManager:
    def get_plugin_config(self, plugin_id: str) -> dict[str, Any] | None:
        return None

    def _mask_sensitive(self, config: dict[str, Any]) -> dict[str, Any]:
        return config


@pytest.fixture
def client_for(request):
    """Build a TestClient whose registry reports *plugin_type*."""

    def _build(plugin_type: str) -> TestClient:
        registry_patch = patch("src.api_server.get_plugin_registry", return_value=_FakeRegistry(plugin_type))
        config_patch = patch("src.api_server.get_config_manager", return_value=_FakeConfigManager())
        registry_patch.start()
        config_patch.start()
        request.addfinalizer(registry_patch.stop)
        request.addfinalizer(config_patch.stop)
        return TestClient(app)

    return _build


def test_plugin_detail_reports_transition_plugin_type(client_for):
    """A transition plugin's detail payload identifies it as a transition."""
    response = client_for("transition").get("/plugins/typewriter")

    assert response.status_code == 200
    assert response.json()["plugin_type"] == "transition"


def test_plugin_detail_reports_data_plugin_type(client_for):
    """A data plugin's detail payload identifies it as data."""
    response = client_for("data").get("/plugins/typewriter")

    assert response.status_code == 200
    assert response.json()["plugin_type"] == "data"
