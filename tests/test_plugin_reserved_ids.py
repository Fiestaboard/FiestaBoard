"""Plugin ids the template grammar reserves, and the variable ``format`` field (plan D19).

``{{red:HOT}}`` is a colour span and ``{{icon:sun}}`` an icon, so a plugin
called ``red`` or ``icon`` could never have its variables addressed. Colour
names, tile codes 63-71 and ``icon`` are therefore reserved plugin ids.
A variable may declare ``"format": "markup"`` to pass its value through the
data neutraliser untouched; any other value is an error.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from src.markup import RESERVED_PLUGIN_IDS
from src.plugins.manifest import PluginManifest, validate_manifest

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("validate_plugins", ROOT / "scripts" / "validate_plugins.py")
validate_plugins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_plugins)

# Ids that are valid identifiers, so only the reservation can reject them.
NAMED_RESERVED = sorted(i for i in RESERVED_PLUGIN_IDS if i[0].isalpha())


def _manifest(**extra) -> dict:
    return {"id": "demo", "name": "Demo", "version": "1.0.0", **extra}


@pytest.mark.parametrize("plugin_id", NAMED_RESERVED)
def test_manifest_validator_rejects_a_reserved_id(plugin_id):
    ok, errors = validate_manifest(_manifest(id=plugin_id))
    assert not ok
    assert any("reserved" in e for e in errors)


@pytest.mark.parametrize("plugin_id", NAMED_RESERVED)
def test_validate_plugins_rejects_a_reserved_id(plugin_id):
    errors = validate_plugins.validate_manifest_schema(_manifest(id=plugin_id), plugin_id)
    assert any("reserved" in e for e in errors)


def test_validate_plugins_accepts_an_id_that_only_contains_a_colour():
    assert validate_plugins.validate_manifest_schema(_manifest(id="redwood"), "redwood") == []


def test_registry_validation_rejects_a_reserved_id():
    entry = {"id": "icon", "repository": "https://github.com/Fiestaboard/fiestaboard-plugin--icon"}
    assert any("reserved" in e for e in validate_plugins.validate_registry_entry(entry, verbose=False))


def test_no_bundled_plugin_uses_a_reserved_id():
    ids = {p.name for p in (ROOT / "plugins").iterdir() if p.is_dir()}
    assert ids & RESERVED_PLUGIN_IDS == set()


def test_no_registry_plugin_uses_a_reserved_id():
    registry = json.loads((ROOT / "plugin-registry.json").read_text(encoding="utf-8"))
    assert {p["id"] for p in registry["plugins"]} & RESERVED_PLUGIN_IDS == set()


def test_variable_format_markup_is_parsed():
    manifest = PluginManifest.from_dict(_manifest(variables={"simple": {"art": {"format": "markup"}}}))
    assert manifest.variables.metadata["art"].format == "markup"


def test_variable_format_defaults_to_text():
    manifest = PluginManifest.from_dict(_manifest(variables={"simple": {"art": {}}}))
    assert manifest.variables.metadata["art"].format == "text"


def test_array_item_field_format_is_parsed():
    variables = {"arrays": {"rows": {"item_fields": {"cells": {"format": "markup"}}}}}
    manifest = PluginManifest.from_dict(_manifest(variables=variables))
    assert manifest.variables.metadata["rows.*.cells"].format == "markup"


@pytest.mark.parametrize("fmt", ["markup", "text"])
def test_manifest_validator_accepts_a_known_format(fmt):
    ok, errors = validate_manifest(_manifest(variables={"simple": {"art": {"format": fmt}}}))
    assert ok, errors


def test_manifest_validator_rejects_an_unknown_format():
    ok, errors = validate_manifest(_manifest(variables={"simple": {"art": {"format": "html"}}}))
    assert not ok
    assert any("format" in e for e in errors)


def test_validate_plugins_rejects_an_unknown_format():
    errors = validate_plugins.validate_manifest_schema(
        _manifest(variables={"arrays": {"rows": {"item_fields": {"cells": {"format": "html"}}}}}), "demo"
    )
    assert any("format" in e for e in errors)
