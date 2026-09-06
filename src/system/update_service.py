"""System-update service: version checks, sidecar client, snapshots, state (issue #1758).

Everything here moved verbatim out of ``src/api_server.py``: the Docker Hub /
GitHub Releases version comparison (newest-of-both-sources, #1430), the
fiestaupdater sidecar HTTP client, pre-update settings snapshots with
retention pruning, and the ``.system-update.json`` state machine with its
lock + atomic-write semantics (#1745) preserved exactly.

Patch seams: ``api_server`` re-imports every name here, so the test-suite's
``patch("src.api_server.<name>")`` targets keep working — the extracted route
handlers in ``src/system/routes.py`` resolve these helpers *through*
``src.api_server`` at call time (the #1756/#1757 pattern). The two path
overrides (``SYSTEM_UPDATE_STATE_FILE`` / ``SETTINGS_SNAPSHOT_DIR``) stay
*defined* on ``api_server`` and are read back through it at call time here,
so ``monkeypatch.setattr("src.api_server.SETTINGS_SNAPSHOT_DIR", ...)``
keeps steering the service.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from fastapi import HTTPException

from src import __version__
from src.atomic_io import write_json_atomic, write_text_atomic
from src.paths import get_data_dir

from .models import SystemActionResponse, UpdateCheckResponse

logger = logging.getLogger(__name__)


def _detect_hardware_model() -> str | None:
    """Return the host hardware model string, or None if undetectable.

    Reads ``/proc/device-tree/model``, which on Raspberry Pi devices contains a
    null-terminated string such as ``"Raspberry Pi 5 Model B Rev 1.0"``. The
    file is absent on most non-Pi hosts (generic Docker, macOS, etc.), so the
    UI suppresses the row when this returns None.
    """
    try:
        with open("/proc/device-tree/model", "rb") as f:
            raw = f.read(256)
    except (FileNotFoundError, PermissionError, OSError):
        return None
    model = raw.decode("utf-8", errors="replace").rstrip("\x00").strip()
    return model or None


GITHUB_RELEASES_URL = "https://github.com/Fiestaboard/FiestaBoard/releases"
GITHUB_PACKAGE_URL = f"{GITHUB_RELEASES_URL}/latest"
GITHUB_RELEASES_API = "https://api.github.com/repos/Fiestaboard/FiestaBoard/releases/latest"
DOCKERHUB_TAGS_URL = "https://hub.docker.com/v2/repositories/fiestaboard/fiestaboard/tags"


def _release_notes_url(version: str | None) -> str:
    """Build the release-notes URL for a specific version.

    Pinning to ``/releases/tag/v{version}`` guarantees the link goes to the
    same release we surfaced in the banner — ``/releases/latest`` redirects
    to whichever release GitHub currently has flagged Latest, which can lag
    behind the Docker Hub tag we detected (or trail a newer GitHub release
    that hasn't been flipped yet).
    """
    if not version:
        return GITHUB_PACKAGE_URL
    return f"{GITHUB_RELEASES_URL}/tag/v{version}"


def _check_dockerhub_for_latest() -> str | None:
    """Check Docker Hub for the latest version tag.

    Queries the Docker Hub API for available tags. No authentication required
    for public repositories. Filters tags to find the highest semver version.

    Returns the latest version string, or None if the check fails.
    """
    try:
        # Query Docker Hub tags endpoint
        resp = requests.get(DOCKERHUB_TAGS_URL, timeout=4)
        resp.raise_for_status()
        data = resp.json()

        # Extract tag names from results
        results = data.get("results", [])
        tags = [result.get("name") for result in results if result.get("name")]

        # Filter to semver-style tags and find the highest version
        version_tags = []
        for tag in tags:
            parts = tag.split(".")
            if len(parts) >= 2 and all(p.isdigit() for p in parts):
                version_tags.append(tuple(int(p) for p in parts))

        if not version_tags:
            return None

        best = max(version_tags)
        return ".".join(str(p) for p in best)
    except Exception as e:
        logger.debug(f"Docker Hub version check failed: {e}")
        return None


def _check_github_releases_for_latest() -> str | None:
    """Check GitHub Releases API for the latest version.

    Returns the latest version string, or None if the check fails.
    """
    try:
        resp = requests.get(
            GITHUB_RELEASES_API,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=4,
        )
        resp.raise_for_status()
        tag_name = resp.json().get("tag_name", "")
        return tag_name.lstrip("v") if tag_name else None
    except Exception as e:
        logger.debug(f"GitHub releases check failed: {e}")
        return None


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a numeric ``a.b.c`` version string into a comparable tuple.

    Raises ``ValueError`` for anything that is not purely dot-separated
    integers (e.g. a stray ``v`` prefix or an ``-rc`` suffix).
    """
    parts = v.split(".")
    if not parts or not all(p.isdigit() for p in parts):
        raise ValueError(f"Invalid version: {v}")
    return tuple(int(x) for x in parts)


def _pick_latest_version(*candidates: str | None) -> str | None:
    """Return the newest parseable version among the given candidates.

    Update availability is sourced from more than one place (Docker Hub tags
    and the GitHub Releases API). Those sources can disagree or lag — Docker
    Hub's tag-listing metadata sometimes trails a release that GitHub already
    publishes. Taking the highest version any source reports (rather than
    preferring one source and only falling back when it is empty) surfaces a
    real release as soon as either source sees it. Empty or unparseable
    candidates are ignored.
    """
    best_parsed: tuple[int, ...] | None = None
    best_str: str | None = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = _parse_version(candidate)
        except (ValueError, AttributeError):
            continue
        if best_parsed is None or parsed > best_parsed:
            best_parsed = parsed
            best_str = candidate
    return best_str


async def _perform_update_check() -> UpdateCheckResponse:
    """Run the actual update check against Docker Hub / GitHub Releases.

    Extracted from the HTTP handler so the background scheduler (auto-update
    interval) can reuse it without going through the network stack.  Records
    ``last_check`` in the system update state file on every successful query.
    Both source checks run in parallel to halve worst-case latency.
    """
    is_production = os.getenv("PRODUCTION", "false").lower() == "true"

    try:
        # Run both source checks in parallel and take the newest version either
        # reports. Trusting one source and only falling back when it is empty
        # lets a lagging source (e.g. Docker Hub tag metadata that has not yet
        # registered a freshly published release) mask a real update the other
        # source already sees.
        dh_version, gh_version = await asyncio.gather(
            asyncio.to_thread(_check_dockerhub_for_latest),
            asyncio.to_thread(_check_github_releases_for_latest),
        )
        latest_version = _pick_latest_version(dh_version, gh_version)

        if latest_version:
            update_available = _is_newer_version(latest_version, __version__)
            try:
                _system_update_state_update(last_check=datetime.now(UTC).isoformat())
            except Exception as e:
                logger.debug("Could not persist update-check result (non-fatal): %s", e, exc_info=True)
            return UpdateCheckResponse(
                current_version=__version__,
                latest_version=latest_version,
                update_available=update_available,
                package_url=_release_notes_url(latest_version),
                is_production=is_production,
            )

        raise RuntimeError("Both Docker Hub and GitHub Releases checks failed")
    except Exception as e:
        logger.warning(f"Failed to check for updates: {e}")
        return UpdateCheckResponse(
            current_version=__version__,
            latest_version=None,
            update_available=False,
            package_url=GITHUB_PACKAGE_URL,
            error=f"Could not check for updates: {e}",
            is_production=is_production,
        )


def _is_newer_version(latest: str, current: str) -> bool:
    """Compare two semver-style version strings.

    Returns True if latest is strictly newer than current.
    Handles version strings with varying component counts (e.g. "2.0" vs "2.0.1").
    """
    try:
        return _parse_version(latest) > _parse_version(current)
    except (ValueError, AttributeError):
        return False


# Path to the small JSON file that persists the auto-update toggle and
# bookkeeping (last check, last update).  Kept separate from settings.json
# because this state is system-level, not display-level.
#
# ``SYSTEM_UPDATE_STATE_FILE`` is a *test seam*: production leaves it ``None``
# and ``_system_update_state_file()`` resolves lazily through
# ``src.paths.get_data_dir()`` (honoring ``FIESTABOARD_DATA_DIR``, #1762).
# Tests that need a specific file keep monkeypatching the module attribute
# *on api_server* — the constant stays defined there and is read back
# through it at call time below.


def _system_update_state_file() -> Path:
    """Resolve the system-update state file path at call time.

    The ``SYSTEM_UPDATE_STATE_FILE`` override lives on ``src.api_server``
    (a documented test seam patched as ``src.api_server.SYSTEM_UPDATE_STATE_FILE``);
    read it through that module so the patch keeps steering us.
    """
    from src import api_server  # patched-in-tests seam — see module docstring

    if api_server.SYSTEM_UPDATE_STATE_FILE is not None:
        return Path(api_server.SYSTEM_UPDATE_STATE_FILE)
    return get_data_dir() / ".system-update.json"


# Serialises the read-modify-write of the state file.  Three writers share it —
# the hourly auto-update loop, ``POST /system/update`` and
# ``POST /system/update/auto`` — and each does load -> mutate -> save.  Without
# this lock a writer's read goes stale and the other writer's field is lost
# (#1745).  Re-entrant so a guarded update can call load/save directly.
_SYSTEM_UPDATE_STATE_LOCK = threading.RLock()


def _system_update_state_load() -> dict[str, Any]:
    """Read the system-update state file.  Returns a fresh dict on any error."""
    with _SYSTEM_UPDATE_STATE_LOCK:
        state_file = _system_update_state_file()
        try:
            if state_file.exists():
                with state_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception as e:
            logger.debug(f"Failed to read {state_file}: {e}")
        return {}


def _system_update_state_save(state: dict[str, Any]) -> None:
    """Persist the system-update state file atomically.

    A truncating ``open("w")`` here used to leave a half-written file behind on
    a crash; the loader swallows the resulting JSON error and returns ``{}``,
    which silently resets the auto-update toggle to its default (#1745).
    """
    with _SYSTEM_UPDATE_STATE_LOCK:
        state_file = _system_update_state_file()
        try:
            write_json_atomic(state_file, state)
        except Exception as e:
            logger.warning(f"Failed to write {state_file}: {e}")


def _system_update_state_update(**changes: Any) -> dict[str, Any]:
    """Merge *changes* into the state file as one locked read-modify-write."""
    with _SYSTEM_UPDATE_STATE_LOCK:
        state = _system_update_state_load()
        state.update(changes)
        _system_update_state_save(state)
        return state


def _is_update_check_due(state: dict[str, Any], period_days: int) -> bool:
    """Return True if ``last_check`` is older than ``period_days`` (or missing).

    Used by the background scheduler to decide whether to call
    ``_perform_update_check`` on a given tick.  Period of 0 always returns
    False (manual mode).
    """
    if period_days <= 0:
        return False
    raw = state.get("last_check")
    if not raw:
        return True
    try:
        last = datetime.fromisoformat(raw)
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return True
    elapsed = datetime.now(UTC) - last
    return elapsed.total_seconds() >= period_days * 86400


def _fiestaboard_profile() -> str:
    """Return the install profile: "pi" if running on the FiestaPi flashable
    image, else "docker".  Determined by a build-time env var baked in by the
    pi-gen recipe.
    """
    return os.getenv("FIESTABOARD_PROFILE", "docker").strip().lower() or "docker"


def _managed_externally() -> bool:
    """True when FiestaBoard's lifecycle is owned by an external supervisor
    that ships its own update mechanism — currently the Home Assistant add-on.

    Under HA, add-on updates come from the Supervisor's add-on store;
    FiestaBoard cannot update itself and the Supervisor already surfaces its
    own "update available" notice.  Ours would be a duplicate pointing the
    user at an action they can't take, so the UI hides every update
    notification and the periodic Docker Hub poll is skipped when this is set.

    Detection signals (any one flips it on):
      * ``FIESTABOARD_MANAGED_EXTERNALLY`` — explicit opt-in the add-on shim
        can set unambiguously (accepts true/1/yes; false/0/no forces off).
      * ``SUPERVISOR_TOKEN`` — injected by HA Supervisor into every add-on
        container.  Present whether the UI is reached through Ingress or the
        add-on's directly-published port, so it also covers direct access.
    """
    explicit = os.getenv("FIESTABOARD_MANAGED_EXTERNALLY", "").strip().lower()
    if explicit in ("true", "1", "yes"):
        return True
    if explicit in ("false", "0", "no"):
        return False
    return bool(os.getenv("SUPERVISOR_TOKEN", "").strip())


# Valid values for ``auto_update_interval``, mapped to their period in days.
# ``manual`` (0) disables the periodic check entirely; the user can still hit
# the Refresh button on Settings → System to trigger an on-demand check.
AUTO_UPDATE_INTERVALS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "manual": 0,
}


