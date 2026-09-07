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
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """The single error body the API serves."""

    detail: str


#: Canonical description per status code, so sibling endpoints across domains
#: document the same failure the same way.
_DESCRIPTIONS: dict[int, str] = {
    400: "Invalid request — the payload references something that does not exist or violates a rule.",
    403: "Forbidden.",
    404: "Resource not found.",
    409: "Conflict — duplicate id, or a resource pinned by the environment.",
    422: "Request body failed validation.",
    503: "A required dependency is unavailable.",
}


def errors(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Build the ``responses=`` block for the given failure codes."""
    unknown = [code for code in status_codes if code not in _DESCRIPTIONS]
    if unknown:
        raise ValueError(f"No canonical description for status code(s) {unknown}; add one to src/api_errors.py")
    return {code: {"model": ErrorResponse, "description": _DESCRIPTIONS[code]} for code in status_codes}
