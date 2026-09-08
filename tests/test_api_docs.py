"""Tests for the API's OpenAPI / Swagger UI exposure.

The FiestaBoard API is served behind nginx at the ``/api/*`` prefix, so when
visiting ``/api/docs`` the embedded Swagger UI must reference
``/api/openapi.json`` (not ``/openapi.json``) for the spec to load.
"""

from fastapi.testclient import TestClient

from src.api_server import app
from src.v1.visibility import build_internal_openapi


def test_app_has_api_root_path():
    """FastAPI's root_path must be /api so docs reference /api/openapi.json."""
    assert app.root_path == "/api"


def test_openapi_json_served():
    """The OpenAPI schema is served by the backend at /openapi.json."""
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    body = response.json()
    assert body.get("info", {}).get("title") == "FiestaBoard Display API"


def test_docs_page_references_prefixed_openapi_url():
    """Swagger UI HTML must point at /api/openapi.json so it loads via nginx."""
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200
    # Swagger UI is configured with the prefixed openapi URL.
    assert "/api/openapi.json" in response.text


def _operation_ids(schema: dict) -> list[str]:
    ids = []
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict) and "operationId" in operation:
                ids.append(operation["operationId"])
    return ids


def test_openapi_schema_has_unique_operation_ids():
    """Every operationId in the schema must be unique.

    A route registered with @app.api_route(methods=["GET", "HEAD"]) collapses
    to a single APIRoute whose unique_id is computed once (not once per HTTP
    method), so FastAPI's default generate_unique_id emits the same
    operationId for both the GET and HEAD operations. Duplicate operationIds
    break OpenAPI client generators (openapi-generator, orval, etc.), which
    key off operationId to name generated methods.

    Checked on the **internal** document. A collision needs two routes to
    collide, and the published document has 33 of the app's ~230 operations —
    checking it would leave the other ~197 unchecked while still passing.
    """
    schema = build_internal_openapi(app)

    ids = _operation_ids(schema)
    assert len(ids) > 200, "the internal document should carry the whole surface"
    duplicates = {op_id for op_id in ids if ids.count(op_id) > 1}
    assert not duplicates, f"Duplicate operationId(s): {sorted(duplicates)}"


def test_openapi_schema_operation_ids_are_deterministic():
    """The schema must not depend on Python set-iteration order.

    route.methods is a set, so a default generate_unique_id that reads
    list(route.methods)[0] can pick GET one process run and HEAD the next.
    Rebuilding the schema must produce the same operationId for the /health
    route every time. ``/health`` is internal, so the internal document is
    where it can be read.
    """
    first = build_internal_openapi(app)
    second = build_internal_openapi(app)

    first_health_ids = sorted(
        op.get("operationId") for op in first["paths"]["/health"].values() if isinstance(op, dict)
    )
    second_health_ids = sorted(
        op.get("operationId") for op in second["paths"]["/health"].values() if isinstance(op, dict)
    )
    assert first_health_ids == second_health_ids


def test_the_internal_schema_is_served_at_its_documented_path():
    """``/check-types`` and the web contract both fetch it by this URL."""
    response = TestClient(app).get("/internal/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "FiestaBoard Internal API"
