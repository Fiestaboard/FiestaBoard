"""Shared result envelopes for operation executors.

Every mutating operation — whichever grammar named it — returns the same
success/error envelope the MCP tools have always returned, so re-expressing
a tool on the ops layer changes no observable output.
"""

from __future__ import annotations

from typing import Any


def ok(message: str, **fields: Any) -> dict[str, Any]:
    """Standard success envelope for mutation operations."""
    return {"status": "success", "message": message, **fields}


def err(error: str) -> dict[str, Any]:
    """Standard error envelope. Executors never raise — they return this instead."""
    return {"status": "error", "error": error}


def rest_detail(exc: Any) -> str:
    """Flatten an HTTPException detail into a single message.

    The plugin-config endpoint raises ``detail={"errors": [...]}``; the
    rest raise a plain string.
    """
    detail = getattr(exc, "detail", exc)
    if isinstance(detail, dict) and detail.get("errors"):
        return "; ".join(str(e) for e in detail["errors"])
    return str(detail)


def serialize(obj: Any) -> Any:
    """Convert Pydantic models / dataclasses / datetimes to JSON-compatible primitives.

    Used when an executor returns Pydantic models (pages, schedules,
    collections) or dataclasses (settings objects). Plain dicts/lists pass
    through. Falls back to ``__dict__`` for other ad-hoc objects
    (e.g. SimpleNamespace).
    """
    import dataclasses
    from datetime import date, datetime, time

    if obj is None or isinstance(obj, str | int | float | bool):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: serialize(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [serialize(x) for x in obj]
    if isinstance(obj, tuple):
        return [serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, datetime | date | time):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return {k: serialize(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)
