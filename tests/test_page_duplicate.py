# ruff: noqa: F811 - pytest fixtures are imported from their home modules
"""H9c: "Make a copy for another display…" (Figma 04d 1.6b, ``174:71469``).

``POST /pages/{id}/duplicate`` copies a page to a display's size (or an
explicit geometry, resolved as H4's validate does) and answers the copy plus
a crop report: H4's ``line_too_long`` at the target width, the lines and
composite rows that fell off the bottom, the canvases rescaled, and the
target board's H3 ``drawing``. The source page is never changed.
"""

from __future__ import annotations

import pytest

from tests.test_v1_contract import boards, client  # noqa: F401 - fixtures

FLAGSHIP = ["X" * 22, "LINE TWO", "", "FOUR", "", "SIX"]


@pytest.fixture
def source(client):
    response = client.post(
        "/pages",
        json={"name": "Commute", "type": "template", "device_type": "flagship", "template": FLAGSHIP, "tags": ["Work"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _dup(client, page_id, **body):
    return client.post(f"/pages/{page_id}/duplicate", json=body)


def _ok(client, page_id, **body):
    response = _dup(client, page_id, **body)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_copy_for_a_smaller_display_takes_its_size(client, boards, source):
    _, hallway = boards  # a Note, 15 x 3
    body = _ok(client, source["id"], board_id=hallway)
    copy = body["page"]
    assert copy["id"] != source["id"]
    assert copy["device_type"] == "note"
    assert copy["template"] == FLAGSHIP[:3]
    assert copy["name"] == "Commute (Hallway)"


def test_the_crop_report_says_what_was_cut(client, boards, source):
    _, hallway = boards
    report = _ok(client, source["id"], board_id=hallway)["report"]
    assert (report["rows"], report["cols"]) == (3, 15)
    assert (report["from_rows"], report["from_cols"]) == (6, 22)
    assert report["rows_dropped"] == [3, 5]  # 0-based source lines with content: "FOUR", "SIX"
    assert [(e["line"], e["max_length"]) for e in report["lines_too_long"]] == [(1, 22)]
    assert report["composite_rows_dropped"] == []
    assert report["canvases_scaled"] == 0


def test_the_report_carries_the_target_boards_drawing(client, boards, source):
    _, hallway = boards
    drawing = _ok(client, source["id"], board_id=hallway)["report"]["drawing"]
    assert drawing["source"] in {"device", "baseline"}
    assert "features" in drawing


def test_the_source_page_is_unchanged(client, boards, source):
    _, hallway = boards
    _ok(client, source["id"], board_id=hallway)
    after = client.get(f"/pages/{source['id']}").json()
    assert after["template"] == FLAGSHIP
    assert after["device_type"] == "flagship"
    assert after["updated_at"] == source["updated_at"]


def test_explicit_geometry_wins_over_a_board(client, boards, source):
    _, hallway = boards
    body = _ok(client, source["id"], board_id=hallway, device_type="panel", grid_rows=12, grid_cols=29)
    assert (body["page"]["grid_rows"], body["page"]["grid_cols"]) == (12, 29)
    assert (body["report"]["rows"], body["report"]["cols"]) == (12, 29)
    assert body["report"]["rows_dropped"] == []
    assert body["report"]["lines_too_long"] == []


def test_a_panel_without_a_grid_is_422(client, source):
    assert _dup(client, source["id"], device_type="panel").status_code == 422


def test_no_target_copies_at_the_same_size(client, source):
    body = _ok(client, source["id"])
    assert body["page"]["template"] == FLAGSHIP
    assert body["page"]["name"] == "Commute copy"
    assert body["report"]["drawing"] is None
    assert body["report"]["rows_dropped"] == []


def test_a_name_can_be_given(client, source):
    assert _ok(client, source["id"], name="Commute for the hall")["page"]["name"] == "Commute for the hall"


def test_a_long_default_name_is_cut_to_100(client, boards):
    _, hallway = boards
    long = client.post("/pages", json={"name": "N" * 100, "type": "template", "template": ["A"]}).json()
    assert len(_ok(client, long["id"], board_id=hallway)["page"]["name"]) == 100


def test_tags_are_copied(client, source):
    assert _ok(client, source["id"])["page"]["tags"] == ["Work"]


def test_the_copy_records_a_duplicated_version(client, source):
    copy = _ok(client, source["id"])["page"]
    revisions = client.get(f"/pages/{copy['id']}/revisions").json()["revisions"]
    assert [r["origin"] for r in revisions] == ["duplicated"]


def test_composite_rows_past_the_target_are_dropped(client, boards):
    _, hallway = boards
    composite = client.post(
        "/pages",
        json={
            "name": "Mix",
            "type": "composite",
            "rows": [
                {"source": "weather", "row_index": 0, "target_row": 0},
                {"source": "weather", "row_index": 1, "target_row": 5},
            ],
        },
    ).json()
    body = _ok(client, composite["id"], board_id=hallway)
    assert [r["target_row"] for r in body["page"]["rows"]] == [0]
    assert body["report"]["composite_rows_dropped"] == [1]


def test_a_composite_with_nothing_left_is_400(client, boards):
    _, hallway = boards
    composite = client.post(
        "/pages",
        json={"name": "Low", "type": "composite", "rows": [{"source": "weather", "row_index": 0, "target_row": 5}]},
    ).json()
    response = _dup(client, composite["id"], board_id=hallway)
    assert response.status_code == 400
    assert len(client.get("/pages").json()["pages"]) == 1


def test_canvases_are_scaled_to_the_target(client):
    page = client.post(
        "/pages",
        json={
            "name": "Art",
            "type": "template",
            "device_type": "panel",
            "grid_rows": 12,
            "grid_cols": 30,
            "template": ["HI"],
            "canvases": [{"id": "pic", "area": {"row": 7, "col": 16, "rows": 6, "cols": 15}, "source": "x"}],
        },
    )
    assert page.status_code == 201, page.text
    body = _ok(client, page.json()["id"], device_type="panel", grid_rows=6, grid_cols=15)
    from src.canvas import scale_area
    from src.canvas.models import CanvasArea

    expected = scale_area(CanvasArea(row=7, col=16, rows=6, cols=15), (12, 30), (6, 15))
    area = body["page"]["canvases"][0]["area"]
    assert (area["row"], area["col"], area["rows"], area["cols"]) == (
        expected.row,
        expected.col,
        expected.rows,
        expected.cols,
    )
    assert (area["row"], area["col"]) != (7, 16)
    assert body["report"]["canvases_scaled"] == 1


def test_an_unknown_page_or_board_is_404(client, source):
    assert _dup(client, "nope").status_code == 404
    assert _dup(client, source["id"], board_id="nope").status_code == 404
    assert len(client.get("/pages").json()["pages"]) == 1


def test_the_phone_may_duplicate_and_a_tv_may_not():
    from src.auth import scopes

    assert scopes.permits(scopes.CONTROL, "POST", "/pages/x/duplicate")
    assert not scopes.permits(scopes.TV_PANELS, "POST", "/pages/x/duplicate")
