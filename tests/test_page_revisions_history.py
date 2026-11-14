# ruff: noqa: F811 - pytest fixtures are imported from their home modules
"""H9a: a page's saved versions, and restoring one into the draft.

Every content-changing save through ``PageService`` appends a revision to
``<data>/page_revisions/<digest>.json``: at most 20, none older than 90 days
(the newest is always kept), and saves from the same origin within 60 s
replace the newest instead of flushing the window. Restore never touches the
live page: it writes the draft (Figma 04d decision 5), and publishing that
draft records ``origin: restored``.

Not to be confused with ``Page.revision``, the in-memory edit generation that
``expected_revision`` checks (``tests/test_page_revisions.py``).
"""

from __future__ import annotations

import json
from datetime import UTC

import pytest

from tests.test_auth_mobile_control_scope import auth, browser, no_network, phone  # noqa: F401 - fixtures
from tests.test_v1_contract import _seed_page, client  # noqa: F401 - fixtures

DAY = 86_400.0


class Clock:
    def __init__(self, now: float = 1_800_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(client):
    from src.pages.service import get_page_service

    fake = Clock()
    get_page_service().history.clock = fake
    return fake


@pytest.fixture
def page(client, clock):
    return _seed_page(client, "Commute")


def _lines(text: str) -> list[str]:
    return [text, "", "", "", "", ""]


def _save(client, page_id, **fields):
    response = client.put(f"/pages/{page_id}", json=fields)
    assert response.status_code == 200, response.text
    return response.json()["page"]


def _revisions(client, page_id) -> list[dict]:
    response = client.get(f"/pages/{page_id}/revisions")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_id"] == page_id
    assert body["total"] == len(body["revisions"])
    return body["revisions"]


def _content(client, page_id, rev_id) -> dict:
    response = client.get(f"/pages/{page_id}/revisions/{rev_id}")
    assert response.status_code == 200, response.text
    return response.json()["content"]


# ── recording ───────────────────────────────────────────────────────────────


def test_creating_a_page_records_its_first_revision(client, page):
    (rev,) = _revisions(client, page)
    assert rev["origin"] == "created"
    assert rev["name"] == "Commute"
    assert (rev["rows"], rev["cols"]) == (6, 22)
    assert rev["current"] is True
    assert rev["restored_from"] is None
    assert rev["saved_at"].endswith("+00:00")
    assert "content" not in rev


def test_each_save_records_a_revision_newest_first(client, page, clock):
    clock.now += 120
    _save(client, page, template=_lines("TWO"))
    clock.now += 120
    _save(client, page, template=_lines("THREE"))
    revs = _revisions(client, page)
    assert [r["origin"] for r in revs] == ["edited", "edited", "created"]
    assert [_content(client, page, r["id"])["template"][0] for r in revs] == ["THREE", "TWO", "HI"]
    assert [r["current"] for r in revs] == [True, False, False]


def test_a_save_that_changes_nothing_records_nothing(client, page, clock):
    clock.now += 120
    _save(client, page, template=_lines("HI"))
    assert len(_revisions(client, page)) == 1


def test_edits_within_a_minute_replace_the_newest_revision(client, page, clock):
    clock.now += 120
    _save(client, page, template=_lines("A"))
    clock.now += 30
    _save(client, page, template=_lines("AB"))
    revs = _revisions(client, page)
    assert [r["origin"] for r in revs] == ["edited", "created"]
    assert _content(client, page, revs[0]["id"])["template"][0] == "AB"


def test_an_edit_a_minute_later_is_its_own_revision(client, page, clock):
    clock.now += 120
    _save(client, page, template=_lines("A"))
    clock.now += 61
    _save(client, page, template=_lines("AB"))
    assert len(_revisions(client, page)) == 3


def test_at_most_twenty_revisions_are_kept(client, page, clock):
    for n in range(25):
        clock.now += 120
        _save(client, page, template=_lines(f"V{n}"))
    revs = _revisions(client, page)
    assert len(revs) == 20
    assert _content(client, page, revs[0]["id"])["template"][0] == "V24"
    assert _content(client, page, revs[-1]["id"])["template"][0] == "V5"


def test_revisions_older_than_ninety_days_are_dropped_but_the_newest_stays(client, page, clock):
    clock.now += 120
    _save(client, page, template=_lines("OLD"))
    clock.now += 91 * DAY
    _save(client, page, template=_lines("NEW"))
    revs = _revisions(client, page)
    assert [_content(client, page, r["id"])["template"][0] for r in revs] == ["NEW"]


def test_the_newest_revision_survives_the_age_cap(client, page, clock):
    clock.now += 200 * DAY
    _save(client, page, name="Renamed long after")  # prunes everything older; keeps itself
    clock.now += 200 * DAY
    assert len(_revisions(client, page)) == 1


def test_a_pre_h9_page_records_its_old_content_as_a_baseline_on_first_save(client, page, clock, _isolated_data_dir):
    # A page saved by a build without H9 has no history file.
    for path in (_isolated_data_dir / "page_revisions").glob("*.json"):
        path.unlink()
    clock.now += 120
    _save(client, page, template=_lines("FIRST EDIT"))
    revs = _revisions(client, page)
    assert [r["origin"] for r in revs] == ["edited", "baseline"]
    assert _content(client, page, revs[1]["id"])["template"][0] == "HI"


def test_a_page_untouched_for_100_days_keeps_its_baseline(client, page, clock, _isolated_data_dir):
    # Review #2463 must-fix 2 (probe P1): the baseline carries the page's old
    # updated_at, and the 90-day cap must not prune it in the call that writes it.
    from datetime import datetime

    for path in (_isolated_data_dir / "page_revisions").glob("*.json"):
        path.unlink()
    live = client.get(f"/pages/{page}").json()
    updated_at = datetime.fromisoformat(live["updated_at"] or live["created_at"]).timestamp()
    clock.now = updated_at + 100 * DAY
    _save(client, page, template=_lines("FIRST EDIT"))
    revs = _revisions(client, page)
    assert [r["origin"] for r in revs] == ["edited", "baseline"]
    assert _content(client, page, revs[1]["id"])["template"][0] == "HI"
    assert revs[1]["saved_at"].startswith(datetime.fromtimestamp(updated_at, UTC).date().isoformat())
    # ...and it survives the next save too: it ages from when it was recorded.
    clock.now += 120
    _save(client, page, template=_lines("SECOND EDIT"))
    assert [r["origin"] for r in _revisions(client, page)] == ["edited", "edited", "baseline"]


def test_a_baseline_ages_out_ninety_days_after_it_was_recorded(client, page, clock, _isolated_data_dir):
    from datetime import datetime

    for path in (_isolated_data_dir / "page_revisions").glob("*.json"):
        path.unlink()
    live = client.get(f"/pages/{page}").json()
    updated_at = datetime.fromisoformat(live["updated_at"] or live["created_at"]).timestamp()
    clock.now = updated_at + 100 * DAY
    _save(client, page, template=_lines("FIRST EDIT"))
    clock.now += 91 * DAY
    _save(client, page, template=_lines("MUCH LATER"))
    assert [r["origin"] for r in _revisions(client, page)] == ["edited"]


def test_a_tag_or_extension_only_change_is_not_a_content_change(client, page, clock):
    clock.now += 120
    response = client.put(f"/pages/{page}", json={"duration_seconds": 300})  # the value it already has
    assert response.status_code == 200
    assert len(_revisions(client, page)) == 1


def test_the_revision_content_carries_no_server_fields(client, page):
    (rev,) = _revisions(client, page)
    content = _content(client, page, rev["id"])
    for key in ("id", "revision", "created_at", "updated_at", "edit_protocol", "document_protocol"):
        assert key not in content


def test_a_failed_revision_write_never_fails_the_save(client, page, clock, monkeypatch):
    from src.pages import history

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(history.PageHistory, "_write_revisions", boom)
    clock.now += 120
    saved = _save(client, page, template=_lines("STILL SAVED"))
    assert saved["template"][0] == "STILL SAVED"


def test_a_board_resize_records_a_resized_revision(client, page, clock):
    from src.pages.models import PageUpdate
    from src.pages.service import get_page_service

    clock.now += 120
    get_page_service().update_page(page, PageUpdate(device_type="note"), origin="resized", via="hub")
    rev = _revisions(client, page)[0]
    assert (rev["origin"], rev["via"]) == ("resized", "hub")
    assert (rev["rows"], rev["cols"]) == (3, 15)


def test_history_survives_a_restart(client, page, clock):
    from tests.conftest import _drop_all_singletons

    clock.now += 120
    _save(client, page, template=_lines("KEPT"))
    before = _revisions(client, page)
    _drop_all_singletons()
    assert _revisions(client, page) == before


def test_the_revision_file_is_versioned_and_names_its_page(client, page, _isolated_data_dir):
    (path,) = (_isolated_data_dir / "page_revisions").glob("*.json")
    stored = json.loads(path.read_text())
    assert stored["schema_version"] == 1
    assert stored["page_id"] == page
    assert page not in path.name


# ── who saved it ────────────────────────────────────────────────────────────


def test_a_browser_save_is_via_web(browser, clock):
    page_id = _seed_page(browser, "From the web")
    assert _revisions(browser, page_id)[0]["via"] == "web"


def test_a_phone_save_is_via_phone(phone, browser, clock):
    page_id = _seed_page(browser, "From the phone")
    phone_client, _ = phone
    clock.now += 120
    assert phone_client.put(f"/pages/{page_id}", json={"name": "Phone edit"}).status_code == 200
    rev = _revisions(phone_client, page_id)[0]
    assert (rev["origin"], rev["via"]) == ("edited", "phone")


def test_an_assistant_save_is_origin_assistant(client, page, clock):
    from src.ops import executors

    revision = client.get(f"/pages/{page}").json()["revision"]
    clock.now += 120
    result = executors.update_page(page_id=page, expected_revision=revision, name="Bot renamed")
    assert result.get("success", True) is not False, result
    assert _revisions(client, page)[0]["origin"] == "assistant"


# ── restore ─────────────────────────────────────────────────────────────────


@pytest.fixture
def two_versions(client, page, clock):
    clock.now += 120
    _save(client, page, template=_lines("NEWER"))
    return page, _revisions(client, page)[1]["id"]  # the "created" one (HI)


def test_restore_writes_the_draft_and_leaves_the_live_page(client, two_versions):
    page, old = two_versions
    response = client.post(f"/pages/{page}/revisions/{old}/restore")
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["restored_from"] == old
    assert draft["content"]["template"][0] == "HI"
    assert client.get(f"/pages/{page}").json()["template"][0] == "NEWER"
    assert client.get(f"/pages/{page}/draft").json() == draft


def test_restore_over_an_existing_draft_is_409(client, two_versions):
    page, old = two_versions
    assert client.put(f"/pages/{page}/draft", json={"name": "Unsaved work"}).status_code == 200
    response = client.post(f"/pages/{page}/revisions/{old}/restore")
    assert response.status_code == 409
    assert client.get(f"/pages/{page}/draft").json()["content"]["name"] == "Unsaved work"


def test_restore_can_replace_a_draft_when_asked(client, two_versions):
    page, old = two_versions
    assert client.put(f"/pages/{page}/draft", json={"name": "Unsaved work"}).status_code == 200
    response = client.post(f"/pages/{page}/revisions/{old}/restore", json={"replace_draft": True})
    assert response.status_code == 200
    assert response.json()["content"]["name"] == "Commute"


def test_publishing_a_restored_draft_records_origin_restored(client, two_versions, clock):
    page, old = two_versions
    client.post(f"/pages/{page}/revisions/{old}/restore")
    clock.now += 120
    published = client.post(f"/pages/{page}/draft/publish")
    assert published.status_code == 200, published.text
    assert published.json()["page"]["template"][0] == "HI"
    newest = _revisions(client, page)[0]
    assert (newest["origin"], newest["restored_from"]) == ("restored", old)
    assert newest["current"] is True


def test_publishing_a_plain_draft_records_origin_published(client, page, clock):
    client.put(f"/pages/{page}/draft", json={"template": _lines("FROM DRAFT")})
    clock.now += 120
    client.post(f"/pages/{page}/draft/publish")
    assert _revisions(client, page)[0]["origin"] == "published"


def test_unknown_page_or_revision_is_404(client, page):
    assert client.get("/pages/nope/revisions").status_code == 404
    assert client.get("/pages/nope/revisions/rv_x").status_code == 404
    assert client.get(f"/pages/{page}/revisions/rv_missing").status_code == 404
    assert client.post(f"/pages/{page}/revisions/rv_missing/restore").status_code == 404
    assert client.post("/pages/nope/revisions/rv_x/restore").status_code == 404


def test_deleting_the_page_deletes_its_history(client, page, _isolated_data_dir):
    _seed_page(client, "Keep one")
    assert client.delete(f"/pages/{page}").status_code == 200
    assert client.get(f"/pages/{page}/revisions").status_code == 404
    remaining = [json.loads(p.read_text())["page_id"] for p in (_isolated_data_dir / "page_revisions").glob("*.json")]
    assert page not in remaining


# ── files this build can't fully read (review #2463 must-fix 1) ─────────────


def _revisions_file(data_dir, page_id):
    from src.pages.history import _digest

    return data_dir / "page_revisions" / f"{_digest(page_id)}.json"


def _rewrite_newest(data_dir, page_id, **changes):
    from tests.conftest import _drop_all_singletons

    path = _revisions_file(data_dir, page_id)
    stored = json.loads(path.read_text())
    stored["revisions"][-1].update(changes)
    path.write_text(json.dumps(stored))
    _drop_all_singletons()


def test_a_version_with_an_origin_this_build_doesnt_know_is_skipped(client, page, clock, _isolated_data_dir):
    clock.now += 120
    _save(client, page, template=_lines("MERGED"))
    _rewrite_newest(_isolated_data_dir, page, origin="merged")
    response = client.get(f"/pages/{page}/revisions")
    assert response.status_code == 200, response.text
    assert [r["origin"] for r in response.json()["revisions"]] == ["created"]


def test_a_version_from_a_client_this_build_doesnt_know_reads_with_no_via(client, page, clock, _isolated_data_dir):
    _rewrite_newest(_isolated_data_dir, page, via="tv")
    (rev,) = _revisions(client, page)
    assert (rev["origin"], rev["via"]) == ("created", None)
    assert client.get(f"/pages/{page}/revisions/{rev['id']}").status_code == 200


@pytest.mark.parametrize("saved_at", [float("nan"), float("inf"), -1.0, 1e20, True])
def test_a_version_with_a_bad_instant_is_skipped_not_400(client, page, clock, _isolated_data_dir, saved_at):
    clock.now += 120
    _save(client, page, template=_lines("BAD CLOCK"))
    bad = _revisions(client, page)[0]["id"]
    _rewrite_newest(_isolated_data_dir, page, saved_at=saved_at)
    response = client.get(f"/pages/{page}/revisions")
    assert response.status_code == 200, response.text
    assert [r["origin"] for r in response.json()["revisions"]] == ["created"]
    assert client.get(f"/pages/{page}/revisions/{bad}").status_code == 404


def test_a_version_with_bad_restored_from_reads_as_none(client, page, clock, _isolated_data_dir):
    _rewrite_newest(_isolated_data_dir, page, restored_from=42)
    assert _revisions(client, page)[0]["restored_from"] is None


def test_a_save_still_records_after_a_bad_version_is_read(client, page, clock, _isolated_data_dir):
    _rewrite_newest(_isolated_data_dir, page, origin="merged")
    clock.now += 120
    _save(client, page, template=_lines("AFTER"))
    assert [r["origin"] for r in _revisions(client, page)] == ["edited", "baseline"]


# ── caps the suite did not pin (mutants A2, A3) ─────────────────────────────


def test_edits_from_different_clients_within_a_minute_are_separate_versions(phone, browser, clock):
    page_id = _seed_page(browser, "Shared")
    phone_client, _ = phone
    clock.now += 120
    assert browser.put(f"/pages/{page_id}", json={"name": "Web edit"}).status_code == 200
    clock.now += 10
    assert phone_client.put(f"/pages/{page_id}", json={"name": "Phone edit"}).status_code == 200
    revs = _revisions(browser, page_id)
    assert [(r["origin"], r["via"], r["name"]) for r in revs] == [
        ("edited", "phone", "Phone edit"),
        ("edited", "web", "Web edit"),
        ("created", "web", "Shared"),
    ]


def test_the_file_size_cap_drops_the_oldest_versions_and_keeps_the_newest(client, page, clock, monkeypatch):
    from src.pages import history

    monkeypatch.setattr(history, "MAX_REVISION_FILE_BYTES", 2_000)
    for n in range(8):
        clock.now += 120
        _save(client, page, template=_lines(f"V{n} " + "X" * 15))
    revs = _revisions(client, page)
    names = [_content(client, page, r["id"])["template"][0][:2] for r in revs]
    assert names[0] == "V7"
    assert 1 <= len(revs) < 9
    assert names == [f"V{n}" for n in range(7, 7 - len(revs), -1)]  # the oldest went first


def test_a_single_version_over_the_size_cap_is_still_kept(client, page, clock, monkeypatch):
    from src.pages import history

    monkeypatch.setattr(history, "MAX_REVISION_FILE_BYTES", 10)
    clock.now += 120
    _save(client, page, template=_lines("ONLY ME"))
    revs = _revisions(client, page)
    assert len(revs) == 1
    assert _content(client, page, revs[0]["id"])["template"][0] == "ONLY ME"


# ── the phone scope ─────────────────────────────────────────────────────────


H9A_CONTROL = [
    ("GET", "/pages/drafts"),
    ("GET", "/pages/x/draft"),
    ("PUT", "/pages/x/draft"),
    ("DELETE", "/pages/x/draft"),
    ("POST", "/pages/x/draft/publish"),
    ("GET", "/pages/x/revisions"),
    ("GET", "/pages/x/revisions/y"),
    ("POST", "/pages/x/revisions/y/restore"),
]


@pytest.mark.parametrize(("method", "path"), H9A_CONTROL)
def test_the_phone_reaches_drafts_and_history_and_a_tv_does_not(method, path):
    from src.auth import scopes

    assert scopes.permits(scopes.CONTROL, method, path)
    assert not scopes.permits(scopes.TV_PANELS, method, path)
