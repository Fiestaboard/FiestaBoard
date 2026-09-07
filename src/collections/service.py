"""Collection service: CRUD and active-page resolution.

For ``time`` mode the resolution is deterministic and stateless — same logic
as the original carousel.

For ``variable`` mode the service evaluates each rule against the live plugin
template context (built once per resolution call) and returns the first match.
Expression errors are logged but never raised, so a single bad rule cannot
blank the board.
"""

import logging
import math
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .models import (
    Collection,
    CollectionCreate,
    CollectionUpdate,
    is_collection_id,
)
from .storage import CollectionStorage

logger = logging.getLogger(__name__)


def _is_truthy(result: str) -> bool:
    """Interpret an expression engine result string as truthy/falsy.

    The expression engine renders booleans as "Yes"/"No", numbers as their
    string form, and errors as ``#CODE``. We treat empty, error, "No",
    "False", and numeric-zero results as falsy; everything else as truthy.
    """
    if not result:
        return False
    if result.startswith("#"):
        return False
    s = result.strip()
    if not s:
        return False
    if s.lower() in {"no", "false"}:
        return False
    try:
        return float(s) != 0.0
    except ValueError:
        return True


class CollectionService:
    """Service for collection operations.

    Handles CRUD and resolves which page should currently be displayed for
    a given collection ID, dispatching on ``selection_mode``.
    """

    def __init__(self, storage: CollectionStorage | None = None):
        self.storage = storage or CollectionStorage()
        logger.info("CollectionService initialized")

    # --- CRUD ------------------------------------------------------------

    def list_collections(self) -> list[Collection]:
        return self.storage.list_all()

    def get_collection(self, collection_id: str) -> Collection | None:
        return self.storage.get(collection_id)

    def create_collection(self, data: CollectionCreate) -> Collection:
        collection = Collection(
            name=data.name,
            page_ids=data.page_ids,
            selection_mode=data.selection_mode,
            time=data.time,
            variable=data.variable,
            random=data.random,
            created_at=datetime.utcnow(),
        )
        return self.storage.create(collection)

    def update_collection(self, collection_id: str, data: CollectionUpdate) -> Collection | None:
        updates = data.model_dump(exclude_unset=True)
        return self.storage.update(collection_id, updates)

    def delete_collection(self, collection_id: str) -> bool:
        return self.storage.delete(collection_id)

    def exists(self, collection_id: str) -> bool:
        return self.storage.exists(collection_id)

    # --- resolution ------------------------------------------------------

    def resolve_page_id(
        self,
        ref_id: str,
        now_unix: float | None = None,
        context: dict[str, Any] | None = None,
        context_factory: Callable[[], dict[str, Any] | None] | None = None,
    ) -> str | None:
        """If *ref_id* is a collection, return the page that should be shown.

        - Plain page IDs are returned unchanged.
        - For ``time`` mode, falls back to deterministic time-slice cycling.
        - For ``variable`` mode, walks ``variable.rules`` in order and returns
          the first ``page_id`` whose expression evaluates truthy. If
          ``context`` is None, ``context_factory`` (when given) supplies it —
          the display loop passes its per-tick shared BOARD-AGNOSTIC context
          this way (issue #1752) so every board's resolution shares one
          ``board=None`` plugin fan-out per tick; otherwise it is built
          lazily from the plugin registry (also board-agnostic).
        - For ``random`` mode, returns the shuffle-bag page for the current
          duration window (deterministic, stateless, no back-to-back repeats).

        Returns None if the collection is not found or has no pages.
        """
        if not is_collection_id(ref_id):
            return ref_id

        collection = self.storage.get(ref_id)
        if not collection or not collection.page_ids:
            return None

        if collection.selection_mode == "time":
            ts = now_unix if now_unix is not None else time.time()
            return collection.current_page_id_time(ts)

        if collection.selection_mode == "variable":
            return self._resolve_variable(collection, context, context_factory)

        if collection.selection_mode == "random":
            ts = now_unix if now_unix is not None else time.time()
            return collection.current_page_id_random(ts)

        # Unknown selection mode (shouldn't happen given the Literal type).
        logger.warning(f"Unknown selection_mode {collection.selection_mode!r} for {ref_id}")
        return collection.page_ids[0]

    def seconds_until_next_check(self, ref_id: str, now_unix: float | None = None) -> int | None:
        """Return how many seconds until the active-page loop should
        re-check this collection.

        - ``time`` mode: seconds until the next cycle boundary (matches the
          legacy carousel behavior).
        - ``variable`` mode: ``variable.poll_seconds``.
        - ``random`` mode: seconds until the next duration window boundary
          (same math as ``time`` mode, using ``random.interval_seconds``).

        Returns None for non-collections or collections with <2 pages.
        """
        if not is_collection_id(ref_id):
            return None
        collection = self.storage.get(ref_id)
        if not collection or not collection.page_ids or len(collection.page_ids) < 2:
            return None

        if collection.selection_mode == "time":
            ts = now_unix if now_unix is not None else time.time()
            elapsed = ts % collection.time.interval_seconds
            return max(1, math.ceil(collection.time.interval_seconds - elapsed))

        if collection.selection_mode == "variable" and collection.variable is not None:
            return collection.variable.poll_seconds

        if collection.selection_mode == "random" and collection.random is not None:
            ts = now_unix if now_unix is not None else time.time()
            elapsed = ts % collection.random.interval_seconds
            return max(1, math.ceil(collection.random.interval_seconds - elapsed))

        return None

    # --- variable-mode internals -----------------------------------------

    def _build_variable_context(self) -> dict[str, Any]:
        """Build the plugin template context for variable-mode evaluation.

        Imported lazily to avoid a hard dependency from this module on the
        plugin registry — useful for tests that pass an explicit context.
        """
        from src.plugins.registry import get_plugin_registry  # local import

        return get_plugin_registry().build_template_context()

    def _resolve_variable(
        self,
        collection: Collection,
        context: dict[str, Any] | None,
        context_factory: Callable[[], dict[str, Any] | None] | None = None,
    ) -> str | None:
        from src.templates.expressions import evaluate  # local import

        if collection.variable is None:
            # Should be caught by validation; defend anyway.
            return collection.page_ids[0]

        if not collection.variable.rules:
            # No rules to evaluate — the default always wins; skip the
            # plugin fan-out a context build would cost.
            return collection.variable.default_page_id

        ctx = context
        if ctx is None and context_factory is not None:
            # Per-tick shared context from the display loop (issue #1752).
            ctx = context_factory()
        if ctx is None:
            ctx = self._build_variable_context()

        for idx, rule in enumerate(collection.variable.rules):
            try:
                result = evaluate(rule.expression, ctx)
            except Exception as e:  # safety net — evaluate() catches FormulaError
                logger.warning(f"Collection {collection.id} rule {idx} raised: {e}")
                continue
            if result.startswith("#"):
                logger.debug(f"Collection {collection.id} rule {idx} returned error {result}")
                continue
            if _is_truthy(result):
                return rule.page_id

        return collection.variable.default_page_id


