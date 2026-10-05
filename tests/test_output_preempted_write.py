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
