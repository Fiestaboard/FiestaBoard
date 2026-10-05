"""Bitmap faces for LED matrices, loaded from FiestaUI's published font data.

``led-fonts.json`` is FiestaUI's ``LED_FONTS`` (``src/lib/led-fonts.ts``)
exported as data and vendored verbatim (see :mod:`src.led.provenance`). A
glyph is a list of rows, top to bottom, each ``glyph_width`` characters of
``#`` (lit) or ``.`` (off).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

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
    raw = json.loads(Path(__file__).with_name("led-fonts.json").read_text(encoding="utf-8"))
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
