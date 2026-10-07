"""Pixel canvas data model (design: ``docs/internal/reference/PIXEL_CANVAS.md`` §1).

A page may hold up to :data:`MAX_CANVASES_PER_PAGE` canvases. Each covers an
area of the page's character grid and carries drawing *content* (background,
palette, shapes, pixel rows) and/or a *source* expression that yields content
at render time. Any shape field may be a ``{{…}}`` expression, so numeric
fields accept a string as well as a number; such strings are checked only
for being expressions here and resolved by :mod:`src.canvas.evaluate`.

Validation messages are written for people and for LLMs: they name the field
and say what is allowed.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from src.led.matrix import BOARD_COLORS

__all__ = [
    "BOARD_COLOR_NAMES",
    "MAX_CANVASES_PER_PAGE",
    "MAX_CONTENT_SIZE",
    "MAX_COORD",
    "MAX_LINE_WIDTH",
    "MAX_PALETTE_KEYS",
    "MAX_PIXEL_COLS",
    "MAX_PIXEL_ROWS",
    "MAX_POLYGON_POINTS",
    "MAX_SCALE",
    "MAX_SHAPES",
    "MAX_TEXT_LENGTH",
    "RGBA",
    "Canvas",
    "CanvasArea",
    "CanvasContent",
    "CircleShape",
    "EllipseShape",
    "GradientShape",
    "LineShape",
    "PolygonShape",
    "RectShape",
    "Shape",
    "TextShape",
    "is_expression",
    "parse_color",
    "validate_page_canvases",
]

MAX_CANVASES_PER_PAGE = 8
MAX_SCALE = 8
MAX_PALETTE_KEYS = 62
MAX_SHAPES = 256
MAX_PIXEL_ROWS = 128
MAX_PIXEL_COLS = 128
MAX_CONTENT_SIZE = 128
MAX_POLYGON_POINTS = 256
MAX_TEXT_LENGTH = 256
MAX_LINE_WIDTH = 16
#: Every coordinate, length and radius lies in ``[-MAX_COORD, MAX_COORD]``,
#: which bounds the rasteriser's work for a hostile or mistaken value.
MAX_COORD = 1024

#: An RGBA colour; ``None`` wherever a colour may be is "transparent".
RGBA = tuple[int, int, int, int]

#: The board colour names a canvas understands, as the LED renderer draws them.
BOARD_COLOR_NAMES: tuple[str, ...] = tuple(BOARD_COLORS)
_TRANSPARENT_NAMES = frozenset({"none", "transparent", "."})
_HEX3 = re.compile(r"#([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])")
_HEX6 = re.compile(r"#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})")
_PALETTE_KEY = re.compile(r"[A-Za-z0-9]")
_CANVAS_ID = re.compile(r"[a-z0-9_-]{1,16}")
_LOOP_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,31}")
_COLOR_HELP = (
    f"use #rgb, #rrggbb, a palette key, a board colour name ({', '.join(BOARD_COLOR_NAMES)}), or none/transparent"
)


def is_expression(value: object) -> bool:
    """Whether *value* is a string holding a ``{{…}}`` expression."""
    return isinstance(value, str) and "{{" in value and "}}" in value


def parse_color(value: str, palette: Mapping[str, Any] | None = None) -> RGBA | None:
    """A colour string -> RGBA, or ``None`` for transparent.

    Accepts ``#rgb``, ``#rrggbb``, a board colour name (case-insensitive;
    the LED renderer's RGB values from :data:`src.led.matrix.BOARD_COLORS`),
    ``none`` / ``transparent`` / ``.``, or a key of *palette* (whose value is
    parsed the same way, without palette lookup). Raises :class:`ValueError`.
    """
    text = value.strip() if isinstance(value, str) else value
    if not isinstance(text, str) or not text:
        raise ValueError(f"{value!r} is not a colour: {_COLOR_HELP}")
    if palette is not None and len(text) == 1 and text in palette:
        entry = palette[text]
        if entry is None or isinstance(entry, tuple):  # already resolved
            return entry
        return parse_color(entry)
    lowered = text.lower()
    if lowered in _TRANSPARENT_NAMES:
        return None
    if lowered in BOARD_COLORS:
        return parse_color(BOARD_COLORS[lowered])
    if m := _HEX6.fullmatch(text):
        return (int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16), 255)
    if m := _HEX3.fullmatch(text):
        return (int(m.group(1) * 2, 16), int(m.group(2) * 2, 16), int(m.group(3) * 2, 16), 255)
    if len(text) == 1 and _PALETTE_KEY.fullmatch(text):
        raise ValueError(f"{value!r} is not a colour: it looks like a palette key, but it is not in the palette")
    raise ValueError(f"{value!r} is not a colour: {_COLOR_HELP}")


# --- Field types -----------------------------------------------------------------

#: A number, or a ``{{…}}`` expression that yields one.
Num = float | int | str
#: A colour string (literal or ``{{…}}``); checked against the palette by the content.
Color = str


def _check_num(value: Any, name: str) -> Any:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number or a {{{{…}}}} expression, not true/false")
    if isinstance(value, int | float):
        if not math.isfinite(value) or abs(value) > MAX_COORD:
            raise ValueError(f"{name} must be between -{MAX_COORD} and {MAX_COORD}, got {value}")
        return value
    if isinstance(value, str):
        if is_expression(value):
            return value
        raise ValueError(f"{name} must be a number or a {{{{…}}}} expression, got {value!r}")
    raise ValueError(f"{name} must be a number or a {{{{…}}}} expression")


def _check_color(value: Any, name: str) -> Any:
    if value is None or is_expression(value):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a colour string: {_COLOR_HELP}")
    try:
        parse_color(value, palette=None)
    except ValueError as exc:
        # A single character may be a palette key: the content checks those.
        if len(value.strip()) == 1 and _PALETTE_KEY.fullmatch(value.strip()):
            return value
        raise ValueError(f"{name}: {exc}") from None
    return value


_NUM_FIELDS = ("x", "y", "w", "h", "cx", "cy", "r", "rx", "ry", "x1", "y1", "x2", "y2", "width", "angle")
_COLOR_FIELDS = ("fill", "stroke", "color", "from", "to")


class _ShapeBase(BaseModel):
    """Fields every shape has: ``if``, ``foreach`` and ``as``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    if_: bool | str | None = Field(default=None, alias="if")
    foreach: str | None = None
    as_: str | None = Field(default=None, alias="as")

    @field_validator("if_")
    @classmethod
    def _if_is_expression(cls, value: Any) -> Any:
        if isinstance(value, str) and not is_expression(value):
            raise ValueError('"if" must be true, false or a {{…}} expression')
        return value

    @field_validator("foreach")
    @classmethod
    def _foreach_is_expression(cls, value: Any) -> Any:
        if value is not None and not is_expression(value):
            raise ValueError('"foreach" must be a {{…}} expression that yields a list, e.g. "{{plugin.items}}"')
        return value

    @field_validator("as_")
    @classmethod
    def _as_is_a_name(cls, value: Any) -> Any:
        if value is not None and not _LOOP_NAME.fullmatch(value):
            raise ValueError('"as" must be a simple name (letters, digits, _; not starting with a digit), e.g. "p"')
        return value

    @field_validator(*_NUM_FIELDS, mode="before", check_fields=False)
    @classmethod
    def _number_fields(cls, value: Any, info: ValidationInfo) -> Any:
        return value if value is None else _check_num(value, info.field_name)

    @field_validator(*_COLOR_FIELDS, mode="before", check_fields=False)
    @classmethod
    def _color_fields(cls, value: Any, info: ValidationInfo) -> Any:
        name = info.field_name.rstrip("_")
        return _check_color(value, name)

    @model_validator(mode="after")
    def _as_needs_foreach(self) -> _ShapeBase:
        if self.as_ is not None and self.foreach is None:
            raise ValueError('"as" names the "foreach" item; add "foreach" or remove "as"')
        return self

    def colors(self) -> list[tuple[str, str]]:
        """``(field, value)`` for every literal colour field that is set."""
        out = []
        for name in _COLOR_FIELDS:
            attr = "from_" if name == "from" else name
            value = getattr(self, attr, None)
            if isinstance(value, str) and not is_expression(value):
                out.append((name, value))
        return out


