"""JSON file-based storage for pages.

Provides simple persistence for page configurations that survives restarts.
Includes schema versioning and automatic migration on startup.
"""

import contextlib
import json
import logging
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from src.text_utils import extract_alignment_from_line as _extract_alignment_from_line

from .models import Page

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 4


# Mapping from obsolete plugin id (used in template variable references,
# `display_type` for single pages, and `rows[].source` for composite
# pages) to its replacement id. Driven by the same renames in
# `src/config_manager.py:PLUGIN_ID_RENAMES`; kept local here to avoid a
# cross-module import from a low-level storage layer.
_PLUGIN_ID_RENAMES: dict[str, str] = {
    "baywheels": "lyft_bike_share",
}


def _migrate_v0_to_v1(pages_data: list[dict]) -> int:
    """Migration 0 -> 1: extract inline alignment prefixes into line_metadata.

    Mutates *pages_data* in place.  Returns the number of pages migrated.
    """
    migrated_count = 0

    for page_data in pages_data:
        if page_data.get("type") != "template":
            continue
        template = page_data.get("template")
        if not template or not isinstance(template, list):
            continue
        if page_data.get("line_metadata") is not None:
            continue

        metadata: list[dict] = []
        clean_lines: list[str] = []

        for line in template:
            alignment, wrap_enabled, content = _extract_alignment_from_line(line)
            metadata.append({"alignment": alignment, "wrap": wrap_enabled})
            clean_lines.append(content)

        page_data["template"] = clean_lines
        page_data["line_metadata"] = metadata
        migrated_count += 1

    return migrated_count


def _migrate_v1_to_v2(pages_data: list[dict]) -> int:
    """Migration 1 -> 2: add demo_plugin_id field to all pages.

    Ensures every page has the ``demo_plugin_id`` key (defaults to ``None``).
    """
    migrated = 0
    for page_data in pages_data:
        if "demo_plugin_id" not in page_data:
            page_data["demo_plugin_id"] = None
            migrated += 1
    return migrated


def _build_plugin_id_rename_pattern() -> re.Pattern:
    """Build a single regex matching any obsolete plugin id from
    ``_PLUGIN_ID_RENAMES`` followed by a ``.`` (variable accessor).

    The negative lookbehind on ``[A-Za-z0-9_]`` ensures we don't match
    an id that's the suffix of a longer identifier (e.g. ``mybaywheels.``).
    """
    alternation = "|".join(re.escape(old_id) for old_id in _PLUGIN_ID_RENAMES)
    return re.compile(rf"(?<![A-Za-z0-9_])({alternation})\.")


_PLUGIN_ID_RENAME_PATTERN = _build_plugin_id_rename_pattern()


def _rewrite_plugin_id_references(text: str) -> tuple[str, int]:
    """Rewrite obsolete plugin id references in *text*.

    Replaces any occurrence of ``<old_id>.`` (where ``<old_id>`` is a key
    of ``_PLUGIN_ID_RENAMES``) that is not part of a longer identifier
    with ``<new_id>.``. Returns the rewritten string and the number of
    substitutions made. Catches both plain ``{{baywheels.x}}`` references
    and formula references like ``{{= baywheels.x + 1 }}``.
    """
    if not text or "." not in text:
        return text, 0

    def _sub(match: re.Match) -> str:
        return _PLUGIN_ID_RENAMES[match.group(1)] + "."

    new_text, n = _PLUGIN_ID_RENAME_PATTERN.subn(_sub, text)
    return new_text, n


def _migrate_v2_to_v3(pages_data: list[dict]) -> int:
    """Migration 2 -> 3: rewrite obsolete plugin id references.

    Updates pages that reference plugin ids listed in
    ``_PLUGIN_ID_RENAMES`` (e.g. ``baywheels`` → ``lyft_bike_share``):

    * Template strings: rewrites every ``<old_id>.<field>`` reference,
      including those inside ``{{ ... }}`` and ``{{= ... }}`` formulas.
    * Single pages: rewrites ``display_type`` if it equals an old id.
    * Composite pages: rewrites ``rows[].source`` if it equals an old id.
    * Demo-page tracking: rewrites ``demo_plugin_id`` if it equals an old id.

    Returns the number of pages that were modified.
    """
    migrated = 0
    for page_data in pages_data:
        page_changed = False

        # Template strings (template-type pages)
        template = page_data.get("template")
        if isinstance(template, list):
            new_template: list = []
            for line in template:
                if isinstance(line, str):
                    rewritten, count = _rewrite_plugin_id_references(line)
                    if count:
                        page_changed = True
                    new_template.append(rewritten)
                else:
                    new_template.append(line)
            if page_changed:
                page_data["template"] = new_template

        # Single-page display_type
        display_type = page_data.get("display_type")
        if isinstance(display_type, str) and display_type in _PLUGIN_ID_RENAMES:
            page_data["display_type"] = _PLUGIN_ID_RENAMES[display_type]
            page_changed = True

        # Composite-page row sources
        rows = page_data.get("rows")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                source = row.get("source")
                if isinstance(source, str) and source in _PLUGIN_ID_RENAMES:
                    row["source"] = _PLUGIN_ID_RENAMES[source]
                    page_changed = True

        # Demo-page tracking field
        demo_plugin_id = page_data.get("demo_plugin_id")
        if isinstance(demo_plugin_id, str) and demo_plugin_id in _PLUGIN_ID_RENAMES:
            page_data["demo_plugin_id"] = _PLUGIN_ID_RENAMES[demo_plugin_id]
            page_changed = True

        if page_changed:
            migrated += 1

    return migrated


