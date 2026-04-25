"""Pydantic schemas that define the API contracts between the Python backend
and the Next.js frontend.

These schemas mirror what the frontend TypeScript types expect. If the backend
changes a response shape, these schemas will fail — catching contract drift
before it reaches production.

Each schema is defined with strict=True to reject unexpected fields by default.
"""

from typing import Any, Dict, List, Optional, Union
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
    active_page: Optional[str] = None
    uptime_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


class PageSchema(BaseModel):
    """A single page object as returned by the backend."""
    id: str
    name: str
    type: str  # "template" | "single" | "composite" | "note"
    template: Optional[Union[List[str], str]] = None
    display_type: Optional[str] = None
    rows: Optional[List[Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PagesListResponse(BaseModel):
    """GET /pages"""
    pages: List[PageSchema]
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
    board_id: Optional[str] = None
    enabled: Optional[bool] = None


class SchedulesListResponse(BaseModel):
    """GET /schedules"""
    schedules: List[ScheduleSchema]
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
    page_id: Optional[str] = None
    active: bool


class DefaultPageResponse(BaseModel):
    """GET /schedules/default-page"""
    page_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TransitionSettingsResponse(BaseModel):
    """GET /settings/transitions"""
    strategy: str
    step_interval_ms: Optional[int] = None
    step_size: Optional[int] = None


class OutputSettingsResponse(BaseModel):
    """GET /settings/output"""
    target: str  # "ui" | "board" | ...


class BoardInstanceSchema(BaseModel):
    """A single board instance in the board settings."""
    id: Optional[str] = None
    name: str
    device_type: Optional[str] = None
    board_color: Optional[str] = None
    api_mode: Optional[str] = None
    enabled: Optional[bool] = None


class BoardSettingsResponse(BaseModel):
    """GET /settings/board"""
    boards: List[Dict[str, Any]]
    board_type: Optional[str] = None
    devices: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------


class PluginSchema(BaseModel):
    """A single plugin entry as returned by /plugins."""
    id: str
    name: str
    enabled: bool
    version: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None


class PluginsListResponse(BaseModel):
    """GET /plugins"""
    plugins: List[PluginSchema]


class PluginDetailResponse(BaseModel):
    """GET /plugins/{plugin_id}"""
    id: str
    name: str
    enabled: bool
    version: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
