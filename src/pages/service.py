"""Page service for CRUD operations and rendering.

Provides high-level operations on pages including preview and send.
"""

import logging
import time
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.canvas import covered_cells, free_spans, render_canvases_on_grid, scale_area
from src.canvas.refs import canvas_plugin_ids
from src.devices import (
    DEFAULT_DEVICE_TYPE,
    GEOMETRY_FIELDS,
    BoardContext,
    board_context_for,
    dimensions_of,
    geometry_of,
    pages_compatible_with_board,
    size_key,
)
from src.displays.service import DisplayResult, get_display_service
from src.led.matrix import DEFAULT_LED_FONT, grid_layout
from src.plugins.manifest import DemoPageSchema
from src.settings.service import get_settings_service
from src.templates.engine import extract_template_plugin_ids, get_template_engine
from src.text_to_board import SPLIT_FLAP_EXTENDED_MARKUP

from .models import LineMetadata, Page, PageCreate, PageUpdate
from .storage import PageStorage

logger = logging.getLogger(__name__)


# Cache TTL in seconds for non-polling preview requests (e.g. UI preview list).
# The background polling loop bypasses this cache via force_refresh=True.
PREVIEW_CACHE_TTL = 120

# Prefix for the per-size coverage entries `shared_context_for` keeps inside
# the per-tick ``contexts`` cache (issue #1751): ``coverage_key -> set of
# plugin ids the cached context was fetched for``. A size key never starts
# with NUL, so these companion entries can share the dict without colliding.
# A size WITHOUT a coverage entry was built with fetch-all (full coverage).
_CONTEXT_COVERAGE_PREFIX = "\x00fetched:"

# Prefix for the per-size payload-hash companion entries `shared_context_for`
# keeps beside each cached context (issue #1883 follow-up): ``fingerprint_key
# -> {plugin_id: PluginResult.data_fingerprint()}``, covering EXACTLY the ids
# in that size's context. The render short-circuit composes those hashes
# instead of re-serialising every payload once per board per tick; a size
# WITHOUT this entry makes it fall back to hashing the payloads itself.
CONTEXT_FINGERPRINT_PREFIX = "\x00fingerprints:"

# Prefix for the per-size render-fingerprint memo (issue #1883 follow-up).
# Keyed by size so board-aware plugins, which legitimately return different
# data per geometry, can never have their fingerprints collapsed together.
CONTEXT_RENDER_MEMO_PREFIX = "\x00render-fp:"


# Default welcome page templates per device type
DEFAULT_PAGE_TEMPLATES = {
    "flagship": [
        "      Welcome to      ",
        "     FiestaBoard      ",
        "                      ",
        "   Create a new page  ",
        "    to get started    ",
        "                      ",
    ],
    "note": [
        "   Welcome to  ",
        "  FiestaBoard  ",
        "               ",
    ],
}

# Backward compatibility alias
DEFAULT_PAGE_TEMPLATE = DEFAULT_PAGE_TEMPLATES["flagship"]


def page_plugin_ids(page: Page) -> set[str] | None:
    """The plugin ids a page's render reads: its template's and its canvases'.

    ``None`` when either cannot be determined statically (a formula), which
    callers read as "fetch every enabled plugin" (issue #1751).
    """
    template_refs = extract_template_plugin_ids(getattr(page, "template", None))
    canvases = getattr(page, "canvases", None)
    canvas_refs = canvas_plugin_ids(canvases) if isinstance(canvases, list) else set()
    if template_refs is None or canvas_refs is None:
        return None
    return template_refs | canvas_refs


def draws_pixels(display: Any) -> bool:
    """Whether *display* (a :class:`~src.outputs.display_profile.DisplayProfile`) is a pixel matrix."""
    supports = getattr(display, "supports", None)
    try:
        return bool(supports and supports("pixels"))
    except ValueError:
        return False


@dataclass
class DeleteResult:
    """Result of a page deletion operation."""

    deleted: bool
    default_page_created: bool = False
    new_page_id: str | None = None
    active_page_updated: bool = False
    new_active_page_id: str | None = None


@dataclass
class CachedPreview:
    """Cached preview result for a page."""

    result: DisplayResult
    page_updated_at: datetime | None  # Timestamp when page was last updated
    cached_at: float  # Unix timestamp when this was cached

    def is_valid(self, page: Page, ttl_seconds: int = PREVIEW_CACHE_TTL) -> bool:
        """Check if this cache entry is still valid.

        Args:
            page: The page to check against
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if cache is still valid, False otherwise
        """
        # Check if page was updated after cache was created
        if page.updated_at and self.page_updated_at:
            if page.updated_at > self.page_updated_at:
                return False
        elif page.updated_at != self.page_updated_at:
            # One is None and the other isn't
            return False

        # Check TTL
        age = time.time() - self.cached_at
        return age < ttl_seconds


