"""Bounded historical engine computations, never evidence of output delivery."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal

from .issues import LayoutIssue

MAX_PAGES = 64
MAX_ISSUES = 128
MAX_TEXT = 512
MAX_PATH = 16
ComputationMode = Literal["page", "native", "silence", "held"]


@dataclass(frozen=True)
class LayoutComputation:
    """An owned immutable JSON snapshot. Readers always receive fresh objects."""

    encoded: str

    def to_json(self) -> dict[str, Any]:
        return json.loads(self.encoded)


class ComputationBuilder:
    """Collect one bounded render pass without retaining frames or plugin data."""

    def __init__(self, reference_id: str, mode: ComputationMode):
        self.pages: list[dict[str, Any]] = []
        self.issue_count = 0
        self.omitted_pages = 0
        self.omitted_issues = 0
        self.truncated_strings = 0
        self.reference_id = self._text(reference_id)
        self.mode = mode
        self.computed_at = time.time()

    def _text(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        if len(value) > MAX_TEXT:
            self.truncated_strings += 1
        return value[:MAX_TEXT]

    def add(self, page: Any, result: Any) -> None:
        issues = getattr(result, "layout_issues", ())
        issues = issues if isinstance(issues, (list, tuple)) else ()
        if len(self.pages) >= MAX_PAGES:
            self.omitted_pages += 1
            self.omitted_issues += len(issues)
            return
        retained = []
        remaining = MAX_ISSUES - self.issue_count
        self.omitted_issues += max(0, len(issues) - remaining)
        for issue in issues[:remaining]:
            if not isinstance(issue, LayoutIssue):
                continue
            retained.append(
                {
                    "path": [self._text(part) for part in issue.path[:MAX_PATH]],
                    "code": issue.code,
                    "severity": issue.severity,
                    "message": self._text(issue.message),
                    "omitted_path_segments": max(0, len(issue.path) - MAX_PATH),
                }
            )
        self.issue_count += len(retained)
        raw = getattr(result, "raw", None)
        surface = raw.get("surface") if isinstance(raw, dict) else None
        safe_surface = None
        if isinstance(surface, dict) and surface.get("kind") in ("cells", "pixels"):
            safe_surface = {"kind": surface["kind"]}
            for key in ("rows", "cols") if surface["kind"] == "cells" else ("width", "height"):
                value = surface.get(key)
                if type(value) is int and 0 < value <= 4096:
                    safe_surface[key] = value
        self.pages.append(
            {
                "page_id": self._text(getattr(page, "id", None)),
                "revision": self._text(getattr(page, "revision", None)),
                "available": getattr(result, "available", False) is True,
                "error": self._text(getattr(result, "error", None)),
                "surface": safe_surface,
                "issues": retained,
            }
        )

    def snapshot(self, *, complete: bool) -> LayoutComputation:
        return LayoutComputation(
            json.dumps(
                {
                    "scope": "engine_computation",
                    "mode": self.mode,
                    "reference_id": self.reference_id,
                    "computed_at": self.computed_at,
                    "complete": complete,
                    "pages": self.pages,
                    "omitted_pages": self.omitted_pages,
                    "omitted_issues": self.omitted_issues,
                    "truncated_strings": self.truncated_strings,
                },
                separators=(",", ":"),
            )
        )


def single_computation(page: Any, result: Any, mode: ComputationMode) -> LayoutComputation:
    builder = ComputationBuilder(getattr(page, "id", ""), mode)
    builder.add(page, result)
    return builder.snapshot(complete=True)
