"""Find stored board text whose meaning changes once extended markup is on.

Today the board grammar knows colour tiles (``{red}``, ``{63}``) and end tags
(``{/red}``, ``{/}``); anything else in braces is literal text, and a
split-flap board draws the braces as blanks. The extended grammar FiestaUI
speaks (and core will parse, output-plugins plan D15) adds three markers:

* colour span ``{red:HOT}``, ``{63:HOT}``, ``{#ff8800:HOT}``
* block span ``{black/white:OPEN}`` (foreground/background)
* icon ``{icon:sun}``

Text that already contains one of those heads renders literally today and
will render differently once the parser is on. This module finds it, so the
upgrade that turns the parser on can report (and release notes can name)
exactly which pages or settings are affected, instead of discovering it on
someone's wall.

Why ``src/`` and not a test helper: the scan has to run against a *user's*
data directory at upgrade time (the release that enables extended markup), so
it is production code. The Phase 0 upgrade fixtures use it today to prove the
fixtures carry no such text; ``tests/test_upgrade_fixtures.py`` holds its unit
tests.

The scan is deliberately conservative — case-insensitive, and it reports a
head even when no closing brace follows — because a false positive costs one
line in a report and a false negative is a silently changed board.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Colours a span head may name: the colour-tile codes and names (FiestaUI
#: ``ALL_COLOR_CODES``; ``filled`` is a tile but not a span colour).
SPAN_COLORS: tuple[str, ...] = (
    "63",
    "64",
    "65",
    "66",
    "67",
    "68",
    "69",
    "70",
    "71",
    "red",
    "orange",
    "yellow",
    "green",
    "blue",
    "violet",
    "purple",
    "white",
    "black",
)

_COLOR = "(?:" + "|".join(SPAN_COLORS) + r"|#[0-9a-f]{6})"
# ``(?<!\{)``: a ``{{template.variable}}`` is the template engine's syntax, not
# board markup, so a head directly after another brace is not one of ours.
_HEAD = r"(?<!\{)\{"

#: kind -> pattern for each marker head. Order is the report order.
MARKER_PATTERNS: dict[str, re.Pattern[str]] = {
    "block_span": re.compile(_HEAD + _COLOR + "/" + _COLOR + ":", re.IGNORECASE),
    "colour_span": re.compile(_HEAD + _COLOR + ":", re.IGNORECASE),
    "icon": re.compile(_HEAD + r"icon:", re.IGNORECASE),
}

#: Keys whose string values are literal board text in the stores. ``template``
#: covers pages (and the inline temporary override in settings.json);
#: ``indicator_text`` is the silence-schedule card and ``welcome_message`` the
#: setup greeting, both in config.json.
BOARD_TEXT_KEYS: frozenset[str] = frozenset({"template", "indicator_text", "welcome_message"})


@dataclass(frozen=True)
class MarkupFinding:
    """One piece of stored text that extended markup would reinterpret."""

    store: str  # file name inside the data dir, e.g. "pages.json"
    location: str  # JSON path inside it, e.g. "pages[2].template[0]"
    kind: str  # a MARKER_PATTERNS key
    marker: str  # the matched head, e.g. "{red:"
    text: str  # the whole stored string


def scan_text(text: str) -> list[tuple[str, str]]:
    """Return ``(kind, marker)`` for every extended-markup head in *text*, in
    text order. The three heads cannot match at the same brace (a block span
    has ``/`` where a colour span has ``:``), so each head is reported once.
    """
    found = [
        (match.start(), kind, match.group(0))
        for kind, pattern in MARKER_PATTERNS.items()
        for match in pattern.finditer(text)
    ]
    return [(kind, marker) for _, kind, marker in sorted(found)]


def _board_strings(value: Any, path: str, in_text: bool) -> Iterator[tuple[str, str]]:
    """Yield ``(json_path, string)`` for every board-text string under *value*."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _board_strings(child, f"{path}.{key}" if path else str(key), in_text or key in BOARD_TEXT_KEYS)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _board_strings(child, f"{path}[{i}]", in_text)
    elif isinstance(value, str) and in_text:
        yield path, value


def scan_document(store: str, data: Any) -> list[MarkupFinding]:
    """Scan one parsed store document."""
    findings: list[MarkupFinding] = []
    for location, text in _board_strings(data, "", False):
        for kind, marker in scan_text(text):
            findings.append(MarkupFinding(store=store, location=location, kind=kind, marker=marker, text=text))
    return findings


def scan_data_dir(data_dir: Path) -> list[MarkupFinding]:
    """Scan every live ``*.json`` store in *data_dir* (backups are not live).

    Unreadable or non-JSON files are skipped: this is a report, and a broken
    store is some other check's finding.
    """
    findings: list[MarkupFinding] = []
    for path in sorted(Path(data_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        findings.extend(scan_document(path.name, data))
    return findings
