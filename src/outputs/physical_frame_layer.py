"""Internal physical-frame marker, separate from the legacy Canvas coordinate space."""

from dataclasses import dataclass, field

from src.canvas.layer import CanvasLayer


@dataclass(frozen=True)
class PhysicalFrameLayer(CanvasLayer):
    """Opaque preview layer plus exact physical RGB888; never inferred from size."""

    physical_rgb: bytes = field(repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.x != 0 or self.y != 0 or any(type(n) is not int or not 1 <= n <= 512 for n in (self.w, self.h)):
            raise ValueError("physical frame must cover a positive bounded surface from the origin")
        if len(self.physical_rgb) != self.w * self.h * 3 or self.rgba[3::4].count(255) != self.w * self.h:
            raise ValueError("physical frame needs complete RGB888 and opaque preview pixels")
        object.__setattr__(self, "physical_rgb", bytes(self.physical_rgb))

    def to_json(self) -> dict:
        """Preview-only marker; exact RGB remains an internal delivery payload."""
        return {**super().to_json(), "physical_frame_version": 1}
