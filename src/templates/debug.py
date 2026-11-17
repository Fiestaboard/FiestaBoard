"""Request-local H7 inspection; formula results are shared by every render pass."""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from uuid import uuid4

from .diagnostics import FormulaReport, RenderReport
from .expressions import Evaluation, evaluate_detailed, find_formulas
from .source_map import Source, SourceTracker, concat, origin_at, sub
from .trace import FormulaTrace

_STANDALONE_MARKUP = re.compile(
    r"(?<!\{)\{(?:6[3-9]|7[01]|red|orange|yellow|green|blue|violet|purple|white|black|filled|icon:[a-z0-9_-]{1,16})\}",
    re.IGNORECASE,
)

_ACTIVE: ContextVar[RenderDebug | None] = ContextVar("render_debug", default=None)


def active_debug() -> RenderDebug | None:
    return _ACTIVE.get()


def authored(value: str, original: str, kind: str) -> str:
    """A replacement inherits its whole authored atom (or its enclosing atom)."""
    current = active_debug()
    if current is None or not current.want_map or not original:
        return value
    first = origin_at(original, 0)
    last = origin_at(original, len(original) - 1)
    if first is None:
        return value
    if first.kind == "literal" and last is not None and first.line == last.line:
        first = Source(first.line, first.start, last.end, kind)
    return current.tracker.mapped(value, first)


class RenderDebug:
    """One render only; never stored on the shared TemplateEngine singleton."""

    def __init__(self, *, trace=None, source_map: bool = False):
        self.selected = None if trace is None else (trace.line, trace.start)
        self.want_map = source_map
        self.tracker = SourceTracker()
        self.trace = None
        self.source_map = None
        self._values: dict[str, str] = {}
        self._original: dict[str, str] = {}
        self._pattern = None
        self._prepared = False

    @contextmanager
    def activate(self):
        token = _ACTIVE.set(self)
        try:
            yield
        finally:
            _ACTIVE.reset(token)

    def prepare(self, lines: list[str], context: dict, report: RenderReport, limit: int) -> list[str]:
        """Evaluate each authored occurrence once, in the existing H5 order.

        Opaque per-request placeholders retain expression-phase insertion:
        normalization must not interpret a formula's output before evaluation.
        Their identities do not depend on provenance remaining below its cap.
        """
        if self._prepared:
            return lines
        self._prepared = True
        nonce = uuid4().hex
        # An authored string can never collide, even when uuid4 is stubbed.
        while any(f"\x00H7:{nonce}:" in line for line in lines):
            nonce += "x"
        prepared = []
        for number, line in enumerate(lines, 1):
            tracked = self.tracker.source(line, line=number) if self.want_map else line
            if self.want_map:
                from src.markup import resolve_icon_name

                def mark(match, tracked=tracked):
                    atom = tracked[match.start() : match.end()]
                    if match.group().lower().startswith("{icon:") and resolve_icon_name(match.group()[6:-1]) is None:
                        return atom
                    return authored(str(atom), atom, "markup")

                tracked = sub(_STANDALONE_MARKUP, mark, tracked)
            parts = []
            cursor = 0
            for start, end, body in find_formulas(line):
                recorder = FormulaTrace() if (number, start) == self.selected else None
                result = evaluate_detailed(body, context, trace=recorder) if body else Evaluation("")
                entry = FormulaReport(
                    line=number,
                    start=start,
                    end=end,
                    source=body,
                    value=result.value[:limit],
                    value_truncated=len(result.value) > limit,
                    error=result.error,
                    error_at=result.error_at,
                    message=result.message,
                )
                report.formulas.append(entry)
                if recorder is not None:
                    self.trace = {**asdict(entry), **recorder.to_json()}
                marker = f"\x00H7:{nonce}:{len(self._values)}\x00"
                self._original[marker] = tracked[start:end]
                source = Source(number, start, end, "formula")
                self._values[marker] = self.tracker.mapped(result.value, source) if self.want_map else result.value
                parts.extend((tracked[cursor:start], marker))
                cursor = end
            parts.append(tracked[cursor:])
            prepared.append(concat(parts))
        if self._values:
            self._pattern = re.compile(r"\x00H7:" + re.escape(nonce) + r":\d+\x00")
        return prepared

    def expand(self, text: str) -> str:
        if self._pattern is None:
            return text
        return sub(self._pattern, lambda match: self._values.get(match.group(), match.group()), text)

    def restore_protected(self, text: str) -> str:
        """A depth-limited authoring form keeps formulas as literal source."""
        if self._pattern is None:
            return text
        return sub(self._pattern, lambda match: self._original.get(match.group(), match.group()), text)

    def finish(self, rendered: str, *, rows: int, cols: int, extended_markup: bool) -> None:
        if self.want_map:
            self.source_map = self.tracker.to_json(rendered, rows=rows, cols=cols, extended_markup=extended_markup)

    def to_json(self) -> dict:
        return {
            "trace": self.trace,
            "source_map": self.source_map,
            "source_map_status": "not_requested"
            if not self.want_map
            else "limit"
            if self.source_map is None
            else "complete",
        }
