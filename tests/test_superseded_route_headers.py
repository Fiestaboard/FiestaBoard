"""The 25 internal endpoints ``/v1`` supersedes announce their removal.

#1934 moved every web-client call that ``/v1`` supersedes onto ``/v1``, which
left 33 internal endpoints with no product caller. #1936 then closed five of
the ten places where a v1 route dropped something its internal twin carried.
Twenty-five of the 33 survive both a caller audit and an exactness audit; they
are the cohort :data:`src.api_deprecation.SUPERSEDED_BY_V1` names, and #1941
tracks their deletion.

They are already ``include_in_schema=False`` (#1935), so the notice is
deliberately invisible in the published document — the audience is a caller
who is already calling them, and the only place such a caller looks is the
response it is already reading. That makes an over-the-wire assertion the
*only* assertion worth making here: a test that read the decorator would pass
on a route whose headers never reach a response.

The eight excluded endpoints are as load-bearing as the twenty-five included
ones, so :func:`test_the_eight_endpoints_v1_does_not_fully_replace_send_no_notice`
pins them by name. A future change that "completes the set" has to delete that
test, which is where the reviewer will ask why.
"""

from __future__ import annotations

from email.utils import parsedate_to_datetime

import pytest
from fastapi.testclient import TestClient

from src.api_deprecation import SUPERSEDED_BY_V1, SUPERSEDED_BY_V1_SUNSET
from src.api_server import DEPRECATED_ROUTES_SUNSET, app
from src.v1.visibility import iter_api_routes


@pytest.fixture
def client() -> TestClient:
    """A client without the app lifespan.

    None of these routes need anything the lifespan starts, and starting it
    costs ~11 seconds of service/registry/mDNS boot per test.
    """
    return TestClient(app)


def _wired_notices() -> dict[str, tuple[str | None, str | None]]:
    """``"<METHOD> <path>"`` -> ``(successor_uri, sunset)`` for the live app.

    Read off the route table rather than off the table in
    ``src/api_deprecation.py``, so the two can be compared against each other.
    """
    found: dict[str, tuple[str | None, str | None]] = {}
    for path, route in iter_api_routes(app.routes):
        for dependency in route.dependencies or []:
            if getattr(dependency.dependency, "superseded_operation", None) is None:
                continue
            for method in sorted(set(route.methods or ()) - {"HEAD", "OPTIONS"}):
                found[f"{method} {path}"] = (
                    dependency.dependency.successor_uri,
                    dependency.dependency.sunset,
                )
    return found


def test_every_operation_in_the_table_carries_the_notice():
    """The table is the cohort; a route that drops out must drop out of both."""
    assert sorted(_wired_notices()) == sorted(SUPERSEDED_BY_V1)


def test_no_route_carries_a_notice_the_table_does_not_name():
    """A decorator added without a table entry is an unreviewed deprecation."""
    for operation, (successor, sunset) in sorted(_wired_notices().items()):
        assert successor == SUPERSEDED_BY_V1[operation]
        assert sunset == SUPERSEDED_BY_V1_SUNSET


def test_no_v1_route_announces_its_own_removal():
    """The successors must never carry the notice — that would be circular."""
    assert not [operation for operation in _wired_notices() if " /v1" in operation]


@pytest.mark.parametrize("operation,successor", sorted(SUPERSEDED_BY_V1.items()))
def test_each_successor_is_an_operation_this_app_actually_serves(operation, successor):
    """A ``successor-version`` link to a path that does not exist is worse than none.

    ``/api`` is stripped by nginx, so the served path is the link minus that
    prefix.
    """
    served = {path for path, _ in iter_api_routes(app.routes)}
    assert successor.startswith("/api/v1/"), operation
    assert successor.removeprefix("/api") in served, f"{operation} -> {successor}"


def test_the_sunset_is_a_valid_http_date():
    """``Sunset`` is an HTTP-date (RFC 8594 §3); a free-form string is unusable."""
    parsed = parsedate_to_datetime(SUPERSEDED_BY_V1_SUNSET)
    assert parsed.tzinfo is not None
    assert (parsed.year, parsed.month, parsed.day) == (2026, 12, 1)


def test_the_cohort_shares_the_clock_the_plugin_routes_already_started():
    """One appliance, one removal date.

    A second date a few weeks from the first would mean an integrator has to
    track two countdowns to learn when their script stops working.
    """
    assert SUPERSEDED_BY_V1_SUNSET == DEPRECATED_ROUTES_SUNSET


# ---------------------------------------------------------------------------
# Over the wire
# ---------------------------------------------------------------------------

#: ``(method, path, status, body)`` for the reads that answer deterministically
#: on an empty install. The bodies are what unmodified ``next`` answers,
#: captured before the dependencies were added and pinned verbatim: this is the
#: "behaviour must not change" half of the contract, and it is worthless unless
#: the expected value came from the tree without the change in it.
UNCHANGED_READS = [
    ("GET", "/pages", 200, {"pages": [], "total": 0}),
    ("GET", "/collections", 200, {"collections": [], "total": 0}),
    (
        "GET",
        "/schedules",
        200,
        {"schedules": [], "total": 0, "default_page_id": None, "enabled": False},
    ),
    (
        "GET",
        "/plugins/variables/all",
        200,
        {"variables": {}, "max_lengths": {}, "plugin_system_enabled": True},
    ),
]


