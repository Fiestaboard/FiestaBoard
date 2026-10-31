"""Measure and fit text in pixels (spec section 5, steps 3 and 4).

A fitted line is a sequence of **items**: a :class:`Glyph` (one cell: a
character, icon or tile, ``advance`` pixels from its left edge to the next)
or a :class:`Gap` (extra blank pixels). A line's width is its cells times the
advance less the trailing gutter, plus its gaps (:func:`measure`).

:func:`fit_text` fits one expanded text block to a width:

- A ``\\n`` in the markup starts a new line.
- ``size: fit`` takes the largest ladder size whose widest line fits the
  width and whose height fits the rect, else the smallest.
- A line too wide follows the block's ``overflow``: ``wrap`` breaks at blanks,
  then mid-word at a glyph boundary (each line holds at least one glyph, so
  wrapping always ends); ``shrink`` steps down the family's ladder (scales
  and faces), and past the smallest size ellipsises; ``ellipsis`` keeps the
  longest prefix that fits with the ellipsis glyph (``…`` when the face has
  it, else ``.``), trailing blanks trimmed.
- More lines than the height holds are cut to what fits, the last one
  ellipsised (``truncated``).
- Fills take no room while wrapping; then, per line, blank fills become
  gaps sharing the spare pixels (extra pixels to earlier fills) and pattern
  fills repeat their pattern (a colour name repeats its tile) as many whole
  cells as fit. A fill with no room is removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.board_chars import BoardChars
from src.markup import BoardToken

from .expand import FILL_SENTINEL_BASE, FillSpec, is_fill_sentinel
from .fonts import FONT_FAMILIES, FontFamily, SizedFace, size_ladder
from .issues import LayoutIssue

if TYPE_CHECKING:
    from .expand import ExpandedBlock
    from .style import ResolvedStyle

__all__ = ["FittedText", "Gap", "Glyph", "LineItem", "fit_text", "measure"]


@dataclass(frozen=True)
class Glyph:
    """One cell of a line: a character, icon or tile."""

    token: BoardToken


@dataclass(frozen=True)
class Gap:
    """``px`` blank pixels in a line (a resolved blank fill)."""

    px: int


@dataclass(frozen=True)
class _Fill:
    """An unresolved fill: no width until its line is known. ``token`` carries its span colours."""

    spec: FillSpec
    token: BoardToken


LineItem = Glyph | Gap


@dataclass(frozen=True)
class FittedText:
    """A text block fitted to a width: its lines, the size they draw at and what fitting did.

    ``width`` is the widest line, ``height`` the lines with their line gaps.
    """

    lines: tuple[tuple[LineItem, ...], ...]
    sized: SizedFace
    width: int
    height: int
    issues: tuple[LayoutIssue, ...]


def measure(items: Any, sized: SizedFace) -> int:
    """The pixel width of a line of items drawn in ``sized`` (unresolved fills take none)."""
    cells = 0
    gaps = 0
    for item in items:
        if isinstance(item, Gap):
            gaps += item.px
        elif isinstance(item, Glyph):
            cells += 1
    return (cells * sized.advance - sized.gutter if cells else 0) + gaps


def _is_blank(item: Any) -> bool:
    if not isinstance(item, Glyph):
        return False
    token = item.token
    return token.type == "char" and token.icon is None and token.background is None and token.value.isspace()


def _rstrip(items: list[Any]) -> list[Any]:
    end = len(items)
    while end and _is_blank(items[end - 1]):
        end -= 1
    return items[:end]


def _lstrip(items: list[Any]) -> list[Any]:
    start = 0
    while start < len(items) and _is_blank(items[start]):
        start += 1
    return items[start:]


def _paragraphs(block: ExpandedBlock) -> list[list[Any]]:
    """The block's tokens as items, split at each ``\\n``."""
    paragraphs: list[list[Any]] = [[]]
    for token in block.tokens:
        if token.type == "char" and token.icon is None and token.value == "\n":
            paragraphs.append([])
        elif token.type == "char" and is_fill_sentinel(token.value):
            index = ord(token.value) - FILL_SENTINEL_BASE
            if index < len(block.fills):
                paragraphs[-1].append(_Fill(block.fills[index], token))
        else:
            paragraphs[-1].append(Glyph(token))
    return paragraphs


