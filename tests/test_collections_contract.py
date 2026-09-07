"""Value-level contract goldens for the /collections API (Phase 2 §2, slice 1).

These are deliberately *values*, not shapes. The shape corpus in
``tests/golden/responses/collections.json`` records key sets and type names, so
it cannot see a wrong id, a reordered ``page_ids`` list, or an error string that
stopped naming the missing resource — the class of regression Phase 1's masking
bug proved shape goldens miss.

Every assertion below is a promise this domain makes to the web client.

Re-pinned by the conventions pass in this same PR. What deliberately changed,
and nothing else:

* ``POST /collections`` answers **201** (was 200) with the **bare** collection
  (was ``{"status": "success", "collection": {...}}``) — conventions doc,
  "Status codes" and "Bare bodies".
* ``PUT /collections/{id}`` answers 200 with the **bare** collection (was the
  same ``status``/``collection`` envelope).
* ``DELETE /collections/{id}`` answers 200 with ``{"id": <deleted id>}`` (was
  ``{"status": "success", "message": "Collection <id> deleted"}``) — the
  conventions doc lets a domain pick "200 with the deleted resource id" or
  "204 with no body"; collections picks the former.

Every value assertion — ids, ``page_ids`` ordering, list ordering and total,
error strings, status codes on the failure paths — is unchanged from the
pre-conversion recording. None was weakened.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

MISSING_ID = "collection:00000000-dead-beef-0000-000000000000"


@pytest.fixture
def client(_isolated_data_dir):
    """A TestClient whose services all resolve into this test's temp data dir."""
    from src.api_server import app

    return TestClient(app)


def _seed_page(client: TestClient, name: str, first_line: str) -> str:
    response = client.post(
        "/pages",
        json={
            "name": name,
            "type": "template",
            "device_type": "flagship",
            "template": [first_line, "", "", "", "", ""],
        },
    )
    # RE-PINNED (pages slice): POST /pages now returns 201 with the created
    # page as a bare body, replacing the 200 + {"page": {...}} envelope.
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def pages(client) -> tuple[str, str]:
    """Two real pages, so collection membership validation passes."""
    return (
        _seed_page(client, "Contract Page A", "AAA"),
        _seed_page(client, "Contract Page B", "BBB"),
    )


