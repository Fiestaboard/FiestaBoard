"""Flexible page layout: the font registry, style resolution and the layout engine."""

from .cells import CellLayout, layout_cell_grid
from .engine import FlexRender, layout_flexible_page, named_size_scale
from .fonts import (
    DEFAULT_FONT_FAMILY,
    FONT_FAMILIES,
    MAX_TEXT_SCALE,
    NAMED_SIZES,
    FontFace,
    FontFamily,
    SizedFace,
    face_for_height,
    face_for_led_font,
    named_size_heights,
    size_ladder,
)
from .issues import ISSUE_CODES, LayoutIssue, LayoutIssueModel, layout_issues_json
from .pixels import canvas_block_op, draw_line, frame_from_ops
from .stack import Rect, StackResult, stack
from .style import (
    ResolvedLayout,
    ResolvedStyle,
    board_style_for,
    device_default_style,
    resolve_block_style,
    resolve_color_value,
    resolve_layout,
)
from .target import FlexTarget, flex_target_for

__all__ = [
    "DEFAULT_FONT_FAMILY",
    "FONT_FAMILIES",
    "ISSUE_CODES",
    "MAX_TEXT_SCALE",
    "NAMED_SIZES",
    "CellLayout",
    "FlexRender",
    "FlexTarget",
    "FontFace",
    "FontFamily",
    "LayoutIssue",
    "LayoutIssueModel",
    "Rect",
    "ResolvedLayout",
    "ResolvedStyle",
    "SizedFace",
    "StackResult",
    "board_style_for",
    "canvas_block_op",
    "device_default_style",
    "draw_line",
    "face_for_height",
    "face_for_led_font",
    "flex_target_for",
    "frame_from_ops",
    "layout_cell_grid",
    "layout_flexible_page",
    "layout_issues_json",
    "named_size_heights",
    "named_size_scale",
    "resolve_block_style",
    "resolve_color_value",
    "resolve_layout",
    "size_ladder",
    "stack",
]
