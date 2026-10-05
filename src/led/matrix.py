"""LED matrix layout and raster: a board message to the RGB888 bytes a panel shows.

A port of FiestaUI's ``src/lib/led-matrix.ts`` (45496c9), the reference
implementation (plan D15): :func:`grid_layout` is ``ledGridLayout``,
:func:`layout_message` is ``layoutLedMessage``, :func:`rasterize` is
``rasterizeLedLayout``, :func:`frame_to_bits` is ``frameToBits``. The golden
fixtures in ``tests/fixtures/fiestaui/`` hold it to FiestaUI's bytes.

A matrix lays a character grid onto its pixels from a bitmap face
(:mod:`src.led.fonts`) and draws each cell into a row-major RGB888 frame.
Parsing is :func:`src.markup.parse_line` with extended markup, the same
grammar the split-flap board reads, so tokens keep their identity: ``°`` is a
degree sign and ``♥`` / ``❤`` / ``{icon:heart}`` the red heart (there is no
code-62 flap on an LED). What an LED does with a token:

- **Text** draws in the layout's text colour, or its colour span's colour
  (an "off" span colour, black, draws unlit letters).
- **Block spans** (``{black/white:OPEN}``) light the glyph box behind the
  glyph; the gutter to a neighbour in the *same* block lights too.
- **Colour tiles** fill the glyph box, not the gutter; black / filled are
  unlit (black means off on an emissive panel).
- **Icons** draw in their own colour; a face without the icon draws the
  icon's split-flap fallback.
- **Monochrome** panels draw every lit pixel in the panel colour; a block
  span there is inverse video.

The layout does not project a message onto a character set: that is the
caller's job (core, per output, with ``charsetFallback``). A set passed in
:class:`LedLayoutOptions` contributes only its custom glyph bitmaps.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

from src.markup import BOARD_ICONS, BoardToken, parse_line

from .charsets import CharacterSet
from .fonts import LED_FONTS, LedFont

__all__ = [
    "BOARD_COLORS",
    "DEFAULT_LED_BLOCK_PADDING",
    "DEFAULT_LED_TEXT_COLOR",
    "DEFAULT_LED_TILE_GAP",
    "LED_BLOCK_PADDINGS",
    "LED_GLYPHS",
    "LED_MONO_COLORS",
    "LED_TILE_GAPS",
    "MAX_MATRIX_SIZE",
    "MIN_MATRIX_SIZE",
    "GutterPixel",
    "LedBlockPadding",
    "LedCell",
    "LedDrawOp",
    "LedFrame",
    "LedGridLayout",
    "LedLayout",
    "LedLayoutChoice",
    "LedLayoutOptions",
    "LedMatrixSpec",
    "LedRenderOptions",
    "LedTileGap",
    "draw_glyph",
    "frame_to_ascii",
    "frame_to_bits",
    "glyph_key",
    "grid_layout",
    "gutter_pixels",
    "is_led_block_padding",
    "is_led_tile_gap",
    "layout_cells",
    "layout_message",
    "layout_policy_for_model",
    "led_layout_options_for_model",
    "led_spec_for_model",
    "paint_ops",
    "parse_hex_color",
    "rasterize",
    "resolve_hex_option",
]

#: Matrix size bounds. 256 covers a chain of four 64-wide HUB75 panels.
MIN_MATRIX_SIZE = 1
MAX_MATRIX_SIZE = 256

#: The board palette (FiestaUI ``BOARD_COLORS``, ``src/lib/board-colors.ts``).
BOARD_COLORS: Mapping[str, str] = {
    "red": "#eb4034",
    "orange": "#f5a623",
    "yellow": "#f8e71c",
    "green": "#7ed321",
    "blue": "#4a90d9",
    "violet": "#9b59b6",
    "white": "#ffffff",
    "black": "#1a1a1a",
}
_COLOR_CODE_MAP = {
    "63": BOARD_COLORS["red"],
    "64": BOARD_COLORS["orange"],
    "65": BOARD_COLORS["yellow"],
    "66": BOARD_COLORS["green"],
    "67": BOARD_COLORS["blue"],
    "68": BOARD_COLORS["violet"],
    "69": BOARD_COLORS["white"],
    "70": BOARD_COLORS["black"],
    "71": BOARD_COLORS["black"],
}
_ALL_COLOR_CODES = {
    **_COLOR_CODE_MAP,
    **BOARD_COLORS,
    "purple": BOARD_COLORS["violet"],
    "filled": _COLOR_CODE_MAP["71"],
}
#: Tile colours that are unlit pixels on an emissive panel.
_OFF_TILE_CODES = frozenset({"70", "71", "black"})
#: A tile's glyph is keyed by its colour, so ``{red}`` and ``{63}`` share one.
_TILE_CODE_BY_HEX: dict[str, str] = {}
for _code, _hex in _COLOR_CODE_MAP.items():
    _TILE_CODE_BY_HEX.setdefault(_hex, _code)

#: Named colours for single-colour panels (FiestaUI ``LED_MONO_COLORS``).
LED_MONO_COLORS: Mapping[str, str] = {
    "red": "#ff3b1f",
    "amber": "#ffb000",
    "green": "#3bff5a",
    "blue": "#3b8bff",
    "white": "#ffffff",
}

#: Pure white: what a device is sent by default.
DEFAULT_LED_TEXT_COLOR = "#ffffff"

#: Every glyph the built-in faces can show, as stable glyph keys (FiestaUI
#: ``LED_GLYPHS``): a frozen membership table, never added to. A cell's
#: ``glyph`` is its key, the same in every process: ``" "`` (blank), the
#: character itself, ``tile:<numeric code>`` (``{red}`` and ``{63}`` are
#: ``tile:63``; ``{black}``, ``{70}``, ``{71}`` and ``{filled}`` are
#: ``tile:70``) or ``icon:<canonical name>`` (aliases resolved). A character
#: beyond it resolves only through the layout's own set (``glyphs``).
LED_GLYPHS: tuple[str, ...] = (
    " ",
    *"ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    *"0123456789",
    *"!@#$()-+&=;:'\"%,./?°",
    *"abcdefghijklmnopqrstuvwxyz",
    "♥",
    *(f"tile:{code}" for code in range(63, 72)),
    *(f"icon:{name}" for name in BOARD_ICONS),
)
_GLYPHS = frozenset(LED_GLYPHS)
_BLANK = " "
_BLANK_TOKEN = BoardToken("char", value=" ")

# JavaScript's \s (and String.prototype.trim), which the reference uses: not
# Python's, which differs on U+001C-U+001F, U+0085 and U+FEFF.
_JS_SPACE = "\t\n\v\f\r    -     　﻿"
_JS_SPACES = re.compile(f"[{_JS_SPACE}]+")
_JS_TRIM = re.compile(f"^[{_JS_SPACE}]+|[{_JS_SPACE}]+$")
_HEX = re.compile(r"#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})")
_HEX_OPTION = re.compile(r"#?([0-9a-fA-F]{6})")


#: What the 1-px gutter between two adjacent cells that are lit fields of one
#: colour does: ``"gap"`` keeps it unlit (a run of tiles reads as cells),
#: ``"fill"`` lights it (the run reads as one solid field). FiestaUI ``LedTileGap``.
LedTileGap = Literal["gap", "fill"]
#: Whether a block span's field extends one pixel past its cells' glyph boxes.
LedBlockPadding = Literal[0, 1]

LED_TILE_GAPS: tuple[str, ...] = ("gap", "fill")
LED_BLOCK_PADDINGS: tuple[int, ...] = (0, 1)
#: The renderer's own defaults: what every layout drew before the options existed.
DEFAULT_LED_TILE_GAP = "gap"
DEFAULT_LED_BLOCK_PADDING = 0


def is_led_tile_gap(value: object) -> bool:
    """``"gap"`` or ``"fill"``, exactly."""
    return isinstance(value, str) and value in LED_TILE_GAPS


def is_led_block_padding(value: object) -> bool:
    """``0`` or ``1``, exactly: an int, never a bool or a string (JS ``v === 0 || v === 1``)."""
    return type(value) is int and value in LED_BLOCK_PADDINGS


@dataclass(frozen=True)
class LedMatrixSpec:
    """A matrix: pixels across and down, the face text is set in, and the
    panel's defaults for the byte-changing layout options (a device model's
    choice, :func:`led_spec_for_model`); an explicit layout option wins."""

    width: int
    height: int
    font: str = "5x7"
    #: The panel's default :attr:`LedLayoutOptions.tile_gap`; unset is ``"gap"``.
    tile_gap: str | None = None
    #: The panel's default :attr:`LedLayoutOptions.block_padding`; unset is ``0``.
    block_padding: int | None = None


@dataclass(frozen=True)
class LedLayoutOptions:
    """How a message is drawn (FiestaUI ``LedLayoutOptions``)."""

    #: ``#rrggbb`` for text. Unparseable -> :data:`DEFAULT_LED_TEXT_COLOR`.
    text_color: str | None = None
    #: A single-colour panel's ``#rrggbb``: every lit pixel becomes it, and
    #: ``text_color`` is ignored. Unparseable -> unset.
    monochrome: str | None = None
    #: ``"upper"`` uppercases like the flap board; ``"mixed"`` keeps case.
    #: Applies only when a markup string is laid out (tokens are already parsed).
    letter_case: Literal["upper", "mixed"] = "upper"
    #: A materialised character set; only its ``glyphs`` are used here.
    charset: CharacterSet | None = None
    #: ``"gap"`` (default) keeps the 1-px gutter between adjacent cells
    #: unlit; ``"fill"`` lights the gutter between two cells that are lit
    #: fields of the **same** colour (two colour tiles, two block cells, a
    #: tile beside a block), a corner only when all four cells are. Changes
    #: device bytes. Anything else is unset: the spec's default, then ``"gap"``.
    tile_gap: str | None = None
    #: ``1`` extends every block span's field one pixel past its glyph boxes,
    #: into the gutters and margin (never past the matrix, never into another
    #: cell's glyph box; a pixel a field of another colour borders stays
    #: unlit). ``0`` (default) draws the field over the glyph boxes only.
    #: Anything else is unset: the spec's default, then ``0``.
    block_padding: int | None = None


@dataclass(frozen=True)
class LedRenderOptions:
    """The resolved options a layout's cells need to be drawn again."""

    monochrome: str | None = None
    glyphs: Mapping[str, Sequence[str]] | None = None
    #: The set the layout was drawn with, when one was given: the pool a
    #: flip's scramble draws from (:mod:`src.led.transitions`).
    charset: CharacterSet | None = None
    #: Resolved :attr:`LedLayoutOptions.tile_gap`, carried so a transition's
    #: mid-way layouts draw their fields exactly as the settled ones do.
    tile_gap: str = DEFAULT_LED_TILE_GAP
    #: Resolved :attr:`LedLayoutOptions.block_padding`, carried likewise.
    block_padding: int = DEFAULT_LED_BLOCK_PADDING