@pytest.mark.parametrize("method,path,status,body", UNCHANGED_READS)
def test_a_superseded_route_answers_exactly_as_before_and_says_so(client, method, path, status, body):
    """Same status, same body, plus three headers. Nothing else changed."""
    response = client.request(method, path)

    assert response.status_code == status, response.text
    assert response.json() == body

    assert response.headers["Deprecation"] == "true"
    assert response.headers["Sunset"] == SUPERSEDED_BY_V1_SUNSET
    assert response.headers["Link"] == f'<{SUPERSEDED_BY_V1[f"{method} {path}"]}>; rel="successor-version"'


def _create_page(client: TestClient) -> str:
    """A saved page, so the collection write below has a member to point at."""
    created = client.post(
        "/pages",
        json={"name": "notice", "type": "template", "template": ["HELLO"]},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_the_notice_reaches_a_write_and_leaves_its_body_alone(client):
    """A ``Depends`` on a POST/DELETE is a different code path from a GET.

    ``POST /pages`` also answers 201 rather than 200, which is the case where
    a header stamped on the injected ``Response`` is easiest to lose.
    """
    page_id = _create_page(client)

    created = client.post("/collections", json={"name": "notice", "page_ids": [page_id]})
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "notice"
    assert created.json()["page_ids"] == [page_id]
    assert created.headers["Deprecation"] == "true"
    assert created.headers["Sunset"] == SUPERSEDED_BY_V1_SUNSET
    assert created.headers["Link"] == '</api/v1/collections>; rel="successor-version"'

    collection_id = created.json()["id"]
    deleted = client.delete(f"/collections/{collection_id}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.headers["Deprecation"] == "true"
    assert deleted.headers["Link"] == '</api/v1/collections/{collection_id}>; rel="successor-version"'


def test_a_successor_link_is_readable_as_a_uri_template(client):
    """RFC 6570 templating is deliberate on a parameterised successor.

    The replacement for a route with a path parameter is itself parameterised,
    and a ``Link`` naming a resource cannot fill the parameter in for the
    caller — so the template is what gets sent, unsubstituted.
    """
    page_id = _create_page(client)

    response = client.get(f"/pages/{page_id}")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == page_id
    assert response.headers["Link"] == '</api/v1/pages/{page_id}>; rel="successor-version"'


def test_a_refusal_carries_no_notice__inherited_limitation(client):
    """Pinning what this mechanism does *not* do, so it is not mistaken for a bug.

    ``deprecation_notice`` stamps the ``Response`` FastAPI injects into the
    handler, and FastAPI merges that object's headers only into a response it
    builds from a returned value. An ``HTTPException`` is answered by the
    exception handler from a fresh response, so the notice is dropped.

    The eleven plugin-specific routes (#1932) behave identically; this is the
    shared mechanism's behaviour, not this cohort's. It costs little — a
    caller that gets a 404 is being told something more urgent than "this is
    going away" — but a caller who only ever sees errors never sees the
    notice, which is recorded on #1941 as the one thing this PR leaves open.
    """
    response = client.get("/pages/no-such-page")
    assert response.status_code == 404
    assert "Deprecation" not in response.headers


#: The eight of #1934's thirty-three that are **not** deprecated, and the fact
#: each one's v1 equivalent still drops. Deprecating one of these would tell a
#: caller to follow a link that loses data.
NOT_SUPERSEDED = {
    "POST /pages/{page_id}/send": "drops paused/target; a paused board is a 409 on v1, not a 200",
    "POST /displays/{display_type}/send": "no v1 write form accepts a plugin id at all",
    "GET /schedules/enabled": "answers for the install with no board named; v1 has no board-less form",
    "PUT /schedules/enabled": "same, and 404s where this falls back to the global mirror",
    "GET /schedules/default-page": "answers for the install with no board named",
    "PUT /schedules/default-page": "same, and 404s on an install with no boards",
    "GET /displays": "drops source; 503s where this answers 200 with an empty list",
    "POST /settings/board/{board_id}/pause": "drops the embedded board_settings block",
}


@pytest.mark.parametrize("operation", sorted(NOT_SUPERSEDED))
def test_the_eight_endpoints_v1_does_not_fully_replace_send_no_notice(operation):
    """Excluded on purpose, and the exclusions are the reviewable half."""
    assert operation not in SUPERSEDED_BY_V1, NOT_SUPERSEDED[operation]
    assert operation not in _wired_notices()


def test_a_route_kept_on_the_internal_surface_sends_nothing(client):
    """``GET /displays`` is in #1934's thirty-three and deliberately not here.

    It is the control for the whole change: if the notice had been applied by
    sweeping a path prefix rather than by an audited list, this route would
    carry it.
    """
    response = client.get("/displays")
    assert response.status_code == 200, response.text
    assert "Deprecation" not in response.headers
    assert "Sunset" not in response.headers
