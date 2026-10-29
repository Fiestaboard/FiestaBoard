"""Block expansion: a flexible page's blocks as markup and board tokens (spec section 5, step 1).

Each text block's text goes through the template engine's **expansion**
only (:meth:`~src.templates.engine.TemplateEngine.render`: variables,
formulas, filters, colours, icons, extended markup), never the grid render
(``render_lines``), which counts in tiles. Then:

- **Fills** (``{{fill_space}}``, ``{{fill_space_repeat:X}}``,
  ``{{filled:X}}``) are width-dependent. The engine leaves each as a marker;
  here it becomes one private-use sentinel character, ``U+E000 + i``, with
  its :class:`FillSpec`. Layout fills it later: in pixels on a frame
  (:mod:`src.layout.measure`), in tiles in the cell grid
  (:func:`markup_with_fills` and the engine's ``resolve_fill``).
- **``if``**: a block shows only while its formula is true. False hides it
  silently; a formula error hides it with an ``if_failed`` warning.
- **Case**: the block's resolved ``case``, or capitals on a board without
  lowercase, applied to the text and never to its markup.
- **Charset fallback**: tokens pass through the board's set exactly as
  :func:`src.outputs.cells.project_message` does, so the frame draws what the
  hidden cells hold (and ``matches_frame`` and readback agree with the pixels).

Unknown block kinds are skipped with ``block_kind_unsupported``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.canvas.evaluate import truthy
from src.led.charsets import CharsetLookup, charset_fallback
from src.markup import BoardToken, map_text_case, parse_line
from src.templates.expressions import FormulaError

from .issues import LayoutIssue

if TYPE_CHECKING:
    from src.pages.flexible import Block
    from src.pages.models import Page
    from src.templates.engine import TemplateEngine

    from .style import ResolvedStyle
    from .target import FlexTarget

__all__ = [
    "FILL_SENTINEL_BASE",
    "ExpandedBlock",
    "FillSpec",
    "expand_blocks",
    "fill_marker",
    "is_fill_sentinel",
    "markup_with_fills",
    "strip_fills",
    "with_fills",
]

#: Fill ``i`` of a block is left in its markup as this code point plus ``i``.
FILL_SENTINEL_BASE = 0xE000
#: The last code point of the private-use area the sentinels are drawn from.
_FILL_SENTINEL_MAX = 0xF8FF

#: The character set a board with no display draws (the flagship's flaps).
_FLAP_CHARSET = "vestaboard_v1"

#: The engine's fill markers, as :meth:`TemplateEngine.render` leaves them.
_ENGINE_FILL = re.compile(r"\x00FILL_SPACE(?:_REPEAT:(.+?))?\x00")
#: An ``if`` written as one ``{{…}}``: its body is the formula.
_WRAPPED = re.compile(r"\s*\{\{(.*)\}\}\s*", re.DOTALL)


@dataclass(frozen=True)
class FillSpec:
    """One width-dependent fill: ``pattern`` is repeated to fill, ``None`` is blank space."""

    pattern: str | None


@dataclass(frozen=True)
class ExpandedBlock:
    """A block ready to lay out.

    ``index`` is its position in the page (for drop order), ``markup`` its
    expanded text with fill ``i`` as the sentinel ``U+E000 + i`` and
    ``fills`` their specs; ``tokens`` the cells it draws on this board (case
    and charset fallback applied; a sentinel stays a ``char`` token whose
    value is the sentinel). A spacer or canvas has no markup or tokens.
    """

    id: str
    kind: str
    index: int
    priority: int | None
    markup: str
    fills: tuple[FillSpec, ...]
    tokens: tuple[BoardToken, ...]
    block: Block


def is_fill_sentinel(ch: str) -> bool:
    """Whether ``ch`` is a fill sentinel."""
    return len(ch) == 1 and FILL_SENTINEL_BASE <= ord(ch) <= _FILL_SENTINEL_MAX


def strip_fills(text: str) -> str:
    """``text`` without its fill sentinels (fills that take no room)."""
    return "".join(ch for ch in text if not is_fill_sentinel(ch))


def fill_marker(spec: FillSpec) -> str:
    """The template engine's own marker for ``spec``, as its ``resolve_fill`` expects it."""
    if spec.pattern is None:
        return "\x00FILL_SPACE\x00"
    return f"\x00FILL_SPACE_REPEAT:{spec.pattern}\x00"


def with_fills(text: str, fills: tuple[FillSpec, ...], text_fill: Callable[[FillSpec], str]) -> str:
    """``text`` with each fill sentinel replaced by ``text_fill(its spec)``."""
    out = []
    for ch in text:
        index = ord(ch) - FILL_SENTINEL_BASE if is_fill_sentinel(ch) else -1
        out.append(text_fill(fills[index]) if 0 <= index < len(fills) else ch)
    return "".join(out)


