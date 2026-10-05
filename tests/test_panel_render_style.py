"""FiestaPanel's render style: a panel draws as split-flap tiles or as an LED matrix.

``render_style`` is an additive panel setting (default ``split_flap``, the
only look a panel had before it existed). Each style is one FiestaUI device
model FiestaBoard declares for its own display — ``fiestapanel_split_flap``
and ``fiestapanel_led_matrix``, exactly as FiestaUI's ``plugin-models.json``
fixture carries them (vendored in ``src/fiestaui``) — so:

- ``GET /panel/{id}`` (the unauthenticated viewer config) reports the style,
  the model id and the model document, and a viewer that predates the field
  ignores three extra keys;
- the panel's board reports that model and its character set like any other
  board (``GET /settings/board``), so previews and the editor's charset
  checks follow the panel instead of reporting "unknown".
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.panels.models import Panel, PanelUpdate
from src.panels.service import PanelService
from src.panels.storage import PanelStorage

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fiestaui" / "plugin-models.json"
FIXTURE_MODELS = {m["id"]: m for m in json.loads(FIXTURE.read_text(encoding="utf-8"))["models"]}


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def panels(tmp_path):
    service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "panels.json")))
    with patch("src.panels.service.get_panel_service", return_value=service):
        yield service


def _panel_board(board_id: str = "vb-panel") -> dict:
    return {
        "id": board_id,
        "name": "Hall TV",
        "device_type": "panel",
        "api_mode": "virtual",
        "grid_rows": 12,
        "grid_cols": 29,
    }


# --- the setting ---------------------------------------------------------------------------


def test_a_panel_renders_split_flap_by_default():
    assert Panel(name="Hall TV", board_id="b1").render_style == "split_flap"


def test_render_style_accepts_led_matrix():
    assert Panel(name="Hall TV", board_id="b1", render_style="led_matrix").render_style == "led_matrix"


def test_render_style_rejects_an_unknown_style():
    with pytest.raises(ValidationError):
        Panel(name="Hall TV", board_id="b1", render_style="neon")
    with pytest.raises(ValidationError):
        PanelUpdate(render_style="neon")


def test_a_panel_stored_before_the_field_loads_as_split_flap(tmp_path):
    path = tmp_path / "panels.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "panels": [{"id": "p1", "short_code": 1, "name": "Old TV", "board_id": "b1"}],
            }
        ),
        encoding="utf-8",
    )
    assert PanelStorage(storage_file=str(path)).get("p1").render_style == "split_flap"


def test_the_default_style_is_not_written_so_old_files_round_trip(tmp_path):
    # tests/test_storage_kernel.py pins panels.json byte for byte; the
    # default is the key's absence, and only a non-default style is stored.
    path = tmp_path / "panels.json"
    storage = PanelStorage(storage_file=str(path))
    storage.create(Panel(id="flap", name="Flap TV", board_id="b1"))
    storage.create(Panel(id="led", name="LED TV", board_id="b2", render_style="led_matrix"))
    stored = {p["id"]: p for p in json.loads(path.read_text(encoding="utf-8"))["panels"]}
    assert "render_style" not in stored["flap"]
    assert stored["led"]["render_style"] == "led_matrix"


def test_patch_sets_the_render_style_and_it_persists(client, panels):
    panel = panels.storage.create(Panel(name="Hall TV", board_id="vb-panel"))
    with patch("src.panels.routes.get_panel_service", return_value=panels):
        response = client.patch(f"/panels/{panel.id}", json={"render_style": "led_matrix"})
    assert response.status_code == 200
    assert response.json()["render_style"] == "led_matrix"
    reloaded = PanelStorage(storage_file=panels.storage.storage_file)
    assert reloaded.get(panel.id).render_style == "led_matrix"


def test_patch_rejects_an_unknown_render_style(client, panels):
    panel = panels.storage.create(Panel(name="Hall TV", board_id="vb-panel"))
    with patch("src.panels.routes.get_panel_service", return_value=panels):
        response = client.patch(f"/panels/{panel.id}", json={"render_style": "neon"})
    assert response.status_code == 422


# --- the viewer config ---------------------------------------------------------------------


@pytest.mark.parametrize("style", ["split_flap", "led_matrix"])
def test_public_config_carries_the_style_and_its_model(client, panels, style):
    panel = panels.storage.create(Panel(name="Hall TV", board_id="vb-panel", render_style=style))
    with (
        patch("src.panels.routes.get_panel_service", return_value=panels),
        patch("src.panels.routes._find_board", return_value=_panel_board()),
    ):
        data = client.get(f"/panel/{panel.id}").json()
    assert data["render_style"] == style
    assert data["device_model"] == f"fiestapanel_{style}"
    assert data["device_model_spec"] == FIXTURE_MODELS[f"fiestapanel_{style}"]


def test_public_config_for_an_orphaned_panel_still_names_its_model(client, panels):
    panel = panels.storage.create(Panel(name="Hall TV", board_id="gone", render_style="led_matrix"))
    with (
        patch("src.panels.routes.get_panel_service", return_value=panels),
        patch("src.panels.routes._find_board", return_value=None),
    ):
        data = client.get(f"/panel/{panel.id}").json()
    assert data["board_missing"] is True
    assert data["device_model"] == "fiestapanel_led_matrix"


# --- the vendored models -------------------------------------------------------------------


def test_fiestapanel_models_are_fiestauis_fixture_models():
    from src.fiestaui import fiestapanel_device_models

    assert fiestapanel_device_models() == {
        "split_flap": FIXTURE_MODELS["fiestapanel_split_flap"],
        "led_matrix": FIXTURE_MODELS["fiestapanel_led_matrix"],
    }


# --- the panel's board ---------------------------------------------------------------------


def _profile(board: dict, panels: PanelService):
    from src.outputs.board_profile import board_profile

    return board_profile(board)


def test_a_split_flap_panels_board_is_the_split_flap_model(panels):
    # A panel imitates Note hardware: the heart flap, so the v2 set -- the
    # set fiestapanel_split_flap declares.
    panels.storage.create(Panel(name="Hall TV", board_id="vb-panel"))
    assert _profile(_panel_board(), panels) == ("fiestapanel_split_flap", "vestaboard_v2")


def test_a_legacy_flagship_shaped_panel_keeps_its_degree_flap(panels):
    # The code-62 rule is the board's (BoardInstance.effective_code62_glyph):
    # only a Flagship-shaped board can carry the degree flap.
    panels.storage.create(Panel(name="Hall TV", board_id="vb-panel"))
    board = {"id": "vb-panel", "device_type": "flagship", "api_mode": "virtual", "code62_glyph": "degree"}
    assert _profile(board, panels) == ("fiestapanel_split_flap", "vestaboard_v1")


def test_an_led_panels_board_is_the_led_model_and_its_font(panels):
    panels.storage.create(Panel(name="Hall TV", board_id="vb-panel", render_style="led_matrix"))
    assert _profile(_panel_board(), panels) == ("fiestapanel_led_matrix", "led_5x7")


def test_an_led_panels_board_draws_with_the_led_character_set(panels):
    from src.outputs.board_profile import board_character_set

    panels.storage.create(Panel(name="Hall TV", board_id="vb-panel", render_style="led_matrix"))
    charset = board_character_set(_panel_board())
    assert charset is not None and charset["id"] == "led_5x7"


def test_a_panel_board_reports_its_model_spec_and_a_builtin_does_not(panels):
    from src.outputs.board_profile import board_model_spec

    panels.storage.create(Panel(name="Hall TV", board_id="vb-panel", render_style="led_matrix"))
    assert board_model_spec(_panel_board()) == FIXTURE_MODELS["fiestapanel_led_matrix"]
    # A built-in model is resolved by id on the client; no document is sent.
    assert board_model_spec({"id": "v1", "device_type": "flagship", "api_mode": "local"}) is None


def test_settings_board_shows_the_panel_models_for_its_board(client, panels):
    from src.settings.service import get_settings_service

    panels.storage.create(Panel(name="Hall TV", board_id="vb-panel", render_style="led_matrix"))
    get_settings_service().set_boards([_panel_board()])
    (shown,) = client.get("/settings/board").json()["boards"]
    assert (shown["device_model"], shown["charset"]) == ("fiestapanel_led_matrix", "led_5x7")
    assert shown["device_model_spec"] == FIXTURE_MODELS["fiestapanel_led_matrix"]


def test_render_for_an_led_panel_board_checks_the_led_charset(client, panels):
    from src.settings.service import get_settings_service

    panels.storage.create(Panel(name="Hall TV", board_id="vb-panel", render_style="led_matrix"))
    get_settings_service().set_boards([_panel_board()])
    body = client.post("/templates/render", json={"template": ["HI"], "board_id": "vb-panel"}).json()
    assert body["charset"] == "led_5x7"
    assert body["charset_issues"] == []


def test_an_unreadable_panel_store_falls_back_to_split_flap():
    from src.outputs.board_profile import board_profile

    broken = SimpleNamespace(get_panel_by_board_id=lambda _id: (_ for _ in ()).throw(OSError("disk")))
    with patch("src.panels.service.get_panel_service", return_value=broken):
        assert board_profile(_panel_board())[0] == "fiestapanel_split_flap"
