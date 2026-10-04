"""The output seed: first-party output plugins baked into the image (plan D8).

A board must never go dark because its output plugin is missing or broken,
and installing one must not need the network (a Pi, the HA add-on, an
offline LAN). So the image carries a read-only **seed**: the first-party
output plugins at the commits pinned in the core lockfile,
``outputs.lock.json`` at the repo root::

    {
      "lock_version": 1,
      "outputs": {
        "<plugin_id>": {
          "repository": "https://github.com/Fiestaboard/fiestaboard-output--<name>",
          "commit": "<40-hex commit sha>",
          "output_api": 1,
          "tree_sha256": "<tree_digest() of the checkout>",
          "loadable": true
        }
      }
    }

- ``commit`` pins the tree; ``tree_sha256`` (:func:`tree_digest`) proves the
  bytes, so a moved tag, a force-push or a corrupted copy is refused.
- ``output_api`` is the contract major the pinned commit targets; a loadable
  entry's manifest must declare the same (checked at build).
- ``loadable: false`` marks a repo the image carries for its **data** only
  (device data, nothing to import): never loaded, never auto-installed.

**Build** (``scripts/seed_outputs.py``, run by the Dockerfile — never at
runtime): :func:`build_seed` fetches each pinned commit into
``<seed>/<plugin_id>/`` (a shallow git checkout, so a copy of it is an
ordinary installed plugin that can update), verifies commit, digest and
manifest, and writes the lock beside them (``<seed>/outputs.lock.json``):
what the seed holds is exactly what that copy says.

**Runtime** reads the seed only:

- :func:`install_seeded_outputs_for_boards` — at boot, a board whose
  ``output`` names a seeded plugin that is not installed gets it copied from
  the seed into the external plugins directory (offline);
- :func:`seeded_output` — the loader's last resort when the installed copy
  of a seeded output plugin cannot run (``src.plugins.loader``).

The seed is never placed in ``plugins/``: built-in plugins always win over
installed ones, so a seeded plugin there could never be updated.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Where the image puts the seed (root-owned, read-only to the app user).
DEFAULT_SEED_DIR = "/opt/fiestaboard/seed/outputs"
#: Overrides :data:`DEFAULT_SEED_DIR` (tests; a non-image install).
SEED_DIR_ENV = "FIESTABOARD_OUTPUT_SEED_DIR"
#: The lockfile's name, at the repo root and inside the seed.
LOCKFILE = "outputs.lock.json"
LOCK_VERSION = 1

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ENTRY_KEYS = frozenset({"repository", "commit", "output_api", "tree_sha256", "loadable"})
#: Never part of a plugin's tree: git's own data and Python's bytecode cache.
_IGNORED_DIRS = frozenset({".git", "__pycache__"})
_TMP_SUFFIX = ".fbseed-tmp"


class LockError(ValueError):
    """The lockfile, or a tree fetched for it, is not what it must be."""


@dataclass(frozen=True)
class LockEntry:
    """One pinned first-party output plugin."""

    plugin_id: str
    repository: str
    commit: str
    output_api: int
    tree_sha256: str
    loadable: bool = True


@dataclass(frozen=True)
class SeedCopy:
    """A seeded plugin present in the seed directory."""

    entry: LockEntry
    path: Path


# --- the lockfile ------------------------------------------------------------------


def parse_lock(data: Any) -> dict[str, LockEntry]:
    """Validate a parsed lockfile; the entries by plugin id.

    Raises:
        LockError: naming every problem found.
    """
    if not isinstance(data, Mapping):
        raise LockError("outputs.lock.json must be a JSON object")
    errors: list[str] = []
    if data.get("lock_version") != LOCK_VERSION:
        errors.append(f"lock_version must be {LOCK_VERSION}, got {data.get('lock_version')!r}")
    outputs = data.get("outputs")
    if not isinstance(outputs, Mapping):
        raise LockError("; ".join([*errors, "'outputs' must be an object keyed by plugin id"]))

    entries: dict[str, LockEntry] = {}
    for plugin_id, raw in outputs.items():
        where = f"outputs.{plugin_id}"
        if not isinstance(plugin_id, str) or not _ID_RE.fullmatch(plugin_id):
            errors.append(f"{where}: not a plugin id (lowercase letters, digits, underscores)")
            continue
        if not isinstance(raw, Mapping):
            errors.append(f"{where}: must be an object")
            continue
        unknown = sorted(set(raw) - _ENTRY_KEYS)
        if unknown:
            errors.append(f"{where}: unknown keys {unknown}")
        repository, commit = raw.get("repository"), raw.get("commit")
        output_api, digest = raw.get("output_api"), raw.get("tree_sha256")
        loadable = raw.get("loadable", True)
        if not isinstance(repository, str) or not repository.startswith("https://"):
            errors.append(f"{where}.repository: must be an https:// URL")
        if not isinstance(commit, str) or not _SHA_RE.fullmatch(commit):
            errors.append(f"{where}.commit: must be a full 40-character commit sha")
        if not isinstance(output_api, int) or isinstance(output_api, bool) or output_api < 1:
            errors.append(f"{where}.output_api: must be a positive integer")
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            errors.append(f"{where}.tree_sha256: must be 64 lowercase hex characters")
        if not isinstance(loadable, bool):
            errors.append(f"{where}.loadable: must be true or false")
        if not any(e.startswith(where) for e in errors):
            entries[plugin_id] = LockEntry(plugin_id, repository, commit, output_api, digest, loadable)
    if errors:
        raise LockError("; ".join(errors))
    return entries


def load_lock(path: Path) -> dict[str, LockEntry]:
    """Read and validate a lockfile.

    Raises:
        LockError: missing, unreadable or invalid.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LockError(f"{path}: {exc}") from exc
    return parse_lock(data)


