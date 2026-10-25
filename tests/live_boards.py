"""Install a real DisplayService whose boards have live runtimes, for route tests.

Routes write to (and read from) a board through its **live** runtime —
``DisplayService.runtime_for(board_id)`` — never through a driver they build
themselves. A route test therefore needs a service whose runtimes the
runtime factory built from saved boards. This helper is that service:
never ``initialize()``d (no poll thread), installed as the process
singleton, with the adaptive post-send refresh replaced by a counter.

Route tests that stub the board's network still need the wire stubbed
(``tests.test_wire_goldens.install_wire_recorder``); the suite's network
fence is on.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any


def live_runtimes_from(boards_source: Callable[[], list[dict]]) -> Any:
    """A stand-in service whose ``runtime_for`` answers live runtimes.

    For route tests that stub the settings service with a Mock (so a real
    ``DisplayService`` would not see their boards): each runtime's driver is
    built by the runtime factory from the board *boards_source* returns, as
    the service builds it at startup. Patch it in as the route's
    ``get_service``.
    """
    from src.outputs.factory import build_driver

    def runtime_for(board_id: str | None) -> Any:
        boards = boards_source() or []
        board = next((b for b in boards if b.get("id") == board_id), None)
        driver = build_driver(board) if board is not None else None
        return SimpleNamespace(client=driver) if driver is not None else None

    return SimpleNamespace(runtime_for=runtime_for)


def install_live_boards(boards: list[dict]) -> Any:
    """Save *boards*, build their live runtimes, and install the service."""
    import src.display_runtime as display_runtime
    from src.main import DisplayService
    from src.settings.service import get_settings_service

    get_settings_service().set_boards(boards)
    service = DisplayService()
    service._build_board_clients(sync_cache=False)
    service.refresh_requests = 0

    def _count_refresh(*_args: Any, **_kwargs: Any) -> None:
        service.refresh_requests += 1

    service.request_board_refresh = _count_refresh
    display_runtime._service = service
    return service
