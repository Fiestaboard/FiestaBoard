"""Backup and restore module.

Provides a single :class:`BackupService` that can serialise the user's
FiestaBoard configuration (config, settings, pages, carousels, schedules
and installed external-plugin metadata) into a portable JSON document and
restore it on a new instance.
"""

from .service import (
    BACKUP_SCHEMA_VERSION,
    BackupError,
    BackupService,
    get_backup_service,
)

__all__ = [
    "BACKUP_SCHEMA_VERSION",
    "BackupError",
    "BackupService",
    "get_backup_service",
]