@dataclass(frozen=True)
class LedGridLayout:
    """The character grid a matrix and face give, and where it starts."""

    width: int
    height: int
    font: str
    rows: int
    cols: int
    #: Pixel x of the first glyph; leftover pixels are split as a margin.
    origin_x: int
    origin_y: int


@dataclass(frozen=True)
class LedCell:
    """One cell: the glyph it shows and the colours it draws in."""

    #: A key of :data:`LED_GLYPHS`, or a character set's own glyph.
    glyph: str
    #: ``#rrggbb`` the cell's text draws in. Tiles and icons bring their own
    #: colour unless the panel is monochrome.
    color: str
    #: ``#rrggbb`` the cell's block-span background lights in; ``None`` is unlit.
    background: str | None = None


@dataclass(frozen=True)
class LedDrawOp:
    """A bitmap glyph (``rows``) or a solid rectangle (``w`` x ``h``), in matrix pixels."""

    kind: Literal["glyph", "rect"]
    x: int
    y: int
    color: str
    rows: tuple[str, ...] = ()
    w: int = 0
    h: int = 0


@dataclass(frozen=True)
class LedLayout:
    """A message as draw ops, plus the text those ops show."""

    width: int
    height: int
    grid: LedGridLayout
    #: ``rows x cols`` cells, row-major. Empty for a 0x0 grid.
    cells: list[LedCell]
    options: LedRenderOptions
    ops: list[LedDrawOp]
    #: The accessible text: the *clipped* grid's rows joined with a space,
    #: tiles and undrawable characters blank, icons as their label,
    #: whitespace collapsed.
    text: str


