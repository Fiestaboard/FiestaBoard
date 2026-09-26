"""Hiding 198 operations is a documentation change and nothing else.

Measured on ``next`` @ ``a7c84ce13``: the app published **231 operations**,
179 of which have no caller outside ``web/src``, and **not one route** used
``include_in_schema=False``. ``src/v1/visibility.py`` takes everything that is
not ``/v1`` — and not one of the two legacy operations the published docs name
— out of the published document, leaving **33**.

The failure mode that would make that a disaster rather than an improvement is
a hidden route that also stops *answering*. ``include_in_schema`` is read when
the OpenAPI document is built and nowhere in the request path, so it cannot —
but "cannot" is the claim, and this file is the evidence. It calls hidden
routes and compares the answers against the same routes' recorded contracts,
rather than asserting the attribute means what the docs say it means.

The second failure mode is quieter: a schema test that goes green because it
now checks nothing. Two guards below (``test_the_published_document_is_not_
trivially_empty`` and ``test_the_internal_document_is_not_a_copy_of_the_public
_one``) exist to make that visible rather than silent.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.v1.visibility import (
    INTERNAL_SCHEMA_PATH,
    PUBLIC_LEGACY_OPERATIONS,
    build_internal_openapi,
    is_consumer_operation,
    iter_api_routes,
)

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})

#: The contract the whole change rests on.
EXPECTED_PUBLISHED_OPERATIONS = 33


def _operations(schema: dict) -> set[str]:
    return {
        f"{method.upper()} {path}"
        for path, operations in schema["paths"].items()
        for method in operations
        if method in _HTTP_METHODS
    }


@pytest.fixture
def client(_isolated_data_dir) -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def published() -> dict:
    return app.openapi()


@pytest.fixture(scope="module")
def internal() -> dict:
    return build_internal_openapi(app)


# ---------------------------------------------------------------------------
# 1. The number
# ---------------------------------------------------------------------------


def test_a_consumer_sees_exactly_thirty_three_operations(published):
    """231 -> 33. A 34th is a decision, not a side effect."""
    assert len(_operations(published)) == EXPECTED_PUBLISHED_OPERATIONS


def test_every_published_operation_is_v1_or_one_of_the_two_named_exceptions(published):
    strays = sorted(
        operation
        for operation in _operations(published)
        if not operation.split(" ", 1)[1].startswith("/v1")
        and tuple(operation.split(" ", 1)) not in PUBLIC_LEGACY_OPERATIONS
    )
    assert strays == []


def test_the_two_legacy_operations_the_published_docs_name_are_still_published(published):
    """``docs/reference/api-endpoints.md`` tells readers to call these two.

    Hiding them would break a documented path for someone following the docs
    exactly as written, which is the one group this change exists to serve.
    """
    operations = _operations(published)
    for method, path in PUBLIC_LEGACY_OPERATIONS:
        assert f"{method} {path}" in operations


def test_the_published_document_is_not_trivially_empty(published):
    """Guard the guard: an import failure must not read as 'nicely small'."""
    assert len(_operations(published)) > 30
    assert "/v1/boards/{board}/message" in published["paths"]


# ---------------------------------------------------------------------------
# 2. Hidden is not gone — the routes
# ---------------------------------------------------------------------------


#: One hidden route per shape of thing that could have broken: a plain read, a
#: read behind a path parameter, a write with a body, a 404 path, and one of
#: the eleven deprecated routes. Each expectation is the answer the route gives
#: on ``next``; none of them is "some 2xx".
HIDDEN_ROUTES_AND_THEIR_ANSWERS = [
    ("GET", "/health", 200),
    ("GET", "/status", 200),
    ("GET", "/pages", 200),
    ("GET", "/settings/board", 200),
    ("GET", "/plugins", 200),
    ("GET", "/config/general", 200),
    ("GET", "/schedules", 200),
    ("GET", "/collections", 200),
    ("GET", "/templates/formula-functions", 200),
    ("GET", "/pages/no-such-page", 404),
]


@pytest.mark.parametrize(("method", "path", "expected_status"), HIDDEN_ROUTES_AND_THEIR_ANSWERS)
def test_a_hidden_route_still_answers_exactly_as_before(client, method, path, expected_status):
    response = client.request(method, path)
    assert response.status_code == expected_status, response.text


@pytest.mark.parametrize(("method", "path", "_status"), HIDDEN_ROUTES_AND_THEIR_ANSWERS)
def test_every_route_this_file_calls_is_actually_hidden(published, method, path, _status):
    """Otherwise the parametrization above proves nothing about hiding."""
    assert f"{method} {path}" not in _operations(published)


def test_a_hidden_route_returns_the_same_body_it_documents(client, internal):
    """A hidden route's *shape* is unchanged, not merely its status code."""
    body = client.get("/templates/formula-functions").json()
    assert isinstance(body, dict)
    assert "functions" in body
    assert body["functions"], "the function catalogue must not have come back empty"
    assert "/templates/formula-functions" in internal["paths"]


