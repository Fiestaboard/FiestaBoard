"""The grids an LED board can produce, one per text size its model allows."""

from src.fiestaui import builtin_device_models
from src.outputs.board_profile import board_producible_grids, producible_grids
from tests.test_led_text_size import _board, declared_set_output, pixoo_output  # noqa: F401

MODELS = builtin_device_models()


def test_a_pixoo_produces_one_grid_per_text_size():
    assert producible_grids(MODELS["divoom_pixoo64"], None) == {"5x7": (8, 10), "3x5": (10, 16)}


def test_a_model_without_a_font_choice_produces_only_its_own_face():
    assert producible_grids(MODELS["hub75_64x32"], None) == {"5x7": (4, 10)}


def test_a_below_floor_grid_is_omitted():
    assert producible_grids(MODELS["ulanzi_tc001_awtrix"], None) == {}  # 1 x 8 at 3x5


def test_a_split_flap_model_produces_nothing():
    assert producible_grids(MODELS["vestaboard_flagship"], None) == {}


def test_a_pixoo_board_reports_both_grids(pixoo_output):  # noqa: F811
    assert board_producible_grids(_board()) == {"5x7": (8, 10), "3x5": (10, 16)}


def test_an_output_with_its_own_character_set_has_a_fixed_face(declared_set_output):  # noqa: F811
    grids = board_producible_grids(_board())
    assert grids is not None and len(grids) == 1


def test_a_vestaboard_has_no_producible_grids():
    assert board_producible_grids({"id": "b", "device_type": "flagship"}) is None