@dataclass(frozen=True)
class LedFrame:
    """Row-major RGB888, origin top-left: ``width * height * 3`` bytes."""

    width: int
    height: int
    pixels: bytes = field(repr=False)


def _clamp_size(n: float) -> int:
    if not math.isfinite(n):
        return MIN_MATRIX_SIZE
    return max(MIN_MATRIX_SIZE, min(MAX_MATRIX_SIZE, math.floor(n)))


def grid_layout(width: float, height: float, font: str = "5x7") -> LedGridLayout:
    """As many glyph cells as fit, with the leftover pixels centred.

    ``cols = (width + spacing_x) // (glyph_width + spacing_x)``, rows likewise.
    A matrix too small for one glyph has a 0x0 grid.
    """
    width, height = _clamp_size(width), _clamp_size(height)
    face = LED_FONTS[font]
    cell_w = face.glyph_width + face.spacing_x
    cell_h = face.glyph_height + face.spacing_y
    cols = (width + face.spacing_x) // cell_w
    rows = (height + face.spacing_y) // cell_h
    used_w = cols * cell_w - face.spacing_x if cols > 0 else 0
    used_h = rows * cell_h - face.spacing_y if rows > 0 else 0
    return LedGridLayout(width, height, font, rows, cols, (width - used_w) // 2, (height - used_h) // 2)


def parse_hex_color(value: str) -> tuple[int, int, int] | None:
    """``#rrggbb`` (``#`` optional, surrounding space ignored) -> RGB, else ``None``."""
    m = _HEX.fullmatch(_JS_TRIM.sub("", value))
    return (int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)) if m else None


