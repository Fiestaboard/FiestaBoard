"""Pydantic models for the system-update endpoint family (issue #1758).

Moved verbatim from ``src/api_server.py``. The api_server module re-imports
them so any existing ``src.api_server.<Model>`` reference keeps resolving.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class VersionResponse(BaseModel):
    """Response model for version information."""

    package_version: str
    build_version: str
    is_dev: bool
    hardware_model: str | None = None


class UpdateCheckResponse(BaseModel):
    """Response model for update check."""

    current_version: str
    latest_version: str | None
    update_available: bool
    package_url: str
    error: str | None = None
    is_production: bool


class UpdateStatusResponse(BaseModel):
    """Response model for system update status (sidecar availability + auto-update flag)."""

    updater_available: bool
    auto_update_enabled: bool  # derived: True when interval != "manual"
    auto_update_interval: str  # "daily" | "weekly" | "monthly" | "manual"
    # True when an external supervisor (the Home Assistant add-on) owns
    # updates.  The UI hides every update notification and the periodic
    # check loop is skipped when this is set.  See ``_managed_externally``.
    managed_externally: bool
    profile: str  # "docker" | "pi"  (where this install is running)
    sidecar_url: str
    last_check: str | None = None
    last_update: str | None = None
    # ── Rollback bookkeeping (5.1) ──────────────────────────────────────
    # ``last_update_status`` reflects the most recent /update or /rollback
    # attempt as reported by the sidecar's GET /last-update endpoint:
    #   * ``in_progress``     – pull/recreate is currently running
    #   * ``success``         – /update completed; new image is in place
    #   * ``rolled_back``     – /rollback completed; previous digest restored
    #   * ``rollback_failed`` – /rollback errored out (typically retag failure)
    #   * ``failed``          – /update pull failed before we could recreate
    #   * ``none``            – no attempt has been made yet
    last_update_status: str | None = None
    last_update_action: str | None = None  # "update" | "rollback"
    last_update_error: str | None = None
    last_update_previous_digest: str | None = None
    last_update_completed_at: str | None = None
    # Most recent settings snapshots taken before each /system/update call.
    # Each entry includes ``previous_digest`` and ``previous_image`` so the
    # UI can offer "revert to the version that was running on <date>".
    settings_snapshots: list[dict[str, Any]] = []
    # If the most recent snapshot has materially more enabled plugins than
    # the live config, surface a recovery hint so users hit by issue #948
    # can roll back with one click instead of discovering the snapshot on
    # their own. ``None`` when there's no detectable regression.
    post_upgrade_regression: dict[str, Any] | None = None


class UpdateApplyResponse(BaseModel):
    """Response model for triggering an update."""

    status: str  # "queued" | "manual"
    mode: str  # "sidecar" | "manual"
    previous_digest: str | None = None
    hint: str | None = None
    # Metadata about the pre-update settings snapshot we just took.  None
    # when the snapshot could not be produced (still safe to update — the
    # user can still roll back the image alone via /system/update/rollback).
    settings_snapshot: dict[str, Any] | None = None


class RollbackRequest(BaseModel):
    """Request body for ``POST /system/update/rollback``.

    The user picks a snapshot to roll back to; the API restores the
    settings from that snapshot and asks the sidecar to retag the
    snapshot's recorded ``previous_digest`` / ``previous_image`` back
    onto the running container.

    * ``snapshot`` — optional snapshot filename.  When omitted, the most
      recent snapshot is used.  Must match the strict
      ``pre-update-YYYYMMDDTHHMMSS[.fff]Z.json`` shape produced by the API.
    * ``restore_settings`` — when False, only the image is rolled back
      (settings are left untouched).  Defaults to True.
    * ``restore_image`` — when False, only the settings are rolled back
      (image is left untouched).  Defaults to True.
    """

    snapshot: str | None = None
    restore_settings: bool = True
    restore_image: bool = True


class RollbackResponse(BaseModel):
    """Response model for the user-initiated rollback endpoint."""

    status: str  # "success" | "queued" | "partial"
    snapshot: str | None = None
    image_rollback: dict[str, Any] | None = None  # {target_digest, target_image, queued} or None
    settings_rollback: dict[str, Any] | None = None  # output of BackupService.import_from_json
    warnings: list[str] = []


class AutoUpdateRequest(BaseModel):
    """Request model for setting the auto-update preference.

    Accepts either ``interval`` (preferred) — one of ``daily``, ``weekly``,
    ``monthly``, ``manual`` — or the legacy ``enabled`` boolean, where True
    is mapped to the install's default interval and False is mapped to
    ``manual``.  At least one of the two must be provided.
    """

    enabled: bool | None = None
    interval: str | None = None


class AutoUpdateResponse(BaseModel):
    """Response model for auto-update toggle."""

    enabled: bool  # derived: True when interval != "manual"
    interval: str  # "daily" | "weekly" | "monthly" | "manual"


class SystemActionResponse(BaseModel):
    """Response model for restart / shutdown system actions."""

    status: str  # "queued"
    action: str  # "restart" | "shutdown"
