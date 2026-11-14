"""Drafts and saved versions of pages (H9a), in files beside ``pages.json``.

Two sidecar stores, one small file per page each, named by a digest of the
page id (an id is caller-visible text; a file name never is):

* ``<data>/page_drafts/<digest>.json`` — at most one **draft** per page: the
  content an editor saved with "Save draft". No board, schedule, collection
  or ``/v1`` read ever sees it; the display runtime only reads ``pages.json``.
* ``<data>/page_revisions/<digest>.json`` — the page's **saved versions**,
  oldest first on disk, newest first on the wire.

Why sidecars and not fields on the page: ``pages.json`` is schema-versioned,
and a build older than the file's version refuses it outright (there is no
downgrade bridge for pages), so a schema bump would make a one-release
rollback show no pages at all. New files are invisible to older builds. Each
sidecar carries its own ``schema_version`` (1) through :class:`JsonStore`.

Not to be confused with ``Page.revision``: that is the in-memory edit
generation ``expected_revision`` checks. A saved version's id is ``rv_…``.

Bounds (per page): :data:`MAX_REVISIONS` versions, none older than
:data:`MAX_REVISION_AGE_SECONDS` (the newest is always kept), the file at most
:data:`MAX_REVISION_FILE_BYTES`; saves from the same origin and client within
:data:`COALESCE_SECONDS` replace the newest version instead of adding one. A
draft is at most :data:`MAX_DRAFT_BYTES`.

Write cost: one atomic, unchanged-bytes-skipping write of one page's file per
explicit save — never per keystroke, render or read.

Reads validate (as ``sends._clean`` does), because these files are written by
whatever build ran last: a version with an origin this build does not know, a
non-finite or out-of-range instant, no id or no content is skipped; an unknown
``via`` or a malformed ``restored_from`` reads as null; a draft with no
revision, a bad instant or no content reads as no draft. Each is logged. A
skipped version is not written back on the next save. A read never fails on
one bad entry, and one bad draft never hides another page's.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, get_args

from src.storage.json_store import JsonStore

from .document import PAGE_SERVER_FIELDS

logger = logging.getLogger(__name__)

MAX_REVISIONS = 20
MAX_REVISION_AGE_SECONDS = 90 * 86_400
MAX_REVISION_FILE_BYTES = 2 * 1024 * 1024
COALESCE_SECONDS = 60.0
MAX_DRAFT_BYTES = 256 * 1024
SCHEMA_VERSION = 1

#: How a version came to be.
Origin = Literal[
    "created", "edited", "published", "restored", "resized", "assistant", "duplicated", "imported", "baseline"
]
#: Who asked: a browser session, a phone (``control``), the API token, the MCP client, or the hub itself.
Via = Literal["web", "phone", "api", "mcp", "hub"]

_ORIGINS: frozenset[str] = frozenset(get_args(Origin))
_VIAS: frozenset[str] = frozenset(get_args(Via))
#: 9999-12-31T23:59:59Z, the last instant ``datetime`` can show.
_LATEST_EPOCH = 253_402_300_799.0

#: Saves from these origins within COALESCE_SECONDS of the newest version replace it.
_COALESCING: frozenset[str] = frozenset({"edited", "assistant"})

#: Not content: identity and timestamps, the internal demo marker, and tags
#: (organisation, not content — a tag change records no version).
CONTENT_EXCLUDED = PAGE_SERVER_FIELDS | {"demo_plugin_id", "tags"}


def page_content(page: Any) -> dict:
    """A page's versionable content as JSON: what a draft holds and a version records."""
    return page.model_dump(mode="json", exclude=CONTENT_EXCLUDED)


def iso(epoch: float | None) -> str | None:
    """UTC with whole seconds, as H12/H13 serialise instants."""
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, UTC).replace(microsecond=0).isoformat()


def _digest(page_id: str) -> str:
    return hashlib.sha256(page_id.encode("utf-8")).hexdigest()[:32]


