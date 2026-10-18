"""Generic MCP display tools exercise real plugin declarations and persisted state."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from src.plugins.loader import PluginLoader
from src.settings.service import SettingsService
from tests import test_mcp_state_effects as sibling
from tests.test_mcp_state_effects import _persisted_files, call, call_expect_error

mcp = sibling.mcp
services = sibling.services
PLUGIN_ID = "recording_output"
STORED_TOKEN = "test_display_stored_token"
UPDATED_TOKEN = "test_display_updated_token"


@pytest.fixture
def output(services, tmp_path, monkeypatch):
    """Load an actual output package; patch only display-service initialization."""
    target = tmp_path / "external" / PLUGIN_ID
    shutil.copytree(
        Path(__file__).parent / "fixtures" / "plugins" / PLUGIN_ID,
        target,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    path = target / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["output"].update(
        min_interval_ms=750,
        write_timeout_ms=1200,
        read_back={"supported": True, "cost": "network", "suggested_interval_s": 91},
        actions=[
            {"id": "identify", "label": "Identify"},
            {
                "id": "inspect_context",
                "label": "Inspect action context",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "minLength": 4,
                            "ui:visible_when": {"@device_model": "recording_sign"},
                        }
                    },
                    "required": ["code"],
                },
                "result_fields": {"token": {"secret": True}},
            },
            {"id": "refuse", "label": "Refuse operation"},
        ],
    )
    manifest["output"]["settings_schema"]["properties"]["access_tokens"] = {
        "type": "array",
        "items": {"type": "string", "secret": True},
    }
    path.write_text(json.dumps(manifest))
    with (target / "__init__.py").open("a") as source:
        source.write(
            "\nACTION_RUNS = []\n"
            "\ndef _inspect_context(self, inputs):\n"
            "    from src.plugins import ActionField, ActionOutcome\n"
            '    result = {"model": self.device_model["id"], "geometry": list(self.board_geometry),\n'
            '              "host": self.config["host"], "token": self.config.get("token"), "code": inputs.get("code")}\n'
            "    ACTION_RUNS.append(result)\n"
            "    return ActionOutcome(fields={key: ActionField(value=value) for key, value in result.items()})\n"
            "\nRecordingOutput.action_inspect_context = _inspect_context\n"
            "\ndef _refuse(self, inputs):\n"
            "    from src.plugins import ActionOutcome\n"
            '    return ActionOutcome(status="error", message="Device refused the operation.")\n'
            "\nRecordingOutput.action_refuse = _refuse\n"
        )
    loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[target.parent])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    settings_file = tmp_path / "settings.json"
    settings = SettingsService(settings_file=str(settings_file))
    settings.set_boards([{"id": "existing-board", "name": "Existing board", "device_type": "flagship"}])
    monkeypatch.setattr("src.settings.service._settings_service", settings)
    monkeypatch.setattr("src.outputs.routes.reinitialize_board_clients", lambda: None)
    monkeypatch.setattr("src.settings.routes.reinitialize_board_clients", lambda: None)
    monkeypatch.setattr("src.api_server.peek_service", lambda: None)
    monkeypatch.setattr("src.display_runtime.peek_service", lambda: None)
    yield SimpleNamespace(
        settings=settings,
        settings_file=settings_file,
        definition=loader.output_plugins[PLUGIN_ID][1].output,
        module=sys.modules[f"plugins.{PLUGIN_ID}"],
    )
    loader.unload_plugin(PLUGIN_ID)


def create(mcp, **overrides):
    return call(
        mcp,
        "create_display",
        **{
            "output_id": PLUGIN_ID,
            "device_model": "recording_sign",
            "output_config": {"host": "192.0.2.50", "token": STORED_TOKEN, "wait_for_cancel": True},
            "name": "Custom display",
            **overrides,
        },
    )["board"]


def stored_board(output, board_id):
    # A new service rereads the file, independent of the tool's singleton.
    fresh = SettingsService(settings_file=str(output.settings_file))
    return next(board for board in fresh.get_board_settings().boards if board["id"] == board_id)


def test_list_display_outputs_exposes_complete_real_plugin_declarations(mcp, output, tmp_path):
    before = _persisted_files(tmp_path)
    listing = call(mcp, "list_display_outputs", output_id=PLUGIN_ID)
    assert listing["total"] == 1
    declaration = listing["outputs"][0]
    assert declaration["id"] == PLUGIN_ID
    assert declaration["device_models"][0]["geometry"] == {"kind": "cells", "rows": 6, "cols": 22}
    assert declaration["device_models"][1]["geometry"]["kind"] == "pixels"
    assert declaration["device_models"][0]["animation"]["delivery"] == "stream"
    assert declaration["character_set"] == output.definition.character_set
    assert declaration["capabilities"]["read_back"] == {
        "supported": True,
        "cost": "network",
        "suggested_interval_s": 91,
    }
    assert declaration["capabilities"]["min_interval_ms"] == 750
    assert declaration["capabilities"]["write_timeout_ms"] == 1200
    assert "max_frames" in declaration["capabilities"]
    assert declaration["settings_schema"]["properties"]["token"]["secret"] is True
    assert {action["id"] for action in declaration["actions"]} == {"identify", "inspect_context", "refuse"}
    assert _persisted_files(tmp_path) == before
    assert output.module.INSTANCES == [], "Discovery must not construct a device instance"


def test_create_display_persists_and_masks_all_declared_secrets(mcp, output):
    created = create(
        mcp,
        output_config={"host": "192.0.2.50", "token": STORED_TOKEN, "access_tokens": ["test_array_token"]},
    )
    saved = stored_board(output, created["id"])
    assert saved["name"] == "Custom display"
    assert saved["output"] == PLUGIN_ID
    assert saved["device_model"] == "recording_sign"
    assert (saved["grid_rows"], saved["grid_cols"]) == (6, 22)
    assert saved["output_config"]["token"] == STORED_TOKEN
    assert saved["output_config"]["access_tokens"] == ["test_array_token"]
    assert created["output_config"]["token"] == "***"
    assert created["output_config"]["access_tokens"] == ["***"]
    assert STORED_TOKEN not in json.dumps(created)
    assert "test_array_token" not in json.dumps(created)


def test_get_display_info_uses_selected_model_and_masks_connection_without_opening(mcp, output, tmp_path):
    created = create(mcp, device_model="divoom_pixoo64")
    before = _persisted_files(tmp_path)
    info = call(mcp, "get_display_info", board_id=created["id"])
    assert info["device_model"] == "divoom_pixoo64"
    assert (info["rows"], info["cols"]) == (10, 16)
    assert info["display"]["width"] == info["display"]["height"] == 64
    assert info["output_config"]["token"] == "***"
    assert info["has_host"] is True
    assert info["has_credentials"] is True
    assert info["capability_source"] == "declared"
    assert STORED_TOKEN not in json.dumps(info)
    assert _persisted_files(tmp_path) == before
    assert output.module.INSTANCES == [], "Description must not open a device"


def test_get_display_info_defaults_to_primary_and_withholds_uninstalled_config(mcp, output):
    output.settings.set_boards(
        [
            {
                "id": "missing",
                "name": "Uninstalled",
                "output": "uninstalled_output",
                "device_type": "panel",
                "device_model": "stored_model",
                "grid_rows": 6,
                "grid_cols": 22,
                "output_config": {"unrecognized_credential": STORED_TOKEN},
            },
            {"id": "second", "name": "Second", "device_type": "note"},
        ]
    )
    info = call(mcp, "get_display_info")
    assert info["id"] == "missing"
    assert info["output_config"] == "***"
    assert info["output_description"] is None
    assert info["capabilities"] is None
    assert info["capability_source"] == "unavailable"
    assert STORED_TOKEN not in json.dumps(info)


def test_configure_display_persists_partial_merge_explicit_false_and_masked_secret(mcp, output):
    created = create(mcp)
    result = call(
        mcp,
        "configure_display",
        board_id=created["id"],
        output_config={"token": "***", "wait_for_cancel": False},
        name="Renamed display",
    )
    saved = stored_board(output, created["id"])
    assert saved["name"] == "Renamed display"
    assert saved["output_config"]["host"] == "192.0.2.50"
    assert saved["output_config"]["token"] == STORED_TOKEN
    assert saved["output_config"]["wait_for_cancel"] is False
    assert saved["device_model"] == "recording_sign"
    assert STORED_TOKEN not in json.dumps(result)
    assert {board["id"] for board in output.settings.get_board_settings().boards} == {"existing-board", created["id"]}
    call(mcp, "configure_display", board_id=created["id"], output_config={"token": UPDATED_TOKEN})
    assert stored_board(output, created["id"])["output_config"]["token"] == UPDATED_TOKEN
    assert call(mcp, "get_display_info", board_id=created["id"])["output_config"]["token"] == "***"


@pytest.mark.parametrize("operation", ["create_display", "configure_display"])
def test_display_mutations_reject_an_undeclared_model_without_persisting(mcp, output, tmp_path, operation):
    created = create(mcp)
    before = _persisted_files(tmp_path)
    arguments = {"output_id": PLUGIN_ID} if operation == "create_display" else {"board_id": created["id"]}
    message = call_expect_error(
        mcp, operation, **arguments, device_model="not_declared", output_config={"host": "192.0.2.99"}
    )
    assert "model" in message.lower()
    assert "not_declared" in message
    assert _persisted_files(tmp_path) == before


def test_configure_display_valid_model_switch_persists_the_new_grid(mcp, output):
    created = create(mcp)
    result = call(mcp, "configure_display", board_id=created["id"], device_model="divoom_pixoo64", output_config={})
    saved = stored_board(output, created["id"])
    assert saved["device_model"] == "divoom_pixoo64"
    assert (saved["grid_rows"], saved["grid_cols"]) == (10, 16)
    assert saved["output_config"]["token"] == STORED_TOKEN
    assert result["board"]["device_model"] == "divoom_pixoo64"


def test_configure_display_invalid_settings_leave_saved_config_untouched(mcp, output, tmp_path):
    created = create(mcp)
    before = _persisted_files(tmp_path)
    message = call_expect_error(
        mcp, "configure_display", board_id=created["id"], output_config={"wait_for_cancel": "not a boolean"}
    )
    assert "wait_for_cancel" in message
    assert _persisted_files(tmp_path) == before


def test_run_display_action_executes_with_model_geometry_and_restored_secret(mcp, output, tmp_path):
    created = create(mcp)
    before = _persisted_files(tmp_path)
    result = call(
        mcp,
        "run_display_action",
        board_id=created["id"],
        action="inspect_context",
        inputs={"code": "1234"},
        output_config={"token": "***"},
    )
    assert result["status"] == "ok"
    assert output.module.ACTION_RUNS[-1] == {
        "model": "recording_sign",
        "geometry": [6, 22],
        "host": "192.0.2.50",
        "token": STORED_TOKEN,
        "code": "1234",
    }
    assert result["fields"]["token"] == {"value": "***", "secret": True, "fills": None}
    assert STORED_TOKEN not in json.dumps(result)
    assert _persisted_files(tmp_path) == before
    assert output.module.INSTANCES[-1].closed


def test_run_display_action_validates_model_specific_input_before_execution(mcp, output):
    created = create(mcp)
    message = call_expect_error(mcp, "run_display_action", board_id=created["id"], action="inspect_context")
    assert "code" in message
    assert output.module.ACTION_RUNS == []
    assert output.module.INSTANCES == []


def test_run_display_action_on_second_model_keeps_saved_pixel_geometry_and_unsaved_edits(mcp, output):
    created = create(mcp, device_model="divoom_pixoo64")
    result = call(
        mcp,
        "run_display_action",
        board_id=created["id"],
        action="inspect_context",
        output_config={"host": "192.0.2.99"},
    )
    assert result["fields"]["model"]["value"] == "divoom_pixoo64"
    assert result["fields"]["geometry"]["value"] == [10, 16]
    assert output.module.ACTION_RUNS[-1]["host"] == "192.0.2.99"
    assert stored_board(output, created["id"])["output_config"]["host"] == "192.0.2.50"


def test_run_display_action_without_result_fields_still_executes(mcp, output):
    created = create(mcp)
    result = call(mcp, "run_display_action", board_id=created["id"], action="identify")
    assert result["status"] == "ok"
    assert output.module.IDENTIFIED == ["192.0.2.50"]
    assert output.module.INSTANCES[-1].closed


def test_run_display_action_device_refusal_is_an_mcp_error(mcp, output):
    created = create(mcp)
    message = call_expect_error(mcp, "run_display_action", board_id=created["id"], action="refuse")
    assert "Device refused" in message


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected"),
    [
        ("list_display_outputs", {"output_id": "uninstalled_output"}, "not installed"),
        ("get_display_info", {"board_id": "missing-board"}, "not found"),
        ("run_display_action", {"board_id": "missing-board", "action": "identify"}, "not found"),
    ],
)
def test_display_lookup_failures_use_standard_mcp_errors(mcp, output, tool_name, arguments, expected):
    assert expected in call_expect_error(mcp, tool_name, **arguments).lower()


def test_generic_display_tools_work_through_published_mcp_protocol(output):
    """Use actual JSON-RPC transport, declarations and persisted board settings."""
    from starlette.testclient import TestClient

    from src.mcp_server import build_streamable_http_app

    headers = {"Accept": "application/json, text/event-stream"}
    with TestClient(build_streamable_http_app(), base_url="http://localhost") as client:

        def rpc(method, params):
            response = client.post(
                "/",
                headers=headers,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )
            assert response.status_code == 200, response.text
            result = response.json()
            assert "error" not in result, result
            return result["result"]

        def invoke(name, **arguments):
            result = rpc("tools/call", {"name": name, "arguments": arguments})
            assert result.get("isError") is not True, result
            return result["structuredContent"]

        rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "display-contract-test", "version": "1"},
            },
        )
        tools = {tool["name"]: tool for tool in rpc("tools/list", {})["tools"]}
        action_hints = tools["run_display_action"]["annotations"]
        assert action_hints["readOnlyHint"] is False
        assert action_hints["destructiveHint"] is True
        assert action_hints["openWorldHint"] is True
        assert tools["list_display_outputs"]["annotations"]["readOnlyHint"] is True
        assert invoke("list_display_outputs", output_id=PLUGIN_ID)["outputs"][0]["id"] == PLUGIN_ID
        created = invoke(
            "create_display",
            output_id=PLUGIN_ID,
            device_model="recording_sign",
            name="Wire display",
            output_config={"host": "192.0.2.50", "token": STORED_TOKEN},
        )["board"]
        assert created["output_config"]["token"] == "***"
        invoke("configure_display", board_id=created["id"], output_config={"host": "192.0.2.51"}, name="Wire renamed")
        info = invoke("get_display_info", board_id=created["id"])
        assert info["name"] == "Wire renamed"
        assert info["output_config"]["host"] == "192.0.2.51"
        assert info["output_config"]["token"] == "***"
        action = invoke("run_display_action", board_id=created["id"], action="inspect_context", inputs={"code": "1234"})
        assert action["fields"]["token"]["value"] == "***"
        assert output.module.ACTION_RUNS[-1]["host"] == "192.0.2.51"
        saved = stored_board(output, created["id"])
        assert saved["name"] == "Wire renamed"
        assert saved["output_config"]["token"] == STORED_TOKEN
        error = rpc("tools/call", {"name": "get_display_info", "arguments": {"board_id": "missing"}})
        assert error["isError"] is True
        assert "not found" in error["content"][0]["text"].lower()
