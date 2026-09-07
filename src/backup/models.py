"""Wire models for ``/backup/export`` and ``/backup/import`` (Phase 2, Task 8)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class BackupDocument(BaseModel):
    """The uploaded backup file.

    ``extra="allow"`` is deliberate and is *not* the ``request: dict`` the
    conventions ban. A backup is a versioned document produced by an older
    release of this app: ``data`` holds whatever stores existed then, keyed by
    filename, and a future field must survive the round trip rather than be
    silently dropped on the floor by a strict model. What the model *does* buy
    is the thing the bare ``dict[str, Any]`` did not — the top-level shape is
    published in the OpenAPI schema, and a JSON array or scalar is a 422 at
    the door instead of an ``AttributeError`` deep inside the restore.

    :class:`~src.backup.service.BackupService` remains the authority on
    whether the document is actually a FiestaBoard backup; it raises
    ``BackupError`` (a 400) when the marker is missing.
    """

    model_config = ConfigDict(extra="allow")

    #: ``BACKUP_FILE_MARKER`` — present and true in every real backup.
    fiestaboard_backup: bool | None = None
    schema_version: int | None = None
    exported_at: str | None = None
    app_version: str | None = None
    #: Store contents keyed by filename (``pages.json``, ``settings.json``, …).
    data: dict[str, Any] | None = None
    installed_plugins: list[dict[str, Any]] | None = None


class FailedPluginReinstall(BaseModel):
    """A registry plugin the restore tried and failed to reinstall."""

    plugin_id: str
    error: str


class ManualPluginReinstall(BaseModel):
    """An external plugin the restore refuses to clone automatically.

    Its ``repository_url`` comes from the uploaded file, so cloning it would
    let a backup point the server at any git host. The operator re-adds these
    explicitly from the Integrations UI.
    """

    plugin_id: str
    reason: str
    repository_url: str


class PluginRestoreReport(BaseModel):
    """What the restore did about the plugins the backup listed."""

    attempted: list[str] = []
    installed: list[str] = []
    already_present: list[str] = []
    failed: list[FailedPluginReinstall] = []
    manual_reinstall_required: list[ManualPluginReinstall] = []


class BackupImportResponse(BaseModel):
    """``POST /backup/import`` — what was restored, skipped and reinstalled."""

    restored_files: list[str]
    skipped_files: list[str]
    #: Suffix of the ``.pre-restore-<ts>`` copies. Empty when nothing was
    #: overwritten, so a caller is never told to roll back to copies that were
    #: never made (Task 10d).
    pre_restore_backup_suffix: str
    #: The files a pre-restore copy actually exists for.
    pre_restore_backup_files: list[str] = []
    plugins: PluginRestoreReport
    #: Services that could not be reloaded in place; a restart clears these.
    reload_errors: list[str] = []
