"""The style cascade: requested style, resolved for one board (spec section 3).

Style values are **requests**. :func:`resolve_block_style` merges the levels
of the cascade (device default, board style, page style, block style; lowest
first) and turns the result into what this board can show, recording every
compromise as a :class:`~src.layout.issues.LayoutIssue`:

- **Font**: the requested family, else the board style's family, else
  ``fiesta``; each miss is ``font_unavailable``.
- **Size**: a named size maps through :func:`~src.layout.fonts.named_size_heights`;
  an exact pixel height takes the largest face (at an integer scale) no taller
  than it (``size_rounded`` when inexact, ``size_too_small`` below the smallest
  face). A cell target has one character size: any other size is ``size_ignored``.
- **Colour**: ``rgb`` boards preserve explicit RGB values. Named black and
  unlit tile codes mean ``#000000``; a black background is an opaque unlit
  fill. ``mono`` boards light any non-black colour in the
  panel colour and leave black unlit; a lit background is inverse video (the
  text is unlit). ``tiles`` boards drop text
  colour (``color_dropped``) and, in Phase 1, background (``background_dropped``).
  A value that is not a colour is ``color_invalid`` and the level below applies.
- **Case**: ``lower`` without lowercase glyphs is ``case_unsupported``, drawn upper.
- **Overflow**: ``scroll`` (reserved) is ``overflow_unsupported``, drawn as ``ellipsis``.
- **Unknown properties** are ``style_unknown`` (info); the document keeps them.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from src.led.matrix import BOARD_COLORS, DEFAULT_LED_TEXT_COLOR, color_code_to_hex

from .fonts import (
    DEFAULT_FONT_FAMILY,
    FONT_FAMILIES,
    NAMED_SIZES,
    SizedFace,
    face_for_height,
    face_for_led_font,
    named_size_heights,
    size_ladder,
)
from .issues import LayoutIssue

if TYPE_CHECKING:
    from src.pages.flexible import FlexLayout

    from .target import FlexTarget

__all__ = [
    "GAP_PX",
    "STYLE_PROPERTIES",
    "ResolvedLayout",
    "ResolvedStyle",
    "board_style_for",
    "device_default_style",
    "resolve_block_style",
    "resolve_color_value",
    "resolve_layout",
]

#: The style properties this build resolves; any other key is ``style_unknown``.
STYLE_PROPERTIES = ("font", "size", "color", "background", "align", "case", "overflow", "height")

#: Pixels between stacked blocks for each named ``gap``.
GAP_PX: Mapping[str, int] = MappingProxyType({"none": 0, "small": 1, "medium": 2, "large": 4})

_ALIGNS = frozenset({"left", "center", "right"})
_CASES = frozenset({"as-is", "upper", "lower"})
_OVERFLOWS = frozenset({"wrap", "shrink", "ellipsis", "scroll"})
_HEIGHT_WORDS = frozenset({"auto", "fill"})

_TILE_CODE = re.compile(r"\{?(6[3-9]|7[01])\}?")
_NAME = re.compile(r"\{?([a-z]+)\}?")
_HEX6 = re.compile(r"#[0-9a-f]{6}")
_UNLIT_CODES = frozenset({"70", "71"})


@dataclass(frozen=True)
class ResolvedStyle:
    """A block's style as this board draws it.

    ``sized`` is the face and integer scale text is drawn in and ``px`` its
    height; on a cell target (one character size) ``sized`` is ``None`` and
    ``px`` is 0. ``color`` and ``background`` are lowercase ``#rrggbb``.
    Black is unlit, as on a grid cell: on an rgb board black text is
    ``#000000``; on a mono panel ``color`` ``None`` means the text lights no
    pixels (black text, or any text on a lit background: inverse video); on a
    tile board ``color`` is ``None`` (text carries no colour). ``background``
    ``None`` means no fill (none asked for, or unlit on a mono target). ``fit`` is true when the size asked for was ``fit``: the
    fitter picks the size, starting from ``sized``.
    """

    family: str
    sized: SizedFace | None
    px: int
    color: str | None
    background: str | None
    align: Literal["left", "center", "right"]
    case: Literal["as-is", "upper", "lower"]
    overflow: Literal["wrap", "shrink", "ellipsis"]
    height: Literal["auto", "fill"] | int | float
    fit: bool


@dataclass(frozen=True)
class ResolvedLayout:
    """How the page's blocks are arranged: ``kind`` (always ``stack`` in v1), ``valign``, ``gap_px``."""

    kind: str
    valign: Literal["top", "middle", "bottom", "spread"]
    gap_px: int


