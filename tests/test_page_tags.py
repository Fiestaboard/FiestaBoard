# ruff: noqa: F811 - pytest fixtures are imported from their home modules
"""H9c: tags on a page (the Pages library's facet; CREATOR-IDE audit "Explorer").

``tags`` is an optional field on the page, stored in ``pages.json`` with no
schema bump: absent means ``[]``, and an older build keeps the key as an
opaque extension. Requests are strict (422): at most 16 tags, each 1-32
characters after NFC + trim + whitespace collapse, no control or format
characters. Duplicates compare case-insensitively; the first spelling wins.
Stored values are cleaned leniently, so a page never fails to load because
of a ``tags`` extension some client stored before H9.
"""

from __future__ import annotations

import json

import pytest

from tests.test_v1_contract import client  # noqa: F401 - fixtures


def _create(client, name="Menu", **fields):
    return client.post("/pages", json={"name": name, "type": "template", "template": ["HI"], **fields})


def _ok(client, name="Menu", **fields):
    response = _create(client, name, **fields)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_page_without_tags_has_an_empty_list(client):
    assert _ok(client)["tags"] == []


def test_tags_are_normalised_and_deduplicated(client):
    page = _ok(client, tags=["  Morning   menu ", "morning MENU", "Café", "Café"])
    assert page["tags"] == ["Morning menu", "Café"]


@pytest.mark.parametrize(
    "tags",
    [
        [f"t{n}" for n in range(17)],
        ["x" * 33],
        ["   "],
        ["bad‮one"],
        ["nul\u0000"],
        [5],
        "Morning",
    ],
)
def test_a_request_over_a_limit_is_422(client, tags):
    assert _create(client, tags=tags).status_code == 422


def test_sixteen_tags_of_thirty_two_characters_are_fine(client):
    tags = [f"{n:02d}" + "x" * 30 for n in range(16)]
    assert _ok(client, tags=tags)["tags"] == tags


def test_put_replaces_clears_or_keeps_tags(client):
    page = _ok(client, tags=["A"])
    assert client.put(f"/pages/{page['id']}", json={"tags": ["B", "C"]}).json()["page"]["tags"] == ["B", "C"]
    assert client.put(f"/pages/{page['id']}", json={"name": "Renamed"}).json()["page"]["tags"] == ["B", "C"]
    assert client.put(f"/pages/{page['id']}", json={"tags": []}).json()["page"]["tags"] == []


def test_put_is_strict_too(client):
    page = _ok(client)
    assert client.put(f"/pages/{page['id']}", json={"tags": ["x" * 40]}).status_code == 422


def test_a_tag_only_change_records_no_saved_version(client):
    page = _ok(client)
    client.put(f"/pages/{page['id']}", json={"tags": ["Lunch"]})
    assert len(client.get(f"/pages/{page['id']}/revisions").json()["revisions"]) == 1


def test_a_draft_never_changes_tags(client):
    # Review #2466 P11: tags aren't drafted, so sending them to the draft route
    # is a 422 rather than a 200 that silently drops them.
    page = _ok(client, tags=["Keep"])
    response = client.put(f"/pages/{page['id']}/draft", json={"tags": ["Drafted"], "name": "Drafted"})
    assert response.status_code == 422, response.text
    assert "PUT /pages/" in response.json()["detail"]
    assert client.get(f"/pages/{page['id']}/draft").status_code == 404
    assert client.get(f"/pages/{page['id']}").json()["tags"] == ["Keep"]


def test_a_draft_without_tags_still_publishes_and_keeps_the_page_tags(client):
    page = _ok(client, tags=["Keep"])
    assert client.put(f"/pages/{page['id']}/draft", json={"name": "Drafted"}).status_code == 200
    published = client.post(f"/pages/{page['id']}/draft/publish").json()["page"]
    assert (published["name"], published["tags"]) == ("Drafted", ["Keep"])


