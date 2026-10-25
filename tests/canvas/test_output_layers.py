"""Layers reach output plugins on the rich frame (design §3 step 7): ``frame.layers``."""

from __future__ import annotations

import json
from pathlib import Path

from src.canvas import CanvasLayer
from src.fiestaui import builtin_device_models
from src.led import LedMatrixSpec, layout_message, rasterize
from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.outputs.cells import RichCells, cells_equal, cells_to_json, project_message
from src.outputs.frames import FrameCache
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.send_outcome import WriteResult

LED_3X5 = BUILTIN_CHARACTER_SETS["led_3x5"]
ROWS, COLS = 10, 16
PIXOO = builtin_device_models()["divoom_pixoo64"]
#: FiestaUI's generic 32-frame sequence player: a model that runs the flip
#: (the Pixoo 64 itself snaps).
SEQUENCE = next(
    case["pluginModel"]
    for case in json.loads((Path(__file__).parents[1] / "fixtures" / "fiestaui" / "led-golden.json").read_text())[
        "transitions"
    ]
    if case["name"] == "sequence device 32-frame budget"
)
RED = CanvasLayer(x=0, y=2, w=2, h=1, rgba=bytes([255, 0, 0, 255]) * 2)
BLUE = CanvasLayer(x=0, y=2, w=2, h=1, rgba=bytes([0, 0, 255, 255]) * 2)


def _frame(message="HELLO", layers=()):
    return project_message(message, ROWS, COLS, LED_3X5, layers=layers)


def test_a_rich_frame_is_a_list_carrying_its_layers():
    cells = _frame(layers=[RED]).cells
    assert isinstance(cells, list) and isinstance(cells, RichCells)
    assert cells.layers == (RED,)
    # An old plugin sees a plain list of rows of tokens; the JSON shape is unchanged.
    assert cells == _frame().cells
    assert cells_to_json(cells) == cells_to_json(_frame().cells)


def test_a_frame_without_layers_has_an_empty_tuple():
    assert _frame().cells.layers == ()


def test_a_split_flap_projection_has_no_cells_and_so_no_layers():
    assert project_message("HELLO", 6, 22, None, layers=[RED]).cells is None


def test_cells_equal_sees_a_layers_only_change():
    assert cells_equal(_frame(layers=[RED]).cells, _frame(layers=[RED]).cells)
    assert not cells_equal(_frame(layers=[RED]).cells, _frame(layers=[BLUE]).cells)
    assert not cells_equal(_frame(layers=[RED]).cells, _frame().cells)


def test_frame_cache_treats_a_layers_only_change_as_a_change():
    cache = FrameCache()
    red = _frame(layers=[RED])
    cache.record_sent(red.characters, cells=red.cells)
    assert cache.matches_frame(red.characters, _frame(layers=[RED]).cells)
    assert not cache.matches_frame(red.characters, _frame(layers=[BLUE]).cells)


def test_the_last_frame_store_keeps_the_layers():
    cache = FrameCache()
    red = _frame(layers=[RED])
    cache.record_sent(red.characters, cells=red.cells)
    assert cache.last_cells_shaped(ROWS, COLS).layers == (RED,)


# --- through the driver to an output plugin ---------------------------------------


class Sign(OutputPluginBase):
    plugin_id = "sign"

    def __init__(self):
        super().__init__("sign", {})
        self.calls: list[tuple] = []
        self.bind_board(device_model=SEQUENCE, character_set=LED_3X5, geometry=(ROWS, COLS))

    def capabilities(self):
        return OutputCapabilities(
            technology="led_matrix", delivery="push", animation="sequence", native_transitions=frozenset()
        )

    def device_key(self):
        return f"sign:{id(self):x}"

    def write(self, frame, *, native, cancel):
        self.calls.append(("write", frame))
        return WriteResult(True, True)

    def write_cells(self, cells, *, native, cancel):
        self.calls.append(("write_cells", cells))
        return WriteResult(True, True)

    def write_transition(self, before, after, transition, *, cancel):
        self.calls.append(("write_transition", before, after))
        return WriteResult(True, True)


def _render(driver, message, layers=()):
    projected = _frame(message, layers)
    return driver.render(projected.characters, cells=projected.cells)


def test_write_cells_receives_frame_layers_and_an_led_plugin_draws_them():
    plugin = Sign()
    driver = OutputPluginDriver(plugin, character_set=LED_3X5)
    _render(driver, "HELLO", [RED])
    name, frame = plugin.calls[-1]
    assert name == "write_cells"
    assert frame.layers == (RED,)
    # What an LED output plugin does with it: hand the layers to the renderer.
    pixels = rasterize(layout_message(frame, LedMatrixSpec(64, 64, "3x5"), layers=getattr(frame, "layers", ()))).pixels
    assert pixels[(2 * 64 + 0) * 3 : (2 * 64 + 0) * 3 + 3] == bytes([255, 0, 0])


def test_a_layers_only_change_is_sent_with_before_and_after_layers():
    plugin = Sign()
    driver = OutputPluginDriver(plugin, character_set=LED_3X5)
    _render(driver, "HELLO", [RED])
    _render(driver, "HELLO", [BLUE])
    name, before, after = plugin.calls[-1]
    assert name == "write_transition"
    assert (before.layers, after.layers) == ((RED,), (BLUE,))


def test_the_same_frame_and_layers_again_reaches_nothing():
    plugin = Sign()
    driver = OutputPluginDriver(plugin, character_set=LED_3X5)
    _render(driver, "HELLO", [RED])
    _render(driver, "HELLO", [RED])
    assert [c[0] for c in plugin.calls] == ["write_cells"]
