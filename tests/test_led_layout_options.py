"""LED ``tile_gap`` and ``block_padding`` (plan D23; FiestaUI #338, design spec §7.6).

Ports of FiestaUI's ``led-matrix.test.ts`` / ``led-transitions.test.ts`` /
``devices.test.ts`` cases for the two byte-changing layout options, one rule
at a time, on top of the byte-for-byte goldens in ``test_led_parity.py`` and
``test_led_transitions.py``. Grid used throughout: 3 x 2 cells of the 3x5
face on a 14x13 matrix with a 1-px margin, so cell (r, c)'s glyph box is
x 1+4c..3+4c, y 1+6r..5+6r; the column gutters are x = 4 and 8, the row
gutter y = 6, the margin x = 0 / 13 and y = 0 / 12.
"""

from __future__ import annotations

import copy

import pytest

from src.fiestaui import builtin_device_models
from src.led import (
    DEFAULT_LED_BLOCK_PADDING,
    DEFAULT_LED_TILE_GAP,
    LED_BLOCK_PADDINGS,
    LED_TILE_GAPS,
    LED_TRANSITION_KINDS,
    LedLayoutOptions,
    LedMatrixSpec,
    LedRenderOptions,
    LedTransitionSpec,
    frame_to_bits,
    grid_layout,
    layout_message,
    layout_policy_for_model,
    led_charset_for_font,
    led_layout_options_for_model,
    led_spec_for_model,
    model_with_led_font,
    plan_transition,
    rasterize,
    transition_frames,
)
from src.markup import parse_line
from src.outputs.fiestaui import validate_device_model

SPEC = LedMatrixSpec(width=14, height=13, font="3x5")
OFF = (0, 0, 0)
RED = (0xEB, 0x40, 0x34)
GREEN = (0x7E, 0xD3, 0x21)
BLUE = (0x4A, 0x90, 0xD9)
WHITE = (255, 255, 255)
AMBER = (0xFF, 0xB0, 0x00)
MODELS = builtin_device_models()


def render(message, spec=SPEC, **options):
    return rasterize(layout_message(message, spec, LedLayoutOptions(**options)))


def pixel(frame, x, y):
    i = (y * frame.width + x) * 3
    return tuple(frame.pixels[i : i + 3])


def lit(frame):
    return sum(frame_to_bits(frame))


# --- defaults ---------------------------------------------------------------


def test_the_renderer_defaults_are_todays_gap_and_no_padding():
    assert (DEFAULT_LED_TILE_GAP, DEFAULT_LED_BLOCK_PADDING) == ("gap", 0)
    assert (LED_TILE_GAPS, LED_BLOCK_PADDINGS) == (("gap", "fill"), (0, 1))


@pytest.mark.parametrize(
    "message", ["{63}{63}{66}\n{63}{66}{66}", "{black/white:II}\n{black/white:I}", "{black/white:A}{white}{63}"]
)
def test_gap_and_no_padding_draw_exactly_what_was_drawn_before(message):
    plain = render(message)
    assert render(message, tile_gap="gap", block_padding=0).pixels == plain.pixels
    spec = LedMatrixSpec(14, 13, "3x5", tile_gap="gap", block_padding=0)
    assert rasterize(layout_message(message, spec)).pixels == plain.pixels
    assert layout_message(message, SPEC, LedLayoutOptions(tile_gap="gap", block_padding=0)).options == (
        LedRenderOptions()
    )


@pytest.mark.parametrize("tile_gap, block_padding", [("wide", 2), (None, True), ("FILL", "1")])
def test_a_value_that_is_not_one_of_the_two_is_unset(tile_gap, block_padding):
    assert render("{63}{63}", tile_gap=tile_gap, block_padding=block_padding).pixels == render("{63}{63}").pixels


# --- tile_gap "fill" ----------------------------------------------------------