class PageService:
    """Service for page operations.

    Handles:
    - CRUD operations on pages
    - Rendering pages to formatted text
    - Previewing pages with caching
    """

    def __init__(self, storage: PageStorage | None = None):
        """Initialize page service.

        Args:
            storage: Page storage instance. Created if not provided.
        """
        self.storage = storage or PageStorage()
        self._preview_cache: dict[str, CachedPreview] = {}
        logger.info("PageService initialized")

    # CRUD operations

    def list_pages(self) -> list[Page]:
        """List all pages."""
        return self.storage.list_all()

    def get_page(self, page_id: str) -> Page | None:
        """Get a page by ID."""
        return self.storage.get(page_id)

    def create_page(self, data: PageCreate) -> Page:
        """Create a new page.

        Args:
            data: Page creation data

        Returns:
            Created page

        Raises:
            ValueError: If page configuration is invalid
        """
        page = Page(
            name=data.name,
            type=data.type,
            device_type=data.device_type,
            display_type=data.display_type,
            rows=data.rows,
            template=data.template,
            line_metadata=data.line_metadata,
            duration_seconds=data.duration_seconds,
            transition_strategy=data.transition_strategy,
            transition_interval_ms=data.transition_interval_ms,
            transition_step_size=data.transition_step_size,
            demo_plugin_id=data.demo_plugin_id,
            # PageCreate leaves W×H optional (None) — default to a single Note.
            notes_wide=data.notes_wide or 1,
            notes_tall=data.notes_tall or 1,
            grid_rows=data.grid_rows,
            grid_cols=data.grid_cols,
            canvases=data.canvases,
            created_at=datetime.now(UTC),
        )

        return self.storage.create(page)

    def update_page(self, page_id: str, data: PageUpdate) -> Page | None:
        """Update an existing page.

        Args:
            page_id: Page ID
            data: Update data

        Returns:
            Updated page or None if not found

        Raises:
            ValueError: If a device/size retarget (issue #1250) would leave
                the page config invalid (e.g. a composite row that no longer
                fits the new geometry)
        """
        updates = data.model_dump(exclude_unset=True)
        self._scale_canvases_on_retarget(page_id, updates)

        # Device/size retarget (issue #1250): re-validate the prospective page
        # before persisting so a retarget can't strand an invalid config.
        # Lossy template truncation is accepted (handled at render time);
        # structural errors (composite rows out of range) are blocked.
        if any(key in updates for key in GEOMETRY_FIELDS):
            existing = self.storage.get(page_id)
            if existing is not None:
                # Mirror storage.update() semantics: None never overwrites the
                # geometry fields, so validate with None values dropped.
                try:
                    prospective = Page(
                        **{**existing.model_dump(), **{k: v for k, v in updates.items() if v is not None}}
                    )
                except ValidationError as exc:
                    # e.g. a retarget to "panel" without a grid.
                    raise ValueError(f"Cannot retarget page: {exc.errors()[0]['msg']}") from exc
                errors = prospective.validate_config()
                if errors:
                    raise ValueError(f"Cannot retarget page: {'; '.join(errors)}")

        updated_page = self.storage.update(page_id, updates)

        # Invalidate preview cache for this page
        if updated_page:
            self._invalidate_cache(page_id)
            logger.debug(f"Invalidated preview cache for page {page_id}")

        return updated_page

    def _scale_canvases_on_retarget(self, page_id: str, updates: dict) -> None:
        """A size retarget that does not send ``canvases`` scales the stored areas.

        Canvas areas are cells of the page grid, so a grid change (a board's
        text size switch, a FiestaPanel re-fit, the editor's retarget) moves
        them proportionally (:func:`src.canvas.scale_area`) rather than
        leaving them where they no longer fit. Explicit ``canvases`` in the
        same update win: the caller already placed them.
        """
        if "canvases" in updates or not any(key in updates for key in GEOMETRY_FIELDS):
            return
        existing = self.storage.get(page_id)
        if existing is None or not existing.canvases:
            return
        merged = {**existing.model_dump(), **{k: v for k, v in updates.items() if v is not None}}
        try:
            old = dimensions_of(existing)
            new = dimensions_of(merged)
        except ValueError:
            return  # the retarget itself is invalid; update_page reports that
        if (old.rows, old.cols) == (new.rows, new.cols):
            return
        updates["canvases"] = [
            canvas.model_copy(update={"area": scale_area(canvas.area, (old.rows, old.cols), (new.rows, new.cols))})
            for canvas in existing.canvases
        ]

    def delete_page(self, page_id: str) -> DeleteResult:
        """Delete a page.

        If this is the last page, a default welcome page is created first
        to ensure there is always at least one page.

        If the deleted page is the active display page, the active page will
        be updated to another valid page.

        Args:
            page_id: Page ID

        Returns:
            DeleteResult with deletion status and info about any default page created
        """
        # Check if page exists
        existing_page = self.storage.get(page_id)
        if existing_page is None:
            return DeleteResult(deleted=False)

        # Check if this page is the active display page
        settings_service = get_settings_service()
        is_active_page = settings_service.get_active_page_id() == page_id

        # Check if this is the last page
        if self.storage.count() == 1:
            # Delete the original FIRST (persisting that deletion), then create
            # the default. If creating the default fails after a successful
            # delete, the user is briefly left with zero pages — a recoverable
            # state — rather than an orphaned "Welcome" page committed to disk
            # alongside an original that was never deleted (issue #1314). The
            # previous create-then-delete order could leave two pages on disk
            # if the delete's save raised after the default was already saved.
            self.storage.delete(page_id)
            self._invalidate_cache(page_id)

            # Create the replacement default. Match the deleted page's
            # device_type so a note (3x15) board doesn't end up with a
            # flagship (6x22) welcome page (issue #1307).
            default_page = self._create_default_page(device_type=existing_page.device_type)
            logger.info(f"Created default page {default_page.id} after deleting last page {page_id}")

            # If deleted page was active, set the new default as active
            if is_active_page:
                settings_service.set_active_page_id(default_page.id)
                logger.info(f"Active page updated to new default: {default_page.id}")

            return DeleteResult(
                deleted=True,
                default_page_created=True,
                new_page_id=default_page.id,
                active_page_updated=is_active_page,
                new_active_page_id=default_page.id if is_active_page else None,
            )

        # Normal deletion
        self.storage.delete(page_id)

        self._invalidate_cache(page_id)

        # If deleted page was active, set another page as active
        new_active_id = None
        if is_active_page:
            remaining_pages = self.storage.list_all()
            if remaining_pages:
                new_active_id = remaining_pages[0].id
                settings_service.set_active_page_id(new_active_id)
                logger.info(f"Active page updated to: {new_active_id}")

        return DeleteResult(deleted=True, active_page_updated=is_active_page, new_active_page_id=new_active_id)

    def _create_default_page(self, device_type: str | None = None) -> Page:
        """Create and save a default welcome page.

        Args:
            device_type: Target device type ("flagship" or "note"). Selects the
                matching welcome template. Falls back to ``DEFAULT_DEVICE_TYPE``
                when unknown so a future device_type doesn't crash this path.

        Returns:
            The created default page
        """
        resolved_device = device_type if device_type in DEFAULT_PAGE_TEMPLATES else DEFAULT_DEVICE_TYPE
        page = Page(
            name="Welcome",
            type="template",
            device_type=resolved_device,
            template=DEFAULT_PAGE_TEMPLATES[resolved_device],
            duration_seconds=300,
            created_at=datetime.now(UTC),
        )
        return self.storage.create(page)

    # Demo page operations

    def get_demo_page(self, plugin_id: str, device_type: str | None = None) -> Page | None:
        """Find the existing demo page for a plugin.

        Returns the page tagged with ``demo_plugin_id == plugin_id``.
        If *device_type* is provided, only pages matching that device type are returned.
        """
        for page in self.storage.list_all():
            if page.demo_plugin_id == plugin_id and (device_type is None or page.device_type == device_type):
                return page
        return None

    def create_demo_page(self, plugin_id: str, demo: DemoPageSchema) -> tuple[Page, bool]:
        """Create (or recreate) the demo page for a plugin.

        The singleton constraint is per plugin + device type: creating a demo for
        "flagship" does not delete an existing "note" demo, and vice versa.

        Returns:
            Tuple of (created_page, was_recreated)
        """
        line_metadata = None
        if demo.line_metadata:
            line_metadata = [
                LineMetadata(
                    alignment=m.get("alignment", "left"),
                    wrap=m.get("wrap", False),
                )
                for m in demo.line_metadata
            ]

        page = Page(
            name=demo.name,
            type="template",
            device_type=demo.device_type,
            template=demo.template,
            line_metadata=line_metadata,
            duration_seconds=demo.duration_seconds,
            demo_plugin_id=plugin_id,
            canvases=getattr(demo, "canvases", None),
            created_at=datetime.now(UTC),
        )

        # Built (and validated) before the old demo goes, so an invalid demo
        # leaves the existing page in place.
        recreated = False
        existing = self.get_demo_page(plugin_id, device_type=demo.device_type)
        if existing:
            self.storage.delete(existing.id)
            self._invalidate_cache(existing.id)
            recreated = True
            logger.info(f"Deleted existing demo page {existing.id} for plugin {plugin_id}")

        created = self.storage.create(page)
        logger.info(f"Created demo page {created.id} for plugin {plugin_id}")
        return created, recreated

    # Rendering

    def shared_context_for(
        self,
        contexts: dict[str, dict] | None,
        device_type: str,
        notes_wide: int = 1,
        notes_tall: int = 1,
        grid_rows: int | None = None,
        grid_cols: int | None = None,
        plugin_ids: Collection[str] | None = None,
        display: Any = None,
    ) -> dict | None:
        """Get-or-build the per-tick shared template context for one board size.

        ``contexts`` is a per-pass cache keyed by :func:`src.devices.size_key`
        (the display loop creates one dict per tick, issue #1752). The first
        consumer of a size pays the plugin fan-out; every later consumer of
        the same size — collection resolution, other boards' renders —
        reuses the same dict, exactly as ``preview_pages_batch`` already
        shares contexts per board size.

        ``plugin_ids`` narrows that fan-out to the plugins the consumer will
        actually read (issue #1751): a filtered build fetches only those ids
        (plus trigger plugins — the registry enforces that), and the cache
        remembers WHICH ids each size's context covers (a companion
        ``\\x00``-prefixed entry, invisible to templates). A later consumer
        needing more — another page's variables, or a fetch-all consumer like
        variable-mode collection resolution (``plugin_ids=None``) — widens
        the cached context by fetching only what it lacks, so no plugin is
        fetched twice in one pass.

        Returns None (caller falls back to building its own context, the
        pre-#1752 behavior) when ``contexts`` is None or the build fails.
        """
        if contexts is None:
            return None
        geometry = (device_type or DEFAULT_DEVICE_TYPE, notes_wide or 1, notes_tall or 1, grid_rows, grid_cols)
        key = size_key(*geometry)
        if display is not None:
            # One size, two displays (split-flap and LED): plugins that adapt
            # to the display get a context each.
            key = f"{key}|{display.key}"
        coverage_key = _CONTEXT_COVERAGE_PREFIX + key
        fingerprint_key = CONTEXT_FINGERPRINT_PREFIX + key
        try:
            from src.plugins.registry import get_plugin_registry

            registry = get_plugin_registry()
            context = contexts.get(key)
            if context is None:
                board = board_context_for(*geometry, display=display)
                fingerprints: dict[str, str] = {}
                if plugin_ids is None:
                    context = registry.build_template_context(board, fingerprints=fingerprints)
                    # No coverage entry: a fetch-all context covers everything.
                else:
                    context = registry.build_template_context(board, plugin_ids=plugin_ids, fingerprints=fingerprints)
                    contexts[coverage_key] = set(plugin_ids) | set(getattr(registry, "trigger_plugins", {}) or {})
                contexts[key] = context
                contexts[fingerprint_key] = fingerprints
                return context

            fetched = contexts.get(coverage_key)
            if fetched is None:
                return context  # built with fetch-all — covers every consumer

            if plugin_ids is not None:
                needed = set(plugin_ids)
            else:
                needed = set(getattr(registry, "enabled_plugins", {}) or {})
            missing = needed - fetched
            if not missing:
                return context

            board = board_context_for(*geometry)
            # Widening fetches EXACTLY the missing ids: the first build for
            # this size already fetched the trigger plugins (they are in
            # ``fetched``), so re-unioning them here would fetch each trigger
            # plugin once per widening consumer (#1862 review).
            widened: dict[str, str] = {}
            context.update(
                registry.build_template_context(
                    board, plugin_ids=missing, include_trigger_plugins=False, fingerprints=widened
                )
            )
            # Keep the hash companion covering exactly what the context holds:
            # a widening that added payloads without adding their hashes would
            # leave the render short-circuit hashing "absent" for live data.
            existing = contexts.get(fingerprint_key)
            if isinstance(existing, dict):
                existing.update(widened)
            else:
                contexts[fingerprint_key] = widened
            if plugin_ids is None:
                contexts.pop(coverage_key, None)  # widened to full coverage
            else:
                contexts[coverage_key] = fetched | missing
            return context
        except Exception as e:
            logger.error(f"Failed to build shared template context: {e}")
            return None

    def render_page(
        self,
        page: Page,
        context: dict | None = None,
        contexts: dict[str, dict] | None = None,
        *,
        extended_markup: bool = SPLIT_FLAP_EXTENDED_MARKUP,
        display: Any = None,
    ) -> DisplayResult:
        """Render a page to formatted text.

        Args:
            page: The page to render
            context: Optional pre-built template context to avoid redundant plugin fetches
            contexts: Optional per-tick shared context cache keyed by board
                size (see :meth:`shared_context_for`). Consulted only when
                ``context`` is not given.
            extended_markup: The target board speaks extended markup (its
                output's character set is rich; plan D19). Template pages
                only; the other page types have no template to render.

        Returns:
            DisplayResult with formatted text
        """
        canvases = page.canvases or []
        pixels = bool(canvases) and draws_pixels(display)
        if context is None and contexts is not None and (page.type == "template" or pixels):
            context = self.shared_context_for(
                contexts,
                *geometry_of(page),
                # Demand-driven fetch (issue #1751): only the plugins this
                # page's template and canvases reference. None (a formula
                # page) keeps the fetch-all fallback.
                plugin_ids=page_plugin_ids(page),
                display=display,
            )
        if context is None and pixels:
            # The canvases read the same context the template renders with.
            context = get_template_engine().build_context(
                board_context_for(*geometry_of(page), display=display), plugin_ids=page_plugin_ids(page)
            )
        if page.type == "single":
            result = self._render_single(page)
        elif page.type == "composite":
            result = self._render_composite(page)
        elif page.type == "template":
            result = self._render_template(page, context=context, extended_markup=extended_markup, display=display)
        else:
            return DisplayResult(
                display_type="page", formatted="", raw={}, available=False, error=f"Unknown page type: {page.type}"
            )
        if canvases and result.available:
            self._apply_canvases(page, result, context, extended_markup=extended_markup, display=display)
        return result

    @staticmethod
    def _apply_canvases(
        page: Page, result: DisplayResult, context: dict | None, *, extended_markup: bool, display: Any
    ) -> None:
        """Design §3: blank the cells under the page's canvases (every board),
        then, for a pixel-matrix *display*, rasterise them into ``result.layers``.

        ``flow`` canvases already kept text out of their cells
        (:meth:`_render_template`); this blanks every covered cell, so a
        ``hide`` canvas's text is gone and a non-template page's too. The
        layers are drawn on the board's own LED grid (its pixel size and the
        face its text size chose) with the page's variable *context*.
        """
        canvases = page.canvases or []
        dims = dimensions_of(page)
        result.formatted = get_template_engine().blank_cells(
            result.formatted, covered_cells(canvases, dims.rows, dims.cols), extended_markup=extended_markup
        )
        if not draws_pixels(display):
            return
        grid = grid_layout(display.width, display.height, display.font or DEFAULT_LED_FONT)
        layers, issues = render_canvases_on_grid(canvases, grid, context or {})
        result.layers = layers
        result.canvas_issues = issues

    @staticmethod
    def _board_for_page(page: Page) -> BoardContext:
        """Build a BoardContext for a page (note-array aware).

        Resolves note-array geometry from the page's notes_wide/notes_tall so a
        note-array page's plugins receive the board's true size, not flagship's.
        """
        return board_context_for(*geometry_of(page))

    @staticmethod
    def _board_key(page: Page) -> str:
        """Stable key identifying a page's board *size* for batch context sharing.

        Delegates to the canonical :func:`src.devices.size_key` so batch
        context sharing and page<->board compatibility use the same notion
        of "same board size". The key is opaque to its consumers.
        """
        return size_key(*geometry_of(page))

    def _render_single(self, page: Page) -> DisplayResult:
        """Render a single-source page."""
        if not page.display_type:
            return DisplayResult(
                display_type="page",
                formatted="",
                raw={"page_id": page.id},
                available=False,
                error="Single page missing display_type",
            )

        display_service = get_display_service()
        board = self._board_for_page(page)
        result = display_service.get_display(page.display_type, board=board)

        # Wrap result with page metadata
        return DisplayResult(
            display_type=f"page:{page.type}:{page.display_type}",
            formatted=result.formatted,
            raw={"page_id": page.id, "source_data": result.raw},
            available=result.available,
            error=result.error,
        )

    def _render_composite(self, page: Page) -> DisplayResult:
        """Render a composite page by combining rows from multiple sources."""
        if not page.rows:
            return DisplayResult(
                display_type="page",
                formatted="",
                raw={"page_id": page.id},
                available=False,
                error="Composite page missing row configuration",
            )

        dims = dimensions_of(page)
        display_service = get_display_service()
        board = self._board_for_page(page)

        # Initialize empty lines for the device
        output_lines = [" " * dims.cols] * dims.rows
        source_data = {}

        for row_config in page.rows:
            # Get the source display. The row source plugin receives the whole
            # board's context (full width/height) — it can't know its row budget.
            result = display_service.get_display(row_config.source, board=board)
            if not result.available:
                continue

            source_data[row_config.source] = result.raw

            source_lines = result.formatted.split("\n")

            # Get the specified row if it exists
            if row_config.row_index < len(source_lines):
                source_line = source_lines[row_config.row_index]
                # Pad or truncate to device width
                source_line = source_line[: dims.cols].ljust(dims.cols)
                if row_config.target_row < dims.rows:
                    output_lines[row_config.target_row] = source_line

        formatted = "\n".join(output_lines)

        return DisplayResult(
            display_type="page:composite",
            formatted=formatted,
            raw={"page_id": page.id, "sources": source_data},
            available=True,
        )

    def _render_template(
        self,
        page: Page,
        context: dict | None = None,
        *,
        extended_markup: bool = SPLIT_FLAP_EXTENDED_MARKUP,
        display: Any = None,
    ) -> DisplayResult:
        """Render a template page with variable substitution.

        Uses the template engine to:
        - Replace {{source.field}} variables
        - Process {color} markers
        - Process {symbol} shortcuts
        - Apply filters like |pad:3 or |upper

        Args:
            page: The page to render
            context: Optional pre-built template context to avoid redundant plugin fetches
        """
        if not page.template:
            return DisplayResult(
                display_type="page",
                formatted="",
                raw={"page_id": page.id},
                available=False,
                error="Template page missing template content",
            )

        try:
            template_engine = get_template_engine()

            # Render the template lines with variable substitution
            # The template engine already handles tile-aware truncation in render_lines()
            # via _truncate_to_tiles() - color codes like {63} count as 1 tile each
            meta = [m.model_dump() for m in page.line_metadata] if page.line_metadata else None
            spans = None
            if any(c.text == "flow" for c in page.canvases or ()):
                dims = dimensions_of(page)
                spans = free_spans(page.canvases, dims.rows, dims.cols)
            formatted = template_engine.render_lines(
                page.template,
                context=context,
                line_metadata=meta,
                device_type=page.device_type,
                notes_wide=page.notes_wide,
                notes_tall=page.notes_tall,
                grid_rows=page.grid_rows,
                grid_cols=page.grid_cols,
                extended_markup=extended_markup,
                display=display,
                free_spans=spans,
            )

            # Note: We do NOT truncate/pad by character count here because:
            # - Color codes like {63} are 4 characters but represent 1 tile
            # - The template engine already handles proper tile-aware truncation
            # - Truncating by character count would break color codes mid-syntax

            return DisplayResult(
                display_type="page:template",
                formatted=formatted,
                raw={"page_id": page.id, "template": page.template},
                available=True,
            )
        except Exception as e:
            logger.error(f"Failed to render template: {e}", exc_info=True)
            return DisplayResult(
                display_type="page:template",
                formatted="",
                raw={"page_id": page.id, "template": page.template},
                available=False,
                error=f"Template rendering failed: {e!s}",
            )

    def preview_page(
        self,
        page_id: str,
        force_refresh: bool = False,
        context: dict | None = None,
        contexts: dict[str, dict] | None = None,
        *,
        extended_markup: bool = SPLIT_FLAP_EXTENDED_MARKUP,
        display: Any = None,
    ) -> DisplayResult | None:
        """Preview a page by ID.

        Uses cached preview if available and valid, unless force_refresh is True.
        The cache speeds up preview requests for page grids while ensuring
        active pages and edits always get fresh data.

        Args:
            page_id: The page ID
            force_refresh: If True, bypass cache and always render fresh
            context: Optional pre-built template context (skips the plugin fan-out)
            contexts: Optional per-tick shared context cache keyed by board
                size (issue #1752); see :meth:`shared_context_for`
            extended_markup: Render with extended markup (see
                :meth:`render_page`). The preview cache holds the default
                render (:data:`~src.text_to_board.SPLIT_FLAP_EXTENDED_MARKUP`),
                which every board now shares; a render in the other mode
                neither reads nor writes it.

        Returns:
            DisplayResult or None if page not found
        """
        page = self.get_page(page_id)
        if not page:
            return None

        if extended_markup != SPLIT_FLAP_EXTENDED_MARKUP or display is not None:
            # A render for one display is that display's: the shared preview
            # cache holds the display-agnostic render and is neither read nor
            # written.
            return self.render_page(
                page, context=context, contexts=contexts, extended_markup=extended_markup, display=display
            )

        # Check cache first if not forcing refresh
        if not force_refresh:
            cached = self._preview_cache.get(page_id)
            if cached and cached.is_valid(page):
                logger.debug(f"Using cached preview for page {page_id}")
                return cached.result

        # Render fresh
        logger.debug(f"Rendering fresh preview for page {page_id} (force_refresh={force_refresh})")
        result = self.render_page(page, context=context, contexts=contexts)

        # Cache the result
        self._preview_cache[page_id] = CachedPreview(
            result=result, page_updated_at=page.updated_at, cached_at=time.time()
        )

        return result

    def preview_pages_batch(
        self,
        page_ids: list[str],
        force_refresh: bool = False,
        active_page_id: str | None = None,
        *,
        extended_markup: bool = SPLIT_FLAP_EXTENDED_MARKUP,
        display: Any = None,
    ) -> dict[str, DisplayResult | None]:
        """Preview multiple pages, building template context once for efficiency.

        When rendering multiple template pages, the template context (plugin data)
        is fetched once and shared across all page renders, avoiding redundant
        plugin data fetches.

        Args:
            page_ids: List of page IDs to preview
            force_refresh: If True, bypass cache for all pages
            active_page_id: If set, always force refresh for this page
            extended_markup: Render with extended markup (see
                :meth:`preview_page`): a render in the mode the preview cache
                does not hold renders every page fresh, and the cache is
                neither read nor written.

        Returns:
            Dict mapping page_id to DisplayResult (or None if page not found)
        """
        results: dict[str, DisplayResult | None] = {}
        pages_to_render: list[tuple[str, Page]] = []
        # A render for one display (or in the other markup mode) is that
        # display's: the shared preview cache is neither read nor written.
        uncached_mode = extended_markup != SPLIT_FLAP_EXTENDED_MARKUP or display is not None

        # First pass: check cache, collect pages that need rendering
        for page_id in page_ids:
            page = self.get_page(page_id)
            if not page:
                results[page_id] = None
                continue

            should_force = force_refresh or (page_id == active_page_id) or uncached_mode

            if not should_force:
                cached = self._preview_cache.get(page_id)
                if cached and cached.is_valid(page):
                    logger.debug(f"Using cached preview for page {page_id}")
                    results[page_id] = cached.result
                    continue

            pages_to_render.append((page_id, page))

        # Build shared template context once per distinct board *size*. Plugins
        # may emit different data per board size, so a single shared context
        # would be wrong when pages target different sizes; fanning out once per
        # distinct board (not per page) keeps the efficiency win. Note arrays of
        # different sizes are distinct boards (see _board_key).
        contexts_by_board: dict[str, dict] = {}
        boards: dict[str, BoardContext] = {}
        # Per-size fetch filters (issue #1751): the union of every batched
        # template page's referenced plugins for that size, or None (fetch
        # all) as soon as any page's references cannot be determined.
        ids_by_board: dict[str, Collection[str] | None] = {}
        for _, p in pages_to_render:
            if p.type != "template" and not (p.canvases and draws_pixels(display)):
                continue
            key = self._board_key(p)
            if key not in boards:
                boards[key] = board_context_for(*geometry_of(p), display=display)
            refs = page_plugin_ids(p)
            if key not in ids_by_board:
                ids_by_board[key] = set(refs) if refs is not None else None
            elif ids_by_board[key] is not None:
                ids_by_board[key] = ids_by_board[key] | refs if refs is not None else None
        if boards:
            try:
                from src.plugins.registry import get_plugin_registry

                contexts_by_board = get_plugin_registry().build_template_contexts_for(boards, plugin_ids=ids_by_board)
            except Exception as e:
                logger.error(f"Failed to build shared template context: {e}")

        # Second pass: render pages that missed cache
        for page_id, page in pages_to_render:
            try:
                context = contexts_by_board.get(self._board_key(page))
                result = self.render_page(page, context=context, extended_markup=extended_markup, display=display)
                if not uncached_mode:
                    self._preview_cache[page_id] = CachedPreview(
                        result=result, page_updated_at=page.updated_at, cached_at=time.time()
                    )

                results[page_id] = result
            except Exception as e:
                logger.error(f"Error rendering page {page_id}: {e}")
                results[page_id] = DisplayResult(
                    display_type="page", formatted="", raw={"page_id": page_id}, available=False, error=str(e)
                )

        return results

    def _invalidate_cache(self, page_id: str | None = None) -> None:
        """Invalidate preview cache.

        Args:
            page_id: Specific page ID to invalidate, or None to clear all
        """
        if page_id:
            self._preview_cache.pop(page_id, None)
        else:
            self._preview_cache.clear()

    def invalidate_preview_cache(self, page_id: str | None = None) -> None:
        """Public entry point for ``POST /pages/cache/clear``.

        The route used to call ``_invalidate_cache`` directly, which
        ``docs/internal/reference/API_CONVENTIONS.md`` bans ("Routes never
        touch another object's ``_private`` members"). The private method
        stays as the internal write-path hook the mutators call; this is the
        one the API is allowed to see, so the cache's shape can change without
        an endpoint changing with it.
        """
        self._invalidate_cache(page_id)

    def get_cache_stats(self) -> dict[str, any]:
        """Get cache statistics for monitoring.

        Returns:
            Dict with cache size and entry info
        """
        return {
            "cache_size": len(self._preview_cache),
            "cached_pages": list(self._preview_cache.keys()),
            "ttl_seconds": PREVIEW_CACHE_TTL,
        }


