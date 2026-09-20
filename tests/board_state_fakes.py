"""Deterministic stand-ins for the ``DisplayService`` surface the board-state
reader consults (#1912), shared by ``tests/test_board_state.py`` and
``tests/test_board_state_contract.py``.

The fakes model a real install faithfully in the one way that matters here:
``runtimes`` is keyed the way ``DisplayService.runtimes`` is — by settings
board id, or by the legacy ``__primary__`` sentinel for the primary board on
installs that predate per-board runtimes — and ``runtime_for`` resolves ids
exactly like ``DisplayService.runtime_for``: the id's own runtime first, the
primary runtime for the settings primary's id only when nothing is keyed
under it.
"""

from __future__ import annotations

from typing import Any

from src.virtual_board_client import VirtualBoardClient

FLAGSHIP = (6, 22)
NOTE = (3, 15)


def grid(shape: tuple[int, int], code: int) -> list[list[int]]:
    rows, cols = shape
    return [[code] * cols for _ in range(rows)]


class PhysicalClient:
    """A physical board client: last-sent cache plus a scripted live read."""

    is_virtual = False

    def __init__(self, *, last_sent=None, live=None, use_cloud=False, last_sent_at=None):
        self._last_characters = last_sent
        self.use_cloud = use_cloud
        self._live = live
        self.live_reads = 0
        if last_sent_at is not None:
            self._last_sent_at = last_sent_at

    def read_current_message(self, sync_cache: bool = False):
        self.live_reads += 1
        return self._live


class Runtime:
    """The three ``BoardRuntime`` fields the reader touches."""

    def __init__(self, client=None, polled=None, polled_at=None):
        self.client = client
        self.polled_characters = polled
        self.polled_at = polled_at


class Service:
    """Just the ``DisplayService`` surface the board-state reader touches."""

    def __init__(self, runtimes: dict[str, Runtime], primary_key: str = "b1"):
        self.runtimes = runtimes
        self._primary_key = primary_key

    @property
    def vb_client(self) -> Any:
        rt = self.runtimes.get(self._primary_key)
        return rt.client if rt is not None else None

    def runtime_for(self, board_id: str | None) -> Runtime | None:
        from src.display_runtime import get_settings_service

        if board_id is None:
            return self.runtimes.get(self._primary_key)
        rt = self.runtimes.get(board_id)
        if rt is not None:
            return rt
        if board_id == get_settings_service().get_primary_board_id():
            return self.runtimes.get(self._primary_key)
        return None

    def get_runtime(self, board_id: str) -> Runtime | None:
        return self.runtimes.get(board_id)

    def live_reads(self) -> int:
        """Network reads across every physical client (virtual memory reads are not counted)."""
        return sum(getattr(rt.client, "live_reads", 0) for rt in self.runtimes.values())


def virtual(device_type: str, *, frame=None, displayed=None, sent_at: float | None = None) -> VirtualBoardClient:
    """An anonymous (instance-local state) virtual client, optionally holding a frame.

    ``displayed`` overrides the displayed frame after the send to simulate a
    re-fit that left an old-shape frame behind; ``sent_at`` fixes the send
    time so ISO timestamps are exact.
    """
    client = VirtualBoardClient(device_type=device_type)
    if frame is not None:
        ok, sent = client.send_characters(frame)
        assert (ok, sent) == (True, True), "seed frame never landed"
        if sent_at is not None:
            client._state.last_sent_at = sent_at
    if displayed is not None:
        client._state.displayed_characters = displayed
    return client
