"""Pixel canvases: drawings that live inside pages on pixel-matrix boards.

Design record: ``docs/internal/reference/PIXEL_CANVAS.md``. This package is
the self-contained engine — data model (:mod:`.models`), placement on the LED
grid (:mod:`.geometry`), expression evaluation (:mod:`.evaluate`), the
pure-Python rasteriser (:mod:`.raster`) and the panel-pixel layers it yields
(:mod:`.layer`). Page storage and the render pipeline wire it in separately.
"""

from .evaluate import CanvasIssue, ResolvedContent, ResolvedShape, resolve_canvas, resolve_content
from .geometry import CanvasPlacement, PixelRect, area_rect, canvas_placement, covered_cells, free_spans, scale_area
from .layer import CanvasLayer, render_canvases, render_canvases_on_grid
from .models import Canvas, CanvasArea, CanvasContent, parse_color, validate_page_canvases

__all__ = [
    "Canvas",
    "CanvasArea",
    "CanvasContent",
    "CanvasIssue",
    "CanvasLayer",
    "CanvasPlacement",
    "PixelRect",
    "ResolvedContent",
    "ResolvedShape",
    "area_rect",
    "canvas_placement",
    "covered_cells",
    "free_spans",
    "parse_color",
    "render_canvases",
    "render_canvases_on_grid",
    "resolve_canvas",
    "resolve_content",
    "scale_area",
    "validate_page_canvases",
]
