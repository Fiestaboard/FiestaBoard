"""API shapes for canvas output: a rasterised layer and a drawing issue.

``CanvasLayerModel`` is FiestaUI's ``LedBitmapLayer`` JSON
(:meth:`src.canvas.layer.CanvasLayer.to_json`); ``CanvasIssueModel`` is
:meth:`src.canvas.evaluate.CanvasIssue.to_json`. Responses for a
pixel-matrix board carry them (page previews, page sends, what a board
shows); every other board's responses leave them out.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["CanvasIssueModel", "CanvasLayerModel", "issues_json", "layers_json"]


class CanvasLayerModel(BaseModel):
    """One canvas drawn in panel pixels (FiestaUI ``LedBitmapLayer``)."""

    x: int = Field(description="Panel x of the layer's left column.")
    y: int = Field(description="Panel y of the layer's top row.")
    width: int = Field(description="Pixels across.")
    height: int = Field(description="Pixels down.")
    rgba: str = Field(
        description="Base64 of width x height x 4 bytes of straight-alpha RGBA, row-major. A pixel with alpha > 0 "
        "overwrites what the cells drew; alpha 0 is transparent."
    )


class CanvasIssueModel(BaseModel):
    """A problem met drawing a canvas; the canvas still draws (with its stored content, or empty)."""

    canvas_id: str
    path: str = Field(description="Where: ``source``, ``area``, ``background``, ``shapes[3].x``, …")
    message: str


def layers_json(layers: Iterable[Any]) -> list[dict[str, Any]]:
    """``CanvasLayer``s as their JSON form."""
    return [layer.to_json() for layer in layers]


def issues_json(issues: Iterable[Any]) -> list[dict[str, str]]:
    """``CanvasIssue``s as their JSON form."""
    return [issue.to_json() for issue in issues]
