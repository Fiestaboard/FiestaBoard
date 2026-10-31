"""Measure and fit text blocks in pixels (plan Task 7, spec section 5 steps 3 and 4).

Every glyph, icon and tile is one cell, ``advance`` wide; a line's width is
its cells less the trailing gutter, plus any pixel gaps. A block too wide for
its rect wraps, shrinks or is ellipsised by its ``overflow``; too many lines
are truncated; fills are resolved in pixels per line.
"""

from __future__ import annotations

from src.layout.expand import FILL_SENTINEL_BASE, ExpandedBlock, FillSpec
from src.layout.fonts import FONT_FAMILIES, SizedFace, face_for_led_font, size_ladder
from src.layout.measure import FittedText, Gap, Glyph, fit_text, measure
from src.layout.style import ResolvedStyle
from src.markup import BoardToken, parse_line
from src.pages.flexible import Block

FIESTA = FONT_FAMILIES["fiesta"]
S35 = SizedFace(face_for_led_font("3x5"), 1)  # advance 4, gutter 1, height 5, line gap 1
S57 = SizedFace(face_for_led_font("5x7"), 1)  # advance 6, gutter 1, height 7
P = ("blocks", "b1")


def glyphs(text: str) -> tuple[Glyph, ...]:
    return tuple(Glyph(BoardToken("char", value=c)) for c in text)


def block(markup: str, fills: tuple[FillSpec, ...] = ()) -> ExpandedBlock:
    tokens = tuple(parse_line(markup, extended_markup=True, preserve_case=True))
    return ExpandedBlock(
        id="b1",
        kind="text",
        index=0,
        priority=None,
        markup=markup,
        fills=fills,
        tokens=tokens,
        block=Block(id="b1", kind="text", text=markup),
    )


def block_with_fill(left: str, pattern: str | None, right: str) -> ExpandedBlock:
    return block(left + chr(FILL_SENTINEL_BASE) + right, (FillSpec(pattern),))


def style(*, sized: SizedFace = S35, overflow: str = "wrap", fit: bool = False) -> ResolvedStyle:
    return ResolvedStyle(
        family="fiesta",
        sized=sized,
        px=sized.height,
        color="#ffffff",
        background=None,
        align="left",
        case="as-is",
        overflow=overflow,
        height="auto",
        fit=fit,
    )


def fit(b: ExpandedBlock, s: ResolvedStyle, width: int, max_height: int = 64) -> FittedText:
    return fit_text(b, s, width, max_height, family=FIESTA, path=P)


def texts(f: FittedText) -> list[str]:
    return ["".join(item.token.value for item in line if isinstance(item, Glyph)) for line in f.lines]


def codes(f: FittedText) -> list[str]:
    return [i.code for i in f.issues]


# --- measure -----------------------------------------------------------------


def test_measure_counts_cells_minus_trailing_gutter():
    assert measure(glyphs("ABC"), S35) == 11 and measure((), S35) == 0


def test_measure_adds_gap_pixels():
    assert measure((*glyphs("A"), Gap(5), *glyphs("B")), S35) == 7 + 5


def test_measure_scales_with_the_face():
    assert measure(glyphs("AB"), SizedFace(face_for_led_font("3x5"), 2)) == 2 * 8 - 2


# --- fits as written -----------------------------------------------------------


def test_text_that_fits_is_one_line_with_no_issue():
    f = fit(block("HELLO"), style(), width=64)
    assert texts(f) == ["HELLO"] and f.issues == () and (f.width, f.height) == (19, 5)


def test_empty_text_has_no_lines_and_no_height():
    f = fit(block(""), style(), width=64)
    assert f.lines == () and f.height == 0


# --- wrap ----------------------------------------------------------------------


def test_wrap_breaks_at_spaces():
    f = fit(block("AB CD EF"), style(overflow="wrap"), width=19)
    assert texts(f) == ["AB CD", "EF"] and codes(f) == ["wrapped"] and f.issues[0].path == P


def test_wrap_drops_leading_blanks_of_a_continuation_line():
    f = fit(block("AB   CD"), style(overflow="wrap"), width=11)
    assert texts(f) == ["AB", "CD"]


def test_wrapped_height_counts_line_gaps():
    f = fit(block("AB CD EF"), style(overflow="wrap"), width=19)
    assert f.height == 2 * 5 + 1


def test_wrap_breaks_a_long_word_at_a_glyph_boundary():
    f = fit(block("ABCDEFGH"), style(overflow="wrap"), width=15)
    assert texts(f) == ["ABCD", "EFGH"]


def test_wrap_always_places_one_glyph_per_line_even_when_narrower():
    f = fit(block("AB"), style(overflow="wrap"), width=2)
    assert texts(f) == ["A", "B"]


def test_unbreakable_word_on_32x8_strip_breaks_midword_then_truncates():  # [RF-3]
    f = fit(block("WWW.EXAMPLESTATION.COM"), style(overflow="wrap"), width=32, max_height=8)
    assert len(f.lines) == 1 and texts(f)[0].endswith(".") and measure(f.lines[0], S35) <= 32
    assert set(codes(f)) == {"wrapped", "truncated"}


def test_truncated_line_keeps_the_longest_prefix_that_fits_with_the_ellipsis():
    f = fit(block("WWW.EXAMPLESTATION.COM"), style(overflow="wrap"), width=32, max_height=8)
    assert texts(f) == ["WWW.EXA."]


