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
from src.config_manager import ConfigManager, unmask_sensitive_values

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
    # conftest's autouse ``_isolated_data_dir`` (#1762) dropped the singleton
    # (and refreshed the lock) before this fixture, and drops it again after.
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
        # The MCP configure_plugin tool goes through PluginService, which
        # resolves the registry from its canonical home (#1757) — patch both
        # lookup points, as tests/test_mcp_server.py's plugin_services does.
        patch("src.plugins.get_plugin_registry", return_value=registry),
        patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True),
        patch("src.api_server.reset_display_service"),
        patch("src.api_server.reset_template_engine"),
    ):
        yield applied, cm


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


KEY_A = "key-for-source-a"
KEY_B = "key-for-source-b"


def _stored_two_sources() -> dict:
    return {
        "sources": [
            {"name": "a", "api_key": KEY_A},
            {"name": "b", "api_key": KEY_B},
        ]
    }


class TestUnmaskListIdentity:
    """Secrets inside a list must follow their element, not its index.

    ``unmask_sensitive_values`` used to pair incoming list elements with stored
    ones by position. Any edit that changes a list's shape — a delete, a
    reorder, an insert — then restored the wrong element's secret, or wrote an
    empty string where a secret belonged.
    """

    def test_deleting_an_earlier_source_does_not_hand_its_key_to_a_later_one(self):
        stored = _stored_two_sources()
        incoming = {"sources": [{"name": "b", "api_key": MASK}]}

        result = unmask_sensitive_values(incoming, stored)

        assert result["sources"] == [{"name": "b", "api_key": KEY_B}]

    def test_reordering_sources_keeps_each_key_with_its_own_source(self):
        stored = _stored_two_sources()
        incoming = {"sources": [{"name": "b", "api_key": MASK}, {"name": "a", "api_key": MASK}]}

        result = unmask_sensitive_values(incoming, stored)

        assert result["sources"] == [
            {"name": "b", "api_key": KEY_B},
            {"name": "a", "api_key": KEY_A},
        ]

    def test_inserting_a_source_neither_cross_wires_nor_destroys_the_others(self):
        stored = _stored_two_sources()
        incoming = {
            "sources": [
                {"name": "c", "api_key": "brand-new-key-c"},
                {"name": "a", "api_key": MASK},
                {"name": "b", "api_key": MASK},
            ]
        }

        result = unmask_sensitive_values(incoming, stored)

        assert result["sources"] == [
            {"name": "c", "api_key": "brand-new-key-c"},
            {"name": "a", "api_key": KEY_A},
            {"name": "b", "api_key": KEY_B},
        ]

    def test_an_unidentifiable_element_keeps_the_mask_rather_than_guessing(self):
        stored = {"sources": [{"url": "https://example.com/one", "api_key": KEY_A}]}
        incoming = {"sources": [{"url": "https://example.com/two", "api_key": MASK}]}

        result = unmask_sensitive_values(incoming, stored)

        # No stable identity ties the incoming element to the stored one, so
        # the sentinel survives for the schema layer to reject. Restoring
        # KEY_A here would authenticate the new URL with the old URL's key;
        # writing "" would destroy a working credential.
        assert result["sources"] == [{"url": "https://example.com/two", "api_key": MASK}]

    def test_elements_without_an_id_field_match_on_their_other_keys(self):
        stored = {
            "sources": [
                {"url": "https://example.com/one", "api_key": KEY_A},
                {"url": "https://example.com/two", "api_key": KEY_B},
            ]
        }
        incoming = {
            "sources": [
                {"url": "https://example.com/two", "api_key": MASK},
                {"url": "https://example.com/one", "api_key": MASK},
            ]
        }

        result = unmask_sensitive_values(incoming, stored)

        assert result["sources"] == [
            {"url": "https://example.com/two", "api_key": KEY_B},
            {"url": "https://example.com/one", "api_key": KEY_A},
        ]

    def test_update_plugin_config_preserves_a_secret_nested_in_a_list(self, tmp_path):
        """update_plugin_config must un-mask at depth, like set_plugin_config."""
        saved_instance = ConfigManager._instance
        ConfigManager._instance = None
        ConfigManager._lock = threading.Lock()
        try:
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            cm.set_plugin_config("test_plugin", {"enabled": True, "sources": [{"name": "a", "api_key": KEY_A}]})

            cm.update_plugin_config("test_plugin", {"sources": [{"name": "a", "api_key": MASK}]})

            assert cm.get_plugin_config("test_plugin")["sources"] == [{"name": "a", "api_key": KEY_A}]
        finally:
            ConfigManager._instance = saved_instance
            ConfigManager._lock = threading.Lock()
