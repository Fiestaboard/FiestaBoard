"""A device model's content grid, and the floor every board must reach (plan D5).

A board's **content grid** is how many characters it shows — rows × cols —
and pages, previews and templates are authored against it. For a board an
output plugin drives, the grid comes from its FiestaUI device model's
``geometry`` (the vocabulary FiestaUI defines; plan D15):

- ``cells`` — the model's own ``rows`` × ``cols``;
- ``pixels`` — as many glyph cells as fit, with the glyph box of the model's
  LED font from FiestaUI's vendored ``led-fonts.json``:
  ``cols = (width + spacingX) // (glyphWidth + spacingX)`` and
  ``rows = (height + spacingY) // (glyphHeight + spacingY)`` — FiestaUI's
  ``ledGridLayout``. A Divoom Pixoo 64 with the 3x5 font is 10 × 16;
- ``panel`` — sized per board: the request's ``rows`` × ``cols``. A panel
  model may declare its own ``rows`` × ``cols`` (FiestaUI Task 7): that is
  its size when the board asks for none, and a board's own grid still wins;
- ``note_array`` — sized per board in Notes: ``notes_tall`` × 3 rows by
  ``notes_wide`` × 15 cols.

The font is the output's declared character set's font when it has one (the
declared set wins over the model's, plan D17), else the model's own ``font``,
else its character set's.

**The floor.** Every board shows at least one Note, 3 × 15: plugins and
templates are authored for that — except an LED board measured in pixels
(``pixels`` geometry), whose floor is 3 × 10 (``MIN_LED_GRID_*``) so a
legible 5x7 face fits: a Divoom Pixoo 64 at 5x7 is 8 × 10, a 64 × 32 HUB75
or Tidbyt 4 × 10. :func:`grid_floor` picks the model's floor. A model whose
grid is smaller is **refused** (:class:`BelowFloorError`) here, before
anything resolves the board's geometry — ``src.devices.clamp_grid`` (which
every ``panel`` grid passes through, LED boards included) would otherwise
quietly inflate a 1 × 8 matrix to 3 × 10 and every frame would be cropped on
the device. A grid above the panel ceiling (``MAX_GRID_ROWS`` ×
``MAX_GRID_COLS``) is refused the same way rather than shrunk.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from src.devices import (
    MAX_GRID_COLS,
    MAX_GRID_ROWS,
    MAX_NOTES_PER_AXIS,
    MIN_GRID_COLS,
    MIN_GRID_ROWS,
    MIN_LED_GRID_COLS,
    MIN_LED_GRID_ROWS,
    NOTE_COLS,
    NOTE_ROWS,
)
from src.fiestaui import builtin_character_sets, builtin_led_fonts
from src.led.charsets import materialize_character_set

#: Geometry kinds sized per board (the request supplies the size).
CONFIGURABLE_KINDS = frozenset({"panel", "note_array"})


class GeometryError(ValueError):
    """A board's requested geometry cannot be used for its device model."""


class BelowFloorError(GeometryError):
    """A device model's grid is smaller than its floor (3 × 15; 3 × 10 for an LED board in pixels)."""


class GlyphBox(NamedTuple):
    """One LED font's glyph size and the gap between glyphs, in pixels."""

    width: int
    height: int
    spacing_x: int
    spacing_y: int


def led_fonts() -> Mapping[str, Mapping[str, Any]]:
    """FiestaUI's LED fonts, by id (vendored; provenance in ``provenance.json``)."""
    return builtin_led_fonts()


def glyph_box(font_id: str) -> GlyphBox:
    """The glyph box of LED font *font_id*.

    Raises:
        GeometryError: FiestaUI defines no such font.
    """
    font = led_fonts().get(font_id)
    if font is None:
        raise GeometryError(f"Unknown LED font {font_id!r}")
    return GlyphBox(
        width=int(font["glyphWidth"]),
        height=int(font["glyphHeight"]),
        spacing_x=int(font.get("spacingX", 1)),
        spacing_y=int(font.get("spacingY", 1)),
    )


def _charset_font(charset_id: Any, declared: Mapping[str, Any] | None) -> str | None:
    """The font of a character set, following ``extends``; ``None`` when none."""
    sets = dict(builtin_character_sets())
    if declared is not None:
        sets[declared["id"]] = declared
    seen: set[str] = set()
    while isinstance(charset_id, str) and charset_id not in seen:
        seen.add(charset_id)
        charset = sets.get(charset_id)
        if charset is None:
            return None
        if isinstance(charset.get("font"), str):
            return charset["font"]
        charset_id = charset.get("extends")
    return None


def font_for(model: Mapping[str, Any], character_set: Mapping[str, Any] | None = None) -> str | None:
    """The LED font a board of *model* draws with.

    The output's declared character set's font wins (plan D17), then the
    model's own ``font``, then its character set's.
    """
    if character_set is not None:
        font = _charset_font(character_set.get("id"), character_set)
        if font is not None:
            return font
    if isinstance(model.get("font"), str):
        return model["font"]
    charset = model.get("charset")
    if isinstance(charset, Mapping):
        materialised = materialize_character_set(charset)
        return _charset_font(materialised["id"], materialised)
    return _charset_font(charset, None)


