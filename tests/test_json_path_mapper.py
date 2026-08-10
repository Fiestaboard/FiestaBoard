"""Manifest grammar for the ``json-path-mapper`` settings widget.

``json-path-mapper`` is the capability-named successor to
``generic-data-mapping-helper``: a field that lets the user probe an endpoint,
browse the JSON that comes back, and map paths in it onto template variables.
The two plugin-specific couplings the old widget carried — which sibling
properties describe the request, and which keys each mapping row is stored
under — are declared in ``ui:options`` instead of being hardcoded.
"""

from typing import Any

from src.plugins.manifest import (
    settings_schema_ui_warnings,
    validate_settings_schema_ui,
)


def _mapper_schema(ui_options: Any = None, widget: str = "json-path-mapper") -> dict:
    """A one-field settings schema whose field uses the mapper widget."""
    prop: dict = {"type": "array", "title": "Variable Mappings", "ui:widget": widget}
    if ui_options is not None:
        prop["ui:options"] = ui_options
    return {"type": "object", "properties": {"mappings": prop}}


def test_json_path_mapper_is_a_widget_this_core_renders():
    """The canonical name must not be reported as vocabulary from the future.

    An unknown ``ui:widget`` degrades a field to a plain input and files a
    warning; that is the right behaviour for a name core has never heard of and
    the wrong one for the name core is being taught here.
    """
    assert settings_schema_ui_warnings(_mapper_schema()) == []
    assert validate_settings_schema_ui(_mapper_schema()) == []


def test_probe_naming_a_request_part_this_core_does_not_know_is_an_error():
    """``probe`` maps *core's* request parts onto the plugin's field names.

    The left-hand side is core's vocabulary, so an unrecognised entry there
    cannot be grammar from a newer plugin — it is a typo, and the field would
    silently probe with that part missing.
    """
    errors = validate_settings_schema_ui(_mapper_schema({"probe": {"ur1": "endpoint"}}))

    assert errors == ["settings_schema.mappings: unknown ui:options.probe key 'ur1'"]


def test_keys_naming_a_row_field_this_core_does_not_know_is_an_error():
    """``keys`` renames the three inputs of a mapping row and nothing else."""
    errors = validate_settings_schema_ui(_mapper_schema({"keys": {"variable": "name", "fallback": "default"}}))

    assert errors == ["settings_schema.mappings: unknown ui:options.keys key 'fallback'"]


def test_a_probe_entry_that_is_not_a_property_name_is_an_error():
    """The right-hand side is a property name, so it has to be a real string.

    ``true`` would read as "yes, send a URL" and send nothing.
    """
    errors = validate_settings_schema_ui(_mapper_schema({"probe": {"url": True, "body": ""}}))

    assert errors == [
        "settings_schema.mappings: ui:options.probe.body must name a property, got ''",
        "settings_schema.mappings: ui:options.probe.url must name a property, got True",
    ]


def test_a_keys_entry_that_is_not_a_property_name_is_an_error():
    errors = validate_settings_schema_ui(_mapper_schema({"keys": {"path": 3}}))

    assert errors == ["settings_schema.mappings: ui:options.keys.path must name a property, got 3"]


def test_a_probe_block_that_is_not_an_object_is_an_error():
    """A list of field names is a plausible mistake and maps nothing."""
    errors = validate_settings_schema_ui(_mapper_schema({"probe": ["url", "format"]}))

    assert errors == ["settings_schema.mappings: ui:options.probe must be an object, got ['url', 'format']"]


def test_an_unknown_top_level_ui_options_key_only_warns():
    """Forward compatibility, unchanged for the new widget.

    A top-level key may be grammar a newer core added, and ``load_manifest``
    returns ``None`` on any error — so the plugin still loads and the key is
    named in the warning instead.
    """
    schema = _mapper_schema({"probe": {"url": "url"}, "row_template": "compact"})

    assert validate_settings_schema_ui(schema) == []
    assert settings_schema_ui_warnings(schema) == [
        "settings_schema.mappings: unknown ui:options key 'row_template' — ignored. Check the spelling; "
        "if the key is spelled correctly it was added in a newer FiestaBoard, and this core will "
        "ignore it until you update."
    ]


def test_probe_and_keys_are_not_themselves_reported_as_unknown():
    """The grammar this core just learned must not warn about itself."""
    schema = _mapper_schema({"probe": {"url": "endpoint"}, "keys": {"variable": "name"}})

    assert settings_schema_ui_warnings(schema) == []


def test_the_deprecated_widget_name_is_still_accepted():
    """No skew window in the old direction.

    A manifest still on ``generic-data-mapping-helper`` must keep loading, and
    keep getting the real widget, on a core that has learned the new name.
    Dropping the alias is a separate, later change.
    """
    schema = _mapper_schema(widget="generic-data-mapping-helper")

    assert settings_schema_ui_warnings(schema) == []
    assert validate_settings_schema_ui(schema) == []


def test_the_shipped_generic_data_mappings_field_validates_unchanged():
    """The manifest as published today, before its own migration lands."""
    schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "title": "Data URL"},
            "format": {"type": "string", "enum": ["json", "xml"], "default": "json"},
            "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
            "headers": {"type": "array", "items": {"type": "object"}},
            "body": {"type": "string"},
            "mappings": {
                "type": "array",
                "title": "Variable Mappings",
                "ui:widget": "generic-data-mapping-helper",
                "items": {
                    "type": "object",
                    "properties": {
                        "variable": {"type": "string"},
                        "path": {"type": "string"},
                        "default": {"type": "string", "default": ""},
                    },
                    "required": ["variable", "path"],
                },
                "default": [],
            },
        },
    }

    assert validate_settings_schema_ui(schema) == []
    assert settings_schema_ui_warnings(schema) == []


def test_a_ui_options_that_is_not_an_object_at_all_is_an_error():
    """There is no vocabulary to be forward-compatible about here."""
    errors = validate_settings_schema_ui(_mapper_schema("probe=url"))

    assert errors == ["settings_schema.mappings: ui:options must be an object"]
