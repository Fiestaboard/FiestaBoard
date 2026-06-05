"""Pydantic schemas that define the API contracts between the Python backend
and the Next.js frontend.

These schemas mirror what the frontend TypeScript types expect. If the backend
changes a response shape, these schemas will fail — catching contract drift
before it reaches production.

Each schema is defined with strict=True to reject unexpected fields by default.
"""

from typing import Any

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Core / Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """GET /health"""

    status: str  # "ok"


class VersionResponse(BaseModel):
    """GET /version"""

    package_version: str
    build_version: str
    is_dev: bool


class StatusResponse(BaseModel):
    """GET /status"""

    running: bool
    active_page: str | None = None
    uptime_seconds: float | None = None


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


class PageSchema(BaseModel):
    """A single page object as returned by the backend."""

    id: str
    name: str
    type: str  # "template" | "single" | "composite" | "note"
    template: list[str] | str | None = None
    display_type: str | None = None
    rows: list[Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


class PagesListResponse(BaseModel):
    """GET /pages"""

    pages: list[PageSchema]
    total: int


class CreatePageResponse(BaseModel):
    """POST /pages"""

    status: str  # "success"
    page: PageSchema


class GetPageResponse(PageSchema):
    """GET /pages/{page_id} — returns the page directly (not nested)."""


class UpdatePageResponse(BaseModel):
    """PUT /pages/{page_id}"""

    status: str  # "success"
    page: PageSchema


class DeletePageResponse(BaseModel):
    """DELETE /pages/{page_id}"""

    status: str  # "success" | "not_found"


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


class ScheduleSchema(BaseModel):
    """A single schedule entry."""

    id: str
    page_id: str
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    day_pattern: str  # "daily" | "weekdays" | "weekends" | ...
    board_id: str | None = None
    enabled: bool | None = None


class SchedulesListResponse(BaseModel):
    """GET /schedules"""

    schedules: list[ScheduleSchema]
    total: int


class CreateScheduleResponse(BaseModel):
    """POST /schedules"""

    status: str
    schedule: ScheduleSchema


class GetScheduleResponse(BaseModel):
    """GET /schedules/{schedule_id}"""

    schedule: ScheduleSchema


class SchedulesEnabledResponse(BaseModel):
    """GET /schedules/enabled"""

    enabled: bool


class ActivePageResponse(BaseModel):
    """GET /schedules/active/page"""

    page_id: str | None = None
    active: bool


class DefaultPageResponse(BaseModel):
    """GET /schedules/default-page"""

    page_id: str | None = None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TransitionSettingsResponse(BaseModel):
    """GET /settings/transitions"""

    strategy: str
    step_interval_ms: int | None = None
    step_size: int | None = None


class OutputSettingsResponse(BaseModel):
    """GET /settings/output"""

    target: str  # "ui" | "board" | ...


class BoardInstanceSchema(BaseModel):
    """A single board instance in the board settings."""

    id: str | None = None
    name: str
    device_type: str | None = None
    board_color: str | None = None
    api_mode: str | None = None
    enabled: bool | None = None


class BoardSettingsResponse(BaseModel):
    """GET /settings/board"""

    boards: list[dict[str, Any]]
    board_type: str | None = None
    devices: list[str] | None = None


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------


class PluginSchema(BaseModel):
    """A single plugin entry as returned by /plugins."""

    id: str
    name: str
    enabled: bool
    version: str | None = None
    description: str | None = None
    category: str | None = None


class PluginsListResponse(BaseModel):
    """GET /plugins"""

    plugins: list[PluginSchema]


class PluginDetailResponse(BaseModel):
    """GET /plugins/{plugin_id}"""

    id: str
    name: str
    enabled: bool
    version: str | None = None
    description: str | None = None
    category: str | None = None
    config: dict[str, Any] | None = None