# Singleton instance
_page_service: PageService | None = None


def get_page_service() -> PageService:
    """Get or create the page service singleton."""
    global _page_service
    if _page_service is None:
        _page_service = PageService()
    return _page_service


# ---------------------------------------------------------------------------
# Page <-> board size compatibility (issue #1245)
# ---------------------------------------------------------------------------


@dataclass
class BoardCompatibility:
    """Result of validating a page/collection ref against a board.

    ``error`` is set when the write must be blocked (HTTP 400 at the API
    layer); ``warnings`` is a non-fatal list for collections whose members
    only partially fit the board.
    """

    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None


def _find_board(board_id: str | None) -> dict | None:
    """Resolve a board dict by id; ``None``/`""` resolve to the primary board.

    Returns None when the board (or any board at all) cannot be found —
    callers treat that as "cannot validate, don't block" for back-compat.
    """
    settings = get_settings_service()
    bid = board_id if board_id else settings.get_primary_board_id()
    if not bid:
        return None
    for board in settings.get_board_settings().boards or []:
        if isinstance(board, dict) and board.get("id") == bid:
            return board
    return None


def check_ref_board_compatibility(page_ref: str | None, board_id: str | None) -> BoardCompatibility:
    """Validate a page or ``collection:`` ref against a board's size.

    Rules (issue #1245):
      - A plain page must match the board's :func:`src.devices.size_key`
        exactly; a mismatch blocks the write.
      - A collection may mix sizes: it is blocked only when ZERO member
        pages fit the board; otherwise it passes with one warning per
        member page that does not fit.
      - Anything that cannot be resolved (missing page, unknown collection,
        unknown board, no boards configured) passes silently so legacy
        installs and defensive callers see zero behavior change.
    """
    result = BoardCompatibility()
    if not page_ref:
        return result

    try:
        board = _find_board(board_id)
        if board is None:
            return result

        board_label = f"'{board.get('name') or board.get('id')}' ({size_key(*geometry_of(board))})"
        page_service = get_page_service()

        from src.collections.models import is_collection_id

        if is_collection_id(page_ref):
            from src.collections.service import get_collection_service

            collection = get_collection_service().get_collection(page_ref)
            if not collection:
                return result
            members = [p for p in (page_service.get_page(pid) for pid in collection.page_ids) if p]
            if not members:
                return result
            misfits = [p for p in members if not pages_compatible_with_board(p, board)]
            if len(misfits) == len(members):
                result.error = (
                    f"Collection '{collection.name}' cannot be used on board {board_label}: "
                    f"none of its {len(members)} pages fit this board size."
                )
                return result
            result.warnings = [
                f"Page '{p.name}' ({size_key(*geometry_of(p))}) in "
                f"collection '{collection.name}' does not fit board {board_label} and will be skipped."
                for p in misfits
            ]
            return result

        page = page_service.get_page(page_ref)
        if page is None:
            return result
        if not pages_compatible_with_board(page, board):
            result.error = (
                f"Page '{page.name}' ({size_key(*geometry_of(page))}) "
                f"is not compatible with board {board_label}: page and board sizes must match exactly."
            )
        return result
    except Exception:  # pragma: no cover - defensive: never let validation crash a write
        logger.exception("Page/board compatibility check failed; allowing write")
        return BoardCompatibility()


