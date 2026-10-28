"""A page for any display with a custom grid — an output plugin's LED board too.

The page editor lists every board stored as a custom grid (a ``panel`` board
of ``grid_rows`` x ``grid_cols``) as a page target, not only FiestaPanels. An
output plugin's board is exactly that: a Divoom Pixoo 64 drawn in the 3x5
face is a 10 x 16 grid. Nothing about the stored page format changes — a page
for it is a ``panel`` page of its grid, the same geometry relationship a
FiestaPanel page has, so ``pages.json`` needs no migration. Pinned here, end
to end through the API, with the output plugin's real device model:

- such a page saves as authored — its grid, its letter case, its colour
  spans and icons — and fits the display (and only displays of its grid);
- the batch preview for that board renders its extended markup and answers
  rich ``cells`` at the board's grid, lowercase kept;
- sending the page to the board delivers those rich cells to its output.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.devices import pages_compatible_with_board
from src.outputs.board_profile import board_character_set
from src.plugins.loader import PluginLoader

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"

PIXOO = {
    "id": "pixoo-1",
    "name": "Pixoo",
    "device_type": "panel",
    "grid_rows": 10,
    "grid_cols": 16,
    "output": PLUGIN_ID,
    "device_model": "divoom_pixoo64",
    "output_config": {"host": "192.0.2.50"},
}
HALL = {"id": "hall-1", "name": "Hall", "device_type": "flagship", "code62_glyph": "degree"}
TEMPLATE = ["Hello {{red:hot}}", "{{icon:sun}}"]


@pytest.fixture
def output_plugin(tmp_path):
    """The recording output plugin, whose device models include the Pixoo 64.

    Without the fixture's own tiny character set: like the real Pixoo plugin,
    the board then draws its model's set (the 3x5 LED face, mixed case).
    """
    root = tmp_path / "plugins"
    shutil.copytree(FIXTURE, root / PLUGIN_ID, ignore=shutil.ignore_patterns("__pycache__"))
    manifest_path = root / PLUGIN_ID / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["output"].pop("character_set")
    manifest_path.write_text(json.dumps(manifest), "utf-8")
    loader = PluginLoader(plugins_dir=root, external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


@pytest.fixture
def api(tmp_path, output_plugin):
    """The API over a real page store, with a Flagship and a Pixoo configured."""
    from src.api_server import app
    from src.pages.service import PageService
    from src.pages.storage import PageStorage
    from src.settings.service import get_settings_service

    get_settings_service().set_boards([HALL, PIXOO])
    service = PageService(PageStorage(str(tmp_path / "pages.json")))
    with mock.patch("src.pages.routes.get_page_service", return_value=service):
        yield TestClient(app), service


def _create(client, **geometry) -> dict:
    body = {"name": "Hot", "type": "template", "template": TEMPLATE, **geometry}
    response = client.post("/pages", json=body)
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_the_pixoo_resolves_to_a_rich_mixed_case_set(output_plugin):
    charset = board_character_set(PIXOO)
    assert charset is not None
    assert charset["mixedCase"] and charset["colorSpans"] and charset["icons"]


def test_a_page_for_the_display_saves_as_authored(api):
    client, _ = api
    page = _create(client, device_type="panel", grid_rows=10, grid_cols=16)

    stored = client.get(f"/pages/{page['id']}").json()
    assert (stored["device_type"], stored["grid_rows"], stored["grid_cols"]) == ("panel", 10, 16)
    assert stored["template"] == TEMPLATE


def test_the_page_fits_the_display_and_no_other_shape(api):
    client, service = api
    page = service.get_page(_create(client, device_type="panel", grid_rows=10, grid_cols=16)["id"])

    assert pages_compatible_with_board(page, PIXOO)
    assert not pages_compatible_with_board(page, HALL)
    assert not pages_compatible_with_board(page, {**PIXOO, "grid_rows": 12, "grid_cols": 29})


def test_the_batch_preview_for_the_display_answers_rich_cells_in_its_case(api):
    client, _ = api
    page_id = _create(client, device_type="panel", grid_rows=10, grid_cols=16)["id"]

    response = client.post("/pages/preview/batch", json={"page_ids": [page_id], "board_id": "pixoo-1"})
    assert response.status_code == 200, response.text
    preview = response.json()["previews"][page_id]

    cells = preview["cells"]
    assert (len(cells), len(cells[0])) == (10, 16)
    assert [c["value"] for c in cells[0][:5]] == list("Hello")
    assert cells[0][6] == {"type": "char", "value": "h", "color": "red"}
    assert cells[1][0]["icon"] == "sun"


def test_the_batch_preview_without_the_board_is_the_split_flap_one(api):
    client, _ = api
    page_id = _create(client, device_type="panel", grid_rows=10, grid_cols=16)["id"]

    preview = client.post("/pages/preview/batch", json={"page_ids": [page_id]}).json()["previews"][page_id]
    assert "cells" not in preview


def test_sending_the_page_to_the_display_delivers_its_rich_cells(api):
    client, _ = api
    page_id = _create(client, device_type="panel", grid_rows=10, grid_cols=16)["id"]
    pixoo_client = SimpleNamespace(
        character_set=board_character_set(PIXOO), render=mock.MagicMock(return_value=(True, True))
    )
    service = SimpleNamespace(
        get_board_client=lambda board_id: pixoo_client if board_id == "pixoo-1" else None,
        vb_client=None,
        request_board_refresh=lambda: None,
    )

    with mock.patch("src.pages.routes.get_service", return_value=service):
        response = client.post(f"/pages/{page_id}/send", json={"target": "board", "board_id": "pixoo-1"})

    assert response.status_code == 200, response.text
    assert response.json()["sent_to_board"] is True
    grid = pixoo_client.render.call_args.args[0]
    cells = pixoo_client.render.call_args.kwargs["cells"]
    assert (len(grid), len(grid[0])) == (10, 16)
    assert [c.value for c in cells[0][:5]] == list("Hello")


def test_a_page_for_the_display_at_5x7_fits_its_8x10_grid(api):
    """At the 5x7 face the Pixoo is 8x10: the board keeps that grid and a page fits it."""
    client, service = api
    from src.settings.service import get_settings_service

    large = {**PIXOO, "id": "pixoo-large", "grid_rows": 8, "grid_cols": 10}
    get_settings_service().set_boards([HALL, large])
    (stored,) = [b for b in get_settings_service().get_board_settings().to_dict()["boards"] if b["id"] == "pixoo-large"]
    assert (stored["grid_rows"], stored["grid_cols"]) == (8, 10)

    page = service.get_page(_create(client, device_type="panel", grid_rows=8, grid_cols=10)["id"])
    assert pages_compatible_with_board(page, stored)
    assert not pages_compatible_with_board(page, PIXOO)
