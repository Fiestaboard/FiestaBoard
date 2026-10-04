"""The engine measures extended markup by rendered tiles (plan D19, Task 12).

With ``extended_markup`` on (an LED board), every width the template engine
computes — alignment, padding, truncation, ``fill_space``, wrap, the wrap
budget beside a prefix, template validation — counts what the board DRAWS:
a span is its cells, a block is its cells, an icon (and a legacy shortcut
alias such as ``{sun}``) is one tile, ``{heart}`` is one ``♥``. A cut never
lands inside a span, block or icon; a span that crosses rows is closed on
one and reopened on the next.

Off (every split-flap board) nothing changes:
``tests/test_template_split_flap_width_corpus.py`` pins that byte for byte.
"""

from __future__ import annotations

import pytest

from src.markup import count_tiles, parse_line
from src.templates.engine import TemplateEngine

CTX = {
    "demo": {
        "short": "72",
        "alpha": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "words": "ONE TWO THREE FOUR SIX SEVEN EIGHT NINE TEN",
        "braces": "a{b}c",
    }
}


@pytest.fixture
def engine():
    return TemplateEngine()


def rows(
    engine: TemplateEngine, lines: list[str], *, alignment: str = "left", wrap: bool = False, **device
) -> list[str]:
    meta = [{"alignment": alignment, "wrap": wrap}] * len(lines)
    return engine.render_lines(lines, CTX, line_metadata=meta, extended_markup=True, **device).split("\n")


def assert_well_formed(row: str, width: int) -> None:
    """The row draws exactly *width* tiles and re-serialises as balanced markup."""
    assert count_tiles(row) == width, row
    assert row.count("{") == row.count("}"), row


# --- the reported bug ------------------------------------------------------------

MIXED = "{{red:hot}} {{black/white:OPEN}} {{icon:sun}}"


def test_mixed_markup_line_is_not_cut_mid_span(engine):
    row = rows(engine, [MIXED])[0]
    assert row == "{red:hot} {black/white:OPEN} {icon:sun}" + " " * 12


@pytest.mark.parametrize(
    ("alignment", "left", "right"),
    [("left", 0, 12), ("center", 6, 6), ("right", 12, 0)],
)
def test_alignment_pads_by_rendered_tiles(engine, alignment, left, right):
    row = rows(engine, [MIXED], alignment=alignment)[0]
    assert row == " " * left + "{red:hot} {black/white:OPEN} {icon:sun}" + " " * right


def test_note_alignment_pads_by_rendered_tiles(engine):
    row = rows(engine, [MIXED], alignment="right", device_type="note")[0]
    assert row == " " * 5 + "{red:hot} {black/white:OPEN} {icon:sun}"


# --- truncation ------------------------------------------------------------------


def test_truncation_closes_a_span_it_cuts(engine):
    row = rows(engine, ["{{red:ABCDEFGHIJKLMNOPQRSTUVWXYZ}}"])[0]
    assert row == "{red:ABCDEFGHIJKLMNOPQRSTUV}"


def test_truncation_closes_a_block_it_cuts(engine):
    row = rows(engine, ["XXXXXXXXXXXXXXXXXXXX{{black/white:OPEN}}"])[0]
    assert row == "XXXXXXXXXXXXXXXXXXXX{black/white:OP}"


def test_truncation_never_cuts_an_icon(engine):
    row = rows(engine, ["X" * 21 + "{{icon:sun}}{{icon:star}}"])[0]
    assert row == "X" * 21 + "{icon:sun}"


def test_variable_inside_a_span_is_truncated_by_tiles(engine):
    row = rows(engine, ["{{red:{{demo.alpha}}}}"])[0]
    assert row == "{red:ABCDEFGHIJKLMNOPQRSTUV}"


def test_formula_inside_a_span_is_measured_by_tiles(engine):
    row = rows(engine, ['{{green:{{= UPPER("ok") }}}} {{red:{{demo.short}}}}'], alignment="right")[0]
    assert row == " " * 17 + "{green:OK} {red:72}"


# --- legacy shortcut aliases by rendered width ---------------------------------


def test_shortcut_aliases_count_as_the_tiles_they_draw(engine):
    # {sun} -> {icon:sun} (1 tile), {heart} -> ♥ (1 tile): 20 + 2 = 22, nothing cut.
    row = rows(engine, ["A" * 20 + "{sun}{heart}"])[0]
    assert row == "A" * 20 + "{icon:sun}♥"


def test_shortcut_alias_is_never_cut_open(engine):
    row = rows(engine, ["A" * 21 + "{sun}{heart}"])[0]
    assert row == "A" * 21 + "{icon:sun}"


def test_shortcut_alias_centres_by_its_rendered_width(engine):
    row = rows(engine, ["{sun} HI"], alignment="center")[0]
    # 4 tiles drawn, 18 of padding.
    assert row == " " * 9 + "{icon:sun} HI" + " " * 9


# --- padding: fill_space -------------------------------------------------------


