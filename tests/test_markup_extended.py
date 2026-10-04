"""Extended markup measured and wrapped by the tiles it draws.

A span ``{red:HOT}`` draws three tiles and an icon ``{icon:sun}`` draws one,
so with ``extended_markup=True`` the tile helpers count, split and wrap them
that way and never cut through their markup. With the flag off (the default,
and what every caller uses today) they keep counting the raw characters —
pinned here so the difference is explicit.
"""

from __future__ import annotations

import random

from src.formatters.message_formatter import MessageFormatter
from src.markup import parse_line
from src.text_to_board import count_tiles, take_tiles, text_to_board_array, wrap_message_text

# --- count_tiles -------------------------------------------------------------


def test_span_counts_its_letters_when_extended():
    assert count_tiles("{red:HOT}", extended_markup=True) == 3


def test_span_counts_its_characters_when_extended_is_off():
    assert count_tiles("{red:HOT}") == 9


def test_icon_counts_one_tile_when_extended():
    assert count_tiles("{icon:sun}", extended_markup=True) == 1


def test_block_span_with_nested_tile_counts_rendered_cells():
    assert count_tiles("{black/white:A{63}B}", extended_markup=True) == 3


def test_end_tag_inside_span_counts_nothing():
    assert count_tiles("{red:A{/}B}", extended_markup=True) == 2


# --- take_tiles --------------------------------------------------------------


def test_take_tiles_reopens_a_span_it_splits():
    assert take_tiles("{red:HOTDOG}", 3, extended_markup=True) == ("{red:HOT}", "{red:DOG}")


def test_take_tiles_reopens_every_enclosing_span():
    assert take_tiles("{black/white:A{red:BC}D}", 2, extended_markup=True) == (
        "{black/white:A{red:B}}",
        "{black/white:{red:C}D}",
    )


def test_take_tiles_cut_at_a_span_start_keeps_the_span_whole_in_the_tail():
    assert take_tiles("AB{Red:cd}", 2, extended_markup=True) == ("AB", "{Red:cd}")


def test_take_tiles_at_a_top_level_boundary_keeps_the_source_verbatim():
    # Re-serializing would drop the empty span; a top-level cut slices instead.
    assert take_tiles("A{red:}B{/}C", 2, extended_markup=True) == ("A{red:}B{/}", "C")


def test_take_tiles_moves_a_span_with_literal_braces_whole_when_the_cut_cannot_be_written():
    # "{red:A{F}" would no longer be a span, so the cut falls back to the span's start.
    assert take_tiles("{red:A{foo}B}", 3, extended_markup=True) == ("", "{red:A{foo}B}")


def test_take_tiles_takes_an_icon_whole():
    assert take_tiles("A{icon:sun}B", 2, extended_markup=True) == ("A{icon:sun}", "B")


def test_take_tiles_when_extended_is_off_cuts_through_a_span():
    assert take_tiles("{red:HOTDOG}", 3) == ("{re", "d:HOTDOG}")


# --- wrapping ----------------------------------------------------------------


def test_wrap_breaks_a_span_at_a_space_and_reopens_it():
    assert wrap_message_text("{red:HOT DOG}", rows=2, cols=3, extended_markup=True) == "{red:HOT}\n{red:DOG}"


def test_wrap_keeps_a_space_inside_a_span_that_fits_on_the_row():
    wrapped = wrap_message_text("XX {black/white:HOT DOG} YY", rows=2, cols=12, extended_markup=True)
    assert wrapped == "XX {black/white:HOT DOG}\nYY"


def test_wrap_leaves_a_line_that_fits_untouched():
    line = "{red:HOT}  {icon:sun} {Blue:cold}"
    assert wrap_message_text(line, rows=1, cols=22, extended_markup=True) == line


def test_wrap_hard_breaks_a_long_span_word_inside_the_span():
    assert wrap_message_text("{green:ABCDEFG}", rows=3, cols=3, extended_markup=True) == (
        "{green:ABC}\n{green:DEF}\n{green:G}"
    )


def test_wrap_falls_back_to_legacy_wrap_when_a_row_cannot_be_written():
    line = "{red:{a b}}"
    legacy_rows = MessageFormatter(rows=4, cols=3)._wrap_line(line)
    assert wrap_message_text(line, rows=4, cols=3, extended_markup=True) == "\n".join(legacy_rows)