def silence_page_id_for_board(board_id: str | None) -> str | None:
    """The page ref a board shows during silence, or None (issue #1788).

    Only meaningful when that board's silence mode is ``page``. Never raises —
    a failure here must not break a page save.
    """
    try:
        from src.config import Config

        silence = Config.silence_config_for(board_id)
        return silence["page_id"] if silence["mode"] == "page" else None
    except Exception:  # pragma: no cover - defensive
        logger.exception("Could not resolve silence page for board %s", board_id)
        return None


def find_incompatible_references(page: Page) -> list[dict]:
    """Find schedule/active-page/silence references the page no longer fits.

    Issue #1250, extended by #1788. After a device/size retarget, existing
    references may point the page at boards whose size no longer matches. This
    scans, for every board the page is now incompatible with:

      - schedule entries referencing the page directly or via a collection
        that contains it (``surface: "schedule"``, with ``schedule_id``)
      - the board's manual active page, direct or via a containing collection
        (``surface: "active_page"``)
      - the board's silence page when its silence mode is ``page``
        (``surface: "silence"``)

    Warn-only by design: nothing is mutated or auto-fixed — callers surface
    the returned refs to the user. Returns
    ``[{board_id, board_name, surface, schedule_id}]``; failures degrade to
    partial results rather than breaking the page save.
    """
    refs: list[dict] = []
    try:
        settings = get_settings_service()
        boards = [b for b in (settings.get_board_settings().boards or []) if isinstance(b, dict)]
        if not boards:
            return refs

        # Collections containing this page: a schedule/active-page ref to such
        # a collection references this page too (it would be skipped there).
        try:
            from src.collections.service import get_collection_service

            containing = {c.id for c in get_collection_service().list_collections() if page.id in c.page_ids}
        except Exception:
            logger.exception("Collection scan failed during stale-reference detection")
            containing = set()

        def references_page(ref: str | None) -> bool:
            return bool(ref) and (ref == page.id or ref in containing)

        from src.schedules.service import get_schedule_service

        schedule_service = get_schedule_service()

        for board in boards:
            if pages_compatible_with_board(page, board):
                continue
            board_id = board.get("id") or ""
            board_name = board.get("name") or board_id
            # list_schedules() already folds legacy board_id "" entries into
            # the primary board, so no extra mapping is needed here.
            for schedule in schedule_service.list_schedules(board_id=board_id):
                if references_page(schedule.page_id):
                    refs.append(
                        {
                            "board_id": board_id,
                            "board_name": board_name,
                            "surface": "schedule",
                            "schedule_id": schedule.id,
                        }
                    )
            if references_page(settings.get_active_page_id(board_id=board_id)):
                refs.append(
                    {
                        "board_id": board_id,
                        "board_name": board_name,
                        "surface": "active_page",
                        "schedule_id": None,
                    }
                )
            if references_page(silence_page_id_for_board(board_id)):
                refs.append(
                    {
                        "board_id": board_id,
                        "board_name": board_name,
                        "surface": "silence",
                        "schedule_id": None,
                    }
                )
    except Exception:  # pragma: no cover - defensive: never let the scan break a save
        logger.exception("Stale-reference detection failed; returning partial results")
    return refs


