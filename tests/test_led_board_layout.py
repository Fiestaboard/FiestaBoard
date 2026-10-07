"""An LED board's tile gap and block padding, from its settings to its bytes (plan D23).

A board stores its choices in ``output_config`` (``tile_gap`` /
``block_padding``, :data:`~src.outputs.board_profile.LED_LAYOUT_CONFIG_KEYS`).
Core resolves them against the board's device model (``layoutOptions``: an
allowed value stands, anything else is the model's default and a warning)
and hands the result to both consumers, so the preview draws the bytes the
device is sent:

- the plugin, through :meth:`OutputPluginBase.led_layout_options`;
- the web preview, through the board view's ``led_layout``.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.fiestaui import builtin_device_models
from src.led import LedLayoutOptions, layout_message, led_spec_for_model, rasterize
from src.outputs.board_profile import LED_LAYOUT_CONFIG_KEYS, board_led_layout, led_layout_choice
from src.outputs.plugin_base import OutputPluginBase
from src.plugins.loader import PluginLoader
from src.send_outcome import WriteResult

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"
MODELS = builtin_device_models()
PIXOO_MODEL = MODELS["divoom_pixoo64"]

PIXOO = {
    "id": "pixoo-1",
    "name": "Pixoo",
    "device_type": "panel",
    "grid_rows": 10,
    "grid_cols": 16,
    "output": PLUGIN_ID,
    "device_model": "divoom_pixoo64",
    "output_config": {"host": "192.0.2.50"},
}
SIGN = {**PIXOO, "id": "sign-1", "device_model": "recording_sign", "grid_rows": 6, "grid_cols": 22}
HALL = {"id": "hall-1", "name": "Hall", "device_type": "flagship", "code62_glyph": "degree"}


class _Led(OutputPluginBase):
    plugin_id = "led_probe"

    def write(self, frame, *, native, cancel):  # pragma: no cover - never written
        return WriteResult(success=True, was_sent=True)


def _plugin(config: dict, model=PIXOO_MODEL) -> _Led:
    instance = _Led("board-1", config)
    instance.bind_board(device_model=model, character_set=None)
    return instance


@pytest.fixture
def output_plugin(tmp_path):
    """The recording output plugin, whose device models include the Pixoo 64."""
    root = tmp_path / "plugins"
    shutil.copytree(FIXTURE, root / PLUGIN_ID, ignore=shutil.ignore_patterns("__pycache__"))
    manifest_path = root / PLUGIN_ID / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["output"].pop("character_set")
    manifest_path.write_text(json.dumps(manifest), "utf-8")
    loader = PluginLoader(plugins_dir=root, external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


# --- resolving a board's choice -------------------------------------------------


def test_the_config_keys_are_the_layout_options_snake_cased():
    assert LED_LAYOUT_CONFIG_KEYS == ("tile_gap", "block_padding")


def test_a_board_that_chose_nothing_draws_with_its_models_defaults():
    assert led_layout_choice(PIXOO_MODEL, {"host": "192.0.2.50"}) == ("gap", 0, "3x5", [])
    assert led_layout_choice(PIXOO_MODEL, None) == ("gap", 0, "3x5", [])


def test_an_allowed_choice_stands():
    assert led_layout_choice(PIXOO_MODEL, {"tile_gap": "fill", "block_padding": 1}) == ("fill", 1, "3x5", [])


def test_a_choice_the_model_does_not_allow_is_its_default_with_a_reason():
    narrow = {**PIXOO_MODEL, "layoutOptions": {"tileGap": {"allowed": ["gap"]}}}
    choice = led_layout_choice(narrow, {"tile_gap": "fill", "block_padding": 1})
    assert (choice.tile_gap, choice.block_padding) == ("gap", 1)
    assert choice.ignored == ['tileGap="fill" is not a value divoom_pixoo64 allows (tileGap: "gap"); using "gap"']


def test_a_split_flap_model_has_no_led_layout():
    assert led_layout_choice(MODELS["vestaboard_flagship"], {"tile_gap": "fill"}) is None
    assert led_layout_choice(None, {"tile_gap": "fill"}) is None


# --- the plugin's options -------------------------------------------------------


def test_the_plugin_lays_out_with_the_boards_choices_and_its_set():
    options = _plugin({"tile_gap": "fill", "block_padding": 1}).led_layout_options()
    assert (options.tile_gap, options.block_padding) == ("fill", 1)
    assert options.charset is not None and options.charset["id"] == "led_3x5"


def test_the_plugin_draws_the_bytes_the_choice_names():
    message = "{black/white:OK} {66}{66}{66}"
    spec = led_spec_for_model(PIXOO_MODEL)
    seamless = rasterize(layout_message(message, spec, _plugin({"tile_gap": "fill"}).led_layout_options()))
    gaps = rasterize(layout_message(message, spec, _plugin({}).led_layout_options()))
    assert seamless.pixels == rasterize(layout_message(message, spec, LedLayoutOptions(tile_gap="fill"))).pixels
    assert seamless.pixels != gaps.pixels


def test_a_disallowed_choice_is_logged_once_per_instance(caplog):
    narrow = {**PIXOO_MODEL, "layoutOptions": {"blockPadding": {"allowed": [0]}}}
    plugin = _plugin({"block_padding": 1}, narrow)
    with caplog.at_level(logging.WARNING, logger="src.outputs.plugin_base"):
        assert plugin.led_layout_options().block_padding == 0
        assert plugin.led_layout_options().block_padding == 0
    warnings = [r.getMessage() for r in caplog.records if "blockPadding=1" in r.getMessage()]
    assert warnings == [
        "led_probe board board-1: blockPadding=1 is not a value divoom_pixoo64 allows (blockPadding: 0); using 0"
    ]


def test_a_split_flap_plugin_gets_the_renderer_defaults():
    options = _plugin({"tile_gap": "fill"}, MODELS["vestaboard_flagship"]).led_layout_options()
    assert (options.tile_gap, options.block_padding) == (None, None)


# --- the board view: what the preview draws -----------------------------------------


def test_the_board_view_names_an_led_boards_resolved_choice(output_plugin):
    assert board_led_layout(PIXOO) == {"tile_gap": "gap", "block_padding": 0}
    seamless = {**PIXOO, "output_config": {"host": "192.0.2.50", "tile_gap": "fill", "block_padding": 1}}
    assert board_led_layout(seamless) == {"tile_gap": "fill", "block_padding": 1}
    garbage = {**PIXOO, "output_config": {"host": "192.0.2.50", "tile_gap": "seamless", "block_padding": "1"}}
    assert board_led_layout(garbage) == {"tile_gap": "gap", "block_padding": 0}


def test_a_split_flap_board_has_no_led_layout(output_plugin):
    assert board_led_layout(HALL) is None
    assert board_led_layout(SIGN) is None


def test_get_settings_board_carries_led_layout_for_led_boards_only(output_plugin):
    from src.api_server import app
    from src.settings.service import get_settings_service

    seamless = {**PIXOO, "output_config": {"host": "192.0.2.50", "tile_gap": "fill", "block_padding": 1}}
    get_settings_service().set_boards([HALL, seamless])
    boards = {b["id"]: b for b in TestClient(app).get("/settings/board").json()["boards"]}
    assert boards["pixoo-1"]["led_layout"] == {"tile_gap": "fill", "block_padding": 1}
    assert "led_layout" not in boards["hall-1"]
