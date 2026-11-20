"""Private settings stay private in public projections and survive edits."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.config_manager import get_config_manager


@pytest.fixture
def client(monkeypatch):
    from src.api_server import app

    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    return TestClient(app)


def _provider(provider_id="first", **changes):
    return {
        "id": provider_id,
        "name": provider_id,
        "base_url": "https://provider.example.invalid/v1",
        "api_key": f"FAKE-api-{provider_id}",
        "headers": {
            "Authorization": f"Bearer FAKE-header-{provider_id}",
            "X-Api-Key": f"FAKE-custom-{provider_id}",
            "X-Empty": "",
        },
        **changes,
    }


@pytest.mark.parametrize("path", ["/settings/ai", "/config/full"])
def test_provider_headers_are_masked_on_reads(client, path):
    cm = get_config_manager()
    cm.set_ai_providers({"providers": [_provider()]})
    response = client.get(path)
    assert response.status_code == 200
    payload = response.json()
    block = payload["ai_providers"] if path == "/config/full" else payload
    assert block["providers"][0]["headers"] == {"Authorization": "***", "X-Api-Key": "***", "X-Empty": ""}
    assert "FAKE-" not in json.dumps(payload)
    assert cm.get_ai_provider("first")["headers"]["Authorization"] == "Bearer FAKE-header-first"


def test_provider_write_response_masks_headers(client):
    response = client.put("/settings/ai", json={"providers": [_provider()]})
    assert response.status_code == 200
    assert response.json()["providers"][0]["headers"]["Authorization"] == "***"
    assert "FAKE-" not in response.text


def test_provider_header_echo_preserves_credentials_after_reorder(client):
    cm = get_config_manager()
    cm.set_ai_providers({"providers": [_provider(), _provider("second")]})
    edited = [
        _provider("second", api_key="***", headers={"Authorization": "***", "X-Api-Key": "***"}),
        _provider("first", api_key="***", headers={"Authorization": "***", "X-Api-Key": "***"}),
    ]
    response = client.put("/settings/ai", json={"providers": edited})
    assert response.status_code == 200
    assert [p["id"] for p in response.json()["providers"]] == ["second", "first"]
    for provider_id in ("first", "second"):
        assert cm.get_ai_provider(provider_id)["headers"] == {
            "Authorization": f"Bearer FAKE-header-{provider_id}",
            "X-Api-Key": f"FAKE-custom-{provider_id}",
        }
    stored = json.loads(Path(cm._config_path).read_text())
    assert stored["ai_providers"]["providers"][0]["headers"]["Authorization"] == "Bearer FAKE-header-second"


def test_provider_header_echo_matches_header_names_case_insensitively(client):
    cm = get_config_manager()
    cm.set_ai_providers({"providers": [_provider()]})
    response = client.put("/settings/ai", json={"providers": [_provider(headers={"authorization": "***"})]})
    assert response.status_code == 200
    assert cm.get_ai_provider("first")["headers"] == {"authorization": "Bearer FAKE-header-first"}


@pytest.mark.parametrize(
    "provider",
    [
        _provider("new", headers={"Authorization": "***"}),
        _provider(headers={"X-Missing": "***"}),
    ],
)
def test_unknown_header_echo_is_rejected_without_changing_any_settings(client, provider):
    cm = get_config_manager()
    cm.set_ai_providers({"enabled": False, "providers": [_provider()]})
    before = cm.get_all()
    response = client.put("/settings/ai", json={"enabled": True, "providers": [provider]})
    assert response.status_code == 400
    assert cm.get_all() == before
    assert "FAKE-" not in response.text


def test_ambiguous_header_echo_is_rejected(client):
    cm = get_config_manager()
    cm.set_ai_providers({"providers": [_provider(headers={"Authorization": "FAKE-one", "authorization": "FAKE-two"})]})
    before = cm.get_all()
    response = client.put("/settings/ai", json={"providers": [_provider(headers={"AUTHORIZATION": "***"})]})
    assert response.status_code == 400
    assert cm.get_all() == before


def test_header_values_can_be_replaced_removed_and_cleared(client):
    cm = get_config_manager()
    cm.set_ai_providers({"providers": [_provider()]})
    response = client.put(
        "/settings/ai", json={"providers": [_provider(headers={"Authorization": "", "X-New": "FAKE-new"})]}
    )
    assert response.status_code == 200
    assert cm.get_ai_provider("first")["headers"] == {"Authorization": "", "X-New": "FAKE-new"}
    response = client.put("/settings/ai", json={"providers": [_provider(headers={})]})
    assert response.status_code == 200
    assert cm.get_ai_provider("first")["headers"] == {}


@pytest.fixture
def registry(monkeypatch):
    from src.plugins.registry import PluginRegistry

    value = PluginRegistry()
    value._manifests["fixture"] = SimpleNamespace(
        settings_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "credential": {"type": "string", "ui:widget": "password"},
                "nested": {"type": "object", "properties": {"secret": {"secret": True}}},
                "sources": {"type": "array", "items": {"type": "object", "properties": {"token": {"secret": True}}}},
            },
        }
    )
    monkeypatch.setattr("src.plugins.registry._registry", value)
    return value


def _mcp_export():
    pytest.importorskip("mcp")
    from src.mcp_server import _build_mcp_server
    from tests.test_mcp_state_effects import assert_ok, call

    return assert_ok(call(_build_mcp_server(), "export_backup"), "export_backup")


@pytest.mark.parametrize("plugin_id", ["fixture", "fixture:office"])
def test_assistant_backup_uses_plugin_schema_and_keeps_snapshot_content(registry, plugin_id, monkeypatch, tmp_path):
    from src.backup.service import BackupService

    path = tmp_path / "snapshot"
    path.mkdir()
    snapshot = {
        "plugins": {
            plugin_id: {
                "title": "Snapshot title",
                "credential": "FAKE-widget",
                "nested": {"secret": "FAKE-nested", "public": "visible"},
                "sources": [{"token": "FAKE-array", "label": "visible"}],
                "api_key": "FAKE-legacy",
            }
        },
        "ai_providers": {"providers": [_provider()]},
    }
    (path / "config.json").write_text(json.dumps(snapshot))
    monkeypatch.setattr("src.backup.get_backup_service", lambda: BackupService(path))
    cm = get_config_manager()
    cm.set_plugin_config(plugin_id, {"title": "Live title"})
    before = copy.deepcopy(snapshot)
    result = _mcp_export()
    config = result["data"]["config"]
    assert config["plugins"][plugin_id] == {
        "title": "Snapshot title",
        "credential": "***",
        "nested": {"secret": "***", "public": "visible"},
        "sources": [{"token": "***", "label": "visible"}],
        "api_key": "***",
    }
    assert config["ai_providers"]["providers"][0]["headers"]["Authorization"] == "***"
    assert "FAKE-" not in json.dumps(result)
    assert json.loads((path / "config.json").read_text()) == before
    assert BackupService(path).build_backup()["data"]["config"] == before


@pytest.mark.parametrize("state", ["missing", "uninitialized", "invalid"])
def test_assistant_backup_withholds_plugin_config_without_schema(state, registry, monkeypatch, tmp_path):
    from src.backup.service import BackupService

    plugin_id = "unknown" if state == "missing" else "fixture"
    if state == "uninitialized":
        monkeypatch.setattr("src.plugins.registry._registry", None)
        monkeypatch.setattr(
            "src.plugins.registry.PluginRegistry.initialize", lambda *_: pytest.fail("Read must not initialize plugins")
        )
    elif state == "invalid":
        registry._manifests["fixture"].settings_schema = None
    monkeypatch.setattr(BackupService, "_collect_installed_plugins", lambda *_: [])
    snapshot = {"plugins": {plugin_id: {"arbitrary": "FAKE-unknown"}}}
    (tmp_path / "config.json").write_text(json.dumps(snapshot))
    monkeypatch.setattr("src.backup.get_backup_service", lambda: BackupService(tmp_path))
    result = _mcp_export()
    assert result["data"]["config"]["plugins"][plugin_id] == {}
    assert "FAKE-unknown" not in json.dumps(result)


@pytest.mark.parametrize("draft_has_id", [True, False])
def test_provider_draft_probe_restores_header_echo_without_persisting(client, monkeypatch, draft_has_id):
    cm = get_config_manager()
    cm.set_ai_providers({"providers": [_provider()]})
    before = cm.get_all()
    seen = []

    async def probe(provider, **_kwargs):
        seen.append(copy.deepcopy(provider))
        return {"ok": True, "message": "Configured"}

    monkeypatch.setattr("src.ai.generator.test_provider", probe)
    draft = _provider(headers={"Authorization": "***"}, api_key="***", name="Unsaved title")
    if not draft_has_id:
        draft.pop("id")
    response = client.post("/settings/ai/test", json={"provider_id": "first", "provider": draft})
    assert response.status_code == 200
    assert seen[0]["headers"]["Authorization"] == "Bearer FAKE-header-first"
    assert seen[0]["api_key"] == "FAKE-api-first"
    assert seen[0]["name"] == "Unsaved title"
    assert cm.get_all() == before


def test_provider_draft_probe_refuses_unresolved_header_before_external_request(client, monkeypatch):
    cm = get_config_manager()
    cm.set_ai_providers({"providers": [_provider()]})
    seen = []

    async def probe(provider, **_kwargs):
        seen.append(provider)
        return {"ok": True, "message": "Configured"}

    monkeypatch.setattr("src.ai.generator.test_provider", probe)
    response = client.post(
        "/settings/ai/test",
        json={"provider_id": "first", "provider": _provider("new", headers={"Authorization": "***"})},
    )
    assert response.status_code == 400
    assert seen == []


def test_duplicate_incoming_provider_ids_cannot_copy_header_echoes(client):
    cm = get_config_manager()
    cm.set_ai_providers({"providers": [_provider()]})
    before = cm.get_all()
    response = client.put(
        "/settings/ai",
        json={"providers": [_provider(headers={"Authorization": "***"}), _provider(headers={"Authorization": "***"})]},
    )
    assert response.status_code == 400
    assert cm.get_all() == before


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "properties": {"tokens": {"type": "object", "additionalProperties": {"secret": True}}}},
        {"type": "object", "patternProperties": {".*": {"secret": True}}},
        {"allOf": [{"properties": {"arbitrary": {"secret": True}}}]},
        {"$defs": {"private": {"secret": True}}, "$ref": "#/$defs/private"},
    ],
)
def test_assistant_backup_withholds_unsupported_secret_schema(registry, monkeypatch, tmp_path, schema):
    from src.backup.service import BackupService

    registry._manifests["fixture"].settings_schema = schema
    snapshot = {"plugins": {"fixture": {"arbitrary": "FAKE-unknown", "tokens": {"one": "FAKE-one"}}}}
    (tmp_path / "config.json").write_text(json.dumps(snapshot))
    monkeypatch.setattr("src.backup.get_backup_service", lambda: BackupService(tmp_path))
    result = _mcp_export()
    assert result["data"]["config"]["plugins"]["fixture"] == {}
    assert "FAKE-" not in json.dumps(result)


def test_assistant_backup_withholds_contains_schema_secrets(registry, monkeypatch, tmp_path):
    from src.backup.service import BackupService

    registry._manifests["fixture"].settings_schema = {
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "contains": {"type": "object", "properties": {"credential": {"secret": True}}},
            }
        },
    }
    snapshot = {"plugins": {"fixture": {"entries": [{"credential": "FAKE-contains"}]}}}
    (tmp_path / "config.json").write_text(json.dumps(snapshot))
    monkeypatch.setattr("src.backup.get_backup_service", lambda: BackupService(tmp_path))
    result = _mcp_export()
    assert result["data"]["config"]["plugins"]["fixture"] == {}
    assert "FAKE-contains" not in json.dumps(result)
