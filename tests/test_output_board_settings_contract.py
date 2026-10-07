"""The board settings contract (plan D13): actions, the action routes and ``GET /outputs``.

A board's settings screen renders from its output's declaration — the
``output_config`` settings schema and a list of **actions**. Pinned here:

- **manifest** — ``output.actions`` entries ``{id, label, description?,
  input_schema?, result_fields?}``; the UI vocabulary an output may use is
  the one of its ``output_api`` (an unknown widget is an error, not the data
  plugins' warning); a ``device-picker`` must name a declared action;
- **draft route** ``POST /outputs/{output_id}/actions/{action}`` — runs on
  settings typed before a board exists; ``"***"`` refused;
- **saved route** ``POST /boards/{board_id}/actions/{action}`` — runs on the
  stored settings, edited ones merged in with every ``"***"`` restored by the
  rule saving uses;
- **the envelope** — closed ``ActionResult``; a device verdict is 200
  ``status: "error"``, a refusal before contacting the device a 4xx; secret
  result fields carry ``secret: true`` and never reach the log;
- **listing** — ``GET /outputs``: built-ins first, then plugins, each with
  schema, device models and actions.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.outputs.output_manifest import parse_output_block
from src.plugins.loader import PluginLoader

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"

ACTIONS = [
    {"id": "test_connection", "label": "Test"},
    {"id": "discover", "label": "Find signs"},
    {"id": "identify", "label": "Blink"},
    {"id": "detect_geometry", "label": "Detect size"},
    {
        "id": "pair",
        "label": "Pair",
        "description": "Pair with the sign using the code it shows.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string", "title": "Code", "secret": True}},
            "required": ["code"],
        },
        "result_fields": {"token": {"secret": True, "fills": "token"}},
    },
    {"id": "explode", "label": "Explode"},
    {"id": "missing", "label": "Not implemented"},
]


def _install(root: Path) -> Path:
    target = root / PLUGIN_ID
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("__pycache__"))
    path = target / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    schema = manifest["output"]["settings_schema"]
    schema["properties"]["mode"] = {
        "type": "string",
        "enum": ["lan", "cloud"],
        "default": "lan",
        "ui:widget": "mode-cards",
        "ui:options": {"cards": [{"value": "lan", "title": "On my network"}, {"value": "cloud", "title": "Cloud"}]},
    }
    schema["properties"]["host"]["ui:widget"] = "device-picker"
    schema["properties"]["host"]["ui:visible_when"] = {"mode": "lan"}
    schema["ui:sections"] = [
        {"id": "connection", "title": "Connection", "fields": ["mode", "host", "token"]},
        {"id": "advanced", "title": "Advanced", "fields": ["min_interval_ms"], "collapsible": True, "collapsed": True},
    ]
    manifest["output"]["actions"] = ACTIONS
    path.write_text(json.dumps(manifest), "utf-8")
    return root


def _module():
    """The fixture plugin's module, as the loader imported it (each load is fresh)."""
    import sys

    return sys.modules[f"plugins.{PLUGIN_ID}"]


@pytest.fixture
def bundled(tmp_path):
    loader = PluginLoader(plugins_dir=_install(tmp_path / "plugins"), external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


@pytest.fixture
def third_party(tmp_path):
    loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[_install(tmp_path / "external")])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


def _instances():
    return _module().INSTANCES


def _settings():
    from src.settings.service import get_settings_service

    return get_settings_service()


def _draft(client, action, output_config=None, **body):
    return client.post(
        f"/outputs/{PLUGIN_ID}/actions/{action}",
        json={"output_config": output_config or {"host": "192.0.2.50", "token": "test_token_1234"}, **body},
    )


# --- the manifest -------------------------------------------------------------------------------


def _block(**overrides):
    block = {
        "output_api": 1,
        "device_models": ["divoom_pixoo64"],
        "settings_schema": {"type": "object", "properties": {"host": {"type": "string"}}},
        **overrides,
    }
    return parse_output_block(block, base_dir=Path("."), data_files=[])


