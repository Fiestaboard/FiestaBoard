"""Resolve a canvas against the page's variable context (design §1, §3 step 2).

Everything that may hold a ``{{…}}`` expression is evaluated with the
template engine's formula language (:func:`src.templates.expressions.evaluate_value`),
so canvases read plugin data exactly as ``{{= … }}`` formulas do: variable
paths, ``IF``, ``LET``, arithmetic, string functions. The leading ``=`` is
optional inside a canvas.

- A field that is *one* ``{{…}}`` takes the expression's native value
  (numbers stay numbers, a list stays a list); a string with text around its
  expressions (``"T {{weather.temp}}"``) interpolates them as board text.
- ``if``: falsy (``false``, ``0``, ``""``, ``"no"``, empty list) skips the shape.
- ``foreach`` + ``as`` (default ``item``): the shape repeats per list item,
  with ``<as>.index`` (0-based), ``<as>.value`` (the item itself) and, for a
  dict item, each of its fields as ``<as>.<field>`` (a field named ``value``
  shadows the item; ``index`` is always the position).
- ``source`` yields a content object (a dict, or a JSON string of one) that
  replaces the stored content; if it fails, the stored content is used.

Nothing raises: a field that fails to evaluate (or yields the wrong kind of
value) skips its shape — or that one ``foreach`` item — and records a
:class:`CanvasIssue`.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from src.templates.expressions import FormulaError, ensure_render_clock, evaluate_value, value_to_text

from .models import MAX_COORD, MAX_LINE_WIDTH, RGBA, Canvas, CanvasContent, is_expression, parse_color

__all__ = [
    "MAX_EXPANDED_SHAPES",
    "CanvasIssue",
    "ResolvedContent",
    "ResolvedShape",
    "resolve_canvas",
    "resolve_content",
]

#: Shapes one canvas may draw after ``foreach`` expansion.
MAX_EXPANDED_SHAPES = 1024

_EXPR = re.compile(r"\{\{(.*?)\}\}", re.S)
_NUMBER_FIELDS = frozenset({"x", "y", "w", "h", "cx", "cy", "r", "rx", "ry", "x1", "y1", "x2", "y2", "width", "angle"})
_COLOR_FIELDS = frozenset({"fill", "stroke", "color", "from", "to"})
_CONTROL_FIELDS = frozenset({"type", "if_", "foreach", "as_"})
_FORMULA_HINTS = {
    "#REF": "a variable it names has no value",
    "#NAME?": "unknown function",
    "#SYNTAX": "syntax error",
    "#VALUE": "wrong kind of value",
    "#DIV/0": "division by zero",
    "#NUM": "number out of range",
}


@dataclass(frozen=True)
class CanvasIssue:
    """A problem met while resolving or drawing a canvas; the canvas still renders."""

    canvas_id: str
    #: Where: ``source``, ``area``, ``background``, ``shapes[3].x``, ``shapes[3].foreach``.
    path: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {"canvas_id": self.canvas_id, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class ResolvedShape:
    """A shape with every field concrete.

    ``values`` maps each field (public names, e.g. ``"from"``) to: a float for
    numbers, an RGBA tuple or ``None`` (transparent / unset) for colours, a
    ``str`` for ``text`` / ``font``, a list of ``(x, y)`` float pairs for
    ``points``; gradient ``x/y/w/h`` stay ``None`` when unset.
    """

    type: str
    values: dict[str, Any]


@dataclass(frozen=True)
class ResolvedContent:
    """Canvas content ready to rasterise."""

    size: tuple[int, int] | None
    background: RGBA | None
    palette: dict[str, RGBA | None]
    shapes: tuple[ResolvedShape, ...] = ()
    pixels: tuple[str, ...] = field(default=())


class _Skip(Exception):
    """A field could not be resolved; the shape (or foreach item) is skipped."""

    def __init__(self, field_name: str, message: str):
        super().__init__(message)
        self.field_name = field_name
        self.message = message


def _formula_message(text: str, exc: FormulaError) -> str:
    hint = _FORMULA_HINTS.get(exc.code.split(":")[0])
    return f"{text} failed with {exc.code}" + (f" ({hint})" if hint else "")


def _value(raw: Any, field_name: str, context: dict[str, Any], bindings: dict[str, Any] | None) -> Any:
    """*raw* with its ``{{…}}`` expressions evaluated (see the module docstring)."""
    if not is_expression(raw):
        return raw
    text = raw.strip()
    matches = list(_EXPR.finditer(text))
    try:
        if len(matches) == 1 and matches[0].span() == (0, len(text)):
            return evaluate_value(_body(matches[0].group(1)), context, bindings)
        return _EXPR.sub(lambda m: value_to_text(evaluate_value(_body(m.group(1)), context, bindings)), raw)
    except FormulaError as exc:
        raise _Skip(field_name, _formula_message(text, exc)) from None


def _body(inner: str) -> str:
    body = inner.strip()
    return body[1:].strip() if body.startswith("=") else body


def _number(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise _Skip(field_name, f"expected a number, got {value}")
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            raise _Skip(field_name, f"expected a number, got {value!r}") from None
    if not isinstance(value, int | float):
        raise _Skip(field_name, f"expected a number, got a {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number) or abs(number) > MAX_COORD:
        raise _Skip(field_name, f"must be between -{MAX_COORD} and {MAX_COORD}, got {value}")
    return number


def _color(value: Any, field_name: str, palette: Mapping[str, RGBA | None]) -> RGBA | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _Skip(field_name, f"{value!r} is not a colour")
    try:
        return parse_color(value, palette)
    except ValueError as exc:
        raise _Skip(field_name, str(exc)) from None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "no", "0")
    if isinstance(value, list | tuple | dict):
        return len(value) > 0
    return bool(value)


def _points(raw: Any, context: dict[str, Any], bindings: dict[str, Any] | None) -> list[tuple[float, float]]:
    points = _value(raw, "points", context, bindings)
    if not isinstance(points, list | tuple):
        raise _Skip("points", f"expected a list of [x, y] pairs, got a {type(points).__name__}")
    out = []
    for i, point in enumerate(points):
        if isinstance(point, Mapping) and "x" in point and "y" in point:
            point = (point["x"], point["y"])
        if not isinstance(point, list | tuple) or len(point) != 2:
            raise _Skip("points", f"points[{i}] is not an [x, y] pair")
        out.append(
            (
                _number(_value(point[0], "points", context, bindings), "points"),
                _number(_value(point[1], "points", context, bindings), "points"),
            )
        )
    if len(out) < 3:
        raise _Skip("points", f"a polygon needs at least 3 points, got {len(out)}")
    return out


def _resolve_shape(
    shape: Any, context: dict[str, Any], bindings: dict[str, Any] | None, palette: Mapping[str, RGBA | None]
) -> ResolvedShape | None:
    """The concrete shape, or ``None`` when its ``if`` is falsy. Raises :class:`_Skip`."""
    if shape.if_ is not None and not _truthy(_value(shape.if_, "if", context, bindings)):
        return None
    values: dict[str, Any] = {}
    for attr in type(shape).model_fields:
        if attr in _CONTROL_FIELDS:
            continue
        name = attr.rstrip("_")
        raw = getattr(shape, attr)
        if name == "points":
            values[name] = _points(raw, context, bindings)
        elif name in _NUMBER_FIELDS:
            values[name] = None if raw is None else _number(_value(raw, name, context, bindings), name)
        elif name in _COLOR_FIELDS:
            values[name] = _color(_value(raw, name, context, bindings), name, palette)
        else:  # text, font
            value = _value(raw, name, context, bindings)
            values[name] = value if isinstance(value, str) else value_to_text(value)
    width = values.get("width")
    if shape.type == "line" and not 1 <= width <= MAX_LINE_WIDTH:
        raise _Skip("width", f"must be between 1 and {MAX_LINE_WIDTH}, got {width:g}")
    return ResolvedShape(shape.type, values)


def _bound_item(item: Any, index: int) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return {"value": item, **item, "index": index}
    return {"index": index, "value": item}


def resolve_content(
    content: CanvasContent, context: dict[str, Any], canvas_id: str = ""
) -> tuple[ResolvedContent, list[CanvasIssue]]:
    """Resolve stored (or source-supplied) *content*; see the module docstring."""
    issues: list[CanvasIssue] = []
    palette = {key: parse_color(value) for key, value in content.palette.items()}

    background = None
    try:
        background = _color(_value(content.background, "background", context, None), "background", palette)
    except _Skip as skip:
        issues.append(CanvasIssue(canvas_id, "background", skip.message))

    shapes: list[ResolvedShape] = []
    capped = False
    for i, shape in enumerate(content.shapes):
        if capped:
            break
        if shape.foreach is None:
            runs: list[dict[str, Any] | None] = [None]
        else:
            try:
                items = _value(shape.foreach, "foreach", context, None)
            except _Skip as skip:
                issues.append(CanvasIssue(canvas_id, f"shapes[{i}].foreach", skip.message))
                continue
            if not isinstance(items, list | tuple):
                issues.append(
                    CanvasIssue(canvas_id, f"shapes[{i}].foreach", f"must yield a list, got a {type(items).__name__}")
                )
                continue
            name = shape.as_ or "item"
            runs = [{name: _bound_item(item, n)} for n, item in enumerate(items)]
        for n, bindings in enumerate(runs):
            if len(shapes) >= MAX_EXPANDED_SHAPES:
                issues.append(
                    CanvasIssue(
                        canvas_id,
                        f"shapes[{i}]",
                        f"a canvas draws at most {MAX_EXPANDED_SHAPES} shapes after foreach; the rest were skipped",
                    )
                )
                capped = True
                break
            try:
                resolved = _resolve_shape(shape, context, bindings, palette)
            except _Skip as skip:
                prefix = f"item {n}: " if bindings is not None else ""
                issues.append(CanvasIssue(canvas_id, f"shapes[{i}].{skip.field_name}", prefix + skip.message))
                continue
            if resolved is not None:
                shapes.append(resolved)

    return (
        ResolvedContent(
            size=content.size,
            background=background,
            palette=palette,
            shapes=tuple(shapes),
            pixels=tuple(content.pixels),
        ),
        issues,
    )


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        loc = ".".join(str(p) for p in error["loc"])
        parts.append(f"{loc}: {error['msg']}" if loc else error["msg"])
    return "; ".join(parts)


def _source_content(canvas: Canvas, context: dict[str, Any]) -> tuple[CanvasContent | None, str | None]:
    """The content *canvas.source* yields, or ``(None, why)``."""
    try:
        value = _value(canvas.source, "source", context, None)
    except _Skip as skip:
        return None, skip.message
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None, "source must yield a content object; it yielded text that is not JSON"
    if not isinstance(value, Mapping):
        return None, f"source must yield a content object (a dict), got a {type(value).__name__}"
    try:
        return CanvasContent.model_validate(value), None
    except ValidationError as exc:
        return None, f"source content is invalid: {_validation_message(exc)}"


def resolve_canvas(canvas: Canvas, context: Mapping[str, Any]) -> tuple[ResolvedContent | None, list[CanvasIssue]]:
    """Resolve *canvas* against a template *context*.

    Returns ``(None, issues)`` when there is nothing to draw (no stored
    content and no usable source): the canvas is then transparent.
    """
    ctx = ensure_render_clock(dict(context))
    issues: list[CanvasIssue] = []
    content = canvas.content
    if canvas.source is not None:
        sourced, why = _source_content(canvas, ctx)
        if sourced is not None:
            content = sourced
        else:
            issues.append(CanvasIssue(canvas.id, "source", why or "source failed"))
    if content is None:
        return None, issues
    resolved, content_issues = resolve_content(content, ctx, canvas.id)
    return resolved, issues + content_issues
