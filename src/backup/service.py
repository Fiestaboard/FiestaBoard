"""Backup and restore service for FiestaBoard.

The :class:`BackupService` produces a single JSON document containing all
user-mutable state:

* ``data/config.json`` — board + plugin configuration
* ``data/settings.json`` — runtime settings
* ``data/pages.json`` — user pages
* ``data/collections.json`` — user collections
* ``data/schedules.json`` — user schedules
* ``data/panels.json`` — FiestaPanel panels (their virtual boards live in
  settings.json, so restoring one without the other orphans them)
* metadata about installed external plugins so they can be re-cloned on
  the new instance

Logs, caches, migration ``.json.v*_backup`` files and the contents of
``external_plugins/`` are intentionally excluded — the latter is replaced
with a metadata list so plugins are reinstalled from their canonical git
sources rather than being shipped inside the user's backup file.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import stat
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.atomic_io import staging_path, write_json_atomic
from src.paths import get_data_dir

#: Strict allowlist for repository URLs read from a backup file.  We only
#: clone HTTPS URLs that contain a conservative set of characters; anything
#: Strict allowlist for plugin ids read from a backup file.  Mirrors the
#: ``PLUGIN_ID_RE`` used in :mod:`src.plugins.sources` but is duplicated here
#: so the validation runs before any plugin code is imported.
_BACKUP_PLUGIN_ID_RE = re.compile(r"[a-z][a-z0-9_]*")

logger = logging.getLogger(__name__)


# ── constants ───────────────────────────────────────────────────────────────

#: Bumped whenever the backup file format changes in a non-backwards-compatible
#: way.  Importers refuse files with a higher version than they understand.
BACKUP_SCHEMA_VERSION = 1

#: Magic key on the top-level object so we can sanity-check uploaded files.
BACKUP_FILE_MARKER = "fiestaboard_backup"

#: Filenames in ``data/`` that we round-trip through a backup.  Order matters
#: for deterministic export output.
DATA_FILES: tuple[str, ...] = (
    "config.json",
    "settings.json",
    "pages.json",
    "collections.json",
    "schedules.json",
    "panels.json",
)


class BackupError(Exception):
    """Raised when a backup cannot be produced or restored."""


class BackupRestoreAborted(BackupError):
    """A restore stopped because the environment, not the backup, failed.

    Distinguished from a plain :class:`BackupError` — which means "this file
    is not a usable backup", a client error — so a full disk or an
    unwritable ``data/`` is reported as the server-side failure it is
    instead of blaming the uploaded file.
    """


@dataclass
class _RestoreWrite:
    path: Path
    before: tuple[bytes, int] | None
    after: tuple[bytes, int] | None = None
    after_known: bool = False


class BackupService:
    """Export and import FiestaBoard user data."""

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            data_dir = get_data_dir()
        self.data_dir = Path(data_dir)
        self._lock = threading.Lock()

    # ── export ──────────────────────────────────────────────────────────

    def build_backup(self) -> dict[str, Any]:
        """Produce an in-memory backup document.

        Returns:
            JSON-serialisable dict.  Missing data files are represented as
            ``None`` so importers can distinguish "not present at export
            time" from "present but empty".
        """
        with self._lock:
            data: dict[str, Any | None] = {}
            for filename in DATA_FILES:
                key = filename[:-5]  # strip ".json"
                data[key] = self._read_json(self.data_dir / filename)

            installed_plugins = self._collect_installed_plugins()

            from src import __version__ as app_version

            return {
                BACKUP_FILE_MARKER: True,
                "schema_version": BACKUP_SCHEMA_VERSION,
                "exported_at": datetime.now(UTC).isoformat(),
                "app_version": app_version,
                "data": data,
                "installed_plugins": installed_plugins,
            }

    def export_to_json(self, *, indent: int = 2) -> str:
        """Return the backup as a JSON string."""
        return json.dumps(self.build_backup(), indent=indent, sort_keys=False)

    # ── import ──────────────────────────────────────────────────────────

    def import_from_dict(
        self,
        backup: Any,
        *,
        reinstall_plugins: bool = True,
    ) -> dict[str, Any]:
        """Restore a backup produced by :meth:`build_backup`.

        The current ``data/`` directory is *not* deleted — instead each
        file we are about to overwrite is copied to
        ``data/<name>.json.pre-restore-<timestamp>`` so the user can roll
        back manually if something goes wrong. A file whose copy cannot be
        written is not overwritten at all; the restore aborts with
        :class:`BackupError` instead.

        Caught file-phase failures compensate earlier writes in reverse,
        restoring original bytes/modes and removing newly created files.
        Recovery failures and intervening changes are reported, with verified
        rollback copies retained for manual repair. Services are not reloaded
        and plugins are not reinstalled after an aborted file phase.

        .. warning::
           This is **not transactional across files**: readers may observe
           intermediate states. Compensation is in-memory, not a durable
           crash journal; process death or power loss can still leave a
           partial restore. Per-store locks protect cooperative in-process
           writers only, and identical-content/mode intervening writes cannot
           be distinguished. Plugin reinstall/reload side effects after a
           successful file phase are outside this recovery boundary.

        Args:
            backup: Parsed backup document.
            reinstall_plugins: When True, attempt to clone any external
                plugins recorded in the backup that are not yet installed
                locally.  Failures are reported but do not abort the
                restore (the user can install them manually afterwards).

        Returns:
            Summary dict suitable for returning from the API.

        Raises:
            BackupError: if *backup* is not a recognisable backup
                document.
        """
        self._validate_backup(backup)

        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            # The returned suffix remains usable after a later restore, even
            # within the same clock tick. A failed later copy must never
            # overwrite/delete an earlier operation's rollback files either.
            timestamp = f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex}"
            restored: list[str] = []
            skipped: list[str] = []
            # Only files whose pre-restore copy actually landed. The suffix
            # used to be advertised unconditionally, pointing users at
            # rollback copies that may never have been written (Task 10d).
            backed_up: list[str] = []

            data_section = backup.get("data") or {}
            writes: list[_RestoreWrite] = []
            filename = "data directory"
            try:
                for filename in DATA_FILES:
                    key = filename[:-5]
                    payload = data_section.get(key)
                    legacy = payload is None and key == "collections" and data_section.get("carousels") is not None
                    if legacy:
                        filename = "carousels.json"
                        payload = data_section["carousels"]
                    if payload is None:
                        skipped.append(filename)
                        continue
                    with self._owning_lock(filename):
                        path = self.data_dir / filename
                        write = _RestoreWrite(path, self._file_state(path))
                        # Register before attempting the write: a replace can
                        # land and then raise. Capture its actual outcome too.
                        writes.append(write)
                        try:
                            if self._write_json_with_backup(path, payload, timestamp):
                                backed_up.append(filename)
                        finally:
                            write.after = self._file_state(path)
                            write.after_known = True
                    restored.append(filename + " (legacy)" if legacy else filename)
            except Exception as exc:
                logger.exception("Restore file phase failed at %s; attempting recovery", filename)
                message = self._recover_restore(writes, timestamp)
                unchanged = f" {filename} was not overwritten." if isinstance(exc, BackupRestoreAborted) else ""
                raise BackupRestoreAborted(f"Restore aborted at {filename}.{unchanged} {message}") from exc

        plugin_results: dict[str, Any] = {
            "attempted": [],
            "installed": [],
            "already_present": [],
            "failed": [],
            "manual_reinstall_required": [],
        }

        installed_meta = backup.get("installed_plugins") or []
        if reinstall_plugins and installed_meta:
            plugin_results = self._reinstall_plugins(installed_meta)

        # Reload services so the restored data is visible immediately.
        reload_errors = _reload_services()

        return {
            "status": "success",
            "restored_files": restored,
            "skipped_files": skipped,
            # Empty when nothing was overwritten, so a caller can no longer
            # be told to roll back to copies that were never made (Task 10d).
            "pre_restore_backup_suffix": f".pre-restore-{timestamp}" if backed_up else "",
            "pre_restore_backup_files": backed_up,
            "plugins": plugin_results,
            "reload_errors": reload_errors,
        }

    def import_from_json(
        self,
        raw: str,
        *,
        reinstall_plugins: bool = True,
    ) -> dict[str, Any]:
        """Parse *raw* JSON text and call :meth:`import_from_dict`."""
        try:
            backup = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BackupError(f"Backup file is not valid JSON: {exc.msg}") from exc
        return self.import_from_dict(backup, reinstall_plugins=reinstall_plugins)

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _file_state(path: Path) -> tuple[bytes, int] | None:
        try:
            return path.read_bytes(), stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError:
            return None

    @staticmethod
    def _restore_file(write: _RestoreWrite) -> None:
        """Compensate exactly, including CRLF/formatting and original mode."""
        if write.before is None:
            write.path.unlink(missing_ok=True)
            return
        contents, mode = write.before
        temporary = staging_path(write.path)
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(contents)
                stream.flush()
                os.fchmod(stream.fileno(), mode)
                os.fsync(stream.fileno())
            temporary.replace(write.path)
        finally:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)

    def _recover_restore(self, writes: list[_RestoreWrite], timestamp: str) -> str:
        """Best-effort compensation; never overwrite a detected later writer.

        Keep one store lock at a time, matching the forward write ordering.
        Recovery failures cannot stop compensation of the remaining files.
        Only copies verified against the captured original are advertised.
        """
        failures: list[str] = []
        copies: list[str] = []
        for write in reversed(writes):
            try:
                with self._owning_lock(write.path.name):
                    snapshot = write.path.with_suffix(write.path.suffix + f".pre-restore-{timestamp}")
                    try:
                        if write.before is not None and self._file_state(snapshot) == write.before:
                            copies.append(write.path.name)
                    except OSError:
                        logger.warning("Could not verify rollback copy for %s", write.path.name, exc_info=True)
                    current = self._file_state(write.path)
                    if current == write.before:
                        continue
                    if not write.after_known or current != write.after:
                        failures.append(f"{write.path.name} changed or could not be verified")
                        continue
                    self._restore_file(write)
            except Exception:
                failures.append(f"{write.path.name} could not be recovered")
                logger.exception("Restore recovery failed for %s", write.path.name)
        message = "Recovery incomplete: " + "; ".join(failures) + "." if failures else "Original files recovered."
        if copies:
            message += f" Verified rollback copies: {', '.join(reversed(copies))}; suffix .pre-restore-{timestamp}."
        return message

    @staticmethod
    def _read_json(path: Path) -> Any | None:
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read %s for backup: %s", path, exc)
            return None

    @staticmethod
    def _owning_lock(filename: str) -> contextlib.AbstractContextManager:
        """Return the lock of the live singleton that normally writes *filename*.

        A restore rewrites files that JsonStore-backed services (settings,
        pages, collections, schedules, panels) and the ConfigManager also
        write from other threads. Even with per-call staging names a
        concurrent save could still interleave with the restore (last rename
        wins mid-restore), so each file is written under its owner's lock
        (#1860).

        Lock ordering: the restore loop takes exactly ONE of these locks at a
        time — acquire, write the one file, release, move on — and never
        nests them, so it cannot deadlock against writers that each hold only
        their own lock.

        Falls back to a no-op context when the owning subsystem cannot be
        loaded (a restore must still succeed in a minimal environment).
        """
        try:
            if filename == "config.json":
                from src.config_manager import get_config_manager

                return get_config_manager().lock
            if filename == "settings.json":
                from src.settings.service import get_settings_service

                return get_settings_service().lock
            if filename == "pages.json":
                from src.pages.service import get_page_service

                return get_page_service().storage.lock
            if filename == "collections.json":
                from src.collections.service import get_collection_service

                return get_collection_service().storage.lock
            if filename == "schedules.json":
                from src.schedules.service import get_schedule_service

                return get_schedule_service().storage.lock
            if filename == "panels.json":
                from src.panels.service import get_panel_service

                return get_panel_service().storage.lock
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("No owning lock for %s during restore: %s", filename, exc)
        return contextlib.nullcontext()

    @staticmethod
    def _write_json_with_backup(path: Path, payload: Any, timestamp: str) -> bool:
        """Write *payload* to *path*, preserving any existing file.

        The old file (if any) is copied to ``<path>.pre-restore-<timestamp>``
        **before** the new content is written. Writes go through
        :func:`src.atomic_io.write_json_atomic` (unique per-call staging file
        + ``os.replace``) so a crash mid-restore can never leave a partially
        written JSON file in place and no concurrent writer can collide on
        the staging name. Callers restoring a file owned by a live store must
        additionally hold that store's lock (see :meth:`_owning_lock`).

        Returns:
            True when a pre-restore copy was written, False when *path* did
            not exist and there was therefore nothing to preserve.

        Raises:
            BackupRestoreAborted: the pre-restore copy failed. The live file is left
                untouched — the copy is the user's only way back out of a
                bad restore, so overwriting without one (which is what this
                did before Phase 2 Task 10d) destroys the escape hatch and
                then reports success.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            write_json_atomic(path, payload)
            return False

        backup_path = path.with_suffix(path.suffix + f".pre-restore-{timestamp}")
        try:
            shutil.copy2(path, backup_path)
        except OSError as exc:
            # A half-written copy is worse than none: it looks usable. Drop
            # it, then abort before touching the live file.
            with contextlib.suppress(OSError):
                backup_path.unlink(missing_ok=True)
            logger.error("Could not write pre-restore backup %s: %s", backup_path, exc)
            raise BackupRestoreAborted(
                f"Could not preserve the existing {path.name} before restoring it ({exc}). "
                f"{path.name} was not overwritten."
            ) from exc
        logger.info("Saved pre-restore backup to %s", backup_path)

        write_json_atomic(path, payload)
        return True

    @staticmethod
    def _validate_backup(backup: Any) -> None:
        if not isinstance(backup, dict):
            raise BackupError("Backup file must be a JSON object.")
        if not backup.get(BACKUP_FILE_MARKER):
            raise BackupError(f"File does not look like a FiestaBoard backup (missing '{BACKUP_FILE_MARKER}' marker).")
        version = backup.get("schema_version")
        if not isinstance(version, int):
            raise BackupError("Backup file is missing 'schema_version'.")
        if version > BACKUP_SCHEMA_VERSION:
            raise BackupError(
                f"Backup was produced by a newer version of FiestaBoard "
                f"(schema_version={version}, this build supports "
                f"{BACKUP_SCHEMA_VERSION})."
            )
        if "data" not in backup or not isinstance(backup["data"], dict):
            raise BackupError("Backup file is missing the 'data' section.")

    @staticmethod
    def _collect_installed_plugins() -> list[dict[str, str]]:
        """Return metadata describing currently-installed external plugins.

        Built-in plugins are skipped because they ship with the application
        and never need to be reinstalled.
        """
        try:
            from src.plugins import get_plugin_registry  # type: ignore
        except Exception:  # pragma: no cover - plugin system optional
            return []

        try:
            registry = get_plugin_registry()
        except Exception:  # pragma: no cover - defensive
            logger.warning("Could not access plugin registry for backup", exc_info=True)
            return []

        plugins: list[dict[str, str]] = []
        try:
            sources = registry._loader.plugin_sources  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive
            return []

        for plugin_id, source in sources.items():
            source_type = getattr(source, "source_type", "")
            if source_type in ("builtin", "built-in", ""):
                continue
            repository = getattr(source, "repository_url", "") or ""
            if not repository:
                continue
            plugins.append(
                {
                    "plugin_id": plugin_id,
                    "source_type": source_type,
                    "repository_url": repository,
                }
            )
        plugins.sort(key=lambda p: p["plugin_id"])
        return plugins

    @staticmethod
    def _reinstall_plugins(
        installed_meta: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Best-effort reinstall of external plugins listed in the backup."""
        result: dict[str, Any] = {
            "attempted": [],
            "installed": [],
            "already_present": [],
            "failed": [],
            "manual_reinstall_required": [],
        }

        try:
            from src.plugins import get_plugin_registry  # type: ignore
        except Exception:
            for entry in installed_meta:
                pid = entry.get("plugin_id", "")
                result["failed"].append({"plugin_id": pid, "error": "plugin system unavailable"})
            return result

        try:
            registry = get_plugin_registry()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Plugin registry unavailable during restore: %s", exc)
            for entry in installed_meta:
                pid = entry.get("plugin_id", "")
                result["failed"].append({"plugin_id": pid, "error": "plugin registry unavailable"})
            return result

        for entry in installed_meta:
            plugin_id = entry.get("plugin_id") or ""
            source_type = entry.get("source_type") or ""
            if not plugin_id:
                continue

            # Validate plugin_id with a strict allowlist.
            pid_m = _BACKUP_PLUGIN_ID_RE.fullmatch(plugin_id)
            if pid_m is None:
                result["failed"].append({"plugin_id": plugin_id, "error": "invalid plugin id in backup"})
                continue
            safe_plugin_id = pid_m.group(0)

            # External git plugins carry a user-controlled repository_url from
            # the backup file.  Passing that URL into subprocess (even after
            # regex validation) creates a CodeQL py/command-line-injection
            # finding, and automatically cloning arbitrary URLs from an uploaded
            # file is an SSRF risk.  These plugins are surfaced in
            # ``manual_reinstall_required`` so the operator can re-add them
            # explicitly via the Integrations UI.  Only registry plugins can
            # be reinstalled automatically because their URL is looked up from
            # the trusted static plugin-registry.json, not from the backup.
            if source_type != "registry":
                result["manual_reinstall_required"].append(
                    {
                        "plugin_id": safe_plugin_id,
                        "reason": "external_git_plugin",
                        "repository_url": entry.get("repository_url") or "",
                    }
                )
                continue

            result["attempted"].append(safe_plugin_id)

            if registry.get_plugin(safe_plugin_id) is not None:
                result["already_present"].append(safe_plugin_id)
                continue

            try:
                errors = registry.install_from_registry(safe_plugin_id)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Plugin reinstall raised: %s", safe_plugin_id)
                result["failed"].append({"plugin_id": safe_plugin_id, "error": "install failed (see server logs)"})
                continue

            if errors:
                # Install errors embed git/loader exception text (URLs, paths,
                # stderr) — keep the detail in the server log and return a
                # static message (CodeQL py/stack-trace-exposure).
                logger.warning("Plugin reinstall for '%s' failed: %s", safe_plugin_id, "; ".join(errors))
                result["failed"].append({"plugin_id": safe_plugin_id, "error": "install failed (see server logs)"})
            else:
                result["installed"].append(safe_plugin_id)

        return result


# ── service singleton + reload helpers ──────────────────────────────────────


_backup_service: BackupService | None = None
_singleton_lock = threading.Lock()


def get_backup_service() -> BackupService:
    """Return the process-wide :class:`BackupService` singleton."""
    global _backup_service
    if _backup_service is None:
        with _singleton_lock:
            if _backup_service is None:
                _backup_service = BackupService()
    return _backup_service


def _reload_services() -> list[str]:
    """Reload in-memory singletons after a restore.

    Each step is wrapped in its own try/except so a failure in one
    subsystem does not prevent the others from reloading.  Returns a
    list of human-readable error strings (empty on full success).
    """
    errors: list[str] = []

    # Config manager: re-read config.json from disk.
    try:
        from src.config_manager import get_config_manager

        get_config_manager().reload()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to reload config manager")
        errors.append("config: reload failed (see server logs)")

    # Settings, pages, collections, schedules: drop singletons so the next
    # access re-reads from the freshly written JSON files.
    for module_path, attr in (
        ("src.settings.service", "_settings_service"),
        ("src.pages.service", "_page_service"),
        ("src.collections.service", "_collection_service"),
        ("src.schedules.service", "_schedule_service"),
        ("src.panels.service", "_panel_service"),
    ):
        try:
            import importlib

            mod = importlib.import_module(module_path)
            if hasattr(mod, attr):
                setattr(mod, attr, None)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to reset %s.%s", module_path, attr)
            errors.append(f"{module_path}: reset failed (see server logs)")

    # Plugin registry: live plugin objects still hold the pre-restore
    # configuration. A restore rewrites config.json wholesale, so this is one
    # of the few places that genuinely must rebuild the whole plugin set —
    # everywhere else a single plugin's config change reaches only that plugin
    # (issue #1753).
    try:
        from src.plugins import get_plugin_registry

        get_plugin_registry().initialize(force=True)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to reload plugin registry")
        errors.append("plugins: reload failed (see server logs)")

    # Display service has its own reset helper.
    try:
        from src.displays.service import reset_display_service

        reset_display_service()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to reset display service")
        errors.append("displays: reset failed (see server logs)")

    # Template engine caches plugin variables — reset so it picks up the
    # restored plugin configuration on next render.
    try:
        from src.templates.engine import reset_template_engine

        reset_template_engine()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to reset template engine")
        errors.append("templates: reset failed (see server logs)")

    return errors