def _auto_update_default_interval() -> str:
    """Default interval when the user hasn't set one.

    Pi installs default to ``daily`` (matching the prior auto-update-on
    behavior); Docker installs default to ``weekly`` so users get nudged
    about updates without having to remember to check Settings.
    """
    return "daily" if _fiestaboard_profile() == "pi" else "weekly"


def _resolve_auto_update_interval(state: dict[str, Any]) -> str:
    """Read the configured interval from state, falling back to legacy bool.

    Order of precedence:
      1. ``auto_update_interval`` if set to a valid value
      2. legacy ``auto_update_enabled`` bool: True → default interval, False → "manual"
      3. profile-aware default
    """
    raw = state.get("auto_update_interval")
    if isinstance(raw, str) and raw in AUTO_UPDATE_INTERVALS:
        return raw
    if "auto_update_enabled" in state:
        return _auto_update_default_interval() if bool(state["auto_update_enabled"]) else "manual"
    return _auto_update_default_interval()


def _updater_url() -> str:
    """Base URL of the fiestaupdater sidecar on the compose network."""
    return os.getenv("FIESTAUPDATER_URL", "http://fiestaupdater:8765").rstrip("/")


def _updater_token() -> str:
    """Shared bearer token for the sidecar."""
    return os.getenv("FIESTAUPDATER_TOKEN", "")


