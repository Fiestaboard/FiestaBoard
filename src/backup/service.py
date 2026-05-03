"""Backup and restore service for FiestaBoard.

The :class:`BackupService` produces a single JSON document containing all
user-mutable state:

* ``data/config.json`` — board + plugin configuration
* ``data/settings.json`` — runtime settings
* ``data/pages.json`` — user pages
* ``data/carousels.json`` — user carousels
* ``data/schedules.json`` — user schedules
* metadata about installed external plugins so they can be re-cloned on
  the new instance

Logs, caches, migration ``.json.v*_backup`` files and the contents of
``external_plugins/`` are intentionally excluded — the latter is replaced
with a metadata list so plugins are reinstalled from their canonical git
sources rather than being shipped inside the user's backup file.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
DATA_FILES: Tuple[str, ...] = (
    "config.json",
    "settings.json",
    "pages.json",
    "carousels.json",
    "schedules.json",
)


class BackupError(Exception):
    """Raised when a backup cannot be produced or restored."""


class BackupService:
    """Export and import FiestaBoard user data."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            data_dir = project_root / "data"
        self.data_dir = Path(data_dir)
        self._lock = threading.Lock()

    # ── export ──────────────────────────────────────────────────────────

    def build_backup(self) -> Dict[str, Any]:
        """Produce an in-memory backup document.

        Returns:
            JSON-serialisable dict.  Missing data files are represented as
            ``None`` so importers can distinguish "not present at export
            time" from "present but empty".
        """
        with self._lock:
            data: Dict[str, Optional[Any]] = {}
            for filename in DATA_FILES:
                key = filename[:-5]  # strip ".json"
                data[key] = self._read_json(self.data_dir / filename)

            installed_plugins = self._collect_installed_plugins()

            try:
                from .. import __version__ as app_version
            except Exception:  # pragma: no cover - defensive only
                app_version = "unknown"

            return {
                BACKUP_FILE_MARKER: True,
                "schema_version": BACKUP_SCHEMA_VERSION,
                "exported_at": datetime.now(timezone.utc).isoformat(),
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
    ) -> Dict[str, Any]:
        """Restore a backup produced by :meth:`build_backup`.

        The current ``data/`` directory is *not* deleted — instead each
        file we are about to overwrite is copied to
        ``data/<name>.json.pre-restore-<timestamp>`` so the user can roll
        back manually if something goes wrong.

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
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            restored: List[str] = []
            skipped: List[str] = []

            data_section = backup.get("data") or {}

            for filename in DATA_FILES:
                key = filename[:-5]
                payload = data_section.get(key)
                if payload is None:
                    skipped.append(filename)
                    continue
                self._write_json_with_backup(
                    self.data_dir / filename, payload, timestamp
                )
                restored.append(filename)

        plugin_results: Dict[str, Any] = {
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
            "pre_restore_backup_suffix": f".pre-restore-{timestamp}",
            "plugins": plugin_results,
            "reload_errors": reload_errors,
        }

    def import_from_json(
        self,
        raw: str,
        *,
        reinstall_plugins: bool = True,
    ) -> Dict[str, Any]:
        """Parse *raw* JSON text and call :meth:`import_from_dict`."""
        try:
            backup = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BackupError(f"Backup file is not valid JSON: {exc.msg}") from exc
        return self.import_from_dict(backup, reinstall_plugins=reinstall_plugins)

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _read_json(path: Path) -> Optional[Any]:
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read %s for backup: %s", path, exc)
            return None

    @staticmethod
    def _write_json_with_backup(path: Path, payload: Any, timestamp: str) -> None:
        """Write *payload* to *path*, preserving any existing file.

        The old file (if any) is moved to ``<path>.pre-restore-<timestamp>``
        before the new content is written.  Writes are atomic via
        ``os.replace`` so a crash mid-restore can never leave a partially
        written JSON file in place.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup_path = path.with_suffix(path.suffix + f".pre-restore-{timestamp}")
            try:
                shutil.copy2(path, backup_path)
                logger.info("Saved pre-restore backup to %s", backup_path)
            except OSError as exc:
                logger.warning("Could not write pre-restore backup %s: %s", backup_path, exc)

        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        tmp_path.replace(path)

    @staticmethod
    def _validate_backup(backup: Any) -> None:
        if not isinstance(backup, dict):
            raise BackupError("Backup file must be a JSON object.")
        if not backup.get(BACKUP_FILE_MARKER):
            raise BackupError(
                "File does not look like a FiestaBoard backup "
                f"(missing '{BACKUP_FILE_MARKER}' marker)."
            )
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
    def _collect_installed_plugins() -> List[Dict[str, str]]:
        """Return metadata describing currently-installed external plugins.

        Built-in plugins are skipped because they ship with the application
        and never need to be reinstalled.
        """
        try:
            from ..plugins import get_plugin_registry  # type: ignore
        except Exception:  # pragma: no cover - plugin system optional
            return []

        try:
            registry = get_plugin_registry()
        except Exception:  # pragma: no cover - defensive
            logger.warning("Could not access plugin registry for backup", exc_info=True)
            return []

        plugins: List[Dict[str, str]] = []
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
        installed_meta: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Best-effort reinstall of external plugins listed in the backup."""
        result: Dict[str, Any] = {
            "attempted": [],
            "installed": [],
            "already_present": [],
            "failed": [],
            "manual_reinstall_required": [],
        }

        try:
            from ..plugins import get_plugin_registry  # type: ignore
        except Exception:
            for entry in installed_meta:
                pid = entry.get("plugin_id", "")
                result["failed"].append(
                    {"plugin_id": pid, "error": "plugin system unavailable"}
                )
            return result

        try:
            registry = get_plugin_registry()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Plugin registry unavailable during restore: %s", exc)
            for entry in installed_meta:
                pid = entry.get("plugin_id", "")
                result["failed"].append(
                    {"plugin_id": pid, "error": "plugin registry unavailable"}
                )
            return result

        for entry in installed_meta:
            plugin_id = entry.get("plugin_id") or ""
            source_type = entry.get("source_type") or ""
            if not plugin_id:
                continue

            # Validate plugin_id with a strict allowlist.
            pid_m = _BACKUP_PLUGIN_ID_RE.fullmatch(plugin_id)
            if pid_m is None:
                result["failed"].append(
                    {"plugin_id": plugin_id, "error": "invalid plugin id in backup"}
                )
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
                result["failed"].append(
                    {"plugin_id": safe_plugin_id, "error": "install failed (see server logs)"}
                )
                continue

            if errors:
                result["failed"].append(
                    {"plugin_id": safe_plugin_id, "error": "; ".join(errors)}
                )
            else:
                result["installed"].append(safe_plugin_id)

        return result


# ── service singleton + reload helpers ──────────────────────────────────────


_backup_service: Optional[BackupService] = None
_singleton_lock = threading.Lock()


def get_backup_service() -> BackupService:
    """Return the process-wide :class:`BackupService` singleton."""
    global _backup_service
    if _backup_service is None:
        with _singleton_lock:
            if _backup_service is None:
                _backup_service = BackupService()
    return _backup_service


def _reload_services() -> List[str]:
    """Reload in-memory singletons after a restore.

    Each step is wrapped in its own try/except so a failure in one
    subsystem does not prevent the others from reloading.  Returns a
    list of human-readable error strings (empty on full success).
    """
    errors: List[str] = []

    # Config manager: re-read config.json from disk.
    try:
        from ..config_manager import get_config_manager
        get_config_manager().reload()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to reload config manager")
        errors.append("config: reload failed (see server logs)")

    # Settings, pages, carousels, schedules: drop singletons so the next
    # access re-reads from the freshly written JSON files.
    for module_path, attr in (
        ("src.settings.service", "_settings_service"),
        ("src.pages.service", "_page_service"),
        ("src.carousels.service", "_carousel_service"),
        ("src.schedules.service", "_schedule_service"),
    ):
        try:
            import importlib
            mod = importlib.import_module(module_path)
            if hasattr(mod, attr):
                setattr(mod, attr, None)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to reset %s.%s", module_path, attr)
            errors.append(f"{module_path}: reset failed (see server logs)")

    # Display service has its own reset helper.
    try:
        from ..displays.service import reset_display_service
        reset_display_service()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to reset display service")
        errors.append("displays: reset failed (see server logs)")

    # Template engine caches plugin variables — reset so it picks up the
    # restored plugin configuration on next render.
    try:
        from ..templates.engine import reset_template_engine
        reset_template_engine()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to reset template engine")
        errors.append("templates: reset failed (see server logs)")

    return errors