class RectShape(_ShapeBase):
    type: Literal["rect"]
    x: Num
    y: Num
    w: Num
    h: Num
    fill: Color | None = None
    stroke: Color | None = None


class CircleShape(_ShapeBase):
    type: Literal["circle"]
    cx: Num
    cy: Num
    r: Num
    fill: Color | None = None
    stroke: Color | None = None


class EllipseShape(_ShapeBase):
    type: Literal["ellipse"]
    cx: Num
    cy: Num
    rx: Num
    ry: Num
    fill: Color | None = None
    stroke: Color | None = None


class LineShape(_ShapeBase):
    type: Literal["line"]
    x1: Num
    y1: Num
    x2: Num
    y2: Num
    stroke: Color
    width: Num = 1

    @field_validator("width")
    @classmethod
    def _width_range(cls, value: Any) -> Any:
        if isinstance(value, int | float) and not 1 <= value <= MAX_LINE_WIDTH:
            raise ValueError(f"width must be between 1 and {MAX_LINE_WIDTH}, got {value}")
        return value


class PolygonShape(_ShapeBase):
    type: Literal["polygon"]
    #: ``[[x, y], …]`` (each value a number or expression), or one expression yielding that list.
    points: list[tuple[Num, Num]] | str
    fill: Color | None = None
    stroke: Color | None = None

    @field_validator("points", mode="before")
    @classmethod
    def _points(cls, value: Any) -> Any:
        if isinstance(value, str):
            if not is_expression(value):
                raise ValueError("points must be a list of [x, y] pairs or a {{…}} expression yielding one")
            return value
        if not isinstance(value, list):
            raise ValueError("points must be a list of [x, y] pairs")
        if not 3 <= len(value) <= MAX_POLYGON_POINTS:
            raise ValueError(f"a polygon needs at least 3 points and at most {MAX_POLYGON_POINTS}, got {len(value)}")
        out = []
        for i, point in enumerate(value):
            if not isinstance(point, list | tuple) or len(point) != 2:
                raise ValueError(f"points[{i}] must be an [x, y] pair")
            out.append((_check_num(point[0], f"points[{i}].x"), _check_num(point[1], f"points[{i}].y")))
        return out


