"""JSON file-based storage for FiestaPanel panels.

Mirrors the src/pages storage pattern: schema-versioned JSON with ordered
migrations, atomic writes via a staging file, and preservation of entries
that fail validation on load.
"""

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from src.storage.json_store import JsonStore

from .models import Panel

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 5


def _migrate_v1_to_v2(panels_data: list[dict]) -> int:
    """Migration 1 -> 2: backfill short_code for TV-typable /p/{n} URLs.

    Codes are assigned in stable id order, lowest free integer first, and
    entries that somehow already carry a positive code keep it (idempotent).
    """
    used = {
        p.get("short_code") for p in panels_data if isinstance(p.get("short_code"), int) and p.get("short_code", 0) > 0
    }
    migrated = 0
    next_code = 1
    for panel_data in sorted(
        (p for p in panels_data if isinstance(p, dict)),
        key=lambda p: str(p.get("id", "")),
    ):
        if isinstance(panel_data.get("short_code"), int) and panel_data["short_code"] > 0:
            continue
        while next_code in used:
            next_code += 1
        panel_data["short_code"] = next_code
        used.add(next_code)
        migrated += 1
    return migrated


def _migrate_v2_to_v3(panels_data: list[dict]) -> int:
    """Migration 2 -> 3: stamp the animations_enabled default (off) explicitly."""
    migrated = 0
    for panel_data in panels_data:
        if isinstance(panel_data, dict) and "animations_enabled" not in panel_data:
            panel_data["animations_enabled"] = False
            migrated += 1
    return migrated


def _migrate_v3_to_v4(panels_data: list[dict]) -> int:
    """Migration 3 -> 4: stamp the is_display default (no panel designated)."""
    migrated = 0
    for panel_data in panels_data:
        if isinstance(panel_data, dict) and "is_display" not in panel_data:
            panel_data["is_display"] = False
            migrated += 1
    return migrated


def _migrate_v4_to_v5(panels_data: list[dict]) -> int:
    """Migration 4 -> 5: stamp the default 16:9 screen aspect explicitly.

    Panels created before aspect ratios existed were all sized assuming a
    16:9 screen, so that is what they keep.
    """
    migrated = 0
    for panel_data in panels_data:
        if isinstance(panel_data, dict) and (
            "screen_aspect_w" not in panel_data or "screen_aspect_h" not in panel_data
        ):
            panel_data.setdefault("screen_aspect_w", 16.0)
            panel_data.setdefault("screen_aspect_h", 9.0)
            migrated += 1
    return migrated


# Ordered migrations: (target_version, function). Each function takes the raw
# panels list, mutates in place, and returns the number of entries processed.
MIGRATIONS: list[tuple[int, Callable[[list[dict]], int]]] = [
    (2, _migrate_v1_to_v2),
    (3, _migrate_v2_to_v3),
    (4, _migrate_v3_to_v4),
    (5, _migrate_v4_to_v5),
]


def _adapt_migration(fn: Callable[[list[dict]], int]) -> Callable[[dict], int]:
    """Adapt a panels-list migration to the kernel's whole-document signature."""
    return lambda data: fn(data.get("panels", []))


