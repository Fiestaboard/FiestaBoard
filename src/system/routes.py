"""FastAPI router for the ``/version`` + ``/system`` update endpoint family (issue #1758).

Handlers moved verbatim from ``src/api_server.py``. Names that still live in
``api_server`` — or that moved to :mod:`src.system.update_service` and are
re-exported by ``api_server`` — are imported *inside* each handler so they
resolve through the api_server module at call time. A module-level import
would both create an import cycle (api_server imports this router) and
detach the handlers from the test-suite's ``patch("src.api_server.<name>")``
targets (the #1756/#1757 pattern).

``requests`` is imported at module level on purpose: the suite patches
``src.api_server.requests.get``/``.post``, which mutates the shared
``requests`` module object, so the patch reaches these handlers regardless
of which module they live in.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

import requests
from fastapi import APIRouter, HTTPException

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


@router.get("/version", response_model=VersionResponse)
async def version():
    """Get version information.

    Returns both the package version (from __version__) and the build version
    (from VERSION environment variable). In production builds, these should match.
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring
        __version__,
        _detect_hardware_model,
    )

    build_version = os.getenv("VERSION", "dev")
    production = os.getenv("PRODUCTION", "false").lower() == "true"
    return VersionResponse(
        package_version=__version__,
        build_version=build_version,
        is_dev=build_version == "dev" and not production,
        hardware_model=_detect_hardware_model(),
    )


