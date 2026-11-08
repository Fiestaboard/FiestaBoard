"""Which page a collection would pick, at an instant and across a window (H8).

The 2.11 rule tester: every rule of a formula collection evaluated (not
short-circuited, so "rule 2 is true too, but rule 1 is checked first" can be
said), the winner, a timeline, and the boards whose schedule shows the
collection then. Sample and missing data, the instant and the data mode are
H6's preview, applied to a request-local copy; the evaluations share one
render budget (S2). Nothing is stored and no board is touched.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.templates.preview import Preview

from .models import Collection
from .service import _is_truthy

#: The most segments a time or random timeline lists (then ``truncated``).
MAX_SEGMENTS = 96
#: The most instants a formula collection's timeline evaluates.
MAX_POINTS = 97


@dataclass
class DryRun:
    page_id: str | None
    rules: list[dict[str, Any]] | None
    matched_rule: int | None
    timeline: list[dict[str, Any]]
    truncated: bool


def _segment(start: datetime, until: datetime, page_id: str | None) -> dict[str, Any]:
    from src.schedules.at_time import stamp

    return {"from": stamp(start), "until": stamp(until), "page_id": page_id}


def _merge(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for segment in segments:
        if merged and merged[-1]["page_id"] == segment["page_id"]:
            merged[-1]["until"] = segment["until"]
        else:
            merged.append(segment)
    return merged


def _rule_rows(collection: Collection, context: dict[str, Any], at: datetime) -> tuple[list[dict], int | None]:
    from src.templates.expressions import RENDER_CLOCK_KEY, evaluate_detailed

    variable = collection.variable
    clocked = {**context, RENDER_CLOCK_KEY: at}
    rows: list[dict[str, Any]] = []
    first: int | None = None
    for index, rule in enumerate(variable.rules if variable is not None else []):
        outcome = evaluate_detailed(rule.expression, clocked)
        matched = outcome.error is None and _is_truthy(outcome.value)
        if matched and first is None:
            first = index
        rows.append(
            {
                "index": index,
                "expression": rule.expression,
                "page_id": rule.page_id,
                "value": outcome.value,
                "error": outcome.error,
                "message": outcome.message,
                "matched": matched,
            }
        )
    return rows, first


def _winner(collection: Collection, rows: list[dict[str, Any]], first: int | None) -> str | None:
    if first is not None:
        return rows[first]["page_id"]
    return collection.variable.default_page_id if collection.variable is not None else None


def _variable_context(collection: Collection, preview: Preview) -> dict[str, Any]:
    from src.templates.engine import extract_template_plugin_ids, get_template_engine
    from src.templates.expressions import ensure_render_clock

    rules = collection.variable.rules if collection.variable is not None else []
    plugin_ids = extract_template_plugin_ids([f"{{{{= {rule.expression} }}}}" for rule in rules])
    context = get_template_engine()._preview_context(None, plugin_ids, preview)
    # One render budget (S2) for every evaluation of this dry run.
    return ensure_render_clock(context)


def run(collection: Collection, preview: Preview, at: datetime, window_seconds: int, step_seconds: int) -> DryRun:
    """The dry run of *collection* at *at* (hub-local) and over the window after it."""
    end = at + timedelta(seconds=window_seconds)
    if collection.selection_mode == "variable":
        context = _variable_context(collection, preview)
        rows, first = _rule_rows(collection, context, at)
        segments = []
        steps = window_seconds // step_seconds
        for k in range(steps + 1):
            start = at + timedelta(seconds=k * step_seconds)
            point_rows, point_first = (rows, first) if k == 0 else _rule_rows(collection, context, start)
            until = min(start + timedelta(seconds=step_seconds), end) if k < steps else end
            segments.append(_segment(start, until, _winner(collection, point_rows, point_first)))
        return DryRun(_winner(collection, rows, first), rows, first, _merge(segments), False)

    if collection.selection_mode == "random" and collection.random is not None:
        interval, pick = collection.random.interval_seconds, collection.current_page_id_random
    else:
        interval, pick = collection.time.interval_seconds, collection.current_page_id_time
    segments, truncated = [], False
    stamp_unix, end_unix = at.timestamp(), end.timestamp()
    while True:
        boundary = (math.floor(stamp_unix / interval) + 1) * interval
        until = min(boundary, end_unix)
        segments.append(
            _segment(
                datetime.fromtimestamp(stamp_unix, at.tzinfo),
                datetime.fromtimestamp(until, at.tzinfo),
                pick(stamp_unix),
            )
        )
        if boundary >= end_unix:
            break
        if len(segments) >= MAX_SEGMENTS:
            truncated = True
            break
        stamp_unix = boundary
    return DryRun(pick(at.timestamp()), None, None, _merge(segments), truncated)


def shown_on(collection_id: str, at_utc: datetime, zone: Any) -> list[str]:
    """The boards whose schedule (or manual pin) names *collection_id* at *at_utc*."""
    from src.schedules.next_change import _page_at
    from src.settings.service import get_settings_service

    boards = get_settings_service().get_board_settings().boards or []
    return [
        board["id"]
        for board in boards
        if isinstance(board, dict) and board.get("id") and _page_at(board["id"], at_utc, zone) == collection_id
    ]
