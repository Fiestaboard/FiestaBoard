"""The storage kernel: one atomic, locked, schema-versioned JSON file store.

``JsonStore`` owns the three things every FiestaBoard store used to open-code
(and drift on):

* **Atomic writes** — every save goes through
  :func:`src.atomic_io.write_json_atomic` (process-scoped staging file, fsync,
  ``os.replace``), so a mid-write crash never truncates the real file (#1304)
  and two processes never collide on a fixed ``.tmp`` name.

* **In-process locking** — a ``threading.RLock`` serialises ``load``/``save``/
  ``mutate``. The lock is public (:attr:`lock`) so a composing service can
  extend the critical section around its own read-modify-write (the fix for
  lost concurrent settings PUTs, #1848).

* **Schema migrations** — the ordered ``(target_version, fn)`` machinery from
  ``src/pages/storage.py``, generalised. Migration functions receive the raw
  top-level object (usually a dict; stores whose payload is a wrapped list
  adapt with a small lambda) and are run in order on ``load()`` when the
  file's ``schema_version`` is behind. A backup of the pre-migration file is
  written once as ``<file>.v{N}_backup``. The kernel does **not** write the
  migrated data back itself — it sets :attr:`migrated` and the domain store
  persists via its own ``save`` path, so the on-disk bytes keep coming from
  the domain's serialisation exactly as before.

Domain rules stay in the domain: each store keeps its own
``CURRENT_SCHEMA_VERSION`` and ``MIGRATIONS`` list (per CLAUDE.md, never
heuristic detection) and hands them to the kernel to run.
"""

import json
import logging
import shutil
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from src.atomic_io import write_json_atomic
from src.paths import get_data_dir

logger = logging.getLogger(__name__)

# A migration: (target_version, fn). ``fn`` mutates the raw top-level data in
# place and returns the number of records/changes it touched (for logging).
Migration = tuple[int, Callable[[Any], int]]


class JsonStore:
    """Atomic, locked, schema-versioned persistence for one JSON file."""

    def __init__(
        self,
        filename_or_path: str | Path,
        *,
        current_schema_version: int = 0,
        migrations: Sequence[Migration] = (),
        label: str | None = None,
    ):
        """Create a store for one JSON file.

        Args:
            filename_or_path: A bare filename (``"pages.json"``) resolves into
                the central data directory via ``get_data_dir()``; anything
                with a directory component is used as given (explicit path
                wins).
            current_schema_version: The version ``save()`` stamps on dict
                payloads and ``load()`` migrates files up to. ``0`` disables
                schema versioning entirely.
            migrations: Ordered ``(target_version, fn)`` pairs; each ``fn``
                mutates the raw loaded object in place and returns a count.
            label: Name used in migration log lines (defaults to the file
                stem).
        """
        path = Path(filename_or_path)
        if len(path.parts) == 1:
            path = get_data_dir() / path
        self._path = path
        self._version = current_schema_version
        self._migrations = list(migrations)
        self._label = label or path.stem
        self._lock = threading.RLock()
        self._data: Any = None
        #: True when the most recent ``load()`` applied migrations; the caller
        #: should persist (``mutate()`` does so automatically).
        self.migrated = False

    @property
    def path(self) -> Path:
        """The resolved on-disk path of this store."""
        return self._path

    @property
    def lock(self) -> threading.RLock:
        """The store's re-entrant lock, for composing services that need to
        extend the critical section around their own read-modify-write."""
        return self._lock

    def exists(self) -> bool:
        """True when the backing file exists on disk."""
        return self._path.exists()

    # ── core operations ────────────────────────────────────────────────

    def load(self) -> Any:
        """Read the file, run any pending migrations, and return the data.

        Returns ``None`` when the file does not exist. Read/parse errors
        propagate — the domain store decides whether a broken file is fatal.
        Sets :attr:`migrated` when migrations ran; the migrated data is NOT
        written back here (see module docstring).
        """
        with self._lock:
            self.migrated = False
            if not self._path.exists():
                self._data = None
                return None
            # builtins.open (not Path.open) so existing tests can patch
            # builtins.open to inject I/O errors.
            with open(self._path) as f:  # noqa: PTH123
                data = json.load(f)
            if self._migrations_pending(data):
                self._backup_before_migration(data)
                self._run_migrations(data)
                self.migrated = True
            self._data = data
            return data

    def save(self, data: Any) -> None:
        """Atomically persist *data*, stamping ``schema_version`` on
        versioned dict payloads. Write errors propagate."""
        with self._lock:
            if self._version and isinstance(data, dict):
                data["schema_version"] = self._version
            write_json_atomic(self._path, data)
            self._data = data

    def mutate(self, fn: Callable[[Any], Any]) -> Any:
        """The read-modify-write primitive: lock → load (or cached data, or a
        fresh ``{}`` when the file is missing) → ``fn(data)`` → save.

        ``fn`` mutates the data in place; its return value is passed through.

        Assumes this store instance is the only writer of its file: once
        ``self._data`` is populated it is trusted as-is — the file is never
        re-read, so changes written by another JsonStore instance or another
        process are silently overwritten. The missing-file path starts from a
        bare ``{}`` without running migrations (``load()`` on an existing
        file is where migrations happen). Use the process-wide singleton
        store for a given file, and single-process deployment, for this to
        hold.
        """
        with self._lock:
            data = self._data
            if data is None:
                data = self.load()
            if data is None:
                data = {}
            result = fn(data)
            self.save(data)
            return result

    # ── schema migrations ──────────────────────────────────────────────

    def _migrations_pending(self, data: Any) -> bool:
        return self._version > 0 and isinstance(data, dict) and self._file_version(data) < self._version

    @staticmethod
    def _file_version(data: dict) -> int:
        version = data.get("schema_version", 0)
        return version if isinstance(version, int) else 0

    def _backup_before_migration(self, data: dict) -> None:
        """Copy the pre-migration file to ``<file>.v{N}_backup``, once."""
        version = self._file_version(data)
        backup_path = self._path.with_suffix(f"{self._path.suffix}.v{version}_backup")
        if backup_path.exists():
            return
        try:
            shutil.copy2(self._path, backup_path)
            logger.info(f"Created pre-migration backup at {backup_path}")
        except Exception as e:
            logger.warning(f"Could not create backup: {e}")

    def _run_migrations(self, data: dict) -> None:
        version = self._file_version(data)
        for target_version, migrate_fn in self._migrations:
            if version >= target_version:
                continue
            count = migrate_fn(data)
            logger.info(f"{self._label} schema migration v{version}->v{target_version}: {count} change(s) applied")
            version = target_version
        data["schema_version"] = self._version
