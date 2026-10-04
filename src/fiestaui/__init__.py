"""FiestaUI's device data, vendored once for every part of core that needs it.

FiestaUI is the reference for what a display *is* (plan D15). This package
holds its published data, copied byte for byte from one FiestaUI commit by
``scripts/fiestaui_fixtures/vendor.sh``:

- the **DeviceModel** and **CharacterSet** JSON Schemas (validated against in
  :mod:`src.outputs.fiestaui`);
- the built-in **character sets**, flattened (made whole in
  :mod:`src.led.charsets`);
- the built-in **device models**;
- the **LED fonts** (glyph boxes and bitmaps: :mod:`src.led.fonts`,
  :mod:`src.outputs.geometry`);
- the **plugin-style example models**, of which FiestaPanel's two (one per
  render style) are FiestaBoard's own display (:func:`fiestapanel_device_models`).

``provenance.json`` names the commit and pins each file's sha256, the golden
fixtures under ``tests/fixtures/fiestaui/`` included;
``tests/test_fiestaui_vendored.py`` fails if any of them drifts.

This module is a leaf: it imports nothing from ``src``, so both the output
layer and the LED renderer can read it without importing each other.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

__all__ = [
    "CHARACTER_SET_SCHEMA_FILE",
    "DATA_DIR",
    "DEVICE_MODEL_SCHEMA_FILE",
    "builtin_character_sets",
    "builtin_device_models",
    "builtin_led_fonts",
    "fiestapanel_device_models",
    "provenance",
    "read",
]

DATA_DIR = Path(__file__).parent
DEVICE_MODEL_SCHEMA_FILE = "device-model.schema.json"
CHARACTER_SET_SCHEMA_FILE = "character-set.schema.json"


def read(filename: str) -> Any:
    """A vendored file in this package, parsed."""
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))


@cache
def provenance() -> dict[str, Any]:
    """Where the vendored files came from, and their sha256 by repo-relative path."""
    return read("provenance.json")


@cache
def builtin_character_sets() -> Mapping[str, Mapping[str, Any]]:
    """FiestaUI's built-in character sets, flattened, by id."""
    return read("character-sets.json")


@cache
def builtin_device_models() -> Mapping[str, Mapping[str, Any]]:
    """FiestaUI's built-in device models, by id."""
    return read("device-models.json")


@cache
def builtin_led_fonts() -> Mapping[str, Mapping[str, Any]]:
    """FiestaUI's LED fonts (glyph box, spacing, glyphs, icons), by id."""
    return read("led-fonts.json")


@cache
def fiestapanel_device_models() -> Mapping[str, Mapping[str, Any]]:
    """FiestaPanel's device models, by render style (``split_flap`` / ``led_matrix``).

    FiestaUI does not build these in -- ``resolveDeviceModel("fiestapanel_...")``
    throws there, as for any plugin's model -- because FiestaPanel is
    FiestaBoard's display, declared the way an output plugin declares its own:
    as documents, one per render style, carried in FiestaUI's
    ``plugin-models.json`` fixture. A client resolves them by the document.
    """
    models = read("plugin-models.json")["models"]
    return {
        model["id"].removeprefix("fiestapanel_"): model
        for model in models
        if model.get("family") == "fiestapanel" and model["id"].startswith("fiestapanel_")
    }
