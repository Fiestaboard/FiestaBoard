"""Core owns rich projection and deduplication; the output plugin only accepts frames."""

from contextlib import ExitStack

import pytest
from plugins.fiestapanel import FiestaPanelOutput

from src.canvas.layer import CanvasLayer
from src.outputs.cells import frame_layers, project_for_output
from src.outputs.first_party import first_party_source
from src.outputs.plugin_driver import OutputPluginDriver
from src.plugins.manifest import load_manifest


@pytest.fixture
def driver_factory():
    manifest, errors = load_manifest(first_party_source("fiestapanel").path / "manifest.json")
    assert not errors, errors
    with ExitStack() as cleanup:

        def build(*, led):
            plugin = FiestaPanelOutput("pixel-delivery", {"device_type": "panel", "grid_rows": 12, "grid_cols": 32})
            plugin.bind_manifest(manifest.output)
            plugin.bind_board(device_model=manifest.output.model(1 if led else 0), geometry=(12, 32))
            driver = OutputPluginDriver(plugin, character_set=plugin.character_set, first_party=True)
            cleanup.callback(driver.close)
            return driver

        yield build


def test_led_projection_retains_rich_text_and_pixel_layers_in_core_store(driver_factory):
    driver = driver_factory(led=True)
    red = CanvasLayer(2, 3, 1, 1, bytes([255, 0, 0, 255]))
    grid, kwargs = project_for_output(driver, "{red:a}", 12, 32, layers=[red])
    assert driver.render(grid, **kwargs) == (True, True)
    cached = driver._frames.cells
    assert cached is not None
    assert (cached[0][0].value, cached[0][0].color) == ("a", "red")
    assert frame_layers(cached) == (red,)


def test_pixel_only_changes_and_removal_are_new_frames_but_duplicates_are_not(driver_factory):
    driver = driver_factory(led=True)
    red = CanvasLayer(0, 0, 1, 1, bytes([255, 0, 0, 255]))
    blue = CanvasLayer(0, 0, 1, 1, bytes([0, 0, 255, 255]))
    for layers in ([red], [blue], []):
        grid, kwargs = project_for_output(driver, "", 12, 32, layers=layers)
        assert driver.render(grid, **kwargs) == (True, True)
        assert frame_layers(driver._frames.cells) == tuple(layers)
        assert driver.render(grid, **kwargs) == (True, False)


def test_split_flap_projection_remains_integer_text_without_layers(driver_factory):
    driver = driver_factory(led=False)
    red = CanvasLayer(0, 0, 1, 1, bytes([255, 0, 0, 255]))
    grid, kwargs = project_for_output(driver, "a{red}", 12, 32, layers=[red])
    assert kwargs == {}
    assert grid[0][:2] == [1, 63]
    assert driver.render(grid, **kwargs) == (True, True)
    assert driver._frames.characters == grid
    assert driver._frames.cells is None
