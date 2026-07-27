"""Tests for TransitionRunner and BoardClient.render() façade."""

import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.board_client import TRANSITION_PLUGIN_PREFIX, BoardClient
from src.plugins.base import TransitionFrame, TransitionPluginBase
from src.transitions.runner import TransitionRunner


@pytest.fixture(autouse=True)
def _enable_transition_plugins_beta():
    """Enable the beta flag for every render() test in this module.

    The defense-in-depth gate in :meth:`BoardClient.render` falls back to
    a non-plugin send when ``beta.transition_plugins_enabled`` is False;
    tests that exercise the plugin code path need the flag on.
    """
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    original = settings.get_beta_settings().transition_plugins_enabled
    settings.update_beta_settings({"transition_plugins_enabled": True})
    yield
    settings.update_beta_settings({"transition_plugins_enabled": original})


# ---------------------------------------------------------------------------
# Test plugins
# ---------------------------------------------------------------------------


class _SeqPlugin(TransitionPluginBase):
    """Yields a fixed list of frames (delay is the manifest min_interval_ms)."""

    def __init__(self, manifest: dict[str, Any], frames: list[TransitionFrame]):
        super().__init__(manifest)
        self._frames = frames

    @property
    def plugin_id(self) -> str:
        return self._manifest.get("id", "seq")

    def generate_frames(self, from_grid, to_grid, device, config):
        yield from self._frames


class _BareGridPlugin(TransitionPluginBase):
    """Yields raw grids without a (grid, delay) tuple wrapping."""

    def __init__(self, manifest, grids):
        super().__init__(manifest)
        self._grids = grids

    @property
    def plugin_id(self) -> str:
        return self._manifest.get("id", "bare")

    def generate_frames(self, from_grid, to_grid, device, config):
        yield from self._grids  # bare grid, no delay


class _RaisingPlugin(TransitionPluginBase):
    @property
    def plugin_id(self) -> str:
        return "boom"

    def generate_frames(self, from_grid, to_grid, device, config):
        if False:
            yield  # mark as generator function
        raise RuntimeError("plugin exploded")


class _ForeverPlugin(TransitionPluginBase):
    """Yields an unbounded stream of frames -- used to test caps + cancel."""

    @property
    def plugin_id(self) -> str:
        return "forever"

    def generate_frames(self, from_grid, to_grid, device, config):
        n = 0
        while True:
            n += 1
            yield to_grid, 5


# ---------------------------------------------------------------------------
# Mock board client
# ---------------------------------------------------------------------------


class _FakeBoard:
    """Minimal stand-in for BoardClient that records sends."""

    def __init__(self, cached: list[list[int]] | None = None, read: list[list[int]] | None = None):
        self.sent: list[list[list[int]]] = []
        self._last_characters = cached
        self._read_result = read
        self.fail_after = None  # if set, the Nth send raises

    def send_characters(self, characters, strategy=None, force=False, **kwargs):
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise RuntimeError("send blew up")
        self.sent.append([list(r) for r in characters])
        self._last_characters = [list(r) for r in characters]
        return (True, True)

    def read_current_message(self):
        return self._read_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manifest(plugin_id: str, **transition_settings) -> dict[str, Any]:
    return {
        "id": plugin_id,
        "name": plugin_id,
        "version": "1.0.0",
        "plugin_type": "transition",
        "transition_settings": transition_settings,
    }


def _grid(value: int) -> list[list[int]]:
    """6x22 flagship grid filled with *value*."""
    return [[value] * 22 for _ in range(6)]


# ---------------------------------------------------------------------------
# Runner: basic flow
# ---------------------------------------------------------------------------


def test_run_drives_frames_and_snaps_to_target():
    target = _grid(1)
    frames = [(_grid(0), 0), (_grid(2), 0), (_grid(3), 0)]
    plugin = _SeqPlugin(_manifest("seq", min_interval_ms=0), frames)
    runner = TransitionRunner(lambda pid: plugin if pid == "seq" else None)

    board = _FakeBoard()
    success, was_sent = runner.run(
        plugin_id="seq",
        to_grid=target,
        board_client=board,
        cancel_event=threading.Event(),
    )

    assert success
    assert was_sent
    # 3 plugin frames + 1 final snap to target
    assert len(board.sent) == 4
    assert board.sent[-1] == target


def test_run_falls_back_to_blank_when_no_cache_or_read():
    """When the board has no cached state and read returns None, from_grid is blank."""
    captured = []

    class _CapturePlugin(TransitionPluginBase):
        @property
        def plugin_id(self):
            return "cap"

        def generate_frames(self, from_grid, to_grid, device, config):
            captured.append(from_grid)
            yield to_grid, 0

    plugin = _CapturePlugin(_manifest("cap", min_interval_ms=0))
    runner = TransitionRunner(lambda pid: plugin)

    board = _FakeBoard(cached=None, read=None)
    runner.run(plugin_id="cap", to_grid=_grid(1), board_client=board)

    assert captured and captured[0] == _grid(0)


