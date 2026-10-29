"""The flexible layout entry point: one page laid out for one board (spec section 5).

:func:`layout_flexible_page` runs the whole pipeline: resolve the page's
layout, resolve every block's style down the cascade (device default, board
style, page style, block style), expand the blocks against the board's
context, then

- on a pixel board, stack them over the whole surface and paint the frame;
- on every board, lay them out as cells at the board's character grid (on a
  pixel board those cells lie hidden under the frame, spec section 6).

Every compromise is returned as a :class:`LayoutIssue`; nothing here raises
for content a board cannot show.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.led.matrix import DEFAULT_LED_TILE_GAP, LedFrame, LedRenderOptions

from .cells import layout_cell_grid
from .fonts import (
    DEFAULT_FONT_FAMILY,
    FONT_FAMILIES,
    face_for_led_font,
    named_size_heights,
    size_ladder,
)
from .issues import LayoutIssue
from .stack import Rect, stack
from .style import ResolvedStyle, resolve_block_style, resolve_layout

if TYPE_CHECKING:
    from src.pages.models import Page
    from src.templates.engine import TemplateEngine

    from .target import FlexTarget

__all__ = ["FlexRender", "layout_flexible_page", "named_size_scale"]


@dataclass(frozen=True)
class FlexRender:
    """A flexible page laid out for one board.

    ``frame`` is the full-frame image (pixel boards only, else ``None``);
    ``cell_lines`` the page at the board's character grid; ``issues`` every
    compromise, frame issues first, then cell issues, one per ``(path,
    code)``; ``shown`` the ids of the blocks drawn, in page order.
    """

    frame: LedFrame | None
    cell_lines: tuple[str, ...]
    issues: tuple[LayoutIssue, ...]
    shown: tuple[str, ...]


def _level(style: Any) -> Mapping[str, Any] | None:
    """A page or block style model as a cascade level (unset properties fall through)."""
    if style is None:
        return None
    return style.model_dump(exclude_none=True)


def _deduplicated(issues: Iterable[LayoutIssue]) -> tuple[LayoutIssue, ...]:
    """``issues`` in order, keeping the first of each ``(path, code)``."""
    seen: set[tuple[tuple[str, ...], str]] = set()
    out: list[LayoutIssue] = []
    for issue in issues:
        key = (issue.path, issue.code)
        if key not in seen:
            seen.add(key)
            out.append(issue)
    return tuple(out)


def _render_options(target: FlexTarget) -> LedRenderOptions:
    display = target.display
    charset = display.character_set if display is not None else None
    return LedRenderOptions(
        monochrome=target.monochrome,
        glyphs=charset.get("glyphs") if charset else None,
        tile_gap=(display.tile_gap if display is not None else None) or DEFAULT_LED_TILE_GAP,
    )


def layout_flexible_page(
    page: Page,
    target: FlexTarget,
    context: Mapping[str, Any],
    *,
    engine: TemplateEngine | None = None,
) -> FlexRender:
    """Lay ``page`` out for ``target`` with plugin data ``context``.

    ``engine`` expands templates and colour expressions (default: the shared
    template engine). Issue paths point into the page document: ``("layout",
    …)``, ``("style", …)`` for the page's own background, ``("blocks", id,
    …)`` for a block. Style issues of a block hidden by its ``if`` are not
    reported, as the block itself is hidden silently.
    """
    from .expand import expand_blocks  # Task 6

    layout, layout_issues = resolve_layout(page.layout, path=("layout",))
    page_level = _level(page.style)

    styles: dict[str, ResolvedStyle] = {}
    style_issues: dict[str, list[LayoutIssue]] = {}
    for block in page.blocks or []:
        path = ("blocks", block.id)
        styles[block.id], style_issues[block.id] = resolve_block_style(
            [target.board_style, page_level, _level(block.style)], target, context, path=path, engine=engine
        )

    blocks, expand_issues = expand_blocks(page, target, context, styles, engine=engine)

    frame_issues: list[LayoutIssue] = list(layout_issues)
    for block in blocks:
        frame_issues.extend(style_issues.get(block.id, ()))
    frame_issues.extend(expand_issues)

    frame: LedFrame | None = None
    shown: tuple[str, ...] | None = None
    if target.pixels and target.width is not None and target.height is not None:
        page_style, page_style_issues = resolve_block_style(
            [target.board_style, page_level], target, context, path=(), engine=engine
        )
        frame_issues.extend(i for i in page_style_issues if i.path == ("style", "background"))
        result = stack(
            blocks,
            styles,
            Rect(0, 0, target.width, target.height),
            layout=layout,
            options=_render_options(target),
            context=context,
            family=page_style.family,
        )
        frame_issues.extend(result.issues)
        frame = result.frame(target.width, target.height, page_style.background)
        shown = result.shown

    cells = layout_cell_grid(
        blocks,
        styles,
        target.rows,
        target.cols,
        layout=layout,
        report_styles=not target.pixels,
        engine=engine,
    )
    return FlexRender(
        frame=frame,
        cell_lines=cells.lines,
        issues=_deduplicated([*frame_issues, *cells.issues]),
        shown=shown if shown is not None else cells.shown,
    )


def named_size_scale(target: FlexTarget) -> dict[str, int]:
    """The pixel height each named size draws at on ``target`` (for a capability brief).

    The same mapping the style resolver applies, in the board's default font
    family. A cell board has one
    character size, so it has no named sizes: ``{}``.
    """
    if not target.pixels or target.height is None:
        return {}
    requested = target.board_style.get("font")
    family = FONT_FAMILIES.get(requested if isinstance(requested, str) else "", FONT_FAMILIES[DEFAULT_FONT_FAMILY])
    try:
        default_height = face_for_led_font(target.default_face_id or "").pixel_height
    except KeyError:
        default_height = size_ladder(family)[0].height
    return named_size_heights(surface_height=target.height, default_height=default_height, family=family)
