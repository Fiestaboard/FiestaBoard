"""The board settings UI grammar (plan D13): ``ui:visible_when``, ``ui:sections``
and the core widgets ``mode-cards`` / ``tile-grid`` / ``device-picker``.

``ui:visible_when`` is evaluated in two places — Python validation of a
board's ``output_config`` and the web form — and the two must agree. The
vectors in ``web/src/lib/visible-when.cases.json`` are run by this module and
by ``web/src/lib/visible-when.test.ts``; a vector that passes on one side and
fails on the other is exactly the drift they exist to catch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.plugins.manifest import KNOWN_SETTINGS_WIDGETS, settings_schema_ui_warnings, validate_settings_schema_ui
from src.plugins.settings_ui import (
    DEVICE_PICKER_WIDGET,
    MODE_CARDS_WIDGET,
    TILE_GRID_WIDGET,
    condition_errors,
    is_visible,
    strip_hidden,
)

CASES = json.loads(
    (Path(__file__).parent.parent / "web" / "src" / "lib" / "visible-when.cases.json").read_text("utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_visible_when_vector(case):
    assert is_visible(case["when"], case["values"], case["properties"]) is case["visible"]


# --- what validation reports about a condition ---------------------------------------------------


FIELDS = {"mode": {"type": "string"}, "advanced": {"type": "boolean"}}


def test_a_well_formed_condition_has_no_errors():
    assert condition_errors({"any": [{"mode": ["local", "cloud"]}, {"not": {"advanced": True}}]}, FIELDS) == []


def test_a_condition_must_be_an_object():
    assert condition_errors("mode == local", FIELDS) == ["must be an object"]


def test_an_empty_condition_is_an_error():
    assert condition_errors({}, FIELDS) == ["must name at least one field, or be a 'not' / 'any'"]


def test_an_unknown_field_is_an_error():
    assert condition_errors({"colour": "red"}, FIELDS) == ["references unknown property 'colour'"]


def test_not_beside_fields_is_an_error():
    assert condition_errors({"not": {"mode": "x"}, "mode": "y"}, FIELDS) == ["'not' must be the only key"]


def test_any_must_be_a_non_empty_list():
    assert condition_errors({"any": []}, FIELDS) == ["'any' must be a non-empty array of conditions"]


def test_an_expected_value_must_be_a_scalar():
    assert condition_errors({"mode": {"is": "local"}}, FIELDS) == [
        "mode: expected a string, number, boolean or null, or an array of them"
    ]


# --- hidden fields are not validated -------------------------------------------------------------

SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["local", "cloud"], "default": "local"},
        "host": {"type": "string", "ui:visible_when": {"mode": "local"}},
        "cloud_key": {"type": "string", "ui:visible_when": {"mode": "cloud"}},
    },
    "required": ["mode", "host", "cloud_key"],
}


def test_strip_hidden_drops_hidden_values_and_their_required_entries():
    values, schema = strip_hidden({"mode": "cloud", "host": 7, "cloud_key": "k"}, SCHEMA)
    assert values == {"mode": "cloud", "cloud_key": "k"}
    assert schema["required"] == ["mode", "cloud_key"]


def test_output_config_validation_ignores_a_hidden_required_field():
    from src.outputs.output_config import validate_output_config

    assert validate_output_config({"mode": "cloud", "cloud_key": "k"}, SCHEMA) == []


def test_output_config_validation_still_requires_a_visible_field():
    from src.outputs.output_config import validate_output_config

    assert validate_output_config({"mode": "cloud"}, SCHEMA) == ["output_config: 'cloud_key' is a required property"]


# --- the settings-schema checks -------------------------------------------------------------------


def test_the_core_widgets_are_known():
    assert {MODE_CARDS_WIDGET, TILE_GRID_WIDGET, DEVICE_PICKER_WIDGET} <= KNOWN_SETTINGS_WIDGETS


def _schema(**props):
    return {"type": "object", "properties": {"mode": {"type": "string", "enum": ["local", "cloud"]}, **props}}


def test_a_bad_visible_when_is_a_schema_error():
    errors = validate_settings_schema_ui(_schema(host={"type": "string", "ui:visible_when": {"colour": "red"}}))
    assert errors == ["settings_schema.host: ui:visible_when references unknown property 'colour'"]


def test_sections_must_name_existing_fields_once():
    schema = _schema(host={"type": "string"})
    schema["ui:sections"] = [
        {"id": "conn", "title": "Connection", "fields": ["mode", "host"]},
        {"id": "adv", "title": "Advanced", "fields": ["host", "nope"], "collapsible": True},
    ]
    assert validate_settings_schema_ui(schema) == [
        "settings_schema.ui:sections[1]: field 'host' is already in section 'conn'",
        "settings_schema.ui:sections[1]: unknown property 'nope'",
    ]


def test_sections_need_unique_ids_and_titles():
    schema = _schema()
    schema["ui:sections"] = [
        {"id": "a", "title": "A", "fields": ["mode"]},
        {"id": "a", "fields": []},
    ]
    assert validate_settings_schema_ui(schema) == [
        "settings_schema.ui:sections[1]: duplicate id 'a'",
        "settings_schema.ui:sections[1]: title must be a non-empty string",
    ]


def test_collapsed_requires_collapsible():
    schema = _schema()
    schema["ui:sections"] = [{"id": "a", "title": "A", "fields": ["mode"], "collapsed": True}]
    assert validate_settings_schema_ui(schema) == ["settings_schema.ui:sections[0]: collapsed requires collapsible"]


def test_mode_cards_needs_an_enum():
    errors = validate_settings_schema_ui(_schema(kind={"type": "string", "ui:widget": "mode-cards"}))
    assert errors == ["settings_schema.kind: ui:widget 'mode-cards' requires an enum"]


def test_mode_cards_cards_must_be_enum_values():
    schema = _schema()
    schema["properties"]["mode"]["ui:widget"] = "mode-cards"
    schema["properties"]["mode"]["ui:options"] = {"cards": [{"value": "local", "title": "Local"}, {"value": "usb"}]}
    assert validate_settings_schema_ui(schema) == [
        "settings_schema.mode: ui:options.cards[1].value 'usb' is not one of the enum values"
    ]


def test_tile_grid_needs_row_and_col_items_and_size_fields():
    errors = validate_settings_schema_ui(
        _schema(
            tiles={"type": "array", "ui:widget": "tile-grid", "items": {"type": "object", "properties": {}}},
        )
    )
    assert errors == [
        "settings_schema.tiles: ui:widget 'tile-grid' items need integer 'row' and 'col' properties",
        "settings_schema.tiles: ui:options.rows_field must name an integer property",
        "settings_schema.tiles: ui:options.cols_field must name an integer property",
    ]


def test_a_well_formed_tile_grid_is_accepted():
    tile = {"type": "object", "properties": {"row": {"type": "integer"}, "col": {"type": "integer"}}}
    schema = _schema(
        wide={"type": "integer"},
        tall={"type": "integer"},
        tiles={
            "type": "array",
            "ui:widget": "tile-grid",
            "items": tile,
            "ui:options": {"rows_field": "tall", "cols_field": "wide"},
        },
    )
    assert validate_settings_schema_ui(schema) == []
    assert settings_schema_ui_warnings(schema) == []


def test_device_picker_must_be_a_string_field():
    errors = validate_settings_schema_ui(_schema(dev={"type": "integer", "ui:widget": "device-picker"}))
    assert errors == ["settings_schema.dev: ui:widget 'device-picker' requires type 'string'"]


def test_an_unknown_core_widget_option_is_a_warning():
    schema = _schema()
    schema["properties"]["mode"]["ui:widget"] = "mode-cards"
    schema["properties"]["mode"]["ui:options"] = {"colour": "red"}
    [warning] = settings_schema_ui_warnings(schema)
    assert warning.startswith("settings_schema.mode: unknown ui:options key 'colour' — ignored.")
