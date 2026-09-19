"""Conversation service: the autosave upsert, the read side, and the scrub.

**The secret scrub.** The transcript is stored as the panel holds it, and
the panel holds whatever the model said and whatever a tool returned. The
ops layer already refuses to *set* a credential through a chat tool
(:data:`src.ops.executors.SECRET_SETTING_KEYS`) and masks them on read, so
in the normal course nothing secret reaches the transcript. This scrub is
the guard for the other course — a user pasting a key into the chat for
the assistant to "just use", a tool argument the model filled in from that
paste, a result that echoed a header. Any value under one of those key
names, anywhere in the document, is stored as ``***``. A key that arrives
already masked stays masked.

The scrub runs on write only. What is on disk is what is served, so a
client that reads a conversation back and re-PUTs it cannot un-mask
anything: the masked value is all it ever had.
"""

from __future__ import annotations

import logging
from typing import Any

from src.ops.executors import SECRET_SETTING_KEYS

from .models import (
    Conversation,
    ConversationMessage,
    ConversationRename,
    ConversationUpsert,
    derive_title,
    utc_now_iso,
)
from .storage import ConversationStorage

logger = logging.getLogger(__name__)

MASK = "***"


def scrub_secrets(value: Any) -> Any:
    """A deep copy of *value* with every secret-keyed value replaced by ``***``.

    The key list is the ops layer's :data:`SECRET_SETTING_KEYS`, so the two
    cannot disagree about what a credential is. Keys are matched exactly and
    case-sensitively, as the settings models spell them.
    """
    if isinstance(value, dict):
        return {k: (MASK if k in SECRET_SETTING_KEYS else scrub_secrets(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    return value


def _scrub_messages(messages: list[ConversationMessage]) -> list[ConversationMessage]:
    return [ConversationMessage(**scrub_secrets(m.model_dump())) for m in messages]


class ConversationService:
    """Service for saved-conversation operations."""

    def __init__(self, storage: ConversationStorage | None = None):
        self.storage = storage or ConversationStorage()

    def list(self, query: str | None = None) -> list[Conversation]:
        """Most recently updated first; ``query`` filters by title substring."""
        items = self.storage.list_all()
        if query:
            needle = query.strip().casefold()
            if needle:
                items = [c for c in items if needle in c.title.casefold()]
        return items

    def get(self, conversation_id: str) -> Conversation | None:
        return self.storage.get(conversation_id)

    def upsert(self, conversation_id: str, data: ConversationUpsert) -> tuple[Conversation, bool]:
        """Store the transcript under *conversation_id*.

        Returns ``(conversation, created)``. The title is the client's if it
        sent one, else the existing record's, else derived from the first
        user line. ``created_at`` survives an update; ``updated_at`` moves.
        """
        messages = _scrub_messages(data.messages)
        with self.storage.lock:
            existing = self.storage.get(conversation_id)
            now = utc_now_iso()
            conversation = Conversation(
                id=conversation_id,
                title=data.title or (existing.title if existing else derive_title(messages)),
                created_at=existing.created_at if existing else now,
                updated_at=now,
                provider_id=data.provider_id,
                model=data.model,
                approval=data.approval,
                messages=messages,
            )
            created = self.storage.upsert(conversation)
        return conversation, created

    def rename(self, conversation_id: str, data: ConversationRename) -> Conversation | None:
        with self.storage.lock:
            existing = self.storage.get(conversation_id)
            if existing is None:
                return None
            # A rename is not an update to the transcript: ``updated_at`` (and
            # so the list order and the eviction order) stays put.
            renamed = existing.model_copy(update={"title": data.title})
            self.storage.upsert(renamed)
        return renamed

    def delete(self, conversation_id: str) -> bool:
        return self.storage.delete(conversation_id)

    def clear(self) -> int:
        return self.storage.clear()


_conversation_service: ConversationService | None = None


def get_conversation_service() -> ConversationService:
    global _conversation_service
    if _conversation_service is None:
        _conversation_service = ConversationService()
    return _conversation_service


def reset_conversation_service() -> None:
    """Drop the singleton (tests: each test gets its own data dir)."""
    global _conversation_service
    _conversation_service = None
