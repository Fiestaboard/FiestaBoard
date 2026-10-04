"""LED matrix rendering in core: board markup to the RGB888 frame a panel shows.

A pure-Python port (no Pillow: output plugins cannot install dependencies) of
FiestaUI's LED layer, the reference implementation (plan D15). It lives in
core so output plugins share one renderer; it reaches them through the plugin
API, versioned by ``output_api``, in a later layer. The fonts, built-in
character sets and golden fixtures are FiestaUI's data, pinned in
:mod:`src.led.provenance`.

    >>> from src.led import LedMatrixSpec, layout_message, rasterize
    >>> frame = rasterize(layout_message("{icon:sun} 72°", LedMatrixSpec(64, 64, "3x5")))
    >>> len(frame.pixels) == 64 * 64 * 3
    True

Transitions (FiestaBoard's seeded-scramble flip) are a later layer, once
FiestaUI publishes their golden sequences.
"""

from .charsets import (
    BUILTIN_CHARACTER_SETS,
    CharacterSet,
    ValidationResult,
    materialize_character_set,
    validate_character_set,
)
from .fonts import LED_FONTS, LedFont
from .matrix import (
    BOARD_COLORS,
    DEFAULT_LED_TEXT_COLOR,
    LED_GLYPHS,
    LED_MONO_COLORS,
    MAX_MATRIX_SIZE,
    MIN_MATRIX_SIZE,
    LedCell,
    LedDrawOp,
    LedFrame,
    LedGridLayout,
    LedLayout,
    LedLayoutOptions,
    LedMatrixSpec,
    LedRenderOptions,
    draw_glyph,
    frame_to_ascii,
    frame_to_bits,
    glyph_key,
    grid_layout,
    layout_cells,
    layout_message,
    led_spec_for_model,
    parse_hex_color,
    rasterize,
    resolve_hex_option,
)

__all__ = [
    "BOARD_COLORS",
    "BUILTIN_CHARACTER_SETS",
    "DEFAULT_LED_TEXT_COLOR",
    "LED_FONTS",
    "LED_GLYPHS",
    "LED_MONO_COLORS",
    "MAX_MATRIX_SIZE",
    "MIN_MATRIX_SIZE",
    "CharacterSet",
    "LedCell",
    "LedDrawOp",
    "LedFont",
    "LedFrame",
    "LedGridLayout",
    "LedLayout",
    "LedLayoutOptions",
    "LedMatrixSpec",
    "LedRenderOptions",
    "ValidationResult",
    "draw_glyph",
    "frame_to_ascii",
    "frame_to_bits",
    "glyph_key",
    "grid_layout",
    "layout_cells",
    "layout_message",
    "led_spec_for_model",
    "materialize_character_set",
    "parse_hex_color",
    "rasterize",
    "resolve_hex_option",
    "validate_character_set",
]
