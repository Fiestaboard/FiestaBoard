"""FastAPI router for ``/ai/conversations`` — saved FiestaBot chats (#2022).

The third ``ai``-tagged router (with ``src/ai/routes.py`` for ``/ai/operations``
and ``src/ai/page_routes.py`` for ``/pages/ai/*``): one domain for the
conventions ratchet, its own prefix for readability.

**Conventions** (``docs/internal/reference/API_CONVENTIONS.md``): every route
declares its ``response_model`` and its errors through ``errors()``; bodies
are Pydantic models; failures are never 200. Two shapes worth naming:

- ``PUT /{id}`` is an **upsert** under a client-generated id — it is the
  panel's autosave, fired after every turn. It answers **201** the first
  time an id is seen and **200** after, so the client can tell the two
  apart without a preceding GET.
- ``GET /{id}/export`` is the same document as ``GET /{id}`` served as a
  download (``Content-Disposition: attachment``), so a thread can be
  attached to a bug report. It keeps the ``response_model`` — the body *is*
  the response model — and only adds the header.

The id is validated as a UUID in the path so a stray string never becomes a
record. Nothing here is reachable from the MCP tools: the assistant cannot
read, rewrite or delete its own history.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response

from src.api_errors import errors

from .models import (
    ConversationClearResponse,
    ConversationDeleteResponse,
    ConversationListResponse,
    ConversationRename,
    ConversationResponse,
    ConversationSummary,
    ConversationUpsert,
)
from .service import get_conversation_service

router = APIRouter(prefix="/ai/conversations", tags=["ai"])

_UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

ConversationId = Annotated[
    str,
    Path(pattern=_UUID_PATTERN, description="The conversation's id — a UUID the client generated."),
]


def _not_found(conversation_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Conversation not found: {conversation_id}")


@router.get(
    "",
    response_model=ConversationListResponse,
    responses=errors(422),
    summary="List saved conversations, newest first",
)
async def list_conversations(
    q: Annotated[str | None, Query(max_length=200, description="Case-insensitive title filter.")] = None,
) -> ConversationListResponse:
    """Summaries only (no transcripts), most recently updated first."""
    conversations = get_conversation_service().list(q)
    return ConversationListResponse(
        conversations=[ConversationSummary.of(c) for c in conversations],
        total=len(conversations),
    )


@router.delete(
    "",
    response_model=ConversationClearResponse,
    summary="Delete every saved conversation",
)
async def clear_conversations() -> ConversationClearResponse:
    """Idempotent: clearing an empty store is a success with ``deleted: 0``."""
    return ConversationClearResponse(deleted=get_conversation_service().clear())


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    responses=errors(404, 422),
    summary="Read one saved conversation with its transcript",
)
async def get_conversation(conversation_id: ConversationId) -> ConversationResponse:
    conversation = get_conversation_service().get(conversation_id)
    if conversation is None:
        raise _not_found(conversation_id)
    return conversation


@router.put(
    "/{conversation_id}",
    response_model=ConversationResponse,
    responses={201: {"model": ConversationResponse, "description": "Created"}, **errors(422)},
    summary="Save (create or replace) a conversation under a client id",
)
async def upsert_conversation(
    conversation_id: ConversationId, data: ConversationUpsert, response: Response
) -> ConversationResponse:
    """The panel's autosave. 201 on first sight of the id, 200 after.

    Secret-keyed values anywhere in the transcript are stored as ``***``
    (see :func:`src.ai.conversations.service.scrub_secrets`).
    """
    conversation, created = get_conversation_service().upsert(conversation_id, data)
    if created:
        response.status_code = 201
    return conversation


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
    responses=errors(404, 422),
    summary="Rename a saved conversation",
)
async def rename_conversation(conversation_id: ConversationId, data: ConversationRename) -> ConversationResponse:
    conversation = get_conversation_service().rename(conversation_id, data)
    if conversation is None:
        raise _not_found(conversation_id)
    return conversation


@router.delete(
    "/{conversation_id}",
    response_model=ConversationDeleteResponse,
    responses=errors(404, 422),
    summary="Delete one saved conversation",
)
async def delete_conversation(conversation_id: ConversationId) -> ConversationDeleteResponse:
    if not get_conversation_service().delete(conversation_id):
        raise _not_found(conversation_id)
    return ConversationDeleteResponse(id=conversation_id)


@router.get(
    "/{conversation_id}/export",
    response_model=ConversationResponse,
    responses=errors(404, 422),
    summary="Download one saved conversation as a JSON file",
)
async def export_conversation(conversation_id: ConversationId, response: Response) -> ConversationResponse:
    """``GET /{id}`` with a ``Content-Disposition`` so the browser saves it."""
    conversation = get_conversation_service().get(conversation_id)
    if conversation is None:
        raise _not_found(conversation_id)
    response.headers["Content-Disposition"] = f'attachment; filename="fiestabot-conversation-{conversation_id}.json"'
    response.headers["Cache-Control"] = "no-store"
    return conversation