def test_wrap_when_extended_is_off_breaks_inside_span_markup():
    assert wrap_message_text("{red:HOT DOG}", rows=2, cols=8) == "{red:HOT\nDOG}"


def test_message_formatter_counts_spans_by_tiles_when_extended():
    lines = MessageFormatter(rows=2, cols=3, extended_markup=True).split_into_lines("{red:HOT}")
    assert lines == ["{red:HOT}"]


def _random_markup(rng: random.Random, depth: int = 0) -> str:
    out = []
    for _ in range(rng.randint(0, 6)):
        roll = rng.random()
        if roll < 0.45:
            out.append(rng.choice("ABCdef12 "))
        elif roll < 0.55:
            out.append(rng.choice(["{63}", "{red}", "{/}", "{/red}"]))
        elif roll < 0.65:
            out.append(rng.choice(["{icon:sun}", "{icon:up}", "{icon:bus}"]))
        elif depth < 2:
            head = rng.choice(["red", "63", "#ff8800", "black/white", "Blue"])
            out.append("{" + head + ":" + _random_markup(rng, depth + 1) + "}")
    return "".join(out)


def test_wrapped_rows_fit_and_keep_every_visible_tile_in_order():
    rng = random.Random(42)
    failures = []
    for _ in range(2000):
        line = _random_markup(rng)
        cols = rng.choice([1, 3, 5, 8])
        rows = wrap_message_text(line, rows=50, cols=cols, extended_markup=True).split("\n")
        drawn = [
            t.to_dict()
            for row in rows
            for t in parse_line(row, extended_markup=True)
            if t.value.strip() or t.type == "color"
        ]
        expected = [t.to_dict() for t in parse_line(line, extended_markup=True) if t.value.strip() or t.type == "color"]
        too_wide = [r for r in rows if count_tiles(r, extended_markup=True) > cols]
        if drawn != expected or too_wide:
            failures.append((line, cols, rows))
    assert failures == []


# --- text_to_board_array -----------------------------------------------------


def test_board_array_draws_span_letters_when_extended():
    assert text_to_board_array("{red:HOT}", rows=1, cols=5, extended_markup=True) == [[8, 15, 20, 0, 0]]


def test_board_array_draws_icon_fallbacks_when_extended():
    assert text_to_board_array("{icon:sun}{icon:up}{icon:bus}X", rows=1, cols=5, extended_markup=True) == [
        [65, 46, 0, 24, 0]
    ]


def test_board_array_strips_icon_colour_tiles_without_colour_tiles():
    board = text_to_board_array("{icon:sun}A", rows=1, cols=3, use_color_tiles=False, extended_markup=True)
    assert board == [[1, 0, 0]]


def test_board_array_draws_span_markup_literally_when_extended_is_off():
    assert text_to_board_array("{red:HI}", rows=1, cols=8) == [[0, 18, 5, 4, 50, 8, 9, 0]]


# --- span heads: colours only, never the filled tile -------------------------
# `filled` / 71 is a tile ({filled}, {71}), not a colour a letter can be drawn
# in, so a span or block head naming it is literal text (FiestaUI 5364439).


def _literal(text: str) -> list[dict]:
    return [{"type": "char", "value": ch.upper()} for ch in text]


def test_filled_name_is_not_a_span_colour():
    assert [t.to_dict() for t in parse_line("{filled:x}", extended_markup=True)] == _literal("{filled:x}")


def test_filled_code_is_not_a_span_colour():
    assert [t.to_dict() for t in parse_line("{71:x}", extended_markup=True)] == _literal("{71:x}")


def test_filled_is_not_a_block_foreground():
    assert [t.to_dict() for t in parse_line("{filled/red:x}", extended_markup=True)] == _literal("{filled/red:x}")


def test_filled_is_not_a_block_background():
    assert [t.to_dict() for t in parse_line("{red/71:x}", extended_markup=True)] == _literal("{red/71:x}")


def test_code_70_is_still_a_span_colour():
    assert [t.to_dict() for t in parse_line("{70:x}", extended_markup=True)] == [
        {"type": "char", "value": "X", "color": "70"}
    ]


def test_filled_is_still_a_tile_when_extended():
    assert [t.to_dict() for t in parse_line("{filled}{71}", extended_markup=True)] == [
        {"type": "color", "code": "filled"},
        {"type": "color", "code": "71"},
    ]
