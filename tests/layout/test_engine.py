"""The flexible layout entry point (plan Task 10).

The plan's end-to-end tests lay out :data:`SAMPLE` with the real expansion
and fit. The engine's own orchestration (which issues come first, which
levels are cascaded, what a cell target gets) is also pinned against a
stand-in expansion that turns each block's text into its markup unchanged,
so each rule is tested apart from what expansion does.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pytest

from src.layout import engine as engine_module
from src.layout.engine import FlexRender, layout_flexible_page, named_size_scale
from src.layout.issues import LayoutIssue
from src.layout.target import FlexTarget
from src.pages.flexible import Block
from src.pages.models import Page
from tests.layout.devices import SAMPLE, SAMPLE_CTX, golden_target, profile

# --- the plan's end-to-end tests ---------------------------------------------


def test_pixel_target_gets_frame_and_cells():
    r = layout_flexible_page(Page.model_validate(SAMPLE), golden_target("pixoo64_3x5"), SAMPLE_CTX)
    assert r.frame.width == 64 and len(r.frame.pixels) == 64 * 64 * 3
    # SAMPLE stacks with valign middle: its four cell rows start at row (10 - 4) // 2.
    assert len(r.cell_lines) == 10 and r.cell_lines[3] == " " * 5 + "12:45" + " " * 6


def test_cell_target_has_no_frame():
    r = layout_flexible_page(Page.model_validate(SAMPLE), golden_target("flagship"), SAMPLE_CTX)
    assert r.frame is None and len(r.cell_lines) == 6


def test_issue_paths_start_at_blocks():
    r = layout_flexible_page(Page.model_validate(SAMPLE), golden_target("strip_32x8"), SAMPLE_CTX)
    assert all(i.path[0] in ("blocks", "layout", "style") for i in r.issues)
    assert any(i.code == "dropped" for i in r.issues)


def test_tiny_surface_reports_instead_of_crashing():
    t = FlexTarget(rows=0, cols=0, display=replace(profile("hub75_64x32"), width=4, height=4))
    r = layout_flexible_page(Page.model_validate(SAMPLE), t, SAMPLE_CTX)
    assert r.cell_lines == () and any(i.code == "surface_too_small" for i in r.issues)


def test_frame_is_deterministic_for_identical_inputs():
    a = layout_flexible_page(Page.model_validate(SAMPLE), golden_target("pixoo64_5x7"), SAMPLE_CTX)
    b = layout_flexible_page(Page.model_validate(SAMPLE), golden_target("pixoo64_5x7"), SAMPLE_CTX)
    assert a.frame.pixels == b.frame.pixels


# --- orchestration, against a stand-in expansion -----------------------------


@dataclass(frozen=True)
class StubExpanded:
    """The fields of Task 6's ``ExpandedBlock`` the stack and the cell layout read."""

    id: str
    kind: str
    index: int
    priority: int | None
    block: Block
    markup: str = ""
    fills: tuple = ()
    tokens: tuple = ()


