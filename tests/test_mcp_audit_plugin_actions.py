"""Offline regression contracts for the MCP display and plugin audit."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.plugins.loader import PluginLoader

PLUGIN_ID = "recording_output"
FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / PLUGIN_ID


@pytest.fixture
def output(tmp_path):
    root = tmp_path / "external"
    target = root / PLUGIN_ID
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("__pycache__"))
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    properties = manifest["output"]["settings_schema"]["properties"]
    properties["access_tokens"] = {"type": "array", "items": {"type": "string", "secret": True}}
    properties["connection"] = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["lan", "cloud"]},
            "cloud_key": {"type": "string", "ui:visible_when": {"mode": "cloud"}},
        },
        "required": ["mode", "cloud_key"],
    }
    manifest["output"]["actions"] = [
        {"id": "inspect", "label": "Inspect settings"},
        {"id": "inspect_override", "label": "Inspect alternate connection"},
        {
            "id": "require_model_code",
            "label": "Model-specific operation",
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
        },
    ]
    manifest_path.write_text(json.dumps(manifest))
    with (target / "__init__.py").open("a") as source:
        source.write(
            "\n\ndef _audit_inspect(self, inputs):\n"
            "    from src.plugins import ActionField, ActionOutcome\n"
            '    return ActionOutcome(fields={"config": ActionField(value=self.config)})\n'
            "\nRecordingOutput.action_inspect = _audit_inspect\n"
            "RecordingOutput.action_require_model_code = _audit_inspect\n"
            "\n\ndef _audit_handle(cls, ctx):\n"
            "    from src.plugins import ActionField, ActionOutcome\n"
            '    if ctx.action == "inspect_override":\n'
            '        instance = ctx.instance({**ctx.board["output_config"], "host": "192.0.2.51"})\n'
            "        return ActionOutcome(fields={\n"
            '            "model": ActionField(value=instance.device_model["id"]),\n'
            '            "geometry": ActionField(value=list(instance.board_geometry)),\n'
            "        })\n"
            "    return super(RecordingOutput, cls).handle_action(ctx)\n"
            "\nRecordingOutput.handle_action = classmethod(_audit_handle)\n"
        )
    loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[root])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    from src.api_server import app

    with patch("src.outputs.routes.reinitialize_board_clients"):
        yield TestClient(app)
    loader.unload_plugin(PLUGIN_ID)


def _create(output, **config):
    return output.post(
        f"/outputs/{PLUGIN_ID}/boards",
        json={
            "device_model": "recording_sign",
            "output_config": {"host": "192.0.2.50", "token": "test_stored_token", **config},
        },
    )


def test_declared_property_secrets_are_masked_and_restored_for_actions(output):
    created = _create(output)
    assert created.status_code == 201, created.text
    board = created.json()
    assert board["output_config"]["token"] == "***"
    response = output.post(
        f"/boards/{board['id']}/actions/inspect",
        json={"output_config": board["output_config"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["fields"]["config"]["value"]["token"] == "test_stored_token"


def test_secret_array_items_do_not_leave_create_response_in_plaintext(output):
    created = _create(output, access_tokens=["test_array_secret"])
    assert created.status_code == 201, created.text
    assert created.json()["output_config"]["access_tokens"] == ["***"]


def test_hidden_required_nested_field_does_not_prevent_board_creation(output):
    created = _create(output, connection={"mode": "lan"})
    assert created.status_code == 201, created.text


def test_visible_required_nested_field_is_still_required(output):
    created = _create(output, connection={"mode": "cloud"})
    assert created.status_code == 400, created.text
    assert "cloud_key" in created.text


def test_saved_action_partial_edits_preserve_unedited_connection_settings(output):
    created = _create(output)
    assert created.status_code == 201, created.text
    response = output.post(
        f"/boards/{created.json()['id']}/actions/inspect",
        json={"output_config": {"token": "test_replacement_token"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["fields"]["config"]["value"] == {
        "host": "192.0.2.50",
        "token": "test_replacement_token",
    }


@pytest.mark.parametrize("saved", [False, True], ids=["draft", "saved"])
def test_model_visible_action_input_is_required_for_the_selected_model(output, saved):
    if saved:
        created = _create(output)
        assert created.status_code == 201, created.text
        url = f"/boards/{created.json()['id']}/actions/require_model_code"
        body = {}
    else:
        url = f"/outputs/{PLUGIN_ID}/actions/require_model_code"
        body = {"device_model": "recording_sign", "output_config": {"host": "192.0.2.50"}}
    response = output.post(url, json=body)
    assert response.status_code == 400, response.text
    assert "code" in response.text


def test_model_hidden_action_input_can_be_omitted_on_another_model(output):
    response = output.post(
        f"/outputs/{PLUGIN_ID}/actions/require_model_code",
        json={"device_model": "divoom_pixoo64", "output_config": {"host": "192.0.2.50"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_action_connection_override_preserves_selected_model_and_geometry(output):
    created = output.post(
        f"/outputs/{PLUGIN_ID}/boards",
        json={"device_model": "divoom_pixoo64", "output_config": {"host": "192.0.2.50"}},
    )
    assert created.status_code == 201, created.text
    board = created.json()
    response = output.post(f"/boards/{board['id']}/actions/inspect_override", json={})
    assert response.status_code == 200, response.text
    fields = response.json()["fields"]
    assert {"model": fields["model"]["value"], "geometry": fields["geometry"]["value"]} == {
        "model": "divoom_pixoo64",
        "geometry": [board["rows"], board["cols"]],
    }


def test_action_closes_throwaway_instance_when_connection_open_fails(output, monkeypatch):
    module = sys.modules[f"plugins.{PLUGIN_ID}"]

    def failing_open(self):
        self.opened = True
        raise OSError("test device offline after opening resources")

    monkeypatch.setattr(module.RecordingOutput, "open", failing_open)
    response = output.post(f"/outputs/{PLUGIN_ID}/actions/inspect", json={"output_config": {"host": "192.0.2.50"}})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "error"
    instance = module.INSTANCES[-1]
    assert instance.opened
    assert instance.closed


def test_successful_action_closes_its_throwaway_instance(output):
    module = sys.modules[f"plugins.{PLUGIN_ID}"]
    response = output.post(f"/outputs/{PLUGIN_ID}/actions/inspect", json={"output_config": {"host": "192.0.2.50"}})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
    instance = module.INSTANCES[-1]
    assert instance.opened
    assert instance.closed


def test_array_item_secrets_are_restored_only_with_matching_identity():
    from src.outputs.output_config import mask_output_config, masked_secret_paths, unmask_output_config

    schema = {"type": "array", "items": {"type": "string", "secret": True}}
    assert mask_output_config(["secret", ""], schema) == ["***", ""]
    restored = unmask_output_config(["***"], ["secret"], schema)
    assert restored == ["***"]  # A position is not evidence of identity.
    assert masked_secret_paths(restored, schema) == ["[0]"]

    nested = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "secrets": schema},
        },
    }
    assert mask_output_config([{"id": "a", "secrets": ["secret"]}], nested) == [{"id": "a", "secrets": ["***"]}]


def test_secret_schema_nodes_mask_and_restore_entire_values():
    from src.outputs.output_config import mask_output_config, masked_secret_paths, unmask_output_config

    schema = {"type": "object", "secret": True}
    assert mask_output_config({"token": "secret"}, schema) == "***"
    assert unmask_output_config("***", {"token": "secret"}, schema) == {"token": "secret"}
    assert masked_secret_paths("***", schema) == ["output_config"]


def test_nested_secret_fields_restore_after_array_reordering():
    from src.outputs.output_config import mask_output_config, masked_secret_paths, unmask_output_config

    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "credentials": {"type": "object", "secret": True}},
        },
    }
    stored = [{"id": "a", "credentials": {"token": "first"}}, {"id": "b", "credentials": {"token": "second"}}]
    masked = mask_output_config(stored, schema)
    assert masked == [{"id": "a", "credentials": "***"}, {"id": "b", "credentials": "***"}]
    restored = unmask_output_config(list(reversed(masked)), stored, schema)
    assert restored == list(reversed(stored))
    assert masked_secret_paths(restored, schema) == []


def test_output_listing_preserves_model_charset_and_frame_budget(output):
    from dataclasses import replace

    from src.outputs.actions import describe_output
    from src.outputs.models import OutputSummary
    from src.outputs.registry import output_registry

    definition = output_registry().get(PLUGIN_ID)
    definition = replace(definition, capabilities=replace(definition.capabilities, max_frames=7))
    wire = OutputSummary(**describe_output(definition)).model_dump()
    assert wire["device_models"][0]["geometry"] == {"kind": "cells", "rows": 6, "cols": 22}
    assert wire["character_set"] == definition.output_manifest.character_set
    assert wire["capabilities"]["max_frames"] == 7
    assert wire["device_models"][1]["geometry"]["kind"] == "pixels"


def test_conditional_array_items_validate_their_own_visible_fields():
    from copy import deepcopy

    from jsonschema import Draft7Validator

    from src.outputs.output_config import validate_output_config
    from src.plugins.settings_ui import strip_hidden

    item_schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string"},
            "key": {"type": "string", "minLength": 4, "ui:visible_when": {"mode": "cloud"}},
        },
        "required": ["mode", "key"],
    }
    schema = {"type": "array", "items": item_schema}
    original = deepcopy(schema)
    visible, reduced = strip_hidden([{"mode": "lan"}, {"mode": "cloud", "key": "code"}], schema)
    Draft7Validator.check_schema(reduced)
    assert Draft7Validator(reduced).is_valid(visible)
    assert schema == original
    assert validate_output_config([{"mode": "lan"}, {"mode": "cloud", "key": "code"}], schema) == []
    assert validate_output_config([{"mode": "lan"}, {"mode": "cloud"}], schema)
    assert validate_output_config([{"mode": "lan"}, {"mode": "cloud", "key": "x"}], schema)


@pytest.mark.parametrize("stage", ["bind_manifest", "bind_board"])
def test_action_closes_instance_when_binding_fails(output, monkeypatch, stage):
    module = sys.modules[f"plugins.{PLUGIN_ID}"]

    def fail(self, *args, **kwargs):
        raise ValueError("failed binding")

    monkeypatch.setattr(module.RecordingOutput, stage, fail)
    response = output.post(f"/outputs/{PLUGIN_ID}/actions/inspect", json={"output_config": {"host": "192.0.2.50"}})
    assert response.json()["status"] == "error"
    assert module.INSTANCES[-1].closed
