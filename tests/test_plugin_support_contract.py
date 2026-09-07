"""Value-level contract goldens for the plugin-support endpoints.

Phase 2 §2, Task 8. Thirteen platform routes exist that serve *individual
plugins* — the shape ``CLAUDE.md`` says must not live in ``src/`` at all.
This slice audited each one for a live consumer instead of converting them by
reflex:

============================================  ==========================================
route                                         verdict
============================================  ==========================================
``GET /home-assistant/entities``              **converted** — ``web/src/components/
                                              home-assistant-entity-picker.tsx``
``POST /generic-data/test-fetch``             **converted** — ``web/src/components/
                                              plugin-settings/json-path-mapper-field.tsx``
``GET /baywheels/stations{,/nearby,/search}`` deprecated — no UI consumer
``GET /muni/stops{,/nearby,/search}``         deprecated — no UI consumer
``GET /stocks/search``                        deprecated — no UI consumer
``POST /stocks/validate``                     deprecated — no UI consumer
``POST /traffic/routes/{geocode,validate}``   deprecated — no UI consumer
``GET /transit/cache/status``                 deprecated — no client of any kind
============================================  ==========================================

The eleven deprecated routes keep serving their exact current contract (see
``docs/internal/reference/API_CONVENTIONS.md`` §"Deprecation, never deletion":
two of them are documented as public API in shipped plugin SETUP guides, so a
third-party integration we cannot see may call them). They are marked
``deprecated=True`` in the OpenAPI schema and tracked for removal in #1915;
that flag is pinned below so a later refactor cannot quietly un-deprecate them
— and neither can it delete them, which would break an integration this repo
cannot see (two are published as public API in shipped plugin SETUP guides).

This file is the pre-conversion recording of the two converted routes.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app

HA_SOURCE = "src.utils.home_assistant.get_home_assistant_source"
#: The generic-data host allowlist moved to src/plugin_support/url_guard.py
#: with its one caller; the router binds it by that name.
ALLOWED_HOSTS = "src.plugin_support.routes._get_generic_data_allowed_hosts"


@pytest.fixture
def client():
    return TestClient(app)


def _ha_source() -> Mock:
    source = Mock()
    source.base_url = "http://ha.example.com:8123"
    source.headers = {"Authorization": "Bearer test_token"}
    source.timeout = 10
    return source


# ===========================================================================
# GET /home-assistant/entities
# ===========================================================================


def test_entities_flattens_each_state_into_id_state_attributes_and_friendly_name(client):
    upstream = Mock()
    upstream.raise_for_status = Mock()
    upstream.json.return_value = [
        {
            "entity_id": "light.kitchen",
            "state": "on",
            "attributes": {"friendly_name": "Kitchen Light", "brightness": 180},
        }
    ]
    with patch(HA_SOURCE, return_value=_ha_source()), patch("requests.get", return_value=upstream):
        resp = client.get("/home-assistant/entities")
    assert resp.status_code == 200
    assert resp.json() == {
        "entities": [
            {
                "entity_id": "light.kitchen",
                "state": "on",
                "attributes": {"friendly_name": "Kitchen Light", "brightness": 180},
                "friendly_name": "Kitchen Light",
            }
        ]
    }


def test_entities_falls_back_to_the_entity_id_when_home_assistant_omits_attributes(client):
    """HA may send ``attributes: null``; the picker still needs a label."""
    upstream = Mock()
    upstream.raise_for_status = Mock()
    upstream.json.return_value = [{"entity_id": "sensor.bare", "state": "42", "attributes": None}]
    with patch(HA_SOURCE, return_value=_ha_source()), patch("requests.get", return_value=upstream):
        body = client.get("/home-assistant/entities").json()
    assert body["entities"] == [
        {"entity_id": "sensor.bare", "state": "42", "attributes": {}, "friendly_name": "sensor.bare"}
    ]


def test_entities_is_503_when_home_assistant_is_not_configured(client):
    with patch(HA_SOURCE, return_value=None):
        resp = client.get("/home-assistant/entities")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Home Assistant not configured"


def test_entities_is_503_when_home_assistant_cannot_be_reached(client):
    with patch(HA_SOURCE, return_value=_ha_source()), patch("requests.get", side_effect=OSError("refused")):
        resp = client.get("/home-assistant/entities")
    assert resp.status_code == 503
    assert resp.json()["detail"].startswith("Failed to fetch entities:")


# ===========================================================================
# POST /generic-data/test-fetch
# ===========================================================================


def _remote(payload, *, content: bytes = b"{}") -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = payload
    resp.content = content
    return resp


def test_test_fetch_returns_the_parsed_json_document(client):
    with (
        patch(ALLOWED_HOSTS, return_value=["example.com"]),
        patch("requests.request", return_value=_remote({"temp": 21})) as request,
    ):
        resp = client.post("/generic-data/test-fetch", json={"url": "https://example.com/api", "format": "json"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "data": {"temp": 21}}
    assert request.call_args.args[0] == "GET"
    assert request.call_args.kwargs["allow_redirects"] is False


def test_test_fetch_refuses_a_private_address_with_a_400_that_explains_itself(client):
    resp = client.post("/generic-data/test-fetch", json={"url": "http://192.168.1.10/api"})
    assert resp.status_code == 400
    assert "local or private network addresses" in resp.json()["detail"]


def test_test_fetch_refuses_a_host_outside_the_allowlist(client):
    with patch(ALLOWED_HOSTS, return_value=["myapi.com"]):
        resp = client.post("/generic-data/test-fetch", json={"url": "https://example.com/api"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "URL host is not in the allowlist"


def test_test_fetch_caps_the_response_body_at_one_megabyte(client):
    oversized = _remote({"x": 1}, content=b"x" * 1_048_577)
    with (
        patch(ALLOWED_HOSTS, return_value=["example.com"]),
        patch("requests.request", return_value=oversized),
    ):
        resp = client.post("/generic-data/test-fetch", json={"url": "https://example.com/api"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Response too large (exceeds 1 MB)"


def test_test_fetch_reports_an_upstream_timeout_as_504(client):
    import requests as req

    with (
        patch(ALLOWED_HOSTS, return_value=["example.com"]),
        patch("requests.request", side_effect=req.exceptions.Timeout()),
    ):
        resp = client.post("/generic-data/test-fetch", json={"url": "https://example.com/api"})
    assert resp.status_code == 504
    assert resp.json()["detail"] == "Request timed out"


def test_test_fetch_reports_an_upstream_connection_failure_as_502(client):
    import requests as req

    with (
        patch(ALLOWED_HOSTS, return_value=["example.com"]),
        patch("requests.request", side_effect=req.exceptions.ConnectionError()),
    ):
        resp = client.post("/generic-data/test-fetch", json={"url": "https://example.com/api"})
    assert resp.status_code == 502
    assert resp.json()["detail"] == "Connection error — check the URL"


def test_test_fetch_never_echoes_the_upstream_error_back_to_the_caller(client):
    import requests as req

    with (
        patch(ALLOWED_HOSTS, return_value=["example.com"]),
        patch("requests.request", side_effect=req.exceptions.HTTPError("403 for https://example.com?key=SECRET")),
    ):
        resp = client.post("/generic-data/test-fetch", json={"url": "https://example.com/api"})
    assert resp.status_code == 502
    assert resp.json()["detail"] == "HTTP error from remote service"


def test_test_fetch_sends_the_interpolated_headers_the_caller_asked_for(client):
    with (
        patch(ALLOWED_HOSTS, return_value=["example.com"]),
        patch("requests.request", return_value=_remote({})) as request,
    ):
        client.post(
            "/generic-data/test-fetch",
            json={"url": "https://example.com/api", "headers": [{"name": "X-Key", "value": "abc"}]},
        )
    assert request.call_args.kwargs["headers"]["X-Key"] == "abc"


# ===========================================================================
# The eleven deprecated plugin-specific routes
# ===========================================================================

DEPRECATED_ROUTES = {
    ("GET", "/baywheels/stations"),
    ("GET", "/baywheels/stations/nearby"),
    ("GET", "/baywheels/stations/search"),
    ("GET", "/muni/stops"),
    ("GET", "/muni/stops/nearby"),
    ("GET", "/muni/stops/search"),
    ("GET", "/stocks/search"),
    ("POST", "/stocks/validate"),
    ("POST", "/traffic/routes/geocode"),
    ("POST", "/traffic/routes/validate"),
    ("GET", "/transit/cache/status"),
}


def _legacy_records():
    from tests.test_route_inventory import build_route_metadata

    return {(m, r["path"]): r for r in build_route_metadata() for m in r["methods"]}


def test_every_plugin_specific_legacy_route_is_still_served():
    """Deprecation, never deletion — a removed route breaks integrations we cannot see."""
    served = set(_legacy_records())
    assert served >= DEPRECATED_ROUTES, sorted(DEPRECATED_ROUTES - served)


def test_every_plugin_specific_legacy_route_is_marked_deprecated_in_the_schema():
    """The OpenAPI flag is the only signal a third-party caller ever sees (#1915)."""
    records = _legacy_records()
    undeprecated = sorted(key for key in DEPRECATED_ROUTES if not records[key]["route"].deprecated)
    assert undeprecated == [], undeprecated


def test_the_two_converted_routes_are_not_marked_deprecated():
    """A checker that flags everything is as useless as one that flags nothing."""
    records = _legacy_records()
    for key in [("GET", "/home-assistant/entities"), ("POST", "/generic-data/test-fetch")]:
        assert records[key]["route"].deprecated is not True, key
