"""The setup wizard's welcome card, sized for whatever device is configured.

Moved verbatim from ``src/api_server.py`` (Phase 2, Task 8) — three module
constants and one pure function that only ``POST /send-welcome-message`` has
ever used, and that had no reason to live in the app module beyond where its
one caller was declared.
"""

from __future__ import annotations

import logging

from src.devices import resolve_dimensions

logger = logging.getLogger(__name__)


# Default welcome messages, sized to fit each device's center row.
# Flagship has 22 columns; Note has 15 columns.
_DEFAULT_WELCOME_FLAGSHIP = "HIYA FROM FIESTABOARD"
_DEFAULT_WELCOME_NOTE = "HIYA FIESTA!"

# Colorful welcome template for Flagship (6 rows x 22 cols).
# Matches the welcome page in pages.json.
_WELCOME_TEMPLATE_FLAGSHIP = [
    "{{red}}{{red}}{{orange}}{{yellow}}{{orange}}{{red}}{{violet}}{{red}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{red}}{{orange}}{{red}}{{yellow}}{{violet}}{{orange}}{{red}}{{yellow}}",
    "{{orange}}{{yellow}}{{red}}{{violet}}{{yellow}}{{orange}}{{red}}{{yellow}}{{violet}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{orange}}{{red}}{{violet}}{{yellow}}{{red}}{{orange}}{{red}}",
    "{center}",
    "{{violet}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{orange}}{{red}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}{{violet}}{{red}}{{orange}}{{yellow}}{{orange}}{{red}}{{violet}}{{orange}}",
    "{{red}}{{yellow}}{{orange}}{{violet}}{{red}}{{orange}}{{red}}{{violet}}{{yellow}}{{orange}}{{violet}}{{red}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}{{red}}",
    "{{orange}}{{violet}}{{red}}{{yellow}}{{violet}}{{red}}{{orange}}{{yellow}}{{red}}{{red}}{{orange}}{{yellow}}{{violet}}{{orange}}{{red}}{{yellow}}{{orange}}{{red}}{{yellow}}{{violet}}{{red}}{{orange}}",
]

# Colorful welcome template for Note (3 rows x 15 cols).
# Two colorful border rows surround a centered text row.
_WELCOME_TEMPLATE_NOTE = [
    "{{red}}{{orange}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}",
    "{center}",
    "{{yellow}}{{orange}}{{violet}}{{red}}{{yellow}}{{orange}}{{violet}}{{red}}{{yellow}}{{orange}}{{violet}}{{red}}{{yellow}}{{orange}}{{violet}}",
]


def build_welcome_template(
    device_type: str,
    custom_msg: str,
    notes_wide: int = 1,
    notes_tall: int = 1,
) -> list:
    """Build the welcome message template for a given device type.

    Returns a list of template strings (one per row) sized appropriately
    for the device. The center row contains the welcome text, truncated to
    fit the device's column count.

    Args:
        device_type: "flagship", "note", or "note_array"
        custom_msg: Optional user-configured welcome message; when empty,
            a device-appropriate default is used.
        notes_wide: For note_array: number of notes side-by-side (default 1).
        notes_tall: For note_array: number of notes stacked (default 1).
    """
    try:
        dims = resolve_dimensions(device_type, notes_wide=notes_wide, notes_tall=notes_tall)
    except ValueError:
        dims = resolve_dimensions("flagship")

    cols = dims.cols

    if device_type == "note":
        default_msg = _DEFAULT_WELCOME_NOTE
        rows = list(_WELCOME_TEMPLATE_NOTE)
    elif device_type == "note_array":
        default_msg = _DEFAULT_WELCOME_NOTE
        # Generate a plain template: blank rows with center row carrying text
        center_idx = dims.rows // 2
        rows = [""] * dims.rows
        rows[center_idx] = "{center}"
    else:
        default_msg = _DEFAULT_WELCOME_FLAGSHIP
        rows = list(_WELCOME_TEMPLATE_FLAGSHIP)

    center_text = (custom_msg.upper() if custom_msg else default_msg)[:cols]
    if custom_msg and len(custom_msg) > cols:
        logger.debug(
            "Welcome message truncated from %d to %d characters for %s device",
            len(custom_msg),
            cols,
            device_type,
        )
    return [row.replace("{center}", center_text) for row in rows]
