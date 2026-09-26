"""Pydantic models for saved conversations: the stored record and the wire.

The transcript is stored as the panel holds it, not as the chat endpoint
replays it. The wire shape (``src.ai.page_routes.ChatMessage``) is what the
model needs and is lossy for a person looking back: it drops the question
text of an ``ask_user``, the phase a tool call ended in, and the result the
card showed. So ``ConversationMessage`` pins only what every entry has — a
``role`` and ``content`` — and lets the rest through untouched
(``extra="allow"``), and :func:`src.ai.conversations.service.scrub_secrets`
walks the whole document before it is stored.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Longest title a person may type.
TITLE_MAX_LENGTH = 80

#: Longest title derived from what the user asked for. Shorter than a typed
#: one on purpose: a derived title is scanned in a list, not read, and the
#: History rows truncate around here anyway — better to cut at a word with
#: an ellipsis than to let the list cut mid-word.
TITLE_DERIVED_MAX_LENGTH = 48

ConversationRole = Literal["user", "assistant", "system", "tool"]


def utc_now_iso() -> str:
    """The store's timestamp format: ISO 8601 with an explicit ``+00:00``."""
    return datetime.now(UTC).isoformat()


class ConversationMessage(BaseModel):
    """One transcript entry, as the panel holds it.

    Everything beyond ``role`` / ``content`` (tool calls with their
    arguments, results and phases; a question and its answer; warnings) is
    carried as-is so the panel can render a saved chat exactly as it looked
    live.
    """

    model_config = ConfigDict(extra="allow")

    role: ConversationRole
    content: str = ""


class Conversation(BaseModel):
    """The stored record. ``ConversationResponse`` is this model: nothing on
    it is derived or masked at read time — the secret scrub happens on
    write, so what is on disk is what is served."""

    id: str
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    provider_id: str | None = None
    model: str | None = None
    #: The conversation's "don't ask again" flag (#2021), so a resumed chat
    #: keeps the approval choice the user made in it.
    approval: bool = False
    messages: list[ConversationMessage] = Field(default_factory=list)


ConversationResponse = Conversation


class ConversationSummary(BaseModel):
    """One row of ``GET /ai/conversations`` — no transcript."""

    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    provider_id: str | None = None
    model: str | None = None

    @classmethod
    def of(cls, conversation: Conversation) -> ConversationSummary:
        return cls(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=len(conversation.messages),
            provider_id=conversation.provider_id,
            model=conversation.model,
        )


class ConversationListResponse(BaseModel):
    """Body of ``GET /ai/conversations``."""

    conversations: list[ConversationSummary]
    total: int


class ConversationUpsert(BaseModel):
    """Body of ``PUT /ai/conversations/{id}`` — the panel's autosave.

    The title is never posted here: it is derived from the first user line
    on create and kept on update (so an autosave never undoes a rename);
    ``PATCH`` is the only way to change it. ``provider_id`` / ``model``
    left *out* of the body keep what the record already has — the panel
    saves before ``/settings/ai`` has answered — while an explicit ``null``
    clears them.
    """

    provider_id: str | None = None
    model: str | None = None
    approval: bool = False
    messages: list[ConversationMessage] = Field(min_length=1)


class ConversationRename(BaseModel):
    """Body of ``PATCH /ai/conversations/{id}``."""

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)

    @field_validator("title")
    @classmethod
    def _title_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title cannot be blank")
        return stripped


class ConversationDeleteResponse(BaseModel):
    """Body of ``DELETE /ai/conversations/{id}``: the deleted id, the same
    delete shape as the collections domain."""

    id: str


class ConversationClearResponse(BaseModel):
    """Body of ``DELETE /ai/conversations``."""

    deleted: int


#: A sentence or clause ends here — but only when what follows is a space or
#: the end of the line, so "7:00" and "v1.2" are not boundaries.
_CLAUSE_END = re.compile(r"[.?!;:](?=\s|$)")

#: Quotes a request often opens with, and the punctuation a title never ends on.
_WRAPPING_QUOTES = "\"'\u201c\u201d\u2018\u2019\u00ab\u00bb"
_TRAILING_PUNCTUATION = " .,;:!?-\u2013\u2014"

_UNTITLED = "Untitled chat"


def _title_from_line(line: str) -> str:
    """One line of a request, as a title: first clause, unquoted, trimmed."""
    boundary = _CLAUSE_END.search(line)
    if boundary:
        line = line[: boundary.start()]
    line = line.strip().strip(_WRAPPING_QUOTES).strip().rstrip(_TRAILING_PUNCTUATION).strip()
    if not line:
        return ""
    if len(line) <= TITLE_DERIVED_MAX_LENGTH:
        return line

    # Cut between words where there is one, and mark the cut.
    cut = line[: TITLE_DERIVED_MAX_LENGTH - 1].rstrip()
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut.rstrip(_TRAILING_PUNCTUATION) + "\u2026"


def derive_title(messages: list[ConversationMessage]) -> str:
    """What to call this conversation, from the first thing the user asked.

    The whole first line used to become the title, opening quote and all,
    cut at 80 characters mid-word (#2024). A title is scanned rather than
    read: the first sentence or clause of the request, without its quotes
    or its trailing punctuation, is what tells someone which chat this was.
    """
    for message in messages:
        if message.role != "user":
            continue
        content = message.content.strip()
        if not content:
            continue
        title = _title_from_line(content.splitlines()[0].strip())
        if title:
            return title
    return _UNTITLED
