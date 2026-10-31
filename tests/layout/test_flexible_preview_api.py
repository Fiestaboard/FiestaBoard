"""Previews and sends answer a flexible page's ``layout_issues`` (plan Task 16).

Design section 5 step 7: a ``layout_issues`` list is "returned with every
preview"; section 6: previews of a flexible page return the frame as a layer
(LED) or cells (split-flap), plus ``layout_issues``, through the existing
preview routes and the unsaved-page render route
(``POST /pages/preview/flexible``). A grid page's responses are unchanged:
they carry no ``layout_issues`` key at all.

The layout runs against the stand-in expansion :mod:`tests.layout.test_engine`
uses, so the page is a spacer whose
unknown font is its one reported compromise.
"""

# ruff: noqa: F811  (the tests take the fixtures imported from other modules)

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.pages.models import Page
from src.pages.service import get_page_service
from src.settings.service import get_settings_service
from tests.layout.test_engine import stub_expand  # noqa: F401
from tests.layout.test_flexible_render import stub_refs  # noqa: F401
from tests.test_led_text_size import _board, pixoo_output  # noqa: F401
from tests.test_v1_contract import client  # noqa: F401

#: A Pixoo 64 at the 3x5 face: 10 x 16 cells on a 64 x 64 matrix.
PIXOO = _board()
FLAGSHIP = {"id": "flag", "name": "Flagship", "device_type": "flagship"}
NOTE = {"id": "note", "name": "Note", "device_type": "note"}
#: A split-flap board whose output plugin is not installed: no display profile.
GHOST = {"id": "ghost", "name": "Ghost", "device_type": "flagship", "output": "ghost_output"}

#: A band asking for a font no board has, so every board reports that one issue.
FLEX_BODY = {
    "name": "Flex",
    "type": "flexible",
    "blocks": [{"id": "band", "kind": "spacer", "style": {"height": 4, "font": "comic"}}],
}
#: That issue, as ``(path, code)``.
FONT_ISSUE = (["blocks", "band", "style", "font"], "font_unavailable")
GRID_BODY = {"name": "Grid", "type": "template", "device_type": "flagship", "template": ["HELLO"]}


@pytest.fixture
def flex_layout(stub_expand, stub_refs):
    """Flexible layout with the stand-in expansion and plugin references."""


@pytest.fixture
def pixoo_board_id(client, pixoo_output) -> str:
    get_settings_service().set_boards([PIXOO])
    return PIXOO["id"]


@pytest.fixture
def flex_id(client, flex_layout) -> str:
    return get_page_service().storage.create(Page.model_validate(FLEX_BODY)).id


@pytest.fixture
def grid_id(client) -> str:
    return get_page_service().storage.create(Page.model_validate(GRID_BODY)).id


def _batch(client, page_id: str, board_id: str | None = None) -> dict:
    body = {"page_ids": [page_id], **({"board_id": board_id} if board_id else {})}
    response = client.post("/pages/preview/batch", json=body)
    assert response.status_code == 200, response.text
    return response.json()["previews"][page_id]


def _unsaved(client, page: dict, board_id: str | None = None):
    return client.post("/pages/preview/flexible", json={"page": page, **({"board_id": board_id} if board_id else {})})


def _send_ui(client, page_id: str) -> dict:
    service = Mock()
    service.vb_client = Mock()
    with patch("src.pages.routes.get_service", return_value=service):
        response = client.post(f"/pages/{page_id}/send", json={"target": "ui"})
    assert response.status_code == 200, response.text
    return response.json()


# --- POST /pages/preview/batch ------------------------------------------------


def test_batch_preview_returns_frame_layer_cells_and_issues(client, pixoo_board_id, flex_id):
    body = client.post("/pages/preview/batch", json={"page_ids": [flex_id], "board_id": pixoo_board_id}).json()
    p = body["previews"][flex_id]
    assert p["layers"][0]["width"] == 64 and p["cells"] and isinstance(p["layout_issues"], list)
    assert all(isinstance(i["path"], list) and i["code"] for i in p["layout_issues"])


