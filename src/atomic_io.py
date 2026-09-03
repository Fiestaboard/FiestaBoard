"""Naming for the staging files used by FiestaBoard's atomic JSON writes.

Every long-lived store under ``data/`` (config, settings, pages, schedules,
collections, auth) writes by staging a temp file next to the target and then
``os.replace``-ing it into place, so a mid-write crash never truncates the
real file (see #1304).

That pattern is only safe if each writer owns its staging file. The in-process
locks guarding these stores are ``threading.Lock``, so they serialise threads
and nothing else — and ``data/`` is routinely shared by more than one process:
every ``pytest -n auto`` xdist worker, the API server alongside a CLI script or
the MQTT bridge. With one fixed ``<file>.tmp`` name, the process that renames
second finds its source already renamed away and ``os.replace`` fails with
``ENOENT``, taking the save (and, in tests, an unrelated request) down with it.

Scoping the staging name to the process removes the collision. The write stays
atomic: staging file and target are still siblings, so the rename is still a
same-filesystem rename.
"""

import contextlib
import json
import os
from pathlib import Path
from typing import Any


def staging_path(target: Path) -> Path:
    """Return the process-scoped staging path to write before renaming onto *target*.

    ``data/pages.json`` becomes ``data/pages.json.<pid>.tmp``.
    """
    return target.with_suffix(f"{target.suffix}.{os.getpid()}.tmp")


def write_json_atomic(target: Path, data: Any, *, indent: int | None = 2) -> None:
    """Serialise *data* as JSON onto *target* without ever truncating it.

    Stages the JSON in the process-scoped sibling from :func:`staging_path` and
    ``os.replace``s it into place. A crash (OOM, SIGKILL, power loss) partway
    through the write leaves the previous contents of *target* fully intact, and
    the partial staging file is removed on any failure rather than leaked.

    Parent directories are created if missing. Exceptions propagate — the caller
    decides whether a failed save is fatal.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = staging_path(target)
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=indent)
        tmp_path.replace(target)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise
