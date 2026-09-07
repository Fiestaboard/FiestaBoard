"""FastAPI router for backup export and restore.

``GET /backup/export`` downloads every user-owned store as one JSON document;
``POST /backup/import`` restores such a document onto a running instance.

Phase 2, Task 8 — the last untagged routes. Moved out of ``src/api_server.py``
and converted to ``docs/internal/reference/API_CONVENTIONS.md``: the import
body is a Pydantic model instead of ``dict[str, Any]``, the response is a
declared model, the ``{"status": "success"}`` envelope is gone, and both
failure codes are declared.

``GET /backup/export`` carries two checked-in ratchet exceptions, both in
``tests/conventions_manifest.json``: it serves an opaque file download behind
``Content-Disposition``, not a JSON model, so there is no ``response_model``
to declare and no failure of its own to document.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Response

from src.api_errors import errors

from .models import BackupDocument, BackupImportResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["backup"])


@router.get("/backup/export")
async def export_backup():
    """Download a JSON file containing all user data (config, settings,
    pages, collections, schedules, and metadata for installed external
    plugins).

    The file can be re-uploaded to ``/backup/import`` on a new instance
    to migrate or restore a configuration.
    """
    from . import get_backup_service

    payload = get_backup_service().export_to_json()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"fiestaboard-backup-{timestamp}.json"
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/backup/import", response_model=BackupImportResponse, responses=errors(400, 500))
async def import_backup(
    payload: BackupDocument,
    reinstall_plugins: bool = Query(True),
):
    """Restore a backup file produced by ``/backup/export``.

    Existing data files are preserved as ``<name>.json.pre-restore-<ts>``
    siblings before being overwritten so the operator can roll back
    manually if needed.  In-memory service singletons are reloaded so the
    change takes effect without restarting the container.
    """
    from . import BackupError, BackupRestoreAborted, get_backup_service

    # ``exclude_unset`` keeps the document byte-for-byte what was uploaded:
    # a key the file did not carry must stay absent, not arrive as an
    # explicit null the restore would then have to special-case.
    document = payload.model_dump(exclude_unset=True)

    try:
        result = get_backup_service().import_from_dict(document, reinstall_plugins=reinstall_plugins)
    except BackupRestoreAborted as exc:
        # The environment failed, not the uploaded file — a 400 would blame
        # the operator's backup for a full disk (Phase 2 Task 10d).
        logger.error("Backup restore aborted: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Backup import failed")
        raise HTTPException(status_code=500, detail="Backup import failed") from None

    return result
