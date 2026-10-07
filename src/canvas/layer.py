"""Canvas layers: rasterised canvases in panel pixels (design §3 steps 2-3, §4).

:func:`render_canvases` is the engine's entry point: it places each canvas on
the board's LED grid, resolves its content against the page's variable
context, rasterises it and returns one :class:`CanvasLayer` per drawable
canvas, in page order (later layers paint over earlier ones). Boards that are
not pixel matrices get no layers.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from src.led.matrix import DEFAULT_LED_FONT, LedGridLayout, grid_layout
from src.outputs.geometry import is_led_pixel_model

from .evaluate import CanvasIssue, resolve_canvas
from .geometry import canvas_placement
from .models import Canvas
from .raster import render_content, upscale

__all__ = ["CanvasLayer", "render_canvases", "render_canvases_on_grid"]


@dataclass(frozen=True)
class CanvasLayer:
    """A straight-alpha RGBA bitmap at panel pixel ``(x, y)``, ``w × h`` pixels, row-major.

    Painting rules (FiestaUI ``bitmap`` op, Fiestaboard/FiestaUI#343; the
    core LED renderer mirrors them): a pixel with alpha > 0 overwrites the RGB
    under it (no blending), alpha 0 is transparent, the layer is clipped to
    the matrix (rows never wrap), later layers paint over earlier ones. On a
    monochrome panel a pixel with alpha > 0 is lit iff
    ``299·r + 587·g + 114·b >= 127500`` (PIL ``L`` weights), else unlit.

    The JSON form (:meth:`to_json`) is FiestaUI's ``LedBitmapLayer``:
    ``{x, y, width, height, rgba}``, ``rgba`` base64 of row-major RGBA.
    """

    x: int
    y: int
    w: int
    h: int
    rgba: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.rgba) != self.w * self.h * 4:
            raise ValueError(
                f"CanvasLayer {self.w}x{self.h} needs {self.w * self.h * 4} rgba bytes "
                f"(4 bytes per pixel), got {len(self.rgba)}"
            )

    def to_json(self) -> dict[str, Any]:
        """``{x, y, width, height, rgba}`` with ``rgba`` standard base64 (FiestaUI ``LedBitmapLayer``)."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.w,
            "height": self.h,
            "rgba": base64.b64encode(self.rgba).decode("ascii"),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> CanvasLayer:
        """Inverse of :meth:`to_json`. Raises :class:`ValueError` on bad base64 or a size mismatch."""
        try:
            rgba = base64.b64decode(data["rgba"], validate=True)
        except (binascii.Error, TypeError) as exc:
            raise ValueError(f"CanvasLayer rgba is not valid base64: {exc}") from None
        return cls(x=int(data["x"]), y=int(data["y"]), w=int(data["width"]), h=int(data["height"]), rgba=rgba)


def render_canvases_on_grid(
    canvases: Iterable[Canvas] | None, grid: LedGridLayout, context: Mapping[str, Any]
) -> tuple[list[CanvasLayer], list[CanvasIssue]]:
    """Layers for *canvases* on an LED character *grid*; see :func:`render_canvases`."""
    layers: list[CanvasLayer] = []
    issues: list[CanvasIssue] = []
    for canvas in canvases or ():
        placement = canvas_placement(canvas, grid)
        if placement is None:
            issues.append(
                CanvasIssue(
                    canvas.id,
                    "area",
                    f"the area is outside this board's {grid.rows} x {grid.cols} grid "
                    f"or too small for scale {canvas.scale}; nothing drawn",
                )
            )
            continue
        resolved, canvas_issues = resolve_canvas(canvas, context)
        issues.extend(canvas_issues)
        pixels = render_content(resolved, placement.width, placement.height)
        rgba = upscale(pixels, placement.width, placement.height, placement.scale)
        layers.append(
            CanvasLayer(
                x=placement.x,
                y=placement.y,
                w=placement.width * placement.scale,
                h=placement.height * placement.scale,
                rgba=rgba,
            )
        )
    return layers, issues


def render_canvases(
    canvases: Iterable[Canvas] | None,
    model: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    font: str | None = None,
) -> tuple[list[CanvasLayer], list[CanvasIssue]]:
    """Rasterise a page's *canvases* for a board of FiestaUI device *model*.

    *font* is the board's chosen LED face (``"3x5"`` / ``"5x7"``; default the
    model's own), which sets the character grid the areas refer to.
    *context* is the page's template variable context. Returns
    ``(layers, issues)``; ``([], [])`` for a model that is not a pixel matrix.
    Never raises for bad canvas content: problems are issues.
    """
    if not canvases or not is_led_pixel_model(model):
        return [], []
    geometry = model["geometry"]
    grid = grid_layout(geometry["width"], geometry["height"], font or model.get("font") or DEFAULT_LED_FONT)
    return render_canvases_on_grid(canvases, grid, context)
