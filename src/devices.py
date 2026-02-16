"""Device type definitions and board dimensions.

Defines the supported Vestaboard device types and their physical constraints.
"""

from typing import Literal, Dict, NamedTuple


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
