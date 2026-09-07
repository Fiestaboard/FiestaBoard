"""FastAPI router for the ``/version`` + ``/system`` update endpoint family (issue #1758).

Converted to the API conventions by the Phase 2 ``system`` slice
(``docs/internal/reference/API_CONVENTIONS.md``, enforced by
``tests/test_api_conventions_ratchet.py``):

* every ``HTTPException.detail`` is a **string** — the dict details these
  handlers used to raise carried ad-hoc ``status`` / ``mode`` / ``error`` /
  ``hint`` keys, no ``message``, and no reader: ``web/src/lib/api/core.ts``
  simply ``JSON.stringify``\\ s a non-string detail into the error toast;
* every route declares ``responses=`` for the codes it can actually answer.

Collaborators are resolved through :mod:`src.system.update_service`, which is
where they live. Nothing here imports ``src.api_server`` — not at module level
and not at call time — so ``import src.system.routes`` never drags the monolith
in (``tests/test_system_seams.py`` asserts that in a fresh interpreter). Tests
patch the service module: ``patch("src.system.update_service.<name>")``.

The module object is imported rather than its members so that a patch applied
to ``src.system.update_service`` after import time still steers these handlers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

import requests
from fastapi import APIRouter, HTTPException

from src import __version__

from . import update_service
from .models import (
    AutoUpdateRequest,
    AutoUpdateResponse,
    RollbackRequest,
    RollbackResponse,
    SystemActionResponse,
    UpdateApplyResponse,
    UpdateCheckResponse,
    UpdateStatusResponse,
    VersionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

#: Declared error responses, reused across the sidecar-backed routes. Every
#: code here is one these handlers actually raise.
_SIDECAR_UNAVAILABLE = {503: {"description": "The fiestaupdater sidecar is not configured or not reachable"}}
_SIDECAR_ERRORS = {
    500: {"description": "The sidecar rejected our token"},
    502: {"description": "The sidecar answered with an error"},
    **_SIDECAR_UNAVAILABLE,
}


@router.get("/version", response_model=VersionResponse)
async def version():
    """Get version information.

    Returns both the package version (from __version__) and the build version
    (from VERSION environment variable). In production builds, these should match.
    """
    build_version = os.getenv("VERSION", "dev")
    production = os.getenv("PRODUCTION", "false").lower() == "true"
    return VersionResponse(
        package_version=__version__,
        build_version=build_version,
        is_dev=build_version == "dev" and not production,
        hardware_model=update_service._detect_hardware_model(),
    )


@router.get("/system/update-check", response_model=UpdateCheckResponse)
async def system_update_check():
    """Check if a newer version of FiestaBoard is available.

    Checks both Docker Hub and the GitHub Releases API and reports the newest
    version either source lists (neither is preferred over the other, so a
    lagging source cannot hide a release the other already sees). No
    authentication is required because the package and repository are public.

    Returns the current version, latest version, and whether an update is available.

    This is a **probe endpoint** in the sense of API_CONVENTIONS.md: an
    unreachable Docker Hub is a verdict about something else, reported at 200
    in the declared ``error`` field, not a failure of this request.
    """
    return await update_service._perform_update_check()


@router.get("/system/update/status", response_model=UpdateStatusResponse)
async def system_update_status():
    """Report whether the FiestaUpdater sidecar is reachable and whether the
    user has opted in to scheduled auto-updates.

    The UI uses this to decide between showing the in-app "Update Now" button
    or fallback "manual update" instructions.

    Also reports the outcome of the most recent /system/update or
    /system/update/rollback attempt, plus the list of available settings
    snapshots, so the UI can offer "revert to the version that was
    running on <date>" without polling the sidecar separately.
    """
    state = update_service._system_update_state_load()
    has_token = bool(update_service._updater_token())
    available = await asyncio.to_thread(update_service._updater_probe) if has_token else False
    # Only consult the sidecar's last-update record when it is reachable.
    last = await asyncio.to_thread(update_service._updater_last_update) if available else {}
    interval = update_service._resolve_auto_update_interval(state)
    snapshots = await asyncio.to_thread(update_service._list_settings_snapshots)
    regression = await asyncio.to_thread(update_service._detect_post_upgrade_regression)
    return UpdateStatusResponse(
        updater_available=available,
        auto_update_enabled=interval != "manual",
        auto_update_interval=interval,
        managed_externally=update_service._managed_externally(),
        profile=update_service._fiestaboard_profile(),
        sidecar_url=update_service._updater_url(),
        last_check=state.get("last_check"),
        last_update=state.get("last_update"),
        last_update_status=last.get("status"),
        last_update_action=last.get("action"),
        last_update_error=last.get("error"),
        last_update_previous_digest=last.get("previous_digest"),
        last_update_completed_at=last.get("completed_at"),
        settings_snapshots=snapshots,
        post_upgrade_regression=regression,
    )


@router.post("/system/update", response_model=UpdateApplyResponse, responses=_SIDECAR_ERRORS)
async def system_update_apply():
    """Trigger an in-place update via the fiestaupdater sidecar.

    The request returns 202 from the sidecar almost immediately; the actual
    container recreation happens shortly after, which will kill this process.
    Clients should expect their HTTP connection to drop and should poll
    `/health` to detect when the new version is up.

    Raises:
        503 when the sidecar is not configured or not reachable, with the
            manual-update instructions as the detail so the UI can show them.
        500 when the sidecar rejects our shared token.
        502 for any other sidecar failure.
    """
    if not update_service._updater_token():
        raise HTTPException(
            status_code=503,
            detail=(
                "FIESTAUPDATER_TOKEN is not set. Add COMPOSE_PROFILES=fiestaupdater to your .env "
                "and run 'docker compose up -d' to enable in-app updates."
            ),
        )

    # Snapshot the current settings *before* we trigger the update so the
    # user can later choose to roll configuration back to this exact
    # moment via /system/update/rollback.  We tag the snapshot with the
    # currently-running image's digest + reference (looked up via the
    # sidecar's /version endpoint) so rollback knows which image to pair
    # with the restored settings.  A snapshot failure is non-fatal: the
    # user can still manually roll the image back via the sidecar.
    version = await asyncio.to_thread(update_service._updater_version)
    snapshot = await asyncio.to_thread(
        update_service._take_settings_snapshot,
        version.get("digest"),
        version.get("image"),
    )

    url = f"{update_service._updater_url()}/update"
    headers = {"Authorization": f"Bearer {update_service._updater_token()}"}

    def _post():
        return requests.post(url, headers=headers, timeout=(5, 30))

    try:
        resp = await asyncio.to_thread(_post)
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Could not reach the fiestaupdater sidecar. Run 'docker compose pull && docker compose up -d' "
                "from your install directory to update manually."
            ),
        ) from None
    except Exception as e:
        logger.warning(f"fiestaupdater update call failed: {e}")
        raise HTTPException(status_code=502, detail=f"fiestaupdater update call failed: {e}") from e

    if resp.status_code == 401:
        raise HTTPException(
            status_code=500,
            detail="fiestaupdater rejected our token; check FIESTAUPDATER_TOKEN matches in both services",
        )
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"fiestaupdater returned {resp.status_code}: {resp.text[:200]}",
        )

    # Record bookkeeping so the UI can show "last update".
    body = {}
    try:
        body = resp.json()
    except ValueError as e:
        # fiestaupdater may return a non-JSON body (e.g. plain-text on error); fall back to empty dict.
        logger.debug("fiestaupdater response is not JSON, using empty body (non-fatal): %s", e)
    update_service._system_update_state_update(last_update=datetime.now(UTC).isoformat())

    return UpdateApplyResponse(
        status="queued",
        mode="sidecar",
        previous_digest=body.get("previous_digest"),
        settings_snapshot=snapshot,
    )


@router.post(
    "/system/update/rollback",
    response_model=RollbackResponse,
    responses={
        400: {"description": "Nothing to restore, or the snapshot is unreadable"},
        404: {"description": "No matching settings snapshot"},
        **_SIDECAR_ERRORS,
    },
)
async def system_update_rollback(req: RollbackRequest):
    """Roll the running instance back to a previous version.

    The user selects a snapshot — the most recent by default — and we:

    1. Look up the snapshot's recorded ``previous_digest`` /
       ``previous_image`` (captured the moment the snapshot was taken).
    2. (When ``restore_settings=True``, the default) restore configuration
       from the snapshot via :class:`~src.backup.service.BackupService`.
    3. (When ``restore_image=True``, the default) ask the sidecar's
       ``POST /rollback`` to retag that digest back onto the original
       image reference and force-recreate the container.

    Settings are restored *before* the image flip so that when the
    container comes back up on the previous image, it reads the matching
    configuration.

    Raises:
        404 when no matching snapshot exists.
        400 when the snapshot is unreadable, both ``restore_*`` flags
            are False, or the snapshot document is not a backup.
        500 when the restore is aborted by the environment, or the sidecar
            rejects our token.
        502 when the sidecar answers with an error.
        503 when the sidecar is needed but unreachable.

    A snapshot with no recorded image identity, or a missing sidecar token,
    is *partial success*, not a failure: the settings were restored, so the
    response is a 200 whose ``warnings`` name what was skipped.
    """
    if not req.restore_settings and not req.restore_image:
        raise HTTPException(
            status_code=400,
            detail="At least one of restore_settings, restore_image must be true.",
        )

    path = await asyncio.to_thread(update_service._resolve_snapshot_name, req.snapshot)
    if path is None:
        raise HTTPException(status_code=404, detail="No matching settings snapshot was found.")

    snapshot_meta = await asyncio.to_thread(update_service._read_snapshot_metadata, path)

    warnings: list[str] = []
    settings_result: dict[str, Any] | None = None
    image_result: dict[str, Any] | None = None

    # ── Settings rollback ───────────────────────────────────────────────
    if req.restore_settings:
        try:
            raw = await asyncio.to_thread(path.read_text, "utf-8")
        except OSError as e:
            logger.warning("Could not read snapshot %s: %s", path, e)
            raise HTTPException(status_code=400, detail=f"Could not read snapshot: {e}") from e
        try:
            from src.backup.service import BackupError, BackupRestoreAborted, get_backup_service
        except Exception as e:  # pragma: no cover - import error is exceptional
            logger.exception("BackupService unavailable")
            raise HTTPException(status_code=500, detail=f"Backup service unavailable: {e}") from e

        service = get_backup_service()
        try:
            # Don't reinstall plugins from a settings-only snapshot: the user is
            # rolling back configuration, not reshaping their plugin set.
            result = await asyncio.to_thread(service.import_from_json, raw, reinstall_plugins=False)
        except BackupRestoreAborted as e:
            # Environment failure (unwritable data dir, full disk), not a bad
            # snapshot — see Phase 2 Task 10d.
            logger.error("Settings rollback aborted: %s", e)
            raise HTTPException(status_code=500, detail=str(e)) from e
        except BackupError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        settings_result = {
            "restored_from": path.name,
            "restored_files": result.get("restored_files", []),
            "skipped_files": result.get("skipped_files", []),
            "pre_restore_backup_suffix": result.get("pre_restore_backup_suffix", ""),
            "reload_errors": result.get("reload_errors", []),
        }

    # ── Image rollback ──────────────────────────────────────────────────
    if req.restore_image:
        digest = snapshot_meta.get("previous_digest")
        image_ref = snapshot_meta.get("previous_image")
        if not digest or not image_ref:
            # Old snapshot taken before we started annotating.  We can't
            # safely guess the digest, so report partial success rather
            # than guessing.
            warnings.append("Snapshot does not record a previous image digest; image was not rolled back.")
        elif not update_service._DIGEST_RE.fullmatch(digest) or not update_service._IMAGE_REF_RE.fullmatch(image_ref):
            warnings.append("Snapshot's recorded image identity is malformed; image was not rolled back.")
        elif not update_service._updater_token():
            warnings.append(
                "FIESTAUPDATER_TOKEN is not set; image rollback is unavailable. "
                "Settings have been restored but the image is unchanged."
            )
        else:
            url = f"{update_service._updater_url()}/rollback"
            headers = {
                "Authorization": f"Bearer {update_service._updater_token()}",
                "Content-Type": "application/json",
            }
            payload = {"digest": digest, "image": image_ref}

            def _post():
                return requests.post(url, headers=headers, json=payload, timeout=(5, 30))

            try:
                resp = await asyncio.to_thread(_post)
            except requests.exceptions.ConnectionError:
                raise HTTPException(
                    status_code=503,
                    detail="Could not reach the fiestaupdater sidecar; image rollback unavailable.",
                ) from None
            except Exception as e:
                logger.warning("fiestaupdater rollback call failed: %s", e)
                raise HTTPException(status_code=502, detail=f"fiestaupdater rollback call failed: {e}") from e

            if resp.status_code == 401:
                raise HTTPException(status_code=500, detail="fiestaupdater rejected our token")
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail=f"fiestaupdater returned {resp.status_code}: {resp.text[:200]}",
                )

            image_result = {
                "target_digest": digest,
                "target_image": image_ref,
                "queued": True,
            }

    overall = "success" if not warnings else "partial"
    return RollbackResponse(
        status=overall,
        snapshot=path.name,
        image_rollback=image_result,
        settings_rollback=settings_result,
        warnings=warnings,
    )


@router.post(
    "/system/update/auto",
    response_model=AutoUpdateResponse,
    responses={422: {"description": "Neither interval nor enabled was supplied, or the interval is unknown"}},
)
async def system_update_set_auto(req: AutoUpdateRequest):
    """Set the auto-update preference.

    Accepts either ``interval`` (preferred) — one of ``daily``, ``weekly``,
    ``monthly``, ``manual`` — or the legacy ``enabled`` boolean.  Legacy
    booleans map to: True → install default interval (``daily`` on Pi,
    ``weekly`` on Docker) and False → ``manual``.

    The background scheduler (started in the API lifespan) reads this value
    on each tick, so changes take effect within the next polling window
    without requiring a restart.
    """
    if req.interval is not None:
        if req.interval not in update_service.AUTO_UPDATE_INTERVALS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid interval {req.interval!r}; "
                    f"must be one of: {sorted(update_service.AUTO_UPDATE_INTERVALS.keys())}"
                ),
            )
        interval = req.interval
    elif req.enabled is not None:
        interval = update_service._auto_update_default_interval() if req.enabled else "manual"
    else:
        raise HTTPException(
            status_code=422,
            detail="Request must include either 'interval' or 'enabled'.",
        )

    update_service._system_update_state_update(
        auto_update_interval=interval,
        # Keep the legacy bool in sync so older clients reading the file see a
        # consistent picture.
        auto_update_enabled=interval != "manual",
    )
    return AutoUpdateResponse(enabled=interval != "manual", interval=interval)


@router.post("/system/restart", response_model=SystemActionResponse, responses=_SIDECAR_ERRORS)
async def system_restart():
    """Restart the FiestaBoard container via the fiestaupdater sidecar.

    The connection will drop while the container restarts (~5 s).
    Clients should poll /health until it comes back.
    """
    update_service._require_updater_token()
    try:
        resp = await asyncio.to_thread(update_service._updater_post, "/restart")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Could not reach the fiestaupdater sidecar.") from None
    except Exception as e:
        logger.warning("fiestaupdater restart call failed: %s", e)
        raise HTTPException(status_code=502, detail=f"fiestaupdater restart call failed: {e}") from e
    return update_service._handle_updater_response(resp, "restart")


@router.post("/system/shutdown", response_model=SystemActionResponse, responses=_SIDECAR_ERRORS)
async def system_shutdown():
    """Shut down the host machine via the fiestaupdater sidecar.

    The sidecar stops all compose services, then powers off the host.
    Requires the fiestaupdater container to have the SYS_BOOT capability
    (cap_add: [SYS_BOOT] in docker-compose.yml).
    """
    update_service._require_updater_token()
    try:
        resp = await asyncio.to_thread(update_service._updater_post, "/shutdown")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Could not reach the fiestaupdater sidecar.") from None
    except Exception as e:
        logger.warning("fiestaupdater shutdown call failed: %s", e)
        raise HTTPException(status_code=502, detail=f"fiestaupdater shutdown call failed: {e}") from e
    return update_service._handle_updater_response(resp, "shutdown")
