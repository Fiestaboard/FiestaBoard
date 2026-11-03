"""Explicit physical-pixel contracts for flexible pages; legacy grids are separate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PhysicalSurface:
    width: int
    height: int
    modes: frozenset[str]

    def __post_init__(self) -> None:
        if any(type(value) is not int or not 1 <= value <= 512 for value in (self.width, self.height)):
            raise ValueError("physical surface dimensions must be integers from 1 to 512")
        modes = frozenset(self.modes)
        if not modes or not modes <= {"ordinary", "native"}:
            raise ValueError("physical surface modes must contain ordinary or native")
        object.__setattr__(self, "modes", modes)

    def to_json(self) -> dict[str, Any]:
        return {"version": 1, "width": self.width, "height": self.height, "modes": sorted(self.modes)}


def parse_physical_frames(
    value: Any, *, api: Any, models: Mapping[str, Mapping] | None
) -> tuple[dict[str, PhysicalSurface], list[str]]:
    """Parse the API-2 declaration. Absence never promises pixel preservation."""
    if value is None:
        return {}, []
    prefix = "output.physical_frames"
    if api != 2:
        return {}, [f"{prefix} requires output_api 2"]
    if not isinstance(value, dict) or set(value) != {"version", "models"} or type(value.get("version")) is not int:
        return {}, [f"{prefix} requires version and models"]
    if value["version"] != 1:
        return {}, [f"{prefix}.version must be 1"]
    declarations = value["models"]
    if not isinstance(declarations, dict) or not 1 <= len(declarations) <= 32:
        return {}, [f"{prefix}.models must contain 1 to 32 declared pixel models"]
    parsed = {}
    errors = []
    for model_id, spec in declarations.items():
        if models is not None:
            model = models.get(model_id)
            if model is None or model.get("geometry", {}).get("kind") != "pixels":
                errors.append(f"{prefix}.models.{model_id} must name a declared pixel model")
                continue
        if not isinstance(spec, dict) or set(spec) != {"width", "height", "modes"}:
            errors.append(f"{prefix}.models.{model_id} requires width, height and modes")
            continue
        modes = spec["modes"]
        if not isinstance(modes, list) or not all(isinstance(mode, str) for mode in modes):
            errors.append(f"{prefix}.models.{model_id}.modes must be a list")
            continue
        try:
            parsed[model_id] = PhysicalSurface(spec["width"], spec["height"], frozenset(modes))
        except ValueError as exc:
            errors.append(f"{prefix}.models.{model_id}: {exc}")
    return parsed, errors


def physical_frame_layer(frame: Any, *, monochrome: str | None = None):
    """Mark a computed physical frame while retaining the existing preview encoding."""
    from src.led.page_frame import full_frame_layer

    from .physical_frame_layer import PhysicalFrameLayer

    preview = full_frame_layer(frame, monochrome=monochrome)
    return PhysicalFrameLayer(preview.x, preview.y, preview.w, preview.h, preview.rgba, frame.pixels)


def physical_frame_pixels(cells: Any, width: int, height: int) -> bytes | None:
    """Exact RGB888 for an explicitly tagged frame, else None for legacy content.

    Output API 2 adapters call this before legacy composition. A tagged frame
    with a different surface or additional layers is refused, never cropped.
    """
    from .cells import frame_layers
    from .physical_frame_layer import PhysicalFrameLayer

    layers = frame_layers(cells)
    marked = [layer for layer in layers if isinstance(layer, PhysicalFrameLayer)]
    if not marked:
        return None
    if len(layers) != 1 or len(marked) != 1 or (marked[0].w, marked[0].h) != (width, height):
        raise ValueError("physical frame does not match the declared surface")
    return marked[0].physical_rgb