class TextShape(_ShapeBase):
    type: Literal["text"]
    x: Num
    y: Num
    text: str = Field(max_length=MAX_TEXT_LENGTH)
    color: Color
    font: Literal["3x5", "5x7"] = "5x7"


class GradientShape(_ShapeBase):
    type: Literal["gradient"]
    x: Num | None = None
    y: Num | None = None
    w: Num | None = None
    h: Num | None = None
    from_: Color = Field(alias="from")
    to: Color
    #: Degrees; 0 = left→right, 90 = top→bottom (y grows downward).
    angle: Num = 90


Shape = Annotated[
    RectShape | CircleShape | EllipseShape | LineShape | PolygonShape | TextShape | GradientShape,
    Field(discriminator="type"),
]


class CanvasContent(BaseModel):
    """What a canvas draws, in its own coordinate space (``size``)."""

    model_config = ConfigDict(extra="forbid")

    #: Content coordinate space ``[width, height]``; default = the canvas pixel size.
    size: tuple[int, int] | None = None
    background: Color | None = None
    palette: dict[str, str] = Field(default_factory=dict)
    shapes: list[Shape] = Field(default_factory=list)
    pixels: list[str] = Field(default_factory=list)

    @field_validator("size", mode="before")
    @classmethod
    def _size(cls, value: Any) -> Any:
        if value is None:
            return value
        if (
            not isinstance(value, list | tuple)
            or len(value) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in value)
            or not all(1 <= v <= MAX_CONTENT_SIZE for v in value)
        ):
            raise ValueError(f"size must be [width, height], each a whole number from 1 to {MAX_CONTENT_SIZE}")
        return tuple(value)

    @field_validator("background", mode="before")
    @classmethod
    def _background(cls, value: Any) -> Any:
        return _check_color(value, "background")

    @field_validator("palette")
    @classmethod
    def _palette(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > MAX_PALETTE_KEYS:
            raise ValueError(f"a palette has at most {MAX_PALETTE_KEYS} keys, got {len(value)}")
        for key, colour in value.items():
            if key == ".":
                raise ValueError('palette key "." is reserved for transparent; pick a letter or digit')
            if len(key) != 1:
                raise ValueError(f"palette key {key!r} must be a single character (A-Z, a-z or 0-9)")
            if not _PALETTE_KEY.fullmatch(key):
                raise ValueError(f"palette key {key!r} must be a letter or digit (A-Z, a-z, 0-9)")
            try:
                parse_color(colour)
            except ValueError as exc:
                raise ValueError(f"palette[{key!r}]: {exc}") from None
        return value

    @field_validator("shapes", mode="before")
    @classmethod
    def _shape_count(cls, value: Any) -> Any:
        if isinstance(value, list) and len(value) > MAX_SHAPES:
            raise ValueError(f"a canvas has at most {MAX_SHAPES} shapes, got {len(value)}")
        return value

    @field_validator("pixels")
    @classmethod
    def _pixel_bounds(cls, value: list[str]) -> list[str]:
        if len(value) > MAX_PIXEL_ROWS:
            raise ValueError(f"pixels has at most {MAX_PIXEL_ROWS} rows, got {len(value)}")
        for i, row in enumerate(value):
            if len(row) > MAX_PIXEL_COLS:
                raise ValueError(f"pixels row {i + 1} has at most {MAX_PIXEL_COLS} characters, got {len(row)}")
        return value

    @model_validator(mode="after")
    def _palette_references(self) -> CanvasContent:
        palette = self.palette
        for i, row in enumerate(self.pixels):
            for ch in row:
                if ch != "." and ch not in palette:
                    raise ValueError(
                        f"pixels row {i + 1}: {ch!r} is not in the palette (use a palette key, or '.' for transparent)"
                    )
        literal = [("background", self.background)] if self.background and not is_expression(self.background) else []
        for i, shape in enumerate(self.shapes):
            literal += [(f"shapes[{i}].{name}", value) for name, value in shape.colors()]
        for where, value in literal:
            try:
                parse_color(value, palette)
            except ValueError as exc:
                raise ValueError(f"{where}: {exc}") from None
        return self


BleedSide = Literal["top", "left", "right", "bottom", "all"]


class CanvasArea(BaseModel):
    """1-based character cells of the page grid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    row: int = Field(ge=1)
    col: int = Field(ge=1)
    rows: int = Field(ge=1)
    cols: int = Field(ge=1)


class Canvas(BaseModel):
    """One pixel canvas on a page."""

    model_config = ConfigDict(extra="forbid")

    id: str
    area: CanvasArea
    #: Sides that extend to the panel edge (honoured only where the area touches the grid edge).
    bleed: list[BleedSide] = Field(default_factory=list)
    #: Panel pixels per canvas pixel.
    scale: int = Field(default=1, ge=1, le=MAX_SCALE)
    #: ``hide``: text under the canvas is blanked. ``flow``: text flows around it.
    text: Literal["hide", "flow"] = "hide"
    content: CanvasContent | None = None
    #: A ``{{…}}`` expression yielding a content object (e.g. a plugin's ``format: canvas`` variable).
    source: str | None = None

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not _CANVAS_ID.fullmatch(value):
            raise ValueError(f"canvas id {value!r} must be 1-16 characters of a-z, 0-9, _ or -")
        return value

    @field_validator("scale", mode="before")
    @classmethod
    def _scale(cls, value: Any) -> Any:
        if isinstance(value, int) and not isinstance(value, bool) and not 1 <= value <= MAX_SCALE:
            raise ValueError(f"scale must be a whole number from 1 to {MAX_SCALE}, got {value}")
        return value

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Any:
        if value not in ("hide", "flow"):
            raise ValueError(f"text must be 'hide' or 'flow', got {value!r}")
        return value

    @field_validator("source")
    @classmethod
    def _source(cls, value: str | None) -> str | None:
        if value is not None and not is_expression(value):
            raise ValueError('source must be a {{…}} expression yielding a content object, e.g. "{{plugin.canvas}}"')
        return value

    @model_validator(mode="after")
    def _has_something_to_draw(self) -> Canvas:
        if self.content is None and self.source is None:
            raise ValueError(f"canvas {self.id!r} needs content, a source, or both")
        return self


def validate_page_canvases(canvases: Iterable[Canvas | Mapping[str, Any]] | None) -> list[Canvas]:
    """Validate a page's canvases: each one, at most 8, ids unique. ``None`` is no canvases.

    Raises :class:`ValueError` (a pydantic ``ValidationError`` for a bad canvas).
    """
    if canvases is None:
        return []
    items = [c if isinstance(c, Canvas) else Canvas.model_validate(c) for c in canvases]
    if len(items) > MAX_CANVASES_PER_PAGE:
        raise ValueError(f"a page has at most {MAX_CANVASES_PER_PAGE} canvases, got {len(items)}")
    seen: set[str] = set()
    for canvas in items:
        if canvas.id in seen:
            raise ValueError(f"canvas id {canvas.id!r} is used twice; ids must be unique in a page")
        seen.add(canvas.id)
    return items
