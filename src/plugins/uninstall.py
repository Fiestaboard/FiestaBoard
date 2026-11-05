"""Reversible code-cache staging for a caught uninstall failure.

The config commit is owned by the registry. This helper does not provide a
crash journal or automatically interpret leftovers from an earlier process.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path

from .errors import PluginOperationFailed

logger = logging.getLogger(__name__)


class StagedPluginRemoval:
    """Hide an installed tree without destroying its rollback copy."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.root: Path | None = None
        self.backup: Path | None = None
        self.committed = False
        self._root_identity: tuple[int, int] | None = None
        self._code_identity: tuple[int, int] | None = None

    @staticmethod
    def _identity(path: Path) -> tuple[int, int]:
        value = path.lstat()
        return value.st_dev, value.st_ino

    def _owned_root(self) -> bool:
        return (
            self.root is not None
            and not self.root.is_symlink()
            and self._identity(self.root) == self._root_identity
        )

    def __enter__(self) -> StagedPluginRemoval:
        pending = list(self.path.parent.glob(f".{self.path.name}.uninstall-*"))
        if pending:
            logger.error("Uninstall cache requires inspection before retry for %s: %s", self.path.name, pending)
            raise PluginOperationFailed("Uninstall recovery cache requires inspection; see server logs before retrying.")
        if not self.path.exists() and not self.path.is_symlink():
            return self
        if not self.path.is_dir() or self.path.is_symlink():
            raise PluginOperationFailed("Installed plugin path is not a verified directory; uninstall was not started.")
        self._code_identity = self._identity(self.path)
        self.root = Path(tempfile.mkdtemp(prefix=f".{self.path.name}.uninstall-", dir=self.path.parent))
        self._root_identity = self._identity(self.root)
        self.backup = self.root / self.path.name
        try:
            self.path.rename(self.backup)
        except BaseException:
            try:
                if self._owned_root():
                    self.root.rmdir()
            except OSError:
                logger.warning("Could not remove unused uninstall staging directory %s", self.root, exc_info=True)
            raise
        return self

    def commit(self) -> None:
        """The combined config purge/tombstone is now durable."""
        self.committed = True

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if self.root is None:
            return False
        if self.committed:
            if exc_type is not None:
                self.retain_after_failure()
            return False
        try:
            if (
                not self._owned_root()
                or self.backup is None
                or self._identity(self.backup) != self._code_identity
            ):
                raise OSError("Uninstall rollback copy is no longer the owned code tree")
            if self.path.exists() or self.path.is_symlink():
                raise FileExistsError("An unexpected replacement occupies the plugin path")
            self.backup.rename(self.path)
        except BaseException as rollback:
            logger.error("Plugin uninstall rollback failed; code cache retained at %s", self.root, exc_info=True)
            raise PluginOperationFailed(
                "Uninstall failed and code rollback failed; recovery cache was retained. See server logs before retrying."
            ) from rollback
        try:
            if self._owned_root():
                self.root.rmdir()
        except OSError:
            logger.warning("Code rollback succeeded but empty staging cache remains at %s", self.root, exc_info=True)
        return False

    def retain_after_failure(self) -> None:
        logger.error("Uninstall committed but teardown failed; recovery cache retained at %s", self.root)

    def cleanup(self, remove: Callable[[Path], bool]) -> None:
        """Best-effort GC of the committed, hidden code cache, outside registry lock."""
        if self.root is None:
            return
        try:
            if not self._owned_root():
                raise OSError("Uninstall staging directory is no longer transaction-owned")
            remove(self.root)
        except OSError:
            logger.warning("Plugin uninstalled; hidden code cache cleanup is pending at %s", self.root, exc_info=True)
