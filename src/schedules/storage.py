"""JSON file-based storage for schedule entries.

Provides simple persistence for schedule configurations that survives restarts.
Includes schema versioning and automatic migration on startup.
"""

import contextlib
import json
import logging
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .models import DEFAULT_BOARD_ID, ScheduleEntry

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 2

_LEGACY_CAROUSEL_PREFIX = "carousel:"
_COLLECTION_PREFIX = "collection:"


def _rewrite_carousel_ref(ref: str | None) -> tuple[str | None, bool]:
    """Rewrite a single ``carousel:<uuid>`` reference to ``collection:<uuid>``.

    Returns ``(new_ref, changed)``. Non-carousel and falsy refs pass through.
    """
    if isinstance(ref, str) and ref.startswith(_LEGACY_CAROUSEL_PREFIX):
        return _COLLECTION_PREFIX + ref[len(_LEGACY_CAROUSEL_PREFIX) :], True
    return ref, False


def _migrate_v0_to_v1(data: dict) -> int:
    """Migration 0 -> 1: introduce recurrence_type field (defaults to 'weekly').

    Pre-existing entries had no recurrence concept, so they all map to weekly.
    Date-override fields default to None and don't need to be written explicitly,
    but we set recurrence_type so reload + resave produces consistent JSON.
    """
    migrated = 0
    for entry in data.get("schedules", []) or []:
        if "recurrence_type" not in entry:
            entry["recurrence_type"] = "weekly"
            migrated += 1
    return migrated


def _migrate_v1_to_v2(data: dict) -> int:
    """Migration 1 -> 2: rewrite ``carousel:<uuid>`` refs to ``collection:<uuid>``.

    Walks every persisted ``page_id`` slot (per-schedule, board defaults,
    legacy global default) and rewrites in place. Returns the total number
    of references rewritten.
    """
    rewrites = 0

    for schedule in data.get("schedules", []) or []:
        new_ref, changed = _rewrite_carousel_ref(schedule.get("page_id"))
        if changed:
            schedule["page_id"] = new_ref
            rewrites += 1

    default_ref, changed = _rewrite_carousel_ref(data.get("default_page_id"))
    if changed:
        data["default_page_id"] = default_ref
        rewrites += 1

    board_defaults = data.get("default_page_by_board") or {}
    for board_id, page_ref in list(board_defaults.items()):
        new_ref, changed = _rewrite_carousel_ref(page_ref)
        if changed:
            board_defaults[board_id] = new_ref
            rewrites += 1
    if board_defaults:
        data["default_page_by_board"] = board_defaults

    return rewrites


MIGRATIONS: list[tuple[int, Callable[[dict], int]]] = [
    (1, _migrate_v0_to_v1),
    (2, _migrate_v1_to_v2),
]


