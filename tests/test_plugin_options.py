"""Tests for the generic plugin options primitive.

Covers the three backend pieces of the contract:

1. ``src.plugins.manifest`` — settings-schema ``ui:widget``/``ui:options``
   validation and options-id collection.
2. ``src.plugins.base`` — the ``Option``/``OptionsRequest``/``OptionsResult``
   value types and the ``PluginBase.get_options`` hook.
3. ``src.plugins.registry`` — dispatch into a throwaway sandbox instance.
"""

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.plugins import manifest as manifest_module
from src.plugins.base import (
    Option,
    OptionsRequest,
    OptionsResult,
    OptionsUnavailable,
    PluginBase,
    PluginResult,
    TransitionPluginBase,
    normalise,
)
from src.plugins.loader import PluginLoader
from src.plugins.manifest import (
    collect_options_ids,
    settings_schema_ui_warnings,
    validate_manifest,
    validate_settings_schema_ui,
)
from src.plugins.registry import PluginRegistry


class _StubPlugin(PluginBase):
    """Minimal concrete plugin used to exercise the base-class contract."""

    @property
    def plugin_id(self) -> str:
        return "stub"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={})


def test_remote_options_widget_without_options_id_is_an_error():
    """``remote-options`` is meaningless without an id to dispatch on."""
    schema = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
            }
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert any("options_id" in e for e in errors), errors


def test_options_id_must_be_a_lowercase_snake_case_identifier():
    """``options_id`` ends up in a URL path segment — keep it boring."""
    schema = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "Stock-Symbols"},
            }
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert any("Stock-Symbols" in e for e in errors), errors


def test_unknown_key_inside_ui_options_is_a_warning_not_an_error():
    """Forward compatibility.

    Core cannot tell a typo from a key added by a newer core, and
    ``load_manifest`` returns ``None`` on *any* validation error — so treating
    an unrecognised key as fatal uninstalls the plugin from every user whose
    core is a release behind. It is reported, never fatal.
    """
    schema = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "cache_second": 60},
            }
        },
    }

    assert validate_settings_schema_ui(schema) == []


def test_an_unknown_ui_options_key_is_reported_as_a_warning():
    """The key still has to be *named* — a silently-ignored typo is how a
    picker ships without ever calling the plugin."""
    schema = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "group_by": "exchange"},
            }
        },
    }

    warnings = settings_schema_ui_warnings(schema)

    assert warnings == [
        "settings_schema.symbols: unknown ui:options key 'group_by' — ignored. Check the spelling; "
        "if the key is spelled correctly it was added in a newer FiestaBoard, and this core will "
        "ignore it until you update."
    ]


def test_multiple_requires_an_array_typed_field():
    """A multi-select needs somewhere to put the second selection."""
    schema = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "multiple": True},
            }
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert any("multiple" in e for e in errors), errors


def test_cache_seconds_outside_the_allowed_range_is_an_error():
    """Cache windows above an hour are almost always a units mistake."""
    schema = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "cache_seconds": 86400},
            }
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert any("cache_seconds" in e for e in errors), errors


@pytest.mark.parametrize("key", ["searchable", "server_search", "reorderable", "allow_custom"])
def test_boolean_ui_options_flags_are_accepted(key):
    """The widget's render flags are part of the grammar, not typos."""
    schema = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "multiple": True, key: True},
            }
        },
    }

    assert validate_settings_schema_ui(schema) == []


@pytest.mark.parametrize("key", ["searchable", "server_search", "reorderable", "allow_custom"])
def test_boolean_ui_options_flags_reject_a_non_boolean(key):
    """A truthy string renders the same as ``true`` in JS — say so in Python."""
    schema = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "multiple": True, key: "yes"},
            }
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert errors == [f"settings_schema.symbols: ui:options.{key} must be a boolean, got 'yes'"]


def test_placeholder_text_is_accepted():
    """The trigger's placeholder is the plugin author's copy, not core's."""
    schema = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "placeholder": "Search tickers"},
            }
        },
    }

    assert validate_settings_schema_ui(schema) == []


def test_placeholder_must_be_a_string():
    """Anything else reaches the DOM as ``[object Object]``."""
    schema = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "placeholder": 42},
            }
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert errors == ["settings_schema.symbol: ui:options.placeholder must be a string, got 42"]


