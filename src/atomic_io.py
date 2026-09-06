"""Atomic file writes for FiestaBoard's JSON stores.

Every long-lived store under ``data/`` (config, settings, pages, schedules,
collections, panels, auth) writes by staging a temp file next to the target and
then ``os.replace``-ing it into place, so a mid-write crash never truncates the
real file (see #1304).

That pattern is only safe if each writer owns its staging file, and writers
come from more than one process: every ``pytest -n auto`` xdist worker, the API
server alongside a CLI script or the MQTT bridge. With one fixed
``<file>.tmp`` name, the process that renames second finds its source already
renamed away and ``os.replace`` fails with ``ENOENT``, taking the save (and, in
tests, an unrelated request) down with it. Scoping the staging name to the
process — plus a per-process monotonic counter — removes that collision while
keeping staging file and target siblings, so the rename stays a
same-filesystem rename.

The counter matters within one process too: two threads writing the same
target (a settings PUT racing a backup restore, #1860) each get their own
staging file, so neither can truncate or adopt the other's half-written temp.
Unique staging names make the *rename* safe, not the *data*: last rename still
wins, so writers that must not lose each other's updates still serialise their
saves. The stores built on :class:`src.storage.json_store.JsonStore` do this
with the store's ``RLock``; stores with their own locking (``ConfigManager``)
hold that lock across the write. This module itself is lock-free — it provides
the atomic write, not the serialisation.
"""

import contextlib
import itertools
import json
import os
import stat
from pathlib import Path
from typing import Any, TextIO

#: Per-process monotonic counter folded into every staging name so that no two
#: calls — even from different threads staging the same target — ever share a
#: staging file (#1860).
_staging_counter = itertools.count()


def staging_path(target: Path) -> Path:
    """Return a unique staging path to write before renaming onto *target*.

    ``data/pages.json`` becomes ``data/pages.json.<pid>.<n>.tmp`` where
    ``<n>`` is a per-process monotonic counter. Every call returns a fresh
    path: unique across processes (the pid) and across calls within one
    process (the counter), so concurrent writers can never open, truncate,
    or rename each other's staging file.
    """
    return target.with_suffix(f"{target.suffix}.{os.getpid()}.{next(_staging_counter)}.tmp")


def _open_staging(tmp_path: Path, private: bool) -> TextIO:
    """Open *tmp_path* for writing.

    ``private=True`` creates the file with owner-only (0600) permissions via
    ``os.open`` so a credential store is never world-readable, even briefly.
    The default path uses builtins ``open`` — deliberately, so existing tests
    that patch ``builtins.open`` to inject I/O errors keep working.
    """
    if private:
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        return os.fdopen(fd, "w", encoding="utf-8")
    return open(tmp_path, "w", encoding="utf-8")  # noqa: PTH123


def write_json_atomic(
    target: Path,
    data: Any,
    *,
    indent: int | None = 2,
    private: bool = False,
) -> None:
    """Serialise *data* as JSON onto *target* without ever truncating it.

    Stages the JSON in the process-scoped sibling from :func:`staging_path`,
    fsyncs, and ``os.replace``s it into place. A crash (OOM, SIGKILL, power
    loss) partway through the write leaves the previous contents of *target*
    fully intact, and the partial staging file is removed on any failure
    rather than leaked.

    Parent directories are created if missing. ``private=True`` creates the
    file owner-only (0600). Exceptions propagate — the caller decides whether
    a failed save is fatal.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = staging_path(target)
    try:
        with _open_staging(tmp_path, private) as fh:
            json.dump(data, fh, indent=indent)
            fh.flush()
            os.fsync(fh.fileno())
        tmp_path.replace(target)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


def write_text_atomic(target: Path, text: str, *, private: bool = False) -> None:
    """Write pre-serialised *text* onto *target* with the same guarantees as
    :func:`write_json_atomic` (staging sibling, fsync, ``os.replace``).

    For callers that already hold serialised content (e.g. an annotated
    settings snapshot) and only need the atomic install.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = staging_path(target)
    try:
        with _open_staging(tmp_path, private) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        tmp_path.replace(target)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise
