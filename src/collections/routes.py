"""FastAPI router for the collection endpoints.

Handlers were moved here verbatim from ``src/api_server.py`` (issue #1756);
Phase 2 slice 1 then applied ``docs/internal/reference/API_CONVENTIONS.md`` to
them and retired the call-time ``from src.api_server import ...`` seams the
move left behind.

Collaborators now resolve from their canonical homes at **module import
time**, so this module never loads ``src.api_server``
(``tests/test_collections_decoupled.py`` asserts that in a fresh
interpreter). Tests that need to stub a collaborator patch it where this
module binds it — ``src.collections.routes.<name>`` — not
``src.api_server.<name>``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api_deprecation import superseded_by_v1
from src.api_errors import errors
from src.pages.service import get_page_service
from src.templates.engine import get_template_engine
from src.templates.expressions import validate_expression

from .models import (
    CollectionCreate,
    CollectionDeleteResponse,
    CollectionListResponse,
    CollectionResponse,
    CollectionUpdate,
)
from .service import get_collection_service

router = APIRouter(tags=["collections"])


def _validate_collection_payload(
    data,
    page_service,
    *,
    require_pages: bool = True,
) -> None:
    """Shared validation for create / update.

    Confirms every page_id (membership and rule targets) resolves to a real
    page, and statically validates variable-mode rule expressions against the
    known plugin sources before we let them hit storage.
    """
    page_ids = getattr(data, "page_ids", None)
    if page_ids is None and require_pages:
        return  # let Pydantic surface the missing field
    if page_ids is not None:
        for pid in page_ids:
            if not page_service.get_page(pid):
                raise HTTPException(status_code=400, detail=f"Page not found: {pid}")

    variable = getattr(data, "variable", None)
    if variable is None:
        return

    if page_ids is not None:
        if variable.default_page_id not in page_ids:
            raise HTTPException(
                status_code=400,
                detail="default_page_id must be one of page_ids",
            )
        for idx, rule in enumerate(variable.rules):
            if rule.page_id not in page_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Variable rule {idx} page_id not in page_ids",
                )

    template_engine = get_template_engine()
    known_sources = template_engine.get_all_known_sources()
    for idx, rule in enumerate(variable.rules):
        issues = validate_expression(rule.expression, known_sources=known_sources)
        if issues:
            first = issues[0]
            raise HTTPException(
                status_code=400,
                detail=(f"Variable rule {idx} expression invalid: {first.code} {first.message}"),
            )


@router.get(
    "/collections",
    response_model=CollectionListResponse,
    dependencies=[superseded_by_v1("GET /collections")],
)
async def list_collections():
    """List all collections."""
    collection_service = get_collection_service()
    collections = collection_service.list_collections()
    return CollectionListResponse(collections=collections, total=len(collections))


@router.post(
    "/collections",
    response_model=CollectionResponse,
    status_code=201,
    responses=errors(400),
    dependencies=[superseded_by_v1("POST /collections")],
)
async def create_collection(data: CollectionCreate):
    """Create a new collection."""
    collection_service = get_collection_service()
    page_service = get_page_service()

    _validate_collection_payload(data, page_service)

    try:
        return collection_service.create_collection(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/collections/{collection_id}",
    response_model=CollectionResponse,
    responses=errors(404),
    dependencies=[superseded_by_v1("GET /collections/{collection_id}")],
)
async def get_collection(collection_id: str):
    """Get a collection by ID."""
    collection_service = get_collection_service()
    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection not found: {collection_id}")
    return collection


@router.put(
    "/collections/{collection_id}",
    response_model=CollectionResponse,
    responses=errors(400, 404),
    dependencies=[superseded_by_v1("PUT /collections/{collection_id}")],
)
async def update_collection(collection_id: str, data: CollectionUpdate):
    """Update an existing collection."""
    collection_service = get_collection_service()
    page_service = get_page_service()

    _validate_collection_payload(data, page_service, require_pages=False)

    try:
        collection = collection_service.update_collection(collection_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection not found: {collection_id}")
    return collection


@router.delete(
    "/collections/{collection_id}",
    response_model=CollectionDeleteResponse,
    responses=errors(404),
    dependencies=[superseded_by_v1("DELETE /collections/{collection_id}")],
)
async def delete_collection(collection_id: str):
    """Delete a collection."""
    collection_service = get_collection_service()
    deleted = collection_service.delete_collection(collection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Collection not found: {collection_id}")
    return CollectionDeleteResponse(id=collection_id)