def test_reorderable_requires_a_multi_select():
    """There is nothing to reorder in a single choice — the arrows never render."""
    schema = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "reorderable": True},
            }
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert errors == ["settings_schema.symbol: ui:options.reorderable requires ui:options.multiple"]


def test_server_search_implies_searchable_without_declaring_it():
    """The widget renders the box on ``searchable || server_search``, so asking
    for a second flag would be ceremony the UI does not need."""
    schema = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "server_search": True},
            }
        },
    }

    assert validate_settings_schema_ui(schema) == []


def test_server_search_contradicting_an_explicit_searchable_false_is_an_error():
    """``searchable: false`` here is a declaration the widget will ignore, and a
    silently-ignored declaration is exactly what the unknown-key rule prevents."""
    schema = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "server_search": True, "searchable": False},
            }
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert errors == [
        "settings_schema.symbol: ui:options.server_search implies ui:options.searchable, got searchable=False"
    ]


def test_depends_on_must_name_a_real_property():
    """A dangling dependency means the picker never unlocks."""
    schema = {
        "type": "object",
        "properties": {
            "agency": {"type": "string"},
            "stop": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "stops", "depends_on": ["agenncy"]},
            },
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert any("agenncy" in e for e in errors), errors


def test_depends_on_may_reference_a_root_property_from_a_nested_field():
    """Array rows routinely depend on the top-level account/agency setting."""
    schema = {
        "type": "object",
        "properties": {
            "agency": {"type": "string"},
            "routes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "stop": {
                            "type": "string",
                            "ui:widget": "remote-options",
                            "ui:options": {"options_id": "stops", "depends_on": ["agency"]},
                        }
                    },
                },
            },
        },
    }

    assert validate_settings_schema_ui(schema) == []


def test_labels_field_naming_a_sibling_of_a_multi_select_is_accepted():
    """``labels_field`` lets a multi-select carry a per-choice display name.

    The names land in the *sibling* property it points at, keyed by option
    value, so the sibling has to be declared alongside the picker.
    """
    schema = {
        "type": "object",
        "properties": {
            "ride_ids": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "rides", "multiple": True, "labels_field": "custom_names"},
            },
            "custom_names": {"type": "object"},
        },
    }

    assert validate_settings_schema_ui(schema) == []


def test_labels_field_must_be_a_string():
    """It is a property *name*; anything else cannot be looked up at all."""
    schema = {
        "type": "object",
        "properties": {
            "ride_ids": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "rides", "multiple": True, "labels_field": True},
            },
            "custom_names": {"type": "object"},
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert errors == ["settings_schema.ride_ids: ui:options.labels_field must be a string, got True"]


def test_labels_field_must_name_a_declared_sibling_property():
    """The names are written into that sibling, so a typo silently discards
    every display name the user types."""
    schema = {
        "type": "object",
        "properties": {
            "ride_ids": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "rides", "multiple": True, "labels_field": "custom_nmaes"},
            },
            "custom_names": {"type": "object"},
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert errors == ["settings_schema.ride_ids: ui:options.labels_field references unknown property 'custom_nmaes'"]


def test_labels_field_sibling_is_resolved_inside_the_array_item_not_at_the_root():
    """A picker on an array row writes into *that row*, so a same-named root
    property is not the sibling it means."""
    schema = {
        "type": "object",
        "properties": {
            "custom_names": {"type": "object"},
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ride_ids": {
                            "type": "array",
                            "ui:widget": "remote-options",
                            "ui:options": {"options_id": "rides", "multiple": True, "labels_field": "custom_names"},
                        }
                    },
                },
            },
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert errors == [
        "settings_schema.rows.items.ride_ids: ui:options.labels_field references unknown property 'custom_names'"
    ]


def test_labels_field_without_multiple_is_an_error():
    """A single choice has nothing to key a map of names by — the field's own
    title already names it, and the widget renders no label input at all."""
    schema = {
        "type": "object",
        "properties": {
            "ride_id": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "rides", "labels_field": "custom_names"},
            },
            "custom_names": {"type": "object"},
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert errors == ["settings_schema.ride_id: ui:options.labels_field requires ui:options.multiple"]


def test_validation_recurses_into_array_item_properties():
    """Most real pickers live on array item fields, not at the root."""
    schema = {
        "type": "object",
        "properties": {
            "routes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"stop": {"type": "string", "ui:widget": "remote-options"}},
                },
            }
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert any("routes.items.stop" in e for e in errors), errors


