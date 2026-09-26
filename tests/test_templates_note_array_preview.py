"""``POST /templates/render`` previews a note array at its real size (issue #2032).

A note array has no fixed size: it is ``notes_wide`` × ``notes_tall`` Notes, so
its grid is ``15·notes_wide`` columns by ``3·notes_tall`` rows. Every other
render path already carries that geometry — ``PageService._render_template``
forwards ``page.notes_wide``/``page.notes_tall``, which is why a saved page
reaches the physical board at full width — but the two preview endpoints the
page editor calls dropped it, so ``{{filled:-}}`` on a FiestaPanel stopped after
one note's 15 columns in the preview pane while the board itself was correct.

The blank early-return had the mirror-image bug: it sized itself from
``DEVICE_DIMENSIONS``, which has no ``note_array`` key, so an empty array
template answered with *flagship* rows while a non-empty one rendered at note
width — two different wrong sizes in one handler.

These are value assertions on tile counts, not shape checks: a render that
silently halves the board width still has the right JSON shape.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /templates/render
# ---------------------------------------------------------------------------


def test_render_fills_the_full_width_of_a_side_by_side_array(client):
    response = client.post(
        "/templates/render",
        json={"template": ["{{filled:-}}"], "device_type": "note_array", "notes_wide": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lines"][0] == "-" * 30, "two Notes side by side are 30 tiles wide, not 15"


def test_render_pads_a_stacked_array_to_its_row_count(client):
    response = client.post(
        "/templates/render",
        json={"template": ["TOP"], "device_type": "note_array", "notes_tall": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["line_count"] == 6, "two Notes stacked are 6 rows"
    assert body["lines"] == ["TOP            ", *["               "] * 5]


def test_render_of_an_empty_array_template_blanks_at_the_array_row_count(client):
    response = client.post(
        "/templates/render",
        json={"template": [], "device_type": "note_array", "notes_wide": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["line_count"] == 3, "a 2x1 array is 3 rows; the blank path used to answer flagship's 6"
    assert body["lines"] == ["", "", ""]


def test_render_rejects_a_note_count_beyond_the_maximum(client):
    response = client.post(
        "/templates/render",
        json={"template": ["HI"], "device_type": "note_array", "notes_wide": 99},
    )
    assert response.status_code == 422


def test_render_rejects_a_zero_note_count(client):
    response = client.post(
        "/templates/render",
        json={"template": ["HI"], "device_type": "note_array", "notes_tall": 0},
    )
    assert response.status_code == 422


def test_render_of_a_note_ignores_the_array_geometry(client):
    response = client.post(
        "/templates/render",
        json={"template": ["{{filled:-}}"], "device_type": "note", "notes_wide": 4},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lines"] == ["-" * 15, " " * 15, " " * 15], "a Note is 3x15 whatever notes_wide says"


def test_render_of_a_flagship_ignores_the_array_geometry(client):
    response = client.post(
        "/templates/render",
        json={"template": ["{{filled:-}}"], "device_type": "flagship", "notes_wide": 4},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["line_count"] == 6
    assert body["lines"][0] == "-" * 22


def test_render_still_rejects_an_unknown_device_type_rather_than_failing(client):
    response = client.post(
        "/templates/render",
        json={"template": ["HI"], "device_type": "bogus", "notes_wide": 2},
    )
    assert response.status_code == 422, "an unrecognised device answers a validation error, never a 500"


# ---------------------------------------------------------------------------
# POST /templates/render/live
# ---------------------------------------------------------------------------


def test_render_live_fills_the_full_width_of_a_side_by_side_array(client):
    response = client.post(
        "/templates/render/live",
        json={"template": ["{{filled:-}}"], "device_type": "note_array", "notes_wide": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lines"][0] == "-" * 30, "two Notes side by side are 30 tiles wide, not 15"


def test_render_live_of_an_empty_array_template_blanks_at_the_array_row_count(client):
    response = client.post(
        "/templates/render/live",
        json={"template": [], "device_type": "note_array", "notes_wide": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["line_count"] == 3
    assert body["lines"] == ["", "", ""]
    assert body["sent_to_board"] is False


def test_render_live_of_a_note_ignores_the_array_geometry(client):
    response = client.post(
        "/templates/render/live",
        json={"template": ["{{filled:-}}"], "device_type": "note", "notes_wide": 4},
    )
    assert response.status_code == 200
    assert response.json()["lines"] == ["-" * 15, " " * 15, " " * 15]


def test_render_live_still_rejects_an_unknown_device_type_rather_than_failing(client):
    response = client.post(
        "/templates/render/live",
        json={"template": ["HI"], "device_type": "bogus", "notes_wide": 2},
    )
    assert response.status_code == 422
