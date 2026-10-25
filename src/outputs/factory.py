"""The runtime factory: the one place a board's driver is built.

Nothing else in ``src/`` constructs a board client
(``tests/test_runtime_for_board.py`` holds that at zero). Two doors, kept
apart on purpose:

- :func:`build_driver` — for a **saved** board, called only by
  ``DisplayService`` when it builds the board's live ``BoardRuntime``. Every
  other caller that wants to write to or read from a saved board asks for
  that live runtime (``DisplayService.runtime_for(board_id)``), so all of a
  board's traffic shares one send lock, cancel token, frame cache and floor.
- :func:`draft_driver` — for **unsaved** connection details: probing
  credentials the user is still typing (``POST /config/board/test``), or
  flashing a tile that is not assigned yet (identify's override). The
  driver gets a private runtime of its own and is never bound to a live
  board's; it is thrown away after the call.

Both build the same driver from the same board dict, so a draft probe
exercises exactly the transport the saved board will use: the board resolves
to its output id (:func:`~src.outputs.registry.resolve_output_id`), and the
output registered under that id builds the driver. A board naming an output
that is not registered gets no driver — :class:`UnknownOutputError`, logged —
never a Vestaboard in its place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .registry import UnknownOutputError, definition_for, output_registry, resolve_output_id

__all__ = ["UnknownOutputError", "build_driver", "draft_driver"]

if TYPE_CHECKING:
    from .driver import OutputDriver


def _construct(board: dict) -> OutputDriver | None:
    # Output plugins register when the plugin registry loads. A board built
    # before that (the display service's first init at boot) must not be
    # refused for it: load the registry once first, so an output that is
    # merely not registered *yet* is never logged as unknown.
    if output_registry().get(resolve_output_id(board)) is None:
        _load_output_plugins()
    return definition_for(board).build(board)


def _load_output_plugins() -> bool:
    """Load the plugin registry if nothing has yet; True when it just did."""
    from src.plugins import registry

    if registry.plugin_registry_initialized():
        return False
    registry.get_plugin_registry().initialize()
    return True


def build_driver(board: dict) -> OutputDriver | None:
    """The driver for a saved board, for its live runtime.

    Returns ``None`` when the board has no usable connection (missing host,
    key or token); raises ``ValueError`` on a connection the client refuses,
    and :class:`UnknownOutputError` (a ``ValueError``) when the board names
    an output that is not registered.
    """
    return _construct(board)


def draft_driver(board: dict) -> OutputDriver | None:
    """A throwaway driver for unsaved connection details.

    It runs on a private runtime: it shares no lock, cancel token, frame
    cache or dedupe with any saved board, so it can never be mistaken for —
    or interfere with — a board's live runtime. (The send floor is keyed by
    device, so a draft write to a device a saved board also drives still
    sees that device's window.)
    """
    return _construct(board)
