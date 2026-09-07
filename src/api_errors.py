"""Shared error-response declarations for the domain routers.

Phase 2, spec §2: every converted domain serves **one** error contract —
FastAPI's ``{"detail": <string>}`` — and *declares* the failure codes it can
return so they appear in the OpenAPI schema and in the CI conventions ratchet
(``tests/test_api_conventions_ratchet.py``).

Usage in a router::

    from src.api_errors import errors

    @router.get("/things/{thing_id}", response_model=ThingResponse, responses=errors(404))
    async def get_thing(thing_id: str): ...

Declare only the codes a route can actually return. A route with no failure
path declares nothing and carries a checked-in exception in
``tests/conventions_manifest.json`` saying why.

Every declared code publishes :class:`ErrorResponse` except **422**, which is
FastAPI's own schema-validation failure and publishes
:class:`HTTPValidationError` (a list body) instead — see ``_model_for``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """The single error body the API serves."""

    detail: str


class ValidationError(BaseModel):
    """One entry in FastAPI's request-validation error list.

    Mirrors the ``ValidationError`` component FastAPI generates for schema
    rejections (same field names, so the two describe one component rather
    than two).
    """

    loc: list[str | int]
    msg: str
    type: str


class HTTPValidationError(BaseModel):
    """FastAPI's 422 body: a *list* of per-field validation errors.

    422 is not the ``{"detail": <string>}`` contract the rest of the API
    serves — it is the code FastAPI raises for request-schema rejection, whose
    ``detail`` is a list of ``{loc, msg, type}`` objects (see
    ``docs/internal/reference/API_CONVENTIONS.md`` §"422 belongs to FastAPI").
    Declaring ``errors(422)`` therefore has to publish *this* shape, not
    :class:`ErrorResponse`, so the schema matches what the endpoint sends.
    """

    detail: list[ValidationError] | None = None


#: Canonical description per status code, so sibling endpoints across domains
#: document the same failure the same way.
_DESCRIPTIONS: dict[int, str] = {
    400: "Invalid request — the payload references something that does not exist or violates a rule.",
    403: "Forbidden.",
    404: "Resource not found.",
    405: "The resource exists but does not implement this operation.",
    409: "Conflict — duplicate id, or a resource pinned by the environment.",
    422: "Request body failed validation.",
    429: "Rate-limited — the request arrived inside a minimum interval; see Retry-After.",
    500: "The server could not complete the operation. Deliberately raised, not an unhandled error.",
    501: "The resource declares this capability but does not implement it.",
    502: "An upstream the server called on your behalf failed.",
    503: "A required dependency is unavailable.",
    504: "An upstream the server called on your behalf did not answer in time.",
}


def _model_for(code: int) -> type[BaseModel]:
    """The response model a given status code publishes.

    Everything the API hand-raises is the ``{"detail": <string>}``
    :class:`ErrorResponse`. 422 is the one exception: it belongs to FastAPI's
    schema validation and carries a list body, so it publishes
    :class:`HTTPValidationError` instead. Attaching ``ErrorResponse`` to 422
    overrode FastAPI's own model with one that lies about the shape.
    """
    return HTTPValidationError if code == 422 else ErrorResponse


def errors(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Build the ``responses=`` block for the given failure codes."""
    unknown = [code for code in status_codes if code not in _DESCRIPTIONS]
    if unknown:
        raise ValueError(f"No canonical description for status code(s) {unknown}; add one to src/api_errors.py")
    return {code: {"model": _model_for(code), "description": _DESCRIPTIONS[code]} for code in status_codes}
