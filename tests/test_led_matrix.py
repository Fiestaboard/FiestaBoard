"""Behaviour of ``src.led``: layout, raster and character-set materialisation.

Most cases are ports of FiestaUI's own ``src/lib/led-matrix.test.ts``
(45496c9), so the reference implementation's intent is checked one rule at a
time on top of the byte-for-byte goldens in ``test_led_parity.py``.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.led import (
    BUILTIN_CHARACTER_SETS,
    DEFAULT_LED_TEXT_COLOR,
    LED_FONTS,
    LedDrawOp,
    LedLayoutOptions,
    LedMatrixSpec,
    LedRenderOptions,
    draw_glyph,
    frame_to_ascii,
    frame_to_bits,
    glyph_key,
    grid_layout,
    layout_message,
    materialize_character_set,
    rasterize,
    resolve_hex_option,
    validate_character_set,
)
from src.markup import BOARD_ICONS, BoardToken, message_to_grid, parse_line

WHITE = (255, 255, 255)
RED = (0xEB, 0x40, 0x34)
YELLOW = (0xF8, 0xE7, 0x1C)
OFF = (0, 0, 0)

S3 = LedMatrixSpec(width=12, height=5, font="3x5")
WIDE = LedMatrixSpec(width=64, height=32)


def render(message, spec=WIDE, **options):
    return rasterize(layout_message(message, spec, LedLayoutOptions(**options)))


def pixel(frame, x, y):
    i = (y * frame.width + x) * 3
    return tuple(frame.pixels[i : i + 3])


def lit(frame):
    return sum(frame_to_bits(frame))


# --- grid -------------------------------------------------------------------


def test_grid_fits_whole_cells_and_centres_the_leftover():
    grid = grid_layout(32, 8, "3x5")
    assert (grid.width, grid.height, grid.font, grid.rows, grid.cols) == (32, 8, "3x5", 1, 8)
    assert (grid.origin_x, grid.origin_y) == (0, 1)
    assert (grid_layout(64, 64).rows, grid_layout(64, 64).cols, grid_layout(64, 64).font) == (8, 10, "5x7")


def test_grid_clamps_sizes():
    grid = grid_layout(0, 9999)
    assert (grid.width, grid.height, grid.cols) == (1, 256, 0)
    grid = grid_layout(float("nan"), 2.9)
    assert (grid.width, grid.height) == (1, 2)


def test_too_small_matrix_has_no_cells_and_renders_dark():
    layout = layout_message("A", LedMatrixSpec(width=2, height=2))
    assert (layout.grid.rows, layout.grid.cols, layout.cells, layout.text) == (0, 0, [], "")
    assert lit(rasterize(layout)) == 0


def test_unknown_font_is_an_error():
    with pytest.raises(KeyError):
        grid_layout(64, 32, "4x6")


# --- raster -----------------------------------------------------------------


def test_frame_is_rgb888_row_major_and_dark_for_an_empty_message():
    frame = render("")
    assert len(frame.pixels) == 64 * 32 * 3
    assert lit(frame) == 0


def test_glyph_lands_exactly_where_the_font_says():
    # 5x7 "I" top row is ".###." at origin (2, 0).
    frame = render("I")
    assert DEFAULT_LED_TEXT_COLOR == "#ffffff"
    assert [pixel(frame, x, 0) for x in (2, 3, 5, 6)] == [OFF, WHITE, WHITE, OFF]


def test_3x5_face_pixel_for_pixel():
    assert frame_to_ascii(render("HI!", S3)) == "\n".join(
        ["#.#.###..#..", "#.#..#...#..", "###..#...#..", "#.#..#......", "#.#.###..#.."]
    )


def test_uppercases_by_default_like_the_flap_board():
    assert render("hello").pixels == render("HELLO").pixels


def test_mixed_case_keeps_lowercase():
    assert layout_message("Hi", WIDE, LedLayoutOptions(letter_case="mixed")).text == "Hi"
    assert render("Hi", letter_case="mixed").pixels != render("HI").pixels


def test_tile_fills_its_glyph_box_not_its_gutter_and_black_is_off():
    frame = render("{63}{black}")
    assert lit(frame) == 5 * 7
    assert pixel(frame, 2, 0) == RED
    assert pixel(frame, 7, 0) == OFF


def test_text_past_the_grid_is_clipped_line_by_line():
    s = LedMatrixSpec(width=32, height=8, font="3x5")
    assert render("ABCDEFGHIJKLMNOP", s).pixels == render("ABCDEFGH", s).pixels
    assert render("AB\nCD", s).pixels == render("AB", s).pixels


def test_unparseable_text_colour_falls_back_to_white():
    assert pixel(render("I", text_color="rgba(255, 176, 0, 1)"), 3, 0) == WHITE


def test_text_colour_is_honoured():
    assert pixel(render("I", text_color="#ffb000"), 3, 0) == (0xFF, 0xB0, 0x00)


def test_unparseable_monochrome_is_treated_as_unset():
    assert render("{63}I", monochrome="amber").pixels == render("{63}I").pixels


# --- degree and heart -------------------------------------------------------


def test_degree_and_heart_each_draw_as_themselves():
    degree, heart = render("°", S3), render("♥", S3)
    assert frame_to_ascii(degree).split("\n")[0] == "##.........."
    assert frame_to_ascii(heart).split("\n")[0] == "#.#........."
    assert pixel(degree, 0, 0) == WHITE
    assert layout_message("72° ♥", LedMatrixSpec(width=24, height=5, font="3x5")).text == "72° ♥"


def test_every_spelling_of_the_heart_is_the_same_red_heart():
    typed = render("♥", S3)
    assert render("❤", S3).pixels == typed.pixels
    assert render("{icon:heart}", S3).pixels == typed.pixels
    assert pixel(typed, 0, 0) == RED
    assert pixel(render("{blue:♥}", S3), 0, 0) == RED
    assert pixel(render("♥"), 2, 2) == RED


# --- spans, icons, monochrome -----------------------------------------------


def test_colour_span_colours_only_its_letters():
    frame = render("{red:H}I", S3)
    assert (pixel(frame, 0, 0), pixel(frame, 4, 0)) == (RED, WHITE)


def test_numeric_and_hex_span_colours_and_a_tile_inside_a_span():
    frame = render("{#00ff00:A{63}}", S3)
    assert (pixel(frame, 1, 0), pixel(frame, 4, 0)) == ((0, 255, 0), RED)
    assert pixel(render("{67:I}", S3), 0, 0) == (0x4A, 0x90, 0xD9)


def test_off_colour_span_draws_unlit_letters():
    assert lit(render("{black:HI}", S3)) == 0


def test_legacy_tile_then_text_is_unchanged():
    frame = render("{red}I", S3)
    assert (pixel(frame, 0, 0), pixel(frame, 4, 0)) == (RED, WHITE)


def test_malformed_end_tag_is_literal_text_whose_braces_are_blank_cells():
    s = LedMatrixSpec(width=64, height=8, font="3x5")
    layout = layout_message("{/white:A}", s)
    assert layout.text == "/WHITE:A"
    assert [c.glyph for c in layout.cells[:2]] == [" ", "/"]
    assert render("{/white:A}", s).pixels == render("{/WHITE:A}", s).pixels
    assert render("{/white:A}", s).pixels != render("/WHITE:A", s).pixels


def test_icon_draws_its_own_glyph_in_its_own_colour_and_is_named():
    frame = render("{icon:sun}")
    assert pixel(frame, 4, 0) == YELLOW
    assert lit(frame) == "".join(LED_FONTS["5x7"].icons["sun"]).count("#")
    assert layout_message("{icon:sun} 72°", WIDE).text == "sun 72°"


def test_icon_without_a_glyph_draws_its_split_flap_fallback():
    assert lit(render("{icon:bus}", S3)) == 0  # fallback: blank
    snow = render("{icon:snow}", S3)  # fallback: violet tile
    assert BOARD_ICONS["snow"].fallback == "68"
    assert lit(snow) == 15
    assert pixel(snow, 0, 0) == (0x9B, 0x59, 0xB6)


def test_monochrome_turns_every_lit_pixel_the_panel_colour():
    mono = "#ff3b1f"
    frame = render("{63}{red:A}{icon:sun}♥I", monochrome=mono, text_color="#00ff00")
    colours = {pixel(frame, p % 64, p // 64) for p, bit in enumerate(frame_to_bits(frame)) if bit}
    assert colours == {(0xFF, 0x3B, 0x1F)}
    assert lit(render("{black}", monochrome=mono)) == 0
    assert frame_to_bits(frame) == frame_to_bits(render("{63}{red:A}{icon:sun}♥I"))


def test_block_span_lights_the_background_behind_the_glyph():
    frame = render("{black/white:I}", S3)
    assert pixel(frame, 0, 0) == OFF
    assert pixel(frame, 0, 1) == WHITE
    assert pixel(frame, 1, 1) == OFF
    assert pixel(frame, 3, 1) == OFF  # a lone block cell keeps its gutter dark
    rb = render("{red/blue:I}", S3)
    assert (pixel(rb, 1, 1), pixel(rb, 0, 1)) == (RED, (0x4A, 0x90, 0xD9))


def test_block_run_lights_the_gutter_between_its_cells():
    frame = render("{black/white:II}", S3)
    assert (pixel(frame, 3, 1), pixel(frame, 7, 1)) == (WHITE, OFF)
    assert layout_message("{black/white:ON} AIR", WIDE).text == "ON AIR"


def test_block_rows_join_vertically_only_with_the_same_background():
    s = LedMatrixSpec(width=4, height=11, font="3x5")
    same = render("{black/white:I}\n{black/white:I}", s)
    assert pixel(same, 0, 5) == WHITE  # the row gutter between the two cells
    differ = render("{black/white:I}\n{black/blue:I}", s)
    assert pixel(differ, 0, 5) == OFF


def test_block_span_on_a_monochrome_panel_is_inverse_video():
    mono = "#ff3b1f"
    frame = render("{red/blue:I}", S3, monochrome=mono)
    assert (pixel(frame, 1, 1), pixel(frame, 0, 1)) == (OFF, (0xFF, 0x3B, 0x1F))
    assert frame_to_bits(frame) == frame_to_bits(render("{black/white:I}", S3))


def test_frame_to_bits_is_one_where_any_channel_is_lit():
    bits = frame_to_bits(render("{63}", LedMatrixSpec(width=8, height=5, font="3x5")))
    assert len(bits) == 40
    assert list(bits[:8]) == [1, 1, 1, 0, 0, 0, 0, 0]
    assert sum(bits) == 15


# --- text -------------------------------------------------------------------


def test_text_is_the_clipped_grid_with_tiles_blank_and_whitespace_collapsed():
    s = LedMatrixSpec(width=32, height=8, font="3x5")
    assert layout_message("  {63}A   B  {icon:up}xyz", s).text == "A B"


def test_undrawable_character_is_a_blank_cell():
    layout = layout_message("A€B", S3)
    assert layout.text == "A B"
    assert layout.cells[1].glyph == " "


# --- rich tokens in ---------------------------------------------------------


def test_a_rich_token_grid_lays_out_like_its_markup():
    message = "{red:HOT} {black/white:UV}\n{icon:sun} 72°"
    rows = [parse_line(line, extended_markup=True) for line in message.split("\n")]
    assert rasterize(layout_message(rows, WIDE)).pixels == render(message).pixels
    assert layout_message(rows, WIDE).text == layout_message(message, WIDE).text


def test_a_padded_grid_from_message_to_grid_lays_out_like_its_markup():
    grid = message_to_grid("{icon:sun} HI", 5, 10, extended_markup=True, device_type="panel")
    # message_to_grid draws code 62 as the board's flap; the tokens without one agree.
    assert rasterize(layout_message(grid, WIDE)).pixels == render("{icon:sun} HI").pixels


def test_token_rows_past_the_grid_are_clipped():
    rows = [parse_line("ABCDEFGHIJKLMNOP"), parse_line("CD")]
    s = LedMatrixSpec(width=32, height=8, font="3x5")
    assert rasterize(layout_message(rows, s)).pixels == render("ABCDEFGH", s).pixels


# --- plugin character sets --------------------------------------------------


ACME = {
    "id": "acme_v1",
    "label": "ACME",
    "extends": "led_3x5",
    "chars": ["A", "€"],
    "glyphs": {"€": [".##", "##.", "#..", "##.", ".##"]},
}


def test_custom_glyph_draws_where_the_face_has_none():
    set_ = materialize_character_set(ACME)
    layout = layout_message("€", S3, LedLayoutOptions(charset=set_))
    assert layout.text == "€"
    assert frame_to_ascii(rasterize(layout)).split("\n")[:2] == [".##.........", "##.........."]


def test_custom_glyph_wins_over_the_shared_face():
    # Plan D17 rule 5; FiestaUI glyphRows is `custom ?? face` since 45496c9
    # (golden "plugin glyph overrides the face's" draws a rounded 0).
    set_ = materialize_character_set({**ACME, "glyphs": {"A": ["###", "###", "###", "###", "###"]}})
    frame = rasterize(layout_message("A", S3, LedLayoutOptions(charset=set_)))
    assert lit(frame) == 15


def test_materialise_inherits_omitted_fields_and_never_the_version():
    set_ = materialize_character_set({"id": "x_v1", "extends": "vestaboard_v2"})
    parent = BUILTIN_CHARACTER_SETS["vestaboard_v2"]
    assert set_["version"] == 1 and parent["version"] == 2
    assert set_["chars"] == parent["chars"]
    assert set_["code62Glyph"] == "heart"
    assert set_["label"] == parent["label"]
    assert set_["extends"] == "vestaboard_v2"


def test_materialise_replaces_arrays_wholesale():
    assert materialize_character_set({"id": "x_v1", "extends": "led_3x5", "chars": ["A"]})["chars"] == ["A"]


def test_materialise_extends_a_known_plugin_set():
    parent = materialize_character_set(ACME)
    child = materialize_character_set({"id": "acme_v2", "extends": "acme_v1", "version": 2}, known=[parent])
    assert child["glyphs"] == ACME["glyphs"] and child["version"] == 2


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        ({"id": "x_v1", "extends": "nope"}, 'extends unknown set "nope"'),
        ({"id": "led_3x5", "extends": "led_3x5"}, "extends itself"),
        ({"id": "x_v1", "label": "X"}, "is invalid"),
        ({"id": "x_v1", "extends": "led_3x5", "glyphs": {"€": ["###"] * 5}}, "glyphs.€: not in chars"),
        ({"id": "x_v1", "extends": "led_3x5", "chars": ["€"], "glyphs": {"€": ["#"] * 5}}, "5 rows of 3"),
        ({"id": "x_v1", "extends": "led_3x5", "icons": ["moon"]}, "icons:"),
    ],
)
def test_materialise_rejects_bad_declarations(declaration, message):
    with pytest.raises(ValueError, match=message):
        materialize_character_set(declaration, known=[])


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        ({"id": "x_v1", "extends": "led_3x5", "colour": "no"}, "colour: not a character set field"),
        ({"id": "x_v1", "extends": "led_3x5", "glyph": {"A": ["###"] * 5}}, "glyph: not a character set field"),
        ({"id": "x_v1", "extends": "led_3x5", "tiles": 1}, "tiles: a boolean"),
        ({"id": "Bad Id", "extends": "led_3x5"}, "id: a lowercase identifier"),
    ],
)
def test_materialise_validates_the_declaration_before_inheriting(declaration, message):
    # FiestaUI 45496c9: a typo'd key is a field the author meant, never dropped.
    with pytest.raises(ValueError, match=message):
        materialize_character_set(declaration)


def test_a_partial_declaration_with_a_stray_key_is_reported_alone():
    declaration = {"id": "x_v1", "extends": "led_3x5", "colour": "no"}
    assert validate_character_set(declaration).errors == ["colour: not a character set field"]


def test_version_is_never_inherited_down_a_plugin_chain():
    ticker = materialize_character_set({"id": "ticker", "extends": "led_3x5", "version": 3})
    child = materialize_character_set({"id": "ticker_child", "extends": "ticker"}, known=[ticker])
    assert (ticker["version"], child["version"]) == (3, 1)
    grandchild = materialize_character_set(
        {"id": "ticker_grandchild", "extends": "ticker_child", "version": 7}, known=[ticker, child]
    )
    assert grandchild["version"] == 7
    assert grandchild["chars"] == ticker["chars"] == BUILTIN_CHARACTER_SETS["led_3x5"]["chars"]


def test_a_complete_set_needs_no_parent():
    full = dict(BUILTIN_CHARACTER_SETS["vestaboard_v1"])
    full["id"] = "flap_copy_v1"
    assert materialize_character_set(full)["chars"] == full["chars"]


def test_validate_reports_every_problem():
    result = validate_character_set({"id": "Bad", "version": 0, "tiles": "yes"})
    assert not result.ok
    assert any(e.startswith("id:") for e in result.errors)
    assert any(e.startswith("version:") for e in result.errors)
    assert any(e.startswith("tiles:") for e in result.errors)
    assert not validate_character_set([]).ok


# --- icons in blocks and fallbacks (FiestaUI 45496c9) -----------------------

VIOLET = (0x9B, 0x59, 0xB6)
AMBER = (0xFF, 0xB0, 0x00)


def test_block_lights_behind_a_tile_fallback_icon_and_the_tile_draws_on_top():
    tile = render("{black/white:{icon:snow}A}", S3)
    assert pixel(tile, 0, 0) == VIOLET
    assert pixel(tile, 2, 4) == VIOLET
    assert pixel(tile, 3, 0) == WHITE  # the joined gutter is the block's
    assert pixel(tile, 4, 0) == WHITE  # "A" row 0 is ".#.": x=4 is background
    assert pixel(tile, 5, 0) == OFF


def test_a_drawn_icon_sits_on_its_block_field_in_its_own_colour():
    sun = render("{black/white:{icon:sun}}")
    assert (pixel(sun, 4, 0), pixel(sun, 2, 0)) == (YELLOW, WHITE)


def test_a_blank_fallback_icon_is_an_empty_block_cell():
    blank = render("{black/white:{icon:bus}A}", S3)
    assert (pixel(blank, 0, 0), pixel(blank, 3, 0)) == (WHITE, WHITE)


def test_icons_in_a_monochrome_block_are_inverse_video():
    mono = "#ffb000"
    tile = render("{black/white:{icon:snow}A}", S3, monochrome=mono)
    assert (pixel(tile, 0, 0), pixel(tile, 3, 0)) == (OFF, AMBER)
    sun = render("{black/white:{icon:sun}}", monochrome=mono)
    assert (pixel(sun, 4, 0), pixel(sun, 2, 0)) == (OFF, AMBER)


def test_a_colour_span_around_a_tile_fallback_icon_changes_nothing():
    assert render("{red:{icon:snow}}", S3).pixels == render("{icon:snow}", S3).pixels


def test_an_icon_draws_its_character_fallback_when_the_face_lacks_it():
    # Both built-in faces carry every character-fallback icon (up, down, fog),
    # so this branch is reached with a face stripped of its icons, as FiestaUI does.
    face = replace(LED_FONTS["3x5"], icons={})
    ops: list[LedDrawOp] = []
    key = glyph_key(BoardToken("char", value="+", icon="up"))
    draw_glyph(ops, key, 0, 0, face, "#ffffff", LedRenderOptions())
    assert ops == [LedDrawOp("glyph", 0, 0, "#ffffff", rows=tuple(LED_FONTS["3x5"].glyphs["+"]))]


# --- colour options ---------------------------------------------------------


@pytest.mark.parametrize("value", ["#ffb000", "#FFB000", "ffb000", "  #FfB000\n", "FFB000 "])
def test_hex_option_normalises_to_lowercase_hash_rrggbb(value):
    assert resolve_hex_option(value, None) == "#ffb000"


@pytest.mark.parametrize(
    "value", ["", " ", "#", "#fff", "fff", "#ffb0000", "#ffb00g", "rgba(255, 176, 0, 1)", "red", "#ff b000"]
)
def test_hex_option_falls_back_for_anything_but_six_hex_digits(value):
    assert resolve_hex_option(value, "#123456") == "#123456"
    assert resolve_hex_option(value, None) is None


def test_hex_option_of_none_is_the_fallback():
    assert resolve_hex_option(None, "#123456") == "#123456"


def test_layout_carries_normalised_colours():
    assert layout_message("A", S3, LedLayoutOptions(monochrome=" FFB000 ")).options.monochrome == "#ffb000"
    assert layout_message("A", S3, LedLayoutOptions(text_color="FFB000")).cells[0].color == "#ffb000"
    assert layout_message("A", S3, LedLayoutOptions(text_color="#fff")).cells[0].color == DEFAULT_LED_TEXT_COLOR
    assert layout_message("A", S3, LedLayoutOptions(monochrome="#fff")).options.monochrome is None
