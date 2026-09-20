"""Conversation service: the autosave upsert, the read side, and the scrub.

**The secret scrub.** The transcript is stored as the panel holds it, and
the panel holds whatever the model said and whatever a tool returned. The
ops layer already refuses to *set* a credential through a chat tool
(:data:`src.ops.executors.SECRET_SETTING_KEYS`) and masks them on read, so
in the normal course nothing secret reaches the transcript. This scrub is
the guard for the other course — a user pasting a key into the chat for
the assistant to "just use", a tool argument the model filled in from that
paste, a result that echoed a header — and it runs in two passes over the
whole document:

1. **By key.** Any value under a key that names a credential is stored as
   ``***``. The key set is :data:`SECRET_SETTING_KEYS` (what
   ``update_setting`` refuses) united with
   :data:`src.config_manager.SENSITIVE_FIELDS` (what the config masks on
   read, which is where a ``configure_plugin`` argument ends up), matched
   case-insensitively, plus any key that *contains* ``key``, ``token``,
   ``secret`` or ``password`` — so a plugin's ``finnhub_api_key`` or a
   ``webhook_secret_url`` is caught without this list knowing its name.
2. **By shape.** Free text — a user line, the assistant's prose, a string
   argument, a title — has any run that looks like a credential replaced by
   ``***``: vendor-prefixed keys (``sk-…``, ``ghp_…``, ``xoxb-…``,
   ``AKIA…``), JWTs (``eyJ…``), and long unbroken hex or base64 runs.
   Conservative on purpose: a UUID, a date, a template line or a URL path
   is left alone; the cost of a false positive is three asterisks in a
   transcript, the cost of a miss is a key on disk.

The scrub runs on write only. What is on disk is what is served, so a
client that reads a conversation back and re-PUTs it cannot un-mask
anything: the masked value is all it ever had.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.config_manager import SENSITIVE_FIELDS
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

#: Every key name whose value is a credential, lower-cased for matching.
SECRET_KEYS: frozenset[str] = frozenset(k.lower() for k in SECRET_SETTING_KEYS | set(SENSITIVE_FIELDS))

#: A key containing one of these names a credential whatever the rest says.
_SECRET_KEY_FRAGMENTS = ("key", "token", "secret", "password")

#: Runs of text that look like a credential. Each alternative is anchored on
#: a word-ish boundary so a run inside a longer identifier is still caught
#: but a short ordinary word never is.
_SECRET_TEXT_PATTERNS = re.compile(
    r"(?<![A-Za-z0-9_/+.-])(?:"
    r"sk-[A-Za-z0-9_-]{16,}"  # OpenAI-style and many others
    r"|(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}"  # GitHub
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"  # Slack
    r"|AKIA[0-9A-Z]{16}"  # AWS access key id
    r"|AIza[0-9A-Za-z_-]{35}"  # Google API key
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]+)?"  # JWT
    r"|[0-9a-fA-F]{32,}"  # hex digest / hex token
    r"|(?=[A-Za-z0-9+/_-]*[0-9])(?=[A-Za-z0-9+/_-]*[A-Za-z])[A-Za-z0-9+/_-]{40,}={0,2}"  # base64-ish, mixed
    r")(?![A-Za-z0-9_/+-])"
)


def is_secret_key(key: str) -> bool:
    """True when a dict key names a credential."""
    lowered = key.lower()
    return lowered in SECRET_KEYS or any(fragment in lowered for fragment in _SECRET_KEY_FRAGMENTS)


def scrub_text(text: str) -> str:
    """*text* with every credential-shaped run replaced by ``***``."""
    return _SECRET_TEXT_PATTERNS.sub(MASK, text)


def scrub_secrets(value: Any) -> Any:
    """A deep copy of *value* with secrets masked by key and by shape."""
    if isinstance(value, dict):
        return {k: (MASK if is_secret_key(str(k)) else scrub_secrets(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    if isinstance(value, str):
        return scrub_text(value)
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

        Returns ``(conversation, created)``. The title is the existing
        record's, else derived from the first (scrubbed) user line.
        ``created_at`` survives an update; ``updated_at`` moves.
        """
        messages = _scrub_messages(data.messages)
        sent = data.model_fields_set
        with self.storage.lock:
            existing = self.storage.get(conversation_id)
            now = utc_now_iso()
            conversation = Conversation(
                id=conversation_id,
                title=existing.title if existing else derive_title(messages),
                created_at=existing.created_at if existing else now,
                updated_at=now,
                provider_id=data.provider_id if "provider_id" in sent or existing is None else existing.provider_id,
                model=data.model if "model" in sent or existing is None else existing.model,
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
            renamed = existing.model_copy(update={"title": scrub_text(data.title).strip() or MASK})
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