class TestManifest:
    def test_actions_are_parsed_in_order_and_hooks_are_flagged_builtin(self):
        manifest, errors = _block(actions=[{"id": "discover", "label": "Find"}, {"id": "pair", "label": "Pair"}])
        assert errors == []
        assert [(a.id, a.builtin) for a in manifest.actions] == [("discover", True), ("pair", False)]

    def test_a_result_field_must_fill_a_settings_property(self):
        _manifest, errors = _block(
            actions=[{"id": "pair", "label": "Pair", "result_fields": {"token": {"secret": True, "fills": "nope"}}}]
        )
        assert errors == [
            "output.actions[0].result_fields.token.fills must name a settings_schema property, got 'nope'"
        ]

    def test_duplicate_and_malformed_action_ids_are_errors(self):
        _manifest, errors = _block(
            actions=[{"id": "pair", "label": "Pair"}, {"id": "pair", "label": "Again"}, {"id": "Bad-Id", "label": "x"}]
        )
        assert errors == [
            "output.actions[1]: duplicate action id 'pair'",
            "output.actions[2].id must match ^[a-z][a-z0-9_]*$",
        ]

    def test_an_unknown_key_in_an_action_is_an_error(self):
        _manifest, errors = _block(actions=[{"id": "pair", "label": "Pair", "javascript": "alert(1)"}])
        assert errors == ["output.actions[0]: unknown key 'javascript'"]

    def test_a_widget_outside_the_output_api_vocabulary_is_an_error(self):
        _manifest, errors = _block(
            settings_schema={"type": "object", "properties": {"host": {"type": "string", "ui:widget": "fancy-map"}}}
        )
        assert errors == ["output.settings_schema.host: ui:widget 'fancy-map' is not in output_api 1's vocabulary"]

    def test_an_input_schema_is_held_to_the_same_vocabulary(self):
        _manifest, errors = _block(
            actions=[
                {
                    "id": "pair",
                    "label": "Pair",
                    "input_schema": {"type": "object", "properties": {"c": {"type": "string", "ui:widget": "x"}}},
                }
            ]
        )
        assert errors == ["output.actions[0].input_schema.c: ui:widget 'x' is not in output_api 1's vocabulary"]

    def test_an_action_can_be_shown_only_while_a_condition_holds(self):
        manifest, errors = _block(
            actions=[
                {"id": "pair", "label": "Pair", "visible_when": {"host": "", "@device_type": "note_array"}},
                {"id": "detect_geometry", "label": "Size", "auto_apply": True},
            ]
        )
        assert errors == []
        assert manifest.actions[0].visible_when == {"host": "", "@device_type": "note_array"}
        assert (manifest.actions[0].auto_apply, manifest.actions[1].auto_apply) == (False, True)

    def test_an_action_condition_is_held_to_the_grammar(self):
        _manifest, errors = _block(
            actions=[
                {"id": "pair", "label": "Pair", "visible_when": {"mode": "lan"}},
                {"id": "size", "label": "Size", "visible_when": {"@colour": "red"}, "auto_apply": "yes"},
            ]
        )
        assert errors == [
            "output.actions[0].visible_when references unknown property 'mode'",
            "output.actions[1].visible_when references unknown board fact '@colour' "
            "(known: @device_model, @device_type)",
            "output.actions[1].auto_apply must be a boolean",
        ]

    def test_a_tile_grid_item_action_must_be_declared(self):
        tile = {"type": "object", "properties": {"row": {"type": "integer"}, "col": {"type": "integer"}}}
        schema = {
            "type": "object",
            "properties": {
                "tiles": {
                    "type": "array",
                    "items": tile,
                    "ui:widget": "tile-grid",
                    "ui:options": {"layout": "board", "item_actions": ["identify", "pair"]},
                }
            },
        }
        _manifest, errors = _block(settings_schema=schema, actions=[{"id": "identify", "label": "Blink"}])
        assert errors == ["output.settings_schema.tiles: tile-grid item action 'pair' is not declared in actions"]

    def test_a_device_picker_must_name_a_declared_action(self):
        _manifest, errors = _block(
            settings_schema={"type": "object", "properties": {"host": {"type": "string", "ui:widget": "device-picker"}}}
        )
        assert errors == ["output.settings_schema.host: device-picker action 'discover' is not declared in actions"]


# --- GET /outputs ---------------------------------------------------------------------------------