class ScheduleStorage:
    """JSON file-based storage for schedule entries.

    Stores schedules and default page configuration in a JSON file for
    simple persistence. Thread-safe for basic operations.
    """

    def __init__(self, storage_file: str | None = None):
        """Initialize schedule storage.

        Args:
            storage_file: Path to JSON storage file. Defaults to data/schedules.json
        """
        if storage_file is None:
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            self.storage_file = data_dir / "schedules.json"
        else:
            self.storage_file = Path(storage_file)

        # In-memory cache
        self._schedules: dict[str, ScheduleEntry] = {}
        self._default_page_id: str | None = None  # legacy single default
        self._default_page_by_board: dict[str, str] = {}  # board_id -> page_id
        # Raw entries (post-migration) that failed Pydantic validation on load.
        # Round-tripped through _save so a transient parsing failure (e.g. a
        # bug in a migration, a renamed enum value) never silently deletes a
        # user's schedule from disk.
        self._failed_entries: list[dict] = []

        # Load existing schedules
        self._load()

        logger.info(f"ScheduleStorage initialized (file: {self.storage_file}, schedules: {len(self._schedules)})")

    def _run_migrations(self, data: dict) -> bool:
        """Run any pending schema migrations on raw JSON data.

        Returns True if any migrations were applied (caller should resave).
        """
        current_version = data.get("schema_version", 0)

        if current_version >= CURRENT_SCHEMA_VERSION:
            return False

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
            count = migrate_fn(data)
            logger.info(f"Schedules schema migration v{current_version}->v{target_version}: {count} change(s) applied")
            current_version = target_version

        data["schema_version"] = CURRENT_SCHEMA_VERSION
        return True

    def _load(self) -> None:
        """Load schedules from storage file, running migrations if needed."""
        if not self.storage_file.exists():
            self._schedules = {}
            self._default_page_id = None
            self._default_page_by_board = {}
            self._failed_entries = []
            return

        try:
            # Use builtins.open (not Path.open) so existing tests can
            # patch builtins.open to inject I/O errors.
            with open(self.storage_file) as f:  # noqa: PTH123
                data = json.load(f)

            needs_save = self._run_migrations(data)

            self._schedules = {}
            self._failed_entries = []
            for schedule_data in data.get("schedules", []):
                # Snapshot before datetime coercion so we can round-trip the
                # entry untouched if Pydantic validation fails below.
                raw_snapshot = dict(schedule_data) if isinstance(schedule_data, dict) else schedule_data
                try:
                    if isinstance(schedule_data, dict):
                        if "board_id" not in schedule_data:
                            schedule_data["board_id"] = DEFAULT_BOARD_ID
                        if "created_at" in schedule_data and isinstance(schedule_data["created_at"], str):
                            schedule_data["created_at"] = datetime.fromisoformat(schedule_data["created_at"])
                        if "updated_at" in schedule_data and isinstance(schedule_data["updated_at"], str):
                            schedule_data["updated_at"] = datetime.fromisoformat(schedule_data["updated_at"])

                    schedule = ScheduleEntry(**schedule_data)
                    self._schedules[schedule.id] = schedule
                except Exception as e:
                    schedule_id = raw_snapshot.get("id", "<unknown>") if isinstance(raw_snapshot, dict) else "<unknown>"
                    logger.error(
                        "Failed to parse schedule %s; preserving raw entry to avoid data loss: %s",
                        schedule_id,
                        e,
                    )
                    self._failed_entries.append(raw_snapshot)

            if self._failed_entries:
                logger.error(
                    "Schedules load preserved %d unparseable entr%s as-is in storage",
                    len(self._failed_entries),
                    "y" if len(self._failed_entries) == 1 else "ies",
                )

            self._default_page_id = data.get("default_page_id")
            self._default_page_by_board = dict(data.get("default_page_by_board") or {})

            logger.info(f"Loaded {len(self._schedules)} schedules from storage")

            if needs_save:
                self._save()
                logger.info("Saved migrated schedules to storage")

        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load schedules file: {e}")
            self._schedules = {}
            self._default_page_id = None
            self._default_page_by_board = {}
            self._failed_entries = []

    def _save(self) -> None:
        """Save schedules to storage file.

        Writes to a sibling ``<file>.tmp`` and ``os.replace``s it into place
        so a mid-write crash (OOM, SIGKILL, power loss) never leaves a
        truncated file that would wipe in-memory state on reload (see #1304).
        """
        try:
            schedules_out: list[dict] = []
            for schedule in self._schedules.values():
                schedule_data = schedule.model_dump()
                # Convert datetime objects to ISO strings for JSON serialization
                if isinstance(schedule_data.get("created_at"), datetime):
                    schedule_data["created_at"] = schedule_data["created_at"].isoformat()
                if isinstance(schedule_data.get("updated_at"), datetime):
                    schedule_data["updated_at"] = schedule_data["updated_at"].isoformat()
                schedules_out.append(schedule_data)

            # Round-trip any entries that failed to parse on load so a
            # follow-up save doesn't quietly delete them from disk.
            schedules_out.extend(self._failed_entries)

            data = {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "schedules": schedules_out,
                "default_page_id": self._default_page_id,
                "default_page_by_board": self._default_page_by_board,
            }

            # Datetimes are already coerced to ISO strings while building
            # schedules_out above (covers both parsed schedules and preserved
            # _failed_entries), so write data straight out — atomically.
            tmp_path = self.storage_file.with_suffix(self.storage_file.suffix + ".tmp")
            try:
                # Use builtins.open (not Path.open) on the tmp path so existing
                # tests can patch builtins.open to inject I/O errors.
                with open(tmp_path, "w") as f:  # noqa: PTH123
                    json.dump(data, f, indent=2)
                tmp_path.replace(self.storage_file)
            except BaseException:
                # Clean up the partial tmp file on any failure so we don't
                # leak it; the original storage file stays untouched.
                with contextlib.suppress(OSError):
                    tmp_path.unlink(missing_ok=True)
                raise

            logger.debug(f"Saved {len(self._schedules)} schedules to storage")

        except OSError as e:
            logger.error(f"Failed to save schedules file: {e}")
            raise

    def list_all(self, board_id: str | None = None) -> list[ScheduleEntry]:
        """Get stored schedules, optionally filtered by board_id.

        Args:
            board_id: Filter by board_id. None returns default board schedules.
                     Use explicit "*" to get ALL schedules across all boards (for cleanup/admin).

        Returns:
            List of schedules (for board_id if given), ordered by created_at
        """
        if board_id == "*":
            # Return all schedules across all boards
            schedules = list(self._schedules.values())
        else:
            bid = board_id if board_id is not None else DEFAULT_BOARD_ID
            schedules = [
                s for s in self._schedules.values() if (s.board_id or DEFAULT_BOARD_ID) == (bid or DEFAULT_BOARD_ID)
            ]
        schedules.sort(key=lambda s: s.created_at)
        return schedules

    def get(self, schedule_id: str) -> ScheduleEntry | None:
        """Get a schedule by ID.

        Args:
            schedule_id: The schedule ID

        Returns:
            ScheduleEntry if found, None otherwise
        """
        return self._schedules.get(schedule_id)

    def create(self, schedule: ScheduleEntry) -> ScheduleEntry:
        """Create a new schedule entry."""
        if schedule.id in self._schedules:
            raise ValueError(f"Schedule with ID {schedule.id} already exists")
        if not schedule.board_id:
            schedule.board_id = DEFAULT_BOARD_ID
        errors = schedule.validate_config()
        if errors:
            raise ValueError(f"Invalid schedule configuration: {errors}")
        self._schedules[schedule.id] = schedule
        self._save()
        logger.info(f"Created schedule: {schedule.id} (board_id={schedule.board_id})")
        return schedule

    def update(self, schedule_id: str, updates: dict) -> ScheduleEntry | None:
        """Update an existing schedule.

        Args:
            schedule_id: The schedule ID
            updates: Dictionary of fields to update

        Returns:
            Updated schedule if found, None otherwise
        """
        if schedule_id not in self._schedules:
            return None

        schedule = self._schedules[schedule_id]

        # Apply updates
        schedule_dict = schedule.model_dump()
        # Fields that are allowed to be set to None explicitly
        nullable_fields = {
            "end_time",
            "annual_date",
            "annual_end_date",
            "one_off_date",
            "one_off_end_date",
        }
        for key, value in updates.items():
            if key in schedule_dict and (value is not None or key in nullable_fields):
                schedule_dict[key] = value

        # Update timestamp
        schedule_dict["updated_at"] = datetime.now(UTC)

        # Recreate schedule with updates
        updated_schedule = ScheduleEntry(**schedule_dict)

        # Validate
        errors = updated_schedule.validate_config()
        if errors:
            raise ValueError(f"Invalid schedule configuration: {errors}")

        self._schedules[schedule_id] = updated_schedule
        self._save()

        logger.info(f"Updated schedule: {schedule_id}")
        return updated_schedule

    def delete(self, schedule_id: str) -> bool:
        """Delete a schedule.

        Args:
            schedule_id: The schedule ID

        Returns:
            True if deleted, False if not found
        """
        if schedule_id not in self._schedules:
            return False

        del self._schedules[schedule_id]
        self._save()

        logger.info(f"Deleted schedule: {schedule_id}")
        return True

    def exists(self, schedule_id: str) -> bool:
        """Check if a schedule exists.

        Args:
            schedule_id: The schedule ID

        Returns:
            True if exists
        """
        return schedule_id in self._schedules

    def count(self) -> int:
        """Get the number of stored schedules."""
        return len(self._schedules)

    def get_default_page_id(self, board_id: str | None = None) -> str | None:
        """Get the default page ID for schedule gaps for the given board."""
        bid = board_id or DEFAULT_BOARD_ID
        if bid in self._default_page_by_board:
            return self._default_page_by_board[bid] or None
        return self._default_page_id

    def set_default_page_id(self, page_id: str | None, board_id: str | None = None) -> None:
        """Set the default page ID for schedule gaps for the given board."""
        bid = board_id or DEFAULT_BOARD_ID
        if bid == DEFAULT_BOARD_ID:
            self._default_page_id = page_id
        if page_id:
            self._default_page_by_board[bid] = page_id
        else:
            self._default_page_by_board.pop(bid, None)
            if bid == DEFAULT_BOARD_ID:
                self._default_page_id = None
        self._save()
        logger.info(f"Set default page ID for board {bid!r} to: {page_id}")