def find_incompatible_board_references(board: dict) -> list[dict]:
    """Find schedule/active-page refs whose pages no longer fit *board*.

    Board-side mirror of :func:`find_incompatible_references` for surfaces
    that reshape a board in place — a FiestaPanel TV-size edit re-fits its
    virtual board's grid, and pages authored for the old grid stay
    referenced but can no longer render (the send loop rejects the
    mismatched shape and the panel freezes on its last frame).

    Scans only *board*'s own references:

      - schedule entries whose page (direct, or via a containing collection)
        no longer matches the board's size (``surface: "schedule"``)
      - the board's manual active page, likewise (``surface: "active_page"``)

    Warn-only by design, like the page-side scan: nothing is mutated.
    Returns ``[{page_id, page_name, surface, schedule_id}]``; failures
    degrade to partial results rather than breaking the panel save.
    """
    refs: list[dict] = []
    try:
        board_id = (board or {}).get("id") or ""
        page_service = get_page_service()
        settings = get_settings_service()

        try:
            from src.collections.service import get_collection_service

            collection_pages = {c.id: list(c.page_ids) for c in get_collection_service().list_collections()}
        except Exception:
            logger.exception("Collection scan failed during board-side stale-reference detection")
            collection_pages = {}

        def misfit_pages(ref: str | None) -> list:
            """Pages behind *ref* (a page id or collection id) that no longer fit."""
            if not ref:
                return []
            out = []
            for page_id in collection_pages.get(ref, [ref]):
                page = page_service.get_page(page_id)
                if page is not None and not pages_compatible_with_board(page, board):
                    out.append(page)
            return out

        from src.schedules.service import get_schedule_service

        for schedule in get_schedule_service().list_schedules(board_id=board_id):
            for page in misfit_pages(schedule.page_id):
                refs.append(
                    {
                        "page_id": page.id,
                        "page_name": page.name,
                        "surface": "schedule",
                        "schedule_id": schedule.id,
                    }
                )
        for page in misfit_pages(settings.get_active_page_id(board_id=board_id)):
            refs.append(
                {
                    "page_id": page.id,
                    "page_name": page.name,
                    "surface": "active_page",
                    "schedule_id": None,
                }
            )
    except Exception:  # pragma: no cover - defensive: never let the scan break a save
        logger.exception("Board-side stale-reference detection failed; returning partial results")
    return refs
