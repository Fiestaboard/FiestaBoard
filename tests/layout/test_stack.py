"""The vertical stack and the pixel emitter (plan Task 8).

Spacer and canvas blocks exercise the stack's drop, fill, valign and clipping
rules on their own; text blocks go through the real ``fit_text``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.layout.fonts import FONT_FAMILIES, SizedFace, face_for_led_font
from src.layout.issues import LayoutIssue
from src.layout.measure import Glyph as MGlyph
from src.layout.measure import measure
from src.layout.pixels import canvas_block_op, clip_op, draw_line, frame_from_ops
from src.layout.stack import Rect, StackResult, stack
from src.layout.style import ResolvedLayout, ResolvedStyle
from src.led.matrix import LedDrawOp, LedFrame, LedRenderOptions, scaled_rows
from src.markup import BoardToken, parse_line
from src.pages.flexible import Block

FIESTA = FONT_FAMILIES["fiesta"]
S35 = SizedFace(face_for_led_font("3x5"), 1)
S57 = SizedFace(face_for_led_font("5x7"), 1)
RGB = LedRenderOptions()
TOP = ResolvedLayout("stack", "top", 1)


# --- helpers -----------------------------------------------------------------


@dataclass(frozen=True)
class Blk:
    """The fields of an expanded block the stack reads (Task 6's ``ExpandedBlock``)."""

    id: str
    kind: str
    index: int
    priority: int | None
    block: Block
    markup: str = ""
    fills: tuple = ()
    tokens: tuple[BoardToken, ...] = field(default=())


@dataclass(frozen=True)
class Glyph:
    token: BoardToken


@dataclass(frozen=True)
class Gap:
    px: int


def style(
    *,
    sized: SizedFace | None = S35,
    color: str | None = "#ffffff",
    background: str | None = None,
    align: str = "left",
    overflow: str = "wrap",
    height: Any = "auto",
) -> ResolvedStyle:
    return ResolvedStyle(
        family="fiesta",
        sized=sized,
        px=sized.height if sized else 0,
        color=color,
        background=background,
        align=align,
        case="as-is",
        overflow=overflow,
        height=height,
        fit=False,
    )


def spacer(bid: str, index: int, height: Any, *, priority: int | None = None) -> Blk:
    return Blk(bid, "spacer", index, priority, Block(id=bid, kind="spacer"))


def canvas(bid: str, index: int, content: dict | None = None, *, source: str | None = None, priority=None) -> Blk:
    body: dict[str, Any] = {}
    if content is not None:
        body["content"] = content
    if source is not None:
        body["source"] = source
    return Blk(bid, "canvas", index, priority, Block(id=bid, kind="canvas", canvas=body))


def text(bid: str, index: int, markup: str, *, priority: int | None = None) -> Blk:
    tokens = tuple(parse_line(markup, extended_markup=True, preserve_case=True))
    return Blk(bid, "text", index, priority, Block(id=bid, kind="text", text=markup), markup=markup, tokens=tokens)


def lit_pixels(frame: LedFrame) -> set[tuple[int, int]]:
    px = frame.pixels
    return {
        (i // 3 % frame.width, i // 3 // frame.width) for i in range(0, len(px), 3) if px[i] or px[i + 1] or px[i + 2]
    }


def band_ys(result: StackResult) -> list[tuple[int, int]]:
    """``(y, h)`` of every background band rect, in draw order."""
    return [(op.y, op.h) for op in result.ops if op.kind == "rect"]


BG = "#ff0000"


def spacers(*specs: tuple[str, Any, int | None]) -> tuple[list[Blk], dict[str, ResolvedStyle]]:
    blocks = [spacer(bid, i, h, priority=p) for i, (bid, h, p) in enumerate(specs)]
    styles = {bid: style(background=BG, height=h) for bid, h, _ in specs}
    return blocks, styles


def run(blocks, styles, rect, layout=TOP, **kw) -> StackResult:
    return stack(blocks, styles, rect, layout=layout, options=kw.pop("options", RGB), context={}, family=FIESTA, **kw)


# --- pixels ------------------------------------------------------------------


def test_frame_from_ops_fills_background_then_paints_ops():
    frame = frame_from_ops(3, 2, [LedDrawOp("rect", 1, 0, "#00ff00", w=1, h=1)], "#0000ff")
    assert frame.pixels[0:3] == bytes((0, 0, 255))
    assert frame.pixels[3:6] == bytes((0, 255, 0))
    assert frame.pixels[15:18] == bytes((0, 0, 255))


def test_frame_from_ops_without_background_is_unlit():
    assert frame_from_ops(2, 2, [], None).pixels == bytes(12)


def test_draw_line_advances_by_scaled_cell_and_gap_pixels():
    s2 = SizedFace(face_for_led_font("3x5"), 2)
    ops: list[LedDrawOp] = []
    draw_line(
        ops,
        [Glyph(BoardToken("char", value="A")), Gap(3), Glyph(BoardToken("char", value="B"))],
        5,
        7,
        s2,
        RGB,
        "#ffffff",
    )
    assert [(op.x, op.y) for op in ops] == [(5, 7), (5 + s2.advance + 3, 7)]
    a_rows = tuple(face_for_led_font("3x5").led_font.glyphs["A"])
    assert ops[0].rows == scaled_rows(a_rows, 2) and ops[0].color == "#ffffff"


def test_draw_line_joins_block_backgrounds_over_the_gutter_only_to_the_same_background():
    tokens = parse_line("{white/red:AB}{white/blue:C}", extended_markup=True)
    ops: list[LedDrawOp] = []
    draw_line(ops, [Glyph(t) for t in tokens], 0, 0, S35, RGB, "#ffffff")
    rects = [(op.x, op.w) for op in ops if op.kind == "rect"]
    # A joins over its gutter to B (same red); B does not join to C (blue).
    assert rects == [(0, 4), (4, 3), (8, 3)]


def test_draw_line_unlit_text_on_mono_draws_black_glyphs():
    mono = LedRenderOptions(monochrome="#ffaa00")
    ops: list[LedDrawOp] = []
    draw_line(ops, [Glyph(BoardToken("char", value="A"))], 0, 0, S35, mono, None)
    assert [op.color for op in ops] == ["#000000"]


def test_canvas_block_op_draws_content_scaled_to_the_rect():
    blk = canvas("c1", 0, {"size": [2, 1], "palette": {"r": "#ff0000", "g": "#00ff00"}, "pixels": ["rg"]})
    op, issues = canvas_block_op(blk, Rect(3, 4, 4, 2), {})
    assert issues == []
    assert (op.kind, op.x, op.y, op.w, op.h) == ("bitmap", 3, 4, 4, 2)
    assert op.rgba[0:4] == bytes((255, 0, 0, 255)) and op.rgba[8:12] == bytes((0, 255, 0, 255))


def test_canvas_block_op_on_a_mono_panel_lights_in_the_panel_colour():
    blk = canvas("c1", 0, {"size": [1, 1], "palette": {"w": "#ffffff"}, "pixels": ["w"]})
    op, _ = canvas_block_op(blk, Rect(0, 0, 1, 1), {}, monochrome="#ffaa00")
    assert op.rgba == bytes((255, 170, 0, 255))


def test_canvas_issues_carry_the_block_path():
    blk = canvas("c1", 0, source="{{missing.canvas}}")
    op, issues = canvas_block_op(blk, Rect(0, 0, 4, 4), {}, path=("regions", "r1"))
    assert op is None
    assert issues[0].code == "canvas" and issues[0].path == ("regions", "r1", "blocks", "c1", "canvas", "source")


def test_clip_op_crops_glyphs_and_bitmaps_to_the_rect():
    glyph = LedDrawOp("glyph", 0, 0, "#ffffff", rows=("###", "###"))
    assert clip_op(glyph, Rect(1, 1, 5, 5)) == LedDrawOp("glyph", 1, 1, "#ffffff", rows=("##",))
    bitmap = LedDrawOp("bitmap", 0, 0, "", w=2, h=1, rgba=bytes((1, 1, 1, 255, 2, 2, 2, 255)))
    clipped = clip_op(bitmap, Rect(1, 0, 4, 4))
    assert (clipped.x, clipped.w, clipped.rgba) == (1, 1, bytes((2, 2, 2, 255)))
    assert clip_op(glyph, Rect(10, 10, 2, 2)) is None


# --- stack -------------------------------------------------------------------


def test_lowest_priority_dropped_first_with_issue():
    blocks, styles = spacers(("b1", 7, 2), ("b2", 7, 1), ("b3", 7, 3))
    r = run(blocks, styles, Rect(0, 0, 64, 8))
    assert r.shown == ("b2",)
    dropped = [i for i in r.issues if i.code == "dropped"]
    assert [i.path for i in dropped] == [("blocks", "b3"), ("blocks", "b1")]
    assert all(i.severity == "warning" for i in dropped)


def test_unset_priority_drops_before_explicit_and_bottom_first():
    blocks, styles = spacers(("b1", 7, None), ("b2", 7, 9), ("b3", 7, None))
    r = run(blocks, styles, Rect(0, 0, 64, 8))
    assert r.shown == ("b2",)
    assert [i.path[-1] for i in r.issues if i.code == "dropped"] == ["b3", "b1"]


def test_valign_middle_centres_the_stack():
    blocks, styles = spacers(("b1", 5, None), ("b2", 5, None))
    r = run(blocks, styles, Rect(0, 0, 64, 64), layout=ResolvedLayout("stack", "middle", 1))
    assert min(op.y for op in r.ops) == (64 - 11) // 2


def test_valign_bottom_ends_at_the_rect_bottom():
    blocks, styles = spacers(("b1", 5, None), ("b2", 5, None))
    r = run(blocks, styles, Rect(0, 4, 64, 30), layout=ResolvedLayout("stack", "bottom", 1))
    assert band_ys(r) == [(4 + 30 - 11, 5), (4 + 30 - 5, 5)]


def test_spread_distributes_space_between_blocks():
    blocks, styles = spacers(("b1", 4, None), ("b2", 4, None), ("b3", 4, None))
    r = run(blocks, styles, Rect(0, 0, 64, 21), layout=ResolvedLayout("stack", "spread", 1))
    # 21 - 12 = 9 px between three blocks: 5 then 4 (extra pixel to the earlier gap).
    assert band_ys(r) == [(0, 4), (9, 4), (17, 4)]


def test_spread_with_one_block_centres_it():
    blocks, styles = spacers(("b1", 4, None))
    r = run(blocks, styles, Rect(0, 0, 64, 20), layout=ResolvedLayout("stack", "spread", 1))
    assert band_ys(r) == [(8, 4)]


def test_int_and_fractional_heights():
    blocks, styles = spacers(("b1", 3, None), ("b2", 0.5, None))
    r = run(blocks, styles, Rect(0, 0, 64, 21))
    assert band_ys(r) == [(0, 3), (4, 10)]


def test_fill_canvas_takes_remaining_height():
    blocks = [spacer("s1", 0, 10), canvas("c1", 1, {"pixels": ["r"], "palette": {"r": "#ff0000"}})]
    styles = {"s1": style(height=10), "c1": style(height="fill")}
    r = run(blocks, styles, Rect(0, 0, 64, 64))
    (op,) = [op for op in r.ops if op.kind == "bitmap"]
    assert (op.y, op.h, op.w) == (11, 64 - 10 - 1, 64)


def test_fill_blocks_share_the_remainder_with_extra_pixels_to_earlier():
    blocks, styles = spacers(("f1", "fill", None), ("f2", "fill", None))
    r = run(blocks, styles, Rect(0, 0, 64, 10))
    assert band_ys(r) == [(0, 5), (6, 4)]


def test_fill_block_with_no_room_is_dropped():
    blocks, styles = spacers(("b1", 10, None), ("f1", "fill", None))
    r = run(blocks, styles, Rect(0, 0, 64, 11))
    assert r.shown == ("b1",)
    assert [(i.code, i.path) for i in r.issues] == [("dropped", ("blocks", "f1"))]


def test_canvas_auto_height_keeps_its_content_aspect():
    blk = canvas("c1", 0, {"size": [8, 2], "pixels": ["r"], "palette": {"r": "#ff0000"}})
    r = run([blk], {"c1": style(height="auto")}, Rect(0, 0, 32, 32))
    (op,) = r.ops
    assert (op.w, op.h) == (32, 32 * 2 // 8)


def test_canvas_auto_height_without_a_size_fills():
    blk = canvas("c1", 0, {"pixels": ["r"], "palette": {"r": "#ff0000"}})
    r = run([blk], {"c1": style(height="auto")}, Rect(0, 0, 32, 20))
    (op,) = r.ops
    assert (op.y, op.h) == (0, 20)


def test_block_background_band_spans_the_rect_width():
    blocks, styles = spacers(("b1", 6, None))
    r = run(blocks, styles, Rect(7, 3, 20, 30))
    (op,) = r.ops
    assert (op.kind, op.x, op.y, op.w, op.h, op.color) == ("rect", 7, 3, 20, 6, BG)


def test_stack_never_draws_outside_its_rect():  # regions constraint
    many = [
        spacer("s1", 0, 9),
        canvas("c1", 1, {"size": [1, 1], "pixels": ["r"], "palette": {"r": "#ff0000"}}),
        spacer("s2", 2, 9),
        canvas("c2", 3, {"pixels": ["g"], "palette": {"g": "#00ff00"}}),
    ]
    styles = {
        "s1": style(background=BG, height=9),
        "c1": style(height="auto"),
        "s2": style(background=BG, height=9),
        "c2": style(height="fill"),
    }
    r = run(many, styles, Rect(10, 5, 30, 20))
    lit = lit_pixels(r.frame(64, 64))
    assert lit and all(10 <= x < 40 and 5 <= y < 25 for x, y in lit)


#: Text wider and taller than the 30 x 20 rect at (10, 5), one case each:
#: ``(markup, style overrides)``.
OVERSIZED_TEXT = {
    "right_aligned_ellipsis": ("W" * 40, {"align": "right", "overflow": "ellipsis"}),
    "centred_ellipsis": ("W" * 40, {"align": "center", "overflow": "ellipsis"}),
    "wrapped_taller_than_the_rect": (" ".join(["WWWW"] * 20), {"overflow": "wrap"}),
    "block_span_background": ("{white/red:" + "W" * 40 + "}", {"overflow": "ellipsis"}),
}


@pytest.mark.parametrize("case", sorted(OVERSIZED_TEXT))
def test_stack_never_draws_text_outside_its_rect(case):  # regions constraint, through the real fit_text
    markup, overrides = OVERSIZED_TEXT[case]
    r = run([text("t1", 0, markup)], {"t1": style(**overrides)}, Rect(10, 5, 30, 20))
    lit = lit_pixels(r.frame(64, 64))
    assert lit and all(10 <= x < 40 and 5 <= y < 25 for x, y in lit)


def test_stack_clips_text_its_fit_let_overflow():  # regions constraint, the final clip itself
    # fit_text can hand back a line wider than the rect: wrapping 'WW' at
    # scale 2 into a 4 px column leaves one 10 px glyph per line, as no
    # narrower break exists. Only the final clip keeps those glyphs inside.
    wide = SizedFace(face_for_led_font("5x7"), 2)
    r = run([text("t1", 0, "WW")], {"t1": style(sized=wide, overflow="wrap")}, Rect(10, 5, 4, 40))
    lit = lit_pixels(r.frame(64, 64))
    assert lit and all(10 <= x < 14 and 5 <= y < 45 for x, y in lit)


def test_frame_paints_the_page_background_under_the_ops():
    blocks, styles = spacers(("b1", 2, None))
    frame = run(blocks, styles, Rect(0, 0, 4, 4)).frame(4, 4, "#0000ff")
    assert frame.pixels[0:3] == bytes((255, 0, 0)) and frame.pixels[-3:] == bytes((0, 0, 255))


def test_rect_smaller_than_the_smallest_face_draws_no_text_and_reports():
    blocks = [text("t1", 0, "HI")]
    r = run(blocks, {"t1": style()}, Rect(0, 0, 64, 4))
    assert r.ops == () and r.shown == ()
    assert r.issues == (
        LayoutIssue(path=(), code="surface_too_small", severity="warning", message=r.issues[0].message),
    )


def test_empty_stack_draws_nothing():
    r = run([], {}, Rect(0, 0, 64, 64))
    assert (r.ops, r.issues, r.shown) == ((), (), ())


# --- text ------------------------------------------------------------------------


def test_empty_and_unavailable_variable_blocks():  # [RF-1]
    blocks = [text("b1", 0, ""), text("b2", 1, "???"), text("b3", 2, "B")]
    styles = {b.id: style() for b in blocks}
    r = run(blocks, styles, Rect(0, 0, 64, 64))
    assert r.shown == ("b2", "b3")  # empty text takes zero height, "???" renders as text
    assert min(op.y for op in r.ops if op.kind == "glyph") == 0


@pytest.mark.parametrize("overflow", ["wrap", "ellipsis"])
def test_text_that_fits_to_nothing_is_reported_not_dropped_silently(overflow):
    # 'WW' at 5x7 scale 2 is one 10 px glyph wider than the 4 px rect and the
    # line, wrapped or cut, keeps nothing: fitting must still say so.
    wide = SizedFace(face_for_led_font("5x7"), 2)
    r = run([text("t1", 0, "WW")], {"t1": style(sized=wide, overflow=overflow)}, Rect(0, 0, 4, 20))
    assert r.ops == () and r.shown == ()
    codes = [issue.code for issue in r.issues]
    assert codes and codes[-1] == "dropped"
    assert {"wrapped" if overflow == "wrap" else "ellipsized"} <= set(codes)
    assert all(issue.path == ("blocks", "t1") for issue in r.issues)
    assert r.issues[-1].severity == "warning" and "t1" in r.issues[-1].message


def test_empty_text_block_is_not_reported():
    r = run([text("b1", 0, ""), text("b2", 1, "   ")], {"b1": style(), "b2": style()}, Rect(0, 0, 64, 64))
    assert (r.ops, r.issues, r.shown) == ((), (), ())


def test_text_aligns_within_the_rect():
    blocks = [text("b1", 0, "AB")]
    w = measure([MGlyph(t) for t in blocks[0].tokens], S35)
    for align, x in (("left", 10), ("center", 10 + (40 - w) // 2), ("right", 10 + 40 - w)):
        r = run(blocks, {"b1": style(align=align)}, Rect(10, 0, 40, 20))
        assert min(op.x for op in r.ops if op.kind == "glyph") == x
