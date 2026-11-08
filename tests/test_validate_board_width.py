"""H4: ``POST /templates/validate`` measures at the real board width (#1176).

The route used to measure every line against 22 columns, even with a
``board_id``: a Note, TC001 or Pixoo got no warning for a line that will be
cut, and a FiestaPanel or note array got false ones. Pinned here:

- geometry resolves exactly as ``POST /templates/render`` does: the request's
  own geometry, else the ``board_id`` board's, else the Flagship default;
- per display type: Note 15, note array 15 x wide, FiestaPanel grid, Pixoo
  and TC001 at the grid their text face gives;
- ``line_metadata`` wrap is honoured like ``|wrap``;
- the shape the 2.9 editor reads: ``code`` and ``max_length`` per error,
  ``rows`` / ``cols`` validated at.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests import test_board_drawing as drawing
from tests import test_led_board_layout as layout

output_plugin = layout.output_plugin
small_led_output = drawing.small_led_output


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


def _set_boards(boards: list[dict]) -> list[dict]:
    from src.settings.service import get_settings_service

    return get_settings_service().set_boards(boards).boards


def _validate(client: TestClient, **body) -> dict:
    response = client.post("/templates/validate", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _too_long(body: dict) -> list[dict]:
    return [e for e in body["errors"] if e["code"] == "line_too_long"]


PANEL = {
    "id": "panel-1",
    "name": "Lobby TV",
    "output": "fiestapanel",
    "api_mode": "virtual",
    "device_type": "panel",
    "grid_rows": 12,
    "grid_cols": 40,
    "output_config": {},
}


# ── the width per display type ──────────────────────────────────────────────


def test_a_note_board_is_validated_at_fifteen_columns(client):
    boards = _set_boards([{"device_type": "flagship", "name": "Kitchen"}, {"device_type": "note", "name": "Hall"}])
    line = "A" * 16

    note = _validate(client, template=line, board_id=boards[1]["id"])
    flagship = _validate(client, template=line, board_id=boards[0]["id"])

    assert (note["rows"], note["cols"]) == (3, 15)
    assert [(e["line"], e["column"], e["max_length"]) for e in _too_long(note)] == [(1, 15, 16)]
    assert note["valid"] is False
    assert flagship == {"valid": True, "errors": [], "rows": 6, "cols": 22}


def test_a_fiestapanel_is_validated_at_its_grid_not_twenty_two(client):
    (panel,) = _set_boards([PANEL])

    body = _validate(client, template="A" * 30, board_id=panel["id"])

    assert (body["rows"], body["cols"]) == (12, 40)
    assert body["valid"] is True


def test_explicit_panel_geometry_is_validated_at_that_grid(client):
    body = _validate(client, template="A" * 30, device_type="panel", grid_rows=12, grid_cols=40)

    assert (body["rows"], body["cols"]) == (12, 40)
    assert _too_long(body) == []
    assert _too_long(_validate(client, template="A" * 41, device_type="panel", grid_rows=12, grid_cols=40))


def test_a_note_array_is_fifteen_columns_per_note_across(client):
    body = _validate(client, template="A" * 30, device_type="note_array", notes_wide=2, notes_tall=1)

    assert (body["rows"], body["cols"]) == (3, 30)
    assert body["valid"] is True
    assert _too_long(_validate(client, template="A" * 31, device_type="note_array", notes_wide=2))


def test_a_pixoo_is_validated_at_the_grid_its_text_face_gives(client, output_plugin):
    boards = _set_boards([layout.HALL, layout.PIXOO])  # 10 x 16, the 3x5 face

    fits = _validate(client, template="a" * 16, board_id=boards[1]["id"])
    cut = _validate(client, template="a" * 17, board_id=boards[1]["id"])

    assert (fits["rows"], fits["cols"]) == (10, 16)
    assert _too_long(fits) == []
    assert [e["max_length"] for e in _too_long(cut)] == [17]


def test_a_pixoo_counts_extended_markup_in_tiles_at_its_width(client, output_plugin):
    boards = _set_boards([layout.HALL, layout.PIXOO])

    # hot, space, OPEN, space, sun icon, space, XXXXX = 3+1+4+1+1+1+5 = 16 drawn tiles, though 47 characters.
    line = "{{red:hot}} {{black/white:OPEN}} {{icon:sun}} XXXXX"
    fits = _validate(client, template=line, board_id=boards[1]["id"])
    cut = _validate(client, template=line + "X", board_id=boards[1]["id"])

    assert _too_long(fits) == []
    assert [e["max_length"] for e in _too_long(cut)] == [17]


def test_a_tc001_is_validated_at_eight_columns(client, small_led_output):
    tc001 = {**layout.PIXOO, "id": "tc001-1", "device_model": "ulanzi_tc001_awtrix", "grid_rows": 1, "grid_cols": 8}
    boards = _set_boards([layout.HALL, tc001])

    body = _validate(client, template="12:45 PM", board_id=boards[1]["id"])
    cut = _validate(client, template="12:45 PM!", board_id=boards[1]["id"])

    assert (body["rows"], body["cols"]) == (1, 8)
    assert body["valid"] is True
    assert [(e["column"], e["max_length"]) for e in _too_long(cut)] == [(8, 9)]


# ── resolution order and fallbacks ──────────────────────────────────────────


def test_explicit_geometry_beats_the_boards(client):
    boards = _set_boards([{"device_type": "flagship", "name": "Kitchen"}, {"device_type": "note", "name": "Hall"}])

    body = _validate(client, template="A" * 20, board_id=boards[1]["id"], device_type="flagship")

    assert (body["rows"], body["cols"]) == (6, 22)
    assert body["valid"] is True


def test_no_board_and_no_geometry_is_the_flagship_default(client):
    body = _validate(client, template="A" * 23)

    assert (body["rows"], body["cols"]) == (6, 22)
    assert [e["max_length"] for e in _too_long(body)] == [23]


def test_an_unknown_board_falls_back_to_the_default(client):
    _set_boards([{"device_type": "note", "name": "Hall"}])

    body = _validate(client, template="A" * 20, board_id="no-such-board")

    assert (body["rows"], body["cols"]) == (6, 22)
    assert body["valid"] is True


def test_a_panel_without_a_grid_is_rejected(client):
    response = client.post("/templates/validate", json={"template": "HI", "device_type": "panel"})

    assert response.status_code == 422


def test_the_panel_rejection_speaks_of_validating_not_rendering(client):
    response = client.post("/templates/validate", json={"template": "HI", "device_type": "panel"})

    message = " ".join(str(item.get("msg", "")) for item in response.json()["detail"])
    assert "Validating for a panel needs grid_rows and grid_cols" in message
    assert "render" not in message


def test_a_render_without_a_panel_grid_still_says_render(client):
    response = client.post("/templates/render", json={"template": "HI", "device_type": "panel"})

    assert response.status_code == 422
    assert "A panel render needs grid_rows and grid_cols" in str(response.json()["detail"])


# ── per-line wrap ───────────────────────────────────────────────────────────


def test_a_line_whose_metadata_wraps_is_not_too_long(client):
    body = _validate(
        client,
        template=["A" * 30, "B" * 30],
        line_metadata=[{"alignment": "left", "wrap": True}, {"alignment": "left", "wrap": False}],
    )

    assert [e["line"] for e in _too_long(body)] == [2]


def test_a_list_line_holding_a_newline_keeps_its_own_metadata(client):
    """``line_metadata`` is one entry per list element. An element that holds a
    newline is two lines to measure, and both take that element's entry, so
    the elements after it keep theirs (the line numbers count the split lines)."""
    body = _validate(
        client,
        template=["A" * 5 + "\n" + "B" * 30, "C" * 30],
        line_metadata=[{"alignment": "left", "wrap": True}, {"alignment": "left", "wrap": False}],
    )

    assert [e["line"] for e in _too_long(body)] == [3]


# ── the shape the editor reads ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("template", "code"),
    [
        ("{{ unclosed", "mismatched_braces"),
        ("{{weather.nope}}", "unknown_source"),
        ("{{date_time.time|sparkle}}", "unknown_filter"),
        ("{{= IF( }}", "formula"),
        ("A" * 23, "line_too_long"),
    ],
)
def test_each_problem_carries_a_code(client, template, code):
    body = _validate(client, template=template)

    assert code in [e["code"] for e in body["errors"]], body


def test_an_unknown_field_carries_its_code(client, monkeypatch):
    from src.templates.engine import TemplateEngine

    monkeypatch.setattr(TemplateEngine, "get_all_known_sources", lambda self: {"date_time"})
    monkeypatch.setattr(TemplateEngine, "_known_fields", lambda self: {"date_time": {"time"}})

    body = _validate(client, template="{{date_time.nope}}")

    assert [e["code"] for e in body["errors"]] == ["unknown_field"]


def test_max_length_is_only_on_a_line_that_is_too_long(client):
    body = _validate(client, template=["{{weather.nope}}", "A" * 23])

    by_code = {e["code"]: e for e in body["errors"]}
    assert by_code["unknown_source"]["max_length"] is None
    assert by_code["line_too_long"]["max_length"] == 23
    assert set(by_code["line_too_long"]) == {"line", "column", "message", "code", "max_length"}
