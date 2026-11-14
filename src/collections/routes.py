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
from src.pages.storage import PageRevisionConflict
from src.templates.engine import get_template_engine
from src.templates.expressions import validate_expression

from .models import (
    CollectionCreate,
    CollectionDeleteResponse,
    CollectionDryRunRequest,
    CollectionDryRunResponse,
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


@router.post(
    "/collections/{collection_id}/dry-run",
    response_model=CollectionDryRunResponse,
    responses=errors(404, 422),
)
async def dry_run_collection(collection_id: str, request: CollectionDryRunRequest | None = None):
    """Which page this collection would pick at ``at`` (default now), and across a window (H8).

    A formula collection evaluates every rule (the first true one wins, else
    the default page) with H6's sample and missing data; ``window_seconds``
    adds a timeline (``step_seconds`` apart for formula collections, exact
    boundaries for time and random ones). Read-only: nothing is stored and no
    board is touched. An unknown collection is a 404.
    """
    from datetime import datetime

    from src.schedules.at_time import instant, stamp
    from src.templates.routes import _preview

    from . import dry_run

    collection = get_collection_service().get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection not found: {collection_id}")
    request = request or CollectionDryRunRequest()
    if (
        collection.selection_mode == "variable"
        and request.window_seconds // request.step_seconds + 1 > dry_run.MAX_POINTS
    ):
        raise HTTPException(
            status_code=422,
            detail=f"A formula collection's timeline is at most {dry_run.MAX_POINTS} points: widen step_seconds",
        )
    try:
        local, at_utc = instant(request.at if request.at is not None else datetime.now().astimezone())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    preview = _preview(request.model_copy(update={"at": None}))
    result = dry_run.run(collection, preview, local, request.window_seconds, request.step_seconds)
    return CollectionDryRunResponse(
        collection_id=collection.id,
        selection_mode=collection.selection_mode,
        at=stamp(at_utc),
        page_id=result.page_id,
        rules=result.rules,
        matched_rule=result.matched_rule,
        timeline=result.timeline,
        truncated=result.truncated,
        truncated_reason=result.truncated_reason,
        shown_on=dry_run.shown_on(collection.id, at_utc, local.tzinfo),
        sources=preview.sources,
    )


@router.put(
    "/collections/{collection_id}",
    response_model=CollectionResponse,
    responses=errors(400, 404, 412),
    dependencies=[superseded_by_v1("PUT /collections/{collection_id}")],
)
async def update_collection(collection_id: str, data: CollectionUpdate):
    """Update an existing collection."""
    collection_service = get_collection_service()
    page_service = get_page_service()

    _validate_collection_payload(data, page_service, require_pages=False)

    try:
        collection = collection_service.update_collection(collection_id, data)
    except PageRevisionConflict as e:
        raise HTTPException(status_code=412, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection not found: {collection_id}")
    return collection


@router.delete(
    "/collections/{collection_id}",
    response_model=CollectionDeleteResponse,
    responses=errors(404, 409, 412),
    dependencies=[superseded_by_v1("DELETE /collections/{collection_id}")],
)
async def delete_collection(collection_id: str, expected_revision: str | None = None):
    """Delete a collection."""
    collection_service = get_collection_service()
    from src.content_references import ContentInUseError

    try:
        deleted = (
            collection_service.delete_collection(collection_id)
            if expected_revision is None
            else collection_service.delete_collection(collection_id, expected_revision=expected_revision)
        )
    except PageRevisionConflict as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except ContentInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Collection not found: {collection_id}")
    return CollectionDeleteResponse(id=collection_id)
