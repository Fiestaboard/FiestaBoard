"""The board a flexible page is laid out for: its grid, its display and its board style."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from src.devices import dimensions_of
from src.led.matrix import DEFAULT_LED_TEXT_COLOR, LED_MONO_COLORS, resolve_hex_option
from src.outputs.display_profile import DisplayProfile

from .style import board_style_for

__all__ = ["DEFAULT_FACE_ID", "FLAGSHIP_GRID", "FlexTarget", "flex_target_for"]

#: The grid a board with no known size is laid out at (the flagship's).
FLAGSHIP_GRID = (6, 22)

#: The face a pixel display draws text in when it names none (the LED grid default).
DEFAULT_FACE_ID = "5x7"

ColorModel = Literal["rgb", "mono", "tiles"]


@dataclass(frozen=True)
class FlexTarget:
    """One board as layout sees it.

    ``rows`` and ``cols`` are the board's current character grid; ``display``
    is what it can draw (``None``: the split-flap baseline); ``board_style``
    is the board's own style level in the cascade (empty in Phase 1).
    """

    rows: int
    cols: int
    display: DisplayProfile | None
    board_style: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def pixels(self) -> bool:
        """The board is a pixel matrix: layout draws a full-frame image for it."""
        return self.display is not None and self.display.supports("pixels")

    @property
    def width(self) -> int | None:
        """The surface width in pixels; ``None`` on a cell (character-grid) target."""
        return self.display.width if self.pixels and self.display is not None else None

    @property
    def height(self) -> int | None:
        """The surface height in pixels; ``None`` on a cell (character-grid) target."""
        return self.display.height if self.pixels and self.display is not None else None

    @property
    def mixed_case(self) -> bool:
        """Lowercase draws as lowercase."""
        return self.display is not None and self.display.mixed_case

    @property
    def color_model(self) -> ColorModel:
        """How colour is shown: any colour (``rgb``), lit or unlit (``mono``) or flap tiles.

        A cell target is always ``tiles``: its text is an ordinary 0-71 grid.
        """
        if not self.pixels or self.display is None:
            return "tiles"
        return "rgb" if self.display.color == "rgb" else ("mono" if self.display.color == "mono" else "tiles")

    @property
    def monochrome(self) -> str | None:
        """A monochrome panel's lit colour as lowercase ``#rrggbb``; ``None`` on any other board."""
        if self.color_model != "mono" or self.display is None:
            return None
        declared = self.display.monochrome
        if declared is not None and declared.strip().lower() in LED_MONO_COLORS:
            declared = LED_MONO_COLORS[declared.strip().lower()]
        return resolve_hex_option(declared, DEFAULT_LED_TEXT_COLOR)

    @property
    def default_face_id(self) -> str | None:
        """The face the board draws grid pages in (its ``medium`` size); ``None`` on a cell target."""
        if not self.pixels or self.display is None:
            return None
        return self.display.font or DEFAULT_FACE_ID


def _board_grid(board: Mapping[str, Any] | None) -> tuple[int, int] | None:
    if board is None:
        return None
    try:
        dims = dimensions_of(board)
    except (ValueError, TypeError):
        return None
    return dims.rows, dims.cols


def flex_target_for(board: Mapping[str, Any] | None, display: DisplayProfile | None) -> FlexTarget:
    """The :class:`FlexTarget` for ``board`` drawn on ``display``.

    The grid is the display's when it knows one, else the board's
    (:func:`src.devices.dimensions_of`), else the flagship's 6 x 22.
    """
    if display is not None and display.rows and display.cols:
        rows, cols = display.rows, display.cols
    else:
        rows, cols = _board_grid(board) or FLAGSHIP_GRID
    return FlexTarget(rows=rows, cols=cols, display=display, board_style=board_style_for(board))
