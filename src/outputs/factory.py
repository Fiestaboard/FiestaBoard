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
exercises exactly the transport the saved board will use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .driver import OutputDriver


def _construct(board: dict) -> OutputDriver | None:
    # Imported lazily: the client modules import this package.
    from src.board_client import board_client_from_board_dict

    return board_client_from_board_dict(board)


def build_driver(board: dict) -> OutputDriver | None:
    """The driver for a saved board, for its live runtime.

    Returns ``None`` when the board has no usable connection (missing host,
    key or token); raises ``ValueError`` on a connection the client refuses.
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