def test_fill_lights_same_colour_tile_gutters_only_and_never_the_margin():
    frame = render("{63}{63}{66}\n{63}{66}{66}", tile_gap="fill")
    assert pixel(frame, 4, 1) == RED  # red | red
    assert pixel(frame, 8, 1) == OFF  # red | green
    assert pixel(frame, 2, 6) == RED  # red over red
    assert pixel(frame, 6, 6) == OFF  # red over green
    assert pixel(frame, 10, 6) == GREEN  # green over green
    assert pixel(frame, 4, 6) == OFF  # corner: red red / red green
    assert pixel(frame, 8, 6) == OFF  # corner: red green / green green
    assert all(pixel(frame, x, 0) == OFF for x in range(14))
    assert all(pixel(frame, 0, y) == OFF for y in range(13))


def test_fill_moves_nothing_cells_grid_and_text_unchanged():
    plain = layout_message("{63}{63}{66}\n{63}{66}{66}", SPEC)
    filled = layout_message("{63}{63}{66}\n{63}{66}{66}", SPEC, LedLayoutOptions(tile_gap="fill"))
    assert (filled.cells, filled.grid, filled.text) == (plain.cells, plain.grid, plain.text)
    assert filled.options == LedRenderOptions(tile_gap="fill")


def test_fill_lights_a_corner_only_when_all_four_cells_are_one_field():
    assert pixel(render("{63}{63}\n{63}{63}", tile_gap="fill"), 4, 6) == RED
    ell = render("{63}{63}\n{63}", tile_gap="fill")
    assert (pixel(ell, 4, 1), pixel(ell, 2, 6), pixel(ell, 4, 6)) == (RED, RED, OFF)


def test_fill_differs_from_gap_for_blocks_only_at_the_corner_under_a_longer_upper_row():
    assert pixel(render("{black/white:II}\n{black/white:I}"), 4, 6) == WHITE
    assert pixel(render("{black/white:II}\n{black/white:I}", tile_gap="fill"), 4, 6) == OFF
    slab = "{black/white:II}\n{black/white:II}"
    assert render(slab, tile_gap="fill").pixels == render(slab).pixels


def test_fill_merges_a_tile_with_a_same_colour_block_and_never_another_colour():
    frame = render("{white}{black/white:A}{red/blue:B}\n{white}{66}{red:I}", tile_gap="fill")
    assert pixel(frame, 4, 1) == WHITE  # white tile | white block
    assert pixel(frame, 8, 1) == OFF  # white block | blue block
    assert pixel(frame, 2, 6) == WHITE  # white tile over white tile
    assert pixel(frame, 6, 6) == OFF  # white block over green tile
    assert pixel(frame, 8, 7) == OFF  # green tile | red letters: a glyph has no field


def test_fill_ignores_off_tiles_and_treats_a_tile_fallback_icon_as_its_tile():
    assert pixel(render("{70}{70}", tile_gap="fill"), 4, 1) == OFF
    assert pixel(render("{icon:snow}{icon:snow}", tile_gap="fill"), 4, 1) == (0x9B, 0x59, 0xB6)


# --- block_padding 1 --------------------------------------------------------


def test_padding_grows_a_one_pixel_ring_corners_included_glyphs_untouched():
    padded = render(" {black/white:I} ", block_padding=1)
    for x in range(4, 9):
        assert pixel(padded, x, 0) == WHITE and pixel(padded, x, 6) == WHITE, x
    for y in range(7):
        assert pixel(padded, 4, y) == WHITE and pixel(padded, 8, y) == WHITE, y
    assert pixel(padded, 3, 0) == OFF  # one pixel, not two
    assert pixel(padded, 3, 1) == OFF  # the blank neighbour's glyph box is never claimed
    assert (pixel(padded, 5, 1), pixel(padded, 6, 1)) == (OFF, OFF)  # "I" row 0 is ###
    assert pixel(padded, 5, 2) == WHITE  # ".#." -> x=5 is field
    assert lit(padded) - lit(render(" {black/white:I} ")) == 20  # 2*5 + 2*7 - 4
    assert layout_message("{black/white:I}", SPEC, LedLayoutOptions(block_padding=1)).options == LedRenderOptions(
        block_padding=1
    )