def test_duplicate_options_id_across_the_schema_is_an_error():
    """``options_id`` is the dispatch key — two fields cannot share one."""
    schema = {
        "type": "object",
        "properties": {
            "home": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "stops"},
            },
            "work": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "stops"},
            },
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert any("duplicate" in e.lower() and "stops" in e for e in errors), errors


def test_collect_options_ids_finds_ids_nested_in_array_items():
    """The loader needs every id, including ones on array item fields."""
    schema = {
        "type": "object",
        "properties": {
            "agency": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "agencies"},
            },
            "routes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "stop": {
                            "type": "string",
                            "ui:widget": "remote-options",
                            "ui:options": {"options_id": "stops"},
                        }
                    },
                },
            },
        },
    }

    assert collect_options_ids(schema) == {"agencies", "stops"}


@pytest.mark.parametrize(
    "widget",
    ["stock-symbol-picker", "muni-stop-picker", "lyft-bikeshare-station-picker"],
)
def test_unknown_ui_widget_warns_but_the_manifest_still_validates(widget, caplog):
    """Backward-compat guard.

    ``load_manifest`` returns ``None`` on *any* validation error, so promoting
    an unrecognised ``ui:widget`` to an error would stop already-installed
    plugins from loading at all. Three shipped plugins declare picker widgets
    core never implemented; they must keep working.
    """
    manifest = {
        "id": "stocks",
        "name": "Stocks",
        "version": "1.0.0",
        "settings_schema": {
            "type": "object",
            "properties": {"symbols": {"type": "array", "ui:widget": widget}},
        },
    }

    with caplog.at_level(logging.WARNING, logger="src.plugins.manifest"):
        is_valid, errors = validate_manifest(manifest)

    assert is_valid, errors
    assert errors == []
    assert any(widget in record.message for record in caplog.records), caplog.text


def test_validate_manifest_rejects_a_malformed_remote_options_field():
    """Only a field that explicitly opts into ``remote-options`` is held to the
    strict rules — and there the manifest must fail validation outright."""
    manifest = {
        "id": "muni",
        "name": "Muni",
        "version": "1.0.0",
        "settings_schema": {
            "type": "object",
            "properties": {"stop": {"type": "string", "ui:widget": "remote-options"}},
        },
    }

    is_valid, errors = validate_manifest(manifest)

    assert not is_valid
    assert any("options_id" in e for e in errors), errors


# Every ui:options mistake that must keep costing the plugin its load.
#
# Forward compatibility is for keys this core has never *heard of* — core
# cannot tell those from grammar a newer core added. Everything below is
# either a key core knows carrying a value core knows is wrong, or a broken
# reference core can resolve for itself. There is no newer-core reading of
# any of them, so they stay fatal and this table is the fence around that.
_STILL_FATAL_SETTINGS_SCHEMAS: dict[str, dict[str, Any]] = {
    "cache_seconds_is_not_an_integer": {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "cache_seconds": "soon"},
            }
        },
    },
    "labels_field_is_not_a_string": {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "multiple": True, "labels_field": True},
            },
            "custom_names": {"type": "object"},
        },
    },
    "multiple_is_not_a_boolean": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "multiple": "yes"},
            }
        },
    },
    "remote_options_without_an_options_id": {
        "type": "object",
        "properties": {"symbols": {"type": "array", "ui:widget": "remote-options"}},
    },
    "depends_on_names_a_property_that_does_not_exist": {
        "type": "object",
        "properties": {
            "stop": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "stops", "depends_on": ["agencyy"]},
            },
            "agency": {"type": "string"},
        },
    },
    "labels_field_without_multiple": {
        "type": "object",
        "properties": {
            "ride_id": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "rides", "labels_field": "custom_names"},
            },
            "custom_names": {"type": "object"},
        },
    },
    "labels_field_names_a_non_sibling": {
        "type": "object",
        "properties": {
            "ride_ids": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "rides", "multiple": True, "labels_field": "custom_nmaes"},
            },
            "custom_names": {"type": "object"},
        },
    },
    "duplicate_options_id_across_the_schema": {
        "type": "object",
        "properties": {
            "home": {"type": "string", "ui:widget": "remote-options", "ui:options": {"options_id": "stops"}},
            "work": {"type": "string", "ui:widget": "remote-options", "ui:options": {"options_id": "stops"}},
        },
    },
    "multiple_true_on_a_non_array_field": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "multiple": True},
            }
        },
    },
    "ui_options_is_not_an_object_at_all": {
        "type": "object",
        "properties": {"symbols": {"type": "array", "ui:widget": "remote-options", "ui:options": "symbols"}},
    },
}