class TestListing:
    def test_the_built_ins_come_first_then_plugins(self, client, bundled):
        ids = [o["id"] for o in client.get("/outputs").json()]
        assert ids[:2] == ["vestaboard", "fiestapanel"]
        assert PLUGIN_ID in ids[2:]

    def test_a_plugin_carries_its_screen(self, client, bundled):
        output = next(o for o in client.get("/outputs").json() if o["id"] == PLUGIN_ID)
        assert output["builtin"] is False
        assert output["available"] is True
        assert output["icon"] == "monitor"
        assert output["description"].startswith("Test-only output plugin")
        assert output["output_api"] == 1
        assert output["settings_schema"]["ui:sections"][0]["fields"] == ["mode", "host", "token"]
        assert output["settings_schema"]["properties"]["host"]["ui:visible_when"] == {"mode": "lan"}
        assert [a["id"] for a in output["actions"]] == [a["id"] for a in ACTIONS]
        pair = output["actions"][4]
        assert pair["builtin"] is False
        assert pair["result_fields"] == {"token": {"secret": True, "fills": "token"}}
        assert output["device_models"][0]["id"] and output["device_models"][0]["label"]

    def test_vestaboard_declares_its_hooks_and_enable_local_api(self, client):
        vestaboard = client.get("/outputs").json()[0]
        assert vestaboard["builtin"] is True
        assert vestaboard["output_api"] is None
        assert [m["id"] for m in vestaboard["device_models"]] == [
            "vestaboard_flagship",
            "vestaboard_note",
            "vestaboard_note_array",
        ]
        assert [a["id"] for a in vestaboard["actions"]] == [
            "test_connection",
            "discover",
            "test_tile",
            "identify",
            "detect_geometry",
            "enable_local_api",
        ]
        enable = next(a for a in vestaboard["actions"] if a["id"] == "enable_local_api")
        assert enable["input_schema"]["required"] == ["enablement_token"]
        assert enable["result_fields"] == {"api_key": {"secret": True, "fills": "local_api_key"}}

    def test_a_marketplace_plugin_is_listed_available_with_no_opt_in(self, client, third_party):
        """Settings v7: display plugins need no opt-in; the deprecated wire
        fields read "not gated, available"."""
        output = next(o for o in client.get("/outputs").json() if o["id"] == PLUGIN_ID)
        assert (output["beta_gated"], output["available"]) == (False, True)


# --- the draft route --------------------------------------------------------------------------------


