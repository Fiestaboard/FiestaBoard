"""Per-install identifiers kept in a small private file in the data dir.

Read on hot paths (the connection listing builds ChatGPT's target), so this
never raises: two first uses at once agree on one id, a file left empty by a
crash is regenerated, and an unwritable data dir falls back to an id kept in
memory for the life of the process.
"""

from __future__ import annotations

import contextlib
import logging
import os
import stat
import threading
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_in_memory: dict[str, str] = {}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def load_or_create(path: Path) -> str:
    """The identifier stored at *path*, created (0600) on first use."""
    path = Path(path)
    existing = _read(path)
    if existing:
        return existing
    with _lock:
        existing = _read(path) or _in_memory.get(str(path), "")
        if existing:
            return existing
        identifier = str(uuid.uuid4())
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(identifier)
            try:
                # Atomic and never overwrites: another process may have won.
                os.link(tmp, path)
            except FileExistsError:
                winner = _read(path)
                if winner:
                    return winner
                tmp.replace(path)  # an empty leftover from a crash
            except OSError:
                # No hard links on this filesystem: a plain rename will do.
                winner = _read(path)
                if winner:
                    return winner
                tmp.replace(path)
        except OSError as exc:
            logger.warning("Could not save %s (%s); using an id for this run only", path.name, exc)
            _in_memory[str(path)] = identifier
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()
        return identifier
