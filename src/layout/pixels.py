"""Pixel emit for flexible layout: text runs, canvas blocks and the frame.

Nothing here is a new rasteriser. Glyphs are drawn with
:func:`src.led.matrix.draw_glyph` (at the face's integer ``scale``), coloured
exactly as a grid cell is (:func:`src.led.matrix.cell_for_token`); canvas
blocks go through :func:`src.canvas.evaluate.resolve_canvas` and
:func:`src.canvas.raster.render_content`; the frame is painted with
:func:`src.led.matrix.paint_ops`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from src.canvas.evaluate import resolve_canvas
from src.canvas.models import Canvas
from src.canvas.raster import render_content
from src.led.matrix import (
    LedDrawOp,
    LedFrame,
    LedRenderOptions,
    cell_for_token,
    draw_glyph,
    glyph_key,
    monochrome_rgba,
    paint_ops,
    parse_hex_color,
)

from .issues import LayoutIssue

if TYPE_CHECKING:
    from .fonts import SizedFace
    from .stack import Rect

__all__ = ["UNLIT", "canvas_block_op", "clip_op", "draw_line", "frame_from_ops"]

#: The colour of a pixel that is drawn but not lit.
UNLIT = "#000000"


def _token_of(item: Any) -> Any:
    """A line item's token (a glyph), or ``None`` (a pixel gap)."""
    return getattr(item, "token", None)


def draw_line(
    ops: list[LedDrawOp],
    items: Iterable[Any],
    x: int,
    y: int,
    sized: SizedFace,
    options: LedRenderOptions,
    text_color: str | None,
) -> tuple[str, ...]:
    """Append the ops that draw one fitted line with its left edge at (``x``, ``y``).

    ``items`` are line items: a glyph (``.token``, one cell ``sized.advance``
    wide) or a gap (``.px`` extra pixels). Each glyph is coloured as a grid
    cell colours it. ``text_color`` ``None`` is unlit text (a mono panel's
    black text, or inverse video on a lit band): its glyphs draw black. A
    block-span background is a rect over the cell's glyph box, joined over the
    gutter to the next cell when that cell has the same background.
    """
    face = sized.face.led_font
    scale = sized.scale
    box_w = face.glyph_width * scale
    box_h = face.glyph_height * scale
    mono = options.monochrome
    color_in = text_color if text_color is not None else UNLIT
    custom = options.glyphs
    items = list(items)
    requested = {glyph_key(token, custom) for item in items if (token := _token_of(item)) is not None}
    rejected = {
        key
        for key, rows in (custom or {}).items()
        if len(rows) != face.glyph_height or any(len(row) != face.glyph_width for row in rows)
    }
    if rejected:
        custom = {key: rows for key, rows in custom.items() if key not in rejected}
        options = replace(options, glyphs=custom)
    cells = [
        cell_for_token(tok, color_in, mono, custom) if (tok := _token_of(item)) is not None else None for item in items
    ]
    cx = x
    for i, item in enumerate(items):
        cell = cells[i]
        if cell is None:
            cx += item.px
            continue
        if cell.background:
            nxt = cells[i + 1] if i + 1 < len(cells) else None
            joined = nxt is not None and nxt.background == cell.background
            ops.append(LedDrawOp("rect", cx, y, cell.background, w=box_w + (sized.gutter if joined else 0), h=box_h))
        color = cell.color
        if text_color is None and mono is not None and not cell.background:
            color = UNLIT
        draw_glyph(ops, cell.glyph, cx, y, face, color, options, scale=scale)
        cx += sized.advance
    return tuple(sorted(requested & rejected))


def canvas_block_op(
    block: Any,
    rect: Rect,
    context: Mapping[str, Any],
    *,
    monochrome: str | None = None,
    path: tuple[str, ...] = (),
) -> tuple[LedDrawOp | None, list[LayoutIssue]]:
    """A canvas block drawn into ``rect``: one ``bitmap`` op, or ``None`` when nothing draws.

    The block's canvas body becomes a synthetic one-cell ``Canvas`` so it is
    resolved (sources, formulas, palette) exactly as a grid page's canvas is,
    then rendered at ``rect``'s size. On a mono panel (``monochrome``, the
    panel's ``#rrggbb``) the pixels light in the panel colour. Each
    ``CanvasIssue`` is a ``canvas`` issue at
    ``(*path, "blocks", id, "canvas", issue.path)``.
    """
    block_path = (*path, "blocks", block.id, "canvas")
    if rect.w < 1 or rect.h < 1:
        return None, []
    body = getattr(block.block, "canvas", None)
    try:
        canvas = Canvas(
            id="flex",
            area={"row": 1, "col": 1, "rows": 1, "cols": 1},
            content=getattr(body, "content", None),
            source=getattr(body, "source", None),
        )
    except ValueError as exc:
        return None, [LayoutIssue(block_path, "canvas_not_drawn", "warning", f"canvas cannot be drawn: {exc}")]
    resolved, canvas_issues = resolve_canvas(canvas, context)
    issues = [LayoutIssue((*block_path, issue.path), "canvas", "warning", issue.message) for issue in canvas_issues]
    if resolved is None:
        return None, issues
    rgba = render_content(resolved, rect.w, rect.h)
    panel = parse_hex_color(monochrome) if monochrome else None
    if panel is not None:
        rgba = monochrome_rgba(rgba, panel)
    return LedDrawOp("bitmap", rect.x, rect.y, "", w=rect.w, h=rect.h, rgba=rgba), issues


def clip_op(op: LedDrawOp, rect: Rect) -> LedDrawOp | None:
    """``op`` cropped to ``rect``, or ``None`` when none of it is inside."""
    if op.kind == "glyph":
        w = max((len(row) for row in op.rows), default=0)
        h = len(op.rows)
    else:
        w, h = op.w, op.h
    x0, y0 = max(op.x, rect.x), max(op.y, rect.y)
    x1, y1 = min(op.x + w, rect.x + rect.w), min(op.y + h, rect.y + rect.h)
    if x1 <= x0 or y1 <= y0:
        return None
    if (x0, y0, x1, y1) == (op.x, op.y, op.x + w, op.y + h):
        return op
    dx, dy = x0 - op.x, y0 - op.y
    if op.kind == "rect":
        return LedDrawOp("rect", x0, y0, op.color, w=x1 - x0, h=y1 - y0)
    if op.kind == "glyph":
        rows = tuple(row[dx : dx + x1 - x0] for row in op.rows[dy : dy + y1 - y0])
        return LedDrawOp("glyph", x0, y0, op.color, rows=rows)
    stride = op.w * 4
    rgba = b"".join(
        op.rgba[(dy + r) * stride + dx * 4 : (dy + r) * stride + (dx + x1 - x0) * 4] for r in range(y1 - y0)
    )
    return LedDrawOp("bitmap", x0, y0, "", w=x1 - x0, h=y1 - y0, rgba=rgba)


def frame_from_ops(width: int, height: int, ops: Sequence[LedDrawOp], background: str | None) -> LedFrame:
    """A ``width x height`` frame: ``background`` (``#rrggbb``; ``None`` is unlit) under ``ops``."""
    rgb = parse_hex_color(background) if background else None
    pixels = bytearray(bytes(rgb) * (width * height)) if rgb else bytearray(width * height * 3)
    paint_ops(pixels, width, height, ops)
    return LedFrame(width, height, bytes(pixels))
