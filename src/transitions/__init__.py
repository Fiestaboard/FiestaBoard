"""Transition plugin runtime.

This package wires the transition-plugin SDK (``TransitionPluginBase``)
into the board send path.  The :class:`TransitionRunner` resolves a
plugin id to a loaded plugin instance, iterates its frame generator, and
sends each frame via the :class:`~src.board_client.BoardClient` while
honoring per-plugin caps (max frames, max runtime, min interval) and
cancellation events from concurrent sends.
"""

from .runner import TransitionResolver, TransitionRunner, TransitionRunResult

__all__ = ["TransitionResolver", "TransitionRunResult", "TransitionRunner"]
