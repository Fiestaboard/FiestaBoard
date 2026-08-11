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

import os
from pathlib import Path


def staging_path(target: Path) -> Path:
    """Return the process-scoped staging path to write before renaming onto *target*.

    ``data/pages.json`` becomes ``data/pages.json.<pid>.tmp``.
    """
    return target.with_suffix(f"{target.suffix}.{os.getpid()}.tmp")
