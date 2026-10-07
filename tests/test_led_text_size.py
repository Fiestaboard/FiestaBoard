"""Per-board LED text size: Large (5x7) or Small (3x5) on a pixel board.

An LED board measured in pixels draws as many glyphs as fit, so its face
decides its grid: a Divoom Pixoo 64 is 8 x 10 in the 5x7 face and 10 x 16 in
the 3x5 one. The board's choice lives in ``output_config.font``. Pinned here:

- **resolution** (``board_font``) — the stored choice when the model offers
  it; a board saved before the choice existed keeps the face its grid was
  sized for (an existing 10 x 16 Pixoo stays 3x5, nothing is written); else
  the model's own face, with a warning for a value the model does not offer;
- **new boards** get the model's new-board default (Pixoo: 5x7, 8 x 10) and
  the face is written into ``output_config``;
- **switching** rewrites the grid from the face, whatever grid the client
  echoes; ``PUT /settings/board`` releases the board's frames before its
  client is rebuilt, moves pages sized for the old grid onto the new one, and
  reports the references that no longer fit;
- **plugins** see the new size and face on the very next render, and a result
  cached for the old size is never served for the new one.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.devices import BoardContext
from src.fiestaui import builtin_device_models
from src.plugins.base import PluginBase, PluginResult
from src.plugins.loader import PluginLoader

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"
URL = f"/outputs/{PLUGIN_ID}/boards"
PIXOO = builtin_device_models()["divoom_pixoo64"]


def _install(root: Path, *, character_set: bool) -> Path:
    """The recording output offering the built-in Pixoo 64 (which offers both
    faces). Without *character_set* it declares none, so the board's set
    follows its face as the real Pixoo output's does."""
    target = root / PLUGIN_ID
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("__pycache__"))
    models_path = target / "output" / "device-models.json"
    models = json.loads(models_path.read_text("utf-8"))
    models_path.write_text(json.dumps([models[0], "divoom_pixoo64"]), "utf-8")
    if not character_set:
        manifest_path = target / "manifest.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        del manifest["output"]["character_set"]
        manifest["data_files"] = ["output/device-models.json"]
        manifest_path.write_text(json.dumps(manifest), "utf-8")
        (target / "output" / "character-set.json").unlink()
    return root


