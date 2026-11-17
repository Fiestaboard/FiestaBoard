"""Bounded, request-local provenance carried alongside rendered text.

``MappedText`` remains a string for the existing renderer, but stores compact
runs rather than one origin object per character. Use :func:`concat` and
:func:`sub` in place of string joins, f-strings and regex substitutions: those
builtins otherwise discard string-subclass metadata. Literal runs are affine;
substitutions have one constant origin, however long their value becomes.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

TRACKING_LIMIT = 262_144
SourceKind = Literal["literal", "variable", "formula", "fill", "markup"]


@dataclass(frozen=True)
class Source:
    line: int
    start: int
    end: int
    kind: SourceKind


@dataclass(frozen=True)
class _Run:
    start: int
    end: int
    source: Source
    affine: bool = False


class SourceTracker:
    """One render's cumulative bookkeeping budget and final source table.

    Every newly tracked intermediate string charges its length before its
    runs are built. Parsing mapped markup also reserves its input length.
    Exhaustion drops bookkeeping, never the text or the render itself.
    """

    def __init__(self, limit: int = TRACKING_LIMIT):
        self.limit = limit
        self.used = 0
        self.limited = False

    def reserve(self, length: int) -> bool:
        if self.limited:
            return False
        if length > self.limit - self.used:
            self.limited = True
            return False
        self.used += length
        return True

    def source(self, text: str, *, line: int, offset: int = 0) -> str:
        """Seed literal text; each drawn code point retains its own offset."""
        if not self.reserve(len(text)):
            return str(text)
        origin = Source(line, offset, offset + len(text), "literal")
        runs = (_Run(0, len(text), origin, True),) if text else ()
        return MappedText(text, runs, self)

    def mapped(self, text: str, origin: Source | None) -> str:
        """A substituted value (or generated padding when origin is null)."""
        if not self.reserve(len(text)):
            return str(text)
        runs = (_Run(0, len(text), origin),) if text and origin is not None else ()
        return MappedText(text, runs, self)

    def to_json(self, rendered: str, *, rows: int, cols: int, extended_markup: bool = True) -> dict | None:
        """Project actual parsed cells, interning only their visible origins."""
        if self.limited:
            return None
        # Local import: markup is imported while templates.engine initializes.
        from src.markup import _pieces

        sources: list[dict] = []
        ids: dict[Source, int] = {}
        cells: list[list[int | None]] = []
        lines = rendered.split("\n", rows)
        for row in range(rows):
            line = lines[row] if row < len(lines) else ""
            cells.append([])
            for piece in _pieces(line, extended_markup=extended_markup, max_tokens=cols):
                if piece.token is None:
                    continue
                origin = origin_at(piece.source, 0)
                if origin is not None and origin not in ids:
                    ids[origin] = len(sources)
                    sources.append(asdict(origin))
                cells[-1].append(ids[origin] if origin is not None else None)
            cells[-1].extend([None] * (cols - len(cells[-1])))
        if self.limited:
            return None
        return {"rows": rows, "cols": cols, "sources": sources, "cells": cells}


def _append(runs: list[_Run], run: _Run) -> None:
    """Coalesce constant atoms and contiguous affine literal runs."""
    if runs and runs[-1].end == run.start:
        previous = runs[-1]
        if not previous.affine and not run.affine and previous.source == run.source:
            runs[-1] = _Run(previous.start, run.end, run.source)
            return
        if (
            previous.affine
            and run.affine
            and previous.source.line == run.source.line
            and previous.source.kind == run.source.kind
            and previous.source.end == run.source.start
        ):
            source = Source(run.source.line, previous.source.start, run.source.end, run.source.kind)
            runs[-1] = _Run(previous.start, run.end, source, True)
            return
    runs.append(run)


class MappedText(str):
    """A string carrying source runs; generated gaps have no source."""

    __slots__ = ("_starts", "runs", "tracker")

    def __new__(cls, text: str, runs: tuple[_Run, ...], tracker: SourceTracker):
        instance = str.__new__(cls, text)
        instance.runs = runs
        instance.tracker = tracker
        instance._starts = tuple(run.start for run in runs)
        return instance

    def __getitem__(self, key: int | slice) -> str:
        value = str.__getitem__(self, key)
        if not self.tracker.reserve(len(value)):
            return value
        if isinstance(key, int):
            start = key if key >= 0 else len(self) + key
            stop, step = start + 1, 1
        else:
            start, stop, step = key.indices(len(self))
        if step != 1:
            runs: list[_Run] = []
            for output, original in enumerate(range(start, stop, step)):
                origin = origin_at(self, original)
                if origin is not None:
                    _append(runs, _Run(output, output + 1, origin))
            return MappedText(value, tuple(runs), self.tracker)
        runs = []
        index = max(0, bisect_right(self._starts, start) - 1)
        while index < len(self.runs):
            run = self.runs[index]
            index += 1
            if run.start >= stop:
                break
            left, right = max(start, run.start), min(stop, run.end)
            if left >= right:
                continue
            origin = run.source
            if run.affine:
                origin = Source(
                    origin.line, origin.start + left - run.start, origin.start + right - run.start, origin.kind
                )
            runs.append(_Run(left - start, right - start, origin, run.affine))
        return MappedText(value, tuple(runs), self.tracker)

    def __add__(self, other: str) -> str:
        if not isinstance(other, str):
            return NotImplemented
        return concat((self, other))

    def __radd__(self, other: str) -> str:
        if not isinstance(other, str):
            return NotImplemented
        return concat((other, self))

    def __mul__(self, count: int) -> str:
        if not isinstance(count, int):
            return NotImplemented
        length = len(self) * max(0, count)
        if not self.tracker.reserve(length):
            return str.__mul__(self, count)
        runs: list[_Run] = []
        if self:
            for repeat in range(max(0, count)):
                offset = repeat * len(self)
                for run in self.runs:
                    _append(runs, _Run(run.start + offset, run.end + offset, run.source, run.affine))
        return MappedText(str.__mul__(self, count), tuple(runs), self.tracker)

    __rmul__ = __mul__

    def join(self, iterable: Iterable[str]) -> str:
        parts: list[str] = []
        for part in iterable:
            if parts:
                parts.append(self)
            parts.append(part)
        return concat(parts)

    def split(self, sep: str | None = None, maxsplit: int = -1) -> list[str]:
        if self.tracker.limited:
            return str.split(self, sep, maxsplit)
        if sep is None:
            parts: list[str] = []
            for match in re.finditer(r"\S+", self):
                if maxsplit >= 0 and len(parts) == maxsplit:
                    parts.append(self[match.start() :])
                    break
                parts.append(self[match.start() : match.end()])
            return parts
        if not sep:
            raise ValueError("empty separator")
        parts = []
        start = 0
        while maxsplit < 0 or len(parts) < maxsplit:
            at = self.find(sep, start)
            if at < 0:
                break
            parts.append(self[start:at])
            start = at + len(sep)
        parts.append(self[start:])
        return parts

    def strip(self, chars: str | None = None) -> str:
        left = len(self) - len(str.lstrip(self, chars))
        right = len(str.rstrip(self, chars))
        return self[left : max(left, right)]

    def lstrip(self, chars: str | None = None) -> str:
        return self[len(self) - len(str.lstrip(self, chars)) :]

    def rstrip(self, chars: str | None = None) -> str:
        return self[: len(str.rstrip(self, chars))]

    def replace(self, old: str, new: str, count: int = -1) -> str:
        if count == 0:
            return self
        return sub(re.compile(re.escape(old)), lambda _match: new, self, count=max(0, count))

    def translate(self, table: Mapping[int, Any]) -> str:
        # Charge before scanning/copying or constructing any new source runs.
        if not self.tracker.reserve(len(self)):
            return str.translate(self, table)
        raw = str(self)
        widths: dict[int, int] = {}
        length = 0
        one_to_one = True
        for char in raw:
            code = ord(char)
            if code not in widths:
                try:
                    replacement = table[code]
                except LookupError:
                    replacement = char
                if replacement is None:
                    widths[code] = 0
                elif isinstance(replacement, int):
                    widths[code] = 1
                elif isinstance(replacement, str):
                    widths[code] = len(replacement)
                else:
                    # Let the builtin raise its normal error for a bad table.
                    return str.translate(self, table)
            width = widths[code]
            length += width
            one_to_one = one_to_one and width == 1
        if not self.tracker.reserve(length):
            return str.translate(self, table)
        value = str.translate(self, table)
        if one_to_one:
            # Identity and single-character replacements change no offsets.
            # In particular, unprotecting braces must not expand an affine
            # literal run into thousands of single-character constant runs.
            return MappedText(value, self.runs, self.tracker)

        runs: list[_Run] = []
        original = output = 0
        for run in self.runs:
            output += sum(widths[ord(raw[at])] for at in range(original, run.start))
            original = run.end
            if not run.affine:
                end = output + sum(widths[ord(raw[at])] for at in range(run.start, run.end))
                if end > output:
                    _append(runs, _Run(output, end, run.source))
                output = end
                continue
            source = run.source
            first, segment_output = run.start, output
            for at in range(run.start, run.end):
                width = widths[ord(raw[at])]
                if width != 1:
                    if first < at:
                        origin = Source(
                            source.line, source.start + first - run.start, source.start + at - run.start, source.kind
                        )
                        _append(runs, _Run(segment_output, output, origin, True))
                    if width:
                        start = source.start + at - run.start
                        _append(runs, _Run(output, output + width, Source(source.line, start, start + 1, source.kind)))
                    first, segment_output = at + 1, output + width
                output += width
            if first < run.end:
                origin = Source(source.line, source.start + first - run.start, source.end, source.kind)
                _append(runs, _Run(segment_output, output, origin, True))
        return MappedText(value, tuple(runs), self.tracker)

    def ljust(self, width: int, fillchar: str = " ") -> str:
        result = str.ljust(self, width, fillchar)
        return concat((self, result[len(self) :]))

    def rjust(self, width: int, fillchar: str = " ") -> str:
        result = str.rjust(self, width, fillchar)
        return concat((result[: len(result) - len(self)], self))


def origin_at(text: str, offset: int) -> Source | None:
    if not isinstance(text, MappedText) or text.tracker.limited or not 0 <= offset < len(text):
        return None
    index = bisect_right(text._starts, offset) - 1
    if index < 0:
        return None
    run = text.runs[index]
    if offset >= run.end:
        return None
    source = run.source
    if run.affine:
        at = source.start + offset - run.start
        return Source(source.line, at, at + 1, source.kind)
    return source


def mapped_like(value: str, text: str, offset: int = 0) -> str:
    """Attribute replacement text to the source at one input position."""
    if not isinstance(text, MappedText):
        return value
    return text.tracker.mapped(value, origin_at(text, offset))


def concat(parts: Iterable[str]) -> str:
    """Join strings without losing provenance; plain inputs stay plain."""
    parts = list(parts)
    tracker = next((part.tracker for part in parts if isinstance(part, MappedText)), None)
    if tracker is None or not tracker.reserve(sum(map(len, parts))):
        return "".join(parts)
    runs: list[_Run] = []
    offset = 0
    for part in parts:
        if isinstance(part, MappedText):
            if part.tracker is not tracker:
                # There is no truthful shared budget for accidentally mixed requests.
                tracker.limited = True
                return "".join(parts)
            for run in part.runs:
                _append(runs, _Run(run.start + offset, run.end + offset, run.source, run.affine))
        offset += len(part)
    return MappedText("".join(parts), tuple(runs), tracker)


def sub(pattern: re.Pattern | str, repl: str | Callable[[re.Match], str], text: str, count: int = 0) -> str:
    """Regex replacement preserving copied text and explicit replacement maps."""
    if not isinstance(text, MappedText) or text.tracker.limited:
        return re.sub(pattern, repl, text, count=count)
    compiled = re.compile(pattern)
    parts: list[str] = []
    start = 0
    for number, match in enumerate(compiled.finditer(text)):
        if count and number >= count:
            break
        parts.append(text[start : match.start()])
        replacement = repl(match) if callable(repl) else match.expand(repl)
        parts.append(
            replacement if isinstance(replacement, MappedText) else mapped_like(replacement, text, match.start())
        )
        start = match.end()
    parts.append(text[start:])
    return concat(parts)