# ---------------------------------------------------------------------------
# 3. Hidden is not gone — the document
# ---------------------------------------------------------------------------


def test_the_internal_document_is_served(client):
    response = client.get(INTERNAL_SCHEMA_PATH)
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "FiestaBoard Internal API"


def test_the_internal_document_carries_every_operation_the_app_serves(internal):
    """Every ``APIRoute`` in the live table, hidden or not, is in it."""
    served = {
        f"{method} {path}"
        for path, route in iter_api_routes(app.routes)
        for method in (route.methods or ())
        if method.lower() in _HTTP_METHODS and method != "HEAD"
    }
    assert served - _operations(internal) == set()


def test_the_internal_document_is_not_a_copy_of_the_public_one(published, internal):
    """The whole point: it has the operations the published one dropped."""
    assert len(_operations(internal)) > 200
    assert _operations(published) <= _operations(internal)


def test_the_internal_document_says_it_is_not_a_consumer_api(internal):
    """A second published surface with no warning is a second public API."""
    description = internal["info"]["description"]
    assert "Not a consumer API" in description
    assert "/v1" in description


def test_building_the_internal_document_does_not_change_the_published_one(client):
    """It reads the route table; it must not write to it.

    The obvious implementation — flip ``include_in_schema`` back on, build,
    flip it off — would make the published schema depend on whether anyone had
    recently fetched the internal one. This pins that it does not.
    """
    before = _operations(client.get("/openapi.json").json())
    client.get(INTERNAL_SCHEMA_PATH)
    after = _operations(client.get("/openapi.json").json())
    assert after == before == _operations(app.openapi())


def test_the_internal_document_is_readable_without_a_session(client):
    """``/check-types`` fetches it with plain curl, as it did ``/openapi.json``.

    Gating it would be a new restriction dressed up as a refactor: this is
    exactly what ``/openapi.json`` published, publicly, before the internal
    surface was hidden.
    """
    from src.auth.middleware import _is_public_path

    assert _is_public_path(INTERNAL_SCHEMA_PATH)


# ---------------------------------------------------------------------------
# 4. The rule that decides visibility
# ---------------------------------------------------------------------------


def test_the_sweep_covered_the_whole_route_table():
    """Every APIRoute is now classified — no route escaped the walk.

    The walk has to recurse through FastAPI's ``_IncludedRouter`` nodes to see
    routes at all. A walk that silently stopped at the top level would hide
    eleven routes, publish 220, and this is what notices.
    """
    routes = list(iter_api_routes(app.routes))
    assert len(routes) > 200
    hidden = [route for path, route in routes if not is_consumer_operation(path, route)]
    published_by_route = [route for path, route in routes if is_consumer_operation(path, route)]

    assert all(not route.include_in_schema for route in hidden)
    assert all(route.include_in_schema for route in published_by_route)
    assert len(hidden) > 190


