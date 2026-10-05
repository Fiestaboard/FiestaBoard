"""FiestaUI's plugin-declared example models (Task 7, ``plugin-models.json``).

FiestaUI ships these as the stand-in for what an output plugin's
``output/device-models.json`` declares: an LED sign embedding its own
character set, and one FiestaPanel model per render style. Core must accept
every one of them exactly as FiestaUI's ``validateDeviceModel`` does, and a
``panel`` model that declares its size (new in the Task 7 schema) is sized
by that declaration unless the board asks for its own grid.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.outputs.fiestaui import validate_device_model
from src.outputs.geometry import model_cell_grid, resolve_content_grid

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fiestaui" / "plugin-models.json"
MODELS = {m["id"]: m for m in json.loads(FIXTURE.read_text("utf-8"))["models"]}


@pytest.mark.parametrize("model_id", sorted(MODELS))
def test_every_plugin_declared_model_validates_against_the_vendored_schema(model_id):
    assert validate_device_model(MODELS[model_id]) == []


def test_a_panel_model_that_declares_its_size_is_sized_by_it():
    assert model_cell_grid(MODELS["fiestapanel_split_flap"]) == (12, 29)


def test_a_panel_model_without_a_declared_size_is_still_sized_per_board():
    assert model_cell_grid({"id": "p", "geometry": {"kind": "panel"}}) is None


def test_a_board_on_a_declared_panel_needs_no_geometry_of_its_own():
    assert resolve_content_grid(MODELS["fiestapanel_split_flap"], None, None) == (12, 29)


def test_a_boards_own_grid_wins_over_the_panels_declared_size():
    assert resolve_content_grid(MODELS["fiestapanel_split_flap"], None, {"rows": 6, "cols": 22}) == (6, 22)
