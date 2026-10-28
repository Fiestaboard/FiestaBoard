"""Bitmap faces for LED matrices, loaded from FiestaUI's published font data.

``led-fonts.json`` is FiestaUI's ``LED_FONTS`` (``src/lib/led-fonts.ts``)
exported as data and vendored verbatim in :mod:`src.fiestaui`. A
glyph is a list of rows, top to bottom, each ``glyph_width`` characters of
``#`` (lit) or ``.`` (off).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from src.fiestaui import builtin_led_fonts

__all__ = ["LED_FONTS", "LedFont"]


@dataclass(frozen=True)
class LedFont:
    """One face: its glyph box, the gutters between boxes, and its bitmaps."""

    id: str
    glyph_width: int
    glyph_height: int
    #: Blank pixels between adjacent glyphs.
    spacing_x: int
    #: Blank pixels between text rows.
    spacing_y: int
    #: Character -> rows. Covers the flap set, ``♥``, ``°`` and a-z.
    glyphs: Mapping[str, Sequence[str]]
    #: Icon name -> rows. A face may lack an icon; it then draws the fallback.
    icons: Mapping[str, Sequence[str]]


def _load() -> Mapping[str, LedFont]:
    raw = builtin_led_fonts()
    return MappingProxyType(
        {
            font_id: LedFont(
                id=font_id,
                glyph_width=face["glyphWidth"],
                glyph_height=face["glyphHeight"],
                spacing_x=face["spacingX"],
                spacing_y=face["spacingY"],
                glyphs=MappingProxyType({c: tuple(rows) for c, rows in face["glyphs"].items()}),
                icons=MappingProxyType({n: tuple(rows) for n, rows in face["icons"].items()}),
            )
            for font_id, face in raw.items()
        }
    )


#: Font id (``"3x5"``, ``"5x7"``) -> face.
LED_FONTS: Mapping[str, LedFont] = _load()