def resolve_hex_option(value: str | None, fallback: str | None) -> str | None:
    """A colour option as lowercase ``#rrggbb``, or ``fallback``.

    Whitespace is trimmed and a missing ``#`` supplied, so ``FFB000`` and
    ``#ffb000`` are one colour in a layout's cells and options; anything that
    is not six hex digits (``#fff``, ``rgba(...)``, a name) is the fallback.
    """
    if value is None:
        return fallback
    m = _HEX_OPTION.fullmatch(_JS_TRIM.sub("", value))
    return f"#{m.group(1).lower()}" if m else fallback


def _resolve_color_code(code: str) -> str:
    return _ALL_COLOR_CODES.get(code) or BOARD_COLORS["black"]


def _color_code_to_hex(code: str) -> str | None:
    """Hex of a colour code or ``#rrggbb``; ``None`` for an unlit colour."""
    if code in _OFF_TILE_CODES:
        return None
    if code.startswith("#"):
        return code.lower() if parse_hex_color(code) else None
    return _resolve_color_code(code)


def glyph_key(token: BoardToken, custom: Mapping[str, Sequence[str]] | None = None) -> str:
    """The stable glyph key a parsed token shows (FiestaUI ``ledGlyphKey``).

    Unknown characters are blank, as on a flap, unless ``custom`` (the
    layout's own set's bitmaps) draws them. Pure: nothing is registered, so
    the answer never depends on what was laid out before.
    """
    if token.icon:
        key = f"icon:{token.icon}"
        return key if key in _GLYPHS else _BLANK
    if token.type == "color":
        code = _TILE_CODE_BY_HEX.get(_resolve_color_code(token.code))
        return f"tile:{code}" if code else _BLANK
    value = token.value
    if value in _GLYPHS or (custom is not None and value in custom):
        return value
    return _BLANK


def _glyph_rows(key: str, face: LedFont, custom: Mapping[str, Sequence[str]] | None) -> Sequence[str] | None:
    if key.startswith("icon:"):
        return face.icons.get(key[5:])
    # A set's own bitmap wins over the face's (plan D17 rule 5): a plugin
    # that redraws `0` gets its zero.
    if custom is not None and key in custom:
        return custom[key]
    return face.glyphs.get(key)


def _fallback_key(fallback: str) -> str:
    if len(fallback) == 2 and fallback.isascii() and fallback.isdigit():
        return glyph_key(BoardToken("color", code=fallback))
    return glyph_key(BoardToken("char", value=fallback))


def draw_glyph(
    ops: list[LedDrawOp], key: str, x: int, y: int, face: LedFont, color: str, options: LedRenderOptions
) -> None:
    """Append the ops that draw glyph ``key`` into the cell at (``x``, ``y``)."""
    mono = options.monochrome
    if key == _BLANK:
        return
    if key.startswith("tile:"):
        hex_ = _color_code_to_hex(key[5:])
        # On a monochrome panel a tile is `color`: the panel colour, or black
        # inside a block span, so it still reads as a square there.
        if hex_:
            ops.append(LedDrawOp("rect", x, y, color if mono else hex_, w=face.glyph_width, h=face.glyph_height))
        return
    rows = _glyph_rows(key, face, options.glyphs)
    if key.startswith("icon:"):
        icon = BOARD_ICONS[key[5:]]
        if rows is None:
            if icon.fallback is not None:
                draw_glyph(ops, _fallback_key(icon.fallback), x, y, face, color, options)
            return
        ops.append(LedDrawOp("glyph", x, y, color if mono else icon.color, rows=tuple(rows)))
        return
    if rows is None:
        return
    heart = key == "♥"
    ops.append(LedDrawOp("glyph", x, y, color if mono else BOARD_COLORS["red"] if heart else color, rows=tuple(rows)))


