"""``errors()`` publishes the body each status code actually sends.

Regression for #1923: ``errors()`` attached ``ErrorResponse`` —
``{"detail": <string>}`` — to *every* declared code, including 422. But 422 is
FastAPI's own request-schema rejection, whose ``detail`` is a **list** of
``{loc, msg, type}`` objects. Declaring ``errors(422)`` therefore overrode
FastAPI's ``HTTPValidationError`` with a model that lied about the shape, so
the published schema disagreed with what the endpoint sends (and with the web
client, which #1920 moved onto the real list shape).

These tests pin the fix at two levels: the helper maps 422 to
``HTTPValidationError`` and everything else to ``ErrorResponse``, and the
live OpenAPI schema serves a *list*-shaped 422 on a route whose only 422 is
FastAPI validation.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from src.api_errors import ErrorResponse, HTTPValidationError, errors
from src.api_server import app


def test_errors_maps_422_to_http_validation_error():
    """422 publishes the list-shaped HTTPValidationError, not ErrorResponse."""
    assert errors(422)[422]["model"] is HTTPValidationError


def test_errors_maps_non_422_codes_to_error_response():
    """Every hand-raised code keeps the single-string ErrorResponse body."""
    block = errors(400, 404, 500)
    assert {code: entry["model"] for code, entry in block.items()} == {
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    }


def test_errors_mixes_the_two_models_in_one_block():
    """A route declaring 422 alongside hand-raised codes gets both models."""
    block = errors(400, 422, 500)
    assert block[400]["model"] is ErrorResponse
    assert block[422]["model"] is HTTPValidationError
    assert block[500]["model"] is ErrorResponse


def test_http_validation_error_detail_is_a_list():
    """The published 422 model carries a list, matching FastAPI's real body."""
    schema = HTTPValidationError.model_json_schema()
    assert schema["properties"]["detail"]["type"] == "array"


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Follow a ``$ref`` into ``components/schemas`` (one hop is enough here)."""
    ref = node.get("$ref")
    if not ref:
        return node
    name = ref.rsplit("/", 1)[-1]
    return schema["components"]["schemas"][name]


def _detail_type(schema: dict[str, Any], response: dict[str, Any]) -> str:
    """The JSON type of ``detail`` in a response's declared body model."""
    body = response["content"]["application/json"]["schema"]
    model = _resolve(schema, body)
    return model["properties"]["detail"]["type"]


def _openapi() -> dict[str, Any]:
    app.openapi_schema = None  # bypass FastAPI's cached build
    return TestClient(app).get("/openapi.json").json()


def test_openapi_serves_list_shaped_422_on_a_validation_only_route():
    """POST /pages/preview/batch's only 422 is FastAPI's — schema must show a list.

    Before the fix this resolved to ErrorResponse (``detail`` a string); a
    generated client would deserialize the real list body against the wrong
    shape.
    """
    schema = _openapi()
    response_422 = schema["paths"]["/pages/preview/batch"]["post"]["responses"]["422"]
    assert _detail_type(schema, response_422) == "array"


def test_openapi_keeps_string_shaped_body_on_hand_raised_codes():
    """A hand-raised code (400 on POST /pages/import) still publishes a string."""
    schema = _openapi()
    response_400 = schema["paths"]["/pages/import"]["post"]["responses"]["400"]
    assert _detail_type(schema, response_400) == "string"