def _updater_probe() -> bool:
    """Return True when the sidecar's /healthz responds 200.  Short timeout
    because this is called on every status query from the UI."""
    try:
        resp = requests.get(f"{_updater_url()}/healthz", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def _updater_last_update() -> dict[str, Any]:
    """Return the sidecar's view of the most recent /update attempt.

    The sidecar persists this in ``/var/lib/fiestaupdater/last-update.json``
    and exposes it (no auth, read-only) via ``GET /last-update``.  Returns
    an empty dict on any error so callers can ``data.get(...)`` without
    extra branching.
    """
    try:
        resp = requests.get(f"{_updater_url()}/last-update", timeout=3)
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, dict):
                return body
    except Exception as e:
        logger.debug("fiestaupdater /last-update fetch failed: %s", e)
    return {}


def _updater_version() -> dict[str, Any]:
    """Return the sidecar's view of the running container's image+digest.

    Used by /system/update to label the pre-update snapshot with the exact
    image we're rolling back *from*, so a later /system/update/rollback
    can pair the restored settings with the matching image.  Returns an
    empty dict on any failure — the snapshot is still useful without it,
    just less informative for the UI.
    """
    try:
        resp = requests.get(f"{_updater_url()}/version", timeout=3)
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, dict):
                return body
    except Exception as e:
        logger.debug("fiestaupdater /version fetch failed: %s", e)
    return {}