def test_fill_space_fills_by_rendered_tiles(engine):
    row = rows(engine, ["{{red:L}}{{fill_space}}{{blue:R}}"])[0]
    assert row == "{red:L}" + " " * 20 + "{blue:R}"


def test_fill_space_repeat_fills_by_rendered_tiles(engine):
    row = rows(engine, ["{{icon:sun}}{{fill_space_repeat:-}}{{icon:star}}"])[0]
    assert row == "{icon:sun}" + "-" * 20 + "{icon:star}"


def test_fill_space_with_no_room_truncates_by_tiles(engine):
    row = rows(engine, ["{{red:ABCDEFGHIJKLMNOP}}{{fill_space}}{{blue:QRSTUVWXYZ}}"])[0]
    assert row == "{red:ABCDEFGHIJKLMNOP}{blue:QRSTUV}"


# --- wrap ------------------------------------------------------------------------


def test_line_wrap_closes_and_reopens_a_span_across_rows(engine):
    out = rows(engine, ["{{red:" + "WORD " * 9 + "}}", "", ""], wrap=True)
    assert out[0] == "{red:WORD WORD WORD WORD}" + " " * 3
    assert out[1] == "{red:WORD WORD WORD WORD}" + " " * 3
    assert out[2] == "{red:WORD}" + " " * 18


def test_line_wrap_measures_icons_and_shortcuts_as_one_tile(engine):
    out = rows(engine, ["{sun} " * 15, ""], wrap=True)
    # 11 one-tile icons fit a 22-wide row (11 + 10 joining spaces = 21).
    assert out[0] == " ".join(["{icon:sun}"] * 11) + " "
    assert out[1] == " ".join(["{icon:sun}"] * 4) + " " * 15


def test_line_wrap_respects_the_row_budget(engine):
    meta = [{"alignment": "left", "wrap": w} for w in (True, False, False)]
    lines = ["{{red:" + "WORD " * 20 + "}}", "", "FOOTER"]
    out = engine.render_lines(lines, CTX, line_metadata=meta, device_type="note", extended_markup=True).split("\n")
    # Two rows of budget (the FOOTER row stops the overflow), 14 tiles each on a 15-wide Note.
    assert out[0] == "{red:WORD WORD WORD} "
    assert out[1] == "{red:WORD WORD WORD} "
    assert out[2] == "FOOTER" + " " * 9


def test_line_wrap_hard_breaks_a_long_span_word(engine):
    out = rows(engine, ["{{red:" + "A" * 30 + "}}", ""], wrap=True)
    assert out[0] == "{red:" + "A" * 22 + "}"
    assert out[1] == "{red:" + "A" * 8 + "}" + " " * 14


def test_variable_wrap_budget_counts_a_span_prefix_by_tiles(engine):
    # "{red:HI} " draws 3 tiles, leaving 19 for the first row of the value:
    # "ONE TWO THREE FOUR SIX" (22) would fill a whole row but not those 19.
    out = rows(engine, ["{{red:HI}} {{demo.words|wrap}}", "", ""])
    assert out[0] == "{red:HI} ONE TWO THREE FOUR" + " "
    assert out[1] == "SIX SEVEN EIGHT NINE  "
    assert out[2] == "TEN" + " " * 19


# --- row-emitting formulas (FOREACH) ----------------------------------------------

ITEMS = {"demo": {"items": ["AA", "BB", "CC"]}}


def foreach_rows(engine: TemplateEngine, line: str, *, extended_markup: bool = True) -> list[str]:
    meta = [{"alignment": "left", "wrap": False}]
    return engine.render_lines([line], ITEMS, line_metadata=meta, extended_markup=extended_markup).split("\n")


def test_foreach_row_break_closes_and_reopens_a_span(engine):
    out = foreach_rows(engine, "{{red:{{= FOREACH(demo.items, item)}}}}")
    assert out[:3] == ["{red:AA}" + " " * 20, "{red:BB}" + " " * 20, "{red:CC}" + " " * 20]


def test_foreach_row_break_reopens_a_block_with_its_background(engine):
    out = foreach_rows(engine, "{{black/white:X {{= FOREACH(demo.items, item)}}}}")
    assert out[:3] == [
        "{black/white:X AA}" + " " * 18,
        "{black/white:BB}" + " " * 20,
        "{black/white:CC}" + " " * 20,
    ]
    assert parse_line(out[1], extended_markup=True)[0].background == "white"


def test_foreach_row_break_reopens_every_enclosing_span(engine):
    out = foreach_rows(engine, "{{red:<{{blue:{{= FOREACH(demo.items, item)}}}}>}}")
    assert out[:3] == [
        "{red:<{blue:AA}}" + " " * 19,
        "{red:{blue:BB}}" + " " * 20,
        "{red:{blue:CC}>}" + " " * 19,
    ]


