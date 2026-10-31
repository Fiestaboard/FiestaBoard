"""The character-grid cell layout (plan Task 9).

Blocks are laid out in the board's one character size: wrapped by tiles,
aligned with spaces, stacked one row per spacer, with priority drops and
``valign`` counted in rows. Expanded blocks are stand-ins with the fields
``ExpandedBlock`` carries: ``markup`` holds each fill as the sentinel
``U+E000 + i`` and ``fills`` its spec.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.layout.cells import CellLayout, layout_cell_grid
from src.layout.expand import FILL_SENTINEL_BASE, FillSpec
from src.layout.style import ResolvedLayout, ResolvedStyle
from src.markup import BoardToken, count_tiles
from src.pages.flexible import Block
from src.templates.engine import TemplateEngine

TOP = ResolvedLayout("stack", "top", 0)
_FILL = re.compile(r"\{\{(fill_space|filled:([^}]*))\}\}")


@dataclass(frozen=True)
class Blk:
    """The fields of an expanded block the cell layout reads (Task 6's ``ExpandedBlock``)."""

    id: str
    kind: str
    index: int
    priority: int | None
    block: Block
    markup: str = ""
    fills: tuple[FillSpec, ...] = ()
    tokens: tuple[BoardToken, ...] = field(default=())


def style(*, align: str = "left", overflow: str = "wrap") -> ResolvedStyle:
    return ResolvedStyle(
        family="fiesta",
        sized=None,
        px=0,
        color=None,
        background=None,
        align=align,
        case="as-is",
        overflow=overflow,
        height="auto",
        fit=False,
    )


def text(bid: str, index: int, source: str, *, priority: int | None = None) -> Blk:
    """A text block whose ``{{fill_space}}``/``{{filled:X}}`` become sentinels, as expansion leaves them."""
    fills: list[FillSpec] = []

    def sentinel(match: re.Match[str]) -> str:
        fills.append(FillSpec(match.group(2)))
        return chr(FILL_SENTINEL_BASE + len(fills) - 1)

    markup = _FILL.sub(sentinel, source)
    return Blk(bid, "text", index, priority, Block(id=bid, kind="text", text=source), markup, tuple(fills))


def spacer(bid: str, index: int, *, priority: int | None = None) -> Blk:
    return Blk(bid, "spacer", index, priority, Block(id=bid, kind="spacer"))


def canvas(bid: str, index: int) -> Blk:
    return Blk(bid, "canvas", index, None, Block(id=bid, kind="canvas", canvas={"source": "{{art.canvas}}"}))


def expanded(
    texts: list[str], *, align: str = "left", overflow: str = "wrap", priorities: list[int | None] | None = None
) -> tuple[list[Blk], dict[str, ResolvedStyle]]:
    prios = priorities or [None] * len(texts)
    blocks = [text(f"b{i + 1}", i, t, priority=p) for i, (t, p) in enumerate(zip(texts, prios, strict=True))]
    return blocks, {b.id: style(align=align, overflow=overflow) for b in blocks}


def lay(
    blocks_styles: tuple[list[Blk], dict[str, ResolvedStyle]],
    rows: int,
    cols: int,
    *,
    layout: ResolvedLayout = TOP,
    report_styles: bool = True,
    **kw: Any,
) -> CellLayout:
    blocks, styles = blocks_styles
    return layout_cell_grid(blocks, styles, rows, cols, layout=layout, report_styles=report_styles, **kw)


def codes(out: CellLayout) -> list[tuple[tuple[str, ...], str]]:
    return [(i.path, i.code) for i in out.issues]


BLANK22 = " " * 22


# --- text fitting ------------------------------------------------------------


def test_flagship_wraps_by_characters_and_centres():
    out = lay(expanded(["GOOD MORNING SUNSHINE AND FRIENDS"], align="center"), 6, 22)
    assert out.lines == (
        "GOOD MORNING SUNSHINE ",
        "     AND FRIENDS      ",
        BLANK22,
        BLANK22,
        BLANK22,
        BLANK22,
    )
    assert all(count_tiles(line) <= 22 for line in out.lines)


def test_wrap_reports_wrapped_info_at_the_block_path():
    out = lay(expanded(["GOOD MORNING SUNSHINE AND FRIENDS"]), 6, 22)
    assert [(i.path, i.code, i.severity) for i in out.issues] == [(("blocks", "b1"), "wrapped", "info")]


def test_line_that_fits_is_one_row_with_no_issue():
    out = lay(expanded(["HELLO"]), 3, 22)
    assert out.lines == ("HELLO" + " " * 17, BLANK22, BLANK22) and out.issues == ()


def test_right_align_pads_on_the_left_by_tiles():
    out = lay(expanded(["{red}HI"], align="right"), 1, 5)
    assert out.lines == ("  {red}HI",)


def test_ellipsis_keeps_cols_minus_one_tiles_and_a_dot():
    out = lay(expanded(["ABCDEFGHIJ"], overflow="ellipsis"), 2, 5)
    assert out.lines == ("ABCD.", "     ")
    assert [(i.code, i.severity) for i in out.issues] == [("ellipsized", "warning")]


def test_shrink_wraps_and_reports_shrink_unavailable():
    out = lay(expanded(["AB CD"], overflow="shrink"), 2, 3)
    assert out.lines == ("AB ", "CD ")
    assert ("shrunk", "info") in [(i.code, i.severity) for i in out.issues]


def test_colour_span_markup_survives_wrap():
    out = lay(expanded(["{red:HOT HOT HOT}"]), 3, 5)
    assert out.lines[0].startswith("{red:") and out.lines[1].startswith("{red:")
    assert all(count_tiles(line) <= 5 for line in out.lines)


def test_newline_in_markup_starts_a_new_row():
    out = lay(expanded(["AB\nCD"]), 3, 4)
    assert out.lines == ("AB  ", "CD  ", "    ")


# --- fills -------------------------------------------------------------------


def test_fill_space_in_cells_fills_the_row():
    out = lay(expanded(["A{{fill_space}}B"]), 6, 22)
    assert out.lines[0] == "A" + " " * 20 + "B"


def test_pattern_fill_repeats_its_pattern():
    out = lay(expanded(["A{{filled:-}}B"]), 1, 6)
    assert out.lines == ("A----B",)


def test_fill_uses_the_engine_given():
    calls: list[tuple[str, int]] = []

    class Engine(TemplateEngine):
        def resolve_fill(self, text: str, width: int, *, extended_markup: bool = True) -> str:
            calls.append((text, width))
            return "X" * width

    out = lay(expanded(["A{{fill_space}}B"]), 1, 4, engine=Engine())
    assert calls == [("A\x00FILL_SPACE\x00B", 4)] and out.lines == ("XXXX",)


def test_fills_in_a_wrapped_line_take_no_room():
    out = lay(expanded(["AB{{fill_space}} CD"]), 2, 3)
    assert out.lines == ("AB ", "CD ")


# --- stacking ----------------------------------------------------------------


def test_empty_text_block_takes_no_row():
    out = lay(expanded(["", "???"]), 2, 3)
    assert out.lines == ("???", "   ") and out.issues == ()


def test_spacer_takes_one_row():
    blocks, styles = expanded(["A", "B"])
    blocks.insert(1, spacer("s1", 1))
    styles["s1"] = style()
    out = layout_cell_grid(blocks, styles, 3, 1, layout=TOP, report_styles=True)
    assert out.lines == ("A", " ", "B")


def test_rows_overflow_drops_lowest_priority():
    out = lay(expanded(["A", "B", "C"], priorities=[1, None, 2]), 2, 1)
    assert out.lines == ("A", "C")
    assert codes(out) == [(("blocks", "b2"), "dropped")]


def test_shown_lists_blocks_that_take_rows_in_page_order():
    blocks, styles = expanded(["A", "", "C", "D"], priorities=[1, None, 2, 3])
    blocks.append(canvas("c1", 4))
    out = lay((blocks, styles), 2, 1)
    assert out.shown == ("b1", "b3")


def test_rows_overflow_drops_highest_number_then_later_blocks_first():
    out = lay(expanded(["A", "B", "C"], priorities=[2, 1, 2]), 1, 1)
    assert out.lines == ("B",)
    assert codes(out) == [(("blocks", "b3"), "dropped"), (("blocks", "b1"), "dropped")]


def test_rows_past_the_grid_are_dropped_with_an_issue():
    out = lay(expanded(["A B C D"]), 2, 1)
    assert out.lines == ("A", "B")
    assert (("blocks", "b1"), "dropped") in codes(out)


def test_issue_paths_carry_the_prefix():
    out = lay(expanded(["A", "B"]), 1, 1, path=("regions", "r1"))
    assert codes(out) == [(("regions", "r1", "blocks", "b2"), "dropped")]


def test_valign_middle_centres_the_rows():
    out = lay(expanded(["A", "B"]), 5, 1, layout=ResolvedLayout("stack", "middle", 0))
    assert out.lines == (" ", "A", "B", " ", " ")


def test_valign_bottom_puts_the_rows_last():
    out = lay(expanded(["A", "B"]), 4, 1, layout=ResolvedLayout("stack", "bottom", 0))
    assert out.lines == (" ", " ", "A", "B")


def test_valign_spread_shares_spare_rows_between_blocks():
    out = lay(expanded(["A", "B", "C"]), 6, 1, layout=ResolvedLayout("stack", "spread", 0))
    assert out.lines == ("A", " ", " ", "B", " ", "C")


def test_gap_is_zero_rows_in_cells():
    out = lay(expanded(["A", "B"]), 2, 1, layout=ResolvedLayout("stack", "top", 4))
    assert out.lines == ("A", "B") and out.issues == ()


# --- canvas and report_styles ------------------------------------------------


def test_canvas_block_reported_only_when_cells_are_what_shows():
    blocks, styles = expanded(["A"])
    blocks.append(canvas("c1", 1))
    styles["c1"] = style()
    shown = layout_cell_grid(blocks, styles, 2, 1, layout=TOP, report_styles=True)
    hidden = layout_cell_grid(blocks, styles, 2, 1, layout=TOP, report_styles=False)
    assert shown.lines == hidden.lines == ("A", " ")
    assert [(i.path, i.code, i.severity) for i in shown.issues] == [(("blocks", "c1"), "canvas_not_drawn", "warning")]
    assert hidden.issues == ()


def test_cells_under_a_frame_report_nothing():
    out = lay(expanded(["LONG WORDS HERE", "B"], overflow="shrink", priorities=[1, 2]), 1, 5, report_styles=False)
    assert out.lines == ("LONG ",) and out.issues == ()


def test_zero_rows_is_an_empty_grid():
    out = lay(expanded(["A"]), 0, 0)
    assert out.lines == ()