def _migrate_v3_to_v4(pages_data: list[dict]) -> int:
    """Migration 3 -> 4: add notes_wide/notes_tall fields to all pages.

    Ensures every page has the ``notes_wide`` and ``notes_tall`` keys
    (defaults to ``1`` for both, matching the Page model field defaults).
    This migration is required because CLAUDE.md mandates schema versioning
    whenever new fields are added to the stored page format.

    Idempotent: pages that already have both fields are skipped.
    """
    migrated = 0
    for page_data in pages_data:
        changed = False
        if "notes_wide" not in page_data:
            page_data["notes_wide"] = 1
            changed = True
        if "notes_tall" not in page_data:
            page_data["notes_tall"] = 1
            changed = True
        if changed:
            migrated += 1
    return migrated


# Ordered list of (target_version, migration_function).
# Each function receives the raw pages list and returns the number of pages affected.
MIGRATIONS: list[tuple[int, Callable[[list[dict]], int]]] = [
    (1, _migrate_v0_to_v1),
    (2, _migrate_v1_to_v2),
    (3, _migrate_v2_to_v3),
    (4, _migrate_v3_to_v4),
]


class PageStorage:
    """JSON file-based storage for pages.

    Stores pages in a JSON file for simple persistence.
    Thread-safe for basic operations.
    """

    def __init__(self, storage_file: str | None = None):
        """Initialize page storage.

        Args:
            storage_file: Path to JSON storage file. Defaults to data/pages.json
        """
        if storage_file is None:
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            self.storage_file = data_dir / "pages.json"
        else:
            self.storage_file = Path(storage_file)

        # In-memory cache
        self._pages: dict[str, Page] = {}
        # Raw entries (post-migration) that failed Pydantic validation on load.
        # Round-tripped through _save so a transient parsing failure (e.g. a
        # bug in a migration, a renamed enum value) never silently deletes a
        # user's page from disk.
        self._failed_entries: list[dict] = []

        # Load existing pages (runs migrations if needed)
        self._load()

        logger.info(f"PageStorage initialized (file: {self.storage_file}, pages: {len(self._pages)})")

    def _run_migrations(self, data: dict) -> bool:
        """Run any pending schema migrations on raw JSON data.

        Returns True if any migrations were applied (caller should resave).
        """
        current_version = data.get("schema_version", 0)

        if current_version >= CURRENT_SCHEMA_VERSION:
            return False

        pages_list = data.get("pages", [])

        # Back up before first migration
        if self.storage_file.exists():
            backup_path = self.storage_file.with_suffix(f".json.v{current_version}_backup")
            if not backup_path.exists():
                try:
                    shutil.copy2(self.storage_file, backup_path)
                    logger.info(f"Created pre-migration backup at {backup_path}")
                except Exception as e:
                    logger.warning(f"Could not create backup: {e}")

        for target_version, migrate_fn in MIGRATIONS:
            if current_version >= target_version:
                continue
            count = migrate_fn(pages_list)
            logger.info(f"Pages schema migration v{current_version}->v{target_version}: {count} page(s) processed")
            current_version = target_version

        data["schema_version"] = CURRENT_SCHEMA_VERSION
        return True

    def _load(self) -> None:
        """Load pages from storage file, running migrations if needed."""
        if not self.storage_file.exists():
            self._pages = {}
            self._failed_entries = []
            return

        try:
            with self.storage_file.open() as f:
                data = json.load(f)

            needs_save = self._run_migrations(data)

            self._pages = {}
            self._failed_entries = []
            for page_data in data.get("pages", []):
                # Snapshot before datetime coercion so we can round-trip the
                # entry untouched if Pydantic validation fails below.
                raw_snapshot = dict(page_data) if isinstance(page_data, dict) else page_data
                try:
                    if isinstance(page_data, dict):
                        if "created_at" in page_data and isinstance(page_data["created_at"], str):
                            page_data["created_at"] = datetime.fromisoformat(page_data["created_at"])
                        if "updated_at" in page_data and isinstance(page_data["updated_at"], str):
                            page_data["updated_at"] = datetime.fromisoformat(page_data["updated_at"])

                    page = Page(**page_data)
                    self._pages[page.id] = page
                except Exception as e:
                    page_id = raw_snapshot.get("id", "<unknown>") if isinstance(raw_snapshot, dict) else "<unknown>"
                    logger.error(
                        "Failed to parse page %s; preserving raw entry to avoid data loss: %s",
                        page_id,
                        e,
                    )
                    self._failed_entries.append(raw_snapshot)

            if self._failed_entries:
                logger.error(
                    "Pages load preserved %d unparseable entr%s as-is in storage",
                    len(self._failed_entries),
                    "y" if len(self._failed_entries) == 1 else "ies",
                )

            logger.info(f"Loaded {len(self._pages)} pages from storage")

            if needs_save:
                self._save()
                logger.info("Saved migrated pages to storage")

        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load pages file: {e}")
            self._pages = {}
            self._failed_entries = []

    def _save(self) -> None:
        """Save pages to storage file.

        Writes to a sibling ``<file>.tmp`` and ``os.replace``s it into place
        so a mid-write crash (OOM, SIGKILL, power loss) never leaves a
        truncated file that would wipe in-memory state on reload (see #1304).
        """
        try:
            pages_out: list[dict] = []
            for page in self._pages.values():
                page_data = page.model_dump()
                # Convert datetime objects to ISO strings for JSON serialization
                if isinstance(page_data.get("created_at"), datetime):
                    page_data["created_at"] = page_data["created_at"].isoformat()
                if isinstance(page_data.get("updated_at"), datetime):
                    page_data["updated_at"] = page_data["updated_at"].isoformat()
                pages_out.append(page_data)

            # Round-trip any entries that failed to parse on load so a
            # follow-up save doesn't quietly delete them from disk.
            pages_out.extend(self._failed_entries)

            data = {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "pages": pages_out,
            }

            # Datetimes are already coerced to ISO strings while building
            # pages_out above (covers both parsed pages and preserved
            # _failed_entries), so write data straight out — atomically.
            tmp_path = self.storage_file.with_suffix(self.storage_file.suffix + ".tmp")
            try:
                with tmp_path.open("w") as f:
                    json.dump(data, f, indent=2)
                tmp_path.replace(self.storage_file)
            except BaseException:
                # Clean up the partial tmp file on any failure so we don't
                # leak it; the original storage file stays untouched.
                with contextlib.suppress(OSError):
                    tmp_path.unlink(missing_ok=True)
                raise

            logger.debug(f"Saved {len(self._pages)} pages to storage")

        except OSError as e:
            logger.error(f"Failed to save pages file: {e}")
            raise

    def list_all(self) -> list[Page]:
        """Get all stored pages.

        Returns:
            List of all pages, ordered alphabetically by name
        """
        pages = list(self._pages.values())
        pages.sort(key=lambda p: p.name.lower())
        return pages

    def get(self, page_id: str) -> Page | None:
        """Get a page by ID.

        Args:
            page_id: The page ID

        Returns:
            Page if found, None otherwise
        """
        return self._pages.get(page_id)

    def create(self, page: Page) -> Page:
        """Create a new page.

        Args:
            page: The page to create

        Returns:
            The created page

        Raises:
            ValueError: If page with same ID already exists
        """
        if page.id in self._pages:
            raise ValueError(f"Page with ID {page.id} already exists")

        # Validate
        errors = page.validate_config()
        if errors:
            raise ValueError(f"Invalid page configuration: {errors}")

        self._pages[page.id] = page
        self._save()

        logger.info(f"Created page: {page.id} ({page.name})")
        return page

    def update(self, page_id: str, updates: dict) -> Page | None:
        """Update an existing page.

        Args:
            page_id: The page ID
            updates: Dictionary of fields to update

        Returns:
            Updated page if found, None otherwise
        """
        if page_id not in self._pages:
            return None

        page = self._pages[page_id]

        # Apply updates
        page_dict = page.model_dump()
        # Fields that callers are allowed to clear back to None (e.g. removing a
        # per-page transition override). Without this allowset every nullable
        # field would be permanently sticky after first being set — see #1306.
        # demo_plugin_id is intentionally excluded: it's nullable on Page but
        # internally managed (set only at page creation, absent from PageUpdate),
        # so it must never be cleared through update().
        nullable_fields = {
            "display_type",
            "rows",
            "template",
            "line_metadata",
            "transition_strategy",
            "transition_interval_ms",
            "transition_step_size",
        }
        for key, value in updates.items():
            if key in page_dict and (value is not None or key in nullable_fields):
                page_dict[key] = value

        # Update timestamp
        page_dict["updated_at"] = datetime.now(UTC)

        # Recreate page with updates
        updated_page = Page(**page_dict)

        # Validate
        errors = updated_page.validate_config()
        if errors:
            raise ValueError(f"Invalid page configuration: {errors}")

        self._pages[page_id] = updated_page
        self._save()

        logger.info(f"Updated page: {page_id}")
        return updated_page

    def delete(self, page_id: str) -> bool:
        """Delete a page.

        Args:
            page_id: The page ID

        Returns:
            True if deleted, False if not found
        """
        if page_id not in self._pages:
            return False

        del self._pages[page_id]
        self._save()

        logger.info(f"Deleted page: {page_id}")
        return True

    def exists(self, page_id: str) -> bool:
        """Check if a page exists.

        Args:
            page_id: The page ID

        Returns:
            True if exists
        """
        return page_id in self._pages

    def count(self) -> int:
        """Get the number of stored pages."""
        return len(self._pages)
