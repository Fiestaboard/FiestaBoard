"""Page service for CRUD operations and rendering.

Provides high-level operations on pages including preview and send.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.devices import (
    DEFAULT_DEVICE_TYPE,
    BoardContext,
    board_context_for,
    pages_compatible_with_board,
    resolve_dimensions,
    size_key,
)
from src.displays.service import DisplayResult, get_display_service
from src.plugins.manifest import DemoPageSchema
from src.settings.service import get_settings_service
from src.templates.engine import get_template_engine

from .models import LineMetadata, Page, PageCreate, PageUpdate
from .storage import PageStorage

logger = logging.getLogger(__name__)


# Cache TTL in seconds for non-polling preview requests (e.g. UI preview list).
# The background polling loop bypasses this cache via force_refresh=True.
PREVIEW_CACHE_TTL = 120


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
            demo_plugin_id=data.demo_plugin_id,
            # PageCreate leaves W×H optional (None) — default to a single Note.
            notes_wide=data.notes_wide or 1,
            notes_tall=data.notes_tall or 1,
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

        # Device/size retarget (issue #1250): re-validate the prospective page
        # before persisting so a retarget can't strand an invalid config.
        # Lossy template truncation is accepted (handled at render time);
        # structural errors (composite rows out of range) are blocked.
        if any(key in updates for key in ("device_type", "notes_wide", "notes_tall")):
            existing = self.storage.get(page_id)
            if existing is not None:
                # Mirror storage.update() semantics: None never overwrites the
                # geometry fields, so validate with None values dropped.
                prospective = Page(**{**existing.model_dump(), **{k: v for k, v in updates.items() if v is not None}})
                errors = prospective.validate_config()
                if errors:
                    raise ValueError(f"Cannot retarget page: {'; '.join(errors)}")

        updated_page = self.storage.update(page_id, updates)

        # Invalidate preview cache for this page
        if updated_page:
            self._invalidate_cache(page_id)
            logger.debug(f"Invalidated preview cache for page {page_id}")

        return updated_page

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

        # Invalidate cache for deleted page
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
        recreated = False
        existing = self.get_demo_page(plugin_id, device_type=demo.device_type)
        if existing:
            self.storage.delete(existing.id)
            self._invalidate_cache(existing.id)
            recreated = True
            logger.info(f"Deleted existing demo page {existing.id} for plugin {plugin_id}")

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
            created_at=datetime.now(UTC),
        )

        created = self.storage.create(page)
        logger.info(f"Created demo page {created.id} for plugin {plugin_id}")
        return created, recreated

    # Rendering

    def render_page(self, page: Page, context: dict | None = None) -> DisplayResult:
        """Render a page to formatted text.

        Args:
            page: The page to render
            context: Optional pre-built template context to avoid redundant plugin fetches

        Returns:
            DisplayResult with formatted text
        """
        if page.type == "single":
            return self._render_single(page)
        if page.type == "composite":
            return self._render_composite(page)
        if page.type == "template":
            return self._render_template(page, context=context)
        return DisplayResult(
            display_type="page", formatted="", raw={}, available=False, error=f"Unknown page type: {page.type}"
        )

    @staticmethod
    def _board_for_page(page: Page) -> BoardContext:
        """Build a BoardContext for a page (note-array aware).

        Resolves note-array geometry from the page's notes_wide/notes_tall so a
        note-array page's plugins receive the board's true size, not flagship's.
        """
        return board_context_for(page.device_type, page.notes_wide, page.notes_tall)

    @staticmethod
    def _board_key(page: Page) -> str:
        """Stable key identifying a page's board *size* for batch context sharing.

        Delegates to the canonical :func:`src.devices.size_key` so batch
        context sharing and page<->board compatibility use the same notion
        of "same board size". The key is opaque to its consumers.
        """
        return size_key(page.device_type, page.notes_wide, page.notes_tall)

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

        dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
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

            # Split source into lines
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

    def _render_template(self, page: Page, context: dict | None = None) -> DisplayResult:
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
            formatted = template_engine.render_lines(
                page.template,
                context=context,
                line_metadata=meta,
                device_type=page.device_type,
                notes_wide=page.notes_wide,
                notes_tall=page.notes_tall,
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

    def preview_page(self, page_id: str, force_refresh: bool = False) -> DisplayResult | None:
        """Preview a page by ID.

        Uses cached preview if available and valid, unless force_refresh is True.
        The cache speeds up preview requests for page grids while ensuring
        active pages and edits always get fresh data.

        Args:
            page_id: The page ID
            force_refresh: If True, bypass cache and always render fresh

        Returns:
            DisplayResult or None if page not found
        """
        page = self.get_page(page_id)
        if not page:
            return None

        # Check cache first if not forcing refresh
        if not force_refresh:
            cached = self._preview_cache.get(page_id)
            if cached and cached.is_valid(page):
                logger.debug(f"Using cached preview for page {page_id}")
                return cached.result

        # Render fresh
        logger.debug(f"Rendering fresh preview for page {page_id} (force_refresh={force_refresh})")
        result = self.render_page(page)

        # Cache the result
        self._preview_cache[page_id] = CachedPreview(
            result=result, page_updated_at=page.updated_at, cached_at=time.time()
        )

        return result

    def preview_pages_batch(
        self, page_ids: list[str], force_refresh: bool = False, active_page_id: str | None = None
    ) -> dict[str, DisplayResult | None]:
        """Preview multiple pages, building template context once for efficiency.

        When rendering multiple template pages, the template context (plugin data)
        is fetched once and shared across all page renders, avoiding redundant
        plugin data fetches.

        Args:
            page_ids: List of page IDs to preview
            force_refresh: If True, bypass cache for all pages
            active_page_id: If set, always force refresh for this page

        Returns:
            Dict mapping page_id to DisplayResult (or None if page not found)
        """
        results: dict[str, DisplayResult | None] = {}
        pages_to_render: list[tuple[str, Page]] = []

        # First pass: check cache, collect pages that need rendering
        for page_id in page_ids:
            page = self.get_page(page_id)
            if not page:
                results[page_id] = None
                continue

            should_force = force_refresh or (page_id == active_page_id)

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
        for _, p in pages_to_render:
            if p.type != "template":
                continue
            key = self._board_key(p)
            if key not in boards:
                boards[key] = board_context_for(p.device_type, p.notes_wide, p.notes_tall)
        if boards:
            try:
                from src.plugins.registry import get_plugin_registry

                contexts_by_board = get_plugin_registry().build_template_contexts_for(boards)
            except Exception as e:
                logger.error(f"Failed to build shared template context: {e}")

        # Second pass: render pages that missed cache
        for page_id, page in pages_to_render:
            try:
                result = self.render_page(page, context=contexts_by_board.get(self._board_key(page)))

                # Cache the result
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

        board_label = f"'{board.get('name') or board.get('id')}' ({size_key(*_board_geometry(board))})"
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
                f"Page '{p.name}' ({size_key(p.device_type, p.notes_wide, p.notes_tall)}) in "
                f"collection '{collection.name}' does not fit board {board_label} and will be skipped."
                for p in misfits
            ]
            return result

        page = page_service.get_page(page_ref)
        if page is None:
            return result
        if not pages_compatible_with_board(page, board):
            result.error = (
                f"Page '{page.name}' ({size_key(page.device_type, page.notes_wide, page.notes_tall)}) "
                f"is not compatible with board {board_label}: page and board sizes must match exactly."
            )
        return result
    except Exception:  # pragma: no cover - defensive: never let validation crash a write
        logger.exception("Page/board compatibility check failed; allowing write")
        return BoardCompatibility()


def _board_geometry(board: dict) -> tuple[str, int, int]:
    """Board dict -> (device_type, notes_wide, notes_tall) with defaults."""
    return (
        board.get("device_type") or DEFAULT_DEVICE_TYPE,
        board.get("notes_wide") or 1,
        board.get("notes_tall") or 1,
    )


def find_incompatible_references(page: Page) -> list[dict]:
    """Find schedule/active-page references the page no longer fits (issue #1250).

    After a device/size retarget, existing references may point the page at
    boards whose size no longer matches. This scans, for every board the page
    is now incompatible with:

      - schedule entries referencing the page directly or via a collection
        that contains it (``surface: "schedule"``, with ``schedule_id``)
      - the board's manual active page, direct or via a containing collection
        (``surface: "active_page"``)

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
    except Exception:  # pragma: no cover - defensive: never let the scan break a save
        logger.exception("Stale-reference detection failed; returning partial results")
    return refs
