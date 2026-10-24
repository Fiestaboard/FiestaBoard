"""Resolve TV content once: physical flaps, or pixels with a derived text grid."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from src.devices import DeviceDimensions, dimensions_of
from src.fiestaui import fiestapanel_model
from src.led.matrix import MAX_MATRIX_SIZE, grid_layout

from .autofit import compute_autofit_grid
from .models import Panel

SCREEN_PIXEL_EDGE = 192


class PanelGeometryError(ValueError):
    """A TV layout cannot be represented by the supported renderers."""


@dataclass(frozen=True)
class PanelGeometry:
    rows: int
    cols: int
    width: int | None
    height: int | None
    font: str | None
    model: dict[str, Any]

    @property
    def grid(self) -> DeviceDimensions:
        return DeviceDimensions(self.rows, self.cols)

    @property
    def key(self) -> str:
        return f"{self.model['technology']}:{self.cols}x{self.rows}:{self.width}x{self.height}:{self.font}"

    @property
    def error(self) -> str | None:
        if self.width and self.height and max(self.width, self.height) > MAX_MATRIX_SIZE:
            return "This legacy LED grid exceeds the supported 256-pixel surface. Choose Fit screen shape in panel settings."
        return None


def resolve_panel_geometry(panel: Panel, board: dict | None = None) -> PanelGeometry:
    """The content geometry of saved or proposed panel settings.

    Legacy LED pages retain their stored cell coordinates; screen LED pages
    derive every cell from a bounded, aspect-matched virtual pixel surface.
    Inches, calibration and physical LED pitch affect presentation only.
    """
    if panel.render_style == "led_matrix" and panel.matrix_layout == "screen":
        aspect = (Fraction(str(panel.screen_aspect_w)) / Fraction(str(panel.screen_aspect_h))).limit_denominator(64)
        unit_w, unit_h = aspect.numerator, aspect.denominator
        scale = max(1, SCREEN_PIXEL_EDGE // max(unit_w, unit_h))
        width, height = unit_w * scale, unit_h * scale
        if max(width, height) > MAX_MATRIX_SIZE:
            raise PanelGeometryError(
                "This screen shape cannot fit the supported LED surface. Choose a standard aspect ratio."
            )
        font = panel.matrix_font
        grid = grid_layout(width, height, font)
        # FiestaPanel's pull output supports at least one Note's cell grid.
        if grid.rows < 3 or grid.cols < 15:
            raise PanelGeometryError(
                "This screen shape is too narrow for the LED text size. Use Small text or a wider aspect ratio."
            )
        model = fiestapanel_model("led_matrix")
        model.update(geometry={"kind": "pixels", "width": width, "height": height}, font=font, charset=f"led_{font}")
        return PanelGeometry(grid.rows, grid.cols, width, height, font, model)

    grid = (
        dimensions_of(board)
        if panel.render_style == "led_matrix" and board is not None
        else compute_autofit_grid(panel.screen_diagonal_inches, panel.screen_aspect_w, panel.screen_aspect_h)
    )
    model = fiestapanel_model(panel.render_style, grid.rows, grid.cols)
    if panel.render_style == "split_flap":
        model["geometry"] = {"kind": "panel", "rows": grid.rows, "cols": grid.cols}
        return PanelGeometry(grid.rows, grid.cols, None, None, None, model)
    geometry = model["geometry"]
    return PanelGeometry(grid.rows, grid.cols, geometry["width"], geometry["height"], "5x7", model)
