"""Pydantic models for the ``/transitions`` API (Phase 2 slice 8).

Transition plugins animate the board frame by frame. The Transition Lab in the
web UI replays exactly the grids and delays ``/transitions/preview`` returns,
so ``frames``, ``delay_ms`` and ``capped`` are contract, not decoration.

Every route in this domain is gated behind ``beta.transition_plugins_enabled``
and answers 404 while it is off.

The request models keep the endpoints' own 400s rather than letting Pydantic
turn them into 422s: ``plugin_id``, ``to_page_id`` and the device geometry are
all declared permissively here and validated in the handler, because the
existing clients (and ``tests/test_transitions_api.py``, which drives the
handlers directly) depend on those exact status codes and detail strings.
Widening a 400 into a 422 would be a contract change with no benefit.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TransitionSettingsCaps(BaseModel):
    """A transition plugin's declared limits, from its manifest."""

    interruptible: bool
    min_interval_ms: int
    max_frames: int
    max_runtime_seconds: int


class TransitionPluginEntry(BaseModel):
    """One installed transition plugin, as the picker lists it."""

    id: str
    name: str
    description: str | None = None
    icon: str | None = None
    version: str | None = None
    author: str | None = None
    settings_schema: dict[str, Any] = Field(default_factory=dict)
    transition_settings: TransitionSettingsCaps
    config: dict[str, Any] = Field(default_factory=dict)
    strategy: str = Field(description='The "plugin:<id>" string a page stores')


class TransitionPluginsResponse(BaseModel):
    """``GET /transitions/plugins``."""

    plugins: list[TransitionPluginEntry]


class TransitionPreviewRequest(BaseModel):
    """``POST /transitions/preview`` request body."""

    plugin_id: str | None = None
    from_text: str = ""
    to_text: str = ""
    device_type: str = "flagship"
    notes_wide: Any = 1
    notes_tall: Any = 1
    config: dict[str, Any] | None = None


class TransitionFrame(BaseModel):
    """One frame: the whole grid, plus how long to hold it."""

    grid: list[list[int]]
    delay_ms: int


class TransitionPreviewResponse(BaseModel):
    """``POST /transitions/preview`` — frames generated in-process, no board."""

    plugin_id: str
    device_type: str
    frames: list[TransitionFrame]
    frame_count: int
    total_delay_ms: int
    capped: bool = Field(description="True when max_frames or max_runtime_seconds truncated the run")
    from_grid: list[list[int]]
    to_grid: list[list[int]]


class TransitionLiveTestRequest(BaseModel):
    """``POST /transitions/test-live`` request body."""

    plugin_id: str | None = None
    to_page_id: str | None = None
    from_page_id: str | None = None
    config: dict[str, Any] | None = None
    board_id: str | None = None


class TransitionLiveTestResponse(BaseModel):
    """``POST /transitions/test-live``."""

    status: str = "success"
    sent: bool
    plugin_id: str
    from_page_id: str | None = None
    to_page_id: str
    board_id: str | None = None


class TransitionRestoreRequest(BaseModel):
    """``POST /transitions/restore`` request body (all fields optional)."""

    board_id: str | None = None


class TransitionRestoreResponse(BaseModel):
    """``POST /transitions/restore``."""

    status: str = "success"
    page_id: str
    sent: bool
    board_id: str | None = None