class PanelStorage:
    """JSON file-based storage for panels. Thread-safe for basic operations."""

    def __init__(self, storage_file: str | None = None):
        """Initialize panel storage.

        Args:
            storage_file: Path to JSON storage file. Defaults to data/panels.json
        """
        self._store = JsonStore(
            "panels.json" if storage_file is None else storage_file,
            current_schema_version=CURRENT_SCHEMA_VERSION,
            migrations=[(version, _adapt_migration(fn)) for version, fn in MIGRATIONS],
            label="Panels",
        )
        self.storage_file = self._store.path

        self._panels: dict[str, Panel] = {}
        # Raw entries (post-migration) that failed Pydantic validation on load.
        # Round-tripped through _save so a parsing failure never silently
        # deletes a user's panel from disk.
        self._failed_entries: list[dict] = []

        self._load()

        logger.info(f"PanelStorage initialized (file: {self.storage_file}, panels: {len(self._panels)})")

    @property
    def lock(self) -> threading.RLock:
        """The kernel store's lock, for out-of-band writers of this file
        (the backup restore, #1860) to serialise against normal saves."""
        return self._store.lock

    def _load(self) -> None:
        """Load panels from storage file, running migrations if needed."""
        try:
            data = self._store.load()
            if data is None:
                self._panels = {}
                self._failed_entries = []
                return

            needs_save = self._store.migrated

            self._panels = {}
            self._failed_entries = []
            for panel_data in data.get("panels", []):
                raw_snapshot = dict(panel_data) if isinstance(panel_data, dict) else panel_data
                try:
                    if isinstance(panel_data, dict):
                        for key in ("created_at", "updated_at"):
                            if key in panel_data and isinstance(panel_data[key], str):
                                panel_data[key] = datetime.fromisoformat(panel_data[key])

                    panel = Panel(**panel_data)
                    self._panels[panel.id] = panel
                except Exception as e:
                    panel_id = raw_snapshot.get("id", "<unknown>") if isinstance(raw_snapshot, dict) else "<unknown>"
                    logger.error(
                        "Failed to parse panel %s; preserving raw entry to avoid data loss: %s",
                        panel_id,
                        e,
                    )
                    self._failed_entries.append(raw_snapshot)

            if self._failed_entries:
                logger.error(
                    "Panels load preserved %d unparseable entr%s as-is in storage",
                    len(self._failed_entries),
                    "y" if len(self._failed_entries) == 1 else "ies",
                )

            logger.info(f"Loaded {len(self._panels)} panels from storage")

            if needs_save:
                self._save()
                logger.info("Saved migrated panels to storage")

        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load panels file: {e}")
            self._panels = {}
            self._failed_entries = []

    def _save(self) -> None:
        """Save panels to storage file atomically via the storage kernel."""
        try:
            panels_out: list[dict] = []
            for panel in self._panels.values():
                panel_data = panel.model_dump()
                for key in ("created_at", "updated_at"):
                    if isinstance(panel_data.get(key), datetime):
                        panel_data[key] = panel_data[key].isoformat()
                panels_out.append(panel_data)

            # Round-trip entries that failed to parse on load so a follow-up
            # save doesn't quietly delete them from disk.
            panels_out.extend(self._failed_entries)

            data = {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "panels": panels_out,
            }

            self._store.save(data)

            logger.debug(f"Saved {len(self._panels)} panels to storage")

        except OSError as e:
            logger.error(f"Failed to save panels file: {e}")
            raise

    def list_all(self) -> list[Panel]:
        """All panels, ordered alphabetically by name."""
        panels = list(self._panels.values())
        panels.sort(key=lambda p: p.name.lower())
        return panels

    def get(self, panel_id: str) -> Panel | None:
        """Get a panel by ID, or None."""
        return self._panels.get(panel_id)

    def get_display_panel(self) -> Panel | None:
        """The panel currently designated as the local display, or None."""
        for panel in self._panels.values():
            if panel.is_display:
                return panel
        return None

    def get_by_short_code(self, short_code: int) -> Panel | None:
        """Get a panel by its TV-typable short code, or None."""
        for panel in self._panels.values():
            if panel.short_code == short_code:
                return panel
        return None

    def _next_short_code(self) -> int:
        """Lowest positive integer not already in use.

        Codes held by unparseable preserved entries count as in use too —
        those entries round-trip through every save, so reissuing their code
        would put two panels with the same short_code on disk and make
        /p/{n} resolution order-dependent.
        """
        used = {p.short_code for p in self._panels.values()}
        for entry in self._failed_entries:
            if isinstance(entry, dict) and isinstance(entry.get("short_code"), int):
                used.add(entry["short_code"])
        code = 1
        while code in used:
            code += 1
        return code

    def create(self, panel: Panel) -> Panel:
        """Create a new panel.

        Raises:
            ValueError: If a panel with the same ID already exists.
        """
        with self._store.lock:
            if panel.id in self._panels:
                raise ValueError(f"Panel with ID {panel.id} already exists")

            if panel.short_code <= 0:
                panel = panel.model_copy(update={"short_code": self._next_short_code()})

            self._panels[panel.id] = panel
            self._save()

        logger.info(f"Created panel: {panel.id} ({panel.name})")
        return panel

    def update(self, panel_id: str, updates: dict) -> Panel | None:
        """Update an existing panel from a dict of changed fields.

        Returns the updated panel, or None when the id is unknown.
        """
        with self._store.lock:
            if panel_id not in self._panels:
                return None

            panel_dict = self._panels[panel_id].model_dump()
            for key, value in updates.items():
                if key in panel_dict and value is not None:
                    panel_dict[key] = value

            panel_dict["updated_at"] = datetime.now(UTC)

            updated_panel = Panel(**panel_dict)
            self._panels[panel_id] = updated_panel
            self._save()

        logger.info(f"Updated panel: {panel_id}")
        return updated_panel

    def delete(self, panel_id: str) -> bool:
        """Delete a panel. Returns True if it existed."""
        with self._store.lock:
            if panel_id not in self._panels:
                return False

            del self._panels[panel_id]
            self._save()

        logger.info(f"Deleted panel: {panel_id}")
        return True

    def exists(self, panel_id: str) -> bool:
        return panel_id in self._panels

    def count(self) -> int:
        return len(self._panels)
