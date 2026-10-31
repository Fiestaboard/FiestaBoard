"""A grid page drawn at its own text size, as one full-frame pixel layer.

An LED board produces one grid per text size (face) it allows: a Pixoo 64
gives 10 x 16 in ``"3x5"`` and 8 x 10 in ``"5x7"``. A grid page whose grid
the board reaches only at another face is drawn here at that face, exactly
as an LED output plugin draws core's cells (:func:`render_grid_page_frame`),
and sent as one opaque layer covering the whole matrix (:func:`full_frame_layer`).
The cells under it carry the page text projected to the board's own grid, so
board state, ``matches_frame`` and transitions always compare same-shaped
cells. Every rich-charset output paints ``RichCells.layers`` last, so no
output plugin changes (design sections 6 and 7).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from src.canvas.layer import CanvasLayer
from src.outputs.cells import frame_layers, project_message

from .charsets import BUILTIN_CHARACTER_SETS
from .matrix import LedFrame, LedLayoutOptions, LedMatrixSpec, layout_message, led_charset_for_font, rasterize

if TYPE_CHECKING:
    from src.outputs.display_profile import DisplayProfile

__all__ = [
    "carries_full_frame",
    "full_frame_layer",
    "is_full_frame_layer",
    "render_grid_page_frame",
    "send_layers",
]


def render_grid_page_frame(
    formatted: str,
    rows: int,
    cols: int,
    face: str,
    display: DisplayProfile,
    layers: Sequence[CanvasLayer] = (),
) -> LedFrame:
    """*formatted* (a ``rows`` x ``cols`` page) drawn in *face* on *display*'s matrix.

    The page's text is projected with the face's built-in character set (the
    same fallbacks a plugin receives), laid out on the board's pixel surface
    with its tile style, block padding and monochrome colour, and the page's
    canvas *layers* (rendered on the face's grid) are painted over it.
    Raises :class:`ValueError` when *face* on this display does not produce
    a ``rows`` x ``cols`` grid.
    """
    charset = BUILTIN_CHARACTER_SETS[led_charset_for_font(face)]
    cells = project_message(formatted, rows, cols, charset).cells
    spec = LedMatrixSpec(
        display.width, display.height, face, tile_gap=display.tile_gap, block_padding=display.block_padding
    )
    options = LedLayoutOptions(
        monochrome=display.monochrome,
        charset=charset,
        tile_gap=display.tile_gap,
        block_padding=display.block_padding,
    )
    layout = layout_message(cells, spec, options, layers=layers)
    if (layout.grid.rows, layout.grid.cols) != (rows, cols):
        raise ValueError(f"{face} draws {layout.grid.rows}x{layout.grid.cols} on this display, not {rows}x{cols}")
    return rasterize(layout)


def full_frame_layer(frame: LedFrame, *, monochrome: str | None = None) -> CanvasLayer:
    """An opaque transport layer over the matrix, black included.

    A rendered monochrome frame already contains only unlit and panel-colored
    pixels. Encode its lit pixels as white so the receiving compositor's
    normal luminance conversion applies the panel color exactly once. This
    keeps the existing Canvas layer protocol and its threshold unchanged.
    """
    rgb = frame.pixels
    if monochrome:
        rgb = b"".join(b"\xff\xff\xff" if any(rgb[i : i + 3]) else b"\0\0\0" for i in range(0, len(rgb), 3))
    rgba = bytearray(frame.width * frame.height * 4)
    rgba[0::4] = rgb[0::3]
    rgba[1::4] = rgb[1::3]
    rgba[2::4] = rgb[2::3]
    rgba[3::4] = b"\xff" * (frame.width * frame.height)
    return CanvasLayer(x=0, y=0, w=frame.width, h=frame.height, rgba=bytes(rgba))


def is_full_frame_layer(layer: object, width: int, height: int) -> bool:
    """Whether *layer* covers a ``width`` x ``height`` matrix from (0, 0) with every pixel opaque."""
    if not isinstance(layer, CanvasLayer):
        return False
    if (layer.x, layer.y, layer.w, layer.h) != (0, 0, width, height):
        return False
    alpha = layer.rgba[3::4]
    return alpha.count(255) == len(alpha)


def carries_full_frame(cells: object, model: Mapping | None) -> bool:
    """Whether a frame for a board of device *model* carries a full-frame layer.

    Only a pixel-matrix model (``geometry.kind == "pixels"``) can; anything
    else, or no model, is ``False``.
    """
    geometry = model.get("geometry") if isinstance(model, Mapping) else None
    if not isinstance(geometry, Mapping) or geometry.get("kind") != "pixels":
        return False
    width, height = int(geometry["width"]), int(geometry["height"])
    return any(is_full_frame_layer(layer, width, height) for layer in frame_layers(cells))


def send_layers(result: Any, rows: int, cols: int, display: DisplayProfile | None) -> list[CanvasLayer]:
    """The layers to send with a rendered page.

    A result rendered at a face (``result.face`` set; *rows* x *cols* is the
    page's grid) on a pixel board becomes one full-frame layer, its canvas
    layers drawn into it. Any other result's own layers pass through unchanged.
    """
    face = getattr(result, "face", None)
    own = list(getattr(result, "layers", None) or ())
    if not face or display is None or not display.supports("pixels"):
        return own
    frame = render_grid_page_frame(result.formatted, rows, cols, face, display, own)
    return [full_frame_layer(frame, monochrome=display.monochrome)]
