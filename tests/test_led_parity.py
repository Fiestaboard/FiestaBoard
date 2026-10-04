"""LED layout and raster parity with FiestaUI, the reference implementation.

Every case in ``tests/fixtures/fiestaui/led-golden.json`` (FiestaUI's
``layoutLedMessage`` + ``rasterizeLedLayout`` output) must give the same
accessible text and the same RGB888 bytes here. The plugin-set case lays out
with ``acme_sign_v1`` materialised over ``led_3x5``, so the
``charset-golden.json`` materialisation cases are checked too: this is the
golden check of core's one materialiser, which the output-plugin manifest
uses as well.

Provenance: ``src/fiestaui/provenance.json`` (pinned by
``tests/test_fiestaui_vendored.py``).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from src.fiestaui import builtin_device_models
from src.led import (
    BUILTIN_CHARACTER_SETS,
    LED_FONTS,
    LedLayoutOptions,
    LedMatrixSpec,
    grid_layout,
    layout_message,
    led_spec_for_model,
    materialize_character_set,
    rasterize,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "fiestaui"
LED_GOLDEN = json.loads((FIXTURES / "led-golden.json").read_text(encoding="utf-8"))
CHARSET_GOLDEN = json.loads((FIXTURES / "charset-golden.json").read_text(encoding="utf-8"))
DEVICE_MODELS = builtin_device_models()

LAYOUT_CASES = LED_GOLDEN["layouts"]


def _spec(raw: dict) -> LedMatrixSpec:
    return LedMatrixSpec(width=raw["width"], height=raw["height"], font=raw.get("font", "5x7"))


def _options(case: dict) -> LedLayoutOptions:
    raw = case.get("options", {})
    charset = materialize_character_set(case["charset"]) if "charset" in case else None
    return LedLayoutOptions(
        text_color=raw.get("textColor"),
        monochrome=raw.get("monochrome"),
        letter_case=raw.get("letterCase", "upper"),
        charset=charset,
    )


def _pixel_diff(actual: bytes, expected: bytes, width: int, limit: int = 8) -> str:
    """The first few differing pixels as ``(x, y): got -> want``."""
    lines = []
    for p in range(min(len(actual), len(expected)) // 3):
        got, want = actual[p * 3 : p * 3 + 3], expected[p * 3 : p * 3 + 3]
        if got != want:
            lines.append(f"  ({p % width}, {p // width}): got #{got.hex()} want #{want.hex()}")
            if len(lines) == limit:
                break
    if len(actual) != len(expected):
        lines.append(f"  length: got {len(actual)} bytes, want {len(expected)}")
    return "\n".join(lines)


# --- fixtures ---------------------------------------------------------------


def test_transition_cases_are_read_by_the_transition_tests():
    # tests/test_led_transitions.py checks every one of these frame by frame.
    assert len(LED_GOLDEN["transitions"]) == 10


# --- layout + raster goldens ------------------------------------------------


@pytest.mark.parametrize("case", LAYOUT_CASES, ids=[c["name"] for c in LAYOUT_CASES])
def test_layout_text_matches_fiestaui(case):
    layout = layout_message(case["message"], _spec(case["spec"]), _options(case))
    assert layout.text == case["text"]


@pytest.mark.parametrize("case", LAYOUT_CASES, ids=[c["name"] for c in LAYOUT_CASES])
def test_rgb888_frame_matches_fiestaui(case):
    frame = rasterize(layout_message(case["message"], _spec(case["spec"]), _options(case)))
    expected = base64.b64decode(case["frame"])
    assert (frame.width, frame.height) == (case["width"], case["height"])
    assert len(frame.pixels) == frame.width * frame.height * 3
    assert frame.pixels == expected, "first differing pixels:\n" + _pixel_diff(frame.pixels, expected, frame.width)


def test_golden_covers_the_parity_fixes():
    # FiestaUI 45496c9 added these after the first port; losing one on a
    # re-vendor would silently drop the behaviour it pins.
    names = {c["name"] for c in LAYOUT_CASES}
    assert {
        "plugin glyph overrides the face's",
        "tile-fallback icons bare, in a colour span, in a block",
        "blank-fallback icons bare, in a colour span, in a block",
        "block behind a drawn icon",
        "icon fallbacks in a block, monochrome",
    } <= names
    assert "lobby_flap" in {c["input"]["id"] for c in CHARSET_GOLDEN["sets"]}


def test_golden_frames_are_not_dark():
    # A frame of zeros would make the byte comparison weak; every case lights something.
    for case in LAYOUT_CASES:
        assert any(base64.b64decode(case["frame"])), case["name"]


# --- character-set materialisation -----------------------------------------


@pytest.mark.parametrize("case", CHARSET_GOLDEN["sets"], ids=[c["input"]["id"] for c in CHARSET_GOLDEN["sets"]])
def test_materialized_set_matches_fiestaui(case):
    assert materialize_character_set(case["input"]) == case["materialized"]


def test_builtin_sets_are_fiestauis_flattened_sets():
    assert set(BUILTIN_CHARACTER_SETS) == {"vestaboard_v1", "vestaboard_v2", "led_5x7", "led_3x5"}
    assert BUILTIN_CHARACTER_SETS["led_3x5"]["font"] == "3x5"


# --- device models ----------------------------------------------------------


def test_pixoo64_is_a_10_by_16_grid():
    spec = led_spec_for_model(DEVICE_MODELS["divoom_pixoo64"])
    assert spec == LedMatrixSpec(width=64, height=64, font="3x5")
    grid = grid_layout(spec.width, spec.height, spec.font)
    assert (grid.rows, grid.cols) == (10, 16)
    # 16 cols * 4 px - 1 = 63 wide, 10 rows * 6 px - 1 = 59 tall: leftovers centred.
    assert (grid.origin_x, grid.origin_y) == (0, 2)


def test_split_flap_models_have_no_led_spec():
    assert led_spec_for_model(DEVICE_MODELS["vestaboard_flagship"]) is None


def test_fonts_load_both_faces():
    assert set(LED_FONTS) == {"3x5", "5x7"}
    assert (LED_FONTS["3x5"].glyph_width, LED_FONTS["3x5"].glyph_height) == (3, 5)
    assert (LED_FONTS["5x7"].glyph_width, LED_FONTS["5x7"].glyph_height) == (5, 7)