@router.get("/system/update-check", response_model=UpdateCheckResponse)
async def system_update_check():
    """Check if a newer version of FiestaBoard is available.

    Checks both Docker Hub and the GitHub Releases API and reports the newest
    version either source lists (neither is preferred over the other, so a
    lagging source cannot hide a release the other already sees). No
    authentication is required because the package and repository are public.

    Returns the current version, latest version, and whether an update is available.
    """
    from src.api_server import _perform_update_check  # patched-in-tests seam — see module docstring

    return await _perform_update_check()


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
    from src.api_server import (  # patched-in-tests seam — see module docstring
        _detect_post_upgrade_regression,
        _fiestaboard_profile,
        _list_settings_snapshots,
        _managed_externally,
        _resolve_auto_update_interval,
        _system_update_state_load,
        _updater_last_update,
        _updater_probe,
        _updater_token,
        _updater_url,
    )

    state = _system_update_state_load()
    has_token = bool(_updater_token())
    available = await asyncio.to_thread(_updater_probe) if has_token else False
    # Only consult the sidecar's last-update record when it is reachable.
    last = await asyncio.to_thread(_updater_last_update) if available else {}
    interval = _resolve_auto_update_interval(state)
    snapshots = await asyncio.to_thread(_list_settings_snapshots)
    regression = await asyncio.to_thread(_detect_post_upgrade_regression)
    return UpdateStatusResponse(
        updater_available=available,
        auto_update_enabled=interval != "manual",
        auto_update_interval=interval,
        managed_externally=_managed_externally(),
        profile=_fiestaboard_profile(),
        sidecar_url=_updater_url(),
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


@router.post("/system/update", response_model=UpdateApplyResponse)
async def system_update_apply():
    """Trigger an in-place update via the fiestaupdater sidecar.

    The request returns 202 from the sidecar almost immediately; the actual
    container recreation happens shortly after, which will kill this process.
    Clients should expect their HTTP connection to drop and should poll
    `/health` to detect when the new version is up.

    If the sidecar is not running (user hasn't opted in), returns 503 with a
    `manual` mode response so the UI can fall back to instructions.
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring
        _system_update_state_update,
        _take_settings_snapshot,
        _updater_token,
        _updater_url,
        _updater_version,
    )

    if not _updater_token():
        raise HTTPException(
            status_code=503,
            detail={
                "status": "manual",
                "mode": "manual",
                "hint": "FIESTAUPDATER_TOKEN is not set. Add COMPOSE_PROFILES=fiestaupdater to your .env and run 'docker compose up -d' to enable in-app updates.",
            },
        )

    # Snapshot the current settings *before* we trigger the update so the
    # user can later choose to roll configuration back to this exact
    # moment via /system/update/rollback.  We tag the snapshot with the
    # currently-running image's digest + reference (looked up via the
    # sidecar's /version endpoint) so rollback knows which image to pair
    # with the restored settings.  A snapshot failure is non-fatal: the
    # user can still manually roll the image back via the sidecar.
    version = await asyncio.to_thread(_updater_version)
    snapshot = await asyncio.to_thread(
        _take_settings_snapshot,
        version.get("digest"),
        version.get("image"),
    )

    url = f"{_updater_url()}/update"
    headers = {"Authorization": f"Bearer {_updater_token()}"}

    def _post():
        return requests.post(url, headers=headers, timeout=(5, 30))

    try:
        resp = await asyncio.to_thread(_post)
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "manual",
                "mode": "manual",
                "hint": "Could not reach the fiestaupdater sidecar. Run 'docker compose pull && docker compose up -d' from your install directory to update manually.",
            },
        ) from None
    except Exception as e:
        logger.warning(f"fiestaupdater update call failed: {e}")
        raise HTTPException(status_code=502, detail={"status": "error", "error": str(e)}) from e

    if resp.status_code == 401:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "error": "fiestaupdater rejected our token; check FIESTAUPDATER_TOKEN matches in both services",
            },
        )
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "error": f"fiestaupdater returned {resp.status_code}: {resp.text[:200]}"},
        )

    # Record bookkeeping so the UI can show "last update".
    body = {}
    try:
        body = resp.json()
    except ValueError as e:
        # fiestaupdater may return a non-JSON body (e.g. plain-text on error); fall back to empty dict.
        logger.debug("fiestaupdater response is not JSON, using empty body (non-fatal): %s", e)
    _system_update_state_update(last_update=datetime.now(UTC).isoformat())

    return UpdateApplyResponse(
        status="queued",
        mode="sidecar",
        previous_digest=body.get("previous_digest"),
        settings_snapshot=snapshot,
    )


@router.post("/system/update/rollback", response_model=RollbackResponse)
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
            are False, or the snapshot has no recorded image to roll
            back to (and the user asked us to roll the image back).
        503 when the sidecar is needed but unreachable.
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring
        _DIGEST_RE,
        _IMAGE_REF_RE,
        _read_snapshot_metadata,
        _resolve_snapshot_name,
        _updater_token,
        _updater_url,
    )

    if not req.restore_settings and not req.restore_image:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error": "At least one of restore_settings, restore_image must be true.",
            },
        )

    path = await asyncio.to_thread(_resolve_snapshot_name, req.snapshot)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "not_found",
                "error": "No matching settings snapshot was found.",
            },
        )

    snapshot_meta = await asyncio.to_thread(_read_snapshot_metadata, path)

    warnings: list[str] = []
    settings_result: dict[str, Any] | None = None
    image_result: dict[str, Any] | None = None

    # ── Settings rollback ───────────────────────────────────────────────
    if req.restore_settings:
        try:
            raw = await asyncio.to_thread(path.read_text, "utf-8")
        except OSError as e:
            logger.warning("Could not read snapshot %s: %s", path, e)
            raise HTTPException(
                status_code=400,
                detail={"status": "error", "error": f"Could not read snapshot: {e}"},
            ) from e
        try:
            from src.backup.service import BackupError, get_backup_service
        except Exception as e:  # pragma: no cover - import error is exceptional
            logger.exception("BackupService unavailable")
            raise HTTPException(status_code=500, detail={"status": "error", "error": str(e)}) from e

        service = get_backup_service()
        try:
            # Don't reinstall plugins from a settings-only snapshot: the user is
            # rolling back configuration, not reshaping their plugin set.
            result = await asyncio.to_thread(service.import_from_json, raw, reinstall_plugins=False)
        except BackupError as e:
            raise HTTPException(
                status_code=400,
                detail={"status": "error", "error": str(e)},
            ) from e
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
        elif not _DIGEST_RE.fullmatch(digest) or not _IMAGE_REF_RE.fullmatch(image_ref):
            warnings.append("Snapshot's recorded image identity is malformed; image was not rolled back.")
        elif not _updater_token():
            warnings.append(
                "FIESTAUPDATER_TOKEN is not set; image rollback is unavailable. "
                "Settings have been restored but the image is unchanged."
            )
        else:
            url = f"{_updater_url()}/rollback"
            headers = {
                "Authorization": f"Bearer {_updater_token()}",
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
                    detail={
                        "status": "manual",
                        "error": "Could not reach the fiestaupdater sidecar; image rollback unavailable.",
                    },
                ) from None
            except Exception as e:
                logger.warning("fiestaupdater rollback call failed: %s", e)
                raise HTTPException(status_code=502, detail={"status": "error", "error": str(e)}) from e

            if resp.status_code == 401:
                raise HTTPException(
                    status_code=500,
                    detail={"status": "error", "error": "fiestaupdater rejected our token"},
                )
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "status": "error",
                        "error": f"fiestaupdater returned {resp.status_code}: {resp.text[:200]}",
                    },
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


@router.post("/system/update/auto", response_model=AutoUpdateResponse)
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
    from src.api_server import (  # patched-in-tests seam — see module docstring
        AUTO_UPDATE_INTERVALS,
        _auto_update_default_interval,
        _system_update_state_update,
    )

    if req.interval is not None:
        if req.interval not in AUTO_UPDATE_INTERVALS:
            raise HTTPException(
                status_code=422,
                detail=(f"Invalid interval {req.interval!r}; must be one of: {sorted(AUTO_UPDATE_INTERVALS.keys())}"),
            )
        interval = req.interval
    elif req.enabled is not None:
        interval = _auto_update_default_interval() if req.enabled else "manual"
    else:
        raise HTTPException(
            status_code=422,
            detail="Request must include either 'interval' or 'enabled'.",
        )

    _system_update_state_update(
        auto_update_interval=interval,
        # Keep the legacy bool in sync so older clients reading the file see a
        # consistent picture.
        auto_update_enabled=interval != "manual",
    )
    return AutoUpdateResponse(enabled=interval != "manual", interval=interval)


@router.post("/system/restart", response_model=SystemActionResponse)
async def system_restart():
    """Restart the FiestaBoard container via the fiestaupdater sidecar.

    The connection will drop while the container restarts (~5 s).
    Clients should poll /health until it comes back.
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring
        _handle_updater_response,
        _require_updater_token,
        _updater_post,
    )

    _require_updater_token()
    try:
        resp = await asyncio.to_thread(_updater_post, "/restart")
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "hint": "Could not reach the fiestaupdater sidecar."},
        ) from None
    except Exception as e:
        logger.warning("fiestaupdater restart call failed: %s", e)
        raise HTTPException(status_code=502, detail={"status": "error", "error": str(e)}) from e
    return _handle_updater_response(resp, "restart")


@router.post("/system/shutdown", response_model=SystemActionResponse)
async def system_shutdown():
    """Shut down the host machine via the fiestaupdater sidecar.

    The sidecar stops all compose services, then powers off the host.
    Requires the fiestaupdater container to have the SYS_BOOT capability
    (cap_add: [SYS_BOOT] in docker-compose.yml).
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring
        _handle_updater_response,
        _require_updater_token,
        _updater_post,
    )

    _require_updater_token()
    try:
        resp = await asyncio.to_thread(_updater_post, "/shutdown")
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "hint": "Could not reach the fiestaupdater sidecar."},
        ) from None
    except Exception as e:
        logger.warning("fiestaupdater shutdown call failed: %s", e)
        raise HTTPException(status_code=502, detail={"status": "error", "error": str(e)}) from e
    return _handle_updater_response(resp, "shutdown")
