"""Draft, publish, saved versions and restore for pages (H9a).

The operations :class:`~src.pages.service.PageService` gains, kept here so the
CRUD/render service does not grow by a third. Every operation runs under the
page storage lock, so a publish, a discard and a restore never interleave
with a save. Errors are domain errors; ``src/pages/routes.py`` maps them to
status codes.

Semantics (design: program ``status/hub-H9.md``):

* A **draft** is a full content snapshot; ``PUT`` applies a sparse
  ``PageUpdate`` over it (or over the published page when there is none).
* **Publish** applies the draft through the ordinary ``update_page`` (so the
  edit generation, preview cache and retarget checks behave exactly as a
  save) and then deletes the draft.
* **Restore** writes a saved version into the draft — never the live page.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from src.storage.json_store import SchemaTooNewError

from .history import MAX_DRAFT_BYTES, PageHistory, iso, page_content
from .models import Page, PageUpdate

logger = logging.getLogger(__name__)

#: ``Page`` fields a draft may carry to ``update_page`` (PageUpdate's content fields).
_UPDATABLE = frozenset(PageUpdate.model_fields) - {"expected_revision"}
#: Fields an update may set back to None (mirrors ``PageStorage._update_locked``).
_NULLABLE = frozenset(
    {
        "display_type",
        "rows",
        "template",
        "line_metadata",
        "transition_strategy",
        "transition_interval_ms",
        "transition_step_size",
        "canvases",
    }
)


class PageNotFound(LookupError):
    def __init__(self, page_id: str):
        super().__init__(f"Page not found: {page_id}")


class DraftNotFound(LookupError):
    def __init__(self, page_id: str):
        super().__init__(f"Page {page_id} has no draft")


class RevisionNotFound(LookupError):
    def __init__(self, revision_id: str):
        super().__init__(f"Saved version not found: {revision_id}")


class NoDraftToPublish(Exception):
    def __init__(self, page_id: str):
        super().__init__(f"Page {page_id} has no draft to publish")


class DraftExists(Exception):
    def __init__(self, page_id: str):
        super().__init__(
            f"Page {page_id} already has a draft. Discard it, publish it, or restore with replace_draft=true."
        )


class DraftConflict(Exception):
    def __init__(self):
        super().__init__("The draft changed since it was loaded. Reload the draft before saving or discarding it.")


class DraftFromNewerBuild(Exception):
    """The page's draft file was written by a newer FiestaBoard; this build must not overwrite it."""

    def __init__(self, page_id: str):
        super().__init__(
            f"Page {page_id} has a draft saved by a newer version of FiestaBoard. "
            "Open it there, or update this hub, before changing it."
        )


class InvalidDraft(ValueError):
    """The draft would not be a valid page, or is over the size bound."""


def _epoch(value: datetime | None) -> float | None:
    return value.timestamp() if isinstance(value, datetime) else None


def _based_on(page: Page) -> str | None:
    """The published page's ``updated_at`` (else ``created_at``), at full precision: two saves can share a second."""
    stamp = page.updated_at or page.created_at
    return stamp.isoformat() if isinstance(stamp, datetime) else None