@pytest.mark.parametrize(
    "tag",
    [
        "\U0001f468\u200d\U0001f469\u200d\U0001f467 family",  # family: man, woman, girl
        "\U0001f3f3\ufe0f\u200d\U0001f308",  # rainbow flag: white flag, VS16, ZWJ, rainbow
        "\U0001f469\U0001f3fd\u200d\U0001f4bb",  # woman technologist, medium skin tone
        "\U0001f3c3\u200d\u2640\ufe0f run",  # woman running
    ],
)
def test_emoji_joined_with_zwj_are_allowed(client, tag):
    assert _ok(client, tags=[tag])["tags"] == [tag]


@pytest.mark.parametrize(
    "tag",
    [
        "ab\u200dcd",  # between letters
        "\u200d\U0001f308",  # leading
        "\U0001f308\u200d",  # trailing
        "\U0001f468\u200d\u200d\U0001f469",  # doubled
        "\U0001f468\u200b\U0001f469",  # zero-width space is still a format character
    ],
)
def test_a_zwj_outside_an_emoji_sequence_is_422(client, tag):
    assert _create(client, tags=[tag]).status_code == 422


def test_the_list_filters_by_tag_case_insensitively(client):
    a = _ok(client, "A", tags=["Morning"])
    _ok(client, "B", tags=["Evening"])
    c = _ok(client, "C", tags=["morning", "Evening"])
    body = client.get("/pages", params={"tag": "MORNING"}).json()
    assert sorted(p["id"] for p in body["pages"]) == sorted([a["id"], c["id"]])
    assert body["total"] == 2
    assert client.get("/pages").json()["total"] == 3


def test_the_tag_facet_counts_pages(client):
    _ok(client, "A", tags=["Morning"])
    _ok(client, "B", tags=["Evening"])
    _ok(client, "C", tags=["morning", "Evening"])
    assert client.get("/pages/tags").json() == {
        "tags": [{"tag": "Evening", "count": 2}, {"tag": "Morning", "count": 2}]
    }


def test_share_strings_leave_tags_out(client):
    page = _ok(client, tags=["Private"])
    share = client.get(f"/pages/{page['id']}/share").json()["share_string"]
    preview = client.post("/pages/import/preview", json={"share_string": share}).json()
    assert "tags" not in preview or preview["tags"] in (None, [])


def test_tags_survive_a_restart(client):
    from tests.conftest import _drop_all_singletons

    page = _ok(client, tags=["Kept"])
    _drop_all_singletons()
    assert client.get(f"/pages/{page['id']}").json()["tags"] == ["Kept"]


@pytest.mark.parametrize(
    ("stored", "loaded"),
    [
        ("oops", []),
        (["ok", 5, "nul\u0000", "x" * 40, "OK"], ["ok"]),
        ({"a": 1}, []),
        ([f"t{n}" for n in range(20)], [f"t{n}" for n in range(16)]),
    ],
)
def test_stored_tags_load_leniently(client, _isolated_data_dir, stored, loaded):
    page = _ok(client)
    path = _isolated_data_dir / "pages.json"
    data = json.loads(path.read_text())
    data["pages"][0]["tags"] = stored
    path.write_text(json.dumps(data))
    from tests.conftest import _drop_all_singletons

    _drop_all_singletons()
    response = client.get(f"/pages/{page['id']}")
    assert response.status_code == 200
    assert response.json()["tags"] == loaded


def test_pages_json_keeps_its_schema_version(client, _isolated_data_dir):
    from src.pages.storage import CURRENT_SCHEMA_VERSION

    _ok(client, tags=["A"])
    assert CURRENT_SCHEMA_VERSION == 6
    assert json.loads((_isolated_data_dir / "pages.json").read_text())["schema_version"] == 6


def test_the_phone_reads_the_tag_facet_and_a_tv_does_not():
    from src.auth import scopes

    assert scopes.permits(scopes.CONTROL, "GET", "/pages/tags")
    assert not scopes.permits(scopes.TV_PANELS, "GET", "/pages/tags")