def test_newline_in_markup_starts_a_new_line():
    f = fit(block("AB\nCD"), style(), width=64)
    assert texts(f) == ["AB", "CD"] and f.issues == ()


# --- shrink ----------------------------------------------------------------------


def test_shrink_steps_down_a_face():
    f = fit(block("HELLO"), style(overflow="shrink", sized=S57), width=24)
    assert f.sized.face.id == "3x5" and codes(f) == ["shrunk"]


def test_shrink_steps_down_a_scale_before_a_face():
    s3 = SizedFace(face_for_led_font("3x5"), 3)  # advance 12: HELLO is 57 px
    f = fit(block("HELLO"), style(overflow="shrink", sized=s3), width=40)
    expected = max(
        (s for s in size_ladder(FIESTA) if s.height < s3.height and measure(glyphs("HELLO"), s) <= 40),
        key=lambda s: s.height,
    )
    assert f.sized == expected and texts(f) == ["HELLO"]


def test_shrink_past_the_smallest_face_ellipsises():
    f = fit(block("ABCDEFGHIJ"), style(overflow="shrink", sized=S57), width=15)
    assert f.sized == S35 and texts(f) == ["ABC."] and codes(f) == ["ellipsized"]
    assert f.issues[0].severity == "warning"


# --- ellipsis --------------------------------------------------------------------


def test_ellipsis_cuts_at_glyph_boundary():
    # "ABC." is 4 cells: 4 * 4 - 1 = 15 px.
    f = fit(block("ABCDEFG"), style(overflow="ellipsis"), width=15, max_height=8)
    assert texts(f) == ["ABC."] and codes(f) == ["ellipsized"]


def test_ellipsis_trims_trailing_blanks_before_the_dot():
    f = fit(block("AB  CDEFG"), style(overflow="ellipsis"), width=19)
    assert texts(f) == ["AB."]


def test_ellipsis_keeps_the_colour_of_the_last_glyph():
    f = fit(block("{red:ABCDEFG}"), style(overflow="ellipsis"), width=15)
    assert f.lines[0][-1].token.value == "." and f.lines[0][-1].token.color == "red"


# --- fit size ---------------------------------------------------------------------


def test_fit_size_picks_largest_one_line_size():
    f = fit(block("12:45"), style(fit=True), width=64)
    expected = max(
        (s for s in size_ladder(FIESTA) if s.height <= 64 and measure(glyphs("12:45"), s) <= 64),
        key=lambda s: s.height,
    )
    assert f.sized == expected and texts(f) == ["12:45"] and f.issues == ()


def test_fit_size_respects_the_height():
    f = fit(block("A"), style(fit=True), width=64, max_height=10)
    assert f.sized.height <= 10 and f.sized.height == max(
        s.height for s in size_ladder(FIESTA) if s.height <= 10 and measure(glyphs("A"), s) <= 64
    )


def test_fit_size_with_nothing_that_fits_takes_the_smallest():
    f = fit(block("ABCDEFGHIJKLMNOP"), style(fit=True, overflow="ellipsis"), width=20)
    assert f.sized == size_ladder(FIESTA)[0]


# --- fills -------------------------------------------------------------------------


def test_blank_fill_resolves_in_pixels():
    f = fit(block_with_fill("A", None, "B"), style(), width=20, max_height=8)
    assert measure(f.lines[0], S35) == 20 and [type(i).__name__ for i in f.lines[0]] == ["Glyph", "Gap", "Glyph"]


def test_two_blank_fills_share_extra_pixels_to_the_earlier():
    b = block("A" + chr(FILL_SENTINEL_BASE) + "B" + chr(FILL_SENTINEL_BASE + 1) + "C", (FillSpec(None),) * 2)
    f = fit(b, style(), width=20)
    assert [i.px for i in f.lines[0] if isinstance(i, Gap)] == [5, 4]  # 20 - 11 = 9


def test_pattern_fill_repeats_its_glyphs_without_overflowing():
    f = fit(block_with_fill("A", "-", "B"), style(), width=22)
    assert texts(f) == ["A---B"] and measure(f.lines[0], S35) <= 22


def test_pattern_fill_alone_fills_the_line():
    f = fit(block_with_fill("", "-", ""), style(), width=19)
    assert texts(f) == ["-----"]


def test_colour_pattern_fill_is_tiles():
    f = fit(block_with_fill("A", "red", ""), style(), width=11)
    assert [i.token.type for i in f.lines[0]] == ["char", "color", "color"]


def test_pattern_fill_inside_a_span_takes_its_colour():
    b = block("{red:A" + chr(FILL_SENTINEL_BASE) + "B}", (FillSpec("-"),))
    f = fit(b, style(), width=19)
    assert all(i.token.color == "red" for i in f.lines[0])


def test_fill_with_no_room_is_removed():
    f = fit(block_with_fill("ABCDE", None, ""), style(), width=19)
    assert [type(i).__name__ for i in f.lines[0]] == ["Glyph"] * 5


def test_fills_take_no_room_while_wrapping():
    f = fit(block_with_fill("AB", None, " CD"), style(overflow="wrap"), width=11)
    assert texts(f) == ["AB", "CD"]