def test_batch_preview_layout_issues_carry_the_block_path(client, pixoo_board_id, flex_id):
    p = _batch(client, flex_id, pixoo_board_id)
    assert [(i["path"], i["code"]) for i in p["layout_issues"]] == [FONT_ISSUE]


def test_batch_preview_cells_are_at_the_boards_grid(client, pixoo_board_id, flex_id):
    p = _batch(client, flex_id, pixoo_board_id)
    assert (len(p["cells"]), len(p["cells"][0])) == (10, 16)


def test_batch_preview_fetches_a_flexible_pages_plugins_for_the_requested_board(client, flex_id):
    # The primary board is a 6 x 22 flagship; the request names the 3 x 15 Note.
    get_settings_service().set_boards([FLAGSHIP, NOTE])
    with patch("src.plugins.registry.get_plugin_registry") as registry:
        registry.return_value.build_template_contexts_for.return_value = {}
        _batch(client, flex_id, NOTE["id"])
    (boards,), _ = registry.return_value.build_template_contexts_for.call_args
    assert [(b.rows, b.cols) for b in boards.values()] == [(3, 15)]


def test_batch_preview_on_a_split_flap_board_has_cells_text_and_issues_but_no_layers(client, flex_id):
    get_settings_service().set_boards([FLAGSHIP])
    p = _batch(client, flex_id, FLAGSHIP["id"])
    assert "layers" not in p and len(p["lines"]) == 6 and p["layout_issues"]


def test_grid_page_batch_preview_has_no_layout_issues_key(client, pixoo_board_id, grid_id):
    assert "layout_issues" not in _batch(client, grid_id, pixoo_board_id)


def test_grid_page_batch_preview_for_a_board_without_a_display_is_served_from_the_preview_cache(client, grid_id):
    # A split-flap board whose output plugin is not installed has no display
    # profile and no rich charset: its grid previews stayed cached before
    # flexible pages, and naming the board (which only a flexible page needs)
    # must not change that.
    get_settings_service().set_boards([GHOST])
    service = get_page_service()
    _batch(client, grid_id, GHOST["id"])
    with patch.object(service, "render_page", wraps=service.render_page) as render:
        _batch(client, grid_id, GHOST["id"])
    render.assert_not_called()


def test_flexible_page_batch_preview_for_a_board_without_a_display_is_rendered_fresh(client, flex_id):
    # A flexible page is laid out for the named board, so the per-page cache
    # (which does not know the board) is bypassed for it.
    get_settings_service().set_boards([GHOST])
    service = get_page_service()
    _batch(client, flex_id, GHOST["id"])
    with patch.object(service, "render_page", wraps=service.render_page) as render:
        _batch(client, flex_id, GHOST["id"])
    render.assert_called_once()


# --- POST /pages/{id}/preview -------------------------------------------------


def test_grid_page_preview_has_no_layout_issues_key(client, grid_id):
    assert "layout_issues" not in client.post(f"/pages/{grid_id}/preview").json()


def test_flexible_page_preview_carries_layout_issues(client, flex_id):
    get_settings_service().set_boards([FLAGSHIP])
    body = client.post(f"/pages/{flex_id}/preview").json()
    assert [(i["path"], i["code"]) for i in body["layout_issues"]] == [FONT_ISSUE]


# --- POST /pages/{id}/send ----------------------------------------------------


def test_flexible_page_send_carries_layout_issues(client, flex_id):
    get_settings_service().set_boards([FLAGSHIP])
    body = _send_ui(client, flex_id)
    assert [(i["path"], i["code"]) for i in body["layout_issues"]] == [FONT_ISSUE]


def test_grid_page_send_has_no_layout_issues_key(client, grid_id):
    assert "layout_issues" not in _send_ui(client, grid_id)


# --- POST /pages/preview/flexible (unsaved) -----------------------------------


