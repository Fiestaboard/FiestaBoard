"""The character-grid cell layout: a flexible page at a board's one character size.

Split-flap and integer-only boards show these cells (spec section 5, step 6);
on pixel boards they lie hidden under the full-frame image, so board state,
readback and duplicate-frame checks still see the page's real text (spec
section 6). Phase 2 reuses :func:`layout_cell_grid` unchanged.

Everything is counted in tiles and rows:

- A text block's markup is one row when it fits ``cols``; otherwise its
  ``overflow`` applies: ``wrap`` (and ``shrink``, which cells cannot do) wraps
  by tiles with :func:`src.markup.wrap_line`, ``ellipsis`` keeps ``cols - 1``
  tiles and a ``.``. A ``\\n`` in the markup starts a new row.
- Fills are resolved by the template engine against ``cols`` on rows that
  fit; on a wrapped or cut row they take no room.
- Rows are aligned with spaces and padded to ``cols``.
- A spacer is one row; a canvas is none (``canvas_not_drawn``); gaps are none.
- A block wrapping past ``rows`` loses its extra rows (``dropped``); then
  whole blocks are dropped by priority, as the pixel stack does, and the rest
  placed by ``valign``.
- Block colours are not mapped to tiles here in Phase 1.

Issues are reported only when ``report_styles`` is true: under an LED frame
the cells are hidden and the frame has already reported its compromises.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.markup import count_tiles, split_rows, take_tiles, wrap_line

from .issues import LayoutIssue
from .stack import Rect, _place

if TYPE_CHECKING:
    from .style import ResolvedLayout, ResolvedStyle

__all__ = ["CellLayout", "layout_cell_grid"]

#: Expansion leaves fill ``i`` in a block's markup as this code point plus ``i`` (Task 6).
_FILL_SENTINEL_BASE = 0xE000
_FILL_SENTINEL_MAX = 0xF8FF


@dataclass(frozen=True)
class CellLayout:
    """A flexible page at a character grid: exactly ``rows`` markup lines, each at most ``cols`` tiles."""

    lines: tuple[str, ...]
    issues: tuple[LayoutIssue, ...]


def _is_sentinel(ch: str) -> bool:
    return _FILL_SENTINEL_BASE <= ord(ch) <= _FILL_SENTINEL_MAX


def _without_fills(line: str) -> str:
    return "".join(ch for ch in line if not _is_sentinel(ch))


def _fill_marker(spec: Any) -> str:
    """The template engine's own marker for a fill, as ``resolve_fill`` expects it."""
    if spec.pattern is None:
        return "\x00FILL_SPACE\x00"
    return f"\x00FILL_SPACE_REPEAT:{spec.pattern}\x00"


def _with_fill_markers(line: str, fills: Sequence[Any]) -> str:
    """``line`` with each fill sentinel turned back into its engine marker."""
    out = []
    for ch in line:
        index = ord(ch) - _FILL_SENTINEL_BASE
        out.append(_fill_marker(fills[index]) if _is_sentinel(ch) and index < len(fills) else ch)
    return "".join(out)


def _resolve_fill(engine: Any, line: str, cols: int) -> str:
    if engine is None:
        from src.templates.engine import get_template_engine

        engine = get_template_engine()
    resolve = getattr(engine, "resolve_fill", None)
    if resolve is not None:
        return resolve(line, width=cols)
    # Until the engine's public ``resolve_fill`` lands (Task 6), call what it will delegate to.
    return engine._process_fill_space(line, cols, extended_markup=True)


def _align(line: str, align: str, cols: int) -> str:
    """``line`` padded with spaces to ``cols`` tiles by ``align``."""
    pad = max(0, cols - count_tiles(line))
    if align == "center":
        left = pad // 2
        return " " * left + line + " " * (pad - left)
    if align == "right":
        return " " * pad + line
    return line + " " * pad


def _text_rows(
    block: Any,
    style: ResolvedStyle,
    cols: int,
    engine: Any,
    report: Callable[[str, str, str], None],
) -> list[str]:
    """A text block's rows at ``cols`` tiles, reporting what its ``overflow`` did."""
    fills = tuple(getattr(block, "fills", ()))
    markup = block.markup
    if not fills and not markup.strip():
        return []
    rows: list[str] = []
    wrapped = cut = False
    for line in split_rows(markup):
        bare = _without_fills(line)
        if count_tiles(bare) <= cols:
            rows.append(_resolve_fill(engine, _with_fill_markers(line, fills), cols) if bare != line else line)
        elif style.overflow == "ellipsis":
            rows.append(take_tiles(bare, cols - 1)[0] + ".")
            cut = True
        else:
            rows.extend(wrap_line(bare, cols))
            wrapped = True
    if wrapped:
        report("wrapped", "info", f"wrapped to {cols} characters")
        if style.overflow == "shrink":
            report("shrunk", "info", "this board has one character size; wrapped instead of shrinking")
    if cut:
        report("ellipsized", "warning", f"cut to {cols} characters")
    return rows


def _victim(entries: list[tuple[Any, list[str]]]) -> tuple[Any, list[str]]:
    """The block to drop next: unset priority first, then the highest number, later blocks first."""
    return max(entries, key=lambda e: (e[0].priority is None, e[0].priority or 0, e[0].index))


def layout_cell_grid(
    blocks: Sequence[Any],
    styles: Mapping[str, ResolvedStyle],
    rows: int,
    cols: int,
    *,
    layout: ResolvedLayout,
    report_styles: bool,
    engine: Any = None,
    path: tuple[str, ...] = (),
) -> CellLayout:
    """Lay ``blocks`` (expanded, in page order) out as ``rows`` lines of at most ``cols`` tiles.

    ``report_styles`` is true when these cells are what the board shows
    (split-flap or integer-only boards) and false under an LED frame; only
    when it is true are issues reported. ``engine`` resolves fills (default:
    the shared template engine). Issue paths start with ``path``.
    """
    if rows <= 0:
        return CellLayout((), ())
    issues: list[LayoutIssue] = []

    def reporter(block_id: str) -> Callable[[str, str, str], None]:
        def report(code: str, severity: str, message: str) -> None:
            if report_styles:
                issues.append(LayoutIssue((*path, "blocks", block_id), code, severity, f"block {block_id!r} {message}"))

        return report

    entries: list[tuple[Any, list[str]]] = []
    for block in blocks:
        report = reporter(block.id)
        if block.kind == "text":
            lines = _text_rows(block, styles[block.id], cols, engine, report)
            if len(lines) > rows:
                lines = lines[:rows]
                report("dropped", "warning", f"rows past {rows} dropped")
            if lines:
                entries.append((block, lines))
        elif block.kind == "spacer":
            entries.append((block, [""]))
        elif block.kind == "canvas":
            report("canvas_not_drawn", "warning", "is a canvas; this board shows characters only")

    while sum(len(lines) for _, lines in entries) > rows:
        victim = _victim(entries)
        entries.remove(victim)
        reporter(victim[0].id)("dropped", "warning", "does not fit; dropped (lowest priority first)")

    grid = [""] * rows
    heights = [len(lines) for _, lines in entries]
    ys = _place(heights, Rect(0, 0, cols, rows), 0, layout.valign) if entries else []
    for (block, lines), y in zip(entries, ys, strict=True):
        for i, line in enumerate(lines):
            grid[y + i] = _align(line, styles[block.id].align, cols)
    return CellLayout(tuple(row or " " * cols for row in grid), tuple(issues))
