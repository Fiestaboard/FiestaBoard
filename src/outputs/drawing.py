"""What a display can draw (H3), as the wire describes it.

The models live here, not in ``src/v1/models.py``, so the pages domain can
answer a board's ``drawing`` too (H9c's duplicate crop report) without
importing the ``/v1`` package, which imports the pages router.
``src.v1.models`` re-exports both.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DrawingFeatures(BaseModel):
    """What the display can draw, one flag per :data:`src.outputs.display_profile.FEATURES`.

    Each is :meth:`DisplayProfile.supports` for that feature, so the editor's
    tools and the hub never disagree.
    """

    lowercase: bool = Field(description="Lowercase draws as lowercase; otherwise text is shown in capitals.")
    color_text: bool = Field(description="Colored text: {{red:HOT}} draws the word in that color.")
    background: bool = Field(description="Highlighted text: {{black/yellow:AQI}} draws words on a colored band.")
    tiles: bool = Field(description="Solid color tiles: {{red}} or {{63}} draws one colored block.")
    icons: bool = Field(description="Icons: {{icon:sun}} draws a small picture (names in drawing.icons).")
    rgb: bool = Field(description="Any color, including #rrggbb hex, not only the fixed palette.")
    solid_shapes: bool = Field(
        description="Neighboring tiles of one color join into one solid shape (seamless LED style)."
    )
    pixels: bool = Field(description="A pixel matrix: the board draws a page's pixel canvases.")


class BoardDrawing(BaseModel):
    """What a board's display can draw, for an editor choosing its tools.

    Derived from what the board's output declares (its device model and
    character set), never configured. A board whose device is unknown (its
    output plugin is not installed) reads the split-flap baseline, capitals
    and color tiles, with ``source: "baseline"``.
    """

    source: Literal["device", "baseline"] = Field(
        description=(
            '"device" when the board\'s output describes its device; "baseline" when it cannot be told (its output '
            "plugin is not installed), and the split-flap baseline is assumed."
        )
    )
    technology: str = Field(
        description='"split_flap", "led_matrix", "screen" or "unknown": the FiestaUI device model\'s technology.'
    )
    color: Literal["tiles", "rgb", "mono"] = Field(
        description='"tiles" (a split-flap\'s fixed colors), "rgb" (any color) or "mono" (one lit color).'
    )
    monochrome: str | None = Field(default=None, description="The lit color of a single-color panel; null otherwise.")
    font: str | None = Field(
        default=None,
        description=(
            'The LED text face the board draws with: "5x7" (Large) or "3x5" (Small); null off LED. Changing it is a '
            "display setting (it changes the board's grid)."
        ),
    )
    icons: list[str] = Field(default_factory=list, description="The icon names {{icon:<name>}} draws on this board.")
    pixel_width: int | None = Field(
        default=None, description="A pixel matrix's width in pixels; null on any other board."
    )
    pixel_height: int | None = Field(
        default=None, description="A pixel matrix's height in pixels; null on any other board."
    )
    features: DrawingFeatures
