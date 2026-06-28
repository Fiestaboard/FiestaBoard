"""JSON file-based storage for collections.

Owns ``data/collections.json``. Includes a schema-versioning system that
mirrors ``src/pages/storage.py`` and a one-shot importer that migrates the
legacy ``data/carousels.json`` file (carousel: prefixed IDs, flat
``interval_seconds``) into the new collection format on first run.
"""

import contextlib
import json
import logging
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .models import COLLECTION_ID_PREFIX, Collection

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1

LEGACY_CAROUSEL_ID_PREFIX = "carousel:"


def _legacy_to_collection_id(ref_id: str) -> str:
    """Rewrite ``carousel:<uuid>`` → ``collection:<uuid>``.

    Returns the input unchanged if it is not a legacy carousel ID.
    """
    if ref_id and ref_id.startswith(LEGACY_CAROUSEL_ID_PREFIX):
        return COLLECTION_ID_PREFIX + ref_id[len(LEGACY_CAROUSEL_ID_PREFIX) :]
    return ref_id


def import_legacy_carousels(raw_carousels: list[dict]) -> list[dict]:
    """Convert legacy carousel records into collection records.

    For each legacy entry:
    - rewrite the ``id`` prefix
    - wrap the flat ``interval_seconds`` into a ``time`` block
    - default ``selection_mode`` to ``"time"``
    """
    collections: list[dict] = []
    for item in raw_carousels:
        new_item = dict(item)
        if "id" in new_item and isinstance(new_item["id"], str):
            new_item["id"] = _legacy_to_collection_id(new_item["id"])
        interval = new_item.pop("interval_seconds", None)
        if interval is None:
            interval = 30
        new_item.setdefault("selection_mode", "time")
        new_item.setdefault("time", {"interval_seconds": int(interval)})
        collections.append(new_item)
    return collections


# Schema migrations operate on the raw ``collections`` list.
# Each function returns the count of records it modified.
MIGRATIONS: list[tuple[int, Callable[[list[dict]], int]]] = []