@pytest.mark.parametrize("case", sorted(_STILL_FATAL_SETTINGS_SCHEMAS))
def test_a_known_ui_options_mistake_still_stops_the_manifest_loading(case):
    """Guard against this being 'simplified' into blanket leniency.

    Unknown *keys* became a warning so a plugin built for a newer core keeps
    working on an older one. That reasoning does not reach any of these: each
    is a value or a reference this core can judge on its own, and letting one
    through ships a picker that silently does the wrong thing.
    """
    manifest = {
        "id": "guard",
        "name": "Guard",
        "version": "1.0.0",
        "settings_schema": _STILL_FATAL_SETTINGS_SCHEMAS[case],
    }

    is_valid, errors = validate_manifest(manifest)

    assert not is_valid, f"{case} must fail validation outright"
    assert errors, f"{case} must say why"


# ── src.plugins.base ────────────────────────────────────────────────────


def test_default_get_options_raises_not_implemented():
    """Plugins opt in; the base class must not pretend to have a catalog."""
    plugin = _StubPlugin({"id": "stub", "name": "Stub", "version": "1.0.0"})

    with pytest.raises(NotImplementedError):
        plugin.get_options(OptionsRequest(options_id="anything"))


def test_normalise_wraps_a_bare_option_list_in_a_result():
    """The ergonomic path: small catalogs just return a list."""
    options = [Option(value="ktm", label="KT Muni Metro")]

    result = normalise(options)

    assert isinstance(result, OptionsResult)
    assert result.options == options
    assert result.has_more is False


def test_option_rejects_a_non_scalar_value():
    """``value`` is written straight into config.json — dicts do not belong."""
    with pytest.raises(TypeError):
        Option(value={"id": "ktm"}, label="KT Muni Metro")


def test_normalise_passes_an_options_result_through_unchanged():
    """Paging plugins build the result themselves; do not rebuild it."""
    result = OptionsResult(options=[Option(value="ktm", label="KT")], has_more=True, cursor="page-2")

    assert normalise(result) is result


# ── src.plugins.registry ────────────────────────────────────────────────


class _OptionsPlugin(PluginBase):
    """Records every interaction so tests can assert on the sandbox lifecycle."""

    def __init__(self, manifest, plugin_id="stocks"):
        self._id = plugin_id
        super().__init__(manifest)
        self.requests: list[OptionsRequest] = []
        self.config_changes: list[tuple[dict, dict]] = []
        self.cleaned_up = False
        self.raise_on_options: Exception | None = None

    @property
    def plugin_id(self) -> str:
        return self._id

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={})

    def get_options(self, request: OptionsRequest):
        self.requests.append(request)
        if self.raise_on_options is not None:
            raise self.raise_on_options
        return [Option(value=self.config.get("account", "AAPL"), label="Apple")]

    def on_config_change(self, old_config, new_config) -> None:
        self.config_changes.append((old_config, new_config))

    def cleanup(self) -> None:
        self.cleaned_up = True


@pytest.fixture
def options_registry():
    """Registry holding one live ``stocks`` plugin plus a sandbox factory."""
    manifest_raw = {"id": "stocks", "name": "Stocks", "version": "1.0.0"}
    sandboxes: list[_OptionsPlugin] = []
    control: dict[str, Any] = {"sandbox_error": None}

    def _create_instance(base_id):
        sandbox = _OptionsPlugin(manifest_raw, plugin_id=base_id)
        sandbox.raise_on_options = control["sandbox_error"]
        sandboxes.append(sandbox)
        return sandbox

    loader = MagicMock()
    loader.load_all_plugins.return_value = {}
    loader.create_instance.side_effect = _create_instance

    with patch("src.plugins.registry.PluginLoader", return_value=loader):
        registry = PluginRegistry(plugins_dir=Path("/fake/plugins"))

    live = _OptionsPlugin(manifest_raw)
    registry._plugins["stocks"] = live
    registry._configs["stocks"] = {"api_key": "test_key"}
    registry._enabled["stocks"] = True

    return SimpleNamespace(registry=registry, live=live, sandboxes=sandboxes, loader=loader, control=control)


