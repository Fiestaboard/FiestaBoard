"""The MCP plugin tools must not depend on ``src.api_server`` (issue #1757).

Before #1757, every mutating plugin MCP tool did a call-time
``from .api_server import <handler>`` — so although ``import src.mcp_server``
was clean, *using* any plugin tool dragged the whole 10k-line api_server
module (and its route table, background tasks, and MCP mount) into the
process, completing the api_server ↔ mcp_server cycle at runtime.

The tools now delegate to :class:`src.plugins.service.PluginService`, which
resolves its collaborators from their canonical homes. This test pins the
improvement the honest way: in a fresh interpreter it imports mcp_server,
builds the server, exercises all six mutating plugin tools end-to-end against
patched canonical seams, verifies they really drove the registry and
ConfigManager (so the run is not vacuous), and then asserts
``src.api_server`` never entered ``sys.modules``.

The remaining api_server imports in mcp_server (``get_system_info``'s
version/service peek and ``set_active_page``) are other domains' seams and
out of #1757's scope — they are exactly why this test exercises the plugin
tools rather than just importing the module.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import asyncio
import sys
from unittest.mock import MagicMock, patch

import src.mcp_server as mcp_server

assert "src.api_server" not in sys.modules, "importing mcp_server must not import api_server"

mcp = mcp_server._build_mcp_server()
assert mcp is not None, "mcp package unavailable; cannot exercise the tools"


def call(tool_name, **kwargs):
    result = mcp._tool_manager._tools[tool_name].fn(**kwargs)
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    return result


registry = MagicMock()
registry.get_plugin.return_value = object()
registry.enable_plugin.return_value = True
registry.disable_plugin.return_value = True
registry.install_from_registry.return_value = []
registry.uninstall_external_plugin.return_value = []
registry.list_plugins.return_value = []
registry.set_plugin_config.return_value = []
registry.get_plugin_source.return_value = None  # update tool: clean 404 path

config_manager = MagicMock()
# Stateful: reads reflect the last persisted config, like the real
# ConfigManager. The service re-reads after persisting (env-overlay re-seed,
# #1864); a fixed return_value fakes a phantom diff and a second
# registry.set_plugin_config call.
_stored = {"api_key": "test_key_123"}

def _persist_config(pid, cfg):
    _stored.clear()
    _stored.update(cfg)

config_manager.get_plugin_config.side_effect = lambda pid, include_env_overrides=True: dict(_stored)
config_manager.set_plugin_config.side_effect = _persist_config
config_manager._mask_sensitive.return_value = {"api_key": "***"}

with (
    patch("src.plugins.get_plugin_registry", return_value=registry),
    patch("src.config_manager.get_config_manager", return_value=config_manager),
    patch("src.displays.service.reset_display_service"),
    patch("src.templates.engine.reset_template_engine"),
):
    assert call("install_plugin", plugin_id="stocks")["status"] == "success"
    assert call("enable_plugin", plugin_id="stocks")["status"] == "success"
    assert call("disable_plugin", plugin_id="stocks")["status"] == "success"
    assert call("configure_plugin", plugin_id="stocks", config={"api_key": "k"})["status"] == "success"
    assert call("uninstall_plugin", plugin_id="stocks")["status"] == "success"
    # No source for the plugin: the guarded update path refuses. #1765 made
    # tool failures raise ToolError (protocol isError) instead of returning
    # an error envelope — the point here is that it refused without
    # api_server, whatever the error surface.
    from mcp.server.mcpserver.exceptions import ToolError
    try:
        call("update_plugin", plugin_id="stocks")
        raise AssertionError("update_plugin with no source must fail")
    except ToolError:
        pass

# Not vacuous: the tools really drove the collaborators.
registry.install_from_registry.assert_called_once_with("stocks")
registry.enable_plugin.assert_called()
registry.disable_plugin.assert_called_once_with("stocks")
registry.set_plugin_config.assert_called_once()
registry.uninstall_external_plugin.assert_called_once_with("stocks")
config_manager.enable_plugin.assert_called()
config_manager.set_plugin_config.assert_called_once()

assert "src.api_server" not in sys.modules, (
    "a plugin MCP tool imported src.api_server — the #1757 cycle break regressed"
)
print("DECOUPLED")
"""


def test_plugin_mcp_tools_run_without_importing_api_server():
    """All six mutating plugin tools work in a process that never loads api_server."""
    pytest.importorskip("mcp", reason="mcp package not installed")
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "DECOUPLED" in result.stdout