def test_unsaved_flexible_preview_renders_without_saving(client, pixoo_board_id, flex_layout):
    before = len(get_page_service().list_pages())
    response = _unsaved(client, FLEX_BODY, pixoo_board_id)
    assert response.status_code == 200, response.text
    assert len(get_page_service().list_pages()) == before


def test_unsaved_flexible_preview_answers_as_a_batch_preview_entry(client, pixoo_board_id, flex_layout):
    body = _unsaved(client, FLEX_BODY, pixoo_board_id).json()
    assert (body["available"], body["page_id"]) == (True, "unsaved")
    assert [(la["width"], la["height"]) for la in body["layers"]] == [(64, 64)]
    assert (len(body["cells"]), len(body["cells"][0])) == (10, 16)
    assert [(i["path"], i["code"]) for i in body["layout_issues"]] == [FONT_ISSUE]


@pytest.mark.parametrize("target", [{}, {"board_id": None}], ids=["omitted", "null"])
def test_unsaved_flexible_preview_without_a_board_lays_out_for_the_primary_board(client, flex_layout, target):
    get_settings_service().set_boards([FLAGSHIP, NOTE])
    response = client.post("/pages/preview/flexible", json={"page": FLEX_BODY, **target})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["lines"]) == 6 and "layers" not in body and "cells" not in body


def test_unsaved_preview_rejects_grid_page_422(client):
    assert _unsaved(client, GRID_BODY).status_code == 422


def test_unsaved_preview_reports_target_exclusion_before_rendering(client, pixoo_board_id, flex_layout):
    page = {**FLEX_BODY, "targets": {"boards": ["another-install"]}}
    response = _unsaved(client, page, pixoo_board_id)
    assert response.status_code == 422
    assert "only on the boards it lists" in response.json()["detail"]


def test_unsaved_preview_rejects_an_invalid_flexible_page_422(client):
    page = {**FLEX_BODY, "blocks": [{"id": "t", "kind": "text"}, {"id": "t", "kind": "text"}]}
    assert _unsaved(client, page).status_code == 422


def test_unsaved_preview_whose_layout_fails_is_a_503(client, flex_layout):
    get_settings_service().set_boards([FLAGSHIP])
    with patch("src.pages.service.layout_flexible_page", side_effect=RuntimeError("boom")):
        response = _unsaved(client, FLEX_BODY)
    assert response.status_code == 503 and "boom" in response.json()["detail"]


# --- the real layout, no stand-ins --------------------------------------------

#: A flexible page laid out by the real expansion and fit.
REAL_FLEX_BODY = {
    "name": "Real flex",
    "type": "flexible",
    "blocks": [{"id": "t", "kind": "text", "text": "HELLO", "style": {"align": "center"}}],
}


@pytest.mark.parametrize("board_id", ["missing-board", ""], ids=["unknown", "empty"])
def test_unsaved_flexible_preview_rejects_an_explicit_unknown_board(client, board_id):
    get_settings_service().set_boards([FLAGSHIP, NOTE])
    response = client.post("/pages/preview/flexible", json={"page": REAL_FLEX_BODY, "board_id": board_id})
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": f"Board not found: {board_id}"}


def test_unsaved_flexible_preview_lays_out_for_the_explicit_secondary_board(client):
    get_settings_service().set_boards([FLAGSHIP, NOTE])
    response = _unsaved(client, REAL_FLEX_BODY, NOTE["id"])
    assert response.status_code == 200, response.text
    lines = response.json()["lines"]
    assert len(lines) == 3 and all(len(line) == 15 for line in lines)
    assert "HELLO" in lines[0]


@pytest.fixture
def real_flex_id(client) -> str:
    return get_page_service().storage.create(Page.model_validate(REAL_FLEX_BODY)).id


def _batch_all(client, page_ids: list[str], board_id: str | None = None) -> dict:
    body = {"page_ids": page_ids, **({"board_id": board_id} if board_id else {})}
    response = client.post("/pages/preview/batch", json=body)
    assert response.status_code == 200, response.text
    return response.json()["previews"]


