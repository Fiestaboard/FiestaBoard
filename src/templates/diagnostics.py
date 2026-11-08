"""What a render did, for the editor's inspector (H5).

:meth:`TemplateEngine.render_lines` fills a :class:`RenderReport` when one
is passed: every ``{{= … }}`` formula with the value the board shows, and
every template line with the rows it wanted, the rows that landed, and why
the rest did not. The engine already decides all of this (its overflow
budget, the ``FOREACH`` split, the board's row count); the report keeps the
decision instead of discarding it, so the editor never re-derives it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

#: Why a template line did not show every row it wanted.
#: ``stopped_by_line``: a non-empty, non-wrap row below hard-stopped it
#: (``clip_line``); ``board_end``: the board ran out of rows; ``covered``: an
#: earlier line's overflow took its row (``clip_line``); ``beyond_board``: the
#: line is past the board's last row.
Clip = Literal["stopped_by_line", "board_end", "covered", "beyond_board"]


@dataclass
class FormulaReport:
    """One ``{{= … }}`` formula: where it is, and what it evaluated to."""

    line: int
    start: int
    end: int
    source: str
    value: str
    error: str | None = None
    error_at: int | None = None
    message: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LineReport:
    """What one template line produced on the board."""

    line: int
    first_row: int | None
    rows_wanted: int
    rows_shown: int
    clip: Clip | None = None
    clip_line: int | None = None
    widest: int = 0
    cut: bool = False
    hidden: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RenderReport:
    """Filled by a render: ``formulas`` in template order, ``lines`` one per
    template line (``lines[i]`` is line ``i + 1``), or ``None`` when the
    render has no rows to report (a page whose text flows around canvases)."""

    formulas: list[FormulaReport] = field(default_factory=list)
    lines: list[LineReport] | None = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "formulas": [formula.to_json() for formula in self.formulas],
            "lines": None if self.lines is None else [line.to_json() for line in self.lines],
        }
