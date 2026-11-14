"""Schema-aware plugin projection and stored-only round-trip behavior."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.config_manager import ConfigManager
from src.plugins.service import PluginConfigInvalid, PluginService

SCHEMA = {
    "properties": {
        "credential": {"secret": True},
        "nested": {"properties": {"opaque": {"ui:widget": "password"}}},
        "rows": {"items": {"properties": {"credential": {"secret": True}}}},
        "tokens": {"items": {"secret": True}},
    }
}
STORED = {
    "credential": "cx-FAKE-root",
    "nested": {"opaque": "cx-FAKE-nested"},
    "rows": [{"id": "a", "credential": "cx-FAKE-a"}, {"id": "b", "credential": "cx-FAKE-b"}],
    "api_key": "cx-FAKE-legacy",
    "visible": "hello",
}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    cm = ConfigManager(str(tmp_path / "config.json"))
    reg = Mock()
    reg.get_manifest.side_effect = lambda key: (
        SimpleNamespace(settings_schema=SCHEMA, plugin_type="data") if key == "probe" else None
    )
    reg.validate_plugin_config.return_value = []
    reg.apply_stored_config.return_value = []
    reg.set_plugin_config.return_value = []
    import src.plugins.registry

    monkeypatch.setattr(src.plugins.registry, "_registry", reg)
    svc = PluginService(registry=reg, config_manager=cm, reset_display=lambda: None, reset_template=lambda: None)
    return cm, reg, svc


@pytest.mark.parametrize("key", ["probe", "probe:office"])
def test_recursive_projection_and_roundtrip(setup, key):
    cm, _, svc = setup
    cm.set_plugin_config(key, deepcopy(STORED))
    masked = svc.mask_config(cm.get_plugin_config(key), key)
    assert masked == {
        "credential": "***",
        "nested": {"opaque": "***"},
        "rows": [{"id": "a", "credential": "***"}, {"id": "b", "credential": "***"}],
        "api_key": "***",
        "visible": "hello",
    }
    assert cm.get_all_masked()["plugins"][key] == masked
    assert cm.get_all_plugin_configs_masked()[key] == masked
    masked["rows"].reverse()
    result = svc.update_plugin_config(key, masked)
    assert result["credential"] == "***"
    saved = cm.get_plugin_config(key, include_env_overrides=False)
    assert saved["credential"] == STORED["credential"]
    assert saved["nested"] == STORED["nested"]
    assert saved["rows"] == list(reversed(STORED["rows"]))


@pytest.mark.parametrize("method", ["set_plugin_config", "update_plugin_config"])
def test_direct_persistence_restores_schema_secrets(setup, method):
    cm, _, _ = setup
    cm.set_plugin_config("probe", STORED)
    getattr(cm, method)("probe", {"credential": "***", "nested": {"opaque": "***"}})
    assert cm.get_plugin_config("probe")["credential"] == STORED["credential"]
    assert cm.get_plugin_config("probe")["nested"] == STORED["nested"]


@pytest.mark.parametrize("rows", [[{"id": "new", "credential": "***"}], [{"credential": "***"}]])
def test_unmatched_array_is_rejected_before_save_or_live_apply(setup, rows):
    cm, reg, svc = setup
    cm.set_plugin_config("probe", STORED)
    with pytest.raises(PluginConfigInvalid):
        svc.update_plugin_config("probe", {"rows": rows})
    assert cm.get_plugin_config("probe") == STORED
    reg.apply_stored_config.assert_not_called()


def test_signature_matching_ignores_nested_secret_values(setup):
    cm, _, svc = setup
    SCHEMA["properties"]["rows"]["items"]["properties"]["nested"] = SCHEMA["properties"]["nested"]
    try:
        cm.set_plugin_config("probe", {"rows": [{"url": "a", "nested": {"opaque": "cx-FAKE-a"}}]})
        svc.update_plugin_config("probe", {"rows": [{"url": "a", "nested": {"opaque": "***"}}]})
        assert cm.get_plugin_config("probe")["rows"][0]["nested"]["opaque"] == "cx-FAKE-a"
    finally:
        del SCHEMA["properties"]["rows"]["items"]["properties"]["nested"]


def test_missing_manifest_withholds_settings_without_initializing_registry(setup, monkeypatch):
    cm, _, svc = setup
    cm.set_plugin_config("gone", {"unknown": "cx-FAKE-unknown"})
    assert svc.mask_config(cm.get_plugin_config("gone"), "gone") == {}
    import src.plugins.registry

    monkeypatch.setattr(src.plugins.registry, "_registry", None)
    monkeypatch.setattr(src.plugins.registry, "get_plugin_registry", lambda: pytest.fail("must not initialize"))
    assert cm.get_all_masked()["plugins"]["gone"] == {}
    assert cm.get_all_plugin_configs_masked()["gone"] == {}


def test_environment_only_secret_is_not_persisted(setup, monkeypatch):
    cm, reg, svc = setup
    cm.set_plugin_config("probe", {"visible": "hello"})

    def overlay(key, cfg):
        cfg["credential"] = "cx-FAKE-env"

    monkeypatch.setattr(cm, "_apply_plugin_env_overlay", overlay)
    svc.update_plugin_config("probe", {"credential": "***", "visible": "changed"})
    assert cm.get_plugin_config("probe", include_env_overrides=False)["credential"] == ""
    assert reg.set_plugin_config.call_args.args[1]["credential"] == "cx-FAKE-env"


def test_secret_array_items_reject_ambiguous_sentinels(setup):
    cm, _, svc = setup
    cm.set_plugin_config("probe", {"tokens": ["cx-FAKE-one", "cx-FAKE-two"]})
    assert svc.mask_config(cm.get_plugin_config("probe"), "probe")["tokens"] == ["***", "***"]
    with pytest.raises(PluginConfigInvalid):
        svc.update_plugin_config("probe", {"tokens": ["***"]})
    assert cm.get_plugin_config("probe")["tokens"] == ["cx-FAKE-one", "cx-FAKE-two"]


@pytest.mark.parametrize("method", ["set_plugin_config", "update_plugin_config"])
def test_schema_lookup_precedes_config_lock(setup, method):
    cm, reg, _ = setup

    def manifest(key):
        assert not cm._file_lock._is_owned(), "registry lock must precede config lock"
        return SimpleNamespace(settings_schema=SCHEMA)

    reg.get_manifest.side_effect = manifest
    getattr(cm, method)("probe", {"credential": "cx-FAKE-value"})


def test_public_asterisk_text_is_not_a_secret_placeholder(setup):
    cm, _, svc = setup
    svc.update_plugin_config("probe", {"visible": "***"})
    assert cm.get_plugin_config("probe")["visible"] == "***"


def test_schema_secret_identity_cannot_select_another_rows_secret(setup):
    cm, reg, svc = setup
    schema = {
        "properties": {
            "rows": {
                "items": {
                    "properties": {
                        "id": {"secret": True},
                        "credential": {"secret": True},
                        "children": {"items": {"properties": {"opaque": {"secret": True}}}},
                    }
                }
            }
        }
    }
    reg.get_manifest.side_effect = lambda key: SimpleNamespace(settings_schema=schema, plugin_type="data")
    rows = [
        {
            "id": "cx-FAKE-id-a",
            "url": "a",
            "credential": "cx-FAKE-a",
            "children": [{"name": "n", "opaque": "cx-FAKE-child-a"}],
        },
        {
            "id": "cx-FAKE-id-b",
            "url": "b",
            "credential": "cx-FAKE-b",
            "children": [{"name": "n", "opaque": "cx-FAKE-child-b"}],
        },
    ]
    cm.set_plugin_config("probe", {"rows": rows})
    masked = svc.mask_config(cm.get_plugin_config("probe"), "probe")
    masked["rows"].reverse()
    svc.update_plugin_config("probe", masked)
    assert cm.get_plugin_config("probe")["rows"] == list(reversed(rows))