def _updater_post(path: str) -> requests.Response:
    """POST to the fiestaupdater sidecar and return the response.
    Raises on network-level failures; callers handle HTTP errors.
    """
    url = f"{_updater_url()}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {_updater_token()}"}
    return requests.post(url, headers=headers, timeout=(5, 30))


def _require_updater_token():
    """Raise 503 if FIESTAUPDATER_TOKEN is not configured."""
    if not _updater_token():
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "hint": "FIESTAUPDATER_TOKEN is not set. Add COMPOSE_PROFILES=fiestaupdater to your .env and run 'docker compose up -d' to enable sidecar features.",
            },
        )


def _handle_updater_response(resp: requests.Response, action: str) -> SystemActionResponse:
    """Translate a sidecar HTTP response into a SystemActionResponse or raise."""
    if resp.status_code == 401:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "error": "fiestaupdater rejected our token; check FIESTAUPDATER_TOKEN matches in both services",
            },
        )
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "error": f"fiestaupdater returned {resp.status_code}: {resp.text[:200]}"},
        )
    return SystemActionResponse(status="queued", action=action)


# ── Settings snapshots (used by the rollback flow) ──────────────────────────

# Where pre-update settings snapshots live.  Each snapshot is a single JSON
# document (the same format the BackupService uses for hand-rolled backups)
# named ``pre-update-<timestamp>.json``.  Kept under data/ so they survive
# container recreates via the ``./data:/app/data`` bind mount.
#
# ``SETTINGS_SNAPSHOT_DIR`` is a *test seam*: production leaves it ``None``
# and ``_settings_snapshot_dir()`` resolves lazily through
# ``src.paths.get_data_dir()`` (honoring ``FIESTABOARD_DATA_DIR``, #1762).
# The constant stays defined on api_server and is read back through it at
# call time below, so ``patch("src.api_server.SETTINGS_SNAPSHOT_DIR")``
# keeps steering the service.


def _settings_snapshot_dir() -> Path:
    """Resolve the settings-snapshot directory at call time."""
    from src import api_server  # patched-in-tests seam — see module docstring

    if api_server.SETTINGS_SNAPSHOT_DIR is not None:
        return Path(api_server.SETTINGS_SNAPSHOT_DIR)
    return get_data_dir() / "update-backups"