@pytest.fixture
def stub_expand(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace the engine's ``expand_blocks`` with markup-as-written expansion.

    A block whose ``if`` is ``"no"`` is hidden; a block with an unknown kind is
    skipped with ``block_kind_unsupported``. Returns the calls' arguments.
    """
    calls: list[dict[str, Any]] = []

    def expand_blocks(page, target, context, styles, *, engine=None):
        calls.append({"styles": dict(styles), "engine": engine, "context": context})
        shown, issues = [], []
        for index, block in enumerate(page.blocks or []):
            if block.if_ == "no":
                continue
            if block.kind not in ("text", "spacer", "canvas"):
                issues.append(LayoutIssue(("blocks", block.id), "block_kind_unsupported", "warning", "unknown kind"))
                continue
            shown.append(StubExpanded(block.id, block.kind, index, block.priority, block, block.text or ""))
        return shown, issues

    monkeypatch.setattr(engine_module, "expand_blocks", expand_blocks)
    return calls


def page(*blocks: dict[str, Any], **fields: Any) -> Page:
    return Page.model_validate({"name": "P", "type": "flexible", "blocks": list(blocks), **fields})


def spacer(bid: str, px: int, **fields: Any) -> dict[str, Any]:
    return {"id": bid, "kind": "spacer", **fields, "style": {"height": px, **fields.pop("style", {})}}


PIXOO = golden_target("pixoo64_3x5")
MAX7219 = golden_target("max7219_32x8")
FLAGSHIP = golden_target("flagship")


def pixel_at(render: FlexRender, x: int, y: int) -> str:
    i = (y * render.frame.width + x) * 3
    return "#" + render.frame.pixels[i : i + 3].hex()


def test_pixel_target_frame_is_the_surface_size(stub_expand):
    r = layout_flexible_page(page(spacer("s", 4)), PIXOO, {})
    assert (r.frame.width, r.frame.height, len(r.frame.pixels)) == (64, 64, 64 * 64 * 3)


def test_pixel_target_also_gets_cells_at_its_grid(stub_expand):
    r = layout_flexible_page(page(spacer("s", 4)), PIXOO, {})
    assert r.cell_lines == (" " * 16,) * 10


def test_frame_draws_stacked_block_backgrounds(stub_expand):
    r = layout_flexible_page(page(spacer("s", 4, style={"background": "#ff0000"})), PIXOO, {})
    assert (pixel_at(r, 0, 0), pixel_at(r, 63, 3), pixel_at(r, 0, 4)) == ("#ff0000", "#ff0000", "#000000")


def test_frame_background_is_the_page_background(stub_expand):
    r = layout_flexible_page(page(spacer("s", 4), style={"background": "#0000ff"}), PIXOO, {})
    assert pixel_at(r, 10, 40) == "#0000ff"


def test_mono_frame_draws_canvases_in_the_panel_colour(stub_expand):
    white = {"size": [4, 1], "palette": {"w": "#ffffff"}, "pixels": ["wwww"]}
    r = layout_flexible_page(page({"id": "c", "kind": "canvas", "canvas": {"content": white}}), MAX7219, {})
    assert pixel_at(r, 0, 0) == MAX7219.monochrome


def test_page_background_compromise_is_reported_at_the_page_style(stub_expand):
    r = layout_flexible_page(page(style={"background": "{{nope.color}}"}), PIXOO, {})
    assert [(i.path, i.code) for i in r.issues] == [(("style", "background"), "color_invalid")]


def test_layout_valign_places_the_stack(stub_expand):
    r = layout_flexible_page(
        page(spacer("s", 4, style={"background": "#ff0000"}), layout={"valign": "bottom"}), PIXOO, {}
    )
    assert (pixel_at(r, 0, 59), pixel_at(r, 0, 60)) == ("#000000", "#ff0000")


def test_shown_lists_the_blocks_the_stack_kept(stub_expand):
    r = layout_flexible_page(page(spacer("a", 40, priority=1), spacer("b", 40, priority=2)), PIXOO, {})
    assert r.shown == ("a",)


def test_cell_target_has_no_frame_and_shows_the_cell_layout(stub_expand):
    r = layout_flexible_page(page({"id": "t", "kind": "text", "text": "HELLO"}), FLAGSHIP, {})
    assert r.frame is None and r.cell_lines == ("HELLO" + " " * 17,) + (" " * 22,) * 5


def test_cell_target_shown_lists_the_blocks_in_the_cells(stub_expand):
    r = layout_flexible_page(
        page({"id": "t", "kind": "text", "text": "HI"}, {"id": "c", "kind": "canvas", "canvas": {}}), FLAGSHIP, {}
    )
    assert r.shown == ("t",)


def test_cells_under_a_frame_report_nothing(stub_expand):
    # Both 1px spacers fit the 8px strip; the one-row cell grid drops one, unseen under the frame.
    r = layout_flexible_page(page(spacer("a", 1), spacer("b", 1)), MAX7219, {})
    assert r.shown == ("a", "b") and r.issues == ()


def test_cell_target_reports_cell_issues(stub_expand):
    r = layout_flexible_page(page({"id": "c", "kind": "canvas", "canvas": {}}), FLAGSHIP, {})
    assert [(i.path, i.code) for i in r.issues] == [(("blocks", "c"), "canvas_not_drawn")]


def test_issues_come_layout_then_style_then_expansion_then_cells(stub_expand):
    p = page(
        {"id": "t", "kind": "text", "text": "HI", "style": {"size": "large"}},
        {"id": "x", "kind": "marquee"},
        {"id": "c", "kind": "canvas", "canvas": {}},
        layout={"kind": "regions"},
    )
    r = layout_flexible_page(p, FLAGSHIP, {})
    assert [(i.path, i.code) for i in r.issues] == [
        (("layout", "kind"), "layout_kind_unsupported"),
        (("blocks", "t", "style", "size"), "size_ignored"),
        (("blocks", "x"), "block_kind_unsupported"),
        (("blocks", "c"), "canvas_not_drawn"),
    ]


def test_issues_are_deduplicated_by_path_and_code_keeping_the_first(stub_expand):
    two_bad = {"id": "x", "kind": "marquee"}
    p = page({"id": "t", "kind": "text", "text": "HI"}, two_bad)

    def twice(page, target, context, styles, *, engine=None):
        issue = LayoutIssue(("blocks", "x"), "block_kind_unsupported", "warning", "first")
        again = LayoutIssue(("blocks", "x"), "block_kind_unsupported", "info", "second")
        return [StubExpanded("t", "text", 0, None, p.blocks[0], "HI")], [issue, again]

    engine_module.expand_blocks = twice  # restored by stub_expand's monkeypatch
    r = layout_flexible_page(p, FLAGSHIP, {})
    assert [(i.code, i.message) for i in r.issues] == [("block_kind_unsupported", "first")]


def test_style_issues_of_blocks_hidden_by_if_are_not_reported(stub_expand):
    p = page({"id": "t", "kind": "text", "text": "HI", "if": "no", "style": {"size": "large"}})
    assert layout_flexible_page(p, FLAGSHIP, {}).issues == ()


def test_styles_cascade_board_page_and_block(stub_expand):
    target = replace(PIXOO, board_style={"align": "right", "case": "upper", "overflow": "ellipsis"})
    p = page(
        {"id": "s", "kind": "spacer", "style": {"align": "center"}},
        style={"align": "left", "case": "lower"},
    )
    layout_flexible_page(p, target, {})
    s = stub_expand[0]["styles"]["s"]
    assert (s.align, s.case, s.overflow) == ("center", "lower", "ellipsis")


def test_engine_and_context_reach_expansion(stub_expand):
    engine, ctx = object(), {"clock": {"time": "12:45"}}
    layout_flexible_page(page(spacer("s", 1)), FLAGSHIP, ctx, engine=engine)
    assert stub_expand[0]["engine"] is engine and stub_expand[0]["context"] is ctx


def test_tiny_surface_reports_surface_too_small(stub_expand):
    t = FlexTarget(rows=0, cols=0, display=replace(profile("hub75_64x32"), width=4, height=4))
    r = layout_flexible_page(page({"id": "t", "kind": "text", "text": "HI"}), t, {})
    assert r.cell_lines == () and [i.code for i in r.issues] == ["surface_too_small"]


# --- named sizes -------------------------------------------------------------


def test_named_size_scale_on_a_pixel_board():
    assert named_size_scale(PIXOO) == {"small": 5, "medium": 5, "large": 15, "xlarge": 30}


def test_named_size_scale_follows_the_board_face():
    assert named_size_scale(golden_target("hub75_64x32")) == {"small": 5, "medium": 7, "large": 10, "xlarge": 15}


def test_named_size_scale_is_empty_on_a_cell_board():
    assert named_size_scale(FLAGSHIP) == {}
