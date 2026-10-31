"""Display profiles of real device models, for layout tests.

Built the way core resolves a board's display (``_profile`` over the
FiestaUI device model with the board's chosen face), so a test target draws
exactly as the device would.
"""

from __future__ import annotations

from src.fiestaui import builtin_device_models, fiestapanel_model
from src.layout.target import FlexTarget, flex_target_for
from src.led.matrix import grid_layout, model_with_led_font
from src.outputs.board_profile import model_character_set
from src.outputs.display_profile import DisplayProfile, _profile

#: The FiestaPanel LED model at a 12 x 32 grid (its pixel size follows the grid).
FIESTAPANEL_LED = "fiestapanel_led_matrix"


def profile(model_id: str, font: str | None = None) -> DisplayProfile:
    """The :class:`DisplayProfile` of built-in model ``model_id``, drawn in ``font``.

    ``font`` is the face the board chose (``"3x5"`` / ``"5x7"``); ``None``
    keeps the model's own. ``"fiestapanel_led_matrix"`` is the FiestaPanel LED
    model at 12 x 32. A pixel model's grid is the one its face lays out.
    """
    if model_id == FIESTAPANEL_LED:
        model = fiestapanel_model("led_matrix", 12, 32)
    else:
        model = builtin_device_models()[model_id]
    if font is not None:
        model = model_with_led_font(model, font)
    probe = _profile(model, model_character_set(model), None, None)
    grid = None
    if probe.width is not None and probe.height is not None:
        layout = grid_layout(probe.width, probe.height, probe.font or "5x7")
        grid = (layout.rows, layout.cols)
    return _profile(model, model_character_set(model), None, grid)


# --- the sample page and the golden devices ----------------------------------

#: The page the engine tests and the layout goldens lay out: a large centred
#: time (priority 1), a wrapped weather line with an icon and a data-driven
#: colour (priority 2) and a footer with a fill (priority 3).
#:
#: The time is ``large``, as in the spec's own example page (section 2): at
#: ``xlarge`` (half the surface) five glyphs cannot fit a 64 px Pixoo. The
#: colour reads a plain field: the template engine reserves the ``_color``
#: suffix for colour-rule lookups, which expand to ``""`` without rules (see
#: ``test_color_expression_formats_plugins_emit``).
SAMPLE = {
    "name": "Sample",
    "type": "flexible",
    "layout": {"valign": "middle", "gap": "small"},
    "blocks": [
        {
            "id": "time",
            "kind": "text",
            "text": "{{clock.time}}",
            "priority": 1,
            "style": {"size": "large", "align": "center"},
        },
        {
            "id": "weather",
            "kind": "text",
            "text": "{sun} {{weather.summary}}",
            "priority": 2,
            "style": {"color": "{{weather.tint}}", "overflow": "wrap"},
        },
        {
            "id": "footer",
            "kind": "text",
            "text": "HOME{{fill_space}}{{weather.temp}}",
            "priority": 3,
            "style": {"size": "small"},
        },
    ],
}

#: Fixed plugin data for :data:`SAMPLE`.
SAMPLE_CTX = {
    "clock": {"time": "12:45"},
    "weather": {"summary": "Sunny and warm all day", "temp": "72F", "tint": "orange"},
}

#: Golden device name -> (built-in model id, face the board chose).
GOLDEN_DEVICES = {
    "pixoo64_3x5": ("divoom_pixoo64", "3x5"),
    "pixoo64_5x7": ("divoom_pixoo64", "5x7"),
    "strip_32x8": ("ulanzi_tc001_awtrix", None),
    "hub75_64x32": ("hub75_64x32", None),
    "fiestapanel_led_192x96": (FIESTAPANEL_LED, None),
    "max7219_32x8": ("max7219_4in1", None),
    "flagship": ("vestaboard_flagship", None),
}


def golden_target(name: str) -> FlexTarget:
    """The :class:`FlexTarget` of golden device ``name`` (a key of :data:`GOLDEN_DEVICES`)."""
    model_id, font = GOLDEN_DEVICES[name]
    return flex_target_for(None, profile(model_id, font))