class PageHistory:
    """Both sidecar stores for one data directory. Callers hold the page storage lock."""

    def __init__(self, data_dir: Path, clock: Callable[[], float] = time.time) -> None:
        self.drafts_dir = Path(data_dir) / "page_drafts"
        self.revisions_dir = Path(data_dir) / "page_revisions"
        self.clock = clock
        self._lock = threading.RLock()
        self._stores: dict[Path, JsonStore] = {}

    # ── files ──────────────────────────────────────────────────────────

    def _store(self, path: Path) -> JsonStore:
        with self._lock:
            store = self._stores.get(path)
            if store is None:
                store = JsonStore(path, current_schema_version=SCHEMA_VERSION, label=f"Page history {path.name}")
                self._stores[path] = store
            return store

    def _read(self, path: Path) -> dict | None:
        try:
            data = self._store(path).load()
        except Exception:
            # Unreadable or written by a newer build: treat as absent for
            # reads; the store's latch refuses to overwrite a newer file.
            logger.warning("Could not read %s", path, exc_info=True)
            return None
        return data if isinstance(data, dict) else None

    def _remove(self, path: Path) -> bool:
        with self._lock:
            self._stores.pop(path, None)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True

    # ── drafts ─────────────────────────────────────────────────────────

    def _draft_path(self, page_id: str) -> Path:
        return self.drafts_dir / f"{_digest(page_id)}.json"

    def get_draft(self, page_id: str) -> dict | None:
        path = self._draft_path(page_id)
        data = self._read(path)
        if not data or data.get("page_id") != page_id:
            return None
        return _clean_draft(data, path)

    def put_draft(self, page_id: str, record: dict) -> None:
        self._store(self._draft_path(page_id)).save({**record, "page_id": page_id})

    def delete_draft(self, page_id: str) -> bool:
        return self._remove(self._draft_path(page_id))

    def list_drafts(self) -> list[dict]:
        if not self.drafts_dir.is_dir():
            return []
        drafts = []
        for path in sorted(self.drafts_dir.glob("*.json")):
            data = self._read(path)
            if data and isinstance(data.get("page_id"), str):
                draft = _clean_draft(data, path)
                if draft is not None:
                    drafts.append(draft)
        return drafts

    # ── revisions ──────────────────────────────────────────────────────

    def _revisions_path(self, page_id: str) -> Path:
        return self.revisions_dir / f"{_digest(page_id)}.json"

    def revisions(self, page_id: str) -> list[dict]:
        """The page's versions, oldest first (as stored)."""
        path = self._revisions_path(page_id)
        data = self._read(path)
        if not data or data.get("page_id") != page_id or not isinstance(data.get("revisions"), list):
            return []
        cleaned = [_clean_revision(r) for r in data["revisions"]]
        skipped = cleaned.count(None)
        if skipped:
            logger.warning("Skipped %d saved version(s) this build cannot read in %s", skipped, path.name)
        return [r for r in cleaned if r is not None]

    def revision(self, page_id: str, revision_id: str) -> dict | None:
        return next((r for r in self.revisions(page_id) if r["id"] == revision_id), None)

    def _write_revisions(self, page_id: str, revisions: list[dict]) -> None:
        self._store(self._revisions_path(page_id)).save({"page_id": page_id, "revisions": revisions})

    def record(
        self,
        page_id: str,
        content: dict,
        *,
        origin: str,
        via: str | None,
        restored_from: str | None = None,
        baseline: tuple[dict, float] | None = None,
    ) -> dict | None:
        """Append *content* as the newest version (or nothing, when it is the newest already).

        *baseline* is ``(content, saved_at)`` of the page before this save. It
        is recorded first when the page has no history yet: a page saved by a
        build without H9 keeps its pre-upgrade content restorable.
        """
        with self._lock:
            now = self.clock()
            revisions = self.revisions(page_id)
            if not revisions and baseline is not None and baseline[0] != content:
                # Saved at the page's old updated_at, but aged from now: a page
                # untouched for 90+ days must keep its pre-upgrade content.
                revisions.append(
                    {**_new_revision(baseline[0], "baseline", None, None, baseline[1]), "recorded_at": now}
                )
            newest = revisions[-1] if revisions else None
            if newest is not None and newest["content"] == content:
                return None
            entry = _new_revision(content, origin, via, restored_from, now)
            if (
                newest is not None
                and origin in _COALESCING
                and newest["origin"] == origin
                and newest.get("via") == via
                and 0 <= now - newest["saved_at"] < COALESCE_SECONDS
            ):
                revisions[-1] = entry
            else:
                revisions.append(entry)
            self._write_revisions(page_id, _bounded(revisions, now))
            return entry

    def forget(self, page_id: str) -> None:
        """A deleted page's draft and versions go with it."""
        self._remove(self._draft_path(page_id))
        self._remove(self._revisions_path(page_id))


def _new_revision(content: dict, origin: str, via: str | None, restored_from: str | None, saved_at: float) -> dict:
    return {
        "id": f"rv_{uuid.uuid4().hex[:16]}",
        "saved_at": saved_at,
        "origin": origin,
        "via": via,
        "restored_from": restored_from,
        "content": content,
    }


def _instant(value: Any) -> float | None:
    """*value* as an epoch ``datetime`` can show, or None."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if not math.isfinite(value) or not 0 <= value <= _LATEST_EPOCH:
        return None
    return float(value)


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _clean_revision(entry: Any) -> dict | None:
    """A stored version as this build reads it, or None when it cannot read it."""
    if not isinstance(entry, dict):
        return None
    saved_at = _instant(entry.get("saved_at"))
    if (
        saved_at is None
        or not isinstance(entry.get("id"), str)
        or entry.get("origin") not in _ORIGINS
        or not isinstance(entry.get("content"), dict)
    ):
        return None
    via = entry.get("via")
    cleaned = {
        "id": entry["id"],
        "saved_at": saved_at,
        "origin": entry["origin"],
        "via": via if via in _VIAS else None,  # a newer build's client reads as unknown
        "restored_from": _str_or_none(entry.get("restored_from")),
        "content": entry["content"],
    }
    recorded_at = _instant(entry.get("recorded_at"))
    if recorded_at is not None:
        cleaned["recorded_at"] = recorded_at
    return cleaned


def _clean_draft(data: dict, path: Path) -> dict | None:
    """A stored draft as this build reads it, or None (logged) when it cannot read it."""
    saved_at = _instant(data.get("saved_at"))
    revision = data.get("revision")
    if saved_at is None or not isinstance(revision, str) or not revision or not isinstance(data.get("content"), dict):
        logger.warning("Skipped a draft this build cannot read: %s", path.name)
        return None
    via = data.get("via")
    return {
        **data,
        "saved_at": saved_at,
        "based_on": _str_or_none(data.get("based_on")),
        "restored_from": _str_or_none(data.get("restored_from")),
        "via": via if via in _VIAS else None,
    }


def _bounded(revisions: list[dict], now: float) -> list[dict]:
    """Count, age and size caps, oldest dropped first; the newest always stays.

    A version ages from when it was recorded: ``saved_at`` for every version
    but a baseline, whose ``saved_at`` is the page's old ``updated_at``.
    """
    newest = revisions[-1]
    kept = [r for r in revisions[:-1] if now - r.get("recorded_at", r["saved_at"]) <= MAX_REVISION_AGE_SECONDS]
    kept = [*kept, newest][-MAX_REVISIONS:]
    while len(kept) > 1 and len(json.dumps(kept)) > MAX_REVISION_FILE_BYTES:
        kept.pop(0)
    return kept