def markup_with_fills(block: ExpandedBlock, text_fill: Callable[[FillSpec], str]) -> str:
    """``block``'s markup with every fill sentinel replaced by ``text_fill(its spec)``.

    With :func:`fill_marker` this restores the engine's markers, for
    ``TemplateEngine.resolve_fill`` to fill at a width in tiles.
    """
    return with_fills(block.markup, block.fills, text_fill)


def _sentinels(rendered: str) -> tuple[str, tuple[FillSpec, ...]]:
    """``rendered`` with each engine fill marker replaced by the next sentinel."""
    fills: list[FillSpec] = []

    def sentinel(match: re.Match[str]) -> str:
        fills.append(FillSpec(match.group(1)))
        return chr(FILL_SENTINEL_BASE + len(fills) - 1)

    return _ENGINE_FILL.sub(sentinel, rendered), tuple(fills)


def _case_fn(case: str, mixed_case: bool) -> Callable[[str], str] | None:
    if case == "upper" or not mixed_case:
        return str.upper
    if case == "lower":
        return str.lower
    return None


def _charset(target: FlexTarget) -> Any:
    display = target.display
    if display is not None and display.character_set:
        return display.character_set
    return _FLAP_CHARSET


def _tokens(markup: str, look: CharsetLookup) -> tuple[BoardToken, ...]:
    """The cells ``markup`` draws with ``look``'s set; sentinels and newlines are kept as written."""
    out: list[BoardToken] = []
    for token in parse_line(markup, extended_markup=True, preserve_case=True):
        if token.type == "char" and token.icon is None and (is_fill_sentinel(token.value) or token.value == "\n"):
            out.append(token)
        else:
            out.append(charset_fallback(look, token))
    return tuple(out)


def _formula(text: str) -> str:
    """The formula body of an ``if``: ``{{= x }}`` / ``{{x}}`` / ``x`` -> ``x``."""
    wrapped = _WRAPPED.fullmatch(text)
    body = wrapped.group(1) if wrapped else text
    body = body.strip()
    return body[1:].strip() if body.startswith("=") else body


def _shows(block: Block, context: Mapping[str, Any], engine: Any) -> tuple[bool, LayoutIssue | None]:
    """Whether ``block``'s ``if`` lets it show, and the issue when the formula fails."""
    if block.if_ is None or not block.if_.strip():
        return True, None
    try:
        value = engine.evaluate_expression(_formula(block.if_), dict(context))
    except FormulaError as exc:
        return False, LayoutIssue(
            ("blocks", block.id, "if"), "if_failed", "warning", f"block {block.id!r} if failed ({exc}); hidden"
        )
    return truthy(value), None


def expand_blocks(
    page: Page,
    target: FlexTarget,
    context: Mapping[str, Any],
    styles: Mapping[str, ResolvedStyle],
    *,
    engine: TemplateEngine | None = None,
) -> tuple[list[ExpandedBlock], list[LayoutIssue]]:
    """``page``'s blocks expanded for ``target`` against plugin data ``context``.

    Returns the blocks that show, in page order, and the issues met.
    ``styles`` maps block id to its resolved style (for ``case``).
    ``engine`` expands text and evaluates ``if`` (default: the shared
    template engine).
    """
    from src.pages.flexible import KNOWN_BLOCK_KINDS  # src.pages imports this package

    if engine is None:
        from src.templates.engine import get_template_engine

        engine = get_template_engine()
    look = CharsetLookup(_charset(target))
    shown: list[ExpandedBlock] = []
    issues: list[LayoutIssue] = []
    for index, block in enumerate(page.blocks or []):
        if block.kind not in KNOWN_BLOCK_KINDS:
            issues.append(
                LayoutIssue(
                    ("blocks", block.id),
                    "block_kind_unsupported",
                    "warning",
                    f"block kind {block.kind!r} is not drawn by this build; skipped",
                )
            )
            continue
        shows, issue = _shows(block, context, engine)
        if issue is not None:
            issues.append(issue)
        if not shows:
            continue
        markup, fills, tokens = "", (), ()
        if block.kind == "text" and block.text:
            markup, fills = _sentinels(engine.render(block.text, dict(context), extended_markup=True))
            style = styles.get(block.id)
            case = _case_fn(style.case if style is not None else "as-is", target.mixed_case)
            if case is not None:
                markup = map_text_case(markup, case)
            tokens = _tokens(markup, look)
        shown.append(
            ExpandedBlock(
                id=block.id,
                kind=block.kind,
                index=index,
                priority=block.priority,
                markup=markup,
                fills=fills,
                tokens=tokens,
                block=block,
            )
        )
    return shown, issues