def test_get_plugin_options_calls_the_plugin_with_the_requested_options_id(options_registry):
    """The request the plugin sees is the one the caller asked for."""
    request = OptionsRequest(options_id="ignored", parent={"exchange": "NASDAQ"}, query="app", limit=25)

    result = options_registry.registry.get_plugin_options("stocks", "symbols", request)

    (sandbox,) = options_registry.sandboxes
    (seen,) = sandbox.requests
    assert seen.options_id == "symbols"
    assert seen.parent == {"exchange": "NASDAQ"}
    assert seen.query == "app"
    assert seen.limit == 25
    assert isinstance(result, OptionsResult)
    assert [o.label for o in result.options] == ["Apple"]


def test_options_use_a_fresh_sandbox_and_never_disturb_the_live_instance(options_registry):
    """HA-MQTT-teardown regression guard.

    Assigning to the live instance's ``config`` property fires ``clear_cache()``
    and ``on_config_change()``. The Home Assistant plugin tears down its running
    MQTT statestream listener in that hook — doing it on every keystroke in a
    settings search box is unacceptable. Options must run on a throwaway
    instance, so the live one must be left completely untouched.
    """
    live = options_registry.live

    options_registry.registry.get_plugin_options("stocks", "symbols", OptionsRequest(options_id="symbols"))

    assert live.config_changes == [], "live instance's on_config_change fired"
    assert live.requests == [], "live instance served the options request"
    assert live.cleaned_up is False, "live instance was cleaned up"
    assert len(options_registry.sandboxes) == 1
    assert options_registry.sandboxes[0] is not live
    options_registry.loader.create_instance.assert_called_once_with("stocks")


def test_sandbox_is_cleaned_up_even_when_get_options_raises(options_registry):
    """A plugin that opens a socket before failing must not leak it."""
    options_registry.control["sandbox_error"] = OptionsUnavailable("no API key configured")

    with pytest.raises(OptionsUnavailable):
        options_registry.registry.get_plugin_options("stocks", "symbols", OptionsRequest(options_id="symbols"))

    (sandbox,) = options_registry.sandboxes
    assert sandbox.cleaned_up is True


def test_instance_key_resolves_class_from_base_id_and_config_from_the_full_key(options_registry):
    """``stocks:growth`` shares the ``stocks`` class but has its own settings."""
    registry = options_registry.registry
    registry._plugins["stocks:growth"] = _OptionsPlugin(
        {"id": "stocks", "name": "Stocks", "version": "1.0.0"}, plugin_id="stocks"
    )
    registry._configs["stocks:growth"] = {"account": "growth"}

    result = registry.get_plugin_options("stocks:growth", "symbols", OptionsRequest(options_id="symbols"))

    options_registry.loader.create_instance.assert_called_once_with("stocks")
    (sandbox,) = options_registry.sandboxes
    assert sandbox.config == {"account": "growth"}
    assert [o.value for o in result.options] == ["growth"]


def test_options_work_while_the_plugin_is_still_disabled(options_registry):
    """You browse the catalog *in order to* configure the plugin — before
    enabling it. The stored config is applied either way."""
    registry = options_registry.registry
    registry._enabled["stocks"] = False
    registry._configs["stocks"] = {"account": "AMZN"}

    result = registry.get_plugin_options("stocks", "symbols", OptionsRequest(options_id="symbols"))

    assert [o.value for o in result.options] == ["AMZN"]


def test_transition_plugin_has_no_options(options_registry):
    """Transitions animate sends; there is no catalog to browse."""

    class _Transition(TransitionPluginBase):
        @property
        def plugin_id(self) -> str:
            return "typewriter"

        def generate_frames(self, from_grid, to_grid, device, config):
            yield from ()

    registry = options_registry.registry
    registry._plugins["typewriter"] = _Transition({"id": "typewriter", "plugin_type": "transition"})

    with pytest.raises(NotImplementedError):
        registry.get_plugin_options("typewriter", "anything", OptionsRequest(options_id="anything"))


def test_sandbox_config_bypasses_the_property_setter(options_registry):
    """``_config`` is assigned directly so no config-change hook fires at all —
    not on the live instance, and not on the sandbox either."""
    options_registry.registry.get_plugin_options("stocks", "symbols", OptionsRequest(options_id="symbols"))

    (sandbox,) = options_registry.sandboxes
    assert sandbox.config == {"api_key": "test_key"}
    assert sandbox.config_changes == []


