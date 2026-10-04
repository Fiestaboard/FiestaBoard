"""LED matrix layout and raster: a board message to the RGB888 bytes a panel shows.

A port of FiestaUI's ``src/lib/led-matrix.ts`` (a70b719), the reference
implementation (plan D15): :func:`grid_layout` is ``ledGridLayout``,
:func:`layout_message` is ``layoutLedMessage``, :func:`rasterize` is
``rasterizeLedLayout``, :func:`frame_to_bits` is ``frameToBits``. The golden
fixtures in ``tests/fixtures/led/`` hold it to FiestaUI's bytes.

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

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from src.markup import BOARD_ICONS, BoardToken, parse_line

from .charsets import CharacterSet
from .fonts import LED_FONTS, LedFont

__all__ = [
    "BOARD_COLORS",
    "DEFAULT_LED_TEXT_COLOR",
    "LED_GLYPHS",
    "LED_MONO_COLORS",
    "MAX_MATRIX_SIZE",
    "MIN_MATRIX_SIZE",
    "LedCell",
    "LedDrawOp",
    "LedFrame",
    "LedGridLayout",
    "LedLayout",
    "LedLayoutOptions",
    "LedMatrixSpec",
    "LedRenderOptions",
    "draw_glyph",
    "frame_to_ascii",
    "frame_to_bits",
    "glyph_key",
    "grid_layout",
    "layout_cells",
    "layout_message",
    "led_spec_for_model",
    "parse_hex_color",
    "rasterize",
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

#: Every glyph an LED cell can show, as keys (FiestaUI ``LED_GLYPHS``): a
#: character, ``tile:<code>`` or ``icon:<name>``. Membership only; FiestaUI
#: stores an index into this table, which is process-local, so a cell here
#: stores the key. Blank is ``" "``.
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


@dataclass(frozen=True)
class LedMatrixSpec:
    """A matrix: pixels across and down, and the face text is set in."""

    width: int
    height: int
    font: str = "5x7"


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


@dataclass(frozen=True)
class LedRenderOptions:
    """The resolved options a layout's cells need to be drawn again."""

    monochrome: str | None = None
    glyphs: Mapping[str, Sequence[str]] | None = None


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


def _resolve_hex(value: str | None, fallback: str | None) -> str | None:
    return value.lower() if value is not None and parse_hex_color(value) else fallback


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
    """The glyph a parsed token shows (FiestaUI ``ledGlyphIndex``).

    Unknown characters are blank, as on a flap, unless ``custom`` (a
    character set's own bitmaps) has them.
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
    # A set's own bitmap wins over the face's (plan D17 rule 5; FiestaUI's
    # CharacterSet.glyphs contract, though its a70b719 code checks the face first).
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


def layout_cells(grid: LedGridLayout, cells: list[LedCell], options: LedRenderOptions) -> LedLayout:
    """The ops and text for resolved cells (FiestaUI ``layoutLedCells``)."""
    face = LED_FONTS[grid.font]
    cell_w = face.glyph_width + face.spacing_x
    cell_h = face.glyph_height + face.spacing_y
    ops: list[LedDrawOp] = []
    lines: list[str] = []
    for row in range(grid.rows):
        line = []
        for col in range(grid.cols):
            cell = cells[row * grid.cols + col]
            x = grid.origin_x + col * cell_w
            y = grid.origin_y + row * cell_h
            if cell.background:
                # The gutter to a neighbour in the same block lights too, so a
                # run reads as one pill; a different colour keeps it dark.
                right = cells[row * grid.cols + col + 1] if col + 1 < grid.cols else None
                below = cells[(row + 1) * grid.cols + col] if row + 1 < grid.rows else None
                w = face.glyph_width + (face.spacing_x if right and right.background == cell.background else 0)
                h = face.glyph_height + (face.spacing_y if below and below.background == cell.background else 0)
                ops.append(LedDrawOp("rect", x, y, cell.background, w=w, h=h))
            draw_glyph(ops, cell.glyph, x, y, face, cell.color, options)
            line.append(_glyph_text(cell.glyph, face, options.glyphs))
        lines.append("".join(line))
    text = _JS_SPACES.sub(" ", " ".join(lines)).strip(" ")
    return LedLayout(grid.width, grid.height, grid, cells, options, ops, text)


def _cell_for_token(
    token: BoardToken, text_color: str, monochrome: str | None, custom: Mapping[str, Sequence[str]] | None
) -> LedCell:
    is_char = token.type == "char"
    spanned = is_char and token.color is not None
    span = _color_code_to_hex(token.color) if spanned else None
    background = _color_code_to_hex(token.background) if is_char and token.background else None
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
    monochrome = _resolve_hex(options.monochrome, None)
    text_color = monochrome if monochrome is not None else _resolve_hex(options.text_color, DEFAULT_LED_TEXT_COLOR)
    custom = options.charset.get("glyphs") if options.charset else None
    resolved = LedRenderOptions(monochrome=monochrome, glyphs=custom)
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
    width, height = layout.width, layout.height
    pixels = bytearray(width * height * 3)
    for op in layout.ops:
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
    return LedFrame(width, height, bytes(pixels))


def frame_to_bits(frame: LedFrame) -> bytes:
    """One byte per pixel, row-major: 1 where any channel is lit (what a 1-bit driver sends)."""
    p = frame.pixels
    return bytes(1 if p[i] or p[i + 1] or p[i + 2] else 0 for i in range(0, len(p), 3))


def frame_to_ascii(frame: LedFrame) -> str:
    """``#`` lit, ``.`` off, one line per pixel row: readable in a test diff."""
    bits = frame_to_bits(frame)
    w = frame.width
    return "\n".join("".join("#" if b else "." for b in bits[y * w : (y + 1) * w]) for y in range(frame.height))


def led_spec_for_model(model: Mapping) -> LedMatrixSpec | None:
    """A FiestaUI ``DeviceModel``'s matrix spec, or ``None`` for a non-pixel device."""
    geometry = model.get("geometry", {})
    if geometry.get("kind") != "pixels":
        return None
    return LedMatrixSpec(width=geometry["width"], height=geometry["height"], font=model.get("font") or "5x7")
