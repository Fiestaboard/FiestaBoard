"""The grids an LED board can produce, one per text size its model allows."""

import json

import pytest

from src.fiestaui import builtin_device_models
from src.outputs.board_profile import board_producible_grids, producible_grids
from src.plugins.loader import PluginLoader
from tests.test_led_text_size import PLUGIN_ID, _board, _install, declared_set_output, pixoo_output  # noqa: F401

MODELS = builtin_device_models()


def test_a_pixoo_produces_one_grid_per_text_size():
    assert producible_grids(MODELS["divoom_pixoo64"], None) == {"5x7": (8, 10), "3x5": (10, 16)}


def test_a_model_without_a_font_choice_produces_only_its_own_face():
    assert producible_grids(MODELS["hub75_64x32"], None) == {"5x7": (4, 10)}


def test_a_tiny_positive_grid_is_supported_by_the_released_pixel_floor():
    assert producible_grids(MODELS["ulanzi_tc001_awtrix"], None) == {"3x5": (1, 8)}


def test_a_surface_that_cannot_hold_one_cell_is_omitted():
    model = {**MODELS["ulanzi_tc001_awtrix"], "geometry": {"kind": "pixels", "width": 1, "height": 1}}
    assert producible_grids(model, None) == {}


def test_a_split_flap_model_produces_nothing():
    assert producible_grids(MODELS["vestaboard_flagship"], None) == {}


def test_a_pixoo_board_reports_both_grids(pixoo_output):  # noqa: F811
    assert board_producible_grids(_board()) == {"5x7": (8, 10), "3x5": (10, 16)}


def test_an_output_with_its_own_character_set_has_a_fixed_face(declared_set_output):  # noqa: F811
    grids = board_producible_grids(_board())
    assert grids is not None and len(grids) == 1


def test_a_vestaboard_has_no_producible_grids():
    assert board_producible_grids({"id": "b", "device_type": "flagship"}) is None


@pytest.fixture
def declared_5x7_output(tmp_path):
    """The recording output declaring a set that extends ``led_5x7``, on a Pixoo 64 (whose own face is 3x5)."""
    root = _install(tmp_path / "plugins", character_set=True)
    set_path = root / PLUGIN_ID / "output" / "character-set.json"
    charset = json.loads(set_path.read_text("utf-8"))
    charset["extends"] = "led_5x7"
    charset.pop("glyphs", None)
    set_path.write_text(json.dumps(charset), "utf-8")
    loader = PluginLoader(plugins_dir=root, external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


def test_an_output_with_its_own_character_set_produces_its_sets_face_grid(declared_5x7_output):
    # Plan D17: the declared set's font wins over the model's own, so a Pixoo
    # 64 drawing a 5x7 set produces 8 x 10, not its own 3x5 face's 10 x 16.
    assert board_producible_grids(_board()) == {"5x7": (8, 10)}
