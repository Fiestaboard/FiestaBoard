"""LED matrix rendering in core: board markup to the RGB888 frame a panel shows.

A pure-Python port (no Pillow: output plugins cannot install dependencies) of
FiestaUI's LED layer, the reference implementation (plan D15). It lives in
core so output plugins share one renderer; it reaches them through the plugin
API, versioned by ``output_api``, in a later layer. The fonts, built-in
character sets and golden fixtures are FiestaUI's data, vendored once in
:mod:`src.fiestaui` (provenance and hashes in its ``provenance.json``).

    >>> from src.led import LedMatrixSpec, layout_message, rasterize
    >>> frame = rasterize(layout_message("{icon:sun} 72°", LedMatrixSpec(64, 64, "3x5")))
    >>> len(frame.pixels) == 64 * 64 * 3
    True

Transitions (FiestaBoard's seeded-scramble flip, and cascade / slide / wipe
/ fade / dissolve) are :mod:`src.led.transitions`; which one a device runs is
:mod:`src.led.transition_registry`.
"""

from .charsets import (
    BUILTIN_CHARACTER_SETS,
    CharacterSet,
    CharacterSetError,
    ValidationResult,
    materialize_character_set,
    validate_character_set,
)
from .fonts import LED_FONTS, LedFont
from .matrix import (
    BOARD_COLORS,
    DEFAULT_LED_BLOCK_PADDING,
    DEFAULT_LED_TEXT_COLOR,
    DEFAULT_LED_TILE_GAP,
    LED_BLOCK_PADDINGS,
    LED_GLYPHS,
    LED_MONO_COLORS,
    LED_TILE_GAPS,
    MAX_MATRIX_SIZE,
    MIN_MATRIX_SIZE,
    GutterPixel,
    LedCell,
    LedDrawOp,
    LedFrame,
    LedGridLayout,
    LedLayout,
    LedLayoutChoice,
    LedLayoutOptions,
    LedMatrixSpec,
    LedRenderOptions,
    draw_glyph,
    frame_to_ascii,
    frame_to_bits,
    glyph_key,
    grid_layout,
    gutter_pixels,
    layout_cells,
    layout_message,
    layout_policy_for_model,
    led_layout_options_for_model,
    led_spec_for_model,
    paint_ops,
    parse_hex_color,
    rasterize,
    resolve_hex_option,
)
from .transition_registry import (
    LED_TRANSITIONS,
    ResolvedLedTransition,
    default_transition_id_for_model,
    resolve_led_transition,
    transition_spec_for_device,
    transitions_for_model,
)
from .transitions import (
    LED_TRANSITION_KINDS,
    LedTransition,
    LedTransitionSpec,
    led_flip_seed,
    plan_transition,
    scramble_pool,
    transition_frames,
)

__all__ = [
    "BOARD_COLORS",
    "BUILTIN_CHARACTER_SETS",
    "DEFAULT_LED_BLOCK_PADDING",
    "DEFAULT_LED_TEXT_COLOR",
    "DEFAULT_LED_TILE_GAP",
    "LED_BLOCK_PADDINGS",
    "LED_FONTS",
    "LED_GLYPHS",
    "LED_MONO_COLORS",
    "LED_TILE_GAPS",
    "LED_TRANSITIONS",
    "LED_TRANSITION_KINDS",
    "MAX_MATRIX_SIZE",
    "MIN_MATRIX_SIZE",
    "CharacterSet",
    "CharacterSetError",
    "GutterPixel",
    "LedCell",
    "LedDrawOp",
    "LedFont",
    "LedFrame",
    "LedGridLayout",
    "LedLayout",
    "LedLayoutChoice",
    "LedLayoutOptions",
    "LedMatrixSpec",
    "LedRenderOptions",
    "LedTransition",
    "LedTransitionSpec",
    "ResolvedLedTransition",
    "ValidationResult",
    "default_transition_id_for_model",
    "draw_glyph",
    "frame_to_ascii",
    "frame_to_bits",
    "glyph_key",
    "grid_layout",
    "gutter_pixels",
    "layout_cells",
    "layout_message",
    "layout_policy_for_model",
    "led_flip_seed",
    "led_layout_options_for_model",
    "led_spec_for_model",
    "materialize_character_set",
    "paint_ops",
    "parse_hex_color",
    "plan_transition",
    "rasterize",
    "resolve_hex_option",
    "resolve_led_transition",
    "scramble_pool",
    "transition_frames",
    "transition_spec_for_device",
    "transitions_for_model",
    "validate_character_set",
]