def test_unknown_plugin_raises_key_error(options_registry):
    """An options request for a plugin that is not loaded is a caller bug."""
    with pytest.raises(KeyError):
        options_registry.registry.get_plugin_options("nope", "symbols", OptionsRequest(options_id="symbols"))


# ── src.plugins.loader ──────────────────────────────────────────────────


def _write_options_plugin(
    tmp_path: Path,
    plugin_id: str,
    *,
    implements_get_options: bool,
    ui_options: dict[str, Any] | None = None,
) -> None:
    """Write a plugin whose manifest declares a remote-options field."""
    plugin_dir = tmp_path / plugin_id
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": plugin_id,
                "name": "Stocks",
                "version": "1.0.0",
                "settings_schema": {
                    "type": "object",
                    "properties": {
                        "symbols": {
                            "type": "array",
                            "ui:widget": "remote-options",
                            "ui:options": ui_options if ui_options is not None else {"options_id": "symbols"},
                        }
                    },
                },
            }
        )
    )
    get_options_src = (
        """
    def get_options(self, request):
        return []
"""
        if implements_get_options
        else ""
    )
    (plugin_dir / "__init__.py").write_text(
        f'''"""Test plugin."""
from src.plugins.base import PluginBase, PluginResult


class StocksPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "{plugin_id}"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={{}})
{get_options_src}'''
    )


def test_loader_flags_a_manifest_that_promises_options_without_implementing_them(tmp_path):
    """Non-fatal: the plugin still loads, but the mismatch surfaces in
    ``GET /plugins/errors`` instead of failing silently at pick time."""
    _write_options_plugin(tmp_path, "brokenopts", implements_get_options=False)
    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])

    plugin = loader.load_plugin("brokenopts")

    assert plugin is not None, "the plugin must still load"
    assert any("get_options" in e for e in loader.load_errors.get("brokenopts", [])), loader.load_errors


def test_loader_loads_a_plugin_using_an_unknown_ui_options_key_and_reports_it(tmp_path):
    """A key from a newer core must not cost the user the whole plugin.

    It is still reported through ``GET /plugins/errors`` so the author who
    typed ``cache_second`` finds out, rather than shipping a picker that
    silently ignores half its configuration.
    """
    _write_options_plugin(
        tmp_path,
        "futurekeys",
        implements_get_options=True,
        ui_options={"options_id": "symbols", "group_by": "exchange"},
    )
    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])

    plugin = loader.load_plugin("futurekeys")

    assert plugin is not None, "the plugin must still load"
    assert any("group_by" in e for e in loader.load_errors.get("futurekeys", [])), loader.load_errors


_DISNEY_RIDE_PICKER = {
    "type": "object",
    "properties": {
        "ride_ids": {
            "type": "array",
            "ui:widget": "remote-options",
            "ui:options": {
                "options_id": "rides",
                "multiple": True,
                "searchable": True,
                "labels_field": "custom_names",
            },
        },
        "custom_names": {"type": "object"},
    },
}


def test_a_manifest_using_a_ui_options_key_from_a_newer_core_still_loads(tmp_path, monkeypatch):
    """The Disney incident, reproduced.

    ``disney-parks-times`` adopted ``labels_field`` in the release that core
    8.25.0 introduced it. On 8.24.x that key did not exist, and an unknown
    ``ui:options`` key was fatal — so the hourly plugin auto-update would have
    deleted the plugin from every board still on the older image. Core updates
    are a manual image pull, so that is a lot of boards.

    An older core is simulated by taking the key back out of the grammar.
    """
    monkeypatch.setattr(manifest_module, "UI_OPTIONS_KEYS", manifest_module.UI_OPTIONS_KEYS - {"labels_field"})
    plugin_dir = tmp_path / "disneyparks"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "disneyparks",
                "name": "Disney Parks",
                "version": "1.0.0",
                "settings_schema": _DISNEY_RIDE_PICKER,
            }
        )
    )
    (plugin_dir / "__init__.py").write_text(
        '''"""Test plugin."""
from src.plugins.base import PluginBase, PluginResult


class DisneyPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "disneyparks"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={})

    def get_options(self, request):
        return []
'''
    )
    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])

    plugin = loader.load_plugin("disneyparks")

    assert plugin is not None, "the plugin must survive a core that predates the key"
    assert any("labels_field" in e for e in loader.load_errors.get("disneyparks", [])), loader.load_errors


