"""The font registry: families of faces, and the sizes a family can draw.

A **family** is a set of **faces** at given pixel heights; a page asks for a
family and a size, never a face. v1 has one family, ``fiesta``: a thin mapping
over the two faces core already vendors (``3x5``, 5 px tall, and ``5x7``, 7 px
tall), built from :data:`src.led.fonts.LED_FONTS` so the vendored files and
their hashes are untouched. New faces and families are data additions.

Larger text comes from **integer scaling** of the bitmap faces
(:func:`size_ladder`): every height a family can draw is some face at some
scale 1..:data:`MAX_TEXT_SCALE`. A face has a ``kind`` (``bitmap`` now,
``outline`` reserved); the ladder only scales bitmap faces.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from src.led.fonts import LED_FONTS, LedFont

__all__ = [
    "DEFAULT_FONT_FAMILY",
    "FONT_FAMILIES",
    "MAX_TEXT_SCALE",
    "NAMED_SIZES",
    "FontFace",
    "FontFamily",
    "SizedFace",
    "face_for_height",
    "face_for_led_font",
    "named_size_heights",
    "size_ladder",
]

#: The largest integer scale a bitmap face is drawn at.
MAX_TEXT_SCALE = 8

#: The family a style falls back to.
DEFAULT_FONT_FAMILY = "fiesta"

#: The named sizes, smallest first (``fit`` and exact pixel heights are not named sizes).
NAMED_SIZES = ("small", "medium", "large", "xlarge")


@dataclass(frozen=True)
class FontFace:
    """One face: its vendored id, kind, glyph box and the LED face that draws it."""

    id: str
    kind: Literal["bitmap", "outline"]
    pixel_height: int
    glyph_width: int
    spacing_x: int
    spacing_y: int
    led_font: LedFont


@dataclass(frozen=True)
class FontFamily:
    """A named set of faces, ascending by pixel height."""

    id: str
    name: str
    faces: tuple[FontFace, ...]


@dataclass(frozen=True)
class SizedFace:
    """A face drawn at an integer scale; its metrics are the face's times ``scale``."""

    face: FontFace
    scale: int

    @property
    def height(self) -> int:
        return self.face.pixel_height * self.scale

    @property
    def advance(self) -> int:
        """Pixels from one glyph's left edge to the next's (glyph plus gutter)."""
        return (self.face.glyph_width + self.face.spacing_x) * self.scale

    @property
    def gutter(self) -> int:
        return self.face.spacing_x * self.scale

    @property
    def line_gap(self) -> int:
        return self.face.spacing_y * self.scale


def _bitmap_face(led_font: LedFont) -> FontFace:
    return FontFace(
        id=led_font.id,
        kind="bitmap",
        pixel_height=led_font.glyph_height,
        glyph_width=led_font.glyph_width,
        spacing_x=led_font.spacing_x,
        spacing_y=led_font.spacing_y,
        led_font=led_font,
    )


def _family(family_id: str, name: str, face_ids: tuple[str, ...]) -> FontFamily:
    faces = sorted((_bitmap_face(LED_FONTS[fid]) for fid in face_ids), key=lambda f: f.pixel_height)
    return FontFamily(id=family_id, name=name, faces=tuple(faces))


#: Family id -> family.
FONT_FAMILIES: Mapping[str, FontFamily] = MappingProxyType(
    {DEFAULT_FONT_FAMILY: _family(DEFAULT_FONT_FAMILY, "Fiesta", ("3x5", "5x7"))}
)

_FACES_BY_ID: Mapping[str, FontFace] = MappingProxyType(
    {face.id: face for family in FONT_FAMILIES.values() for face in family.faces}
)

#: Family id -> (the family it was built for, its ladder). Keyed by id and
#: checked by identity: a family holds mappings, so it is not hashable.
_LADDERS: dict[str, tuple[FontFamily, tuple[SizedFace, ...]]] = {}


def size_ladder(family: FontFamily) -> tuple[SizedFace, ...]:
    """Every height ``family`` can draw: its bitmap faces at scales 1..:data:`MAX_TEXT_SCALE`.

    One entry per height, sorted by height. On a tie the larger face at the
    smaller scale wins (35 px is ``5x7`` ×5, not ``3x5`` ×7): fewer, finer
    source pixels per glyph.
    """
    cached = _LADDERS.get(family.id)
    if cached is not None and cached[0] is family:
        return cached[1]
    best: dict[int, SizedFace] = {}
    for face in family.faces:
        if face.kind != "bitmap":
            continue
        for scale in range(1, MAX_TEXT_SCALE + 1):
            sized = SizedFace(face, scale)
            held = best.get(sized.height)
            if held is None or sized.scale < held.scale:
                best[sized.height] = sized
    ladder = tuple(best[h] for h in sorted(best))
    _LADDERS[family.id] = (family, ladder)
    return ladder


def face_for_height(family: FontFamily, px: int) -> tuple[SizedFace, bool]:
    """The largest ladder entry no taller than ``px``, and whether it is exactly ``px``.

    Below the smallest entry this is ``(smallest, False)``: the caller reports
    that even the smallest face is too big.
    """
    ladder = size_ladder(family)
    chosen = ladder[0]
    for sized in ladder:
        if sized.height > px:
            break
        chosen = sized
    return chosen, chosen.height == px


def face_for_led_font(font_id: str) -> FontFace:
    """The registry face for a vendored LED font id (``"3x5"``, ``"5x7"``); ``KeyError`` if none."""
    try:
        return _FACES_BY_ID[font_id]
    except KeyError:
        raise KeyError(f"no font face {font_id!r}") from None


def _ladder_floor(heights: tuple[int, ...], px: int) -> int:
    """The largest ladder height ≤ ``px``; the smallest height when none is."""
    chosen = heights[0]
    for h in heights:
        if h > px:
            break
        chosen = h
    return chosen


def _ladder_next(heights: tuple[int, ...], px: int) -> int | None:
    """The smallest ladder height above ``px``, or ``None`` at the top of the ladder."""
    return next((h for h in heights if h > px), None)


def named_size_heights(*, surface_height: int, default_height: int, family: FontFamily) -> dict[str, int]:
    """The pixel height each named size maps to on a surface ``surface_height`` px tall.

    - ``small``: the family's smallest height.
    - ``medium``: the board's default face height (``default_height``).
    - ``large``: the larger of the ladder height at or under a quarter of the
      surface and the step above ``medium``; ``medium`` if that is taller than
      the surface.
    - ``xlarge``: the same at half the surface, above ``large``; ``large`` if
      that is taller than the surface.
    """
    heights = tuple(s.height for s in size_ladder(family))
    small = heights[0]
    medium = default_height

    def step(fraction_px: int, below: int) -> int:
        nxt = _ladder_next(heights, below)
        candidate = max(_ladder_floor(heights, fraction_px), nxt if nxt is not None else surface_height + 1)
        return below if candidate > surface_height else candidate

    large = step(surface_height // 4, medium)
    xlarge = step(surface_height // 2, large)
    return {"small": small, "medium": medium, "large": large, "xlarge": xlarge}