# How many pre-update snapshots to retain.  Older ones are pruned after each
# successful snapshot.  Five mirrors the user's ".json.bak" rotation request.
SETTINGS_SNAPSHOT_RETENTION = 5

#: Strict allow-list for snapshot filenames coming in from the API.  We only
#: accept the exact ``pre-update-YYYYMMDDTHHMMSS[.fff]Z.json`` shape we
#: produce (sub-second component optional for back-compat), so the restore
#: endpoint cannot be coaxed into reading arbitrary files.
_SETTINGS_SNAPSHOT_NAME_RE = re.compile(r"^pre-update-\d{8}T\d{6}(?:\.\d{3})?Z\.json$")


def _take_settings_snapshot(
    previous_digest: str | None = None,
    previous_image: str | None = None,
) -> dict[str, Any] | None:
    """Snapshot ``data/*.json`` to ``data/update-backups/pre-update-<ts>.json``.

    Uses :class:`~src.backup.service.BackupService` so the snapshot is the
    same self-contained document the user could hand-restore later.  Returns
    a small metadata dict (``{"name", "path", "created_at", "bytes",
    "previous_digest", "previous_image"}``) or ``None`` if a backup could
    not be produced — the update is allowed to proceed even when
    snapshotting fails, since the user can still roll the image back via
    the sidecar's /rollback alone.

    Args:
        previous_digest: image digest of the running container at the
            moment the snapshot is taken.  Stored inside the snapshot
            JSON so a future /system/update/rollback knows which image
            to revert to alongside the settings.
        previous_image: image reference (``repo:tag``) of the running
            container at the moment the snapshot is taken.
    """
    try:
        from src.backup.service import get_backup_service

        service = get_backup_service()
        document = service.export_to_json()
    except Exception:
        logger.exception("Failed to build pre-update settings snapshot")
        return None

    # Embed the pre-update image identity so a later rollback can pair the
    # restored settings with the matching image without us having to keep
    # a separate index file in sync.  We splice it into the existing JSON
    # document under a ``_fiestaupdater`` key so we don't collide with any
    # existing field that BackupService might add.
    if previous_digest or previous_image:
        try:
            doc = json.loads(document)
            if isinstance(doc, dict):
                # Store ``None`` (not "") for missing values so the
                # round-trip through ``_read_snapshot_metadata`` is
                # symmetric — that helper normalises empty strings to
                # ``None`` when reading, so we may as well write ``None``
                # in the first place.
                doc["_fiestaupdater"] = {
                    "previous_digest": previous_digest or None,
                    "previous_image": previous_image or None,
                }
                document = json.dumps(doc, indent=2)
        except (ValueError, TypeError):
            logger.warning(
                "Could not annotate snapshot with previous image metadata; "
                "rollback will fall back to the sidecar's last-update record."
            )

    try:
        snapshot_dir = _settings_snapshot_dir()
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        # Millisecond precision so multiple snapshots within the same
        # second (e.g. tests, or a user retrying immediately) don't
        # collide on filename and silently overwrite each other.
        now = datetime.now(UTC)
        ts = now.strftime("%Y%m%dT%H%M%S") + f".{now.microsecond // 1000:03d}Z"
        target = snapshot_dir / f"pre-update-{ts}.json"
        # Belt-and-braces against same-millisecond collisions: bump the
        # millisecond field forward until we find a free name.  1000 is
        # the natural upper bound (one full second of ms slots); we treat
        # exhaustion as a fatal-but-non-fatal "snapshot unavailable".
        _MAX_MS_SLOTS = 1000
        for bump in range(1, _MAX_MS_SLOTS + 1):
            if not target.exists():
                break
            ms = (now.microsecond // 1000 + bump) % _MAX_MS_SLOTS
            ts = now.strftime("%Y%m%dT%H%M%S") + f".{ms:03d}Z"
            target = snapshot_dir / f"pre-update-{ts}.json"
        else:  # pragma: no cover - effectively unreachable
            logger.warning("Could not find a free snapshot filename")
            return None
        # Atomic staged write (process-scoped staging name) so a crash
        # mid-write can't leave a truncated snapshot, and a concurrent
        # process can't collide on a fixed .tmp name.
        write_text_atomic(target, document)
    except OSError:
        logger.exception("Failed to write pre-update settings snapshot")
        return None

    _prune_settings_snapshots()
    try:
        size = target.stat().st_size
    except OSError:
        size = 0
    return {
        "name": target.name,
        "path": str(target),
        # Use the same wall-clock value that's encoded in the filename so
        # the metadata returned to callers matches the on-disk artifact.
        "created_at": now.isoformat(),
        "bytes": size,
        "previous_digest": previous_digest or None,
        "previous_image": previous_image or None,
    }


def _read_snapshot_metadata(path: Path) -> dict[str, str | None]:
    """Return ``{previous_digest, previous_image}`` recorded inside a snapshot.

    Snapshots produced before this metadata was added (or that failed to
    annotate cleanly) return ``{"previous_digest": None, "previous_image": None}``.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, ValueError, TypeError):
        return {"previous_digest": None, "previous_image": None}
    meta = doc.get("_fiestaupdater") if isinstance(doc, dict) else None
    if not isinstance(meta, dict):
        return {"previous_digest": None, "previous_image": None}
    return {
        "previous_digest": meta.get("previous_digest") or None,
        "previous_image": meta.get("previous_image") or None,
    }


def _list_settings_snapshots() -> list[dict[str, Any]]:
    """Return metadata for every snapshot currently on disk, newest first.

    Each entry includes the recorded ``previous_digest`` / ``previous_image``
    so the UI can label snapshots with the version they will roll back to.
    """
    snapshot_dir = _settings_snapshot_dir()
    if not snapshot_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        entries = sorted(snapshot_dir.iterdir(), reverse=True)
    except OSError:
        return []
    for entry in entries:
        if not entry.is_file():
            continue
        if not _SETTINGS_SNAPSHOT_NAME_RE.fullmatch(entry.name):
            continue
        try:
            stat = entry.stat()
        except OSError:
            continue
        meta = _read_snapshot_metadata(entry)
        out.append(
            {
                "name": entry.name,
                "bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                "previous_digest": meta["previous_digest"],
                "previous_image": meta["previous_image"],
            }
        )
    return out


def _prune_settings_snapshots() -> None:
    """Delete all but the ``SETTINGS_SNAPSHOT_RETENTION`` newest snapshots."""
    snapshots = _list_settings_snapshots()
    if len(snapshots) <= SETTINGS_SNAPSHOT_RETENTION:
        return
    for stale in snapshots[SETTINGS_SNAPSHOT_RETENTION:]:
        path = _settings_snapshot_dir() / stale["name"]
        try:
            path.unlink()
        except OSError:
            logger.warning("Could not prune old settings snapshot %s", path)


def _resolve_snapshot_name(name: str | None) -> Path | None:
    """Return the absolute path of the named snapshot, or the newest one
    if *name* is None.  Returns ``None`` when no valid snapshot exists.

    The resolved path is constrained to ``SETTINGS_SNAPSHOT_DIR`` and the
    filename must match :data:`_SETTINGS_SNAPSHOT_NAME_RE`, so a caller
    cannot pass ``../../etc/passwd`` or any other path outside the
    snapshot directory.
    """
    if name is None:
        snaps = _list_settings_snapshots()
        if not snaps:
            return None
        name = snaps[0]["name"]
    if not _SETTINGS_SNAPSHOT_NAME_RE.fullmatch(name):
        return None
    snapshot_dir = _settings_snapshot_dir()
    candidate = (snapshot_dir / name).resolve()
    base = snapshot_dir.resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


# ── Strict shape constraints for /rollback's image+digest fields ────────────
# These mirror the patterns enforced inside the sidecar's handler.sh and
# act as a defense-in-depth check on the API side: if a digest looks
# valid but the image reference doesn't (or vice versa), we refuse to
# call the sidecar at all.
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_IMAGE_REF_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,199}(:[a-zA-Z0-9._-]{1,128})?$")


async def run_system_update_check_if_due() -> None:
    """One tick of the scheduled system-update check.

    Body of the hourly loop in api_server's lifespan (the loop shell stays
    there): read the user-configured interval from the state file and, when
    it has elapsed since ``last_check``, refresh via
    :func:`_perform_update_check` so the in-app banner can show
    "Update Available" without the user opening Settings.
    """
    state = _system_update_state_load()
    interval_name = _resolve_auto_update_interval(state)
    period_days = AUTO_UPDATE_INTERVALS.get(interval_name, 0)
    if period_days > 0 and _is_update_check_due(state, period_days):
        logger.info(
            "Auto-update check (interval=%s): checking for new version",
            interval_name,
        )
        await _perform_update_check()
