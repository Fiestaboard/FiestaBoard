"""JSON file-based storage for FiestaPanel panels.

Mirrors the src/pages storage pattern: schema-versioned JSON with ordered
migrations, atomic writes via a staging file, and preservation of entries
that fail validation on load.
"""

import contextlib
import json
import logging
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from src.atomic_io import staging_path

from .models import Panel

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 2


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


# Ordered migrations: (target_version, function). Each function takes the raw
# panels list, mutates in place, and returns the number of entries processed.
MIGRATIONS: list[tuple[int, Callable[[list[dict]], int]]] = [
    (2, _migrate_v1_to_v2),
]


class PanelStorage:
    """JSON file-based storage for panels. Thread-safe for basic operations."""

    def __init__(self, storage_file: str | None = None):
        """Initialize panel storage.

        Args:
            storage_file: Path to JSON storage file. Defaults to data/panels.json
        """
        if storage_file is None:
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            self.storage_file = data_dir / "panels.json"
        else:
            self.storage_file = Path(storage_file)

        self._panels: dict[str, Panel] = {}
        # Raw entries (post-migration) that failed Pydantic validation on load.
        # Round-tripped through _save so a parsing failure never silently
        # deletes a user's panel from disk.
        self._failed_entries: list[dict] = []

        self._load()

        logger.info(f"PanelStorage initialized (file: {self.storage_file}, panels: {len(self._panels)})")

    def _run_migrations(self, data: dict) -> bool:
        """Run any pending schema migrations on raw JSON data.

        Returns True if any migrations were applied (caller should resave).
        """
        current_version = data.get("schema_version", 0)

        if current_version >= CURRENT_SCHEMA_VERSION:
            return False

        panels_list = data.get("panels", [])

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
            count = migrate_fn(panels_list)
            logger.info(f"Panels schema migration v{current_version}->v{target_version}: {count} panel(s) processed")
            current_version = target_version

        data["schema_version"] = CURRENT_SCHEMA_VERSION
        return True

    def _load(self) -> None:
        """Load panels from storage file, running migrations if needed."""
        if not self.storage_file.exists():
            self._panels = {}
            self._failed_entries = []
            return

        try:
            with self.storage_file.open() as f:
                data = json.load(f)

            needs_save = self._run_migrations(data)

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
        """Save panels to storage file atomically (staging file + replace)."""
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

            tmp_path = staging_path(self.storage_file)
            try:
                with tmp_path.open("w") as f:
                    json.dump(data, f, indent=2)
                tmp_path.replace(self.storage_file)
            except BaseException:
                with contextlib.suppress(OSError):
                    tmp_path.unlink(missing_ok=True)
                raise

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

    def get_by_short_code(self, short_code: int) -> Panel | None:
        """Get a panel by its TV-typable short code, or None."""
        for panel in self._panels.values():
            if panel.short_code == short_code:
                return panel
        return None

    def _next_short_code(self) -> int:
        """Lowest positive integer not already in use."""
        used = {p.short_code for p in self._panels.values()}
        code = 1
        while code in used:
            code += 1
        return code

    def create(self, panel: Panel) -> Panel:
        """Create a new panel.

        Raises:
            ValueError: If a panel with the same ID already exists.
        """
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
