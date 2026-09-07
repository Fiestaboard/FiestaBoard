"""Pydantic models for the ``/staff-picks`` API.

Moved out of ``src/pages/models.py`` by Phase 2 slice 8 so staff-picks is a
domain the conventions ratchet can excuse, enforce and review on its own —
it had been sharing the ``pages`` router tag, which made the two
indistinguishable to the manifest. ``src.pages.models`` re-exports them so
older imports keep resolving.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.devices import DEFAULT_DEVICE_TYPE, DeviceType


class StaffPickPlugin(BaseModel):
    """A plugin a staff pick's template depends on."""

    id: str
    name: str


class StaffPick(BaseModel):
    """``GET /staff-picks`` entry — the share string is deliberately absent.

    It is served only by ``GET /staff-picks/{pick_id}/share``, so the list
    stays small and a pick cannot be imported straight out of the listing.
    """

    id: str
    name: str
    description: str = ""
    device_type: DeviceType = DEFAULT_DEVICE_TYPE
    tags: list[str] = Field(default_factory=list)
    image: str | None = None
    featured_at: str | None = None
    required_plugins: list[StaffPickPlugin] = Field(default_factory=list)
