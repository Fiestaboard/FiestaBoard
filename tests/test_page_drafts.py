# ruff: noqa: F811 - pytest fixtures are imported from their home modules
"""H9a: a hub-side draft per page that no board ever sees.

"Save draft" keeps the published page on every display ("Den TV keeps the
7:12 AM version", Figma 04d 1.9); "Save & update board" publishes it; "Discard
changes" deletes it. The draft lives in its own file under
``<data>/page_drafts/``, never in ``pages.json``, so the display runtime (and
an older build after a rollback) can only ever read the published page.
"""

from __future__ import annotations

import json

import pytest

from tests.test_v1_contract import _seed_page, client  # noqa: F401 - fixtures


@pytest.fixture
def page(client):
    return _seed_page(client, "Commute")


def _draft(client, page_id, **fields):
    return client.put(f"/pages/{page_id}/draft", json=fields)


def _ok_draft(client, page_id, **fields):
    response = _draft(client, page_id, **fields)
    assert response.status_code == 200, response.text
    return response.json()


def _restart():
    from tests.conftest import _drop_all_singletons

    _drop_all_singletons()


# ── saving a draft leaves the published page alone ──────────────────────────


def test_a_saved_draft_is_returned_with_its_content(client, page):
    body = _ok_draft(client, page, template=["DRAFT", "", "", "", "", ""])
    assert body["page_id"] == page
    assert body["content"]["template"][0] == "DRAFT"
    assert body["content"]["name"] == "Commute"
    assert body["revision"]
    assert body["stale"] is False
    assert body["restored_from"] is None
    assert client.get(f"/pages/{page}/draft").json() == body


def test_the_published_page_is_unchanged_by_a_draft(client, page):
    before = client.get(f"/pages/{page}").json()
    _ok_draft(client, page, template=["DRAFT", "", "", "", "", ""], name="Commute v2")
    after = client.get(f"/pages/{page}").json()
    assert after["template"] == before["template"]
    assert after["name"] == "Commute"
    assert after["updated_at"] == before["updated_at"]


def test_the_runtime_renders_the_published_page_not_the_draft(client, page):
    from src.pages.service import get_page_service

    _ok_draft(client, page, template=["DRAFT", "", "", "", "", ""])
    rendered = get_page_service().preview_page(page, force_refresh=True)
    assert "DRAFT" not in rendered.formatted
    assert "HI" in rendered.formatted


def test_the_draft_never_reaches_pages_json(client, page, _isolated_data_dir):
    _ok_draft(client, page, template=["SECRET DRAFT", "", "", "", "", ""])
    assert "SECRET DRAFT" not in (_isolated_data_dir / "pages.json").read_text()


def test_a_draft_survives_a_restart(client, page):
    saved = _ok_draft(client, page, template=["KEPT", "", "", "", "", ""])
    _restart()
    assert client.get(f"/pages/{page}/draft").json() == saved


def test_a_second_save_applies_over_the_draft_not_the_page(client, page):
    _ok_draft(client, page, template=["ONE", "", "", "", "", ""])
    body = _ok_draft(client, page, name="Renamed")
    assert body["content"]["template"][0] == "ONE"
    assert body["content"]["name"] == "Renamed"


def test_saving_identical_content_keeps_the_draft_revision(client, page):
    first = _ok_draft(client, page, template=["SAME", "", "", "", "", ""])
    second = _ok_draft(client, page, template=["SAME", "", "", "", "", ""])
    assert second["revision"] == first["revision"]


# ── concurrency ─────────────────────────────────────────────────────────────


def test_a_draft_write_with_a_stale_draft_revision_is_412(client, page):
    first = _ok_draft(client, page, template=["A", "", "", "", "", ""])
    _ok_draft(client, page, template=["B", "", "", "", "", ""], expected_revision=first["revision"])
    response = _draft(client, page, template=["C", "", "", "", "", ""], expected_revision=first["revision"])
    assert response.status_code == 412
    assert client.get(f"/pages/{page}/draft").json()["content"]["template"][0] == "B"


def test_a_draft_is_stale_once_the_page_is_published_elsewhere(client, page):
    _ok_draft(client, page, template=["MINE", "", "", "", "", ""])
    assert client.put(f"/pages/{page}", json={"name": "Changed on the iPad"}).status_code == 200
    assert client.get(f"/pages/{page}/draft").json()["stale"] is True


# ── validation and bounds ───────────────────────────────────────────────────


def test_an_invalid_draft_is_400_and_nothing_is_stored(client, page):
    response = _draft(client, page, device_type="panel")  # a panel needs a grid
    assert response.status_code == 400
    assert client.get(f"/pages/{page}/draft").status_code == 404


def test_a_draft_over_256_kib_is_400(client, page):
    response = _draft(client, page, template=["X" * 100_000] * 3)
    assert response.status_code == 400
    assert "256" in response.json()["detail"]
    assert client.get(f"/pages/{page}/draft").status_code == 404


def test_a_plugin_transition_in_a_draft_needs_the_beta(client, page):
    response = _draft(client, page, transition_strategy="plugin:typewriter")
    assert response.status_code == 400


def test_a_draft_cannot_change_the_page_type(client, page):
    # PageUpdate has no ``type``; an unknown field is ignored, never stored.
    body = _ok_draft(client, page, type="single", template=["T", "", "", "", "", ""])
    assert body["content"]["type"] == "template"


