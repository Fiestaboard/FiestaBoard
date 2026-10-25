"""A FiestaPanel is fit per character, end to end through the real API.

A 55" 16:9 TV holds 12 rows × 29 columns at true flap pitch. It used to be
fit in whole 15 × 3 Note blocks — one block wide, 12 × 15 — leaving half the
screen dark. These tests drive the actual routes a user's app and TV use:
create the panel, author a page for it, put the page on the panel's board,
and read back what the TV viewer would draw.
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
    response = client.post("/panels", json={"name": "Kitchen TV", "screen_diagonal_inches": 55})
    assert response.status_code == 201, response.text
    return response.json()


def _panel_page(client, panel: dict, template: list[str]) -> dict:
    response = client.post(
        "/pages",
        json={
            "name": "Wall",
            "type": "template",
            "template": template,
            "device_type": "panel",
            "grid_rows": panel["rows"],
            "grid_cols": panel["cols"],
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_a_55_inch_panel_is_29_columns_wide(panel):
    assert (panel["device_type"], panel["rows"], panel["cols"]) == ("panel", 12, 29)


def test_a_page_sized_to_the_panel_reaches_the_tv_at_full_width(client, panel):
    page = _panel_page(client, panel, ["{{filled:-}}", "HELLO"])

    sent = client.put("/settings/active-page", json={"page_id": page["id"], "board_id": panel["board_id"]})
    assert sent.status_code == 200, sent.text

    frame = client.get(f"/panel/{panel['id']}/frame").json()
    assert (frame["rows"], frame["cols"]) == (12, 29)
    characters = frame["characters"]
    assert len(characters) == 12 and {len(row) for row in characters} == {29}
    assert all(code != 0 for code in characters[0]), "the filled line spans all 29 columns"


def test_current_display_reports_the_panel_page_grid(client, panel):
    """The editor starts a new page from what the board shows; for a panel
    page that needs the grid, not just the device family."""
    from src.settings.service import get_settings_service

    page = _panel_page(client, panel, ["HELLO"])
    # current-display reads the install-wide (primary) active page; set it
    # directly, since the primary here is a flagship the panel page won't fit.
    get_settings_service().set_active_page_id(page["id"])

    response = client.get("/pages/current-display")
    assert response.status_code == 200, response.text
    body = response.json()

    assert (body["device_type"], body["grid_rows"], body["grid_cols"]) == ("panel", 12, 29)


def test_a_page_sized_to_the_panel_is_compatible_with_its_board(client, panel):
    page = _panel_page(client, panel, ["HELLO"])
    compat = client.put("/settings/active-page", json={"page_id": page["id"], "board_id": panel["board_id"]})
    assert compat.status_code == 200, compat.text


def test_a_page_for_a_different_panel_size_is_refused_by_the_panel_board(client, panel):
    page = client.post(
        "/pages",
        json={
            "name": "Other TV",
            "type": "template",
            "template": ["HELLO"],
            "device_type": "panel",
            "grid_rows": 14,
            "grid_cols": 34,
        },
    ).json()
    response = client.put("/settings/active-page", json={"page_id": page["id"], "board_id": panel["board_id"]})
    assert response.status_code == 400
    assert "panel:12x29" in response.json()["detail"]


def test_a_panel_page_without_a_grid_is_rejected(client):
    response = client.post(
        "/pages",
        json={"name": "No grid", "type": "template", "template": ["HI"], "device_type": "panel"},
    )
    assert response.status_code == 422


def test_preview_renders_a_panel_template_at_the_panel_size(client):
    response = client.post(
        "/templates/render",
        json={"template": ["{{filled:-}}"], "device_type": "panel", "grid_rows": 7, "grid_cols": 17},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["line_count"] == 7
    assert body["lines"][0] == "-" * 17


def test_preview_of_an_empty_panel_template_blanks_at_the_panel_row_count(client):
    response = client.post(
        "/templates/render",
        json={"template": [""], "device_type": "panel", "grid_rows": 7, "grid_cols": 17},
    )
    assert response.status_code == 200, response.text
    assert response.json()["line_count"] == 7


def test_preview_of_a_panel_without_a_grid_is_rejected(client):
    response = client.post("/templates/render", json={"template": ["HI"], "device_type": "panel"})
    assert response.status_code == 422


def test_a_screen_size_change_moves_the_board_to_the_new_character_fit(client, panel):
    response = client.patch(f"/panels/{panel['id']}", json={"screen_diagonal_inches": 65})
    assert response.status_code == 200
    assert (response.json()["rows"], response.json()["cols"]) == (14, 34)
    assert client.get(f"/panel/{panel['id']}/frame").json()["cols"] == 34


def test_a_resize_reports_the_page_sized_for_the_old_grid(client, panel):
    page = _panel_page(client, panel, ["HELLO"])
    client.put("/settings/active-page", json={"page_id": page["id"], "board_id": panel["board_id"]})

    body = client.patch(f"/panels/{panel['id']}", json={"screen_diagonal_inches": 65}).json()

    assert [ref["page_id"] for ref in body["incompatible_references"]] == [page["id"]]


def test_a_one_off_override_can_be_composed_for_a_panel(client):
    response = client.post(
        "/settings/temporary-override",
        json={"template": ["HELLO"], "device_type": "panel", "grid_rows": 12, "grid_cols": 29},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["device_type"], body["grid_rows"], body["grid_cols"]) == ("panel", 12, 29)


def test_a_one_off_override_for_a_panel_needs_its_grid(client):
    response = client.post(
        "/settings/temporary-override",
        json={"template": ["HELLO"], "device_type": "panel"},
    )
    assert response.status_code == 422
    assert "grid_rows" in response.json()["detail"]


def test_a_one_off_override_cannot_exceed_the_panel_rows(client):
    response = client.post(
        "/settings/temporary-override",
        json={"template": ["X"] * 8, "device_type": "panel", "grid_rows": 7, "grid_cols": 17},
    )
    assert response.status_code == 422
    assert "fits 7" in response.json()["detail"]


# --- the 3x10 floor of an LED board in pixels -----------------------------------------------
#
# A Divoom Pixoo 64 drawn in the 5x7 face is 8 rows x 10 cols. Pages,
# previews and one-off overrides accept any grid down to 3x10, the smallest
# board core creates; a FiestaPanel's own autofit still holds the 3x15 Note.


def test_a_page_for_an_8x10_led_board_is_accepted(client):
    response = client.post(
        "/pages",
        json={
            "name": "Large",
            "type": "template",
            "template": ["HI"],
            "device_type": "panel",
            "grid_rows": 8,
            "grid_cols": 10,
        },
    )
    assert response.status_code in (200, 201), response.text
    assert (response.json()["grid_rows"], response.json()["grid_cols"]) == (8, 10)


@pytest.mark.parametrize(("rows", "cols"), [(3, 9), (2, 14)])
def test_a_page_below_3x10_is_refused(client, rows, cols):
    response = client.post(
        "/pages",
        json={
            "name": "Tiny",
            "type": "template",
            "template": ["HI"],
            "device_type": "panel",
            "grid_rows": rows,
            "grid_cols": cols,
        },
    )
    assert response.status_code == 422


def test_preview_renders_at_8x10(client):
    response = client.post(
        "/templates/render",
        json={"template": ["{{filled:-}}"], "device_type": "panel", "grid_rows": 8, "grid_cols": 10},
    )
    assert response.status_code == 200, response.text
    assert (response.json()["line_count"], response.json()["lines"][0]) == (8, "-" * 10)


def test_a_one_off_override_can_be_composed_at_8x10(client):
    response = client.post(
        "/settings/temporary-override",
        json={"template": ["HELLO"], "device_type": "panel", "grid_rows": 8, "grid_cols": 10},
    )
    assert response.status_code == 200, response.text
    assert (response.json()["grid_rows"], response.json()["grid_cols"]) == (8, 10)


def test_a_one_off_override_below_3x10_is_refused(client):
    response = client.post(
        "/settings/temporary-override",
        json={"template": ["HELLO"], "device_type": "panel", "grid_rows": 3, "grid_cols": 9},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "grid_cols must be between 10 and 128"


def test_a_small_tv_panel_still_gets_the_15_column_note_width(client):
    response = client.post("/panels", json={"name": "Pocket", "screen_diagonal_inches": 24})
    assert response.status_code == 201, response.text
    assert (response.json()["rows"], response.json()["cols"]) == (5, 15)
