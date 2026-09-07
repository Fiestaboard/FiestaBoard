"""Pydantic models for the ``/triggers`` API (Phase 2 slice 8).

A trigger is a plugin interrupting the board — a doorbell, a delivery, a
low-battery warning. The web UI sorts the list by ``priority`` and runs its
dismiss countdown off ``remaining_seconds``, so both are part of the contract
rather than incidental fields.

These mirror :class:`src.triggers.service.ActiveTrigger` exactly, so a field
added to the dataclass without being added here shows up as a validation
failure rather than silently disappearing from the API.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TriggerModel(BaseModel):
    """One active trigger, serialised as ``ActiveTrigger.to_dict()`` builds it."""

    trigger_id: str
    plugin_id: str
    message: str | None = None
    formatted_lines: list[str] | None = None
    data: dict[str, Any] | None = None
    priority: int = Field(description="Higher wins when several triggers are active")
    duration_seconds: int
    activated_at: str = Field(description="ISO-8601, aware UTC")
    remaining_seconds: float


class TriggerListResponse(BaseModel):
    """``GET /triggers``."""

    triggers: list[TriggerModel]
    count: int


class ActiveTriggerResponse(BaseModel):
    """``GET /triggers/active`` — ``trigger`` is explicitly null when none fired."""

    trigger: TriggerModel | None = None


class TriggerDismissResponse(BaseModel):
    """``POST /triggers/{trigger_id}/dismiss``."""

    status: str = "dismissed"
    trigger_id: str


class TriggerClearResponse(BaseModel):
    """``POST /triggers/clear``."""

    status: str = "cleared"


class TriggerCheckResponse(BaseModel):
    """``POST /triggers/check`` — a manual poll of every trigger-capable plugin."""

    plugins_checked: int
    active_triggers: list[TriggerModel]
    count: int