def _glyph_text(key: str, face: LedFont, custom: Mapping[str, Sequence[str]] | None) -> str:
    """What a glyph adds to the accessible text; an icon's label is padded."""
    if key.startswith("icon:"):
        return f" {BOARD_ICONS[key[5:]].label} "
    if key == _BLANK or key.startswith("tile:"):
        return " "
    return key if key in face.glyphs or (custom is not None and key in custom) else " "


def _cell_field(cell: LedCell, face: LedFont, mono: str | None) -> str | None:
    """A cell's **field**: the colour its whole glyph box is lit in, or ``None``.

    A block cell's field is its background; a colour tile's is the tile's
    colour (the panel colour on a monochrome panel; ``None`` for an off tile:
    ``{black}``, ``{70}``, ``{71}``); an icon the face cannot draw, whose
    split-flap fallback is a tile, is that tile. A character, a drawn icon
    and a blank have no field: their gutters never fill and they never veto
    a neighbour's padding. FiestaUI ``cellField``.
    """
    if cell.background:
        return cell.background
    key = cell.glyph
    code: str | None = None
    if key.startswith("tile:"):
        code = key[5:]
    elif key.startswith("icon:") and key[5:] not in face.icons:
        fallback = BOARD_ICONS[key[5:]].fallback
        if fallback is not None and len(fallback) == 2 and fallback.isascii() and fallback.isdigit():
            code = fallback
    if code is None:
        return None
    hex_ = _color_code_to_hex(code)
    if not hex_:
        return None
    # As draw_glyph draws it: the panel colour on a monochrome panel.
    return cell.color if mono else hex_


def _gap_mode_block_rect(grid: LedGridLayout, cells: Sequence[LedCell], face: LedFont, row: int, col: int):
    """The rect a block cell draws under its glyph in ``"gap"`` mode (today's rule).

    Where the next cell (right, or below) is in the same block the gutter
    between them lights too, so a run reads as one pill and stacked rows as
    one slab; a neighbour of another colour keeps the gutter dark.
    """
    cell = cells[row * grid.cols + col]
    right = cells[row * grid.cols + col + 1] if col + 1 < grid.cols else None
    below = cells[(row + 1) * grid.cols + col] if row + 1 < grid.rows else None
    return (
        grid.origin_x + col * (face.glyph_width + face.spacing_x),
        grid.origin_y + row * (face.glyph_height + face.spacing_y),
        face.glyph_width + (face.spacing_x if right is not None and right.background == cell.background else 0),
        face.glyph_height + (face.spacing_y if below is not None and below.background == cell.background else 0),
    )


@dataclass(frozen=True)
class GutterPixel:
    """One gutter or margin pixel lit by ``tile_gap="fill"`` or ``block_padding=1``."""

    x: int
    y: int
    color: str
    #: Lit as part of a block's field (a preview's bloom masks it), not a tile's.
    block: bool