def _words(items: list[Any]) -> list[tuple[list[Any], list[Any]]]:
    """``items`` as ``(blanks before, word)`` pairs; a trailing run of blanks is a pair with no word."""
    pairs: list[tuple[list[Any], list[Any]]] = []
    blanks: list[Any] = []
    word: list[Any] = []
    for item in items:
        if _is_blank(item):
            if word:
                pairs.append((blanks, word))
                blanks, word = [], []
            blanks.append(item)
        else:
            word.append(item)
    if word or blanks:
        pairs.append((blanks, word))
    return pairs


def _break_word(word: list[Any], width: int, sized: SizedFace) -> tuple[list[Any], list[Any]]:
    """The longest head of ``word`` that fits ``width`` (at least one glyph), and the rest."""
    glyphs = 0
    cut = 0
    for i, item in enumerate(word):
        if isinstance(item, Glyph):
            if glyphs and measure(word[: i + 1], sized) > width:
                break
            glyphs += 1
        cut = i + 1
    return word[:cut], word[cut:]


def _has_glyph(items: list[Any]) -> bool:
    return any(isinstance(i, Glyph) for i in items)


def _wrap(items: list[Any], width: int, sized: SizedFace) -> list[list[Any]]:
    """Greedy word wrap of one paragraph; a continuation line drops its leading blanks."""
    lines: list[list[Any]] = []
    current: list[Any] = []
    for blanks, word in _words(items):
        candidate = current + blanks + word
        if measure(candidate, sized) <= width:
            current = candidate
            continue
        if _has_glyph(current):
            lines.append(_rstrip(current))
            rest = list(word)
        else:
            rest = candidate if not lines else _lstrip(candidate)
        while measure(rest, sized) > width and sum(isinstance(i, Glyph) for i in rest) > 1:
            head, rest = _break_word(rest, width, sized)
            lines.append(head)
        current = rest
    if _has_glyph(current) or any(isinstance(i, _Fill) for i in current):
        lines.append(_rstrip(current))
    return lines


def _ellipsis_glyph(sized: SizedFace, like: Any) -> Glyph:
    value = "…" if "…" in sized.face.led_font.glyphs else "."
    token = like.token if isinstance(like, Glyph) else None
    if token is None:
        return Glyph(BoardToken("char", value=value))
    return Glyph(BoardToken("char", value=value, color=token.color, background=token.background))


def _ellipsize(items: list[Any], width: int, sized: SizedFace, *, force: bool = False) -> list[Any]:
    """The longest prefix of ``items`` that fits ``width`` with the ellipsis glyph after it.

    Without ``force``, items that already fit are kept whole.
    """
    if not force and measure(items, sized) <= width:
        return items
    prefix = list(items)
    while True:
        kept = _rstrip(prefix)
        glyphs = [i for i in kept if isinstance(i, Glyph)]
        line = [*kept, _ellipsis_glyph(sized, glyphs[-1] if glyphs else None)]
        if measure(line, sized) <= width:
            return line
        if not prefix:
            return []
        prefix = prefix[:-1]


def _pattern_tokens(spec: FillSpec, token: BoardToken, count: int) -> list[Glyph]:
    pattern = spec.pattern or " "
    code = BoardChars.get_color_code(pattern)
    if code is not None:
        tile = BoardToken("color", code=str(code), background=token.background)
        return [Glyph(tile)] * count
    return [
        Glyph(BoardToken("char", value=pattern[i % len(pattern)], color=token.color, background=token.background))
        for i in range(count)
    ]


