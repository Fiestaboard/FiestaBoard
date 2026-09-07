"""Data models for pages and layouts.

Pages can be:
- Single: Display a single source type
- Composite: Combine rows from multiple sources
- Template: Custom templated content with dynamic data
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.devices import DEFAULT_DEVICE_TYPE, MAX_NOTES_PER_AXIS, DeviceType, resolve_dimensions

PageType = Literal["single", "composite", "template"]

LineAlignment = Literal["left", "center", "right"]


class LineMetadata(BaseModel):
    """Per-line formatting metadata for template pages.

    Stores alignment and wrap settings that were previously encoded as
    inline prefixes ({center}, {wrap}, etc.) in the template strings.
    """

    alignment: LineAlignment = "left"
    wrap: bool = False


class RowConfig(BaseModel):
    """Configuration for a single row in a composite page.

    Specifies which row from which source should be placed at which position.
    Row limits depend on the device type of the parent page.
    """

    source: str  # Display type (weather, datetime, etc.)
    row_index: int = Field(ge=0)  # Which row from source
    target_row: int = Field(ge=0)  # Where to place in output


class Page(BaseModel):
    """A saved page configuration.

    Pages can be one of three types:
    - single: Displays a single source type
    - composite: Combines specific rows from multiple sources
    - template: Custom content with templated variables

    Each page targets a specific device type (flagship: 22x6, note: 15x3).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=1, max_length=100)
    type: PageType

    # Device type: "flagship" (22x6) or "note" (15x3)
    device_type: DeviceType = Field(default=DEFAULT_DEVICE_TYPE)

    # For single pages: which display type to show
    display_type: str | None = None

    # For composite pages: row configuration
    rows: list[RowConfig] | None = None

    # For template pages: lines of template text (pure content, no alignment prefixes)
    # Templates can include {{variable}} syntax for dynamic data
    # and {color} syntax for board colors
    template: list[str] | None = None

    # Per-line formatting metadata (alignment, wrap) for template pages
    line_metadata: list[LineMetadata] | None = None

    # Rotation settings
    duration_seconds: int = Field(default=300, ge=10, le=3600)  # 10s to 1h

    # Transition settings (per-page override, None means use system defaults).
    # Valid strategies: column, reverse-column, edges-to-center, row, diagonal,
    # random, or "plugin:<id>" to drive a frame-by-frame transition plugin
    # (e.g. "plugin:typewriter").  Pydantic stores any string; the strategy
    # is validated lazily at send-time by board_client.render().
    transition_strategy: str | None = None
    transition_interval_ms: int | None = Field(default=None, ge=0, le=5000)
    transition_step_size: int | None = Field(default=None, ge=1)

    # Plugin demo page tracking (singleton per plugin)
    demo_plugin_id: str | None = None

    # Note-array dimensions (only relevant when device_type is "note_array")
    # notes_wide × notes_tall determines the grid size: rows = notes_tall × 3, cols = notes_wide × 15
    notes_wide: int = Field(default=1, ge=1, le=MAX_NOTES_PER_AXIS)
    notes_tall: int = Field(default=1, ge=1, le=MAX_NOTES_PER_AXIS)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime | None = None

    model_config = ConfigDict(
        # Pydantic V2 uses serialization_mode_json for custom serializers
        # datetime is automatically serialized to ISO format in V2
    )

    def validate_config(self) -> list[str]:
        """Validate that page configuration is complete and consistent.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        dims = resolve_dimensions(self.device_type, self.notes_wide, self.notes_tall)
        max_row = dims.rows - 1

        if self.type == "single":
            if not self.display_type:
                errors.append("Single page requires display_type")

        elif self.type == "composite":
            if not self.rows or len(self.rows) == 0:
                errors.append("Composite page requires at least one row config")
            else:
                # Check for duplicate target rows
                target_rows = [r.target_row for r in self.rows]
                if len(target_rows) != len(set(target_rows)):
                    errors.append("Composite page has duplicate target rows")
                # Check row indices are within device limits
                for r in self.rows:
                    if r.row_index > max_row:
                        errors.append(f"Row index {r.row_index} exceeds max {max_row} for {self.device_type}")
                    if r.target_row > max_row:
                        errors.append(f"Target row {r.target_row} exceeds max {max_row} for {self.device_type}")

        elif self.type == "template" and (not self.template or len(self.template) == 0):
            errors.append("Template page requires template content")

        return errors

    def is_valid(self) -> bool:
        """Check if page configuration is valid."""
        return len(self.validate_config()) == 0


class PageCreate(BaseModel):
    """Request model for creating a new page."""

    name: str = Field(min_length=1, max_length=100)
    type: PageType
    device_type: DeviceType = Field(default=DEFAULT_DEVICE_TYPE)
    display_type: str | None = None
    rows: list[RowConfig] | None = None
    template: list[str] | None = None
    line_metadata: list[LineMetadata] | None = None
    duration_seconds: int = Field(default=300, ge=10, le=3600)
    # Transition settings (per-page override)
    transition_strategy: str | None = None
    transition_interval_ms: int | None = Field(default=None, ge=0, le=5000)
    transition_step_size: int | None = Field(default=None, ge=1)
    # Plugin demo page tracking
    demo_plugin_id: str | None = None
    # Note-array dimensions (only used when device_type is "note_array")
    notes_wide: int | None = Field(default=None, ge=1, le=MAX_NOTES_PER_AXIS)
    notes_tall: int | None = Field(default=None, ge=1, le=MAX_NOTES_PER_AXIS)


class PageUpdate(BaseModel):
    """Request model for updating an existing page."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    # Device/size retarget (issue #1250). Converting between geometries is
    # lossy (content that doesn't fit is truncated at render time) — the
    # editor confirms shrinking retargets before saving.
    device_type: DeviceType | None = None
    display_type: str | None = None
    rows: list[RowConfig] | None = None
    template: list[str] | None = None
    line_metadata: list[LineMetadata] | None = None
    duration_seconds: int | None = Field(default=None, ge=10, le=3600)
    # Transition settings (per-page override, use ... sentinel to leave unchanged)
    transition_strategy: str | None = None
    transition_interval_ms: int | None = Field(default=None, ge=0, le=5000)
    transition_step_size: int | None = Field(default=None, ge=1)
    # Note-array dimensions (only used when device_type is "note_array")
    notes_wide: int | None = Field(default=None, ge=1, le=MAX_NOTES_PER_AXIS)
    notes_tall: int | None = Field(default=None, ge=1, le=MAX_NOTES_PER_AXIS)


