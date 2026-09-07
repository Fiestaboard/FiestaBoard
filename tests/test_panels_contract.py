"""Value-level contract goldens for the /panels and /panel APIs (Phase 2 §2).

Two surfaces with different audiences:

* ``/panels``  (plural)  — authenticated CRUD for the app.
* ``/panel/``  (singular) — unauthenticated read-only viewer endpoints a TV
  browser polls. The auth exemption is part of the contract and is pinned
  here, because losing it silently would black out every wall display.

Creating a panel co-creates an auto-fit virtual board; deleting one removes
it again. The board's geometry is attached to every panel payload, so the
values below (``rows``/``cols`` for a 55" 16:9 screen, ``board_missing``)
are the ones the viewer scales itself from.

Recorded against the UNCONVERTED trunk: every assertion below passed before a
line of this slice's production code changed. The conversion commit re-pins
only what it deliberately changes, and says so inline.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def panel(client) -> dict:
    """One created panel, as the create endpoint reports it."""
    response = client.post("/panels", json={"name": "Kitchen TV"})
    assert response.status_code == 200, response.text
    return response.json()["panel"]


# ---------------------------------------------------------------------------
# GET /panels
# ---------------------------------------------------------------------------


def test_listing_an_instance_with_no_panels_is_an_empty_list(client):
    response = client.get("/panels")
    assert response.status_code == 200
    assert response.json() == {"panels": [], "total": 0}


def test_listing_attaches_the_backing_board_geometry_to_each_panel(client, panel):
    response = client.get("/panels")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    (listed,) = body["panels"]
    assert listed["id"] == panel["id"]
    assert listed["device_type"] == "note_array"
    assert listed["board_missing"] is False
    assert (listed["rows"], listed["cols"]) == (12, 15)


# ---------------------------------------------------------------------------
# POST /panels
# ---------------------------------------------------------------------------


def test_creating_a_panel_returns_it_with_an_auto_fit_board(client):
    response = client.post("/panels", json={"name": "Kitchen TV"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    created = body["panel"]
    assert created["name"] == "Kitchen TV"
    assert created["short_code"] == 1, "the first panel gets the TV-typable /p/1"
    assert created["screen_diagonal_inches"] == 55.0
    assert created["screen_aspect_w"] == 16.0
    assert created["screen_aspect_h"] == 9.0
    assert created["is_display"] is False
    assert created["backdrop"] == "wall"
    assert created["auto_dim"] == {"enabled": False, "start": "22:00", "end": "07:00"}
    # A 55" 16:9 screen auto-fits to a 3x5 grid of Note blocks = 12x15 flaps.
    assert (created["rows"], created["cols"]) == (12, 15)
    assert created["device_type"] == "note_array"
    assert created["board_missing"] is False


def test_creating_a_panel_co_creates_its_virtual_board(client, panel):
    boards = client.get("/settings/board").json()["boards"]
    board = next(b for b in boards if b["id"] == panel["board_id"])
    assert board["api_mode"] == "virtual"
    assert board["device_type"] == "note_array"
    assert board["name"] == "Kitchen TV (Panel)"


def test_creating_a_panel_without_a_name_is_rejected(client):
    assert client.post("/panels", json={}).status_code == 422


# ---------------------------------------------------------------------------
# PATCH /panels/{panel_id}
# ---------------------------------------------------------------------------


def test_updating_an_unknown_panel_is_a_404(client):
    response = client.patch("/panels/no-such-panel", json={"name": "x"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Panel not found"


def test_updating_returns_the_updated_panel(client, panel):
    response = client.patch(f"/panels/{panel['id']}", json={"name": "Living Room TV"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["panel"]["name"] == "Living Room TV"
    assert body["panel"]["id"] == panel["id"]
    assert "incompatible_references" not in body, "only a screen-size change reports references"


def test_a_screen_size_change_refits_the_board_and_reports_references(client, panel):
    response = client.patch(f"/panels/{panel['id']}", json={"screen_diagonal_inches": 32.0})
    assert response.status_code == 200
    body = response.json()
    assert body["panel"]["screen_diagonal_inches"] == 32.0
    assert (body["panel"]["rows"], body["panel"]["cols"]) != (12, 15), "the grid was re-fit"
    assert body["incompatible_references"] == [], "no pages reference this board yet"


# ---------------------------------------------------------------------------
# DELETE /panels/{panel_id}
# ---------------------------------------------------------------------------


def test_deleting_an_unknown_panel_is_a_404(client):
    response = client.delete("/panels/no-such-panel")
    assert response.status_code == 404
    assert response.json()["detail"] == "Panel not found"


def test_deleting_removes_the_panel_and_its_virtual_board(client, panel):
    response = client.delete(f"/panels/{panel['id']}")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    assert client.get("/panels").json() == {"panels": [], "total": 0}
    board_ids = [b["id"] for b in client.get("/settings/board").json()["boards"]]
    assert panel["board_id"] not in board_ids


# ---------------------------------------------------------------------------
# GET /panel/{panel_id} — public viewer config
# ---------------------------------------------------------------------------


def test_the_public_config_is_the_panel_plus_the_board_presentation(client, panel):
    response = client.get(f"/panel/{panel['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == panel["id"]
    assert body["name"] == "Kitchen TV"
    assert (body["rows"], body["cols"]) == (12, 15)
    assert body["device_type"] == "note_array"
    assert body["board_missing"] is False
    assert body["board_color"] == "black"
    assert body["code62_glyph"] in ("degree", "heart")


def test_the_public_config_is_reachable_by_short_code(client, panel):
    response = client.get(f"/panel/{panel['short_code']}")
    assert response.status_code == 200
    assert response.json()["id"] == panel["id"]


def test_an_unknown_panel_ref_is_a_404(client):
    response = client.get("/panel/no-such-panel")
    assert response.status_code == 404
    assert response.json()["detail"] == "Panel not found"


def test_the_reserved_display_ref_gets_its_own_actionable_404(client):
    """The HDMI kiosk shows this copy before a panel is designated."""
    response = client.get("/panel/display")
    assert response.status_code == 404
    assert response.json()["detail"] == "No display panel selected"


# ---------------------------------------------------------------------------
# GET /panel/{panel_id}/frame — public viewer frame
# ---------------------------------------------------------------------------


def test_a_panel_with_nothing_sent_to_it_serves_a_null_frame_with_its_geometry(client, panel):
    response = client.get(f"/panel/{panel['id']}/frame")
    assert response.status_code == 200
    assert response.json() == {
        "characters": None,
        "message": None,
        "rows": 12,
        "cols": 15,
        "updated_at": None,
    }


def test_an_unknown_panel_frame_is_a_404(client):
    response = client.get("/panel/no-such-panel/frame")
    assert response.status_code == 404
    assert response.json()["detail"] == "Panel not found"