def test_batch_preview_of_a_grid_and_a_flexible_page_previews_both(client, grid_id, real_flex_id):
    get_settings_service().set_boards([FLAGSHIP])
    previews = _batch_all(client, [grid_id, real_flex_id])
    assert previews[grid_id]["available"] and previews[real_flex_id]["available"]
    assert "HELLO" in previews[real_flex_id]["lines"][0]


def test_batch_preview_of_a_grid_and_a_flexible_page_for_a_named_board_previews_both(
    client, pixoo_board_id, grid_id, real_flex_id
):
    previews = _batch_all(client, [grid_id, real_flex_id], pixoo_board_id)
    assert previews[grid_id]["available"] and previews[real_flex_id]["layers"][0]["width"] == 64


def test_batch_preview_page_whose_plugin_lookup_fails_is_an_error_entry_not_a_failed_batch(
    client, grid_id, real_flex_id
):
    get_settings_service().set_boards([FLAGSHIP])
    with patch("src.pages.service.flexible_plugin_ids", side_effect=RuntimeError("boom")):
        previews = _batch_all(client, [grid_id, real_flex_id])
    assert previews[grid_id]["available"]
    assert previews[real_flex_id]["available"] is False and "boom" in previews[real_flex_id]["error"]


def test_saved_flexible_page_preview_renders_with_the_real_layout(client, pixoo_board_id, real_flex_id):
    response = client.post(f"/pages/{real_flex_id}/preview")
    assert response.status_code == 200, response.text
    assert "HELLO" in response.json()["message"]


def test_unsaved_flexible_preview_renders_with_the_real_layout(client, pixoo_board_id):
    response = _unsaved(client, REAL_FLEX_BODY, pixoo_board_id)
    assert response.status_code == 200, response.text
    assert response.json()["layers"][0]["width"] == 64


#: A real-layout text block asking for a size and a colour a Pixoo can draw.
STYLED_FLEX_BODY = {
    "name": "Styled flex",
    "type": "flexible",
    "blocks": [{"id": "t", "kind": "text", "text": "HELLO", "style": {"size": "large", "color": "#ff0000"}}],
}


@pytest.fixture
def styled_flex_id(client) -> str:
    return get_page_service().storage.create(Page.model_validate(STYLED_FLEX_BODY)).id


def test_saved_flexible_page_preview_on_a_pixoo_primary_is_one_full_frame_layer(client, pixoo_board_id, styled_flex_id):
    body = client.post(f"/pages/{styled_flex_id}/preview").json()
    assert [(layer["width"], layer["height"]) for layer in body["layers"]] == [(64, 64)]


def test_saved_flexible_page_preview_on_a_pixoo_primary_reports_no_cell_board_compromises(
    client, pixoo_board_id, styled_flex_id
):
    body = client.post(f"/pages/{styled_flex_id}/preview").json()
    codes = {issue["code"] for issue in body["layout_issues"]}
    assert not codes & {"color_dropped", "size_ignored"}, body["layout_issues"]


def test_saved_flexible_page_preview_on_a_pixoo_primary_answers_cells_at_its_grid(
    client, pixoo_board_id, styled_flex_id
):
    body = client.post(f"/pages/{styled_flex_id}/preview").json()
    assert (len(body["cells"]), len(body["cells"][0])) == (10, 16)


def test_saved_flexible_page_preview_on_a_split_flap_primary_has_no_layers(client, styled_flex_id):
    get_settings_service().set_boards([FLAGSHIP])
    body = client.post(f"/pages/{styled_flex_id}/preview").json()
    assert "layers" not in body and len(body["lines"]) == 6


def test_physical_marker_survives_single_batch_and_unsaved_responses(client, pixoo_board_id, flex_id):
    single = client.post(f"/pages/{flex_id}/preview")
    assert single.status_code == 200
    unsaved = _unsaved(client, FLEX_BODY, pixoo_board_id)
    assert unsaved.status_code == 200
    for result in [single.json(), _batch(client, flex_id, pixoo_board_id), unsaved.json()]:
        assert result["layers"][0]["physical_frame_version"] == 1
