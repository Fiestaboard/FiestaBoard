"""Layout issues: every compromise flexible layout makes, with the path it applies to.

A style value is a request; when a board cannot honour it, or a block does
not fit, layout still produces a frame and records a :class:`LayoutIssue`.
The ``path`` points into the page document (``("blocks", "b2", "style",
"size")``); a later ``regions`` layout kind prefixes ``("regions", "r1")``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

__all__ = [
    "BLOCK_ISSUE_CODES",
    "FIT_ISSUE_CODES",
    "ISSUE_CODES",
    "STYLE_ISSUE_CODES",
    "IssueSeverity",
    "LayoutIssue",
    "LayoutIssueModel",
]

IssueSeverity = Literal["info", "warning"]

#: A style request this board shows differently, or not at all.
STYLE_ISSUE_CODES = frozenset(
    {
        "font_unavailable",
        "size_rounded",
        "size_too_small",
        "size_ignored",
        "color_invalid",
        "color_dropped",
        "background_dropped",
        "case_unsupported",
        "overflow_unsupported",
        "style_unknown",
    }
)

#: A block or layout this build cannot lay out as written.
BLOCK_ISSUE_CODES = frozenset({"block_kind_unsupported", "layout_kind_unsupported", "if_failed"})

#: What fitting and stacking did to make the page fit the surface.
FIT_ISSUE_CODES = frozenset(
    {"wrapped", "shrunk", "ellipsized", "truncated", "dropped", "canvas", "canvas_not_drawn", "surface_too_small"}
)

#: Every issue code layout reports.
ISSUE_CODES = STYLE_ISSUE_CODES | BLOCK_ISSUE_CODES | FIT_ISSUE_CODES

_SEVERITIES = ("info", "warning")


@dataclass(frozen=True)
class LayoutIssue:
    """One compromise: where (``path``), what (``code``), how much it matters and a message."""

    path: tuple[str, ...]
    code: str
    severity: IssueSeverity
    message: str

    def __post_init__(self) -> None:
        if self.code not in ISSUE_CODES:
            raise ValueError(f"unknown layout issue code {self.code!r}")
        if self.severity not in _SEVERITIES:
            raise ValueError(f"unknown layout issue severity {self.severity!r}")

    def to_json(self) -> dict[str, Any]:
        """The response form: ``{"path": [...], "code", "severity", "message"}``."""
        return {"path": list(self.path), "code": self.code, "severity": self.severity, "message": self.message}


class LayoutIssueModel(BaseModel):
    """A :class:`LayoutIssue` in an API response."""

    path: list[str]
    code: str
    severity: IssueSeverity
    message: str
