"""The eleven deprecated plugin-specific routes announce their removal.

``deprecated=True`` on its own only greys the operation out in Swagger. These
routes exist *because* of callers this repo cannot see — two of them are
published as API reference in shipped plugin SETUP guides — and those callers
never open Swagger. Without the headers the deprecation is a note to
ourselves, and #1915's ~2,275-line deletion stays blocked indefinitely rather
than scheduled.

The successor map is pinned by value rather than exercised over the wire:
eleven live calls would mean eleven upstream APIs. One route
(``GET /stocks/search`` with no Finnhub key configured, which searches a
curated in-process list) is called for real, so the headers are proven to
reach an actual response and not just a decorator.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api_server import DEPRECATED_ROUTES_SUNSET, app

# path -> the plugin whose remote-options endpoint replaced it, or None where
# no successor exists yet. Every deprecated route in the app must appear here.
EXPECTED_SUCCESSORS = {
    "/baywheels/stations": "lyft_bike_share",
    "/baywheels/stations/nearby": "lyft_bike_share",
    "/baywheels/stations/search": "lyft_bike_share",
    "/muni/stops": "muni",
    "/muni/stops/nearby": "muni",
    "/muni/stops/search": "muni",
    "/transit/cache/status": None,
    "/stocks/search": "stocks",
    "/stocks/validate": "stocks",
    "/traffic/routes/geocode": "traffic",
    "/traffic/routes/validate": "traffic",
}


@pytest.fixture
def client() -> TestClient:
    """A client without the app lifespan.

    These routes need nothing the lifespan starts, and starting it costs ~11
    seconds of service/registry/mDNS boot per test.
    """
    return TestClient(app)


def _deprecated_routes():
    return [r for r in app.routes if getattr(r, "deprecated", False)]


def _successor_of(route) -> str | None:
    """The successor plugin id the route's deprecation dependency carries."""
    for dependency in route.dependencies:
        successor = getattr(dependency.dependency, "successor_plugin_id", "unset")
        if successor != "unset":
            return successor
    raise AssertionError(f"{route.path} is deprecated but declares no deprecation dependency")


def test_every_deprecated_route_is_in_the_successor_map():
    """A new deprecation must decide its successor, not inherit silence."""
    assert sorted({r.path for r in _deprecated_routes()}) == sorted(EXPECTED_SUCCESSORS)


@pytest.mark.parametrize("path,expected", sorted(EXPECTED_SUCCESSORS.items()))
def test_each_deprecated_route_points_at_its_successor(path, expected):
    routes = [r for r in _deprecated_routes() if r.path == path]
    assert routes, f"no deprecated route at {path}"
    for route in routes:
        assert _successor_of(route) == expected


def test_the_sunset_date_is_a_valid_http_date():
    """``Sunset`` is an HTTP-date (RFC 8594 §3); a free-form string is unusable."""
    from email.utils import parsedate_to_datetime

    parsed = parsedate_to_datetime(DEPRECATED_ROUTES_SUNSET)
    assert parsed.tzinfo is not None
    assert parsed.year == 2026 and parsed.month == 12 and parsed.day == 1


def test_a_deprecated_response_carries_the_headers(client):
    """End to end on the one route that answers without an upstream call."""
    response = client.get("/stocks/search", params={"query": "GOOG", "limit": 1})
    assert response.status_code == 200, response.text
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Sunset"] == DEPRECATED_ROUTES_SUNSET
    assert response.headers["Link"] == '</api/plugins/stocks/options/{options_id}>; rel="successor-version"'


def test_a_route_without_a_successor_sends_no_link(client):
    """A ``successor-version`` link to nothing is worse than no link."""
    response = client.get("/transit/cache/status")
    assert response.status_code == 200, response.text
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Sunset"] == DEPRECATED_ROUTES_SUNSET
    assert "Link" not in response.headers
