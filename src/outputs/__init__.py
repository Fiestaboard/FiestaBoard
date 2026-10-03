"""Outputs: the seam between FiestaBoard's display engine and the devices it drives."""

from .driver import OutputDriver
from .runtime import OutputRuntime

__all__ = ["OutputDriver", "OutputRuntime"]