def board_style_for(board: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """The board's own style level in the cascade.

    Board style (a per-board default font, size, text colour and background)
    arrives in Phase 3; until then every board's level is empty.
    """
    return MappingProxyType({})


def device_default_style(target: FlexTarget) -> dict[str, Any]:
    """The lowest cascade level: what the device draws when nothing is asked for.

    Text colour is the device's own (white; a mono panel's lit colour). A tile
    board has no text colour, so it has no default to drop.
    """
    style: dict[str, Any] = {
        "font": DEFAULT_FONT_FAMILY,
        "size": "medium",
        "align": "left",
        "case": "as-is",
        "overflow": "wrap",
        "height": "auto",
    }
    if target.color_model == "rgb":
        style["color"] = DEFAULT_LED_TEXT_COLOR
    elif target.color_model == "mono":
        style["color"] = target.monochrome
    return style


def resolve_color_value(value: str, context: Mapping[str, Any], *, engine: Any = None) -> str | None:
    """``value`` as lowercase ``#rrggbb``, or ``None`` when it is not a colour.

    Accepts a board colour name (``red``), a tile code 63-71 with or without
    braces (``{63}``, ``63``) and ``#rrggbb``; surrounding whitespace is
    trimmed and case folded. A value holding a ``{{…}}`` expression is first
    rendered by ``engine`` (default: the shared template engine) against
    ``context``. Named black and unlit codes (70, 71) are ``#000000``;
    explicit RGB values are preserved. Never raises.
    """
    text = value
    if "{{" in text:
        try:
            if engine is None:
                from src.templates.engine import get_template_engine

                engine = get_template_engine()
            text = engine.render(text, dict(context), extended_markup=True)
        except Exception:
            return None
        if not isinstance(text, str):
            return None
    text = text.strip().lower()
    code = _TILE_CODE.fullmatch(text)
    if code:
        key = code.group(1)
        return "#000000" if key in _UNLIT_CODES else color_code_to_hex(key)
    name = _NAME.fullmatch(text)
    if name and name.group(1) in BOARD_COLORS:
        key = name.group(1)
        return "#000000" if key == "black" else color_code_to_hex(key)
    if _HEX6.fullmatch(text):
        return text
    return None


def _is_black(hex_color: str) -> bool:
    return hex_color == "#000000"


def _valid_height(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return value in _HEIGHT_WORDS
    return isinstance(value, int | float) and value >= 0


def _valid_size(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return value in NAMED_SIZES or value == "fit"
    return isinstance(value, int) and value >= 1


class _Resolver:
    """One block's resolution: the levels (lowest first) and the issues found."""

    def __init__(
        self,
        levels: Sequence[Mapping[str, Any]],
        target: FlexTarget,
        context: Mapping[str, Any],
        path: tuple[str, ...],
        engine: Any,
    ) -> None:
        self.default = device_default_style(target)
        self.requested = [level for level in levels if level is not None]
        self.target = target
        self.context = context
        self.path = path
        self.engine = engine
        self.issues: list[LayoutIssue] = []

    def report(self, key: str, code: str, severity: Literal["info", "warning"], message: str) -> None:
        self.issues.append(LayoutIssue(path=(*self.path, "style", key), code=code, severity=severity, message=message))

    def candidates(self, key: str) -> list[tuple[Any, bool]]:
        """Every value set for ``key``, highest level first, each with whether it is the device default."""
        found = [(level[key], False) for level in reversed(self.requested) if level.get(key) is not None]
        if self.default.get(key) is not None:
            found.append((self.default[key], True))
        return found

    def pick(self, key: str, valid: Callable[[Any], bool]) -> Any:
        """The highest valid value for ``key``; an invalid one is reported and skipped."""
        for value, _ in self.candidates(key):
            if valid(value):
                return value
            self.report(key, "style_unknown", "info", f"{key} {value!r} is not a value this board knows; ignored")
        return None

    def unknown_keys(self) -> None:
        seen: set[str] = set()
        for level in self.requested:
            for key, value in level.items():
                if key in STYLE_PROPERTIES or key in seen or value is None:
                    continue
                seen.add(key)
                self.report(key, "style_unknown", "info", f"style property {key!r} is not drawn by this build")

    def family(self) -> str:
        requested = self.pick("font", lambda v: isinstance(v, str))
        if requested in FONT_FAMILIES:
            return requested
        self.report("font", "font_unavailable", "warning", f"font {requested!r} is not available; using another")
        board_font = self.target.board_style.get("font")
        if isinstance(board_font, str) and board_font != requested:
            if board_font in FONT_FAMILIES:
                return board_font
            self.report(
                "font", "font_unavailable", "warning", f"board font {board_font!r} is not available; using fiesta"
            )
        return DEFAULT_FONT_FAMILY

    def size(self, family_id: str) -> tuple[SizedFace | None, int, bool]:
        size = self.pick("size", _valid_size)
        target = self.target
        if not target.pixels or target.height is None:
            if size != "medium":
                self.report("size", "size_ignored", "info", "this board has one character size; size ignored")
            return None, 0, False
        family = FONT_FAMILIES[family_id]
        try:
            default_height = face_for_led_font(target.default_face_id or "").pixel_height
        except KeyError:
            default_height = size_ladder(family)[0].height
        named = named_size_heights(surface_height=target.height, default_height=default_height, family=family)
        if size == "fit":
            sized, _ = face_for_height(family, named["medium"])
            return sized, sized.height, True
        if isinstance(size, str):
            sized, _ = face_for_height(family, named[size])
            return sized, sized.height, False
        sized, exact = face_for_height(family, size)
        smallest = size_ladder(family)[0].height
        if size < smallest:
            self.report(
                "size", "size_too_small", "warning", f"{size}px is smaller than the smallest face ({smallest}px)"
            )
        elif not exact:
            self.report("size", "size_rounded", "info", f"{size}px is drawn at {sized.height}px")
        return sized, sized.height, False

    def color(self, key: str) -> str | None:
        """``color`` or ``background`` for this board's colour model."""
        model = self.target.color_model
        for value, is_default in self.candidates(key):
            if key == "background" and isinstance(value, str) and value.strip().lower() == "transparent":
                return None
            if model == "tiles":
                if not is_default:
                    code = "color_dropped" if key == "color" else "background_dropped"
                    self.report(key, code, "info", f"this board cannot draw a {key}; dropped")
                return None
            if not isinstance(value, str):
                self.report(key, "color_invalid", "warning", f"{key} {value!r} is not a colour")
                continue
            resolved = resolve_color_value(value, self.context, engine=self.engine)
            if resolved is None:
                self.report(key, "color_invalid", "warning", f"{key} {value!r} is not a colour")
                continue
            if model == "mono":
                return None if _is_black(resolved) else self.target.monochrome
            return resolved
        return None

    def case(self) -> str:
        case = self.pick("case", lambda v: v in _CASES)
        if case == "lower" and not self.target.mixed_case:
            self.report("case", "case_unsupported", "info", "this board has no lowercase; drawn in capitals")
            return "upper"
        return case

    def overflow(self) -> str:
        overflow = self.pick("overflow", lambda v: v in _OVERFLOWS)
        if overflow == "scroll":
            self.report("overflow", "overflow_unsupported", "info", "scroll is not built yet; text is ellipsised")
            return "ellipsis"
        return overflow


def resolve_block_style(
    levels: Sequence[Mapping[str, Any] | None],
    target: FlexTarget,
    context: Mapping[str, Any],
    *,
    path: tuple[str, ...],
    engine: Any = None,
) -> tuple[ResolvedStyle, list[LayoutIssue]]:
    """Resolve the cascade for one block on ``target``.

    ``levels`` are the levels above the device default, lowest first:
    ``[target.board_style, page.style, block.style]``; ``None`` levels are
    skipped. :func:`device_default_style` is always the lowest level. Issues
    carry ``path + ("style", <property>)``. ``context`` and ``engine`` render
    ``{{…}}`` colour expressions (:func:`resolve_color_value`).
    """
    r = _Resolver(levels, target, context, path, engine)
    r.unknown_keys()
    family = r.family()
    sized, px, fit = r.size(family)
    color = r.color("color")
    background = r.color("background")
    if target.color_model == "mono" and background is not None:
        # Inverse video, as a grid cell on a monochrome panel: lit field, unlit glyph.
        color = None
    align = r.pick("align", lambda v: v in _ALIGNS)
    case = r.case()
    overflow = r.overflow()
    height = r.pick("height", _valid_height)
    style = ResolvedStyle(
        family=family,
        sized=sized,
        px=px,
        color=color,
        background=background,
        align=align,
        case=case,
        overflow=overflow,
        height=height,
        fit=fit,
    )
    return style, r.issues


def resolve_layout(layout: FlexLayout | None, *, path: tuple[str, ...]) -> tuple[ResolvedLayout, list[LayoutIssue]]:
    """The page's arrangement. Only ``stack`` is built: any other kind is a
    ``layout_kind_unsupported`` warning and is laid out as a stack."""
    from src.pages.flexible import FlexLayout

    layout = layout if layout is not None else FlexLayout()
    issues: list[LayoutIssue] = []
    if layout.kind != "stack":
        issues.append(
            LayoutIssue(
                path=(*path, "kind"),
                code="layout_kind_unsupported",
                severity="warning",
                message=f"layout {layout.kind!r} is not built yet; blocks are stacked",
            )
        )
    gap = layout.gap
    gap_px = GAP_PX[gap] if isinstance(gap, str) else max(0, int(gap))
    return ResolvedLayout(kind="stack", valign=layout.valign, gap_px=gap_px), issues
