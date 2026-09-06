"""FastAPI router for the collection endpoints.

Handlers moved verbatim from ``src/api_server.py`` (issue #1756, pure move).
Names that still live in ``api_server`` — the service getters and the
template engine accessor — are imported *inside* each handler so they
resolve through the api_server module at call time. The test-suite patches
them as ``src.api_server.<name>``; a module-level import would both create
an import cycle (api_server imports this router) and detach the moved
handlers from those patches.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .models import CollectionCreate, CollectionUpdate

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
    from src.api_server import get_template_engine  # patched-in-tests seam — see module docstring (#1756)

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

    from src.templates.expressions import validate_expression

    template_engine = get_template_engine()
    known_sources = template_engine._get_all_known_sources()
    for idx, rule in enumerate(variable.rules):
        issues = validate_expression(rule.expression, known_sources=known_sources)
        if issues:
            first = issues[0]
            raise HTTPException(
                status_code=400,
                detail=(f"Variable rule {idx} expression invalid: {first.code} {first.message}"),
            )


@router.get("/collections")
async def list_collections():
    """List all collections."""
    from src.api_server import get_collection_service  # patched-in-tests seam — see module docstring (#1756)

    collection_service = get_collection_service()
    collections = collection_service.list_collections()
    return {
        "collections": [c.model_dump() for c in collections],
        "total": len(collections),
    }


@router.post("/collections")
async def create_collection(data: CollectionCreate):
    """Create a new collection."""
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        get_collection_service,
        get_page_service,
    )

    collection_service = get_collection_service()
    page_service = get_page_service()

    _validate_collection_payload(data, page_service)

    try:
        collection = collection_service.create_collection(data)
        return {"status": "success", "collection": collection.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/collections/{collection_id}")
async def get_collection(collection_id: str):
    """Get a collection by ID."""
    from src.api_server import get_collection_service  # patched-in-tests seam — see module docstring (#1756)

    collection_service = get_collection_service()
    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection not found: {collection_id}")
    return collection.model_dump()


@router.put("/collections/{collection_id}")
async def update_collection(collection_id: str, data: CollectionUpdate):
    """Update an existing collection."""
    from src.api_server import (  # patched-in-tests seam — see module docstring (#1756)
        get_collection_service,
        get_page_service,
    )

    collection_service = get_collection_service()
    page_service = get_page_service()

    _validate_collection_payload(data, page_service, require_pages=False)

    try:
        collection = collection_service.update_collection(collection_id, data)
        if not collection:
            raise HTTPException(status_code=404, detail=f"Collection not found: {collection_id}")
        return {"status": "success", "collection": collection.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/collections/{collection_id}")
async def delete_collection(collection_id: str):
    """Delete a collection."""
    from src.api_server import get_collection_service  # patched-in-tests seam — see module docstring (#1756)

    collection_service = get_collection_service()
    deleted = collection_service.delete_collection(collection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Collection not found: {collection_id}")
    return {"status": "success", "message": f"Collection {collection_id} deleted"}
