"""An explicit instant request snaps an LED output instead of using its default."""

import pytest

from src.fiestaui import builtin_device_models
from src.outputs.plugin_driver import OutputPluginDriver
from tests.canvas.test_output_layers import Sign


@pytest.mark.parametrize("model", ["divoom_pixoo64", "hub75_128x64"])
@pytest.mark.parametrize(
    "strategy, expected, source",
    [
        ("instant", "none", "explicit"),
        ("none", "none", "explicit"),
        (None, "flip", "default"),
        ("flip", "flip", "explicit"),
        ("fade", "fade", "explicit"),
    ],
)
def test_led_transition_respects_explicit_instant_and_keeps_device_defaults(model, strategy, expected, source):
    plugin = Sign()
    plugin.bind_board(device_model=builtin_device_models()[model])
    driver = OutputPluginDriver(plugin)
    resolved = driver.resolve_transition(strategy)
    assert (resolved.id, resolved.source) == (expected, source)