def _create(client: TestClient, **body) -> dict:
    """POST /collections and return the created collection as a dict.

    The one place that knows the create envelope, so re-pinning the envelope
    is a one-line change instead of a sweep.
    """
    response = client.post("/collections", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ── create ──────────────────────────────────────────────────────────────────


def test_create_returns_the_created_collection_with_its_values(client, pages):
    page_a, page_b = pages

    response = client.post("/collections", json={"name": "Morning", "page_ids": [page_a, page_b]})

    # RE-PINNED: 201 + bare resource (was 200 + {"status", "collection"}).
    assert response.status_code == 201, response.text
    collection = response.json()
    assert collection["name"] == "Morning"
    assert collection["page_ids"] == [page_a, page_b]
    assert collection["selection_mode"] == "time"
    assert collection["time"] == {"interval_seconds": 30}
    assert collection["variable"] is None
    assert collection["random"] is None
    assert collection["updated_at"] is None


def test_create_mints_a_prefixed_collection_id(client, pages):
    page_a, _ = pages

    collection = _create(client, name="Prefixed", page_ids=[page_a])

    assert collection["id"].startswith("collection:")
    assert len(collection["id"]) > len("collection:")


def test_create_preserves_page_ids_order_verbatim(client, pages):
    """``page_ids`` is an ordered playlist, not a set — reversal is a bug."""
    page_a, page_b = pages

    forwards = _create(client, name="Forwards", page_ids=[page_a, page_b])
    backwards = _create(client, name="Backwards", page_ids=[page_b, page_a])

    assert forwards["page_ids"] == [page_a, page_b]
    assert backwards["page_ids"] == [page_b, page_a]


def test_create_rejects_an_unknown_page_with_400_naming_the_page(client, pages):
    page_a, _ = pages

    response = client.post("/collections", json={"name": "Bad", "page_ids": [page_a, "no-such-page"]})

    assert response.status_code == 400
    assert response.json() == {"detail": "Page not found: no-such-page"}


def test_create_rejects_a_missing_page_ids_field_with_422(client):
    response = client.post("/collections", json={"name": "No Pages"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert [d["loc"] for d in detail] == [["body", "page_ids"]]
    assert detail[0]["type"] == "missing"


def test_create_rejects_an_empty_page_ids_list_with_422(client):
    response = client.post("/collections", json={"name": "Empty", "page_ids": []})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert [d["loc"] for d in detail] == [["body", "page_ids"]]
    assert detail[0]["type"] == "too_short"


# ── read ────────────────────────────────────────────────────────────────────


def test_get_round_trips_the_created_collection_by_id(client, pages):
    page_a, page_b = pages
    created = _create(client, name="Round Trip", page_ids=[page_a, page_b])

    response = client.get(f"/collections/{created['id']}")

    assert response.status_code == 200, response.text
    assert response.json() == created


def test_get_unknown_collection_returns_404_naming_the_id(client):
    response = client.get(f"/collections/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Collection not found: {MISSING_ID}"}


def test_list_is_empty_before_anything_is_created(client):
    response = client.get("/collections")

    assert response.status_code == 200
    assert response.json() == {"collections": [], "total": 0}


def test_list_returns_every_collection_sorted_by_name_with_a_total(client, pages):
    page_a, page_b = pages
    _create(client, name="Zulu", page_ids=[page_a])
    _create(client, name="Alpha", page_ids=[page_b])

    response = client.get("/collections")

    assert response.status_code == 200
    body = response.json()
    assert [c["name"] for c in body["collections"]] == ["Alpha", "Zulu"]
    assert [c["page_ids"] for c in body["collections"]] == [[page_b], [page_a]]
    assert body["total"] == 2


# ── update ──────────────────────────────────────────────────────────────────


def test_update_returns_the_updated_collection_and_keeps_its_id(client, pages):
    page_a, page_b = pages
    created = _create(client, name="Before", page_ids=[page_a])

    response = client.put(f"/collections/{created['id']}", json={"name": "After", "page_ids": [page_b, page_a]})

    # RE-PINNED: bare resource (was {"status", "collection"}); status stays 200.
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == created["id"]
    assert updated["name"] == "After"
    assert updated["page_ids"] == [page_b, page_a]
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] is not None


def test_update_leaves_unsent_fields_alone(client, pages):
    page_a, page_b = pages
    created = _create(client, name="Keep Pages", page_ids=[page_a, page_b])

    response = client.put(f"/collections/{created['id']}", json={"name": "Renamed Only"})

    assert response.status_code == 200, response.text
    updated = response.json()  # RE-PINNED: bare resource
    assert updated["name"] == "Renamed Only"
    assert updated["page_ids"] == [page_a, page_b]


def test_update_rejects_an_unknown_page_with_400_naming_the_page(client, pages):
    page_a, _ = pages
    created = _create(client, name="Guarded", page_ids=[page_a])

    response = client.put(f"/collections/{created['id']}", json={"page_ids": ["no-such-page"]})

    assert response.status_code == 400
    assert response.json() == {"detail": "Page not found: no-such-page"}


def test_update_unknown_collection_returns_404_naming_the_id(client):
    response = client.put(f"/collections/{MISSING_ID}", json={"name": "Nobody"})

    assert response.status_code == 404
    assert response.json() == {"detail": f"Collection not found: {MISSING_ID}"}


# ── delete ──────────────────────────────────────────────────────────────────


def test_delete_removes_the_collection_and_reports_it(client, pages):
    page_a, _ = pages
    created = _create(client, name="Doomed", page_ids=[page_a])

    response = client.delete(f"/collections/{created['id']}")

    assert response.status_code == 200, response.text
    # RE-PINNED: the deleted resource id (was {"status": "success", "message": ...}).
    assert response.json() == {"id": created["id"]}
    assert client.get(f"/collections/{created['id']}").status_code == 404
    assert client.get("/collections").json() == {"collections": [], "total": 0}


def test_delete_unknown_collection_returns_404_naming_the_id(client):
    response = client.delete(f"/collections/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Collection not found: {MISSING_ID}"}