def gutter_pixels(grid: LedGridLayout, cells: Sequence[LedCell], options: LedRenderOptions) -> list[GutterPixel]:
    """The pixels **outside every glyph box** that ``"fill"`` and padding light, row-major.

    FiestaUI ``ledGutterPixels`` (design spec §7.6). For every matrix pixel
    ``p`` in no cell's glyph box, with ``B(p)`` the cells whose glyph box,
    grown by one pixel on every side, contains ``p`` (two for a gutter pixel,
    four for a corner, one or two for a margin pixel):

    1. ``F`` = the distinct non-``None`` fields of ``B(p)``. Empty, or more
       than one colour: unlit. Different colours never merge, and a field of
       another colour beside a padded block vetoes the padding there.
    2. Otherwise ``F = {C}`` and ``p`` lights in ``C`` when **fill** claims
       it (a gutter pixel inside the grid's used rectangle, every cell of
       ``B(p)`` with field ``C``) or **padding** claims it (some cell of
       ``B(p)`` is a block of background ``C``; gutters and margin alike).
    3. A pixel past the matrix edge does not exist.

    In ``"gap"`` a block run's own gutters are lit by its rects
    (:func:`_gap_mode_block_rect`), so padding only ever adds pixels.
    """
    fill = options.tile_gap == "fill"
    padding = options.block_padding == 1
    if (not fill and not padding) or grid.rows == 0 or grid.cols == 0:
        return []
    face = LED_FONTS[grid.font]
    gw, gh, sx, sy = face.glyph_width, face.glyph_height, face.spacing_x, face.spacing_y
    used_w = grid.cols * (gw + sx) - sx
    used_h = grid.rows * (gh + sy) - sy
    fields = [_cell_field(cell, face, options.monochrome) for cell in cells]

    def touching(at: int, origin: int, count: int, size: int, step: int) -> tuple[list[int], bool]:
        """The grid lines whose grown box covers pixel line *at*, and whether *at* is inside a box."""
        found, in_box = [], False
        for i in range(count):
            start = origin + i * step
            if start - 1 <= at <= start + size:
                found.append(i)
                in_box = in_box or start <= at < start + size
        return found, in_box

    x_min, x_max = max(0, grid.origin_x - 1), min(grid.width - 1, grid.origin_x + used_w)
    y_min, y_max = max(0, grid.origin_y - 1), min(grid.height - 1, grid.origin_y + used_h)
    columns = {}
    for x in range(x_min, x_max + 1):
        cols, col_box = touching(x, grid.origin_x, grid.cols, gw, gw + sx)
        columns[x] = (cols, col_box, grid.origin_x <= x < grid.origin_x + used_w)
    out: list[GutterPixel] = []
    for y in range(y_min, y_max + 1):
        rows, row_box = touching(y, grid.origin_y, grid.rows, gh, gh + sy)
        row_inside = grid.origin_y <= y < grid.origin_y + used_h
        for x in range(x_min, x_max + 1):
            cols, col_box, col_inside = columns[x]
            if col_box and row_box:
                continue  # inside a glyph box: a glyph pixel or a field, never a gutter
            color: str | None = None
            conflict = False
            every = True  # every bordering cell has a field
            block = False  # some bordering cell is a block of that colour
            for r in rows:
                for c in cols:
                    i = r * grid.cols + c
                    f = fields[i]
                    if f is None:
                        every = False
                        continue
                    if color is None:
                        color = f
                    elif color != f:
                        conflict = True
                    if cells[i].background == f:
                        block = True
            if color is None or conflict:
                continue
            if (fill and every and col_inside and row_inside) or (padding and block):
                out.append(GutterPixel(x, y, color, block))
    return out


def layout_cells(grid: LedGridLayout, cells: list[LedCell], options: LedRenderOptions) -> LedLayout:
    """The ops and text for resolved cells (FiestaUI ``layoutLedCells``).

    Every cell draws its glyph box: a block cell lights its field first (in
    ``"gap"`` the rect joins a same-colour block cell to the right or below,
    as before ``tile_gap`` existed; in ``"fill"`` the box alone), then the
    glyph, tile or icon over it. The gutter and margin pixels ``"fill"`` and
    padding light come last, one rect per horizontal run of one colour
    (:func:`gutter_pixels`). Nothing overlaps, so the order is cosmetic.
    """
    face = LED_FONTS[grid.font]
    cell_w = face.glyph_width + face.spacing_x
    cell_h = face.glyph_height + face.spacing_y
    fill = options.tile_gap == "fill"
    ops: list[LedDrawOp] = []
    lines: list[str] = []
    for row in range(grid.rows):
        line = []
        for col in range(grid.cols):
            cell = cells[row * grid.cols + col]
            x = grid.origin_x + col * cell_w
            y = grid.origin_y + row * cell_h
            if cell.background:
                if fill:
                    ops.append(LedDrawOp("rect", x, y, cell.background, w=face.glyph_width, h=face.glyph_height))
                else:
                    rx, ry, w, h = _gap_mode_block_rect(grid, cells, face, row, col)
                    ops.append(LedDrawOp("rect", rx, ry, cell.background, w=w, h=h))
            draw_glyph(ops, cell.glyph, x, y, face, cell.color, options)
            line.append(_glyph_text(cell.glyph, face, options.glyphs))
        lines.append("".join(line))
    # Gutter and margin pixels, merged into horizontal runs of one colour.
    run: list | None = None  # [x, y, w, color]
    for p in gutter_pixels(grid, cells, options):
        if run is not None and run[1] == p.y and run[3] == p.color and run[0] + run[2] == p.x:
            run[2] += 1
            continue
        if run is not None:
            ops.append(LedDrawOp("rect", run[0], run[1], run[3], w=run[2], h=1))
        run = [p.x, p.y, 1, p.color]
    if run is not None:
        ops.append(LedDrawOp("rect", run[0], run[1], run[3], w=run[2], h=1))
    text = _JS_SPACES.sub(" ", " ".join(lines)).strip(" ")
    return LedLayout(grid.width, grid.height, grid, cells, options, ops, text)