def _resolve_fills(line: list[Any], width: int, sized: SizedFace) -> tuple[LineItem, ...]:
    """``line`` with its fills turned into gaps and pattern glyphs that fill ``width``."""
    fills = [item for item in line if isinstance(item, _Fill)]
    rest = [item for item in line if not isinstance(item, _Fill)]
    if not fills:
        return tuple(rest)
    spare = width - measure(rest, sized)
    if spare <= 0:
        return tuple(rest)
    # With no glyph yet, the first glyph a fill adds costs its advance less one gutter.
    lead = 0 if any(isinstance(i, Glyph) for i in rest) else sized.gutter
    share, extra = divmod(spare, len(fills))
    out: list[LineItem] = []
    k = 0
    for item in line:
        if not isinstance(item, _Fill):
            out.append(item)
            continue
        px = share + (1 if k < extra else 0)
        k += 1
        if item.spec.pattern is None:
            if px > 0:
                out.append(Gap(px))
            continue
        count = (px + lead) // sized.advance
        if count > 0:
            lead = 0
            out.extend(_pattern_tokens(item.spec, item.token, count))
    return tuple(out)


def _widest(paragraphs: list[list[Any]], sized: SizedFace) -> int:
    return max((measure(p, sized) for p in paragraphs), default=0)


def _height(lines: int, sized: SizedFace) -> int:
    return lines * sized.height + max(0, lines - 1) * sized.line_gap


def fit_text(
    block: ExpandedBlock,
    style: ResolvedStyle,
    width: int,
    max_height: int,
    *,
    family: FontFamily | str,
    path: tuple[str, ...],
) -> FittedText:
    """Fit ``block``'s text to ``width`` pixels and at most ``max_height`` tall.

    ``style`` gives the size (``sized``, or ``fit``) and ``overflow``;
    ``family`` the ladder ``fit`` and ``shrink`` step along. Issues carry
    ``path``.
    """
    fam = FONT_FAMILIES[family] if isinstance(family, str) else family
    ladder = size_ladder(fam)
    paragraphs = _paragraphs(block)
    if not any(paragraphs):
        return FittedText((), style.sized or ladder[0], 0, 0, ())
    sized = style.sized or ladder[0]
    issues: list[LayoutIssue] = []

    def report(code: str, severity: str, message: str) -> None:
        issues.append(LayoutIssue(path, code, severity, f"block {block.id!r} {message}"))

    if style.fit:
        fitting = [s for s in ladder if s.height <= max_height and _widest(paragraphs, s) <= width]
        sized = fitting[-1] if fitting else ladder[0]

    lines: list[list[Any]] = [list(p) for p in paragraphs]
    if _widest(paragraphs, sized) > width:
        if style.overflow == "wrap":
            lines = [line for p in paragraphs for line in (_wrap(p, width, sized) or [[]])]
            report("wrapped", "info", f"wrapped to {width}px")
        elif style.overflow == "shrink":
            smaller = [s for s in ladder if s.height < sized.height and _widest(paragraphs, s) <= width]
            if smaller:
                sized = smaller[-1]
                report("shrunk", "info", f"shrunk to {sized.height}px to fit {width}px")
            else:
                sized = ladder[0]
                lines = [_ellipsize(p, width, sized) for p in paragraphs]
                report("ellipsized", "warning", f"too wide even at {sized.height}px; cut to {width}px")
        else:
            lines = [_ellipsize(p, width, sized) for p in paragraphs]
            report("ellipsized", "warning", f"cut to {width}px")

    max_lines = (max_height + sized.line_gap) // (sized.height + sized.line_gap)
    if 0 < max_lines < len(lines):
        blank = Glyph(BoardToken("char", value=" "))
        last = _ellipsize([*lines[max_lines - 1], blank, *lines[max_lines]], width, sized, force=True)
        lines = [*lines[: max_lines - 1], last]
        report("truncated", "warning", f"{max_lines} line(s) fit; the rest is cut")

    fitted = tuple(_resolve_fills(line, width, sized) for line in lines)
    return FittedText(
        lines=fitted,
        sized=sized,
        width=max((measure(line, sized) for line in fitted), default=0),
        height=_height(len(fitted), sized),
        issues=tuple(issues),
    )
