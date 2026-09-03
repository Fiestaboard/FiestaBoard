"""Mask-sentinel round-trip tests for plugin configuration writes (issue #1743).

Plugin config leaves the process with every sensitive field replaced by the
``"***"`` sentinel (``ConfigManager._mask_sensitive``). Any client that reads a
config and writes it straight back — the settings form, or an MCP client that
called ``list_installed_plugins()`` — therefore posts the sentinel where the
real secret used to be. Writing that through replaces a working credential with
three asterisks, both in the live plugin instance the registry holds and (for
values nested below the top level) on disk.
"""

from __future__ import annotations

import copy
import json
import threading
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.config_manager import ConfigManager

REAL_SECRET = "super-secret-key-abc123"
NESTED_SECRET = "nested-secret-key-xyz789"
MASK = "***"


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mask_env(tmp_path):
    """Real ConfigManager holding stored secrets, plus a mock plugin registry.

    The ConfigManager is real (pinned at a tmp ``config.json``) so the disk
    assertions are about what actually gets persisted, not about a mock's
    call log.
    """
    saved_instance = ConfigManager._instance
    ConfigManager._instance = None
    ConfigManager._lock = threading.Lock()

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"board": {}, "features": {}, "general": {}, "plugins": {}}))
    cm = ConfigManager(config_path=str(config_path))
    cm.set_plugin_config(
        "test_plugin",
        {
            "enabled": True,
            "api_key": REAL_SECRET,
            "location": "New York",
            "sources": [{"name": "primary", "api_key": NESTED_SECRET}],
        },
    )
    cm.set_plugin_config("test_plugin:office", {"enabled": True, "api_key": REAL_SECRET, "location": "Boston"})

    # The endpoint hands the *same dict object* to the registry and then to the
    # ConfigManager, which un-masks in place — so a plain call-args assertion
    # would inspect the already-repaired dict and pass no matter what. Snapshot
    # the config at the moment the live plugin receives it.
    applied: list[dict] = []

    registry = Mock()
    registry.get_plugin.return_value = Mock()
    registry.set_plugin_config.side_effect = lambda _pid, config: applied.append(copy.deepcopy(config)) or []

    with (
        patch("src.api_server.get_plugin_registry", return_value=registry),
        patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True),
        patch("src.api_server.reset_display_service"),
        patch("src.api_server.reset_template_engine"),
    ):
        yield applied, cm

    ConfigManager._instance = saved_instance
    ConfigManager._lock = threading.Lock()


def _masked_body(cm: ConfigManager, plugin_id: str, **overrides) -> dict:
    """The request body a client builds by echoing back a masked GET."""
    masked = cm._mask_sensitive(cm.get_plugin_config(plugin_id))
    masked.update(overrides)
    return {"config": masked}


def _applied_config(applied: list[dict]) -> dict:
    """The config the endpoint handed to the live plugin registry."""
    assert applied, "registry.set_plugin_config was never called"
    return applied[-1]


class TestRestPluginConfigMaskSentinel:
    """PUT /plugins/{plugin_id}/config must never write the mask sentinel."""

    def test_masked_api_key_is_not_applied_to_the_live_plugin(self, client, mask_env):
        applied, cm = mask_env

        response = client.put("/plugins/test_plugin/config", json=_masked_body(cm, "test_plugin", location="Chicago"))

        assert response.status_code == 200
        assert _applied_config(applied)["api_key"] == REAL_SECRET

    def test_masked_api_key_leaves_the_stored_secret_intact(self, client, mask_env):
        _applied, cm = mask_env

        response = client.put("/plugins/test_plugin/config", json=_masked_body(cm, "test_plugin", location="Chicago"))

        assert response.status_code == 200
        assert cm.get_plugin_config("test_plugin")["api_key"] == REAL_SECRET

    def test_masked_secret_nested_in_a_list_leaves_the_stored_secret_intact(self, client, mask_env):
        _applied, cm = mask_env

        response = client.put("/plugins/test_plugin/config", json=_masked_body(cm, "test_plugin"))

        assert response.status_code == 200
        assert cm.get_plugin_config("test_plugin")["sources"][0]["api_key"] == NESTED_SECRET

    def test_masked_api_key_on_an_instance_key_resolves_against_that_instance(self, client, mask_env):
        applied, cm = mask_env

        response = client.put("/plugins/test_plugin:office/config", json=_masked_body(cm, "test_plugin:office"))

        assert response.status_code == 200
        assert _applied_config(applied)["api_key"] == REAL_SECRET
        assert cm.get_plugin_config("test_plugin:office")["api_key"] == REAL_SECRET

    def test_a_real_new_api_key_still_replaces_the_stored_secret(self, client, mask_env):
        applied, cm = mask_env

        response = client.put(
            "/plugins/test_plugin/config",
            json=_masked_body(cm, "test_plugin", api_key="brand-new-key"),
        )

        assert response.status_code == 200
        assert _applied_config(applied)["api_key"] == "brand-new-key"
        assert cm.get_plugin_config("test_plugin")["api_key"] == "brand-new-key"

    def test_a_masked_api_key_with_nothing_stored_is_not_persisted(self, client, mask_env):
        _applied, cm = mask_env
        cm.set_plugin_config("test_plugin", {"enabled": True, "location": "New York"})

        response = client.put(
            "/plugins/test_plugin/config",
            json={"config": {"enabled": True, "api_key": MASK, "location": "New York"}},
        )

        assert response.status_code == 200
        assert cm.get_plugin_config("test_plugin")["api_key"] == ""


class TestMcpConfigurePluginMaskSentinel:
    """The MCP configure_plugin tool must not write back what it read masked."""

    def test_masked_api_key_from_list_installed_plugins_is_not_written_back(self, mask_env):
        pytest.importorskip("mcp", reason="mcp package not installed")

        from src.mcp_server import _build_mcp_server
        from tests.test_mcp_server import _call_tool

        applied, cm = mask_env
        mcp = _build_mcp_server()
        assert mcp is not None

        # What an MCP client sees from list_installed_plugins(): the mask.
        masked = cm._mask_sensitive(cm.get_plugin_config("test_plugin"))
        assert masked["api_key"] == MASK

        result = _call_tool(mcp, "configure_plugin", plugin_id="test_plugin", config=masked)

        assert result.get("success") is not False, result
        assert _applied_config(applied)["api_key"] == REAL_SECRET
        assert cm.get_plugin_config("test_plugin")["api_key"] == REAL_SECRET