def _cell_for_token(
    token: BoardToken, text_color: str, monochrome: str | None, custom: Mapping[str, Sequence[str]] | None
) -> LedCell:
    # Colours are read off any token: a parsed tile never carries them, but an
    # icon whose fallback is a tile does (`{black/white:{icon:sun}}`), and that
    # cell is a block cell like any other, its glyph or tile drawn on the field.
    spanned = token.color is not None
    span = _color_code_to_hex(token.color) if spanned else None
    background = _color_code_to_hex(token.background) if token.background else None
    # An off span colour draws unlit letters; a block on a monochrome panel is
    # inverse video (lit background, unlit glyph).
    if background and monochrome:
        color = "#000000"
    elif monochrome is not None:
        color = monochrome
    elif span is not None:
        color = span
    else:
        color = "#000000" if spanned else text_color
    key = glyph_key(token, custom)
    if background:
        return LedCell(key, color, monochrome if monochrome is not None else background)
    return LedCell(key, color)


def _first(valid, *values):
    """The first of *values* that *valid* accepts (the last is the default, always valid)."""
    return next(v for v in values if valid(v))


def layout_message(
    message: str | Sequence[Sequence[BoardToken]],
    spec: LedMatrixSpec,
    options: LedLayoutOptions | None = None,
) -> LedLayout:
    """Lay a message out on the matrix's character grid (FiestaUI ``layoutLedMessage``).

    Args:
        message: Board markup (lines split on ``\\n``, parsed with extended
            markup), or rich tokens already parsed, one sequence per row
            (e.g. :func:`src.markup.message_to_grid`). Rows and cells past the
            grid are clipped; short rows are padded with blanks.
        spec: Matrix size and face.
        options: Colours, case and the character set's custom glyphs.
    """
    options = options or LedLayoutOptions()
    grid = grid_layout(spec.width, spec.height, spec.font)
    monochrome = resolve_hex_option(options.monochrome, None)
    text_color = (
        monochrome if monochrome is not None else resolve_hex_option(options.text_color, DEFAULT_LED_TEXT_COLOR)
    )
    custom = options.charset.get("glyphs") if options.charset else None
    resolved = LedRenderOptions(
        monochrome=monochrome,
        glyphs=custom,
        charset=options.charset or None,
        tile_gap=_first(is_led_tile_gap, options.tile_gap, spec.tile_gap, DEFAULT_LED_TILE_GAP),
        block_padding=_first(
            is_led_block_padding, options.block_padding, spec.block_padding, DEFAULT_LED_BLOCK_PADDING
        ),
    )
    if grid.rows == 0 or grid.cols == 0:
        return layout_cells(grid, [], resolved)

    if isinstance(message, str):
        lines = message.split("\n")
        preserve = options.letter_case == "mixed"
        rows: Sequence[Sequence[BoardToken]] = [
            parse_line(lines[r] if r < len(lines) else "", grid.cols, extended_markup=True, preserve_case=preserve)
            for r in range(grid.rows)
        ]
    else:
        rows = message
    cells: list[LedCell] = []
    for r in range(grid.rows):
        tokens = rows[r] if r < len(rows) else ()
        for c in range(grid.cols):
            token = tokens[c] if c < len(tokens) else _BLANK_TOKEN
            cells.append(_cell_for_token(token, text_color, monochrome, custom))
    return layout_cells(grid, cells, resolved)


def rasterize(layout: LedLayout) -> LedFrame:
    """Paint a layout's ops, in order, into an RGB888 frame. Off-matrix pixels are dropped."""
    pixels = bytearray(layout.width * layout.height * 3)
    paint_ops(pixels, layout.width, layout.height, layout.ops)
    return LedFrame(layout.width, layout.height, bytes(pixels))


def paint_ops(pixels: bytearray, width: int, height: int, ops: Sequence[LedDrawOp]) -> None:
    """Paint ops, in order, into a ``width x height`` RGB888 buffer (FiestaUI ``rasterizeLedOps``)."""
    for op in ops:
        rgb = bytes(parse_hex_color(op.color) or (0, 0, 0))
        if op.kind == "rect":
            points = ((op.x + dx, op.y + dy) for dy in range(op.h) for dx in range(op.w))
        else:
            points = (
                (op.x + dx, op.y + dy) for dy, line in enumerate(op.rows) for dx, ch in enumerate(line) if ch == "#"
            )
        for x, y in points:
            if 0 <= x < width and 0 <= y < height:
                i = (y * width + x) * 3
                pixels[i : i + 3] = rgb


