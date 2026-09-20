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

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Longest title, derived or typed.
TITLE_MAX_LENGTH = 80

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


def derive_title(messages: list[ConversationMessage]) -> str:
    """The first non-blank user line, cut to :data:`TITLE_MAX_LENGTH`."""
    for message in messages:
        if message.role == "user":
            line = message.content.strip().splitlines()[0].strip() if message.content.strip() else ""
            if line:
                return line[:TITLE_MAX_LENGTH]
    return "Untitled chat"
