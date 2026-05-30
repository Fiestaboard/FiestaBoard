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
from datetime import datetime
from typing import Any, Dict, List, Optional

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

    def __init__(self, storage: Optional[CollectionStorage] = None):
        self.storage = storage or CollectionStorage()
        logger.info("CollectionService initialized")

    # --- CRUD ------------------------------------------------------------

    def list_collections(self) -> List[Collection]:
        return self.storage.list_all()

    def get_collection(self, collection_id: str) -> Optional[Collection]:
        return self.storage.get(collection_id)

    def create_collection(self, data: CollectionCreate) -> Collection:
        collection = Collection(
            name=data.name,
            page_ids=data.page_ids,
            selection_mode=data.selection_mode,
            time=data.time,
            variable=data.variable,
            created_at=datetime.utcnow(),
        )
        return self.storage.create(collection)

    def update_collection(
        self, collection_id: str, data: CollectionUpdate
    ) -> Optional[Collection]:
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
        now_unix: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """If *ref_id* is a collection, return the page that should be shown.

        - Plain page IDs are returned unchanged.
        - For ``time`` mode, falls back to deterministic time-slice cycling.
        - For ``variable`` mode, walks ``variable.rules`` in order and returns
          the first ``page_id`` whose expression evaluates truthy. If
          ``context`` is None, it is built lazily from the plugin registry.

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
            return self._resolve_variable(collection, context)

        # Unknown selection mode (shouldn't happen given the Literal type).
        logger.warning(
            f"Unknown selection_mode {collection.selection_mode!r} for {ref_id}"
        )
        return collection.page_ids[0]

    def seconds_until_next_check(
        self, ref_id: str, now_unix: Optional[float] = None
    ) -> Optional[int]:
        """Return how many seconds until the active-page loop should
        re-check this collection.

        - ``time`` mode: seconds until the next cycle boundary (matches the
          legacy carousel behavior).
        - ``variable`` mode: ``variable.poll_seconds``.

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

        return None

    # --- variable-mode internals -----------------------------------------

    def _build_variable_context(self) -> Dict[str, Any]:
        """Build the plugin template context for variable-mode evaluation.

        Imported lazily to avoid a hard dependency from this module on the
        plugin registry — useful for tests that pass an explicit context.
        """
        from ..plugins.registry import get_plugin_registry  # local import
        return get_plugin_registry().build_template_context()

    def _resolve_variable(
        self,
        collection: Collection,
        context: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        from ..templates.expressions import evaluate  # local import

        if collection.variable is None:
            # Should be caught by validation; defend anyway.
            return collection.page_ids[0]

        ctx = context if context is not None else self._build_variable_context()

        for idx, rule in enumerate(collection.variable.rules):
            try:
                result = evaluate(rule.expression, ctx)
            except Exception as e:  # safety net — evaluate() catches FormulaError
                logger.warning(
                    f"Collection {collection.id} rule {idx} raised: {e}"
                )
                continue
            if result.startswith("#"):
                logger.debug(
                    f"Collection {collection.id} rule {idx} returned error {result}"
                )
                continue
            if _is_truthy(result):
                return rule.page_id

        return collection.variable.default_page_id


_collection_service: Optional[CollectionService] = None


def get_collection_service() -> CollectionService:
    global _collection_service
    if _collection_service is None:
        _collection_service = CollectionService()
    return _collection_service


def reset_collection_service_for_tests() -> None:
    """Clear the cached singleton. Tests that swap storage paths use this."""
    global _collection_service
    _collection_service = None