# ── reads and 404s ──────────────────────────────────────────────────────────


def test_no_draft_is_404(client, page):
    assert client.get(f"/pages/{page}/draft").status_code == 404


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "/draft", None),
        ("PUT", "/draft", {"name": "x"}),
        ("DELETE", "/draft", None),
        ("POST", "/draft/publish", None),
    ],
)
def test_an_unknown_page_is_404(client, method, suffix, body, _isolated_data_dir):
    response = client.request(method, f"/pages/nope{suffix}", json=body)
    assert response.status_code == 404
    assert not list((_isolated_data_dir / "page_drafts").glob("*.json"))


def test_the_draft_list_names_pages_with_drafts(client, page):
    other = _seed_page(client, "Other")
    assert client.get("/pages/drafts").json() == {"drafts": []}
    _ok_draft(client, page, name="Draft")
    drafts = client.get("/pages/drafts").json()["drafts"]
    assert [d["page_id"] for d in drafts] == [page]
    assert drafts[0]["stale"] is False
    assert drafts[0]["saved_at"].endswith("+00:00")
    assert other not in [d["page_id"] for d in drafts]


# ── discard ─────────────────────────────────────────────────────────────────


def test_discarding_deletes_the_draft(client, page):
    _ok_draft(client, page, name="Draft")
    response = client.delete(f"/pages/{page}/draft")
    assert response.status_code == 200
    assert response.json() == {"page_id": page, "discarded": True}
    assert client.get(f"/pages/{page}/draft").status_code == 404
    assert client.delete(f"/pages/{page}/draft").status_code == 404


def test_discarding_with_a_stale_draft_revision_is_412(client, page):
    first = _ok_draft(client, page, name="A")
    _ok_draft(client, page, name="B")
    response = client.delete(f"/pages/{page}/draft", params={"expected_revision": first["revision"]})
    assert response.status_code == 412
    assert client.get(f"/pages/{page}/draft").status_code == 200


# ── publish ─────────────────────────────────────────────────────────────────


def test_publishing_applies_the_draft_and_deletes_it(client, page):
    _ok_draft(client, page, template=["LIVE NOW", "", "", "", "", ""], name="Commute v2")
    response = client.post(f"/pages/{page}/draft/publish")
    assert response.status_code == 200, response.text
    published = response.json()["page"]
    assert published["template"][0] == "LIVE NOW"
    assert published["name"] == "Commute v2"
    assert response.json()["incompatible_references"] == []
    assert client.get(f"/pages/{page}").json()["template"][0] == "LIVE NOW"
    assert client.get(f"/pages/{page}/draft").status_code == 404


def test_publishing_can_clear_a_nullable_field(client, page):
    assert client.put(f"/pages/{page}", json={"transition_strategy": "column"}).status_code == 200
    _ok_draft(client, page, transition_strategy=None)
    published = client.post(f"/pages/{page}/draft/publish").json()["page"]
    assert published["transition_strategy"] is None


def test_publishing_without_a_draft_is_409(client, page):
    assert client.post(f"/pages/{page}/draft/publish").status_code == 409


def test_publishing_against_a_stale_page_revision_is_412_and_keeps_the_draft(client, page):
    revision = client.get(f"/pages/{page}").json()["revision"]
    _ok_draft(client, page, name="Mine")
    assert client.put(f"/pages/{page}", json={"name": "Theirs"}).status_code == 200
    response = client.post(f"/pages/{page}/draft/publish", json={"expected_revision": revision})
    assert response.status_code == 412
    assert client.get(f"/pages/{page}").json()["name"] == "Theirs"
    assert client.get(f"/pages/{page}/draft").status_code == 200


def test_publishing_reports_a_size_change_that_no_longer_fits(client, page):
    from src.settings.service import get_settings_service

    stored = get_settings_service().set_boards([{"device_type": "flagship", "name": "Kitchen"}])
    board_id = stored.boards[0]["id"]
    get_settings_service().set_active_page_id(page, board_id)
    _ok_draft(client, page, device_type="note", template=["NOTE", "", ""])
    body = client.post(f"/pages/{page}/draft/publish").json()
    assert body["page"]["device_type"] == "note"
    assert [r["board_id"] for r in body["incompatible_references"]] == [board_id]


# ── deleting the page ───────────────────────────────────────────────────────


def test_deleting_the_page_deletes_its_draft(client, page, _isolated_data_dir):
    _seed_page(client, "Keep one")  # so the delete is not the last page
    _ok_draft(client, page, name="Doomed")
    assert client.delete(f"/pages/{page}").status_code == 200
    assert client.get("/pages/drafts").json() == {"drafts": []}
    assert not list((_isolated_data_dir / "page_drafts").glob("*.json"))


# ── on disk ─────────────────────────────────────────────────────────────────


def test_a_draft_file_is_versioned_and_names_its_page(client, page, _isolated_data_dir):
    _ok_draft(client, page, name="On disk")
    (path,) = (_isolated_data_dir / "page_drafts").glob("*.json")
    stored = json.loads(path.read_text())
    assert stored["schema_version"] == 1
    assert stored["page_id"] == page
    assert page not in path.name  # the file name is a digest, never the raw id