# ---------------------------------------------------------------------------
# Response models (Phase 2 slice 3 — API_CONVENTIONS.md "Response shapes")
#
# Every route in this domain declares one of these, so the response is a typed
# contract the TS client (`web/src/lib/api/pages.ts`) and `/check-types` can be
# held to, instead of whatever dict the handler happened to build.
# ---------------------------------------------------------------------------


class PageListResponse(BaseModel):
    """``GET /pages`` — every saved page, plus the count."""

    pages: list[Page]
    total: int


class IncompatibleReference(BaseModel):
    """A reference left pointing this page at a board it no longer fits.

    Produced by a device/size retarget (issue #1250, extended by #1788).
    Warn-only: the backend never mutates or removes the reference.
    """

    board_id: str
    board_name: str
    surface: Literal["schedule", "active_page", "silence"]
    schedule_id: str | None = None


class PageUpdateResponse(BaseModel):
    """``PUT /pages/{page_id}`` — the updated page and its stale references.

    Not a bare ``Page`` because the retarget warning is genuine payload, not
    an envelope: the editor shows it to the user after a size change.
    ``incompatible_references`` is always present and empty when the update
    did not change the page's size.
    """

    page: Page
    incompatible_references: list[IncompatibleReference] = Field(default_factory=list)


class PageDeleteResponse(BaseModel):
    """``DELETE /pages/{page_id}`` — the deleted id plus what else moved.

    Deleting the last page auto-creates a default welcome page, and deleting
    the active page re-points the active reference; both are reported here so
    the client can follow without re-fetching everything.
    """

    id: str
    message: str
    default_page_created: bool = False
    new_page_id: str | None = None
    active_page_updated: bool = False
    new_active_page_id: str | None = None


