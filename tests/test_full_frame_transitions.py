"""Per-cell LED transitions fall back to fade around a full-frame page (design section 6).

A grid page drawn at another text size reaches an LED board as one opaque
full-frame layer over cells projected to the board's own grid. A flip or a
cascade animates those cells, not the picture over them, so the change would
cut: the driver runs a fade instead whenever either side carries the frame.
"""

from __future__ import annotations

from src.canvas import CanvasLayer
from src.fiestaui import builtin_device_models
from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.led.matrix import model_with_led_font
from src.led.transition_registry import transitions_for_model
from src.outputs.cells import project_message
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.outputs.transitions import strategy_for_full_frame
from src.send_outcome import WriteResult

LED_5X7 = BUILTIN_CHARACTER_SETS["led_5x7"]
ROWS, COLS = 8, 10
#: A Pixoo 64 that chose the 5x7 face: 8 x 10 cells on a 64 x 64 matrix.
PIXOO_5X7 = model_with_led_font(builtin_device_models()["divoom_pixoo64"], "5x7")
#: One opaque layer over the whole matrix: what a page drawn at another face sends.
FULL = CanvasLayer(x=0, y=0, w=64, h=64, rgba=bytes([0, 0, 0, 255]) * (64 * 64))


class Sign(OutputPluginBase):
    """An LED output plugin that records the transition each change runs."""

    plugin_id = "sign"

    def __init__(self):
        super().__init__("sign", {})
        self.transitions: list = []
        self.bind_board(device_model=PIXOO_5X7, character_set=LED_5X7, geometry=(ROWS, COLS))

    def capabilities(self):
        return OutputCapabilities(
            technology="led_matrix", delivery="push", animation="stream", native_transitions=frozenset()
        )

    def device_key(self):
        return f"sign:{id(self):x}"

    def write(self, frame, *, native, cancel):
        return WriteResult(True, True)

    def write_cells(self, cells, *, native, cancel):
        return WriteResult(True, True)

    def write_transition(self, before, after, transition, *, cancel):
        self.transitions.append(transition)
        return WriteResult(True, True)


def _driver():
    plugin = Sign()
    return plugin, OutputPluginDriver(plugin, character_set=LED_5X7)


def _render(driver, message, layers=()):
    projected = project_message(message, ROWS, COLS, LED_5X7, layers=layers)
    return driver.render(projected.characters, cells=projected.cells, strategy="flip")


def test_the_board_under_test_runs_both_flip_and_fade():
    available = {entry.id for entry in transitions_for_model(PIXOO_5X7) if entry.available}
    assert {"flip", "fade"} <= available


def test_a_flip_into_a_full_frame_runs_as_fade():
    plugin, driver = _driver()
    _render(driver, "A")
    _render(driver, "B", [FULL])
    assert plugin.transitions[-1].id == "fade"


def test_a_flip_between_ordinary_frames_stays_a_flip():
    plugin, driver = _driver()
    _render(driver, "A")
    _render(driver, "B")
    assert plugin.transitions[-1].id == "flip"


# [RF4]
def test_leaving_a_full_frame_for_a_native_page_runs_as_fade():
    plugin, driver = _driver()
    _render(driver, "A", [FULL])
    _render(driver, "B")
    assert plugin.transitions[-1].id == "fade"


def test_strategy_for_full_frame_maps_per_cell_and_plugin_strategies():
    assert [strategy_for_full_frame(s) for s in ("flip", "cascade", "plugin:typewriter", "slide", None)] == [
        "fade",
        "fade",
        "fade",
        "slide",
        None,
    ]
