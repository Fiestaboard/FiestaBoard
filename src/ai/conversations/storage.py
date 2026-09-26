"""JSON file-based storage for saved conversations: ``data/ai_conversations.json``.

Built on the storage kernel (:class:`src.storage.json_store.JsonStore`) like
every other store: atomic writes, an in-process lock, and an integer
``schema_version`` with an ordered ``MIGRATIONS`` list (empty at v1).

**The cap.** The store keeps at most :data:`MAX_CONVERSATIONS` records.
Inserting a new id when the store is full evicts the least recently
*updated* conversation first. A chat log is not configuration — the cap is
what keeps a year of autosaves from growing the file without bound on a
Pi — and 200 is far more than the History list is useful at. Updating an
existing id never evicts anything.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable

from src.storage.json_store import JsonStore

from .models import Conversation

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1

#: Most conversations the store keeps; the least recently updated is
#: evicted when a new one arrives past this.
MAX_CONVERSATIONS = 200

# Schema migrations operate on the raw ``conversations`` list. Each function
# returns the count of records it modified. None yet: v1 is the first format.
MIGRATIONS: list[tuple[int, Callable[[list[dict]], int]]] = []


def _adapt_migration(fn: Callable[[list[dict]], int]) -> Callable[[dict], int]:
    """Adapt a records-list migration to the kernel's whole-document signature."""
    return lambda data: fn(data.get("conversations", []))


class ConversationStorage:
    """JSON file-based storage for saved conversations."""

    def __init__(self, storage_file: str | None = None):
        self._store = JsonStore(
            "ai_conversations.json" if storage_file is None else storage_file,
            current_schema_version=CURRENT_SCHEMA_VERSION,
            migrations=[(version, _adapt_migration(fn)) for version, fn in MIGRATIONS],
            label="AI conversations",
        )
        self.storage_file = self._store.path

        self._conversations: dict[str, Conversation] = {}
        # Raw entries that failed Pydantic validation on load, round-tripped
        # through _save so a parsing failure never silently drops a chat
        # (the src/pages/storage.py pattern, #1305).
        self._failed_entries: list[dict] = []
        self._load()

        logger.info(
            f"ConversationStorage initialized (file: {self.storage_file}, conversations: {len(self._conversations)})"
        )

    @property
    def lock(self) -> threading.RLock:
        """The kernel store's lock."""
        return self._store.lock

    def _load(self) -> None:
        try:
            data = self._store.load()
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load AI conversations file: {e}")
            self._conversations = {}
            self._failed_entries = []
            return

        if data is None:
            self._conversations = {}
            self._failed_entries = []
            return

        self._conversations = {}
        self._failed_entries = []
        for record in data.get("conversations", []):
            try:
                conversation = Conversation(**record)
            except Exception as e:
                record_id = record.get("id", "<unknown>") if isinstance(record, dict) else "<unknown>"
                logger.error(
                    "Failed to parse conversation %s; preserving raw entry to avoid data loss: %s", record_id, e
                )
                self._failed_entries.append(record)
                continue
            self._conversations[conversation.id] = conversation

        logger.info(f"Loaded {len(self._conversations)} AI conversations from storage")

        if self._store.migrated:
            self._save()
            logger.info("Saved migrated AI conversations to storage")

    def _save(self) -> None:
        """Save conversations to the storage file atomically via the kernel."""
        try:
            records = [c.model_dump() for c in self._conversations.values()]
            records.extend(self._failed_entries)
            self._store.save({"schema_version": CURRENT_SCHEMA_VERSION, "conversations": records})
            logger.debug(f"Saved {len(self._conversations)} AI conversations to storage")
        except OSError as e:
            logger.error(f"Failed to save AI conversations file: {e}")
            raise

    # --- CRUD ------------------------------------------------------------

    def list_all(self) -> list[Conversation]:
        """Every conversation, most recently updated first."""
        items = list(self._conversations.values())
        items.sort(key=lambda c: c.updated_at, reverse=True)
        return items

    def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def upsert(self, conversation: Conversation) -> bool:
        """Store *conversation* under its id. Returns True when it is new.

        A new id past :data:`MAX_CONVERSATIONS` evicts the least recently
        updated record(s) first; an existing id is replaced in place.
        """
        with self._store.lock:
            created = conversation.id not in self._conversations
            if created:
                self._evict_to_make_room()
            self._conversations[conversation.id] = conversation
            self._save()
        return created

    def _evict_to_make_room(self) -> None:
        overflow = len(self._conversations) - MAX_CONVERSATIONS + 1
        if overflow <= 0:
            return
        oldest = sorted(self._conversations.values(), key=lambda c: c.updated_at)[:overflow]
        for victim in oldest:
            del self._conversations[victim.id]
            logger.info(f"Evicted AI conversation {victim.id} ({victim.title!r}) to stay under {MAX_CONVERSATIONS}")

    def delete(self, conversation_id: str) -> bool:
        with self._store.lock:
            if conversation_id not in self._conversations:
                return False
            del self._conversations[conversation_id]
            self._save()
        logger.info(f"Deleted AI conversation: {conversation_id}")
        return True

    def clear(self) -> int:
        """Delete everything. Returns how many conversations there were."""
        with self._store.lock:
            count = len(self._conversations)
            self._conversations = {}
            self._save()
        logger.info(f"Cleared {count} AI conversation(s)")
        return count