# --- the tree digest -----------------------------------------------------------------


def tree_digest(root: Path) -> str:
    """A deterministic sha256 of a plugin tree's content.

    Every regular file under *root* (``.git`` and ``__pycache__`` excluded),
    sorted by its POSIX relative path, contributes
    ``<path>\\0<x|->\\0<sha256 of bytes>\\n`` — the executable bit is part of
    the tree, timestamps and ownership are not. A symlink is refused: a
    seeded tree must be self-contained.

    Raises:
        LockError: *root* is not a directory, or holds a symlink.
    """
    root = Path(root)
    if not root.is_dir():
        raise LockError(f"{root}: not a directory")
    lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        for name in list(dirnames):
            if name in _IGNORED_DIRS:
                dirnames.remove(name)
            elif (here / name).is_symlink():
                raise LockError(f"{(here / name).relative_to(root).as_posix()}: symlinks are not allowed")
        for name in filenames:
            path = here / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise LockError(f"{rel}: symlinks are not allowed")
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode):
                continue
            executable = "x" if mode & 0o111 else "-"
            lines.append(f"{rel}\0{executable}\0{hashlib.sha256(path.read_bytes()).hexdigest()}\n")
    lines.sort()
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


# --- build time: fetch the pinned trees ---------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    return result.stdout.strip()