def test_padding_never_leaves_the_matrix():
    edge = render("{black/white:OPEN}", LedMatrixSpec(15, 5, "3x5"), block_padding=1)
    assert edge.width == 15 and len(edge.pixels) == 15 * 5 * 3
    assert pixel(edge, 0, 2) == OFF  # "O" row 2 is #.#: x=0 is the glyph
    assert pixel(edge, 3, 2) == WHITE  # the run's own gutter


def test_padding_leaves_the_gutter_two_different_colours_would_share_unlit():
    two = render("{black/white:A}{white/red:B}", block_padding=1)
    assert (pixel(two, 4, 1), pixel(two, 4, 0), pixel(two, 4, 6)) == (OFF, OFF, OFF)
    assert (pixel(two, 0, 1), pixel(two, 8, 1)) == (WHITE, RED)
    stacked = render("{black/white:A}\n{white/blue:B}", block_padding=1)
    assert (pixel(stacked, 2, 6), pixel(stacked, 0, 6)) == (OFF, OFF)
    assert (pixel(stacked, 0, 5), pixel(stacked, 0, 7)) == (WHITE, BLUE)
    slab = render("{black/white:A}\n{black/white:B}", block_padding=1)
    assert (pixel(slab, 0, 6), pixel(slab, 4, 6)) == (WHITE, WHITE)


def test_padding_beside_tiles_merges_with_its_colour_and_is_vetoed_by_another():
    frame = render("{black/white:A}{63}\n{white}{63}", block_padding=1)
    assert pixel(frame, 4, 1) == OFF  # white block | red tile
    assert pixel(frame, 4, 0) == OFF  # the corner above borders the red tile too
    assert pixel(frame, 4, 6) == OFF  # and the four-way corner below
    assert pixel(frame, 2, 6) == WHITE  # white block over white tile
    assert pixel(frame, 0, 6) == WHITE  # the margin pixel level with it
    assert pixel(frame, 0, 7) == OFF  # a tile's own margin is not padded
    assert pixel(frame, 6, 6) == OFF  # padding does not fill tile gutters...
    assert pixel(render("{black/white:A}{63}\n{white}{63}", block_padding=1, tile_gap="fill"), 6, 6) == RED  # fill does


# --- monochrome, spec defaults, cells-in --------------------------------------


def test_monochrome_merges_every_field_and_keeps_inverse_glyphs_crisp():
    frame = render("{black/white:I}{63}\n{66}{70}", monochrome="#ffb000", tile_gap="fill", block_padding=1)
    assert pixel(frame, 4, 1) == AMBER  # block | tile
    assert pixel(frame, 2, 6) == AMBER  # block over tile
    assert pixel(frame, 4, 6) == AMBER  # corner: padding; the off tile is no field
    assert pixel(frame, 6, 6) == OFF  # red tile over off tile: fill needs every cell lit
    assert pixel(frame, 0, 1) == AMBER  # padding
    assert pixel(frame, 2, 1) == OFF  # "I" row 0: the glyph is unlit
    same_colour = render("{black/white:I}{white}\n{white}{70}", tile_gap="fill", block_padding=1)
    assert frame_to_bits(frame) == frame_to_bits(same_colour)
    assert frame_to_bits(frame) != frame_to_bits(render("{black/white:I}{63}\n{66}{70}", monochrome="#ffb000"))


def test_the_spec_carries_a_devices_defaults_and_an_explicit_option_wins():
    message = "{black/white:A}{white}{63}"
    device = LedMatrixSpec(14, 13, "3x5", tile_gap="fill", block_padding=1)
    assert rasterize(layout_message(message, device)).pixels == render(message, tile_gap="fill", block_padding=1).pixels
    assert render(message, device, tile_gap="gap", block_padding=0).pixels == render(message).pixels
    assert layout_message(message, LedMatrixSpec(14, 13, "3x5", tile_gap="fill")).options == LedRenderOptions(
        tile_gap="fill"
    )


