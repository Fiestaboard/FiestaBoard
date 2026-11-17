"""Bounded execution events for one formula, separate from its rendered value.

The evaluator reserves a slot before visiting children and completes that
slot on exit. Once full, recording stops while evaluation keeps its normal
work and time limits. Values are previews, never copies of plugin objects.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

MAX_TRACE_EVENTS = 256
MAX_TRACE_TEXT = 128


def _preview(value: Any, scalar_text: Callable[[Any], str]) -> tuple[str, bool]:
    """Make a bounded preview without traversing collections or calling repr."""
    if isinstance(value, str):
        return value[:MAX_TRACE_TEXT], len(value) > MAX_TRACE_TEXT
    if isinstance(value, list):
        return f"list({len(value)})", False
    if isinstance(value, dict):
        return f"dict({len(value)})", False
    # Converting an arbitrarily large plugin integer to decimal could itself
    # be costly (or exceed Python's digit limit). Even 512 bits is over 128
    # decimal digits, so larger integers need only a constant-size summary.
    if type(value) is int and value.bit_length() > 512:
        return "int(large)", True
    if value is None or type(value) in (bool, int, float, date, datetime):
        try:
            text = scalar_text(value)
        except (ValueError, OverflowError):
            # Non-finite floats may be intermediate values even when the
            # formula never tries to render them. The trace must not do so.
            text = str(value)
        return text[:MAX_TRACE_TEXT], len(text) > MAX_TRACE_TEXT
    return type(value).__name__[:MAX_TRACE_TEXT], False


@dataclass
class FormulaTrace:
    """One evaluation's events, in entry order, with bounded value previews.

    ``truncated`` means additional executions were omitted, independently of
    any individual event's ``value_truncated``. IDs are zero-based and parents
    are reserved first, so every parent remains present even at the cap.
    """

    events: list[dict[str, Any]] = field(default_factory=list, init=False)
    truncated: bool = field(default=False, init=False)
    _source: str = field(default="", init=False, repr=False)
    _stack: list[int] = field(default_factory=list, init=False, repr=False)

    def _start(self, source: str) -> None:
        self.events.clear()
        self.truncated = False
        self._stack.clear()
        self._source = source

    def _enter(self, kind: str, label: str | None, start: int, end: int) -> int | None:
        if len(self.events) >= MAX_TRACE_EVENTS:
            self.truncated = True
            return None
        event_id = len(self.events)
        self.events.append(
            {
                "id": event_id,
                "parent": self._stack[-1] if self._stack else None,
                "kind": kind,
                "label": self._source[start : min(end, start + MAX_TRACE_TEXT)]
                if label is None
                else label[:MAX_TRACE_TEXT],
                "start": start,
                "end": end,
                "value": "",
                "value_truncated": False,
                "error": None,
            }
        )
        self._stack.append(event_id)
        return event_id

    def _finish(
        self, event_id: int | None, value: Any, scalar_text: Callable[[Any], str], *, error: str | None = None
    ) -> None:
        if event_id is None:
            return
        try:
            text, truncated = _preview(error if error is not None else value, scalar_text)
            self.events[event_id].update(value=text, value_truncated=truncated, error=error)
        finally:
            self._stack.pop()

    def to_json(self) -> dict[str, Any]:
        """Return a snapshot containing only bounded, JSON-safe scalar fields."""
        return {"events": [dict(event) for event in self.events], "truncated": self.truncated}