def _check_seed_manifest(entry: LockEntry, tree: Path) -> None:
    """A loadable entry must be an output plugin of that id and output_api."""
    try:
        manifest = json.loads((tree / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LockError(f"{entry.plugin_id}: loadable, but manifest.json is unreadable ({exc})") from exc
    if not isinstance(manifest, dict):
        raise LockError(f"{entry.plugin_id}: manifest.json is not an object")
    if manifest.get("id") != entry.plugin_id:
        raise LockError(f"{entry.plugin_id}: manifest id is {manifest.get('id')!r}")
    if manifest.get("plugin_type") != "output":
        raise LockError(f"{entry.plugin_id}: manifest plugin_type is {manifest.get('plugin_type')!r}, not 'output'")
    block = manifest.get("output") if isinstance(manifest.get("output"), dict) else {}
    if block.get("output_api") != entry.output_api:
        raise LockError(
            f"{entry.plugin_id}: manifest output_api is {block.get('output_api')!r}, the lock pins {entry.output_api}"
        )


def fetch_entry(entry: LockEntry, dest_root: Path, *, repository: str | None = None) -> Path:
    """Fetch *entry*'s pinned commit into ``dest_root/<plugin_id>`` and verify it.

    The result is a shallow git checkout (origin = the entry's repository),
    so a copy installed from it updates like any installed plugin.
    *repository* overrides where the commit is fetched from (tests fetch
    from a local fixture repo; the build never passes it).

    Raises:
        LockError: the commit is missing, its tree does not match
            ``tree_sha256``, or a loadable entry's manifest disagrees. Nothing
            is left at the destination.
    """
    dest = Path(dest_root) / entry.plugin_id
    if dest.exists():
        raise LockError(f"{dest}: already exists")
    dest.mkdir(parents=True)
    try:
        _git(dest, "init", "--quiet")
        with (dest / ".git" / "config").open("a", encoding="utf-8") as cfg:
            cfg.write(f'[remote "origin"]\n\turl = {entry.repository}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n')
        source = repository or entry.repository
        try:
            _git(dest, "fetch", "--quiet", "--depth=1", source, entry.commit)
            _git(dest, "reset", "--quiet", "--hard", "FETCH_HEAD")
        except subprocess.CalledProcessError as exc:
            raise LockError(f"{entry.plugin_id}: cannot fetch {entry.commit} ({(exc.stderr or '').strip()})") from exc
        head = _git(dest, "rev-parse", "HEAD")
        if head != entry.commit:
            raise LockError(f"{entry.plugin_id}: fetched {head}, the lock pins {entry.commit}")
        digest = tree_digest(dest)
        if digest != entry.tree_sha256:
            raise LockError(f"{entry.plugin_id}: tree digest is {digest}, the lock pins {entry.tree_sha256}")
        if entry.loadable:
            _check_seed_manifest(entry, dest)
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


def build_seed(
    lock_path: Path, dest_root: Path, *, repositories: Mapping[str, str] | None = None
) -> dict[str, LockEntry]:
    """Fetch every pinned tree of *lock_path* into *dest_root* and copy the
    lock beside them. Build time only (``scripts/seed_outputs.py``).

    Raises:
        LockError: any entry fails; the seed is then incomplete and the
            build must stop.
    """
    entries = load_lock(lock_path)
    dest_root = Path(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    for entry in entries.values():
        fetch_entry(entry, dest_root, repository=(repositories or {}).get(entry.plugin_id))
        logger.info("Seeded output %s at %s", entry.plugin_id, entry.commit)
    shutil.copyfile(lock_path, dest_root / LOCKFILE)
    return entries


# --- runtime: read the seed ----------------------------------------------------------------


def seed_root() -> Path:
    """The seed directory: ``$FIESTABOARD_OUTPUT_SEED_DIR`` or the image default."""
    return Path(os.environ.get(SEED_DIR_ENV, "").strip() or DEFAULT_SEED_DIR)


def seeded_entries(root: Path | None = None) -> dict[str, LockEntry]:
    """The entries the seed was built from. Empty when there is no seed
    (a dev checkout) or its lock cannot be read (logged)."""
    lock = (root if root is not None else seed_root()) / LOCKFILE
    if not lock.is_file():
        return {}
    try:
        return load_lock(lock)
    except LockError as exc:
        logger.error("The output seed's lock is unusable, so the seed is ignored: %s", exc)
        return {}


def seeded_output(plugin_id: str, root: Path | None = None) -> SeedCopy | None:
    """The seed's loadable copy of *plugin_id*, or ``None``."""
    root = root if root is not None else seed_root()
    entry = seeded_entries(root).get(plugin_id)
    if entry is None or not entry.loadable:
        return None
    path = root / plugin_id
    return SeedCopy(entry, path) if (path / "manifest.json").is_file() else None


def install_from_seed(plugin_id: str, external_dir: Path, root: Path | None = None) -> tuple[bool, str]:
    """Copy the seed's *plugin_id* into ``external_dir/<plugin_id>``.

    The copy lands in a hidden temp directory, is verified against the lock's
    digest there, then renamed into place — the target holds the whole
    verified plugin or nothing. An existing target is never touched.
    """
    copy = seeded_output(plugin_id, root)
    if copy is None:
        return False, f"'{plugin_id}' is not a loadable seeded output"
    target = Path(external_dir) / plugin_id
    if target.exists():
        return False, f"{target} already exists"
    tmp = Path(external_dir) / f".{plugin_id}{_TMP_SUFFIX}"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        shutil.copytree(copy.path, tmp, symlinks=True)
        digest = tree_digest(tmp)
        if digest != copy.entry.tree_sha256:
            raise LockError(f"seed copy digest {digest} does not match the lock ({copy.entry.tree_sha256})")
        # The image's seed is read-only; the installed copy must be writable
        # (updates reset its checkout).
        for path in [tmp, *tmp.rglob("*")]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | stat.S_IWUSR)
        tmp.rename(target)
    except (OSError, LockError) as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        return False, f"Could not install '{plugin_id}' from the seed: {exc}"
    logger.info("Installed output plugin %s from the seed (commit %s)", plugin_id, copy.entry.commit)
    return True, ""


def install_seeded_outputs_for_boards(
    boards: Iterable[Mapping[str, Any]],
    *,
    plugin_dirs: Iterable[Path],
    external_dir: Path,
    root: Path | None = None,
) -> list[str]:
    """At boot: install from the seed every output plugin a board names
    explicitly that is in the seed and not installed anywhere in
    *plugin_dirs*. Offline by construction. Returns the ids installed.

    Boards that name no ``output`` (legacy Vestaboard and FiestaPanel
    boards) keep their first-party outputs, staged in-repo.
    """
    root = root if root is not None else seed_root()
    wanted = sorted(
        {b.get("output") for b in boards if isinstance(b, Mapping) and isinstance(b.get("output"), str)} - {""}
    )
    if not wanted:
        return []
    searched = [Path(d) for d in plugin_dirs]
    installed: list[str] = []
    for plugin_id in wanted:
        if seeded_output(plugin_id, root) is None:
            continue
        if any((d / plugin_id / "manifest.json").is_file() for d in searched):
            continue
        ok, err = install_from_seed(plugin_id, external_dir, root)
        if ok:
            installed.append(plugin_id)
        else:
            logger.error("A board names output '%s' but it could not be installed from the seed: %s", plugin_id, err)
    return installed