def test_hiding_is_idempotent():
    """It runs at import; a second call (a test app factory) must be a no-op."""
    from src.v1.visibility import hide_internal_operations

    first = len(hide_internal_operations(app))
    second = len(hide_internal_operations(app))
    assert first == second
    assert len(_operations(app.openapi())) == EXPECTED_PUBLISHED_OPERATIONS


# ---------------------------------------------------------------------------
# 5. The two that stayed visible say what they are
# ---------------------------------------------------------------------------


class _FakeBoardClient:
    """A board client that records what was rendered, with real attributes.

    Not a ``Mock``: the handler's throttle guard reads ``last_send_throttled``
    with an ``is True`` check precisely so a Mock's truthy attributes do not
    put every send on the 429 path.
    """

    def __init__(self):
        self.rendered: list = []
        self.last_send_throttled = False
        self.min_send_interval_ms = 0
        self.use_cloud = False
        self._last_characters = None
        self.skip_unchanged = True

    def render(self, board_array, **kwargs):
        self.rendered.append(board_array)
        return True, True


@pytest.fixture
def sendable(_isolated_data_dir):
    """A one-board install whose send path reaches a 200.

    The deprecation headers are set by a FastAPI dependency, so they ride on
    the *response*. A route that raises ``HTTPException`` never builds one —
    which is why this fixture exists rather than asserting against the 409 an
    unconfigured install gives.
    """
    from unittest.mock import Mock, patch

    board = {"id": "board-primary", "device_type": "flagship", "notes_wide": 1, "notes_tall": 1}
    board_client = _FakeBoardClient()

    service = Mock()
    service.vb_client = board_client
    service.get_board_client = lambda board_id: board_client
    service.request_board_refresh = Mock()
    service.mark_showing_out_of_band = Mock()

    settings_service = Mock()
    board_settings = Mock()
    board_settings.boards = [board]
    settings_service.get_board_settings.return_value = board_settings
    settings_service.get_primary_board_id.return_value = "board-primary"
    settings_service.is_paused.return_value = False
    transition = Mock()
    transition.strategy = None
    transition.step_interval_ms = 0
    transition.step_size = 1
    settings_service.get_transition_settings.return_value = transition

    with (
        patch("src.display_runtime.get_service", return_value=service),
        patch("src.display_runtime.peek_service", return_value=service),
        patch("src.display_runtime.get_settings_service", return_value=settings_service),
        patch("src.board_guards.get_settings_service", return_value=settings_service),
        patch("src.board_guards.Config.is_silence_mode_active", return_value=False),
        patch("src.display_runtime._publish_mqtt_state_update"),
    ):
        yield TestClient(app)


def test_send_message_advertises_its_v1_successor_on_the_wire(sendable):
    """A caller following the old docs learns where the new door is.

    The header, not the schema, because the callers this matters for — a cron
    job, a shell script, someone's Home Assistant automation — never open
    Swagger. That is the same reasoning #1932 recorded for the eleven
    deprecated plugin routes, and it reuses that machinery.
    """
    response = sendable.post("/send-message", json={"text": "HELLO"})

    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Link"] == '</api/v1/boards/{board}/message>; rel="successor-version"'


def test_send_message_carries_no_sunset(sendable):
    """No removal date has been agreed for it, so none is announced.

    An unbacked ``Sunset`` teaches integrators that the header is noise, which
    costs more than the eleven routes that do carry a real one gain.
    """
    response = sendable.post("/send-message", json={"text": "HELLO"})
    assert "Sunset" not in response.headers


@pytest.mark.parametrize("path", ["/send-message", "/refresh"])
def test_the_kept_operations_are_flagged_deprecated_in_the_schema(published, path):
    """Prose and schema may not disagree — the rule #1932 established."""
    assert published["paths"][path]["post"]["deprecated"] is True


@pytest.mark.parametrize("path", ["/send-message", "/refresh"])
def test_the_kept_operations_name_their_successor_in_their_description(published, path):
    description = published["paths"][path]["post"]["description"]
    assert description.lstrip().lower().startswith("deprecated")
    assert "/v1/boards/{board}/message" in description
