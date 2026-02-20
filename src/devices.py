"""Device type definitions and board dimensions.

Defines the supported Vestaboard device types and their physical constraints.
"""

import uuid
from typing import Literal, Dict, NamedTuple, Optional
from dataclasses import dataclass, asdict, field


DeviceType = Literal["flagship", "note"]

DEVICE_TYPES = ("flagship", "note")


class DeviceDimensions(NamedTuple):
    """Physical board dimensions for a device type."""
    rows: int
    cols: int


# Board dimensions per device type
DEVICE_DIMENSIONS: Dict[str, DeviceDimensions] = {
    "flagship": DeviceDimensions(rows=6, cols=22),
    "note": DeviceDimensions(rows=3, cols=15),
}


VALID_API_MODES = ("local", "cloud")


@dataclass
class BoardInstance:
    """A configured Vestaboard instance.
    
    Represents a single physical board with its own identity,
    device type, display color, and connection settings.
    Each board has its own API credentials and connection mode.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    device_type: str = "flagship"
    board_color: str = "black"
    enabled: bool = True
    api_mode: str = "local"
    host: str = ""
    local_api_key: str = ""
    cloud_key: str = ""
    
    def __post_init__(self):
        if self.device_type not in DEVICE_TYPES:
            self.device_type = "flagship"
        if self.board_color not in ("black", "white"):
            self.board_color = "black"
        if self.api_mode not in VALID_API_MODES:
            self.api_mode = "local"
        if not isinstance(self.enabled, bool):
            self.enabled = bool(self.enabled)
        if not self.name:
            self.name = "My Board"
    
    @property
    def is_connection_configured(self) -> bool:
        if self.api_mode == "cloud":
            return bool(self.cloud_key)
        return bool(self.local_api_key and self.host)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "BoardInstance":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            device_type=data.get("device_type", "flagship"),
            board_color=data.get("board_color", "black"),
            enabled=data.get("enabled", True),
            api_mode=data.get("api_mode", "local"),
            host=data.get("host", ""),
            local_api_key=data.get("local_api_key", ""),
            cloud_key=data.get("cloud_key", ""),
        )


def get_dimensions(device_type: str) -> DeviceDimensions:
    """Get board dimensions for a device type.
    
    Args:
        device_type: "flagship" or "note"
        
    Returns:
        DeviceDimensions with rows and cols
        
    Raises:
        ValueError: If device_type is not recognized
    """
    if device_type not in DEVICE_DIMENSIONS:
        raise ValueError(f"Unknown device type: {device_type}. Must be one of {DEVICE_TYPES}")
    return DEVICE_DIMENSIONS[device_type]


# Default device type for backward compatibility
DEFAULT_DEVICE_TYPE: DeviceType = "flagship"
