"""Atomic file writes for FiestaBoard's JSON stores.

Every long-lived store under ``data/`` (config, settings, pages, schedules,
collections, panels, auth) writes by staging a temp file next to the target and
then ``os.replace``-ing it into place, so a mid-write crash never truncates the
real file (see #1304).

That pattern is only safe if each writer owns its staging file. Within one
process that is a live concern: two threads writing the same target (a
settings PUT racing a backup restore, #1860) each need their own staging file,
or one truncates or adopts the other's half-written temp. The per-process
monotonic counter gives them that; the pid in the name extends the same
guarantee to any second process that ever appears, without which the process
that renames second would find its source already renamed away and
``os.replace`` would fail with ``ENOENT``. Both keep staging file and target
siblings, so the rename stays a same-filesystem rename.

(An earlier version of this note named ``pytest -n auto`` workers, "the MQTT
bridge" and "CLI scripts" as *current* multi-process writers. Measured against
this tree in the Phase 2 audit, none of them are: xdist workers each get their
own data dir from ``tests/conftest.py``, MQTT is a daemon thread inside the
API process, and no shipped script under ``scripts/`` writes the data dir. The
pid scoping is defence for a topology that does not exist today — see
``docs/internal/reference/PERSISTENCE.md``.)

Unique staging names make the *rename* safe, not the *data*: last rename still
wins, so writers that must not lose each other's updates still serialise their
saves. The stores built on :class:`src.storage.json_store.JsonStore` do this
with the store's ``RLock``; stores with their own locking (``ConfigManager``)
hold that lock across the write. Those locks are in-process only — there is
deliberately no cross-process file lock; see PERSISTENCE.md for why. This
module itself is lock-free — it provides the atomic write, not the
serialisation.
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