def test_run_uses_cached_grid_as_from():
    captured = []

    class _CapturePlugin(TransitionPluginBase):
        @property
        def plugin_id(self):
            return "cap"

        def generate_frames(self, from_grid, to_grid, device, config):
            captured.append(from_grid)
            yield to_grid, 0

    plugin = _CapturePlugin(_manifest("cap", min_interval_ms=0))
    runner = TransitionRunner(lambda pid: plugin)
    board = _FakeBoard(cached=_grid(7))
    runner.run(plugin_id="cap", to_grid=_grid(1), board_client=board)
    assert captured[0] == _grid(7)


def test_run_does_not_call_read_current_message_when_cache_empty():
    """Runner no longer falls back to a live board read.

    Previously ``_resolve_from_grid`` invoked ``read_current_message`` as a
    last-ditch fallback before the blank grid.  That added a network
    round-trip under the send lock for a value the isinstance check
    typically rejected.  Now we go straight from missing cache to a
    blank grid.
    """
    captured = []

    class _CapturePlugin(TransitionPluginBase):
        @property
        def plugin_id(self):
            return "cap"

        def generate_frames(self, from_grid, to_grid, device, config):
            captured.append(from_grid)
            yield to_grid, 0

    plugin = _CapturePlugin(_manifest("cap", min_interval_ms=0))
    runner = TransitionRunner(lambda pid: plugin)

    read_calls = []

    class _ReadTrackingBoard(_FakeBoard):
        def read_current_message(self):
            read_calls.append(True)
            return _grid(9)

    board = _ReadTrackingBoard(cached=None)
    runner.run(plugin_id="cap", to_grid=_grid(1), board_client=board)
    assert captured[0] == _grid(0)  # blank fallback, not the read result
    assert read_calls == []  # read_current_message is never invoked


def test_run_unknown_plugin_snaps_to_target():
    runner = TransitionRunner(lambda pid: None)
    board = _FakeBoard()
    success, was_sent = runner.run(plugin_id="ghost", to_grid=_grid(4), board_client=board)
    assert success and was_sent
    assert board.sent == [_grid(4)]


def test_run_handles_bare_grid_yield():
    plugin = _BareGridPlugin(_manifest("bare", min_interval_ms=0), [_grid(1), _grid(2)])
    runner = TransitionRunner(lambda pid: plugin)
    board = _FakeBoard()
    runner.run(plugin_id="bare", to_grid=_grid(3), board_client=board)
    # 2 bare frames + 1 snap
    assert [s[0][0] for s in board.sent] == [1, 2, 3]


def test_run_aborts_when_plugin_raises():
    plugin = _RaisingPlugin(_manifest("boom"))
    runner = TransitionRunner(lambda pid: plugin)
    board = _FakeBoard()
    success, was_sent = runner.run(plugin_id="boom", to_grid=_grid(1), board_client=board)
    # Snap to target still happens
    assert success and was_sent
    assert board.sent == [_grid(1)]


def test_run_skips_malformed_frame_and_snaps():
    class _Garbage(TransitionPluginBase):
        @property
        def plugin_id(self):
            return "g"

        def generate_frames(self, from_grid, to_grid, device, config):
            yield ("not", "a", "tuple")  # malformed

    plugin = _Garbage(_manifest("g"))
    runner = TransitionRunner(lambda pid: plugin)
    board = _FakeBoard()
    runner.run(plugin_id="g", to_grid=_grid(5), board_client=board)
    # Plugin frames rejected; only snap reaches the board
    assert board.sent == [_grid(5)]


# ---------------------------------------------------------------------------
# Runner: caps & cancellation
# ---------------------------------------------------------------------------


def test_max_frames_cap_aborts_generator():
    plugin = _ForeverPlugin(_manifest("forever", min_interval_ms=0, max_frames=4))
    runner = TransitionRunner(lambda pid: plugin)
    board = _FakeBoard()
    runner.run(plugin_id="forever", to_grid=_grid(1), board_client=board)
    # 4 plugin frames + 1 snap
    assert len(board.sent) == 5


def test_max_runtime_seconds_cap_aborts():
    plugin = _ForeverPlugin(_manifest("forever", min_interval_ms=20, max_frames=10000, max_runtime_seconds=1))
    runner = TransitionRunner(lambda pid: plugin)
    board = _FakeBoard()
    start = time.monotonic()
    runner.run(plugin_id="forever", to_grid=_grid(1), board_client=board)
    elapsed = time.monotonic() - start
    # Should give up close to the 1s cap, not run forever.
    assert elapsed < 3.0
    assert len(board.sent) >= 2  # at least one plugin frame plus snap


