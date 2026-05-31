"""Page service for CRUD operations and rendering.

Provides high-level operations on pages including preview and send.
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from ..devices import get_dimensions
from ..displays.service import DisplayResult, get_display_service
from ..plugins.manifest import DemoPageSchema
from ..settings.service import get_settings_service
from ..templates.engine import get_template_engine
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
            created_at=datetime.now(UTC)
        )

        return self.storage.create(page)

    def update_page(self, page_id: str, data: PageUpdate) -> Page | None:
        """Update an existing page.

        Args:
            page_id: Page ID
            data: Update data

        Returns:
            Updated page or None if not found
        """
        updates = data.model_dump(exclude_unset=True)
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
        if not self.storage.exists(page_id):
            return DeleteResult(deleted=False)

        # Check if this page is the active display page
        settings_service = get_settings_service()
        is_active_page = settings_service.get_active_page_id() == page_id

        # Check if this is the last page
        if self.storage.count() == 1:
            # Create default page before deleting the last one
            default_page = self._create_default_page()
            logger.info(f"Created default page {default_page.id} before deleting last page {page_id}")

            # Now delete the original page
            self.storage.delete(page_id)

            # If deleted page was active, set the new default as active
            if is_active_page:
                settings_service.set_active_page_id(default_page.id)
                logger.info(f"Active page updated to new default: {default_page.id}")

            return DeleteResult(
                deleted=True,
                default_page_created=True,
                new_page_id=default_page.id,
                active_page_updated=is_active_page,
                new_active_page_id=default_page.id if is_active_page else None
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

        return DeleteResult(
            deleted=True,
            active_page_updated=is_active_page,
            new_active_page_id=new_active_id
        )

    def _create_default_page(self) -> Page:
        """Create and save a default welcome page.

        Returns:
            The created default page
        """
        page = Page(
            name="Welcome",
            type="template",
            template=DEFAULT_PAGE_TEMPLATE,
            duration_seconds=300,
            created_at=datetime.now(UTC)
        )
        return self.storage.create(page)

    # Demo page operations

    def get_demo_page(self, plugin_id: str, device_type: str | None = None) -> Page | None:
        """Find the existing demo page for a plugin.

        Returns the page tagged with ``demo_plugin_id == plugin_id``.
        If *device_type* is provided, only pages matching that device type are returned.
        """
        for page in self.storage.list_all():
            if page.demo_plugin_id == plugin_id:
                if device_type is None or page.device_type == device_type:
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
        elif page.type == "composite":
            return self._render_composite(page)
        elif page.type == "template":
            return self._render_template(page, context=context)
        else:
            return DisplayResult(
                display_type="page",
                formatted="",
                raw={},
                available=False,
                error=f"Unknown page type: {page.type}"
            )

    def _render_single(self, page: Page) -> DisplayResult:
        """Render a single-source page."""
        if not page.display_type:
            return DisplayResult(
                display_type="page",
                formatted="",
                raw={"page_id": page.id},
                available=False,
                error="Single page missing display_type"
            )

        display_service = get_display_service()
        result = display_service.get_display(page.display_type)

        # Wrap result with page metadata
        return DisplayResult(
            display_type=f"page:{page.type}:{page.display_type}",
            formatted=result.formatted,
            raw={"page_id": page.id, "source_data": result.raw},
            available=result.available,
            error=result.error
        )

    def _render_composite(self, page: Page) -> DisplayResult:
        """Render a composite page by combining rows from multiple sources."""
        if not page.rows:
            return DisplayResult(
                display_type="page",
                formatted="",
                raw={"page_id": page.id},
                available=False,
                error="Composite page missing row configuration"
            )

        dims = get_dimensions(page.device_type)
        display_service = get_display_service()

        # Initialize empty lines for the device
        output_lines = [" " * dims.cols] * dims.rows
        source_data = {}

        for row_config in page.rows:
            # Get the source display
            result = display_service.get_display(row_config.source)
            if not result.available:
                continue

            source_data[row_config.source] = result.raw

            # Split source into lines
            source_lines = result.formatted.split('\n')

            # Get the specified row if it exists
            if row_config.row_index < len(source_lines):
                source_line = source_lines[row_config.row_index]
                # Pad or truncate to device width
                source_line = source_line[:dims.cols].ljust(dims.cols)
                if row_config.target_row < dims.rows:
                    output_lines[row_config.target_row] = source_line

        formatted = '\n'.join(output_lines)

        return DisplayResult(
            display_type="page:composite",
            formatted=formatted,
            raw={"page_id": page.id, "sources": source_data},
            available=True
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
                error="Template page missing template content"
            )

        try:
            template_engine = get_template_engine()

            # Render the template lines with variable substitution
            # The template engine already handles tile-aware truncation in render_lines()
            # via _truncate_to_tiles() - color codes like {63} count as 1 tile each
            meta = [m.model_dump() for m in page.line_metadata] if page.line_metadata else None
            formatted = template_engine.render_lines(page.template, context=context, line_metadata=meta, device_type=page.device_type)

            # Note: We do NOT truncate/pad by character count here because:
            # - Color codes like {63} are 4 characters but represent 1 tile
            # - The template engine already handles proper tile-aware truncation
            # - Truncating by character count would break color codes mid-syntax

            return DisplayResult(
                display_type="page:template",
                formatted=formatted,
                raw={"page_id": page.id, "template": page.template},
                available=True
            )
        except Exception as e:
            logger.error(f"Failed to render template: {e}", exc_info=True)
            return DisplayResult(
                display_type="page:template",
                formatted="",
                raw={"page_id": page.id, "template": page.template},
                available=False,
                error=f"Template rendering failed: {str(e)}"
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
            result=result,
            page_updated_at=page.updated_at,
            cached_at=time.time()
        )

        return result

    def preview_pages_batch(self, page_ids: list[str], force_refresh: bool = False,
                            active_page_id: str | None = None) -> dict[str, DisplayResult | None]:
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

        # Build shared template context once if any template pages need rendering
        shared_context = None
        has_template_pages = any(p.type == "template" for _, p in pages_to_render)
        if has_template_pages:
            try:
                template_engine = get_template_engine()
                shared_context = template_engine._build_context()
            except Exception as e:
                logger.error(f"Failed to build shared template context: {e}")

        # Second pass: render pages that missed cache
        for page_id, page in pages_to_render:
            try:
                result = self.render_page(page, context=shared_context)

                # Cache the result
                self._preview_cache[page_id] = CachedPreview(
                    result=result,
                    page_updated_at=page.updated_at,
                    cached_at=time.time()
                )

                results[page_id] = result
            except Exception as e:
                logger.error(f"Error rendering page {page_id}: {e}")
                results[page_id] = DisplayResult(
                    display_type="page",
                    formatted="",
                    raw={"page_id": page_id},
                    available=False,
                    error=str(e)
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
            "ttl_seconds": PREVIEW_CACHE_TTL
        }


# Singleton instance
_page_service: PageService | None = None


def get_page_service() -> PageService:
    """Get or create the page service singleton."""
    global _page_service
    if _page_service is None:
        _page_service = PageService()
    return _page_service

