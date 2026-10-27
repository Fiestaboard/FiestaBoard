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


# --- #2367: /api/docs must reach every route, not only the 36 published ones ---
#
# Since v9.0.0 (#1935) ``/api/openapi.json`` publishes only ``/v1`` plus two
# legacy operations, deliberately. The rest moved to
# ``/api/internal/openapi.json``, but Swagger UI at ``/api/docs`` could only
# load the first, so ~200 working routes were invisible on the docs page and
# the one pointer to them was a sentence in the description. These tests pin
# that the docs page offers both documents, public first.

#: Route groups a v8 user browsed in /api/docs. Each is a path the web UI
#: calls today, so the internal document must keep carrying them.
KEY_INTERNAL_ROUTE_GROUPS = (
    "/pages",
    "/plugins",
    "/schedules",
    "/collections",
    "/settings",
    "/displays",
    "/templates",
    "/system",
)


def _docs_definitions() -> list[dict]:
    """The ``urls`` list Swagger UI at ``/docs`` is configured with."""
    import json
    import re

    response = TestClient(app).get("/docs")
    assert response.status_code == 200
    match = re.search(r'"urls": (\[.*?\]),\n', response.text)
    assert match, "Swagger UI at /docs offers no definition selector (no `urls` config)"
    return json.loads(match.group(1))


def test_docs_page_offers_public_and_internal_documents():
    """The selector lists the published document and the internal one."""
    urls = [definition["url"] for definition in _docs_definitions()]
    assert urls == ["/api/openapi.json", "/api/internal/openapi.json"]


def test_docs_page_opens_on_the_public_document():
    """The consumer API stays the default; the internal one is opt-in."""
    response = TestClient(app).get("/docs")
    first = _docs_definitions()[0]
    assert f'"urls.primaryName": "{first["name"]}"' in response.text
    # `urls` is only rendered by the standalone layout's top bar.
    assert '"layout": "StandaloneLayout"' in response.text


def test_internal_document_is_labelled_as_unstable():
    """A reader picking it in the dropdown is told it carries no promise."""
    internal = _docs_definitions()[1]
    assert "internal" in internal["name"].lower()
    assert "unstable" in internal["name"].lower()


def test_docs_page_reaches_key_route_groups():
    """Every key route group is in a document the docs page can show."""
    client = TestClient(app)
    paths: set[str] = set()
    for definition in _docs_definitions():
        served = definition["url"].removeprefix(app.root_path)
        paths |= set(client.get(served).json()["paths"])
    missing = [group for group in KEY_INTERNAL_ROUTE_GROUPS if not any(p.startswith(group) for p in paths)]
    assert not missing, f"route groups unreachable from /docs: {missing}"
    assert len(paths) > 150, f"/docs reaches only {len(paths)} paths"


def test_docs_page_loads_the_standalone_preset_its_layout_needs():
    """``StandaloneLayout`` and its top bar ship in a separate script.

    FastAPI's page loads only ``swagger-ui-bundle.js`` and lists
    ``SwaggerUIBundle.SwaggerUIStandalonePreset``, which that bundle does not
    define. Asking for the layout without loading the preset renders
    'No layout defined for "StandaloneLayout"' and no operations at all,
    which a browser showed and the tests above did not.
    """
    html = TestClient(app).get("/docs").text
    preset = html.find("swagger-ui-standalone-preset.js")
    binding = html.find("SwaggerUIBundle.SwaggerUIStandalonePreset = SwaggerUIStandalonePreset")
    config = html.find("const ui = SwaggerUIBundle(")
    assert preset != -1, "the standalone preset script is never loaded"
    assert binding != -1, "the preset is never bound where the presets list reads it"
    assert preset < binding < config, "the preset must be loaded and bound before Swagger UI starts"
