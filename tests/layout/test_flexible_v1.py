"""``/v1/pages`` accepts and returns flexible pages (plan Task 17).

Design section 11: ``/v1/pages`` accepts and returns flexible pages, additively.
Clients that list pages see ``type: "flexible"`` without ``template``, and
``document_protocol`` is ``page-document-v2`` for flexible pages only. Section 7:
a flexible page fits every board, so a schedule may put it on a Flagship.
Section 11 again: the share string carries flexible pages, so a share string
imports back into the same page.

``/v1/pages`` reuses ``Page``/``PageCreate``/``PageUpdate``, so these tests pin
that reuse rather than any new code.
"""

# ruff: noqa: F811  (the tests take the fixture imported from another module)

from __future__ import annotations

from tests.test_v1_contract import client  # noqa: F401

FLEX = {
    "name": "Morning",
    "type": "flexible",
    "style": {"font": "fiesta", "size": "medium"},
    "layout": {"kind": "stack", "valign": "middle"},
    "blocks": [
        {"id": "b1", "kind": "text", "text": "GOOD MORNING", "style": {"align": "center"}, "priority": 1},
        {"id": "b2", "kind": "spacer", "style": {"height": 2}},
    ],
}
GRID = {"name": "Grid", "type": "template", "device_type": "flagship", "template": ["HI", "", "", "", "", ""]}


def _create(client, body: dict) -> dict:
    response = client.post("/v1/pages", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_v1_create_and_read_flexible_page(client):
    page_id = _create(client, FLEX)["id"]
    got = client.get(f"/v1/pages/{page_id}").json()
    assert got["type"] == "flexible" and "template" not in got and got["document_protocol"] == "page-document-v2"


def test_v1_read_flexible_page_returns_its_blocks_style_and_layout(client):
    page_id = _create(client, FLEX)["id"]
    got = client.get(f"/v1/pages/{page_id}").json()
    assert [b["id"] for b in got["blocks"]] == ["b1", "b2"]
    assert got["style"]["font"] == "fiesta" and got["layout"]["valign"] == "middle"


def test_v1_list_includes_flexible_without_template(client):
    flex_id = _create(client, FLEX)["id"]
    _create(client, GRID)
    pages = {p["id"]: p for p in client.get("/v1/pages").json()["pages"]}
    assert pages[flex_id]["type"] == "flexible" and "template" not in pages[flex_id]


def test_v1_list_keeps_grid_pages_on_document_v1(client):
    flex_id = _create(client, FLEX)["id"]
    grid_id = _create(client, GRID)["id"]
    pages = {p["id"]: p for p in client.get("/v1/pages").json()["pages"]}
    assert pages[grid_id]["document_protocol"] == "page-document-v1"
    assert pages[flex_id]["document_protocol"] == "page-document-v2"


def test_v1_update_replaces_blocks(client):
    created = _create(client, FLEX)
    new_blocks = [{"id": "only", "kind": "text", "text": "NEW"}]
    response = client.put(
        f"/v1/pages/{created['id']}", json={"blocks": new_blocks, "expected_revision": created["revision"]}
    )
    assert response.status_code == 200, response.text
    got = client.get(f"/v1/pages/{created['id']}").json()
    assert [(b["id"], b.get("text")) for b in got["blocks"]] == [("only", "NEW")]


def test_v1_schedule_flexible_page_on_flagship_board_is_allowed(client):
    from src.settings.service import get_settings_service

    board_id = get_settings_service().set_boards([{"device_type": "flagship", "name": "Kitchen"}]).boards[0]["id"]
    page_id = _create(client, FLEX)["id"]
    response = client.post(
        "/v1/schedules", json={"board_id": board_id, "page_id": page_id, "start_time": "08:00", "end_time": "09:00"}
    )
    assert response.status_code == 201, response.text


def test_import_flexible_share_string_round_trips(client):
    page_id = _create(client, FLEX)["id"]
    share = client.get(f"/pages/{page_id}/share").json()["share_string"]
    imported = client.post("/pages/import", json={"share_string": share})
    assert imported.status_code == 201, imported.text
    body = imported.json()
    original = client.get(f"/v1/pages/{page_id}").json()
    assert body["id"] != page_id and body["type"] == "flexible" and "template" not in body
    for key in ("blocks", "style", "layout"):
        assert body[key] == original[key]