class PageDraftsMixin:
    """Mixed into ``PageService``; relies on its ``storage``, ``history`` and ``update_page``."""

    storage: Any
    history: PageHistory

    # ── helpers ────────────────────────────────────────────────────────

    def _live(self, page_id: str) -> Page:
        page = self.storage.get(page_id)
        if page is None:
            raise PageNotFound(page_id)
        return page

    def draft_view(self, record: dict, page: Page) -> dict:
        """A stored draft as the ``PageDraft`` wire shape."""
        return {
            "page_id": page.id,
            "revision": record["revision"],
            "saved_at": iso(record["saved_at"]),
            "based_on": record.get("based_on"),
            "stale": record.get("based_on") != _based_on(page),
            "restored_from": record.get("restored_from"),
            "via": record.get("via"),
            "content": record["content"],
        }

    def _prospective(self, page: Page, content: dict) -> dict:
        """*content* validated as the page it would publish; its normalised JSON."""
        try:
            prospective = Page(**{**content, "id": page.id, "type": page.type})
        except ValidationError as exc:
            raise InvalidDraft(f"Invalid draft: {exc.errors()[0]['msg']}") from exc
        errors = prospective.validate_config()
        if errors:
            raise InvalidDraft(f"Invalid draft: {'; '.join(errors)}")
        normalised = page_content(prospective)
        size = len(json.dumps(normalised).encode("utf-8"))
        if size > MAX_DRAFT_BYTES:
            raise InvalidDraft(f"The draft is {size} bytes; a draft may be at most {MAX_DRAFT_BYTES // 1024} KiB.")
        return normalised

    def _store_draft(self, page: Page, content: dict, previous: dict | None, **meta: Any) -> dict:
        if previous is not None and previous["content"] == content and not meta.get("restored_from"):
            return previous
        record = {
            "revision": str(uuid.uuid4()),
            "saved_at": self.history.clock(),
            "based_on": previous.get("based_on") if previous else _based_on(page),
            "restored_from": meta.get("restored_from", previous.get("restored_from") if previous else None),
            "via": meta.get("via"),
            "content": content,
        }
        try:
            self.history.put_draft(page.id, record)
        except SchemaTooNewError as exc:
            # Reads treat that file as no draft; a write must not stamp our
            # older schema_version over it (and must not 500).
            raise DraftFromNewerBuild(page.id) from exc
        return record

    # ── drafts ─────────────────────────────────────────────────────────

    def list_drafts(self) -> list[dict]:
        out = []
        for record in self.history.list_drafts():
            page = self.storage.get(record["page_id"])
            if page is not None:
                out.append(self.draft_view(record, page))
        return out

    def get_draft(self, page_id: str) -> dict:
        page = self._live(page_id)
        record = self.history.get_draft(page_id)
        if record is None:
            raise DraftNotFound(page_id)
        return self.draft_view(record, page)

    def save_draft(self, page_id: str, data: PageUpdate, *, via: str | None = None) -> dict:
        with self.storage.lock:
            page = self._live(page_id)
            previous = self.history.get_draft(page_id)
            if data.expected_revision is not None and (previous or {}).get("revision") != data.expected_revision:
                raise DraftConflict()
            base = previous["content"] if previous else page_content(page)
            updates = {
                k: v
                for k, v in data.model_dump(exclude_unset=True).items()
                if k in _UPDATABLE and (v is not None or k in _NULLABLE)
            }
            content = self._prospective(page, {**base, **updates})
            return self.draft_view(self._store_draft(page, content, previous, via=via), page)

    def discard_draft(self, page_id: str, *, expected_revision: str | None = None) -> None:
        with self.storage.lock:
            self._live(page_id)
            record = self.history.get_draft(page_id)
            if record is None:
                raise DraftNotFound(page_id)
            if expected_revision is not None and record["revision"] != expected_revision:
                raise DraftConflict()
            self.history.delete_draft(page_id)

    def publish_draft(
        self,
        page_id: str,
        *,
        expected_revision: str | None = None,
        expected_draft_revision: str | None = None,
        via: str | None = None,
        check_content: Callable[[dict], None] | None = None,
    ) -> tuple[Page, Page]:
        """Apply the draft to the published page; answers ``(before, after)``.

        *expected_revision* is the published page's (412 when it moved);
        *expected_draft_revision* is the draft's (412 when another device
        saved the draft since). *check_content* runs on the draft's content
        under the lock before anything is written (the routes' beta guard).
        """
        with self.storage.lock:
            before = self._live(page_id)
            record = self.history.get_draft(page_id)
            if record is None:
                raise NoDraftToPublish(page_id)
            if expected_draft_revision is not None and record["revision"] != expected_draft_revision:
                raise DraftConflict()
            content = record["content"]
            if check_content is not None:
                check_content(content)
            fields = {k: content.get(k) for k in _UPDATABLE if k in content}
            restored_from = record.get("restored_from")
            try:
                update = PageUpdate(**fields, expected_revision=expected_revision)
            except ValidationError as exc:
                raise InvalidDraft(f"Invalid draft: {exc.errors()[0]['msg']}") from exc
            after = self.update_page(
                page_id,
                update,
                origin="restored" if restored_from else "published",
                via=via,
                restored_from=restored_from,
            )
            if after is None:  # deleted under us; the lock makes this unreachable today
                raise PageNotFound(page_id)
            self.history.delete_draft(page_id)
            return before, after

    # ── saved versions ─────────────────────────────────────────────────

    def list_revisions(self, page_id: str) -> list[dict]:
        page = self._live(page_id)
        current = page_content(page)
        return [self._revision_view(r, current) for r in reversed(self.history.revisions(page_id))]

    def get_revision(self, page_id: str, revision_id: str) -> dict:
        page = self._live(page_id)
        entry = self.history.revision(page_id, revision_id)
        if entry is None:
            raise RevisionNotFound(revision_id)
        return {**self._revision_view(entry, page_content(page)), "content": entry["content"]}

    def restore_revision(
        self,
        page_id: str,
        revision_id: str,
        *,
        replace_draft: bool = False,
        via: str | None = None,
        check_content: Callable[[dict], None] | None = None,
    ) -> dict:
        with self.storage.lock:
            page = self._live(page_id)
            entry = self.history.revision(page_id, revision_id)
            if entry is None:
                raise RevisionNotFound(revision_id)
            previous = self.history.get_draft(page_id)
            if previous is not None and not replace_draft:
                raise DraftExists(page_id)
            if check_content is not None:
                check_content(entry["content"])
            content = self._prospective(page, entry["content"])
            record = self._store_draft(page, content, None, via=via, restored_from=revision_id)
            return self.draft_view(record, page)

    @staticmethod
    def _revision_view(entry: dict, current: dict) -> dict:
        from src.devices import resolve_dimensions

        content = entry["content"]
        try:
            dims = resolve_dimensions(
                content.get("device_type"),
                content.get("notes_wide") or 1,
                content.get("notes_tall") or 1,
                content.get("grid_rows"),
                content.get("grid_cols"),
            )
            rows, cols = dims.rows, dims.cols
        except (ValueError, TypeError):
            rows, cols = 0, 0
        return {
            "id": entry["id"],
            "saved_at": iso(entry["saved_at"]),
            "origin": entry["origin"],
            "via": entry.get("via"),
            "restored_from": entry.get("restored_from"),
            "name": content.get("name") or "",
            "rows": rows,
            "cols": cols,
            "current": content == current,
        }

    def _record_revision(
        self,
        page: Page,
        *,
        origin: str,
        via: str | None,
        restored_from: str | None = None,
        previous: Page | None = None,
    ) -> None:
        """Record *page* as a saved version. Advisory: a failure is logged, never raised."""
        try:
            baseline = None
            if previous is not None:
                baseline = (page_content(previous), _epoch(previous.updated_at) or _epoch(previous.created_at) or 0.0)
            self.history.record(
                page.id, page_content(page), origin=origin, via=via, restored_from=restored_from, baseline=baseline
            )
        except Exception:
            logger.warning("Could not record a saved version of page %s", page.id, exc_info=True)


__all__ = [
    "DraftConflict",
    "DraftExists",
    "DraftFromNewerBuild",
    "DraftNotFound",
    "InvalidDraft",
    "NoDraftToPublish",
    "PageDraftsMixin",
    "PageNotFound",
    "RevisionNotFound",
]
