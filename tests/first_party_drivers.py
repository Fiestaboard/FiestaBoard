"""First-party board drivers for tests, built through the output-plugin path.

The Vestaboard and FiestaPanel transports are output plugins now
(``first_party_outputs/``); a board's driver is an
:class:`~src.outputs.plugin_driver.OutputPluginDriver` wrapping the plugin
instance, built by the runtime factory from a board dict — exactly as the
engine builds it. These helpers spell the board dict for the shapes tests
used to construct the old in-core clients for:

- :func:`local_driver` / :func:`cloud_driver` / :func:`note_array_cloud_driver`
  — a Vestaboard on the Local, RW Cloud or note-array Cloud API;
- :func:`tiles_driver` — a local note array driven tile by tile;
- :func:`panel_driver` — a FiestaPanel (virtual) board.

``clock`` replaces the driver's send-floor clock (the old clients'
``_time_func``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from src.outputs.factory import build_driver
from src.outputs.plugin_driver import OutputPluginDriver


def _built(board: dict, clock: Callable[[], float] | None) -> OutputPluginDriver:
    driver = build_driver(board)
    assert isinstance(driver, OutputPluginDriver), f"no driver for {board}"
    if clock is not None:
        driver._clock = clock
    return driver


def local_driver(
    api_key: str = "test_key",
    host: str = "192.168.1.100",
    *,
    port: int | None = None,
    board_id: str | None = None,
    clock: Callable[[], float] | None = None,
    device_type: str = "flagship",
) -> OutputPluginDriver:
    board: dict[str, Any] = {"api_mode": "local", "device_type": device_type, "host": host, "local_api_key": api_key}
    if port is not None:
        board["port"] = port
    if board_id is not None:
        board["id"] = board_id
    return _built(board, clock)


def cloud_driver(
    api_key: str = "test_key", *, board_id: str | None = None, clock: Callable[[], float] | None = None
) -> OutputPluginDriver:
    board: dict[str, Any] = {"api_mode": "cloud", "cloud_key": api_key}
    if board_id is not None:
        board["id"] = board_id
    return _built(board, clock)


def note_array_cloud_driver(
    token: str = "test_token",
    notes_wide: int = 1,
    notes_tall: int = 1,
    *,
    clock: Callable[[], float] | None = None,
) -> OutputPluginDriver:
    board = {
        "api_mode": "cloud",
        "device_type": "note_array",
        "note_array_token": token,
        "notes_wide": notes_wide,
        "notes_tall": notes_tall,
    }
    return _built(board, clock)


def tiles_driver(tiles: list[dict], notes_wide: int, notes_tall: int) -> OutputPluginDriver:
    board = {
        "api_mode": "local",
        "device_type": "note_array",
        "notes_wide": notes_wide,
        "notes_tall": notes_tall,
        "tiles": tiles,
    }
    return _built(board, None)


def panel_driver(
    device_type: str = "flagship",
    board_id: str | None = None,
    *,
    notes_wide: int = 1,
    notes_tall: int = 1,
    grid_rows: int | None = None,
    grid_cols: int | None = None,
) -> OutputPluginDriver:
    board: dict[str, Any] = {
        "api_mode": "virtual",
        "device_type": device_type,
        "notes_wide": notes_wide,
        "notes_tall": notes_tall,
        "grid_rows": grid_rows,
        "grid_cols": grid_cols,
    }
    if board_id is not None:
        board["id"] = board_id
    return _built(board, None)


def frames_of(driver: OutputPluginDriver) -> Any:
    """The driver's frame cache (dedupe + last frame), on its bound runtime."""
    return driver._output_runtime.frames


@contextmanager
def vestaboards_built() -> Iterator[list[dict]]:
    """Record the config of every Vestaboard plugin instance constructed inside.

    The board-credential tests' question — "which credentials did FiestaBoard
    build a Vestaboard connection from?" — asked of the plugin itself (it
    used to be asked of the in-core client's constructor).
    """
    from first_party_outputs.vestaboard import VestaboardOutput

    built: list[dict] = []
    original = VestaboardOutput.__init__

    def spy(self: Any, board_id: str | None, config: dict) -> None:
        built.append(dict(config))
        original(self, board_id, config)

    with patch.object(VestaboardOutput, "__init__", spy):
        yield built