def test_cells_in_draws_the_same_ops_as_message_in():
    message = "{black/white:A}{white}{63}\n{white}{63}{63}"
    cells = [parse_line(line, 3, extended_markup=True) for line in message.split("\n")]
    options = LedLayoutOptions(tile_gap="fill", block_padding=1)
    assert layout_message(cells, SPEC, options).ops == layout_message(message, SPEC, options).ops


# --- through a transition -----------------------------------------------------

TSPEC = LedMatrixSpec(26, 7, "3x5")
TOPTS = LedLayoutOptions(tile_gap="fill", block_padding=1)


def _from_to():
    return (
        layout_message("{black/white:ON} {63}{63}", TSPEC, TOPTS),
        layout_message("{black/white:OK} {66}{66}", TSPEC, TOPTS),
    )


@pytest.mark.parametrize("kind", LED_TRANSITION_KINDS)
def test_every_kind_settles_on_the_static_frame_with_both_options(kind):
    before, after = _from_to()
    settled = rasterize(after)
    tr = plan_transition(before, after, LedTransitionSpec(kind=kind, step_ms=20, duration_ms=200))
    assert tr.frame_at(tr.duration_ms).pixels == settled.pixels
    assert tr.frame_at(tr.duration_ms + 1).pixels == settled.pixels
    assert transition_frames(tr, 30)[-1].pixels == settled.pixels


def test_a_flips_midway_layouts_carry_the_options_so_fields_never_flicker():
    before, after = _from_to()
    tr = plan_transition(before, after, LedTransitionSpec(kind="flip", step_ms=80, scramble_steps=3, stagger=0))
    for t in range(0, int(tr.duration_ms), 20):
        frame, layout = tr.frame_at(t), tr.layout_at(t)
        assert (layout.options.tile_gap, layout.options.block_padding) == ("fill", 1), t
        assert pixel(frame, 0, 0) == WHITE, t  # padding corner
        assert pixel(frame, 2, 0) == WHITE, t  # padding above
        assert pixel(frame, 4, 3) == WHITE, t  # gutter inside the block run
        assert pixel(frame, 8, 3) == WHITE, t  # padding after the run
        assert pixel(frame, 9, 3) == OFF, t
        tiles = [c.glyph for c in layout.cells[3:5]]
        if tiles[0] == tiles[1] and tiles[0].startswith("tile:"):
            assert pixel(frame, 16, 3) != OFF, t


@pytest.mark.parametrize("kind", ["cascade", "wipe", "dissolve"])
def test_cascade_and_per_pixel_kinds_keep_the_fields(kind):
    before, after = _from_to()
    tr = plan_transition(before, after, LedTransitionSpec(kind=kind, duration_ms=200))
    for t in (0, 50, 100, 150, 199):
        frame = tr.frame_at(t)
        assert (pixel(frame, 0, 0), pixel(frame, 4, 3)) == (WHITE, WHITE), t


# --- device models: layoutOptions -----------------------------------------------


def _led_models():
    return [m for m in MODELS.values() if m["technology"] == "led_matrix"]


def test_every_builtin_led_model_allows_both_with_todays_defaults_and_split_flap_declares_none():
    assert _led_models()
    for m in _led_models():
        declared = {k: v for k, v in m["layoutOptions"].items() if k != "font"}
        assert declared == {
            "tileGap": {"allowed": ["gap", "fill"], "default": "gap"},
            "blockPadding": {"allowed": [0, 1], "default": 0},
        }, m["id"]
        policy = layout_policy_for_model(m)
        assert {k: v for k, v in policy.items() if k != "font"} == declared, m["id"]
        spec = led_spec_for_model(m)
        assert (spec.tile_gap, spec.block_padding) == ("gap", 0), m["id"]
    for m in MODELS.values():
        if m["technology"] == "split_flap":
            assert "layoutOptions" not in m, m["id"]


