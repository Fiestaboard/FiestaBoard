"""The vertical stack: blocks laid top to bottom inside one rect (spec section 5, step 5).

:func:`stack` works over an arbitrary :class:`Rect`, not the whole surface,
so a later ``regions`` layout kind can run one stack per region. It measures
every block, drops blocks from the lowest priority upward until the fixed
heights fit (one ``dropped`` issue each), shares what is left between
``fill`` blocks, places the stack by ``valign`` and emits draw ops. Every op
is clipped to the rect.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.led.matrix import LedDrawOp, LedFrame, LedRenderOptions

from .fonts import FONT_FAMILIES, FontFamily, size_ladder
from .issues import LayoutIssue
from .measure import fit_text, measure
from .pixels import canvas_block_op, clip_op, draw_line, frame_from_ops

if TYPE_CHECKING:
    from .style import ResolvedLayout, ResolvedStyle

__all__ = ["Rect", "StackResult", "stack"]

_FILL = "fill"


@dataclass(frozen=True)
class Rect:
    """A rectangle of matrix pixels: top-left (``x``, ``y``), ``w`` wide, ``h`` tall."""

    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class StackResult:
    """A laid-out stack: its draw ops, the issues met and the ids of the blocks shown, in order."""

    ops: tuple[LedDrawOp, ...]
    issues: tuple[LayoutIssue, ...]
    shown: tuple[str, ...]

    def frame(self, width: int, height: int, background: str | None = None) -> LedFrame:
        """The ops painted over a ``width x height`` frame filled with ``background``."""
        return frame_from_ops(width, height, self.ops, background)


@dataclass
class _Entry:
    block: Any
    style: ResolvedStyle
    height: int | str
    fitted: Any = None


def _has_glyphs(fitted: Any) -> bool:
    """Whether a fitted text block draws anything: a non-blank glyph or a block span."""
    for line in fitted.lines:
        for item in line:
            token = getattr(item, "token", None)
            if token is None:
                continue
            if token.type != "char" or token.icon or token.background or token.value.strip():
                return True
    return False


def _requested_height(value: Any, rect: Rect, auto: int | str) -> int | str:
    """A ``height`` style value in pixels (or ``"fill"``) within ``rect``."""
    if value == _FILL:
        return _FILL
    if isinstance(value, bool) or not isinstance(value, int | float):
        return auto
    if isinstance(value, float) and 0 < value <= 1:
        return math.floor(rect.h * value)
    return max(0, int(value))


def _canvas_auto(block: Any, rect: Rect) -> int | str:
    body = getattr(block.block, "canvas", None)
    size = getattr(getattr(body, "content", None), "size", None)
    if size:
        size_w, size_h = size
        return rect.w * size_h // size_w
    return _FILL


def _victim(visible: list[_Entry]) -> _Entry:
    """The block to drop next: unset priority first, then the highest number, later blocks first."""
    return max(
        visible,
        key=lambda e: (e.block.priority is None, e.block.priority or 0, e.block.index),
    )


def _dropped(entry: _Entry, path: tuple[str, ...], why: str) -> LayoutIssue:
    return LayoutIssue((*path, "blocks", entry.block.id), "dropped", "warning", f"block {entry.block.id!r} {why}")


def _place(heights: list[int], rect: Rect, gap: int, valign: str) -> list[int]:
    """The top ``y`` of each block."""
    n = len(heights)
    total = sum(heights) + gap * (n - 1)
    if valign == "spread" and n > 1:
        extra = rect.h - total
        each, rest = divmod(extra, n - 1)
        ys, y = [], rect.y
        for i, h in enumerate(heights):
            ys.append(y)
            y += h + gap + each + (1 if i < rest else 0)
        return ys
    if valign == "top":
        y = rect.y
    elif valign == "bottom":
        y = rect.y + rect.h - total
    else:  # middle; spread with one block
        y = rect.y + (rect.h - total) // 2
    ys = []
    for h in heights:
        ys.append(y)
        y += h + gap
    return ys


def _align_x(align: str, rect: Rect, w: int) -> int:
    if align == "center":
        return rect.x + (rect.w - w) // 2
    if align == "right":
        return rect.x + rect.w - w
    return rect.x


def stack(
    blocks: Sequence[Any],
    styles: Mapping[str, ResolvedStyle],
    rect: Rect,
    *,
    layout: ResolvedLayout,
    options: LedRenderOptions,
    context: Mapping[str, Any],
    family: FontFamily | str,
    path: tuple[str, ...] = (),
) -> StackResult:
    """Lay ``blocks`` (expanded, in page order) top to bottom inside ``rect``.

    ``styles`` maps each block id to its resolved style. Text is fitted to the
    rect (``fit_text``); a text block that draws nothing (empty after
    expansion) takes no height and no gap. Spacers are their ``height`` (auto:
    their size's height); canvases are their ``height`` (auto: the rect's
    width at their content's aspect, else ``fill``). When the rect is shorter
    or narrower than the family's smallest glyph, no text is drawn and one
    ``surface_too_small`` warning is reported.
    """
    fam = FONT_FAMILIES[family] if isinstance(family, str) else family
    smallest = size_ladder(fam)[0]
    too_small = rect.h < smallest.height or rect.w < smallest.face.glyph_width * smallest.scale
    issues: list[LayoutIssue] = []
    entries: list[_Entry] = []
    hidden_text = False
    for block in blocks:
        style = styles[block.id]
        if block.kind == "text":
            if too_small:
                hidden_text = True
                continue
            fitted = fit_text(block, style, rect.w, rect.h, family=fam, path=(*path, "blocks", block.id))
            height = fitted.height if _has_glyphs(fitted) else 0
            entries.append(_Entry(block, style, height, fitted))
        elif block.kind == "spacer":
            entries.append(_Entry(block, style, _requested_height(style.height, rect, style.px)))
        elif block.kind == "canvas":
            entries.append(_Entry(block, style, _requested_height(style.height, rect, _canvas_auto(block, rect))))
    if hidden_text:
        issues.append(
            LayoutIssue(
                path,
                "surface_too_small",
                "warning",
                f"a {rect.w}x{rect.h} area is smaller than the smallest text ({smallest.height}px); text not drawn",
            )
        )

    gap = layout.gap_px
    visible = [e for e in entries if e.height != 0 or e.block.kind != "text"]

    def fixed() -> int:
        return sum(e.height for e in visible if e.height != _FILL)

    while visible and fixed() + gap * (len(visible) - 1) > rect.h:
        victim = _victim(visible)
        visible.remove(victim)
        issues.append(_dropped(victim, path, "does not fit; dropped (lowest priority first)"))

    heights: dict[int, int] = {}
    while True:
        fills = [e for e in visible if e.height == _FILL]
        if not fills:
            break
        remaining = rect.h - fixed() - gap * (len(visible) - 1)
        share, extra = divmod(remaining, len(fills))
        if share < 1:
            victim = fills[-1]
            visible.remove(victim)
            issues.append(_dropped(victim, path, "has no room left to fill; dropped"))
            continue
        for i, e in enumerate(fills):
            heights[id(e)] = share + (1 if i < extra else 0)
        break

    sized_heights = [heights.get(id(e), e.height) for e in visible]
    ys = _place(sized_heights, rect, gap, layout.valign) if visible else []

    ops: list[LedDrawOp] = []
    for entry, y, h in zip(visible, ys, sized_heights, strict=True):
        band = Rect(rect.x, y, rect.w, h)
        style = entry.style
        if style.background and h > 0:
            ops.append(LedDrawOp("rect", band.x, band.y, style.background, w=band.w, h=band.h))
        if entry.block.kind == "text":
            fitted = entry.fitted
            sized = fitted.sized
            line_y = y
            for line in fitted.lines:
                x = _align_x(style.align, rect, measure(line, sized))
                draw_line(ops, line, x, line_y, sized, options, style.color)
                line_y += sized.height + sized.line_gap
            issues.extend(fitted.issues)
        elif entry.block.kind == "canvas":
            op, canvas_issues = canvas_block_op(entry.block, band, context, monochrome=options.monochrome, path=path)
            if op is not None:
                ops.append(op)
            issues.extend(canvas_issues)

    clipped = tuple(c for op in ops if (c := clip_op(op, rect)) is not None)
    return StackResult(ops=clipped, issues=tuple(issues), shown=tuple(e.block.id for e in visible))
