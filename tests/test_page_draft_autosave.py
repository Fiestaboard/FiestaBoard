# ruff: noqa: F811 - pytest fixtures are imported from their home modules
"""D4 (bug bash BB-E-17): the web editor autosaves a saved page's edits to its
H9a draft and restores them on return.

The editor drives the existing draft routes; nothing new is stored and
``pages.json`` is untouched. These tests pin the lifecycle the editor relies
on, end to end:

1. every autosave is a full ``PUT /pages/{id}/draft`` guarded by the previous
   draft revision, and the live page and the display runtime never move;
2. on return, ``GET /pages/drafts`` names the page and ``GET .../draft``
   gives back the last autosave;
3. only an explicit Save (``PUT /pages/{id}``) changes the live page, after
   which the editor drops its draft with the draft's revision;
4. "Discard" (the restored-draft link, or the leave guard) deletes the draft
   and leaves the live page as it was.
"""

from __future__ import annotations

import pytest

from tests.test_v1_contract import _seed_page, client  # noqa: F401 - fixtures

BLANK = ["", "", "", "", ""]


@pytest.fixture
def page(client):
    return _seed_page(client, "Kitchen morning")


def _autosave(client, page_id, line, revision=None):
    body = {"name": "Kitchen morning", "template": [line, *BLANK]}
    if revision:
        body["expected_revision"] = revision
    response = client.put(f"/pages/{page_id}/draft", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_autosaves_chain_on_the_draft_revision_and_never_move_the_page(client, page):
    from src.pages.service import get_page_service

    live = client.get(f"/pages/{page}").json()
    first = _autosave(client, page, "GOOD")
    second = _autosave(client, page, "GOOD EVE", first["revision"])
    third = _autosave(client, page, "GOOD EVENING", second["revision"])
    assert len({first["revision"], second["revision"], third["revision"]}) == 3

    assert client.get(f"/pages/{page}").json()["template"] == live["template"]
    assert client.get(f"/pages/{page}").json()["revision"] == live["revision"]
    rendered = get_page_service().preview_page(page, force_refresh=True)
    assert "EVENING" not in rendered.formatted


def test_an_autosave_from_a_stale_editor_is_refused_not_merged(client, page):
    first = _autosave(client, page, "TAB ONE")
    _autosave(client, page, "TAB TWO", first["revision"])
    response = client.put(
        f"/pages/{page}/draft",
        json={"template": ["TAB ONE AGAIN", *BLANK], "expected_revision": first["revision"]},
    )
    assert response.status_code == 412
    assert client.get(f"/pages/{page}/draft").json()["content"]["template"][0] == "TAB TWO"


def test_returning_finds_the_last_autosave(client, page):
    first = _autosave(client, page, "BEFORE THE RELOAD")
    last = _autosave(client, page, "AFTER THE RELOAD", first["revision"])
    listed = client.get("/pages/drafts").json()["drafts"]
    assert [entry["page_id"] for entry in listed] == [page]
    restored = client.get(f"/pages/{page}/draft").json()
    assert restored["revision"] == last["revision"]
    assert restored["content"]["template"][0] == "AFTER THE RELOAD"
    assert restored["stale"] is False


def test_only_an_explicit_save_changes_the_live_page_and_then_the_draft_goes(client, page):
    draft = _autosave(client, page, "SAVED ON PURPOSE")
    live = client.get(f"/pages/{page}").json()
    saved = client.put(
        f"/pages/{page}",
        json={"template": ["SAVED ON PURPOSE", *BLANK], "expected_revision": live["revision"]},
    )
    assert saved.status_code == 200, saved.text
    assert client.get(f"/pages/{page}").json()["template"][0] == "SAVED ON PURPOSE"
    # The draft is now behind the page; the editor discards it with its revision.
    assert client.get(f"/pages/{page}/draft").json()["stale"] is True
    gone = client.delete(f"/pages/{page}/draft", params={"expected_revision": draft["revision"]})
    assert gone.status_code == 200
    assert client.get("/pages/drafts").json() == {"drafts": []}


def test_discard_deletes_the_draft_and_keeps_the_live_page(client, page):
    live = client.get(f"/pages/{page}").json()
    draft = _autosave(client, page, "THROW THIS AWAY")
    response = client.delete(f"/pages/{page}/draft", params={"expected_revision": draft["revision"]})
    assert response.status_code == 200
    assert client.get(f"/pages/{page}/draft").status_code == 404
    assert client.get(f"/pages/{page}").json()["template"] == live["template"]