def model_cell_grid(model: Mapping[str, Any], character_set: Mapping[str, Any] | None = None) -> tuple[int, int] | None:
    """The (rows, cols) of characters a device model shows.

    ``None`` for a model sized per board (``panel``, ``note_array``), unless
    a ``panel`` declares its size.

    Raises:
        ValueError: a pixel model with no LED font to size it by.
    """
    geometry = model["geometry"]
    kind = geometry["kind"]
    if kind == "cells":
        return geometry["rows"], geometry["cols"]
    if kind == "panel":
        return _declared_panel(geometry)
    if kind != "pixels":
        return None
    font = font_for(model, character_set)
    if font is None:
        raise GeometryError(f"model {model['id']!r}: no LED font to size its pixels by")
    box = glyph_box(font)
    cols = (geometry["width"] + box.spacing_x) // (box.width + box.spacing_x)
    rows = (geometry["height"] + box.spacing_y) // (box.height + box.spacing_y)
    return rows, cols


def _declared_panel(geometry: Mapping[str, Any]) -> tuple[int, int] | None:
    """A panel model's own ``rows`` x ``cols``, when it declares both."""
    rows, cols = geometry.get("rows"), geometry.get("cols")
    if isinstance(rows, int) and isinstance(cols, int) and not isinstance(rows, bool) and not isinstance(cols, bool):
        return rows, cols
    return None


def _positive(requested: Mapping[str, Any], names: tuple[str, str], model_id: str, what: str) -> tuple[int, int]:
    values = [requested.get(name) for name in names]
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in values):
        raise GeometryError(f"Device model {model_id!r} is sized per board: give geometry {what}.")
    return values[0], values[1]


def _requested_grid(model: Mapping[str, Any], requested: Mapping[str, Any]) -> tuple[int, int]:
    kind = model["geometry"]["kind"]
    if kind == "panel":
        declared = _declared_panel(model["geometry"])
        if declared is not None and requested.get("rows") is None and requested.get("cols") is None:
            return declared
        return _positive(requested, ("rows", "cols"), model["id"], "rows and cols")
    wide, tall = _positive(requested, ("notes_wide", "notes_tall"), model["id"], "notes_wide and notes_tall")
    if wide > MAX_NOTES_PER_AXIS or tall > MAX_NOTES_PER_AXIS:
        raise GeometryError(f"A note array is at most {MAX_NOTES_PER_AXIS} Notes on each side.")
    return tall * NOTE_ROWS, wide * NOTE_COLS


def is_led_pixel_model(model: Mapping[str, Any]) -> bool:
    """Whether *model* is an LED board measured in pixels (``pixels`` geometry)."""
    return model["geometry"]["kind"] == "pixels"


def grid_floor(model: Mapping[str, Any]) -> tuple[int, int]:
    """The smallest (rows, cols) a board of *model* may show.

    3 × 10 for an LED board measured in pixels; the 3 × 15 Note for every
    other model (cells, panel, note array).
    """
    if is_led_pixel_model(model):
        return MIN_LED_GRID_ROWS, MIN_LED_GRID_COLS
    return MIN_GRID_ROWS, MIN_GRID_COLS


def check_floor(model: Mapping[str, Any], rows: int, cols: int) -> None:
    """Refuse a grid below *model*'s floor (:func:`grid_floor`) or above the panel ceiling."""
    min_rows, min_cols = grid_floor(model)
    if rows < min_rows or cols < min_cols:
        what = "an LED board" if is_led_pixel_model(model) else "a board"
        raise BelowFloorError(
            f"Device model {model['id']!r} shows {rows}x{cols} characters, below the {min_rows}x{min_cols} "
            f"minimum {what} needs, so FiestaBoard cannot create a board for it."
        )
    if rows > MAX_GRID_ROWS or cols > MAX_GRID_COLS:
        raise GeometryError(
            f"A {rows}x{cols} grid is larger than the {MAX_GRID_ROWS}x{MAX_GRID_COLS} maximum a board can show."
        )


def resolve_content_grid(
    model: Mapping[str, Any],
    character_set: Mapping[str, Any] | None,
    requested: Mapping[str, Any] | None,
) -> tuple[int, int]:
    """The (rows, cols) a new board of *model* shows, floor checked.

    *requested* is the board's geometry, accepted only for a model sized per
    board (``panel``, ``note_array``) and required for one — except a
    ``panel`` that declares its own size, which is used when none is asked.

    Raises:
        BelowFloorError: the grid is below the model's floor (3 × 15; 3 × 10 for an LED board in pixels).
        GeometryError: geometry missing, unexpected, or above the ceiling.
    """
    configurable = model["geometry"]["kind"] in CONFIGURABLE_KINDS
    if configurable:
        rows, cols = _requested_grid(model, requested or {})
    else:
        if requested:
            raise GeometryError(f"Device model {model['id']!r} has a fixed size; geometry is not accepted for it.")
        grid = model_cell_grid(model, character_set)
        assert grid is not None  # cells and pixels always have one
        rows, cols = grid
    check_floor(model, rows, cols)
    return rows, cols
