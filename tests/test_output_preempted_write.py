"""A preempted output-plugin write gives the board back to the write that preempted it.

The owner's Pixoo stayed dark after "set active page": the engine's write
was uploading when the PUT /settings/active-page send preempted it. The
plugin stopped (``WriteResult(True, False)``: preempted, not failed), but
core kept the floor slot the dead write had reserved and recorded its
frame as shown. The preempting write — the same page — was then refused as
"throttled: 0.3s since last send", so nothing reached the device and the
last-frame store claimed the page was on it.

A write whose run was cancelled and that reports nothing sent did not land:
its slot goes back to the floor and its frame is never recorded.
"""

from __future__ import annotations

import threading

import pytest

from src.outputs.breaker import output_breakers
from src.outputs.floor import send_floors
from src.outputs.hooks import ReadBack
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.send_outcome import WriteResult

PAGE = [[68] * 16 for _ in range(10)]


class SlowPanel(OutputPluginBase):
    """Uploads until preempted on its first write, like the Pixoo's multi-request upload."""

    plugin_id = "slow_panel"

    def __init__(self) -> None:
        super().__init__("b1", {})
        self.started = threading.Event()
        self.landed: list[list[list[int]]] = []
        self.first = True

    def capabilities(self) -> OutputCapabilities:
        return OutputCapabilities(
            technology="led_matrix",
            delivery="push",
            animation="stream",
            native_transitions=frozenset(),
            min_interval_ms=1000,
            read_back=ReadBack(supported=False, cost="cheap", suggested_interval_s=30),
        )

    def device_key(self) -> str:
        return "slow-panel:192.0.2.20"

    def write(self, frame, *, native, cancel):
        if self.first:
            self.first = False
            self.started.set()
            if cancel.wait(5):
                return WriteResult(True, False)  # preempted: stopped mid-upload
        self.landed.append(frame)
        return WriteResult(True, True)


class Clock:
    """Frozen: the preempting write arrives well inside the 1 s floor."""

    def __call__(self) -> float:
        return 1000.0


@pytest.fixture(autouse=True)
def _clean():
    send_floors().clear()
    output_breakers().clear()
    yield
    send_floors().clear()
    output_breakers().clear()


def _preempted_then_resent():
    plugin = SlowPanel()
    driver = OutputPluginDriver(plugin, clock=Clock())
    first: dict = {}
    engine = threading.Thread(target=lambda: first.update(r=driver.render(PAGE, with_outcome=True)))
    engine.start()
    assert plugin.started.wait(5)
    second = driver.render(PAGE, with_outcome=True)
    engine.join(5)
    return plugin, driver, first["r"], second


def test_the_write_that_preempts_an_upload_reaches_the_device():
    plugin, _, _, second = _preempted_then_resent()

    assert not second.throttled, "the preempting write was throttled by the slot of the write it cancelled"
    assert second.was_sent
    assert plugin.landed == [PAGE]


@pytest.mark.parametrize("target_landed", [False, True])
def test_a_preempted_transition_cannot_deduplicate_its_successor(target_landed):
    plugin = SlowPanel()
    plugin.first = False
    now = [1000.0]
    driver = OutputPluginDriver(plugin, clock=lambda: now[0])
    assert driver.send_characters(PAGE, with_outcome=True).was_sent
    send_floors().clear()
    original_write = plugin.write
    intermediate = [[65] * 16 for _ in range(10)]
    target = [[66] * 16 for _ in range(10)]
    brightness = [60]

    def restored_write(frame, *, native, cancel):
        result = original_write(frame, native=native, cancel=cancel)
        brightness[0] = 60
        return result

    def interrupted_write(frame, *, native, cancel):
        # A streamed transition can change the device before its target lands.
        plugin.landed.append(frame if target_landed else intermediate)
        brightness[0] = 0
        plugin.started.set()
        cancel.wait(5)
        plugin.write = restored_write
        return WriteResult(True, target_landed)

    plugin.write = interrupted_write
    worker = threading.Thread(target=lambda: driver.send_characters(target))
    worker.start()
    try:
        assert plugin.started.wait(2)
        now[0] += 2  # respect the floor even when the cancelled target landed
        successor = target if target_landed else PAGE
        returned = driver.send_characters(successor, with_outcome=True)
        assert returned.was_sent, "cached content hid an unfinished cancelled transition"
        assert plugin.landed[-1] == successor
        assert brightness[0] == 60
    finally:
        driver._output_runtime.preempt()
        worker.join(2)


