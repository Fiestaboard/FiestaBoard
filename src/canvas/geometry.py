"""Where a canvas sits: character areas to panel pixels, text spans, grid retargets.

Design §2. A pixel-matrix board's character grid comes from
:func:`src.led.matrix.grid_layout` — origin ``(ox, oy)``, glyph box
``gw × gh`` and gutters ``sx × sy`` from the board's LED font, so the pitch
is ``(gw + sx, gh + sy)``. A 1-based area maps to the half-open pixel rect::

    x0 = ox + (col - 1) * px            x1 = ox + (col - 1 + cols) * px - sx
    y0 = oy + (row - 1) * py            y1 = oy + (row - 1 + rows) * py - sy

Gutters *inside* the area belong to the canvas; the trailing gutter does not.
A ``bleed`` side extends to the panel edge only where the area touches that
edge of the grid. The canvas pixel grid is ``floor(w / scale) × floor(h / scale)``
panel-pixel blocks, centred in the rect (leftover split with the extra pixel
on the right / bottom).

Cell helpers (:func:`covered_cells`, :func:`free_spans`) work in 0-based
``(row, col)`` indices of the page grid, with spans half-open.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from src.led.fonts import LED_FONTS
from src.led.matrix import LedGridLayout

from .models import Canvas, CanvasArea

__all__ = [
    "CanvasPlacement",
    "PixelRect",
    "area_rect",
    "canvas_placement",
    "clamp_area",
    "covered_cells",
    "free_spans",
    "scale_area",
]


@dataclass(frozen=True)
class PixelRect:
    """A rect in panel pixels: top-left ``(x, y)``, size ``w × h``."""

    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class CanvasPlacement:
    """A canvas on the panel.

    ``rect`` is the area's pixel rect (bleed applied). The canvas has
    ``width × height`` canvas pixels, each a ``scale × scale`` panel block;
    canvas pixel ``(0, 0)`` starts at panel pixel ``(x, y)``.
    """

    rect: PixelRect
    x: int
    y: int
    width: int
    height: int
    scale: int


def clamp_area(area: CanvasArea, rows: int, cols: int) -> CanvasArea | None:
    """*area* cut to a ``rows × cols`` grid, or ``None`` when it starts outside it."""
    if area.row > rows or area.col > cols:
        return None
    return CanvasArea(
        row=area.row,
        col=area.col,
        rows=min(area.rows, rows - area.row + 1),
        cols=min(area.cols, cols - area.col + 1),
    )


def area_rect(area: CanvasArea, bleed: Sequence[str], grid: LedGridLayout) -> PixelRect | None:
    """The panel pixel rect of *area* on *grid*, ``None`` when the area is off the grid."""
    clamped = clamp_area(area, grid.rows, grid.cols)
    if clamped is None:
        return None
    face = LED_FONTS[grid.font]
    sx, sy = face.spacing_x, face.spacing_y
    px, py = face.glyph_width + sx, face.glyph_height + sy
    x0 = grid.origin_x + (clamped.col - 1) * px
    y0 = grid.origin_y + (clamped.row - 1) * py
    x1 = grid.origin_x + (clamped.col - 1 + clamped.cols) * px - sx
    y1 = grid.origin_y + (clamped.row - 1 + clamped.rows) * py - sy
    sides = {"top", "left", "right", "bottom"} if "all" in bleed else set(bleed)
    if "left" in sides and clamped.col == 1:
        x0 = 0
    if "top" in sides and clamped.row == 1:
        y0 = 0
    if "right" in sides and clamped.col - 1 + clamped.cols == grid.cols:
        x1 = grid.width
    if "bottom" in sides and clamped.row - 1 + clamped.rows == grid.rows:
        y1 = grid.height
    return PixelRect(x0, y0, x1 - x0, y1 - y0)


def canvas_placement(canvas: Canvas, grid: LedGridLayout) -> CanvasPlacement | None:
    """Where *canvas* draws on *grid*; ``None`` if it is off the grid or smaller than one scaled pixel."""
    rect = area_rect(canvas.area, canvas.bleed, grid)
    if rect is None:
        return None
    scale = canvas.scale
    width, height = rect.w // scale, rect.h // scale
    if width < 1 or height < 1:
        return None
    return CanvasPlacement(
        rect=rect,
        x=rect.x + (rect.w - width * scale) // 2,
        y=rect.y + (rect.h - height * scale) // 2,
        width=width,
        height=height,
        scale=scale,
    )


def covered_cells(canvases: Iterable[Canvas], rows: int, cols: int) -> set[tuple[int, int]]:
    """0-based ``(row, col)`` of every grid cell under any canvas (``hide`` and ``flow``), clamped to the grid."""
    cells: set[tuple[int, int]] = set()
    for canvas in canvases:
        area = clamp_area(canvas.area, rows, cols)
        if area is None:
            continue
        for r in range(area.row - 1, area.row - 1 + area.rows):
            for c in range(area.col - 1, area.col - 1 + area.cols):
                cells.add((r, c))
    return cells


def free_spans(canvases: Iterable[Canvas], rows: int, cols: int) -> list[list[tuple[int, int]]]:
    """Per grid row, the half-open ``(start_col, end_col)`` runs text may flow into.

    Only ``text: "flow"`` canvases take columns away (``hide`` canvases
    blank their cells after text renders, see :func:`covered_cells`). Spans
    are in reading order; a fully covered row has none.
    """
    blocked = [[False] * cols for _ in range(rows)]
    for r, c in covered_cells((cv for cv in canvases if cv.text == "flow"), rows, cols):
        blocked[r][c] = True
    out: list[list[tuple[int, int]]] = []
    for row in blocked:
        spans: list[tuple[int, int]] = []
        start = None
        for c, taken in enumerate(row):
            if not taken and start is None:
                start = c
            elif taken and start is not None:
                spans.append((start, c))
                start = None
        if start is not None:
            spans.append((start, cols))
        out.append(spans)
    return out


def _round_half_up(value: float) -> int:
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def scale_area(area: CanvasArea, old_grid: tuple[int, int], new_grid: tuple[int, int]) -> CanvasArea:
    """*area* retargeted from an ``(rows, cols)`` grid to another, proportionally.

    Used when a board's text size changes the grid. Start offsets and spans
    scale by ``new / old`` and round half up; a span is at least 1, and the
    result is clamped to the new grid (start first, then span).
    """
    (old_rows, old_cols), (new_rows, new_cols) = old_grid, new_grid

    def axis(start: int, span: int, old: int, new: int) -> tuple[int, int]:
        begin = min(new, _round_half_up((start - 1) * new / old) + 1)
        length = max(1, _round_half_up(span * new / old))
        return begin, min(length, new - begin + 1)

    row, rows = axis(area.row, area.rows, old_rows, new_rows)
    col, cols = axis(area.col, area.cols, old_cols, new_cols)
    return CanvasArea(row=row, col=col, rows=rows, cols=cols)