def frame_to_bits(frame: LedFrame) -> bytes:
    """One byte per pixel, row-major: 1 where any channel is lit (what a 1-bit driver sends)."""
    p = frame.pixels
    return bytes(1 if p[i] or p[i + 1] or p[i + 2] else 0 for i in range(0, len(p), 3))


def frame_to_ascii(frame: LedFrame) -> str:
    """``#`` lit, ``.`` off, one line per pixel row: readable in a test diff."""
    bits = frame_to_bits(frame)
    w = frame.width
    return "\n".join("".join("#" if b else "." for b in bits[y * w : (y + 1) * w]) for y in range(frame.height))


class LedLayoutChoice(NamedTuple):
    """The byte-changing layout options a board draws with (:func:`led_layout_options_for_model`)."""

    tile_gap: str
    block_padding: int
    #: Why a requested value was not used, one line each: for a log warning.
    ignored: list[str]


def _policy(choice: object, every: tuple, renderer_default: object) -> dict:
    if not isinstance(choice, Mapping) or not isinstance(choice.get("allowed"), list):
        return {"allowed": list(every), "default": renderer_default}
    allowed = list(choice["allowed"])
    default = choice.get("default")
    if default is None:
        default = renderer_default if renderer_default in allowed else allowed[0]
    return {"allowed": allowed, "default": default}


def layout_policy_for_model(model: Mapping) -> dict:
    """What a DeviceModel permits for each byte-changing layout option, nothing left out.

    FiestaUI ``layoutPolicyForModel``: a field the model's ``layoutOptions``
    does not declare allows every value with the renderer's default; a
    declared one allows what it lists, and its default is the one it names,
    else the renderer's default when allowed, else the first allowed value.
    Shape: ``{"tileGap": {"allowed", "default"}, "blockPadding": {...}}``.
    """
    declared = model.get("layoutOptions")
    declared = declared if isinstance(declared, Mapping) else {}
    return {
        "tileGap": _policy(declared.get("tileGap"), LED_TILE_GAPS, DEFAULT_LED_TILE_GAP),
        "blockPadding": _policy(declared.get("blockPadding"), LED_BLOCK_PADDINGS, DEFAULT_LED_BLOCK_PADDING),
    }


def led_layout_options_for_model(
    model: Mapping, *, tile_gap: object = None, block_padding: object = None
) -> LedLayoutChoice:
    """The layout options a board on *model* draws with (FiestaUI ``ledLayoutOptionsForModel``).

    Each requested value when the model allows it, else the model's default,
    with the reason in ``ignored``; never raises, since a stale board setting
    must not take a board down. ``None`` is unset: the model's default.
    """
    policy = layout_policy_for_model(model)
    ignored: list[str] = []
    model_id = model.get("id")

    def pick(name: str, value: object, choice: dict, valid) -> object:
        if value is None:
            return choice["default"]
        if valid(value) and value in choice["allowed"]:
            return value
        allowed = ", ".join(json.dumps(v) for v in choice["allowed"])
        ignored.append(
            f"{name}={json.dumps(value)} is not a value {model_id} allows ({name}: {allowed}); "
            f"using {json.dumps(choice['default'])}"
        )
        return choice["default"]

    return LedLayoutChoice(
        pick("tileGap", tile_gap, policy["tileGap"], is_led_tile_gap),
        pick("blockPadding", block_padding, policy["blockPadding"], is_led_block_padding),
        ignored,
    )


def led_spec_for_model(model: Mapping) -> LedMatrixSpec | None:
    """A FiestaUI ``DeviceModel``'s matrix spec, or ``None`` for a non-pixel device.

    The spec carries the model's defaults for the byte-changing layout
    options (:func:`layout_policy_for_model`); an explicit option wins.
    """
    geometry = model.get("geometry", {})
    if geometry.get("kind") != "pixels":
        return None
    policy = layout_policy_for_model(model)
    return LedMatrixSpec(
        width=geometry["width"],
        height=geometry["height"],
        font=model.get("font") or "5x7",
        tile_gap=policy["tileGap"]["default"],
        block_padding=policy["blockPadding"]["default"],
    )