def test_an_undeclared_field_is_unrestricted_and_a_declared_one_narrows():
    base = {k: v for k, v in MODELS["hub75_64x32"].items() if k != "layoutOptions"}
    assert layout_policy_for_model(base) == {
        "tileGap": {"allowed": ["gap", "fill"], "default": "gap"},
        "blockPadding": {"allowed": [0, 1], "default": 0},
        "font": {"allowed": ["5x7"], "default": "5x7"},
    }
    fill_only = {**base, "layoutOptions": {"tileGap": {"allowed": ["fill"]}}}
    assert layout_policy_for_model(fill_only)["tileGap"] == {"allowed": ["fill"], "default": "fill"}
    padded = {
        **base,
        "layoutOptions": {"blockPadding": {"allowed": [0, 1], "default": 1}, "tileGap": {"allowed": ["fill", "gap"]}},
    }
    assert layout_policy_for_model(padded) == {
        "tileGap": {"allowed": ["fill", "gap"], "default": "gap"},
        "blockPadding": {"allowed": [0, 1], "default": 1},
        "font": {"allowed": ["5x7"], "default": "5x7"},
    }
    assert led_spec_for_model(padded) == LedMatrixSpec(64, 32, "5x7", tile_gap="gap", block_padding=1)


def test_a_boards_choice_is_honoured_when_allowed_and_falls_back_to_the_default_otherwise():
    base = MODELS["divoom_pixoo64"]
    assert led_layout_options_for_model(base) == ("gap", 0, "3x5", [])
    assert led_layout_options_for_model(base, tile_gap="fill", block_padding=1) == ("fill", 1, "3x5", [])
    gap_only = {
        **base,
        "layoutOptions": {"tileGap": {"allowed": ["gap"]}, "blockPadding": {"allowed": [1], "default": 1}},
    }
    chosen = led_layout_options_for_model(gap_only, tile_gap="fill", block_padding=0)
    assert (chosen.tile_gap, chosen.block_padding) == ("gap", 1)
    assert chosen.ignored == [
        'tileGap="fill" is not a value divoom_pixoo64 allows (tileGap: "gap"); using "gap"',
        "blockPadding=0 is not a value divoom_pixoo64 allows (blockPadding: 1); using 1",
    ]
    assert led_layout_options_for_model(gap_only) == ("gap", 1, "3x5", [])


def test_a_garbage_board_value_is_ignored_never_raised():
    chosen = led_layout_options_for_model(MODELS["divoom_pixoo64"], tile_gap="seamless", block_padding=True)
    assert (chosen.tile_gap, chosen.block_padding) == ("gap", 0)
    assert len(chosen.ignored) == 2


def test_the_vendored_schema_checks_a_layout_options_declaration():
    base = copy.deepcopy(MODELS["divoom_pixoo64"])
    assert validate_device_model(base) == []
    assert validate_device_model({**base, "layoutOptions": {}}) == []
    assert validate_device_model({**base, "layoutOptions": {"tileGap": {"allowed": ["fill"]}}}) == []
    for bad in (
        "fill",
        {"gutter": {"allowed": ["fill"]}},
        {"tileGap": "fill"},
        {"tileGap": {"allowed": []}},
        {"tileGap": {"allowed": ["gap", "gap"]}},
        {"tileGap": {"allowed": ["gap", "wide"]}},
        {"blockPadding": {"allowed": [0, 2]}},
        {"blockPadding": {"allowed": ["1"]}},
        {"tileGap": {"allowed": ["gap"], "values": 1}},
        {"tileGap": {"allowed": ["gap"], "default": "fill"}},
    ):
        assert validate_device_model({**base, "layoutOptions": bad}), bad
    flagship = copy.deepcopy(MODELS["vestaboard_flagship"])
    assert validate_device_model({**flagship, "layoutOptions": {"tileGap": {"allowed": ["gap"]}}})


