"""Find stored board text whose meaning changes now that every board speaks
extended markup (plan D15/D16/D19, the Task 12 split-flap flip).

Before the flip, only an LED board parsed extended markup. On a split-flap
board the grammar knew colour tiles (``{red}``, ``{63}``) and end tags
(``{/red}``, ``{/}``); anything else in braces was literal text, drawn with
the braces as blanks, and the legacy template shortcuts drew ASCII stand-ins
(``{sun}`` -> ``*``). Since the flip (:data:`src.text_to_board.SPLIT_FLAP_EXTENDED_MARKUP`)
every board parses the extended grammar FiestaUI speaks, so stored text that
contains one of these now draws differently on a split-flap board:

* board markup heads: colour span ``{red:HOT}`` / ``{63:HOT}`` /
  ``{#ff8800:HOT}``, block span ``{black/white:OPEN}``, icon ``{icon:sun}``
  (they drew literally; now a span draws its letters and an icon its
  registry fallback);
* template authoring forms (plan D19): ``{{red:HOT}}``, ``{{black/white:OPEN}}``,
  ``{{icon:sun}}`` (they were variable lookups; now they are markup);
* legacy shortcuts whose rendering changes (plan D16): ``{sun}`` is now
  ``{icon:sun}``, a yellow tile where it was ``*``; ``{heart}`` is one ``♥``
  where it was the two cells ``<3``. ``{fog}`` draws ``-`` either way, so it
  is not reported.

This module finds that text in a data directory, so the upgrade can report
(and release notes can name) exactly which pages or settings changed instead
of the user discovering it on the wall. It runs at every startup
(:func:`log_upgrade_scan`, from ``src.api_server._run_startup_migrations``)
and on ``GET /system/markup-compat``.

The scan is deliberately conservative — case-insensitive, and it reports a
head even when no closing brace follows — because a false positive costs one
line in a report and a false negative is a silently changed board.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from src.markup import BOARD_ICONS, resolve_icon_name

logger = logging.getLogger(__name__)

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
# A template authoring form: exactly two braces (not a third before them).
_TEMPLATE_HEAD = r"(?<!\{)\{\{"

#: The colour a split-flap tile code is, for naming an icon's fallback tile.
_TILE_NAMES = {
    "63": "red",
    "64": "orange",
    "65": "yellow",
    "66": "green",
    "67": "blue",
    "68": "violet",
    "69": "white",
    "70": "black",
    "71": "filled",
}


@cache
def _legacy_ascii() -> dict[str, str]:
    """Shortcut name -> the ASCII it drew before the flip.

    Read from the template engine's own table (one table, plan D16), late:
    the engine pulls in the plugin system, which this module must not load
    at import time.
    """
    from src.templates.engine import SYMBOL_CHARS

    return dict(SYMBOL_CHARS)


def shortcut_change(name: str) -> tuple[str, str]:
    """``(before, after)``: what shortcut *name* drew on a split-flap board
    before the flip, and what it draws now, in words (``("*", "yellow
    tile")``, ``("<3", "♥")``, ``("-", "-")`` for ``fog``).
    """
    name = name.lower()
    before = _legacy_ascii()[name]
    if name == "heart":
        return before, "♥"
    icon = resolve_icon_name(name)
    if icon is None:  # a shortcut the registry does not know keeps its ASCII
        return before, before
    fallback = BOARD_ICONS[icon].fallback
    if fallback is None:
        return before, "blank"
    if fallback in _TILE_NAMES:
        return before, f"{_TILE_NAMES[fallback]} tile"
    return before, fallback


@cache
def _changed_shortcut_pattern() -> re.Pattern[str]:
    names = sorted(n for n in _legacy_ascii() if shortcut_change(n)[0] != shortcut_change(n)[1])
    return re.compile(_HEAD + "(?:" + "|".join(names) + r")\}", re.IGNORECASE)


#: kind -> pattern for each marker head that does not need the engine's table.
MARKER_PATTERNS: dict[str, re.Pattern[str]] = {
    "block_span": re.compile(_HEAD + _COLOR + "/" + _COLOR + ":", re.IGNORECASE),
    "colour_span": re.compile(_HEAD + _COLOR + ":", re.IGNORECASE),
    "icon": re.compile(_HEAD + r"icon:", re.IGNORECASE),
    "template_block_span": re.compile(_TEMPLATE_HEAD + _COLOR + "/" + _COLOR + ":", re.IGNORECASE),
    "template_colour_span": re.compile(_TEMPLATE_HEAD + _COLOR + ":", re.IGNORECASE),
    "template_icon": re.compile(_TEMPLATE_HEAD + r"icon:", re.IGNORECASE),
}

#: Every finding kind, in report order.
KINDS: tuple[str, ...] = ("legacy_shortcut", *MARKER_PATTERNS)

#: Keys whose string values are literal board text in the stores. ``template``
#: covers pages (and the inline temporary override in settings.json);
#: ``indicator_text`` is the silence-schedule card and ``welcome_message`` the
#: setup greeting, both in config.json.
BOARD_TEXT_KEYS: frozenset[str] = frozenset({"template", "indicator_text", "welcome_message"})


@dataclass(frozen=True)
class MarkupFinding:
    """One piece of stored text whose split-flap rendering changed."""

    store: str  # file name inside the data dir, e.g. "pages.json"
    location: str  # JSON path inside it, e.g. "pages[2].template[0]"
    kind: str  # one of KINDS
    marker: str  # the matched head, e.g. "{red:" or "{sun}"
    text: str  # the whole stored string
    item_id: str | None = None  # the enclosing record's id (a page), if any
    item_name: str | None = None  # ... and its name


def _patterns() -> Iterator[tuple[str, re.Pattern[str]]]:
    yield "legacy_shortcut", _changed_shortcut_pattern()
    yield from MARKER_PATTERNS.items()


def scan_text(text: str) -> list[tuple[str, str]]:
    """Return ``(kind, marker)`` for every head in *text* that changes, in
    text order. No two kinds match at the same brace (a block span has ``/``
    where a colour span has ``:``; a template form starts with two braces, a
    board head with one), so each head is reported once.
    """
    found = [(match.start(), kind, match.group(0)) for kind, pattern in _patterns() for match in pattern.finditer(text)]
    return [(kind, marker) for _, kind, marker in sorted(found)]


def _board_strings(
    value: Any, path: str, in_text: bool, item: tuple[str | None, str | None]
) -> Iterator[tuple[str, str, tuple[str | None, str | None]]]:
    """Yield ``(json_path, string, (item_id, item_name))`` for every
    board-text string under *value*; the item is the nearest enclosing
    record with a string ``id``."""
    if isinstance(value, dict):
        if isinstance(value.get("id"), str):
            name = value.get("name")
            item = (value["id"], name if isinstance(name, str) else None)
        for key, child in value.items():
            yield from _board_strings(
                child, f"{path}.{key}" if path else str(key), in_text or key in BOARD_TEXT_KEYS, item
            )
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _board_strings(child, f"{path}[{i}]", in_text, item)
    elif isinstance(value, str) and in_text:
        yield path, value, item


def scan_document(store: str, data: Any) -> list[MarkupFinding]:
    """Scan one parsed store document."""
    findings: list[MarkupFinding] = []
    for location, text, (item_id, item_name) in _board_strings(data, "", False, (None, None)):
        for kind, marker in scan_text(text):
            findings.append(MarkupFinding(store, location, kind, marker, text, item_id, item_name))
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


def scan_live_data() -> list[MarkupFinding]:
    """:func:`scan_data_dir` of the install's data directory
    (:func:`src.paths.get_data_dir`), for ``GET /system/markup-compat``."""
    from src.paths import get_data_dir

    return scan_data_dir(get_data_dir())


def _place(finding: MarkupFinding) -> tuple[str, str]:
    """The record a finding belongs to: its item, else its own location."""
    return finding.store, finding.item_id if finding.item_id is not None else finding.location


def summarize(findings: list[MarkupFinding]) -> dict[str, Any]:
    """``{"total", "places", "counts"}``: how many findings, in how many
    places (a page, or a single setting), and how many of each kind (kinds
    with none are left out; report order)."""
    counts = Counter(f.kind for f in findings)
    return {
        "total": len(findings),
        "places": len({_place(f) for f in findings}),
        "counts": {kind: counts[kind] for kind in KINDS if counts[kind]},
    }


def change_of(finding: MarkupFinding) -> tuple[str | None, str | None]:
    """``(before, after)`` for a legacy-shortcut finding; ``(None, None)``
    for the extended-markup kinds, whose change is the parse itself."""
    if finding.kind != "legacy_shortcut":
        return None, None
    return shortcut_change(finding.marker[1:-1])


#: The most findings :func:`log_upgrade_scan` lists one per line.
LOG_FINDINGS_LIMIT = 50


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def log_upgrade_scan(data_dir: Path) -> list[MarkupFinding]:
    """Scan *data_dir* and log what changed: one WARNING summary, then one
    INFO line per finding (at most :data:`LOG_FINDINGS_LIMIT`). Nothing
    affected is one INFO line. Returns the findings."""
    findings = scan_data_dir(data_dir)
    if not findings:
        logger.info("Markup upgrade scan: no stored board text changes with extended markup on every board")
        return findings
    summary = summarize(findings)
    kinds = ", ".join(f"{n} {kind}" for kind, n in summary["counts"].items())
    logger.warning(
        "Markup upgrade scan: %s in %s draw differently on split-flap boards now that every board "
        "speaks extended markup (%s). GET /system/markup-compat lists them.",
        _plural(summary["total"], "stored string"),
        _plural(summary["places"], "place"),
        kinds,
    )
    for finding in findings[:LOG_FINDINGS_LIMIT]:
        before, after = change_of(finding)
        label = f"{finding.item_name!r} " if finding.item_name else ""
        change = f" ({before} -> {after})" if before is not None else ""
        logger.info("  %s %s%s: %s %s%s", finding.store, label, finding.location, finding.kind, finding.marker, change)
    if len(findings) > LOG_FINDINGS_LIMIT:
        logger.info("  ... and %d more", len(findings) - LOG_FINDINGS_LIMIT)
    return findings
