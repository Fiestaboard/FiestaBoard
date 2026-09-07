"""Value-level contract goldens for the /staff-picks API (Phase 2 §2, slice 8).

Staff picks are the curated pages the web UI offers on an empty install. They
are served from a file checked into the repo (``staff-picks/picks.json``), so
these assertions pin two separate things: the *envelope* the client reads, and
the fact that the shipped catalog is intact and importable.

The share string is a base64 page payload the "Add to my board" button feeds
straight into the page importer — a truncated or re-encoded one produces a
broken page rather than an error, which is exactly the failure a shape golden
cannot see.

This domain arrives already conventions-compliant: it was converted with the
pages slice and only changes router tag in this PR (``pages`` →
``staff-picks``), so it can be excused, enforced and reviewed on its own.

Recorded against the UNCONVERTED trunk: every assertion below passed before a
line of this slice's production code changed.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


def test_the_shipped_catalog_is_served_and_is_not_empty(client):
    response = client.get("/staff-picks")
    assert response.status_code == 200
    picks = response.json()
    assert isinstance(picks, list)
    assert len(picks) >= 1
    assert {p["id"] for p in picks} >= {"weather-dashboard"}


def test_a_pick_carries_everything_the_gallery_card_renders(client):
    picks = client.get("/staff-picks").json()
    pick = next(p for p in picks if p["id"] == "weather-dashboard")
    assert pick["name"] == "Weather Dashboard"
    assert pick["device_type"] == "flagship"
    assert pick["tags"] == ["weather"]
    assert pick["image"] == "/staff-picks/weather-dashboard.png"
    assert pick["featured_at"] == "2026-05-24"
    assert pick["required_plugins"] == [
        {"id": "weather", "name": "Weather"},
        {"id": "date_time", "name": "Date & Time"},
    ]


def test_the_listing_never_leaks_the_share_string(client):
    """The share payload is fetched on demand, one pick at a time."""
    for pick in client.get("/staff-picks").json():
        assert "share_string" not in pick


def test_the_share_endpoint_returns_an_importable_page_payload(client):
    response = client.get("/staff-picks/weather-dashboard/share")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"share_string"}

    decoded = json.loads(base64.b64decode(body["share_string"]))
    assert decoded["v"] == 1
    assert decoded["page"]["name"] == "Weather Dashboard"
    assert decoded["page"]["type"] == "template"
    assert decoded["page"]["device_type"] == "flagship"
    assert len(decoded["page"]["template"]) == 6, "a flagship page is six rows"


def test_an_unknown_pick_is_a_404_naming_it(client):
    response = client.get("/staff-picks/no-such-pick/share")
    assert response.status_code == 404
    assert response.json()["detail"] == "Staff pick not found: no-such-pick"