def test_a_field_using_a_newer_cores_key_still_works_minus_that_capability(monkeypatch):
    """Degrade, do not disappear.

    The ride picker keeps dispatching to ``get_options`` and keeps its
    multi-select; only the per-ride custom labels — the part the older core
    cannot render — are missing.
    """
    monkeypatch.setattr(manifest_module, "UI_OPTIONS_KEYS", manifest_module.UI_OPTIONS_KEYS - {"labels_field"})

    assert validate_settings_schema_ui(_DISNEY_RIDE_PICKER) == []
    assert collect_options_ids(_DISNEY_RIDE_PICKER) == {"rides"}


def test_loader_stays_quiet_when_the_plugin_implements_get_options(tmp_path):
    """No false alarm for plugins that do hold up their end."""
    _write_options_plugin(tmp_path, "goodopts", implements_get_options=True)
    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])

    plugin = loader.load_plugin("goodopts")

    assert plugin is not None
    assert loader.load_errors.get("goodopts", []) == []


def test_a_failing_sandbox_cleanup_does_not_fail_the_request(options_registry):
    """Cleanup is best-effort — a sloppy teardown must not break the picker."""

    def _boom():
        raise RuntimeError("teardown exploded")

    original = options_registry.loader.create_instance.side_effect

    def _create_instance(base_id):
        sandbox = original(base_id)
        sandbox.cleanup = _boom
        return sandbox

    options_registry.loader.create_instance.side_effect = _create_instance

    result = options_registry.registry.get_plugin_options("stocks", "symbols", OptionsRequest(options_id="symbols"))

    assert [o.label for o in result.options] == ["Apple"]


def test_missing_plugin_class_raises_key_error(options_registry):
    """The class can go missing after an uninstall races the settings dialog."""
    options_registry.loader.create_instance.side_effect = None
    options_registry.loader.create_instance.return_value = None

    with pytest.raises(KeyError):
        options_registry.registry.get_plugin_options("stocks", "symbols", OptionsRequest(options_id="symbols"))


def test_non_object_ui_options_is_reported_once():
    """A scalar ``ui:options`` is a schema mistake, not a crash."""
    schema = {
        "type": "object",
        "properties": {"symbols": {"type": "array", "ui:widget": "remote-options", "ui:options": "symbols"}},
    }

    errors = validate_settings_schema_ui(schema)

    assert any("ui:options must be an object" in e for e in errors), errors


def test_validation_recurses_into_nested_object_properties():
    """Grouped settings nest a plain ``properties`` block, not ``items``."""
    schema = {
        "type": "object",
        "properties": {
            "advanced": {
                "type": "object",
                "properties": {"stop": {"type": "string", "ui:widget": "remote-options"}},
            }
        },
    }

    errors = validate_settings_schema_ui(schema)

    assert any("advanced.stop" in e for e in errors), errors


def test_a_non_object_property_is_skipped_rather_than_crashing():
    """Hand-edited manifests contain surprises; do not raise on them."""
    schema = {"type": "object", "properties": {"broken": "not-a-schema"}}

    assert validate_settings_schema_ui(schema) == []


def test_collect_options_ids_ignores_a_field_with_no_usable_id():
    """A malformed field is a validation error, not a phantom provider."""
    schema = {
        "type": "object",
        "properties": {"stop": {"type": "string", "ui:widget": "remote-options", "ui:options": {}}},
    }

    assert collect_options_ids(schema) == set()


def test_draft_config_is_layered_over_the_stored_config(options_registry):
    """The picker has to work *before* Save — that is the whole point of a
    settings dialog. Unsaved form values win over what is on disk, and keys the
    form did not touch keep their stored values."""
    options_registry.registry._configs["stocks"] = {"api_key": "stored_key", "account": "STORED"}

    options_registry.registry.get_plugin_options(
        "stocks",
        "symbols",
        OptionsRequest(options_id="symbols"),
        draft_config={"account": "DRAFT"},
    )

    (sandbox,) = options_registry.sandboxes
    assert sandbox.config == {"api_key": "stored_key", "account": "DRAFT"}


def test_no_draft_config_leaves_the_stored_config_alone(options_registry):
    """Opening a dialog without editing anything must not change what the
    sandbox sees."""
    options_registry.registry.get_plugin_options("stocks", "symbols", OptionsRequest(options_id="symbols"))

    (sandbox,) = options_registry.sandboxes
    assert sandbox.config == {"api_key": "test_key"}