def test_a_preempted_write_is_not_recorded_as_shown():
    plugin = SlowPanel()
    driver = OutputPluginDriver(plugin, clock=Clock())
    result: dict = {}
    engine = threading.Thread(target=lambda: result.update(r=driver.render(PAGE, with_outcome=True)))
    engine.start()
    assert plugin.started.wait(5)
    driver._output_runtime.preempt()
    engine.join(5)

    assert not result["r"].was_sent
    assert driver._output_runtime.last_frame is None, "a frame that never landed is in the last-frame store"


def test_a_timed_out_transition_cannot_deduplicate_its_successor(monkeypatch):
    plugin = SlowPanel()
    plugin.first = False
    now = [1000.0]
    driver = OutputPluginDriver(plugin, clock=lambda: now[0])
    assert driver.send_characters(PAGE, with_outcome=True).was_sent
    send_floors().clear()
    original_write = plugin.write
    stopped = threading.Event()

    def interrupted_write(frame, *, native, cancel):
        plugin.landed.append([[65] * 16 for _ in range(10)])
        cancel.wait(5)
        stopped.set()
        return WriteResult(True, False)

    plugin.write = interrupted_write
    monkeypatch.setattr(OutputPluginDriver, "write_timeout_seconds", property(lambda _: 0.05))
    assert not driver.send_characters([[66] * 16 for _ in range(10)], with_outcome=True).success
    assert stopped.wait(2)
    plugin.write = original_write
    now[0] += 2
    assert driver.send_characters(PAGE, with_outcome=True).was_sent
    assert plugin.landed[-1] == PAGE


@pytest.mark.parametrize("failure", ["reported", "raised", "throttled"])
def test_an_interrupted_write_cannot_deduplicate_the_previous_page(failure):
    plugin = SlowPanel()
    plugin.first = False
    now = [1000.0]
    driver = OutputPluginDriver(plugin, clock=lambda: now[0])
    assert driver.send_characters(PAGE, with_outcome=True).was_sent
    send_floors().clear()
    original_write = plugin.write

    def interrupted_write(frame, *, native, cancel):
        plugin.landed.append([[65] * 16 for _ in range(10)])
        if failure == "raised":
            raise OSError("connection lost after an intermediate frame")
        if failure == "throttled":
            return WriteResult(True, False, throttled=True, retry_after_seconds=1)
        return WriteResult(False, False)

    plugin.write = interrupted_write
    failed = driver.send_characters([[66] * 16 for _ in range(10)], with_outcome=True)
    assert failed.throttled if failure == "throttled" else not failed.success
    plugin.write = original_write
    now[0] += 2
    returned = driver.send_characters(PAGE, with_outcome=True)
    assert returned.was_sent, "cached previous page hid an interrupted write's intermediate frame"
    assert plugin.landed[-1] == PAGE


def test_the_driver_says_its_last_write_was_preempted_and_the_next_one_clears_it():
    plugin = SlowPanel()
    driver = OutputPluginDriver(plugin, clock=Clock())
    engine = threading.Thread(target=lambda: driver.render(PAGE))
    engine.start()
    assert plugin.started.wait(5)
    driver._output_runtime.preempt()
    engine.join(5)
    preempted = driver.last_send_preempted

    send_floors().clear()
    driver.render([[67] * 16 for _ in range(10)])

    assert preempted is True
    assert driver.last_send_preempted is False


def test_superseded_outcome_survives_the_replacement_write():
    plugin, driver, first, second = _preempted_then_resent()

    assert first.superseded
    assert not first.was_sent
    assert not second.superseded
    assert second.was_sent
    assert driver.last_send_preempted is False
    assert plugin.landed == [PAGE]