def test_cancel_event_stops_iteration():
    plugin = _ForeverPlugin(_manifest("forever", min_interval_ms=50, max_frames=10000))
    runner = TransitionRunner(lambda pid: plugin)
    board = _FakeBoard()
    cancel = threading.Event()

    def fire_cancel():
        time.sleep(0.1)
        cancel.set()

    t = threading.Thread(target=fire_cancel)
    t.start()
    runner.run(
        plugin_id="forever",
        to_grid=_grid(1),
        board_client=board,
        cancel_event=cancel,
    )
    t.join()
    # Cancel should fire well before the default 120s cap; sends remain small.
    assert len(board.sent) < 50


def test_non_interruptible_ignores_cancel_event():
    plugin = _ForeverPlugin(
        _manifest(
            "forever",
            min_interval_ms=0,
            max_frames=3,  # rely on cap so the test terminates
            interruptible=False,
        )
    )
    runner = TransitionRunner(lambda pid: plugin)
    board = _FakeBoard()
    cancel = threading.Event()
    cancel.set()  # pre-set; runner should still iterate to the cap
    runner.run(
        plugin_id="forever",
        to_grid=_grid(1),
        board_client=board,
        cancel_event=cancel,
    )
    # 3 plugin frames (cap) + 1 snap
    assert len(board.sent) == 4


def test_min_interval_ms_floor_is_enforced():
    plugin = _SeqPlugin(
        _manifest("seq", min_interval_ms=50, max_frames=5),
        [(_grid(1), 0), (_grid(2), 0)],  # plugin yields 0 ms
    )
    runner = TransitionRunner(lambda pid: plugin)
    board = _FakeBoard()
    start = time.monotonic()
    runner.run(plugin_id="seq", to_grid=_grid(3), board_client=board)
    elapsed = time.monotonic() - start
    # Two 50ms sleeps minimum (one after each plugin frame).
    assert elapsed >= 0.09


# ---------------------------------------------------------------------------
# BoardClient.render() façade
# ---------------------------------------------------------------------------


def _build_board_client() -> BoardClient:
    bc = BoardClient(api_key="k", host="h", use_cloud=False)
    # Stub the actual HTTP call so we don't need network.
    bc.send_characters = MagicMock(return_value=(True, True))  # type: ignore[assignment]
    return bc


def test_render_passes_built_in_strategy_through():
    bc = _build_board_client()
    bc.render(_grid(1), strategy="column", step_interval_ms=200, step_size=2)
    bc.send_characters.assert_called_once_with(
        _grid(1),
        strategy="column",
        step_interval_ms=200,
        step_size=2,
        force=False,
    )


def test_render_no_strategy_passes_through():
    bc = _build_board_client()
    bc.render(_grid(1))
    bc.send_characters.assert_called_once()


def test_render_with_plugin_strategy_and_no_runner_falls_back():
    bc = _build_board_client()
    bc.render(_grid(1), strategy=f"{TRANSITION_PLUGIN_PREFIX}missing")
    # Without a runner attached, the call snaps to target via send_characters.
    bc.send_characters.assert_called_once()


def test_render_with_plugin_strategy_invokes_runner():
    bc = _build_board_client()

    captured = {}

    class _Runner:
        def run(self, plugin_id, to_grid, board_client, cancel_event, device_type):
            captured["plugin_id"] = plugin_id
            captured["to_grid"] = to_grid
            captured["cancel"] = cancel_event
            captured["device_type"] = device_type
            return (True, True)

    bc.set_transition_runner(_Runner())
    bc.render(
        _grid(2),
        strategy=f"{TRANSITION_PLUGIN_PREFIX}typewriter",
        device_type="flagship",
    )
    assert captured["plugin_id"] == "typewriter"
    assert captured["to_grid"] == _grid(2)
    assert captured["device_type"] == "flagship"
    assert isinstance(captured["cancel"], threading.Event)


def test_render_empty_plugin_id_falls_back():
    bc = _build_board_client()

    bc.set_transition_runner(MagicMock())
    bc.render(_grid(1), strategy=f"{TRANSITION_PLUGIN_PREFIX}   ")
    # Empty id after the prefix: do not call the runner, snap instead.
    assert bc._transition_runner.run.call_count == 0
    bc.send_characters.assert_called_once()


def test_render_sets_cancel_event_before_handing_off():
    """A second render() while a transition is in flight should signal cancel."""
    bc = _build_board_client()

    events_seen: list[bool] = []

    class _Runner:
        def run(self, plugin_id, to_grid, board_client, cancel_event, device_type):
            # The new render call should clear the event before invoking us.
            events_seen.append(cancel_event.is_set())
            return (True, True)

    bc.set_transition_runner(_Runner())
    bc.render(_grid(1), strategy=f"{TRANSITION_PLUGIN_PREFIX}t")
    bc.render(_grid(2), strategy=f"{TRANSITION_PLUGIN_PREFIX}t")
    # Both runner invocations should see a fresh (cleared) event.
    assert events_seen == [False, False]


def test_set_transition_runner_can_be_cleared():
    bc = _build_board_client()
    bc.set_transition_runner(MagicMock())
    bc.set_transition_runner(None)
    assert bc._transition_runner is None