class CollectionStorage:
    """JSON file-based storage for collections."""

    def __init__(self, storage_file: str | None = None):
        if storage_file is None:
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            self.storage_file = data_dir / "collections.json"
        else:
            self.storage_file = Path(storage_file)

        self._collections: dict[str, Collection] = {}
        # Raw entries (post-migration) that failed Pydantic validation on load.
        # Round-tripped through _save so a transient parsing failure (e.g. a
        # bug in a migration, a renamed enum value) never silently deletes a
        # user's collection from disk. Mirrors src/pages/storage.py (#1305).
        self._failed_entries: list[dict] = []
        self._load()

        logger.info(f"CollectionStorage initialized (file: {self.storage_file}, collections: {len(self._collections)})")

    # --- migrations ------------------------------------------------------

    def _run_migrations(self, data: dict) -> bool:
        """Run any pending schema migrations on raw JSON data.

        Returns True if any migrations were applied (caller should resave).
        """
        current_version = data.get("schema_version", 0)
        if current_version >= CURRENT_SCHEMA_VERSION:
            return False

        records = data.get("collections", [])

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
            count = migrate_fn(records)
            logger.info(
                f"Collections schema migration v{current_version}->v{target_version}: {count} record(s) processed"
            )
            current_version = target_version

        data["schema_version"] = CURRENT_SCHEMA_VERSION
        return True

    def _import_legacy_carousels_if_needed(self) -> bool:
        """If no collections file exists but a legacy carousels.json does,
        import it.

        Returns True if a legacy import happened (caller should treat as a
        fresh load needing save).
        """
        if self.storage_file.exists():
            return False

        legacy_path = self.storage_file.parent / "carousels.json"
        if not legacy_path.exists():
            return False

        try:
            with open(legacy_path) as f:  # noqa: PTH123
                legacy_data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read legacy carousels file: {e}")
            return False

        raw_carousels = legacy_data.get("carousels", []) or []
        if not raw_carousels:
            logger.info("Legacy carousels file present but empty; nothing to import")
            return False

        converted = import_legacy_carousels(raw_carousels)
        logger.info(f"Imported {len(converted)} legacy carousel(s) into collections")

        # Hydrate in-memory cache directly from the converted records so the
        # caller does not have to re-read the file we are about to write.
        self._collections = {}
        self._failed_entries = []
        for record in converted:
            # Snapshot before datetime coercion so a record that fails Pydantic
            # validation is round-tripped untouched rather than silently dropped.
            raw_snapshot = dict(record) if isinstance(record, dict) else record
            try:
                self._hydrate_record(record)
            except Exception as e:
                record_id = raw_snapshot.get("id", "<unknown>") if isinstance(raw_snapshot, dict) else "<unknown>"
                logger.warning(
                    "Failed to load imported collection %s; preserving raw entry to avoid data loss: %s",
                    record_id,
                    e,
                )
                self._failed_entries.append(raw_snapshot)

        # Move the legacy file aside so the import is a one-shot operation.
        try:
            backup = legacy_path.with_suffix(".json.pre-collections-backup")
            legacy_path.rename(backup)
            logger.info(f"Renamed legacy carousels file to {backup} (one-shot import complete)")
        except OSError as e:
            logger.warning(f"Could not rename legacy carousels file: {e}")

        return True

    def _hydrate_record(self, record: dict) -> None:
        """Parse a raw dict into a Collection and add it to the cache."""
        if "created_at" in record and isinstance(record["created_at"], str):
            record["created_at"] = datetime.fromisoformat(record["created_at"])
        if "updated_at" in record and isinstance(record["updated_at"], str):
            record["updated_at"] = datetime.fromisoformat(record["updated_at"])
        collection = Collection(**record)
        self._collections[collection.id] = collection

    # --- load / save -----------------------------------------------------

    def _load(self) -> None:
        # First-run path: import legacy carousels.json if present.
        if self._import_legacy_carousels_if_needed():
            self._save()
            return

        if not self.storage_file.exists():
            self._collections = {}
            self._failed_entries = []
            return

        try:
            with open(self.storage_file) as f:  # noqa: PTH123
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load collections file: {e}")
            self._collections = {}
            self._failed_entries = []
            return

        needs_save = self._run_migrations(data)

        self._collections = {}
        self._failed_entries = []
        for record in data.get("collections", []):
            # Snapshot before datetime coercion so we can round-trip the entry
            # untouched if Pydantic validation fails below.
            raw_snapshot = dict(record) if isinstance(record, dict) else record
            try:
                self._hydrate_record(record)
            except Exception as e:
                record_id = raw_snapshot.get("id", "<unknown>") if isinstance(raw_snapshot, dict) else "<unknown>"
                logger.error(
                    "Failed to parse collection %s; preserving raw entry to avoid data loss: %s",
                    record_id,
                    e,
                )
                self._failed_entries.append(raw_snapshot)

        if self._failed_entries:
            logger.error(
                "Collections load preserved %d unparseable entr%s as-is in storage",
                len(self._failed_entries),
                "y" if len(self._failed_entries) == 1 else "ies",
            )

        logger.info(f"Loaded {len(self._collections)} collections from storage")

        if needs_save:
            self._save()
            logger.info("Saved migrated collections to storage")

    def _save(self) -> None:
        """Save collections to storage file.

        Writes to a sibling ``<file>.tmp`` and ``os.replace``s it into place so
        a mid-write crash (OOM, SIGKILL, power loss) never leaves a truncated
        file that would wipe in-memory state on reload (see #1304).
        """
        try:
            records = []
            for c in self._collections.values():
                record = c.model_dump()
                if record.get("created_at"):
                    record["created_at"] = record["created_at"].isoformat()
                if record.get("updated_at"):
                    record["updated_at"] = record["updated_at"].isoformat()
                records.append(record)

            # Round-trip any entries that failed to parse on load so a follow-up
            # save doesn't quietly delete them from disk (see #1305).
            records.extend(self._failed_entries)

            data = {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "collections": records,
            }

            tmp_path = self.storage_file.with_suffix(self.storage_file.suffix + ".tmp")
            try:
                with open(tmp_path, "w") as f:  # noqa: PTH123
                    json.dump(data, f, indent=2)
                tmp_path.replace(self.storage_file)
            except BaseException:
                # Clean up the partial tmp file on any failure so we don't leak
                # it; the original storage file stays untouched.
                with contextlib.suppress(OSError):
                    tmp_path.unlink(missing_ok=True)
                raise

            logger.debug(f"Saved {len(self._collections)} collections to storage")
        except OSError as e:
            logger.error(f"Failed to save collections file: {e}")
            raise

    # --- CRUD ------------------------------------------------------------

    def list_all(self) -> list[Collection]:
        items = list(self._collections.values())
        items.sort(key=lambda c: c.name.lower())
        return items

    def get(self, collection_id: str) -> Collection | None:
        return self._collections.get(collection_id)

    def create(self, collection: Collection) -> Collection:
        if collection.id in self._collections:
            raise ValueError(f"Collection with ID {collection.id} already exists")
        errors = collection.validate_config()
        if errors:
            raise ValueError(f"Invalid collection configuration: {errors}")
        self._collections[collection.id] = collection
        self._save()
        logger.info(f"Created collection: {collection.id} ({collection.name})")
        return collection

    def update(self, collection_id: str, updates: dict) -> Collection | None:
        if collection_id not in self._collections:
            return None

        current = self._collections[collection_id]
        current_dict = current.model_dump()
        for key, value in updates.items():
            if key in current_dict and value is not None:
                current_dict[key] = value

        current_dict["updated_at"] = datetime.utcnow()
        updated = Collection(**current_dict)

        errors = updated.validate_config()
        if errors:
            raise ValueError(f"Invalid collection configuration: {errors}")

        self._collections[collection_id] = updated
        self._save()
        logger.info(f"Updated collection: {collection_id}")
        return updated

    def delete(self, collection_id: str) -> bool:
        if collection_id not in self._collections:
            return False
        del self._collections[collection_id]
        self._save()
        logger.info(f"Deleted collection: {collection_id}")
        return True

    def exists(self, collection_id: str) -> bool:
        return collection_id in self._collections

    def count(self) -> int:
        return len(self._collections)
