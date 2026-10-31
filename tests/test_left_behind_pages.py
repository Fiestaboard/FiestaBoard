"""Board settings name the pages a resize left behind, and the grids a board can draw.

Design section 7: "Size changes that leave pages behind are listed in board
settings, not only logged." ``PUT /settings/board`` answers
``left_behind_pages``: each page sized for a resized board's old grid that
was not moved and no longer fits the board, with the plain reason the page
picker shows. ``GET /settings/board`` names, per LED board, the grid it
produces at each text size (``producible_grids``), so the web mirrors the fit
rule without asking.
"""

from __future__ import annotations

from tests.test_led_text_size import _board, _settings, client, pixoo_output, runtime  # noqa: F401


def _note_array(notes_wide: int) -> dict:
    return {
        "id": "notes-1",
        "name": "Hallway notes",
        "device_type": "note_array",
        "notes_wide": notes_wide,
        "notes_tall": 1,
    }


def resize_array(client, *, notes_wide: int) -> dict:  # noqa: F811
    """A 2-wide note array with a 3 x 30 page, resized in place through ``PUT``."""
    from src.pages.models import PageCreate
    from src.pages.service import get_page_service

    _settings().set_boards([_note_array(2)])
    get_page_service().create_page(
        PageCreate(
            name="Transit", type="template", device_type="note_array", notes_wide=2, notes_tall=1, template=["TRANSIT"]
        )
    )
    boards = client.get("/settings/board").json()["boards"]
    boards[0].update(notes_wide=notes_wide)
    response = client.put("/settings/board", json={"boards": boards})
    assert response.status_code == 200, response.text
    return response.json()


def board_json(client, board_id: str) -> dict:  # noqa: F811
    (board,) = [b for b in client.get("/settings/board").json()["boards"] if b["id"] == board_id]
    return board


def test_a_note_array_resize_lists_the_pages_it_left_behind(client):  # noqa: F811
    body = resize_array(client, notes_wide=4)
    assert [(p["page_name"], p["reason"]) for p in body["left_behind_pages"]] == [("Transit", "Made for a 3×30 board")]


def test_a_pixoo_board_response_names_its_grids(pixoo_output, client):  # noqa: F811
    _settings().set_boards([_board()])
    assert board_json(client, "pixoo-1")["producible_grids"] == {"5x7": [8, 10], "3x5": [10, 16]}


def test_a_flagship_board_response_has_no_grids(client):  # noqa: F811
    _settings().set_boards([{"id": "hall-1", "name": "Hall", "device_type": "flagship"}])
    assert "producible_grids" not in board_json(client, "hall-1")
