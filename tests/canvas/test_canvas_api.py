"""The APIs answer a pixel board's canvas layers (design §3 step 8): previews, sends, what the board shows."""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.canvas import CanvasLayer
from src.fiestaui import builtin_device_models
from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.outputs.board_profile import board_character_set
from src.outputs.cells import project_message
from src.outputs.runtime import OutputRuntime
from src.plugins.loader import PluginLoader

FIXTURE = Path(__file__).parents[1] / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"
PIXOO_MODEL = builtin_device_models()["divoom_pixoo64"]
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
CANVAS = {"id": "sun", "area": {"row": 1, "col": 1, "rows": 1, "cols": 2}, "content": {"background": "#ff0000"}}
LAYER_KEYS = {"x", "y", "width", "height", "rgba"}


@pytest.fixture
def output_plugin(tmp_path):
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
    from src.api_server import app
    from src.pages.service import PageService
    from src.pages.storage import PageStorage
    from src.settings.service import get_settings_service

    get_settings_service().set_boards([HALL, PIXOO])
    service = PageService(PageStorage(str(tmp_path / "pages.json")))
    with mock.patch("src.pages.routes.get_page_service", return_value=service):
        yield TestClient(app), service


def _create(client, **body) -> str:
    page = {"name": "Sun", "type": "template", "template": ["HELLO"], "canvases": [CANVAS], **body}
    response = client.post("/pages", json=page)
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _red(layer_json) -> bool:
    rgba = base64.b64decode(layer_json["rgba"])
    return any(rgba[i : i + 4] == bytes([255, 0, 0, 255]) for i in range(0, len(rgba), 4))


def test_the_page_api_stores_and_returns_canvases(api):
    client, _ = api
    page_id = _create(client, device_type="panel", grid_rows=10, grid_cols=16)
    assert client.get(f"/pages/{page_id}").json()["canvases"] == [
        {
            "id": "sun",
            "area": CANVAS["area"],
            "bleed": [],
            "scale": 1,
            "text": "hide",
            "content": {"background": "#ff0000", "palette": {}, "shapes": [], "pixels": []},
        }
    ]


def test_an_area_past_the_grid_is_a_422(api):
    client, _ = api
    response = client.post(
        "/pages",
        json={
            "name": "X",
            "type": "template",
            "template": ["A"],
            "canvases": [{**CANVAS, "area": {"row": 7, "col": 1, "rows": 1, "cols": 1}}],
        },
    )
    assert response.status_code == 422


def test_the_batch_preview_for_a_pixel_board_answers_layers_and_issues(api):
    client, _ = api
    page_id = _create(client, device_type="panel", grid_rows=10, grid_cols=16)
    preview = client.post("/pages/preview/batch", json={"page_ids": [page_id], "board_id": "pixoo-1"}).json()[
        "previews"
    ][page_id]
    assert [set(layer) for layer in preview["layers"]] == [LAYER_KEYS]
    assert _red(preview["layers"][0])
    assert preview["canvas_issues"] == []


def test_the_batch_preview_without_a_pixel_board_has_no_layers_key(api):
    client, _ = api
    page_id = _create(client, device_type="panel", grid_rows=10, grid_cols=16)
    preview = client.post("/pages/preview/batch", json={"page_ids": [page_id]}).json()["previews"][page_id]
    assert "layers" not in preview and "canvas_issues" not in preview
    flagship_page = _create(client)
    preview = client.post("/pages/preview/batch", json={"page_ids": [flagship_page], "board_id": "hall-1"}).json()[
        "previews"
    ][flagship_page]
    assert "layers" not in preview


def _pixoo_client():
    return SimpleNamespace(
        plugin=SimpleNamespace(device_model=PIXOO_MODEL, config={}),
        character_set=board_character_set(PIXOO),
        render=MagicMock(return_value=(True, True)),
    )