class ShareStringResponse(BaseModel):
    """``GET /pages/{page_id}/share`` and ``GET /staff-picks/{id}/share``."""

    share_string: str


class PageImportRequest(BaseModel):
    """Body of ``POST /pages/import`` and ``POST /pages/import/preview``."""

    share_string: str


class PageImportPreview(BaseModel):
    """``POST /pages/import/preview`` — the decoded page, not yet persisted.

    Exactly the content fields ``src/pages/share.py`` puts in the envelope:
    no ``id``, ``created_at``, ``updated_at`` or ``demo_plugin_id``, because a
    preview has not been created yet.
    """

    name: str
    type: PageType
    device_type: DeviceType = DEFAULT_DEVICE_TYPE
    display_type: str | None = None
    rows: list[RowConfig] | None = None
    template: list[str] | None = None
    line_metadata: list[LineMetadata] | None = None
    duration_seconds: int | None = None
    transition_strategy: str | None = None
    transition_interval_ms: int | None = None
    transition_step_size: int | None = None


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


class PagePreviewResponse(BaseModel):
    """``POST /pages/{page_id}/preview`` — the rendered board text."""

    page_id: str
    message: str
    lines: list[str]
    display_type: str
    raw: dict


class PagePreviewBatchSuccess(BaseModel):
    """One rendered page inside ``POST /pages/preview/batch``."""

    available: Literal[True] = True
    page_id: str
    message: str
    lines: list[str]
    display_type: str
    raw: dict


class PagePreviewBatchError(BaseModel):
    """One page inside ``POST /pages/preview/batch`` that could not render.

    A per-entry failure, not a request failure: the batch itself answers 200
    because the other pages rendered. ``available`` discriminates the two
    arms so a client can narrow without probing for keys.
    """

    available: Literal[False] = False
    error: str


class PagePreviewBatchRequest(BaseModel):
    """Body of ``POST /pages/preview/batch``."""

    page_ids: list[str] = Field(default_factory=list)
    force_refresh: bool = False


class PagePreviewBatchResponse(BaseModel):
    """``POST /pages/preview/batch`` — one entry per requested page id."""

    previews: dict[str, PagePreviewBatchSuccess | PagePreviewBatchError]
    total: int
    successful: int


class PageCacheStatsResponse(BaseModel):
    """``GET /pages/cache/stats`` — preview-cache occupancy and TTL."""

    cache_size: int
    cached_pages: list[str]
    ttl_seconds: int


class PageCacheClearRequest(BaseModel):
    """Body of ``POST /pages/cache/clear``. Omit ``page_id`` to clear all."""

    page_id: str | None = None


class PageCacheClearResponse(BaseModel):
    """``POST /pages/cache/clear`` — what was evicted."""

    message: str
    page_id: str | None = None


class PageSendRequest(BaseModel):
    """Body of ``POST /pages/{page_id}/send``.

    Both fields may equally be given as query parameters; the query wins.
    """

    target: str | None = None
    board_id: str | None = None


class PageSendResponse(BaseModel):
    """``POST /pages/{page_id}/send`` — what was rendered and where it went.

    ``sent_to_board`` is False for a UI-only target, a silenced board, or a
    paused board (``paused`` tells those last two apart from the first).
    """

    page_id: str
    message: str
    sent_to_board: bool
    paused: bool = False
    target: str
    board_id: str | None = None


class PageSendFailure(BaseModel):
    """The 500 body when the board refused or could not be reached.

    Deliberately not 502/503/504: nginx intercepts those on ``/api/`` and
    replaces the body with its startup placeholder, so the caller would lose
    the reason entirely.
    """

    detail: str
    page_id: str
    sent_to_board: bool = False
    paused: bool = False
    target: str
    board_id: str | None = None


class CurrentDisplayResponse(BaseModel):
    """``GET /pages/current-display`` — what the board is showing now.

    For a template page ``template`` is the **raw** template (``{{vars}}``
    intact) plus its per-line metadata, so the editor can start a new page
    from it. For every other page type it is the rendered output lines and
    ``line_metadata`` is null.
    """

    page_id: str
    page_name: str
    page_type: PageType
    device_type: DeviceType
    template: list[str]
    line_metadata: list[LineMetadata] | None = None
