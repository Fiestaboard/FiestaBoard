"""Creating a board for an output plugin: ``POST /outputs/{output_id}/boards`` (plan D5, Phase 2.5).

Vestaboards are still created with ``POST /settings/board/add`` and
FiestaPanels with ``POST /panels``; this route creates every other board, from
an output plugin's declared device models. Pinned here:

- **the route contract** — a typed body (``name``, ``device_model``,
  ``output_config``, optional ``geometry``), 201 with the created board,
  declared 400/404/409, 422 for a malformed body; the board is saved with an
  explicit ``output`` and ``output_config`` and the display engine rebuilds;
- **geometry** — the content grid comes from the device model: ``cells`` as
  declared, ``pixels`` from the glyph box of FiestaUI's vendored LED fonts
  (cols = (W+1)/(gw+1), rows = (H+1)/(gh+1)), ``panel`` and ``note_array``
  from the request's geometry. A grid below the floor is **refused** before
  any geometry resolution: never inflated by clamp_grid. The floor is the
  3x15 Note, except for an LED board measured in pixels (``pixels``
  geometry), whose floor is 3x10 (Divoom Pixoo 64 at 3x5 = 10x16 and at
  5x7 = 8x10 pass; a 32x8 AWTRIX = 1x8 does not);
- **no coercion** — a plugin board stores its grid as a custom ``panel``
  grid and stays that way; a legacy Vestaboard claiming ``panel`` still
  falls back to flagship exactly as before;
- **additive fields** — settings and v1 board responses carry ``output``,
  the resolved ``device_model`` id and the resolved ``charset`` id.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.devices import BoardInstance
from src.fiestaui import builtin_device_models
from src.outputs import geometry
from src.plugins.loader import PluginLoader

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"
URL = f"/outputs/{PLUGIN_ID}/boards"
MODELS = ["divoom_pixoo64", "ulanzi_tc001_awtrix", "vestaboard_panel", "vestaboard_note_array"]


def _install(root: Path) -> Path:
    """The recording output with more device models, at *root*/recording_output."""
    target = root / PLUGIN_ID
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("__pycache__"))
    path = target / "output" / "device-models.json"
    models = json.loads(path.read_text("utf-8"))
    path.write_text(json.dumps([models[0], *MODELS]), "utf-8")
    return root


@pytest.fixture
def bundled(tmp_path):
    loader = PluginLoader(plugins_dir=_install(tmp_path / "plugins"), external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


@pytest.fixture
def bundled_5x7(tmp_path):
    """The recording output with its character set drawn in the 5x7 face."""
    root = _install(tmp_path / "plugins")
    path = root / PLUGIN_ID / "output" / "character-set.json"
    path.write_text(json.dumps({"id": "recording_sign_v1", "label": "Recording sign", "extends": "led_5x7"}), "utf-8")
    loader = PluginLoader(plugins_dir=root, external_dirs=[])
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

    with mock.patch("src.outputs.routes.reinitialize_board_clients") as rebuild:
        test_client = TestClient(app)
        test_client.rebuild = rebuild
        yield test_client


def _settings():
    from src.settings.service import get_settings_service

    return get_settings_service()


def _stored():
    return _settings().get_board_settings().to_dict(mask_secrets=False)["boards"]


def _body(**overrides):
    return {
        "name": "Kitchen sign",
        "device_model": "divoom_pixoo64",
        "output_config": {"host": "192.0.2.50", "token": "test_token_1234"},
        **overrides,
    }


def _model(model_id: str) -> dict:
    return dict(builtin_device_models()[model_id])


# --- geometry -----------------------------------------------------------------------------------


class TestGeometry:
    def test_a_pixoo_at_3x5_is_10_rows_by_16_cols(self):
        assert geometry.resolve_content_grid(_model("divoom_pixoo64"), None, None) == (10, 16)

    def test_a_32x8_awtrix_is_refused_below_the_floor(self):
        with pytest.raises(geometry.BelowFloorError) as raised:
            geometry.resolve_content_grid(_model("ulanzi_tc001_awtrix"), None, None)
        assert str(raised.value) == (
            "Device model 'ulanzi_tc001_awtrix' shows 1x8 characters, below the 3x10 minimum an LED board "
            "needs, so FiestaBoard cannot create a board for it."
        )

    def test_the_glyph_box_comes_from_fiestauis_vendored_fonts(self):
        assert geometry.glyph_box("3x5") == geometry.GlyphBox(width=3, height=5, spacing_x=1, spacing_y=1)
        assert geometry.glyph_box("5x7") == geometry.GlyphBox(width=5, height=7, spacing_x=1, spacing_y=1)

    def test_the_font_spacing_is_read_not_assumed(self, monkeypatch):
        fonts = {"3x5": {"glyphWidth": 3, "glyphHeight": 5, "spacingX": 0, "spacingY": 0}}
        monkeypatch.setattr(geometry, "led_fonts", lambda: fonts)
        assert geometry.resolve_content_grid(_model("divoom_pixoo64"), None, None) == (12, 21)

    def test_a_declared_character_sets_font_wins(self):
        five_by_seven = {"id": "five", "font": "5x7"}
        assert geometry.resolve_content_grid(_model("divoom_pixoo64"), five_by_seven, None) == (8, 10)

    @pytest.mark.parametrize(
        ("model_id", "grid"),
        [("hub75_64x64", (8, 10)), ("hub75_64x32", (4, 10)), ("tidbyt_tronbyt", (4, 10))],
    )
    def test_an_led_board_at_5x7_clears_the_3x10_led_floor(self, model_id, grid):
        assert geometry.resolve_content_grid(_model(model_id), None, None) == grid

    @pytest.mark.parametrize(
        ("model_id", "grid"),
        [("ulanzi_tc001_awtrix", "1x8"), ("max7219_4in1", "1x8"), ("p10_hub12_32x16", "2x5")],
    )
    def test_an_led_board_below_3x10_is_still_refused(self, model_id, grid):
        with pytest.raises(geometry.BelowFloorError, match=f"shows {grid} characters, below the 3x10 minimum"):
            geometry.resolve_content_grid(_model(model_id), None, None)

    @pytest.mark.parametrize(
        ("pixels", "grid"),
        # 3x5 glyphs on a 1-pixel gap: a column is 4 pixels, a row 6.
        [({"width": 35, "height": 17}, "3x9"), ({"width": 55, "height": 11}, "2x14")],
    )
    def test_an_led_grid_just_below_3x10_is_refused(self, pixels, grid):
        model = {**_model("divoom_pixoo64"), "geometry": {"kind": "pixels", **pixels}}
        with pytest.raises(geometry.BelowFloorError, match=f"shows {grid} characters, below the 3x10 minimum"):
            geometry.resolve_content_grid(model, None, None)

    def test_a_panel_model_keeps_the_3x15_note_floor(self):
        with pytest.raises(geometry.BelowFloorError) as raised:
            geometry.resolve_content_grid(_model("vestaboard_panel"), None, {"rows": 8, "cols": 10})
        assert str(raised.value) == (
            "Device model 'vestaboard_panel' shows 8x10 characters, below the 3x15 minimum a board "
            "needs, so FiestaBoard cannot create a board for it."
        )

    def test_a_cells_model_keeps_the_3x15_note_floor(self):
        model = {**_model("vestaboard_flagship"), "geometry": {"kind": "cells", "rows": 8, "cols": 10}}
        with pytest.raises(geometry.BelowFloorError, match="below the 3x15 minimum"):
            geometry.resolve_content_grid(model, None, None)

    def test_a_cells_model_is_its_declared_grid(self):
        assert geometry.resolve_content_grid(_model("vestaboard_flagship"), None, None) == (6, 22)

    def test_a_panel_model_takes_rows_and_cols(self):
        assert geometry.resolve_content_grid(_model("vestaboard_panel"), None, {"rows": 12, "cols": 40}) == (12, 40)

    def test_a_note_array_model_takes_notes(self):
        grid = geometry.resolve_content_grid(_model("vestaboard_note_array"), None, {"notes_wide": 2, "notes_tall": 1})
        assert grid == (3, 30)

    def test_a_small_panel_grid_is_refused_not_clamped(self):
        with pytest.raises(geometry.BelowFloorError, match="2x40"):
            geometry.resolve_content_grid(_model("vestaboard_panel"), None, {"rows": 2, "cols": 40})

    def test_an_oversized_panel_grid_is_refused_not_clamped(self):
        with pytest.raises(geometry.GeometryError, match="larger than the 96x128 maximum"):
            geometry.resolve_content_grid(_model("vestaboard_panel"), None, {"rows": 12, "cols": 400})

    def test_a_sized_per_board_model_needs_geometry(self):
        with pytest.raises(geometry.GeometryError, match="sized per board"):
            geometry.resolve_content_grid(_model("vestaboard_panel"), None, None)

    def test_a_fixed_model_takes_no_geometry(self):
        with pytest.raises(geometry.GeometryError, match="fixed size"):
            geometry.resolve_content_grid(_model("divoom_pixoo64"), None, {"rows": 3, "cols": 15})

    def test_the_conformance_suite_sizes_models_the_same_way(self):
        from src.outputs.conformance import model_cell_grid

        assert model_cell_grid is geometry.model_cell_grid


# --- the route ----------------------------------------------------------------------------------


class TestCreate:
    def test_a_pixoo_board_is_created(self, bundled, client):
        response = client.post(URL, json=_body())
        assert response.status_code == 201, response.text
        body = response.json()
        assert body == {
            "id": body["id"],
            "name": "Kitchen sign",
            "output": PLUGIN_ID,
            "device_model": "divoom_pixoo64",
            "charset": "recording_sign_v1",
            "device_type": "panel",
            "rows": 10,
            "cols": 16,
            "output_config": {"host": "192.0.2.50", "token": "***"},
        }

    def test_the_board_is_saved_with_its_output_and_grid(self, bundled, client):
        board_id = client.post(URL, json=_body()).json()["id"]
        (stored,) = [b for b in _stored() if b["id"] == board_id]
        assert stored["output"] == PLUGIN_ID
        assert stored["output_config"] == {"host": "192.0.2.50", "token": "test_token_1234"}
        assert stored["device_model"] == "divoom_pixoo64"
        assert (stored["device_type"], stored["grid_rows"], stored["grid_cols"]) == ("panel", 10, 16)

    def test_the_display_engine_rebuilds(self, bundled, client):
        client.post(URL, json=_body())
        client.rebuild.assert_called_once_with()

    def test_a_board_below_the_floor_is_refused_and_nothing_is_saved(self, bundled, client):
        before = _stored()
        with mock.patch("src.devices.clamp_grid", side_effect=AssertionError("clamp_grid was reached")):
            response = client.post(URL, json=_body(device_model="ulanzi_tc001_awtrix"))
        assert response.status_code == 400
        assert response.json()["detail"] == (
            "Device model 'ulanzi_tc001_awtrix' shows 1x8 characters, below the 3x10 minimum an LED board "
            "needs, so FiestaBoard cannot create a board for it."
        )
        assert _stored() == before

    def test_a_pixoo_drawn_at_5x7_is_created_as_an_8x10_board(self, bundled_5x7, client):
        response = client.post(URL, json=_body())
        assert response.status_code == 201, response.text
        assert (response.json()["rows"], response.json()["cols"]) == (8, 10)
        (stored,) = [b for b in _stored() if b["id"] == response.json()["id"]]
        assert (stored["device_type"], stored["grid_rows"], stored["grid_cols"]) == ("panel", 8, 10)

    def test_a_panel_model_board_takes_its_geometry(self, bundled, client):
        response = client.post(URL, json=_body(device_model="vestaboard_panel", geometry={"rows": 8, "cols": 32}))
        assert response.status_code == 201, response.text
        assert (response.json()["rows"], response.json()["cols"]) == (8, 32)

    def test_a_note_array_model_board_takes_notes(self, bundled, client):
        geometry_ = {"notes_wide": 2, "notes_tall": 2}
        response = client.post(URL, json=_body(device_model="vestaboard_note_array", geometry=geometry_))
        assert response.status_code == 201, response.text
        assert (response.json()["device_type"], response.json()["rows"], response.json()["cols"]) == ("panel", 6, 30)

    def test_geometry_for_a_fixed_model_is_refused(self, bundled, client):
        response = client.post(URL, json=_body(geometry={"rows": 10, "cols": 16}))
        assert response.status_code == 400
        assert "fixed size" in response.json()["detail"]

    def test_a_model_the_plugin_does_not_declare_is_refused(self, bundled, client):
        response = client.post(URL, json=_body(device_model="hub75_64x64"))
        assert response.status_code == 400
        assert response.json()["detail"] == (
            f"Output '{PLUGIN_ID}' declares no device model 'hub75_64x64'. It declares: recording_sign, "
            "divoom_pixoo64, ulanzi_tc001_awtrix, vestaboard_panel, vestaboard_note_array."
        )

    def test_an_output_config_the_schema_rejects_is_refused(self, bundled, client):
        response = client.post(URL, json=_body(output_config={"token": "test_token_1234"}))
        assert response.status_code == 400
        assert response.json()["detail"] == "output_config: 'host' is a required property"

    def test_a_masked_secret_is_refused_on_a_new_board(self, bundled, client):
        response = client.post(URL, json=_body(output_config={"host": "192.0.2.50", "token": "***"}))
        assert response.status_code == 400
        assert response.json()["detail"] == "A new board has no stored secret to restore: enter token"

    def test_an_output_that_is_not_installed_is_404(self, client):
        response = client.post(URL, json=_body())
        assert response.status_code == 404
        assert response.json()["detail"] == f"Output '{PLUGIN_ID}' is not installed."

    @pytest.mark.parametrize("builtin", ["vestaboard", "fiestapanel"])
    def test_a_built_in_output_is_pointed_at_its_own_route(self, client, builtin):
        response = client.post(f"/outputs/{builtin}/boards", json=_body())
        assert response.status_code == 400
        assert response.json()["detail"] == (
            f"'{builtin}' boards are not created here: add a Vestaboard with POST /settings/board/add "
            "and a FiestaPanel with POST /panels."
        )

    def test_a_third_party_output_needs_the_beta(self, third_party, client):
        response = client.post(URL, json=_body())
        assert response.status_code == 409
        assert response.json()["detail"] == (
            f"Output plugin '{PLUGIN_ID}' needs the output plugins beta (Integrations page)"
        )

    def test_with_the_beta_on_a_third_party_output_creates(self, third_party, client):
        _settings().update_plugin_settings({"output_plugins_enabled": True})
        assert client.post(URL, json=_body()).status_code == 201

    @pytest.mark.parametrize(
        "body",
        [
            {"device_model": "divoom_pixoo64", "output_config": {}, "surprise": 1},
            {"output_config": {}},
            {"device_model": "divoom_pixoo64", "geometry": {"rows": "ten"}},
        ],
    )
    def test_a_malformed_body_is_422(self, bundled, client, body):
        assert client.post(URL, json=body).status_code == 422


# --- no coercion ----------------------------------------------------------------------------------


class TestNoCoercion:
    def test_a_plugin_boards_custom_grid_is_kept(self):
        board = BoardInstance.from_dict(
            {"output": PLUGIN_ID, "device_type": "panel", "grid_rows": 10, "grid_cols": 16, "api_mode": "local"}
        )
        assert (board.device_type, board.grid_rows, board.grid_cols) == ("panel", 10, 16)

    def test_an_8x10_led_grid_is_kept_not_widened_to_15(self):
        board = BoardInstance.from_dict(
            {"output": PLUGIN_ID, "device_type": "panel", "grid_rows": 8, "grid_cols": 10, "api_mode": "local"}
        )
        assert (board.grid_rows, board.grid_cols) == (8, 10)

    def test_a_grid_below_3x10_is_clamped_to_3x10(self):
        board = BoardInstance.from_dict(
            {"output": PLUGIN_ID, "device_type": "panel", "grid_rows": 1, "grid_cols": 8, "api_mode": "local"}
        )
        assert (board.grid_rows, board.grid_cols) == (3, 10)

    def test_it_survives_a_save_and_reload(self, bundled, client):
        board_id = client.post(URL, json=_body()).json()["id"]
        _settings().set_boards(_settings().get_board_settings().to_dict()["boards"])
        (stored,) = [b for b in _stored() if b["id"] == board_id]
        assert (stored["device_type"], stored["grid_rows"], stored["grid_cols"]) == ("panel", 10, 16)

    def test_a_legacy_vestaboard_claiming_panel_is_still_a_flagship(self):
        board = BoardInstance.from_dict({"device_type": "panel", "grid_rows": 10, "grid_cols": 16, "api_mode": "local"})
        assert (board.device_type, board.grid_rows) == ("flagship", None)

    def test_a_legacy_board_never_stores_a_device_model(self):
        stored = BoardInstance.from_dict({"device_type": "note", "device_model": "vestaboard_note"}).to_dict()
        assert "device_model" not in stored


# --- additive fields ----------------------------------------------------------------------------


def _legacy(**fields):
    return {"id": "v1", "name": "Hall", "api_mode": "local", "host": "192.0.2.10", "local_api_key": "k", **fields}


class TestBoardResponses:
    @pytest.mark.parametrize(
        ("fields", "model", "charset"),
        [
            ({"device_type": "flagship"}, "vestaboard_flagship", "vestaboard_v1"),
            ({"device_type": "flagship", "code62_glyph": "heart"}, "vestaboard_flagship", "vestaboard_v2"),
            ({"device_type": "note"}, "vestaboard_note", "vestaboard_v2"),
            ({"device_type": "note_array", "notes_wide": 2}, "vestaboard_note_array", "vestaboard_v2"),
            # A FiestaPanel's board is the model of its panel's render style
            # (split_flap when no panel claims it): tests/test_panel_render_style.py.
            (
                {"device_type": "panel", "api_mode": "virtual", "grid_rows": 6, "grid_cols": 30},
                "fiestapanel_split_flap",
                "vestaboard_v2",
            ),
        ],
    )
    def test_a_legacy_board_reports_its_model_and_charset(self, client, fields, model, charset):
        _settings().set_boards([_legacy(**fields)])
        (shown,) = client.get("/settings/board").json()["boards"]
        assert (shown["device_model"], shown["charset"]) == (model, charset)

    def test_a_plugin_board_reports_its_model_and_charset(self, bundled, client):
        client.post(URL, json=_body())
        shown = client.get("/settings/board").json()["boards"][-1]
        assert (shown["output"], shown["device_model"], shown["charset"]) == (
            PLUGIN_ID,
            "divoom_pixoo64",
            "recording_sign_v1",
        )

    def test_v1_board_summaries_carry_them(self, bundled, client):
        client.post(URL, json=_body())
        boards = client.get("/v1/boards").json()["boards"]
        assert [(b["output"], b["device_model"], b["charset"]) for b in boards] == [
            ("vestaboard", "vestaboard_flagship", "vestaboard_v1"),
            (PLUGIN_ID, "divoom_pixoo64", "recording_sign_v1"),
        ]

    def test_echoing_a_legacy_board_back_stores_nothing_new(self, client):
        _settings().set_boards([_legacy(device_type="flagship")])
        before = _stored()
        boards = client.get("/settings/board").json()["boards"]
        with mock.patch("src.settings.routes.reinitialize_board_clients"):  # no engine (and no board I/O) here
            assert client.put("/settings/board", json={"boards": boards}).status_code == 200
        assert _stored() == before
