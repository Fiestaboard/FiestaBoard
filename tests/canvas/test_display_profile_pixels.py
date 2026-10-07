"""DisplayProfile on pixel-matrix boards (design §3 step 8): the ``pixels`` feature, pixel size, the canvas brief."""

from __future__ import annotations

from types import SimpleNamespace

from src.fiestaui import builtin_device_models
from src.led.charsets import resolve_character_set
from src.outputs.display_profile import FEATURES, DisplayProfile, display_profile_for_board, display_profile_for_client

MODELS = builtin_device_models()
PIXOO = MODELS["divoom_pixoo64"]
FLAGSHIP = MODELS["vestaboard_flagship"]


def _driver(model, charset_id=None):
    return SimpleNamespace(
        plugin=SimpleNamespace(device_model=model, config={}),
        character_set=resolve_character_set(charset_id) if charset_id else None,
    )


def test_pixels_is_a_feature():
    assert "pixels" in FEATURES


def test_a_pixel_matrix_board_supports_pixels_and_knows_its_pixel_size():
    profile = display_profile_for_client(_driver(PIXOO, "led_3x5"))
    assert profile.supports("pixels")
    assert (profile.width, profile.height) == (64, 64)


def test_a_split_flap_board_draws_no_pixels_and_has_no_pixel_size():
    profile = display_profile_for_client(_driver(FLAGSHIP))
    assert not profile.supports("pixels")
    assert (profile.width, profile.height) == (None, None)
    assert not DisplayProfile().supports("pixels")


def test_the_pixel_size_is_part_of_the_cache_key():
    a = DisplayProfile(technology="led_matrix", device_model="m", width=64, height=32)
    b = DisplayProfile(technology="led_matrix", device_model="m", width=64, height=64)
    assert a.key != b.key
    # A profile without a pixel size keys exactly as before.
    assert DisplayProfile(device_model="m").key == "m|None|tiles|None"


def test_the_ai_brief_mentions_canvases_only_on_a_pixel_board():
    pixel = display_profile_for_client(_driver(PIXOO, "led_3x5")).ai_brief()
    flap = display_profile_for_client(_driver(FLAGSHIP)).ai_brief()
    assert "canvas" in pixel.lower() and "64 x 64" in pixel
    assert "canvas" not in flap.lower()


def test_a_board_entry_resolves_its_pixel_size_too(monkeypatch):
    monkeypatch.setattr("src.outputs.display_profile.board_device_model", lambda board: PIXOO)
    monkeypatch.setattr(
        "src.outputs.display_profile.board_character_set", lambda board: resolve_character_set("led_3x5")
    )
    profile = display_profile_for_board({"id": "b", "grid_rows": 10, "grid_cols": 16})
    assert profile.supports("pixels") and (profile.width, profile.height) == (64, 64)