def test_foreach_rows_outside_any_span_are_left_verbatim(engine):
    out = foreach_rows(engine, "{{red:>}}{{= FOREACH(demo.items, item)}}")
    assert out[:3] == ["{red:>}AA" + " " * 19, "BB" + " " * 20, "CC" + " " * 20]


@pytest.mark.parametrize(
    "line",
    ["{{red:{{= FOREACH(demo.items, item)}}}}", "{{black/white:X {{= FOREACH(demo.items, item)}}}}"],
)
def test_every_foreach_row_is_board_width_and_balanced(engine, line):
    for row in foreach_rows(engine, line):
        assert_well_formed(row, 22)


def test_foreach_split_flap_rows_are_unchanged(engine):
    assert foreach_rows(engine, "{{= FOREACH(demo.items, item)}}", extended_markup=False)[:3] == [
        "AA" + " " * 20,
        "BB" + " " * 20,
        "CC" + " " * 20,
    ]


def test_split_rows_without_a_crossing_span_is_a_plain_split():
    from src.markup import split_rows

    assert split_rows("{red:A}\n{x}B\n") == ["{red:A}", "{x}B", ""]


def test_split_rows_keeps_literal_braces_it_cannot_reexpress():
    from src.markup import split_rows

    # A newline between a span's literal braces: no markup expresses the halves,
    # so the rows are the raw split (as wrap_line falls back to the legacy wrap).
    assert split_rows("{red:A{x\ny}B}") == ["{red:A{x", "y}B}"]


@pytest.mark.parametrize("line", [MIXED, "{{red:" + "WORD " * 9 + "}}", "A" * 21 + "{sun}{heart}"])
@pytest.mark.parametrize("alignment", ["left", "center", "right"])
def test_every_row_is_board_width_and_balanced(engine, line, alignment):
    for row in rows(engine, [line, "", ""], alignment=alignment, wrap=True):
        assert_well_formed(row, 22)


# --- data vs markup --------------------------------------------------------------


def test_neutralised_data_braces_count_as_drawn_parentheses(engine):
    row = rows(engine, ["{{red:{{demo.braces}}}}"], alignment="right")[0]
    assert row == " " * 17 + "{red:a(b)c}"
    assert parse_line(row, extended_markup=True)[-1].color == "red"


# --- validation ------------------------------------------------------------------


def test_validation_measures_extended_markup_by_rendered_tiles(engine):
    # hot, OPEN, two icons, four spaces and nine Xs: 3 + 4 + 2 + 4 + 9 = 22 drawn tiles.
    line = "{{red:hot}} {{black/white:OPEN}} {{icon:sun}} {sun} XXXXXXXXX"
    assert engine._calculate_max_line_length(line, cols=22, extended_markup=True) == 22
    assert not [e for e in engine.validate_template(line, extended_markup=True) if "too long" in e.message]


def test_validation_still_flags_extended_markup_that_overflows(engine):
    line = "{{red:" + "X" * 23 + "}}"
    errors = engine.validate_template(line, extended_markup=True)
    assert any("up to 23" in e.message for e in errors)


def test_validation_counts_heart_shortcut_as_one_tile(engine):
    assert engine._calculate_max_line_length("A{heart}", cols=22, extended_markup=True) == 2
    assert engine._calculate_max_line_length("A{heart}", cols=22) == 3


def test_wrap_line_narrows_only_the_first_row():
    from src.markup import wrap_line

    assert wrap_line("{red:AB CD EF}", 6, first_cols=2) == ["{red:AB}", "{red:CD EF}"]


# --- the validate route ------------------------------------------------------------

FITS_ON_LED = "{{red:hot}} {{black/white:OPEN}} {{icon:sun}} {sun} XXXXXXXXX"


@pytest.fixture
def api_client_with_led_board(monkeypatch):
    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.led.charsets import BUILTIN_CHARACTER_SETS
    from src.settings.service import get_settings_service
    from src.templates import routes

    get_settings_service().set_boards([{"id": "led1", "name": "Sign", "device_type": "flagship"}])
    led = dict(BUILTIN_CHARACTER_SETS["led_5x7"])
    monkeypatch.setattr(routes, "board_character_set", lambda board: led if board.get("id") == "led1" else None)
    return TestClient(app)


def _too_long(body: dict) -> list[str]:
    return [e["message"] for e in body["errors"] if "too long" in e["message"]]


def test_validate_for_a_rich_board_measures_rendered_tiles(api_client_with_led_board):
    body = api_client_with_led_board.post("/templates/validate", json={"template": FITS_ON_LED, "board_id": "led1"})
    assert _too_long(body.json()) == []


def test_validate_without_a_board_measures_as_split_flap(api_client_with_led_board):
    body = api_client_with_led_board.post("/templates/validate", json={"template": FITS_ON_LED})
    assert _too_long(body.json()) != []


def test_validate_for_an_unknown_board_measures_as_split_flap(api_client_with_led_board):
    body = api_client_with_led_board.post("/templates/validate", json={"template": FITS_ON_LED, "board_id": "nope"})
    assert _too_long(body.json()) != []
