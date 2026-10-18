"""MCP contracts across real third-party output declarations and lifecycle."""

import json
import os
import shutil
from pathlib import Path

import pytest

from src.outputs.config_hooks import mask_config
from src.plugins.loader import PluginLoader
from tests import test_mcp_state_effects as sibling
from tests.test_mcp_state_effects import call

mcp = sibling.mcp
services = sibling.services
PLUGIN_ID = "recording_output"


@pytest.fixture
def output(tmp_path, monkeypatch):
    from src.plugins.registry import PluginRegistry

    root = tmp_path / "external"
    target = root / PLUGIN_ID
    shutil.copytree(
        Path(__file__).parent / "fixtures" / "plugins" / PLUGIN_ID,
        target,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["output"]["settings_schema"]["properties"]["pairing_phrase"] = {"type": "string", "secret": True}
    manifest_path.write_text(json.dumps(manifest))
    loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[root])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    registry = PluginRegistry(plugins_dir=tmp_path / "builtin")
    registry._loader = loader
    registry._plugins[PLUGIN_ID], registry._manifests[PLUGIN_ID] = loader.output_plugins[PLUGIN_ID]
    monkeypatch.setattr("src.plugins.get_plugin_registry", lambda: registry)
    yield registry
    loader.unload_plugin(PLUGIN_ID)


def test_normal_output_masking_honors_custom_secret_names(output):
    config = {"host": "192.0.2.50", "pairing_phrase": "test_custom_secret"}
    assert mask_config(PLUGIN_ID, config) == {"host": "192.0.2.50", "pairing_phrase": "***"}
    assert mask_config("uninstalled_output", config) == "***"


@pytest.mark.parametrize("output_id", [PLUGIN_ID, "uninstalled_output"])
def test_backup_respects_output_secret_policy(mcp, services, output, output_id):
    board = {
        "id": "custom-sign",
        "device_type": "panel",
        "output": output_id,
        "output_config": {"host": "192.0.2.50", "pairing_phrase": "test_custom_secret"},
    }
    data_dir = Path(os.environ["FIESTABOARD_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "settings.json").write_text(json.dumps({"board": {"boards": [board]}}))
    result = call(mcp, "export_backup")
    assert "test_custom_secret" not in json.dumps(result)
    assert result["data"]["settings"]["board"]["boards"][0]["output_config"] == mask_config(
        output_id, board["output_config"]
    )


def test_disabling_output_cannot_report_success_while_output_remains_usable(mcp, services, output):
    from mcp.server.mcpserver.exceptions import ToolError

    from src.outputs.factory import build_driver

    try:
        result = call(mcp, "disable_plugin", plugin_id=PLUGIN_ID)
    except ToolError as exc:
        assert "Output plugins" in str(exc) and "pause" in str(exc)
        return
    # Output plugins intentionally need no enable switch. Refusing this data-
    # plugin operation truthfully is also a valid fix; silent success is not.
    if result.get("status") == "error":
        return
    assert result["status"] == "success", result
    assert output.get_plugin(PLUGIN_ID).enabled is False
    board = {
        "id": "custom-sign",
        "device_type": "flagship",
        "output": PLUGIN_ID,
        "output_config": {"host": "192.0.2.50"},
    }
    driver = build_driver(board)
    if driver is None:
        return
    try:
        sent, _ = driver.render([[1] * 22 for _ in range(6)])
        assert sent is False, "MCP reported disabled, but the output still accepted a real frame"
    finally:
        driver.close()
