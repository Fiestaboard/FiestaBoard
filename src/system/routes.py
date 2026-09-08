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

Two multi-step workflows — the update apply and the rollback — moved down into
that service when ``system`` opted into ``tests/test_layering_ratchet.py``.
They raise :class:`~src.system.update_service.SidecarError`, which carries the
status code and detail these endpoints have always answered; the handlers
translate it into ``HTTPException`` and change nothing about it.
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException

from src import __version__
from src.api_errors import errors

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


def _as_http(exc: update_service.SidecarError) -> HTTPException:
    """The domain's refusal, in the transport's vocabulary.

    Status and detail pass through untouched — ``tests/test_system_contract.py``
    pins every pair by value.
    """
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


#: Declared error responses, reused across the sidecar-backed routes. Every
#: code here is one these handlers actually raise.
#:
#: Built with :func:`src.api_errors.errors` like every other domain. This module
#: used to hand-write the dict, which cost it the ``model=ErrorResponse`` on all
#: fifteen of its declarations — so ``/system/*`` errors published no response
#: body in the OpenAPI schema while every other domain published
#: ``{"detail": string}`` — and let eleven inline descriptions drift from the
#: canonical text. It was written that way because ``errors()`` had no 500
#: entry and raised; it has one now.
_SIDECAR_ERRORS = errors(500, 502, 503)


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
    try:
        return await update_service.apply_update()
    except update_service.SidecarError as exc:
        raise _as_http(exc) from exc


@router.post(
    "/system/update/rollback",
    response_model=RollbackResponse,
    responses=errors(400, 404, 500, 502, 503),
)
async def system_update_rollback(req: RollbackRequest):
    """Roll the running instance back to a previous version.

    The user selects a snapshot — the most recent by default — and we restore
    configuration from it (when ``restore_settings``) and ask the sidecar to
    retag the recorded digest back onto the original image reference (when
    ``restore_image``). Settings are restored *before* the image flip so that
    when the container comes back up on the previous image, it reads the
    matching configuration.

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
    try:
        return await update_service.rollback(req)
    except update_service.SidecarError as exc:
        raise _as_http(exc) from exc


@router.post(
    "/system/update/auto",
    response_model=AutoUpdateResponse,
    # 400, not 422. Both rejections below are hand-raised semantic checks on a
    # body that already passed schema validation, and they answer the domain's
    # `{"detail": <string>}`. FastAPI's own 422 — a different body shape,
    # `{"detail": [ ... ]}` — stays this route's 422, generated as usual.
    # Declaring `errors(422)` here would have published the wrong model for it,
    # which is the contradiction review finding 5 named.
    responses=errors(400),
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
                status_code=400,
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
            status_code=400,
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
    try:
        return await update_service.perform_sidecar_action("restart")
    except update_service.SidecarError as exc:
        raise _as_http(exc) from exc


@router.post("/system/shutdown", response_model=SystemActionResponse, responses=_SIDECAR_ERRORS)
async def system_shutdown():
    """Shut down the host machine via the fiestaupdater sidecar.

    The sidecar stops all compose services, then powers off the host.
    Requires the fiestaupdater container to have the SYS_BOOT capability
    (cap_add: [SYS_BOOT] in docker-compose.yml).
    """
    try:
        return await update_service.perform_sidecar_action("shutdown")
    except update_service.SidecarError as exc:
        raise _as_http(exc) from exc
