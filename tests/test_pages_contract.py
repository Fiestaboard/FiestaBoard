"""Value-level contract goldens for the /pages API (Phase 2 §2, slice 3).

These are deliberately *values*, not shapes. The shape corpus in
``tests/golden/responses/pages.json`` records key sets and type names, so it
cannot see a wrong page id, a template whose lines got reordered, a
``sent_to_board`` that flipped, or an error string that stopped naming the
missing resource — the class of regression Phase 1's masking bug proved shape
goldens miss.

Every assertion below is a promise this domain makes to the web client:
the page builder reads the created/updated page straight into editor state,
the compose dialog reads the import result, and the dashboard reads the
send result — unlike collections, whose client discarded every mutation body.

Covers all 16 routes the ``pages`` router serves, success and failure paths.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

MISSING_ID = "00000000-dead-beef-0000-000000000000"

FLAGSHIP_TEMPLATE = ["HELLO CONTRACT", "", "", "", "", ""]


@pytest.fixture
def client(_isolated_data_dir):
    """A TestClient whose services all resolve into this test's temp data dir."""
    from src.api_server import app

    return TestClient(app)


def _create(client: TestClient, name: str, first_line: str) -> dict:
    """POST /pages and return the created page as a dict.

    The one place that knows the create envelope, so re-pinning the envelope
    is a one-line change here instead of a sweep through the file.
    """
    response = client.post(
        "/pages",
        json={
            "name": name,
            "type": "template",
            "device_type": "flagship",
            "template": [first_line, "", "", "", "", ""],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["page"]


@pytest.fixture
def page(client) -> dict:
    return _create(client, "Contract Page A", "HELLO CONTRACT")


# ── POST /pages ─────────────────────────────────────────────────────────────


def test_create_returns_the_created_page_with_its_values(client):
    response = client.post(
        "/pages",
        json={
            "name": "Morning Board",
            "type": "template",
            "device_type": "flagship",
            "template": FLAGSHIP_TEMPLATE,
            "duration_seconds": 45,
        },
    )

    assert response.status_code == 200, response.text
    created = response.json()["page"]
    assert created["name"] == "Morning Board"
    assert created["type"] == "template"
    assert created["device_type"] == "flagship"
    # Line ORDER is the thing a shape golden cannot see.
    assert created["template"] == FLAGSHIP_TEMPLATE
    assert created["duration_seconds"] == 45
    assert isinstance(created["id"], str) and created["id"]
    assert created["updated_at"] is None


def test_create_persists_the_page_under_the_id_it_returned(client):
    created = _create(client, "Persisted", "PERSISTED")

    fetched = client.get(f"/pages/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]
    assert fetched.json()["name"] == "Persisted"


def test_create_rejects_a_body_missing_required_fields_with_422(client):
    response = client.post("/pages", json={"type": "template"})

    assert response.status_code == 422
    # FastAPI's structured validation list, naming the field that was missing.
    locations = [entry["loc"] for entry in response.json()["detail"]]
    assert ["body", "name"] in locations


def test_create_rejects_an_invalid_page_configuration_with_400(client):
    # A template page with no template content fails the service's own
    # validate_config(), not Pydantic's — so this is the 400 path, not 422.
    response = client.post("/pages", json={"name": "Empty", "type": "template", "template": []})

    assert response.status_code == 400
    assert "template" in response.json()["detail"].lower()


# ── GET /pages ──────────────────────────────────────────────────────────────


def test_list_returns_every_page_and_a_matching_total(client):
    first = _create(client, "List One", "ONE")
    second = _create(client, "List Two", "TWO")

    body = client.get("/pages").json()

    ids = [p["id"] for p in body["pages"]]
    assert first["id"] in ids
    assert second["id"] in ids
    assert body["total"] == len(body["pages"])


# ── GET /pages/{page_id} ────────────────────────────────────────────────────


def test_get_returns_the_bare_page_not_an_envelope(client, page):
    body = client.get(f"/pages/{page['id']}").json()

    assert body["id"] == page["id"]
    assert body["name"] == "Contract Page A"
    assert body["template"] == FLAGSHIP_TEMPLATE


def test_get_missing_page_is_404_naming_the_id(client):
    response = client.get(f"/pages/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Page not found: {MISSING_ID}"


# ── PUT /pages/{page_id} ────────────────────────────────────────────────────


def test_update_returns_the_updated_page_with_the_new_values(client, page):
    response = client.put(f"/pages/{page['id']}", json={"name": "Renamed", "duration_seconds": 90})

    assert response.status_code == 200, response.text
    updated = response.json()["page"]
    assert updated["id"] == page["id"]
    assert updated["name"] == "Renamed"
    assert updated["duration_seconds"] == 90
    # Unnamed fields survive a partial update.
    assert updated["template"] == FLAGSHIP_TEMPLATE
    assert updated["updated_at"] is not None


def test_update_without_a_size_change_omits_incompatible_references(client, page):
    body = client.put(f"/pages/{page['id']}", json={"name": "Same Size"}).json()

    assert "incompatible_references" not in body


def test_update_that_retargets_the_size_reports_incompatible_references(client, page):
    body = client.put(f"/pages/{page['id']}", json={"device_type": "note"}).json()

    # Present (list-valued) because the size changed; empty because nothing
    # references this page yet. Warn-only — the page itself did retarget.
    assert body["incompatible_references"] == []
    assert body["page"]["device_type"] == "note"


def test_update_missing_page_is_404_naming_the_id(client):
    response = client.put(f"/pages/{MISSING_ID}", json={"name": "Nobody"})

    assert response.status_code == 404
    assert response.json()["detail"] == f"Page not found: {MISSING_ID}"


# ── DELETE /pages/{page_id} ─────────────────────────────────────────────────


def test_delete_reports_the_deleted_page_and_removes_it(client, page):
    other = _create(client, "Survivor", "SURVIVES")

    response = client.delete(f"/pages/{other['id']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == f"Page {other['id']} deleted"
    assert body["default_page_created"] is False
    assert body["active_page_updated"] is False
    assert client.get(f"/pages/{other['id']}").status_code == 404
    # The other page is untouched.
    assert client.get(f"/pages/{page['id']}").status_code == 200


def test_deleting_the_last_page_creates_a_default_and_says_so(client, page):
    response = client.delete(f"/pages/{page['id']}")

    body = response.json()
    assert body["default_page_created"] is True
    assert body["message"] == f"Page {page['id']} deleted. A default welcome page was created."
    assert body["new_page_id"] != page["id"]
    assert client.get(f"/pages/{body['new_page_id']}").status_code == 200


def test_delete_missing_page_is_404_naming_the_id(client):
    response = client.delete(f"/pages/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Page not found: {MISSING_ID}"


# ── GET /pages/{page_id}/share and the import pair ──────────────────────────


def test_share_round_trips_through_import_preview_without_persisting(client, page):
    share_string = client.get(f"/pages/{page['id']}/share").json()["share_string"]
    assert isinstance(share_string, str) and share_string

    preview = client.post("/pages/import/preview", json={"share_string": share_string})

    assert preview.status_code == 200, preview.text
    decoded = preview.json()
    assert decoded["name"] == "Contract Page A"
    assert decoded["template"] == FLAGSHIP_TEMPLATE
    assert decoded["device_type"] == "flagship"
    # A preview never persists: still exactly one page on the instance.
    assert client.get("/pages").json()["total"] == 1


def test_share_missing_page_is_404_naming_the_id(client):
    response = client.get(f"/pages/{MISSING_ID}/share")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Page not found: {MISSING_ID}"


def test_import_preview_rejects_a_malformed_share_string_with_422(client):
    response = client.post("/pages/import/preview", json={"share_string": "not-a-share"})

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_import_creates_a_new_page_carrying_the_shared_values(client, page):
    share_string = client.get(f"/pages/{page['id']}/share").json()["share_string"]

    response = client.post("/pages/import", json={"share_string": share_string})

    assert response.status_code == 200, response.text
    imported = response.json()["page"]
    assert imported["name"] == "Contract Page A"
    assert imported["template"] == FLAGSHIP_TEMPLATE
    # A fresh resource, not the one that was shared.
    assert imported["id"] != page["id"]
    assert client.get("/pages").json()["total"] == 2


def test_import_rejects_a_malformed_share_string_with_422(client):
    response = client.post("/pages/import", json={"share_string": "not-a-share"})

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


# ── staff picks ─────────────────────────────────────────────────────────────


def test_staff_picks_list_never_leaks_the_share_string(client):
    picks = client.get("/staff-picks").json()

    assert isinstance(picks, list) and picks
    for pick in picks:
        assert "share_string" not in pick
        assert isinstance(pick["id"], str)
        assert isinstance(pick["name"], str)
        assert isinstance(pick["required_plugins"], list)


def test_staff_pick_share_returns_a_string_that_imports(client):
    pick_id = client.get("/staff-picks").json()[0]["id"]

    share_string = client.get(f"/staff-picks/{pick_id}/share").json()["share_string"]

    assert isinstance(share_string, str) and share_string
    assert client.post("/pages/import/preview", json={"share_string": share_string}).status_code == 200


def test_staff_pick_share_missing_is_404_naming_the_id(client):
    response = client.get(f"/staff-picks/{MISSING_ID}/share")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Staff pick not found: {MISSING_ID}"


# ── previews ────────────────────────────────────────────────────────────────


def test_preview_renders_the_page_and_returns_its_lines(client, page):
    response = client.post(f"/pages/{page['id']}/preview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_id"] == page["id"]
    assert body["lines"] == body["message"].split("\n")
    assert body["lines"][0].strip() == "HELLO CONTRACT"
    assert body["display_type"] == "page:template"


def test_preview_missing_page_is_404_naming_the_id(client):
    response = client.post(f"/pages/{MISSING_ID}/preview")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Page not found: {MISSING_ID}"


def test_preview_batch_reports_each_page_separately(client, page):
    response = client.post("/pages/preview/batch", json={"page_ids": [page["id"], MISSING_ID]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert body["successful"] == 1
    good = body["previews"][page["id"]]
    assert good["available"] is True
    assert good["page_id"] == page["id"]
    assert good["lines"][0].strip() == "HELLO CONTRACT"
    bad = body["previews"][MISSING_ID]
    assert bad == {"error": "Page not found", "available": False}


def test_preview_batch_rejects_a_non_list_page_ids_with_400(client):
    response = client.post("/pages/preview/batch", json={"page_ids": "nope"})

    assert response.status_code == 400
    assert response.json()["detail"] == "page_ids must be a list"


# ── cache ───────────────────────────────────────────────────────────────────


def test_cache_stats_counts_the_pages_that_have_been_previewed(client, page):
    assert client.get("/pages/cache/stats").json()["cached_pages"] == []

    client.post(f"/pages/{page['id']}/preview")

    stats = client.get("/pages/cache/stats").json()
    assert page["id"] in stats["cached_pages"]
    assert stats["cache_size"] == len(stats["cached_pages"])
    assert isinstance(stats["ttl_seconds"], int)


def test_clearing_one_page_evicts_only_that_page(client, page):
    other = _create(client, "Other Cached", "OTHER")
    client.post(f"/pages/{page['id']}/preview")
    client.post(f"/pages/{other['id']}/preview")

    response = client.post("/pages/cache/clear", json={"page_id": page["id"]})

    assert response.status_code == 200, response.text
    assert response.json()["message"] == f"Cache cleared for page {page['id']}"
    cached = client.get("/pages/cache/stats").json()["cached_pages"]
    assert page["id"] not in cached
    assert other["id"] in cached


def test_clearing_with_no_body_evicts_every_page(client, page):
    client.post(f"/pages/{page['id']}/preview")

    response = client.post("/pages/cache/clear", json={})

    assert response.status_code == 200, response.text
    assert response.json()["message"] == "All preview caches cleared"
    assert client.get("/pages/cache/stats").json()["cached_pages"] == []


# ── GET /pages/current-display ──────────────────────────────────────────────


def test_current_display_is_404_when_no_page_is_active(client, page):
    response = client.get("/pages/current-display")

    assert response.status_code == 404
    assert response.json()["detail"] == "No active page set"


def test_current_display_returns_the_active_template_page_raw(client, page):
    from src.settings.service import get_settings_service

    get_settings_service().set_active_page_id(page["id"])

    body = client.get("/pages/current-display").json()

    assert body["page_id"] == page["id"]
    assert body["page_name"] == "Contract Page A"
    assert body["page_type"] == "template"
    assert body["device_type"] == "flagship"
    # RAW template, not rendered output — the editor starts a new page from it.
    assert body["template"] == FLAGSHIP_TEMPLATE
    assert body["line_metadata"] is None


# ── POST /pages/{page_id}/send ──────────────────────────────────────────────


def test_send_is_503_when_the_display_service_is_not_initialized(client, page):
    with patch("src.api_server.get_service", return_value=None):
        response = client.post(f"/pages/{page['id']}/send")

    assert response.status_code == 503
    assert response.json()["detail"] == "Service not initialized"


def test_send_rejects_an_unknown_target_with_400(client, page):
    response = client.post(f"/pages/{page['id']}/send", json={"target": "carrier-pigeon"})

    assert response.status_code == 400
    assert response.json()["detail"].startswith("Invalid target: carrier-pigeon")


def test_send_missing_page_is_404_naming_the_id(client):
    service = Mock()
    service.vb_client = Mock()
    with patch("src.api_server.get_service", return_value=service):
        response = client.post(f"/pages/{MISSING_ID}/send", json={"target": "ui"})

    assert response.status_code == 404
    assert response.json()["detail"] == f"Page not found: {MISSING_ID}"


def test_send_to_ui_renders_the_page_without_touching_the_board(client, page):
    service = Mock()
    service.vb_client = Mock()

    with patch("src.api_server.get_service", return_value=service):
        response = client.post(f"/pages/{page['id']}/send", json={"target": "ui"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_id"] == page["id"]
    assert body["sent_to_board"] is False
    assert body["paused"] is False
    assert body["target"] == "ui"
    assert body["board_id"] is None
    assert body["message"].split("\n")[0].strip() == "HELLO CONTRACT"
    service.vb_client.render.assert_not_called()


def test_send_to_board_renders_through_the_board_client(client, page):
    service = Mock()
    service.vb_client.render.return_value = (True, True)

    with patch("src.api_server.get_service", return_value=service):
        response = client.post(f"/pages/{page['id']}/send", json={"target": "board"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sent_to_board"] is True
    assert body["paused"] is False
    assert body["target"] == "board"
    board_array = service.vb_client.render.call_args[0][0]
    assert len(board_array) == 6 and len(board_array[0]) == 22


def test_send_to_an_unreachable_board_is_500_not_a_200_success(client, page):
    """A board that refused the send is never reported as a success.

    Deliberately NOT 502/503/504: nginx intercepts those on /api/ and swaps
    the body for its startup placeholder, so the caller would lose the
    structured reason entirely.
    """
    service = Mock()
    service.vb_client.render.return_value = (False, False)

    with patch("src.api_server.get_service", return_value=service):
        response = client.post(f"/pages/{page['id']}/send", json={"target": "board"})

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Failed to send to board"
    assert body["sent_to_board"] is False
    assert body["page_id"] == page["id"]


def test_send_to_an_unknown_board_id_is_404(client, page):
    service = Mock()
    service.vb_client = Mock()

    with patch("src.api_server.get_service", return_value=service):
        response = client.post(f"/pages/{page['id']}/send?board_id=board:nope", json={"target": "board"})

    assert response.status_code == 404
    assert "board:nope" in response.json()["detail"]