_collection_service: CollectionService | None = None


def get_collection_service() -> CollectionService:
    global _collection_service
    if _collection_service is None:
        _collection_service = CollectionService()
    return _collection_service


def reset_collection_service_for_tests() -> None:
    """Clear the cached singleton. Tests that swap storage paths use this."""
    global _collection_service
    _collection_service = None


def resolve_active_page_id(page_id: str | None, get_collection_service: Callable[[], Any]) -> str | None:
    """Resolve a collection reference to the page it is currently showing.

    When ``page_id`` is a collection ID the Dashboard needs to know which
    member page the collection's logic is presently rendering on the board so
    it can name and link to that page (issue #1513). Plain page IDs (and None)
    are returned unchanged. Never raises — a collection that can't be resolved
    just yields None.

    Lived in ``src/api_server.py`` until Phase 2 §2.3; it reads nothing but
    collections, so the schedules router can import it from here instead of
    reaching into the app module at call time.

    The service *accessor* is a parameter, not this module's global: the caller
    passes its own binding, so the lookup keeps resolving through whichever
    ``get_collection_service`` the calling module binds (and stays lazy — a
    plain page id never touches the service at all).
    """
    if not is_collection_id(page_id):
        return page_id
    try:
        return get_collection_service().resolve_page_id(page_id)
    except Exception:  # pragma: no cover - defensive; resolution is best-effort
        logger.warning("Failed to resolve collection page for %s", page_id, exc_info=True)
        return None


def resolve_next_check_seconds(page_id: str | None, get_collection_service: Callable[[], Any]) -> int | None:
    """Seconds until ``page_id``'s collection may switch to a different page.

    A collection can rotate as often as every 5 seconds (2 for variable-mode
    polling), so a client that caches ``resolved_page_id`` on a fixed timer
    would name the wrong page for most of the interval. Handing back the
    collection's own cadence lets the Dashboard re-poll exactly when the page
    on the board can change (issue #1513). None for plain pages, collections
    that can't rotate (<2 pages), and any resolution failure.

    Takes the service accessor as a parameter for the same reason as
    :func:`resolve_active_page_id`.
    """
    if not is_collection_id(page_id):
        return None
    try:
        return get_collection_service().seconds_until_next_check(page_id)
    except Exception:  # pragma: no cover - defensive; resolution is best-effort
        logger.warning("Failed to compute next check for collection %s", page_id, exc_info=True)
        return None
