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
