"""The font registry as families over the vendored faces, and integer glyph scaling."""

import pytest

from src.layout.fonts import (
    DEFAULT_FONT_FAMILY,
    FONT_FAMILIES,
    MAX_TEXT_SCALE,
    NAMED_SIZES,
    SizedFace,
    face_for_height,
    face_for_led_font,
    named_size_heights,
    size_ladder,
)
from src.led import matrix
from src.led.fonts import LED_FONTS
from src.led.matrix import LedRenderOptions, draw_glyph


def test_fiesta_family_maps_the_two_vendored_faces():
    fam = FONT_FAMILIES["fiesta"]
    assert [(f.id, f.pixel_height, f.kind) for f in fam.faces] == [("3x5", 5, "bitmap"), ("5x7", 7, "bitmap")]


def test_default_family_and_constants():
    assert DEFAULT_FONT_FAMILY == "fiesta" and MAX_TEXT_SCALE == 8
    assert NAMED_SIZES == ("small", "medium", "large", "xlarge")


def test_ladder_heights():
    assert [s.height for s in size_ladder(FONT_FAMILIES["fiesta"])][:8] == [5, 7, 10, 14, 15, 20, 21, 25]


def test_full_ladder_heights_for_fiesta():
    assert [s.height for s in size_ladder(FONT_FAMILIES["fiesta"])] == [
        5, 7, 10, 14, 15, 20, 21, 25, 28, 30, 35, 40, 42, 49, 56,
    ]  # fmt: skip


def test_ladder_tie_prefers_larger_face_at_smaller_scale():
    at_35 = [s for s in size_ladder(FONT_FAMILIES["fiesta"]) if s.height == 35]
    assert [(s.face.id, s.scale) for s in at_35] == [("5x7", 5)]


def test_sized_face_metrics_scale_with_the_face():
    sf = SizedFace(face=face_for_led_font("5x7"), scale=3)
    lf = LED_FONTS["5x7"]
    assert (sf.height, sf.advance, sf.gutter, sf.line_gap) == (
        lf.glyph_height * 3,
        (lf.glyph_width + lf.spacing_x) * 3,
        lf.spacing_x * 3,
        lf.spacing_y * 3,
    )


def test_face_for_height_exact_and_rounded_down():
    sf, exact = face_for_height(FONT_FAMILIES["fiesta"], 14)
    assert (sf.face.id, sf.scale, exact) == ("5x7", 2, True)
    sf, exact = face_for_height(FONT_FAMILIES["fiesta"], 12)
    assert (sf.face.id, sf.scale, exact) == ("3x5", 2, False)
    sf, exact = face_for_height(FONT_FAMILIES["fiesta"], 3)
    assert (sf.face.id, sf.scale, exact) == ("3x5", 1, False)


def test_face_for_led_font_returns_the_vendored_face():
    face = face_for_led_font("3x5")
    assert face.led_font is LED_FONTS["3x5"] and face.glyph_width == LED_FONTS["3x5"].glyph_width


def test_face_for_led_font_unknown_id_raises():
    with pytest.raises(KeyError):
        face_for_led_font("9x9")


@pytest.mark.parametrize(
    "h,default,expected",
    [
        (64, 5, (5, 5, 15, 30)),
        (64, 7, (5, 7, 15, 30)),
        (8, 5, (5, 5, 7, 7)),
        (32, 7, (5, 7, 10, 15)),
        (96, 7, (5, 7, 21, 42)),
    ],
)
def test_named_size_scale(h, default, expected):
    s = named_size_heights(surface_height=h, default_height=default, family=FONT_FAMILIES["fiesta"])
    assert (s["small"], s["medium"], s["large"], s["xlarge"]) == expected


def test_draw_glyph_scale_2_doubles_every_pixel():
    ops = []
    draw_glyph(ops, "A", 0, 0, LED_FONTS["3x5"], "#ffffff", LedRenderOptions(), scale=2)
    rows = ops[0].rows
    base = LED_FONTS["3x5"].glyphs["A"]
    assert len(rows) == 10 and rows[0] == "".join(c * 2 for c in base[0]) and rows[1] == rows[0]


def test_draw_glyph_scale_tile_rect():
    ops = []
    draw_glyph(ops, "tile:63", 0, 0, LED_FONTS["5x7"], "#fff", LedRenderOptions(), scale=3)
    assert (ops[0].w, ops[0].h) == (15, 21)


def test_draw_glyph_default_scale_is_unchanged():
    ops = []
    draw_glyph(ops, "A", 0, 0, LED_FONTS["3x5"], "#ffffff", LedRenderOptions())
    assert ops[0].rows == tuple(LED_FONTS["3x5"].glyphs["A"])


def test_public_aliases_for_cell_and_monochrome_helpers():
    assert matrix.cell_for_token is matrix._cell_for_token
    assert matrix.monochrome_rgba is matrix._monochrome_rgba
    assert {"cell_for_token", "monochrome_rgba"} <= set(matrix.__all__)