def test_sending_to_a_pixel_board_delivers_and_answers_its_layers(api):
    client, _ = api
    page_id = _create(client, device_type="panel", grid_rows=10, grid_cols=16)
    board = _pixoo_client()
    service = SimpleNamespace(
        get_board_client=lambda board_id: board if board_id == "pixoo-1" else None,
        vb_client=None,
        request_board_refresh=lambda: None,
    )
    with mock.patch("src.pages.routes.get_service", return_value=service):
        response = client.post(f"/pages/{page_id}/send", json={"target": "board", "board_id": "pixoo-1"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert _red(body["layers"][0]) and body["canvas_issues"] == []
    cells = board.render.call_args.kwargs["cells"]
    assert len(cells.layers) == 1 and cells.layers[0].to_json() == body["layers"][0]


def test_the_current_message_of_a_pixel_board_answers_the_layers_it_shows(monkeypatch):
    from src.api_server import app

    layer = CanvasLayer(x=0, y=2, w=1, h=1, rgba=bytes([255, 0, 0, 255]))
    frame = project_message("HI", 10, 16, BUILTIN_CHARACTER_SETS["led_3x5"], layers=[layer])
    output = OutputRuntime()
    output.frames.record_sent(frame.characters, cells=frame.cells)
    rt = SimpleNamespace(client=object(), output=output, polled_characters=None, polled_at=None)
    service = SimpleNamespace(vb_client=object(), runtime_for=lambda _board_id: rt)
    settings = MagicMock()
    settings.get_primary_board_id.return_value = "other"
    monkeypatch.setattr("src.outputs.display_profile.board_device_model", lambda board: PIXOO_MODEL)
    with (
        patch("src.board_api.routes.runtime.get_service", return_value=service),
        patch("src.board_api.routes.runtime.get_settings_service", return_value=settings),
        patch("src.board_api.routes._require_board", return_value=PIXOO),
    ):
        body = TestClient(app).get("/board/current-message?board_id=pixoo-1").json()
    assert body["layers"] == [layer.to_json()]


def test_the_current_message_of_a_split_flap_board_has_no_layers_key(monkeypatch):
    from src.api_server import app

    output = OutputRuntime()
    output.frames.record_sent([[1] * 22 for _ in range(6)])
    rt = SimpleNamespace(client=object(), output=output, polled_characters=None, polled_at=None)
    service = SimpleNamespace(vb_client=object(), runtime_for=lambda _board_id: rt)
    settings = MagicMock()
    settings.get_primary_board_id.return_value = "other"
    with (
        patch("src.board_api.routes.runtime.get_service", return_value=service),
        patch("src.board_api.routes.runtime.get_settings_service", return_value=settings),
        patch("src.board_api.routes._require_board", return_value=HALL),
    ):
        body = TestClient(app).get("/board/current-message?board_id=hall-1").json()
    assert "layers" not in body


def test_the_v1_board_detail_answers_a_pixel_boards_layers(api, monkeypatch):
    client, _ = api
    layer = CanvasLayer(x=0, y=2, w=1, h=1, rgba=bytes([255, 0, 0, 255]))
    frame = project_message("HI", 10, 16, BUILTIN_CHARACTER_SETS["led_3x5"], layers=[layer])
    runtime = Mock()
    runtime.output = OutputRuntime()
    runtime.output.frames.record_sent(frame.characters, cells=frame.cells)
    runtime.polled_characters = None
    runtime.polled_at = None
    runtime.client = Mock()
    service = Mock()
    service.get_runtime.return_value = runtime
    service.runtime_for.return_value = runtime
    with (
        patch("src.api_server.get_service", return_value=service),
        patch("src.display_runtime.get_service", return_value=service),
    ):
        pixel = client.get("/v1/boards/pixoo-1").json()
        flap = client.get("/v1/boards/hall-1").json()
    assert pixel["layers"] == [layer.to_json()]
    assert flap.get("layers") is None


# --- The editor's live preview: POST /templates/render with canvases ---------------------------------


def _render(client, **body):
    request = {"template": ["HELLO", "WORLD"], "device_type": "panel", "grid_rows": 10, "grid_cols": 16, **body}
    return client.post("/templates/render", json=request)


def test_template_render_with_canvases_for_a_pixel_board_answers_layers_and_issues(api):
    client, _ = api
    response = _render(client, board_id="pixoo-1", canvases=[CANVAS])
    assert response.status_code == 200, response.text
    body = response.json()
    assert [set(layer) for layer in body["layers"]] == [LAYER_KEYS]
    assert _red(body["layers"][0])
    assert body["canvas_issues"] == []


def test_template_render_with_canvases_blanks_the_cells_under_a_hide_canvas(api):
    client, _ = api
    body = _render(client, board_id="pixoo-1", canvases=[CANVAS]).json()
    # The canvas covers row 1, cols 1-2: "HELLO" loses its first two cells.
    assert body["lines"][0].startswith("  LLO") or body["lines"][0].lower().startswith("  llo")


def test_template_render_flows_text_around_a_flow_canvas(api):
    client, _ = api
    flow = {**CANVAS, "text": "flow"}
    body = _render(client, board_id="pixoo-1", canvases=[flow], line_metadata=[{"wrap": True}, {}]).json()
    assert body["lines"][0][:2] == "  "
    assert "HELLO".lower() in body["lines"][0].lower()


def test_template_render_reports_canvas_issues(api):
    client, _ = api
    broken = {**CANVAS, "source": "{{nope.canvas}}", "content": None}
    body = _render(client, board_id="pixoo-1", canvases=[broken]).json()
    assert body["layers"] is not None
    assert [issue["canvas_id"] for issue in body["canvas_issues"]] == ["sun"]


def test_template_render_with_canvases_for_a_split_flap_board_has_no_layers(api):
    client, _ = api
    response = client.post(
        "/templates/render", json={"template": ["HELLO"], "board_id": "hall-1", "canvases": [CANVAS]}
    )
    body = response.json()
    assert response.status_code == 200, response.text
    assert "layers" not in body and "canvas_issues" not in body
    assert body["lines"][0].startswith("  ")


def test_template_render_refuses_an_invalid_canvas(api):
    client, _ = api
    bad = {**CANVAS, "content": {"shapes": [{"type": "rect", "x": "oops", "y": 0, "w": 1, "h": 1}]}}
    response = _render(client, board_id="pixoo-1", canvases=[bad])
    assert response.status_code == 422
    assert "x" in response.text