# --- device models: layoutOptions.font (FiestaUI #342, per-board text size) ------------
#
# Ports of FiestaUI devices.test.ts's face-choice cases. hub75_64x32 is a 5x7
# model that declares no face choice; the built-in Pixoo 64 offers both, keeps
# font 3x5 / led_3x5 for boards that chose nothing, and gives a NEW board 5x7.

PIXOO = MODELS["divoom_pixoo64"]
HUB75 = MODELS["hub75_64x32"]


def test_the_builtin_pixoo_offers_both_faces_and_keeps_its_own():
    assert PIXOO["layoutOptions"]["font"] == {"allowed": ["5x7", "3x5"], "default": "5x7"}
    assert (PIXOO["font"], PIXOO["charset"]) == ("3x5", "led_3x5")
    assert validate_device_model(copy.deepcopy(PIXOO)) == []


def test_the_face_policy_is_the_declared_choice():
    assert layout_policy_for_model(PIXOO)["font"] == {"allowed": ["5x7", "3x5"], "default": "5x7"}


def test_an_undeclared_face_choice_allows_only_the_models_own_face():
    # Unlike tileGap / blockPadding, undeclared is NOT unrestricted: a face changes the grid.
    assert layout_policy_for_model(HUB75)["font"] == {"allowed": ["5x7"], "default": "5x7"}
    assert layout_policy_for_model({**HUB75, "font": "3x5"})["font"] == {"allowed": ["3x5"], "default": "3x5"}


def test_a_model_without_a_font_offers_the_renderers_face():
    faceless = {k: v for k, v in HUB75.items() if k != "font"}
    assert layout_policy_for_model(faceless)["font"] == {"allowed": ["5x7"], "default": "5x7"}


def test_a_declared_face_choice_without_a_default_defaults_to_the_models_own_face():
    pixoo = {**PIXOO, "layoutOptions": {**PIXOO["layoutOptions"], "font": {"allowed": ["5x7", "3x5"]}}}
    assert layout_policy_for_model(pixoo)["font"] == {"allowed": ["5x7", "3x5"], "default": "3x5"}


def test_led_charset_for_font_is_the_builtin_set_drawn_in_that_face():
    assert led_charset_for_font("5x7") == "led_5x7"
    assert led_charset_for_font("3x5") == "led_3x5"


def test_led_charset_for_font_raises_for_a_face_no_builtin_set_draws():
    with pytest.raises(ValueError, match='No built-in LED character set is drawn in font "7x9"'):
        led_charset_for_font("7x9")


def test_model_with_led_font_swaps_the_face_and_its_set_and_nothing_else():
    large = model_with_led_font(PIXOO, "5x7")
    assert (large["font"], large["charset"]) == ("5x7", "led_5x7")
    assert {k: v for k, v in large.items() if k not in ("font", "charset")} == {
        k: v for k, v in PIXOO.items() if k not in ("font", "charset")
    }
    assert (PIXOO["font"], PIXOO["charset"]) == ("3x5", "led_3x5")


def test_model_with_led_font_returns_the_model_itself_for_its_own_face():
    assert model_with_led_font(PIXOO, "3x5") is PIXOO
    assert model_with_led_font(HUB75, "5x7") is HUB75


def test_model_with_led_font_raises_for_a_face_the_model_does_not_offer():
    with pytest.raises(ValueError) as raised:
        model_with_led_font(HUB75, "3x5")
    assert str(raised.value) == 'hub75_64x32 does not offer font "3x5" (font: "5x7")'


def test_led_spec_for_model_without_a_font_is_the_models_own_face():
    assert led_spec_for_model(PIXOO) == LedMatrixSpec(64, 64, "3x5", tile_gap="gap", block_padding=0)


def test_led_spec_for_model_draws_a_chosen_face_the_model_offers():
    spec = led_spec_for_model(PIXOO, font="5x7")
    assert spec == LedMatrixSpec(64, 64, "5x7", tile_gap="gap", block_padding=0)
    grid = grid_layout(spec.width, spec.height, spec.font)
    assert (grid.rows, grid.cols) == (8, 10)


