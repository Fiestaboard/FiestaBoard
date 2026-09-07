"""Tests for the API's OpenAPI / Swagger UI exposure.

The FiestaBoard API is served behind nginx at the ``/api/*`` prefix, so when
visiting ``/api/docs`` the embedded Swagger UI must reference
``/api/openapi.json`` (not ``/openapi.json``) for the spec to load.
"""

from fastapi.testclient import TestClient

from src.api_server import app


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
    """
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    ids = _operation_ids(schema)
    duplicates = {op_id for op_id in ids if ids.count(op_id) > 1}
    assert not duplicates, f"Duplicate operationId(s) in /openapi.json: {sorted(duplicates)}"


def test_openapi_schema_operation_ids_are_deterministic():
    """The schema must not depend on Python set-iteration order.

    route.methods is a set, so a default generate_unique_id that reads
    list(route.methods)[0] can pick GET one process run and HEAD the next.
    Rebuilding the schema (as FastAPI does lazily, cached on app.openapi_schema)
    must produce the same operationId for the /health route every time.
    """
    client = TestClient(app)

    # Force a fresh schema build each time, bypassing FastAPI's cache, so we
    # actually re-exercise generate_unique_id rather than reading a cached dict.
    app.openapi_schema = None
    first = client.get("/openapi.json").json()
    app.openapi_schema = None
    second = client.get("/openapi.json").json()

    first_health_ids = sorted(
        op.get("operationId") for op in first["paths"]["/health"].values() if isinstance(op, dict)
    )
    second_health_ids = sorted(
        op.get("operationId") for op in second["paths"]["/health"].values() if isinstance(op, dict)
    )
    assert first_health_ids == second_health_ids