@pytest.fixture
def pixoo_output(tmp_path):
    loader = PluginLoader(plugins_dir=_install(tmp_path / "plugins", character_set=False), external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


@pytest.fixture
def declared_set_output(tmp_path):
    loader = PluginLoader(plugins_dir=_install(tmp_path / "plugins", character_set=True), external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


@pytest.fixture
def runtime():
    """The display engine's two hooks, recorded in one call order."""
    calls = mock.Mock()
    with (
        mock.patch("src.settings.routes.release_board_frames", calls.release),
        mock.patch("src.settings.routes.reinitialize_board_clients", calls.rebuild),
        mock.patch("src.outputs.routes.reinitialize_board_clients"),
    ):
        yield calls


@pytest.fixture
def client(runtime):
    from src.api_server import app

    return TestClient(app)


def _settings():
    from src.settings.service import get_settings_service

    return get_settings_service()


def _pages():
    from src.pages.service import get_page_service

    return get_page_service()


def _stored(board_id: str) -> dict:
    (board,) = [b for b in _settings().get_board_settings().boards if b["id"] == board_id]
    return board


def _board(**overrides) -> dict:
    """A Pixoo board dict as settings stores it."""
    return {
        "id": "pixoo-1",
        "name": "Kitchen sign",
        "output": PLUGIN_ID,
        "device_model": "divoom_pixoo64",
        "device_type": "panel",
        "grid_rows": 10,
        "grid_cols": 16,
        "output_config": {"host": "192.0.2.50"},
        **overrides,
    }


def _create(client, **config) -> str:
    response = client.post(
        URL,
        json={
            "name": "Kitchen sign",
            "device_model": "divoom_pixoo64",
            "output_config": {"host": "192.0.2.50", **config},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _switch(client, board_id: str, font: str, **echo) -> dict:
    """Change one board's face the way the settings page does: echo GET, edit, PUT."""
    boards = client.get("/settings/board").json()["boards"]
    for board in boards:
        if board["id"] == board_id:
            board["output_config"] = {**board["output_config"], "font": font}
            board.update(echo)
    response = client.put("/settings/board", json={"boards": boards})
    assert response.status_code == 200, response.text
    return response.json()


def _page(rows: int, cols: int, name: str = "Weather") -> str:
    from src.pages.models import PageCreate

    page = _pages().create_page(
        PageCreate(name=name, type="template", device_type="panel", grid_rows=rows, grid_cols=cols, template=["HI"])
    )
    return page.id


def _probe_page() -> str:
    from src.pages.models import PageCreate

    page = PageCreate(
        name="Probe", type="template", device_type="panel", grid_rows=10, grid_cols=16, template=["{{probe.value}}"]
    )
    return _pages().create_page(page).id


def _page_grid(page_id: str) -> tuple:
    page = _pages().get_page(page_id)
    return page.device_type, page.grid_rows, page.grid_cols


# --- resolution ---------------------------------------------------------------------------------


class TestBoardFont:
    def test_a_board_saved_before_the_choice_keeps_the_3x5_face_its_grid_was_sized_for(self, pixoo_output):
        from src.outputs.board_profile import board_character_set, board_font, board_profile

        board = _board()
        assert board_font(board, PIXOO) == "3x5"
        assert board_profile(board).charset == "led_3x5"
        assert board_character_set(board)["id"] == "led_3x5"

    def test_a_board_saved_before_the_choice_at_8x10_is_the_5x7_face(self, pixoo_output):
        from src.outputs.board_profile import board_font

        assert board_font(_board(grid_rows=8, grid_cols=10), PIXOO) == "5x7"

    def test_a_board_whose_grid_fits_no_face_draws_the_models_own(self, pixoo_output):
        from src.outputs.board_profile import board_font

        assert board_font(_board(grid_rows=6, grid_cols=22), PIXOO) == "3x5"

    def test_a_board_that_chose_5x7_draws_as_the_5x7_model(self, pixoo_output):
        from src.outputs.board_profile import board_character_set, board_device_model, board_profile

        board = _board(output_config={"host": "192.0.2.50", "font": "5x7"})
        model = board_device_model(board)
        assert (model["font"], model["charset"]) == ("5x7", "led_5x7")
        assert board_profile(board).charset == "led_5x7"
        assert board_character_set(board)["id"] == "led_5x7"

    def test_a_face_the_model_does_not_offer_falls_back_to_its_own_with_a_warning(self, pixoo_output, caplog):
        from src.outputs.board_profile import board_font

        with caplog.at_level(logging.WARNING, logger="src.outputs.board_profile"):
            font = board_font(_board(output_config={"host": "192.0.2.50", "font": "9x9"}), PIXOO)
        assert font == "3x5"
        messages = [r.getMessage() for r in caplog.records]
        assert any("divoom_pixoo64" in m and "5x7, 3x5" in m for m in messages), caplog.text
        # output_config can hold secrets: the stored value itself is never logged.
        assert not any("9x9" in m for m in messages), caplog.text

    def test_an_output_that_declares_its_own_character_set_keeps_that_sets_face(self, declared_set_output):
        from src.outputs.board_profile import board_device_model, board_profile

        board = _board(output_config={"host": "192.0.2.50", "font": "5x7"})
        assert board_device_model(board)["font"] == "3x5"
        assert board_profile(board).charset == "recording_sign_v1"

    def test_a_split_flap_board_has_no_face(self):
        from src.outputs.board_profile import board_font

        assert board_font({"device_type": "flagship"}, builtin_device_models()["vestaboard_flagship"]) is None


class TestPreviewFields:
    def test_a_board_on_its_models_own_face_sends_no_model_document(self, pixoo_output):
        from src.outputs.board_profile import board_led_layout, board_model_spec

        assert board_model_spec(_board()) is None
        assert board_led_layout(_board())["font"] == "3x5"

    def test_a_board_on_the_other_face_sends_the_model_it_draws_as(self, pixoo_output):
        from src.outputs.board_profile import board_led_layout, board_model_spec

        board = _board(grid_rows=8, grid_cols=10, output_config={"host": "192.0.2.50", "font": "5x7"})
        spec = board_model_spec(board)
        assert spec is not None and (spec["id"], spec["font"], spec["charset"]) == ("divoom_pixoo64", "5x7", "led_5x7")
        assert board_led_layout(board) == {"tile_gap": "gap", "block_padding": 0, "font": "5x7"}

    def test_the_settings_api_exposes_the_model_document_and_the_face(self, pixoo_output, client):
        board_id = _create(client)
        (board,) = [b for b in client.get("/settings/board").json()["boards"] if b["id"] == board_id]
        assert board["device_model_spec"]["font"] == "5x7"
        assert board["led_layout"]["font"] == "5x7"
        assert board["charset"] == "led_5x7"


# --- a new board --------------------------------------------------------------------------------


class TestCreate:
    def test_a_new_pixoo_board_is_large_8x10_with_its_face_written_down(self, pixoo_output, client):
        response = client.post(
            URL,
            json={"name": "Kitchen sign", "device_model": "divoom_pixoo64", "output_config": {"host": "192.0.2.50"}},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert (body["rows"], body["cols"], body["charset"]) == (8, 10, "led_5x7")
        stored = _stored(body["id"])
        assert stored["output_config"]["font"] == "5x7"
        assert (stored["grid_rows"], stored["grid_cols"]) == (8, 10)

    def test_a_new_board_may_choose_the_small_face(self, pixoo_output, client):
        board_id = _create(client, font="3x5")
        stored = _stored(board_id)
        assert stored["output_config"]["font"] == "3x5"
        assert (stored["grid_rows"], stored["grid_cols"]) == (10, 16)

    def test_a_new_board_asking_for_a_face_the_model_does_not_offer_gets_the_default(self, pixoo_output, client):
        board_id = _create(client, font="9x9")
        stored = _stored(board_id)
        assert stored["output_config"]["font"] == "5x7"
        assert (stored["grid_rows"], stored["grid_cols"]) == (8, 10)


# --- switching ----------------------------------------------------------------------------------


class TestSwitch:
    def test_the_grid_follows_the_face_even_when_the_client_echoes_the_old_grid(self, pixoo_output, client):
        board_id = _create(client, font="3x5")
        _switch(client, board_id, "5x7", grid_rows=10, grid_cols=16)
        assert (_stored(board_id)["grid_rows"], _stored(board_id)["grid_cols"]) == (8, 10)
        _switch(client, board_id, "3x5", grid_rows=8, grid_cols=10)
        assert (_stored(board_id)["grid_rows"], _stored(board_id)["grid_cols"]) == (10, 16)

    def test_a_legacy_board_resaved_without_a_face_keeps_its_grid_and_writes_nothing(self, pixoo_output, client):
        _settings().set_boards([_board()])
        boards = client.get("/settings/board").json()["boards"]
        assert client.put("/settings/board", json={"boards": boards}).status_code == 200
        stored = _stored("pixoo-1")
        assert (stored["grid_rows"], stored["grid_cols"]) == (10, 16)
        assert "font" not in stored["output_config"]

    def test_pages_sized_for_the_old_grid_follow_the_board_both_ways(self, pixoo_output, client):
        board_id = _create(client, font="3x5")
        page_id = _page(10, 16)
        other = _page(6, 22, name="Flagship page")
        body = _switch(client, board_id, "5x7")
        assert _page_grid(page_id) == ("panel", 8, 10)
        assert _page_grid(other) == ("panel", 6, 22)
        assert [p["page_id"] for p in body["retargeted_pages"]] == [page_id]
        _switch(client, board_id, "3x5")
        assert _page_grid(page_id) == ("panel", 10, 16)

    def test_pages_stay_when_another_board_still_has_the_old_size(self, pixoo_output, client):
        first = _create(client, font="3x5")
        _create(client, font="3x5")
        page_id = _page(10, 16)
        _settings().set_active_page_id(page_id, board_id=first)
        body = _switch(client, first, "5x7")
        assert _page_grid(page_id) == ("panel", 10, 16)
        assert body["retargeted_pages"] == []
        assert [(r["page_id"], r["surface"], r["board_id"]) for r in body["incompatible_references"]] == [
            (page_id, "active_page", first)
        ]

    def test_a_switched_board_releases_its_frames_before_its_client_is_rebuilt(self, pixoo_output, client, runtime):
        board_id = _create(client, font="3x5")
        runtime.reset_mock()
        _switch(client, board_id, "5x7")
        assert runtime.mock_calls == [mock.call.release(board_id), mock.call.rebuild()]

    def test_a_save_that_resizes_nothing_releases_nothing(self, pixoo_output, client, runtime):
        board_id = _create(client, font="3x5")
        runtime.reset_mock()
        body = _switch(client, board_id, "3x5")
        assert runtime.mock_calls == [mock.call.rebuild()]
        assert body["retargeted_pages"] == [] and body["incompatible_references"] == []

    def test_the_output_plugin_is_rebuilt_on_the_5x7_model(self, pixoo_output, client):
        from src.main import DisplayService
        from src.outputs.display_profile import display_profile_for_client
        from src.outputs.registry import output_registry

        board_id = _create(client, font="3x5")
        before = dict(_stored(board_id))
        _switch(client, board_id, "5x7")
        after = _stored(board_id)
        assert DisplayService._config_signature(before) != DisplayService._config_signature(after)
        driver = output_registry().get(PLUGIN_ID).build(after)
        assert driver.plugin.device_model["font"] == "5x7"
        assert driver.plugin.character_set["id"] == "led_5x7"
        assert driver.plugin.board_geometry == (8, 10)
        profile = display_profile_for_client(driver)
        assert (profile.font, profile.charset, profile.rows, profile.cols) == ("5x7", "led_5x7", 8, 10)


# --- what plugins see ---------------------------------------------------------------------------

PROBE_MANIFEST = {
    "id": "probe",
    "name": "Probe",
    "version": "1.0.0",
    "settings_schema": {
        "type": "object",
        "properties": {"refresh_seconds": {"type": "integer", "default": 300, "minimum": 10}},
    },
}


class ProbePlugin(PluginBase):
    """Records every board it is rendered for; each fetch answers a new value."""

    def __init__(self):
        super().__init__(PROBE_MANIFEST)
        self._enabled = True
        self.seen: list[BoardContext] = []

    @property
    def plugin_id(self) -> str:
        return "probe"

    def fetch_data(self) -> PluginResult:
        self.seen.append(self.board)
        return PluginResult(available=True, data={"value": f"FETCH {len(self.seen)}"})


@pytest.fixture
def probe(monkeypatch):
    from src.plugins.registry import get_plugin_registry

    registry = get_plugin_registry()
    plugin = ProbePlugin()
    monkeypatch.setitem(registry._plugins, "probe", plugin)
    monkeypatch.setitem(registry._enabled, "probe", True)
    return plugin


class TestPluginContract:
    def _preview(self, client, board_id: str, page_id: str) -> str:
        response = client.post("/pages/preview/batch", json={"page_ids": [page_id], "board_id": board_id})
        assert response.status_code == 200, response.text
        return response.json()["previews"][page_id]["message"]

    def test_a_plugin_sees_the_new_size_and_face_after_a_switch_and_never_its_old_result(
        self, pixoo_output, client, probe
    ):
        board_id = _create(client, font="3x5")
        page_id = _probe_page()

        first = self._preview(client, board_id, page_id)
        seen = probe.seen[-1]
        assert (seen.rows, seen.cols, seen.display.charset, seen.display.font) == (10, 16, "led_3x5", "3x5")

        _switch(client, board_id, "5x7")
        second = self._preview(client, board_id, page_id)
        seen = probe.seen[-1]
        assert (seen.rows, seen.cols) == (8, 10)
        assert (seen.display.charset, seen.display.font) == ("led_5x7", "5x7")
        assert len(probe.seen) == 2, "the 10x16 result was served for the 8x10 board"
        assert "FETCH 1" in first and "FETCH 2" in second

    def test_the_engine_path_renders_the_page_at_the_new_grid_for_the_rebuilt_client(self, pixoo_output, client, probe):
        from src.outputs.display_profile import render_kw
        from src.outputs.registry import output_registry

        board_id = _create(client, font="3x5")
        page_id = _probe_page()
        _switch(client, board_id, "5x7")
        driver = output_registry().get(PLUGIN_ID).build(_stored(board_id))
        result = _pages().preview_page(page_id, force_refresh=True, **render_kw(driver))
        assert result.available
        seen = probe.seen[-1]
        assert (seen.rows, seen.cols, seen.display.font, seen.display.charset) == (8, 10, "5x7", "led_5x7")

    def test_the_template_editor_preview_renders_at_the_boards_new_grid_and_face(self, pixoo_output, client, probe):
        board_id = _create(client, font="3x5")
        _switch(client, board_id, "5x7")
        response = client.post("/templates/render", json={"template": ["{{probe.value}}"], "board_id": board_id})
        assert response.status_code == 200, response.text
        seen = probe.seen[-1]
        assert (seen.rows, seen.cols, seen.display.font) == (8, 10, "5x7")


# --- the profile and the key plugins cache on ---------------------------------------------------


class TestDisplayProfile:
    def _profile(self, font: str):
        from src.outputs.display_profile import display_profile_for_board

        grid = {"5x7": (8, 10), "3x5": (10, 16)}[font]
        return display_profile_for_board(
            _board(grid_rows=grid[0], grid_cols=grid[1], output_config={"host": "192.0.2.50", "font": font})
        )

    def test_the_profile_names_the_face_and_its_key_changes_with_it(self, pixoo_output):
        large, small = self._profile("5x7"), self._profile("3x5")
        assert (large.font, small.font) == ("5x7", "3x5")
        assert large.key.split("|")[-1] == "5x7" and small.key.split("|")[-1] == "3x5"
        assert large.key != small.key

    def test_the_ai_brief_states_the_grid_and_the_face(self, pixoo_output):
        brief = self._profile("5x7").ai_brief()
        assert "8 rows of 10 characters" in brief
        assert "large 5x7" in brief
        assert "small 3x5" in self._profile("3x5").ai_brief()

    def test_a_split_flap_profile_has_no_face(self):
        from src.outputs.display_profile import DisplayProfile

        assert DisplayProfile().font is None


class TestBoardContextKey:
    def test_the_public_key_is_the_one_core_caches_plugin_results_on(self, pixoo_output):
        from src.outputs.display_profile import display_profile_for_board

        display = display_profile_for_board(_board())
        for board in (
            BoardContext.from_device_type("flagship"),
            BoardContext("panel", rows=10, cols=16),
            BoardContext("panel", rows=10, cols=16, display=display),
        ):
            assert board.key == PluginBase._cache_key(board)

    def test_the_key_changes_with_the_face(self, pixoo_output):
        from src.outputs.display_profile import display_profile_for_board

        small = BoardContext("panel", rows=10, cols=16, display=display_profile_for_board(_board()))
        large = BoardContext(
            "panel",
            rows=8,
            cols=10,
            display=display_profile_for_board(
                _board(grid_rows=8, grid_cols=10, output_config={"host": "192.0.2.50", "font": "5x7"})
            ),
        )
        assert small.key != large.key


class TestMcpPreview:
    def test_render_page_preview_for_a_board_hands_the_plugins_its_new_face(self, pixoo_output, client, probe):
        pytest.importorskip("mcp", reason="mcp package not installed")
        from src.mcp_server import _build_mcp_server

        board_id = _create(client, font="3x5")
        _switch(client, board_id, "5x7")
        tool = _build_mcp_server()._tool_manager._tools["render_page_preview"]
        result = tool.fn(
            template_lines=["{{probe.value}}"], device_type="panel", grid_rows=8, grid_cols=10, board_id=board_id
        )
        assert (result["rows"], result["cols"]) == (8, 10)
        seen = probe.seen[-1]
        assert (seen.rows, seen.cols, seen.display.font, seen.display.charset) == (8, 10, "5x7", "led_5x7")


class TestOutputListing:
    def _model(self, client, model_id: str) -> dict:
        (output,) = [o for o in client.get("/outputs").json() if o["id"] == PLUGIN_ID]
        (model,) = [m for m in output["device_models"] if m["id"] == model_id]
        return model

    def test_the_add_board_screen_learns_the_face_a_new_board_gets(self, pixoo_output, client):
        model = self._model(client, "divoom_pixoo64")
        assert (model["new_board_font"], model["new_board_charset"]) == ("5x7", "led_5x7")

    def test_a_model_with_no_face_choice_names_none(self, pixoo_output, client):
        model = self._model(client, "recording_sign")
        assert (model["new_board_font"], model["new_board_charset"]) == (None, None)
