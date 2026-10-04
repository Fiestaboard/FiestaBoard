"""The Vestaboard's settings screen, declared in its plugin manifest (plan D13, Phase 4).

Settings → Hardware and the setup wizard render a Vestaboard board's
settings from ``fiestaboard-output--vestaboard``'s manifest — its
``output.settings_schema`` for ``output_config`` and its ``output.actions`` —
with the same renderer every output plugin gets; core has no Vestaboard form.
This pins that the declaration (as seeded at the pin in ``outputs.lock.json``)
is valid under core's contract and says what the hand-coded form did:

- which fields show for each connection (Local / Cloud) and board shape
  (Flagship and Note / Note array), read from the board's ``@device_type``;
- which actions show, and that "Get API Key from Board" fills the key;
- that every credential is a secret;
- that ``output_config`` validates the way the screen shows it (a hidden
  field is never required).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.outputs.output_config import validate_output_config
from src.outputs.registry import VESTABOARD, output_registry
from src.plugins.manifest import settings_schema_ui_warnings, validate_settings_schema_ui
from src.plugins.settings_ui import is_visible

SHAPES = ("flagship", "note", "note_array")


@pytest.fixture(scope="module")
def definition():
    found = output_registry().get(VESTABOARD)
    assert found is not None, "the Vestaboard output is not in the seed"
    return found


@pytest.fixture(scope="module")
def schema(definition):
    return dict(definition.settings_schema)


def _visible_fields(schema, api_mode, device_type):
    props = schema["properties"]
    values = {"api_mode": api_mode}
    context = {"device_type": device_type, "device_model": None}
    return {
        name
        for name, prop in props.items()
        if name != "api_mode" and is_visible(prop.get("ui:visible_when"), values, props, context)
    }


def _visible_actions(definition, schema, api_mode, device_type):
    props = schema["properties"]
    context = {"device_type": device_type, "device_model": None}
    return [a.id for a in definition.actions if is_visible(a.visible_when, {"api_mode": api_mode}, props, context)]


def test_the_screen_is_valid_under_the_contract(schema):
    assert validate_settings_schema_ui(schema) == []
    assert settings_schema_ui_warnings(schema) == []


def test_the_connection_is_a_choice_of_two_cards(schema):
    api_mode = schema["properties"]["api_mode"]
    assert api_mode["ui:widget"] == "mode-cards"
    assert api_mode["enum"] == ["local", "cloud"]
    assert [c["title"] for c in api_mode["ui:options"]["cards"]] == ["Local API", "Cloud API"]


@pytest.mark.parametrize(
    ("api_mode", "device_type", "fields"),
    [
        ("local", "flagship", {"host", "port", "local_api_key"}),
        ("local", "note", {"host", "port", "local_api_key"}),
        ("cloud", "flagship", {"cloud_key"}),
        ("cloud", "note", {"cloud_key"}),
        ("local", "note_array", {"tiles"}),
        ("cloud", "note_array", {"note_array_token"}),
    ],
)
def test_each_connection_and_shape_shows_only_its_own_fields(schema, api_mode, device_type, fields):
    assert _visible_fields(schema, api_mode, device_type) == fields


def test_a_single_boards_address_is_found_by_the_discover_action(schema):
    host = schema["properties"]["host"]
    assert host["ui:widget"] == "device-picker"
    assert host["ui:options"]["action"] == "discover"


def test_a_local_note_array_is_set_up_tile_by_tile_on_the_boards_layout(definition, schema):
    tiles = schema["properties"]["tiles"]
    assert tiles["ui:widget"] == "tile-grid"
    options = tiles["ui:options"]
    assert options["layout"] == "board"
    assert options["item_actions"] == ["identify", "enable_local_api"]
    assert options["unique_fields"] == ["host", "port"]
    item = tiles["items"]
    assert set(item["properties"]) == {"row", "col", "host", "port", "local_api_key", "enabled"}
    assert item["required"] == ["host", "local_api_key"]
    assert item["properties"]["host"]["ui:widget"] == "device-picker"
    declared = {a.id for a in definition.actions}
    assert set(options["item_actions"]) <= declared


def test_the_port_is_under_advanced(schema):
    [advanced] = schema["ui:sections"]
    assert (advanced["fields"], advanced["collapsible"], advanced["collapsed"]) == (["port"], True, True)


def test_every_credential_is_a_secret(schema):
    props = schema["properties"]
    secrets = {name for name, prop in props.items() if prop.get("secret") is True}
    assert secrets == {"local_api_key", "cloud_key", "note_array_token"}
    assert props["tiles"]["items"]["properties"]["local_api_key"]["secret"] is True


@pytest.mark.parametrize(
    ("api_mode", "device_type", "actions"),
    [
        ("local", "flagship", ["test_connection", "discover", "detect_geometry", "enable_local_api"]),
        ("cloud", "flagship", ["test_connection", "detect_geometry"]),
        ("cloud", "note_array", ["test_connection", "detect_geometry"]),
        # The grid identifies tiles and gets keys per tile; a local array's
        # size is its tiles, so there is nothing to detect.
        ("local", "note_array", ["test_connection", "discover", "identify", "enable_local_api"]),
    ],
)
def test_each_connection_and_shape_offers_only_its_own_actions(definition, schema, api_mode, device_type, actions):
    assert _visible_actions(definition, schema, api_mode, device_type) == actions


def test_auto_detect_applies_the_size_it_reads(definition):
    detect = next(a for a in definition.actions if a.id == "detect_geometry")
    assert (detect.label, detect.auto_apply) == ("Auto-detect from board", True)


def test_get_api_key_from_board_fills_the_local_api_key_as_a_secret(definition):
    enable = next(a for a in definition.actions if a.id == "enable_local_api")
    assert enable.label == "Get API Key from Board"
    assert enable.input_schema["required"] == ["enablement_token"]
    assert enable.input_schema["properties"]["enablement_token"]["secret"] is True
    [(name, field)] = enable.result_fields.items()
    assert (name, field.fills, field.secret) == ("api_key", "local_api_key", True)


# --- output_config validates the way the screen shows it -----------------------------------------


def _errors(schema, config, device_type):
    return validate_output_config(config, schema, {"device_type": device_type, "device_model": None})


def test_a_local_flagship_needs_its_address_and_key(schema):
    errors = _errors(schema, {"api_mode": "local", "host": "", "cloud_key": ""}, "flagship")
    assert errors == ["output_config: 'local_api_key' is a required property"]


def test_a_cloud_flagship_needs_only_its_cloud_key(schema):
    assert _errors(schema, {"api_mode": "cloud", "cloud_key": "k"}, "flagship") == []


def test_a_cloud_note_array_needs_only_its_token(schema):
    assert _errors(schema, {"api_mode": "cloud", "note_array_token": "t"}, "note_array") == []
    assert _errors(schema, {"api_mode": "cloud"}, "note_array") == [
        "output_config: 'note_array_token' is a required property"
    ]


def test_a_local_note_arrays_tile_needs_its_address_and_key(schema):
    config = {"api_mode": "local", "tiles": [{"row": 0, "col": 0, "host": "192.0.2.10"}]}
    assert _errors(schema, config, "note_array") == ["output_config.tiles.0: 'local_api_key' is a required property"]


# --- GET /outputs carries the screen --------------------------------------------------------------


def test_get_outputs_carries_the_vestaboard_screen(definition):
    from src.api_server import app

    vestaboard = next(o for o in TestClient(app).get("/outputs").json() if o["id"] == VESTABOARD)
    assert vestaboard["settings_schema"] == dict(definition.settings_schema)
    detect = next(a for a in vestaboard["actions"] if a["id"] == "detect_geometry")
    assert detect["auto_apply"] is True
    assert detect["visible_when"] == {"not": {"api_mode": "local", "@device_type": "note_array"}}


def test_the_web_tests_render_the_screens_the_seed_serves():
    """The web suite renders the first-party screens from a copy of what
    ``GET /outputs`` serves; a pin bump that changes them must refresh it."""
    root = Path(__file__).parent.parent
    served = json.loads((root / "tests" / "golden" / "outputs" / "first_party_presentation.json").read_text())
    copied = json.loads((root / "web" / "src" / "__tests__" / "mocks" / "first-party-outputs.json").read_text())
    assert copied == served
