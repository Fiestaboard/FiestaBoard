"""The flat board fields are deprecated, still served, through v10.

Settings v4 (plan D8) moved a Vestaboard's connection into the board's
``output_config``; the API still projects the old flat fields (``api_mode``,
``host``, ``port``, ``local_api_key``, ``cloud_key``, ``note_array_token``,
``tiles``) so no integration broke. They stay through v10 and are removed in
v11. Pinned here, with no change of behaviour:

- every HTTP operation that serves them says so on the wire: ``Deprecation:
  true`` plus a ``Link`` to the notice (``rel="deprecation"``, RFC 9745), and
  no ``Sunset`` (v11 has no date yet; ``src/api_deprecation.py``);
- the OpenAPI schema marks the typed flat fields ``deprecated: true``, and
  the untyped board entries say which of their keys are deprecated;
- the fields are still in the responses, unchanged.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api_deprecation import (
    FLAT_BOARD_FIELDS,
    FLAT_BOARD_FIELDS_DOC,
    FLAT_BOARD_FIELDS_REMOVAL,
)
from src.api_server import app
from src.v1.visibility import build_internal_openapi, iter_api_routes

#: Every operation that serves a flat board field.
SERVING_FLAT_FIELDS = {
    "GET /settings/board",
    "PUT /settings/board",
    "POST /settings/board/add",
    "DELETE /settings/board/{board_id}",
    "GET /board/current-message",
    "GET /config",
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _flagged_operations() -> set[str]:
    found: set[str] = set()
    for path, route in iter_api_routes(app.routes):
        for dependency in route.dependencies or []:
            if getattr(dependency.dependency, "deprecated_fields", None) is not None:
                found |= {f"{m} {path}" for m in set(route.methods or ()) - {"HEAD", "OPTIONS"}}
    return found


def test_the_deprecated_fields_and_their_removal_release_are_named_once():
    assert FLAT_BOARD_FIELDS == ("api_mode", "host", "port", "local_api_key", "cloud_key", "note_array_token", "tiles")
    assert FLAT_BOARD_FIELDS_REMOVAL == "v11"


def test_every_operation_serving_them_carries_the_notice():
    assert _flagged_operations() == SERVING_FLAT_FIELDS


def test_the_board_settings_read_says_so_and_still_serves_the_fields(client):
    response = client.get("/settings/board")
    assert response.status_code == 200, response.text
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Link"] == f'<{FLAT_BOARD_FIELDS_DOC}>; rel="deprecation"'
    assert "Sunset" not in response.headers
    (board,) = response.json()["boards"]
    assert "api_mode" in board


def test_the_config_summary_says_so_and_still_serves_the_fields(client):
    response = client.get("/config")
    assert response.status_code == 200, response.text
    assert response.headers["Deprecation"] == "true"
    assert {"board_api_mode", "board_host", "board_key_set"} <= set(response.json())


@pytest.mark.parametrize(
    ("model", "fields"),
    [
        ("BoardCurrentMessageResponse", ["api_mode"]),
        ("ConfigSummaryResponse", ["board_api_mode", "board_host", "board_key_set"]),
    ],
)
def test_the_schema_marks_the_typed_flat_fields_deprecated(model, fields):
    properties = build_internal_openapi(app)["components"]["schemas"][model]["properties"]
    for field in fields:
        assert properties[field].get("deprecated") is True, field


def test_the_schema_names_the_deprecated_keys_of_a_board_entry():
    boards = build_internal_openapi(app)["components"]["schemas"]["BoardSettingsResponse"]["properties"]["boards"]
    description = boards["description"]
    assert description.lower().count("deprecated") and FLAT_BOARD_FIELDS_REMOVAL in description
    for field in FLAT_BOARD_FIELDS:
        assert f"`{field}`" in description