class TestDraftRoute:
    def test_test_connection_answers_the_envelope(self, client, bundled):
        resp = _draft(client, "test_connection")
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "message": "No connection check for this output.",
            "guidance": [],
            "fields": None,
            "geometry": None,
            "devices": None,
        }

    def test_the_throwaway_instance_sees_the_draft_and_is_closed(self, client, bundled):
        _draft(client, "test_connection")
        [instance] = _instances()
        assert instance.board_id is None
        assert instance.config == {"host": "192.0.2.50", "token": "test_token_1234"}
        assert instance.closed is True

    def test_a_device_verdict_is_a_200_error_with_guidance(self, client, bundled):
        resp = _draft(client, "pair", input={"code": "0000"})
        assert resp.status_code == 200
        body = resp.json()
        assert (body["status"], body["message"], body["guidance"]) == (
            "error",
            "Wrong pairing code.",
            ["Read the code off the sign."],
        )

    def test_a_declared_secret_result_field_is_marked_secret(self, client, bundled):
        body = _draft(client, "pair", input={"code": "1234"}).json()
        assert body["status"] == "ok"
        assert body["fields"] == {"token": {"value": "paired-192.0.2.50", "secret": True, "fills": "token"}}

    def test_a_secret_result_value_never_reaches_the_log(self, client, bundled, caplog):
        with caplog.at_level(logging.DEBUG):
            _draft(client, "pair", input={"code": "1234"})
        assert "paired-192.0.2.50" not in caplog.text
        assert "Output recording_output action pair on a draft: ok" in caplog.text

    def test_input_is_checked_against_the_input_schema(self, client, bundled):
        resp = _draft(client, "pair", input={})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "input: 'code' is a required property"

    def test_an_action_that_takes_no_input_refuses_one(self, client, bundled):
        resp = _draft(client, "test_connection", input={"x": 1})
        assert resp.status_code == 400

    def test_an_undeclared_action_is_404(self, client, bundled):
        resp = _draft(client, "action_pair")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Output 'recording_output' has no action 'action_pair'"

    def test_an_unknown_output_is_404(self, client):
        resp = client.post("/outputs/nope/actions/test_connection", json={})
        assert resp.status_code == 404

    def test_a_masked_secret_in_a_draft_is_refused(self, client, bundled):
        resp = _draft(client, "test_connection", output_config={"host": "192.0.2.50", "token": "***"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "A draft has no stored secret to restore: enter token"

    def test_a_crashing_action_is_an_error_verdict_and_logs_no_detail(self, client, bundled, caplog):
        with caplog.at_level(logging.DEBUG):
            body = _draft(client, "explode").json()
        assert (body["status"], body["message"]) == ("error", "'Explode' failed unexpectedly.")
        assert "test_token_1234" not in caplog.text
        assert "secret-in-exception" not in caplog.text

    def test_a_declared_but_unimplemented_action_is_an_error_verdict(self, client, bundled):
        body = _draft(client, "missing").json()
        assert (body["status"], body["message"]) == ("error", "Recording Output does not implement 'Not implemented'.")

    def test_detect_geometry_answers_the_detect_size_shape(self, client, bundled):
        body = _draft(client, "detect_geometry").json()
        assert body["geometry"] == {
            "device_type": "panel",
            "rows": 10,
            "cols": 16,
            "notes_wide": None,
            "notes_tall": None,
            "matched_preset": None,
        }

    def test_identify_runs_the_plugin_hook(self, client, bundled):
        assert _draft(client, "identify").json()["status"] == "ok"
        assert _module().IDENTIFIED == ["192.0.2.50"]

    def test_discover_runs_the_class_hook(self, client, bundled):
        body = _draft(client, "discover").json()
        assert (body["status"], body["devices"]) == ("ok", [])

    def test_a_marketplace_plugin_runs_draft_actions_with_no_opt_in(self, client, third_party):
        assert _draft(client, "test_connection").status_code == 200

    def test_an_undeclared_device_model_is_refused(self, client, bundled):
        assert _draft(client, "test_connection", device_model="vestaboard_flagship").status_code == 400


# --- the saved-board route ----------------------------------------------------------------------------


def _save_plugin_board(client) -> str:
    resp = client.post(
        f"/outputs/{PLUGIN_ID}/boards",
        json={"device_model": "divoom_pixoo64", "output_config": {"host": "192.0.2.50", "token": "stored_token"}},
    )
    assert resp.status_code == 201, resp.text
    _instances().clear()
    return resp.json()["id"]


class TestSavedRoute:
    @pytest.fixture(autouse=True)
    def _no_rebuild(self):
        with mock.patch("src.outputs.routes.reinitialize_board_clients"):
            yield

    def test_an_unknown_board_is_404(self, client, bundled):
        resp = client.post("/boards/nope/actions/test_connection", json={})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Board nope not found"

    def test_the_stored_settings_are_used_when_the_body_has_none(self, client, bundled):
        board_id = _save_plugin_board(client)
        assert client.post(f"/boards/{board_id}/actions/test_connection", json={}).status_code == 200
        [instance] = _instances()
        assert instance.config == {"host": "192.0.2.50", "token": "stored_token"}

    def test_a_masked_secret_in_edited_settings_is_restored_from_storage(self, client, bundled):
        board_id = _save_plugin_board(client)
        resp = client.post(
            f"/boards/{board_id}/actions/test_connection",
            json={"output_config": {"host": "192.0.2.99", "token": "***"}},
        )
        assert resp.status_code == 200
        [instance] = _instances()
        assert instance.config == {"host": "192.0.2.99", "token": "stored_token"}

    def test_the_action_writes_nothing(self, client, bundled):
        board_id = _save_plugin_board(client)
        client.post(f"/boards/{board_id}/actions/test_connection", json={"output_config": {"host": "192.0.2.99"}})
        stored = _settings().get_board_settings().to_dict(mask_secrets=False)["boards"]
        assert next(b for b in stored if b["id"] == board_id)["output_config"]["host"] == "192.0.2.50"

    def test_a_vestaboard_boards_masked_key_is_restored_like_set_boards(self, client):
        board = {"name": "Hall", "device_type": "flagship", "api_mode": "local"}
        _settings().set_boards([{**board, "host": "192.168.0.40", "local_api_key": "test_stored_key"}])
        board_id = _settings().get_board_settings().boards[0]["id"]
        from src.outputs.hooks import ConnectionCheck

        seen = []

        def fake_draft(draft):
            seen.append(dict(draft["output_config"]))
            driver = mock.Mock()
            driver.plugin.check_connection.return_value = ConnectionCheck(success=True, message="ok")
            return driver

        with mock.patch("src.outputs.factory.draft_driver", side_effect=fake_draft):
            resp = client.post(
                f"/boards/{board_id}/actions/test_connection",
                json={"output_config": {"host": "192.168.0.41", "local_api_key": "***"}},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ok"
        assert (seen[0]["host"], seen[0]["local_api_key"]) == ("192.168.0.41", "test_stored_key")


# --- the Vestaboard's actions -------------------------------------------------------------------------


class TestVestaboardActions:
    def test_enable_local_api_returns_the_key_as_a_secret_field_and_never_logs_it(self, client, caplog):
        async def fake_exchange(request):
            assert (request.host, request.enablement_token) == ("192.168.0.40", "test_token")
            return {"success": True, "api_key": "test_local_key_abc", "message": "Local API enabled"}

        with (
            mock.patch("plugins.vestaboard.local_api.exchange_enablement_token", fake_exchange),
            caplog.at_level(logging.DEBUG),
        ):
            resp = client.post(
                "/outputs/vestaboard/actions/enable_local_api",
                json={"output_config": {"host": "192.168.0.40"}, "input": {"enablement_token": "test_token"}},
            )
        assert resp.status_code == 200
        assert resp.json()["fields"] == {
            "api_key": {"value": "test_local_key_abc", "secret": True, "fills": "local_api_key"}
        }
        assert "test_local_key_abc" not in caplog.text

    def test_a_refused_token_is_an_error_verdict(self, client):
        async def fake_exchange(request):
            return {"success": False, "message": "Invalid enablement token", "error": "Invalid token"}

        with mock.patch("plugins.vestaboard.local_api.exchange_enablement_token", fake_exchange):
            body = client.post(
                "/outputs/vestaboard/actions/enable_local_api",
                json={"output_config": {"host": "192.168.0.40"}, "input": {"enablement_token": "test_token"}},
            ).json()
        assert (body["status"], body["message"], body["guidance"]) == (
            "error",
            "Invalid enablement token",
            ["Invalid token"],
        )

    def test_enable_local_api_needs_a_host(self, client):
        resp = client.post("/outputs/vestaboard/actions/enable_local_api", json={"input": {"enablement_token": "t"}})
        assert resp.status_code == 400

    def test_discover_answers_devices(self, client):
        found = [{"ip": "192.168.0.40", "port": 7000, "hostname": "vb.local", "source": "mdns"}]
        with mock.patch("plugins.vestaboard.discovery.discover", return_value=found) as discover:
            body = client.post("/outputs/vestaboard/actions/discover", json={"input": {"timeout": 2}}).json()
        assert discover.call_args.args == (2.0,)
        assert body["devices"] == [{**found[0], "label": None, "fields": {}}]

    def test_test_connection_without_details_is_400(self, client):
        assert client.post("/outputs/vestaboard/actions/test_connection", json={}).status_code == 400

    def test_a_masked_key_in_a_vestaboard_draft_is_refused(self, client):
        resp = client.post(
            "/outputs/vestaboard/actions/test_connection",
            json={"output_config": {"host": "192.168.0.40", "local_api_key": "***"}},
        )
        assert resp.status_code == 400

    def test_identify_outside_a_local_note_array_is_400(self, client):
        resp = client.post(
            "/outputs/vestaboard/actions/identify",
            json={"output_config": {"device_type": "flagship"}, "input": {"target": "all"}},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Identify is only available for note arrays in local API mode"

    def test_fiestapanel_test_connection_is_ok(self, client):
        assert client.post("/outputs/fiestapanel/actions/test_connection", json={}).json()["status"] == "ok"


def test_action_geometry_mirrors_detect_board_size_response():
    from src.outputs.models import ActionGeometry
    from src.settings.models import DetectBoardSizeResponse

    assert list(ActionGeometry.model_fields) == list(DetectBoardSizeResponse.model_fields)