def test_led_spec_for_model_raises_for_a_face_the_model_does_not_offer():
    with pytest.raises(ValueError, match=r'hub75_64x32 does not offer font "3x5" \(font: "5x7"\)'):
        led_spec_for_model(HUB75, font="3x5")


def test_an_unset_board_face_is_the_models_own_not_the_new_board_default():
    # layoutOptions.font.default (5x7) is what a NEW board gets; a board that
    # chose nothing draws exactly what it drew before the choice existed.
    assert led_layout_options_for_model(PIXOO).font == "3x5"


def test_an_offered_board_face_stands():
    assert led_layout_options_for_model(PIXOO, font="5x7") == ("gap", 0, "5x7", [])
    assert led_layout_options_for_model(PIXOO, font="3x5") == ("gap", 0, "3x5", [])


def test_a_face_the_model_does_not_offer_is_its_own_with_a_reason():
    chosen = led_layout_options_for_model(HUB75, font="3x5")
    assert chosen.font == "5x7"
    assert chosen.ignored == ['font="3x5" is not a value hub75_64x32 allows (font: "5x7"); using "5x7"']


@pytest.mark.parametrize("garbage", ["7x9", "5X7", 5, True, ["5x7"]])
def test_a_garbage_board_face_is_ignored_never_raised(garbage):
    chosen = led_layout_options_for_model(PIXOO, font=garbage)
    assert chosen.font == "3x5"
    assert len(chosen.ignored) == 1


# --- validator: layoutOptions.font -------------------------------------------------------


def _with_font_choice(model, choice):
    return {**copy.deepcopy(model), "layoutOptions": {**model.get("layoutOptions", {}), "font": choice}}


def test_a_face_choice_on_a_5x7_model_validates():
    assert validate_device_model(_with_font_choice(HUB75, {"allowed": ["5x7", "3x5"], "default": "3x5"})) == []


def test_the_face_choice_must_include_the_models_own_face():
    errors = validate_device_model(_with_font_choice(PIXOO, {"allowed": ["5x7"]}))
    assert 'device_model.layoutOptions.font.allowed: must include the model\'s own font ("3x5")' in errors


def test_a_face_choice_needs_the_model_to_declare_its_font():
    faceless = {k: v for k, v in PIXOO.items() if k != "font"}
    errors = validate_device_model(_with_font_choice(faceless, {"allowed": ["5x7", "3x5"]}))
    assert "device_model.font: required when layoutOptions.font is declared" in errors


def test_a_face_choice_needs_the_builtin_set_drawn_in_the_models_face():
    errors = validate_device_model({**_with_font_choice(PIXOO, {"allowed": ["5x7", "3x5"]}), "charset": "led_5x7"})
    assert (
        'device_model.charset: "led_3x5" (the built-in set drawn in font "3x5") when layoutOptions.font is declared'
        in errors
    )


def test_a_face_choice_with_an_inline_set_is_refused():
    inline = {"id": "my_led", "extends": "led_3x5"}
    errors = validate_device_model({**_with_font_choice(PIXOO, {"allowed": ["5x7", "3x5"]}), "charset": inline})
    assert (
        'device_model.charset: "led_3x5" (the built-in set drawn in font "3x5") when layoutOptions.font is declared'
        in errors
    )


def test_the_face_default_must_be_one_of_allowed():
    errors = validate_device_model(_with_font_choice(HUB75, {"allowed": ["5x7"], "default": "3x5"}))
    assert "device_model.layoutOptions.font.default: one of allowed" in errors


@pytest.mark.parametrize(
    "choice",
    [
        {"allowed": []},
        {"allowed": ["5x7", "5x7"]},
        {"allowed": ["5x7", "7x9"]},
        {"allowed": ["5x7"], "default": "7x9"},
        {"allowed": ["5x7"], "size": "large"},
        {"default": "5x7"},
        ["5x7", "3x5"],
    ],
)
def test_the_schema_refuses_a_malformed_face_choice(choice):
    assert validate_device_model(_with_font_choice(HUB75, choice)), choice
