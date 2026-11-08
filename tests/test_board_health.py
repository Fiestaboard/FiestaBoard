"""H12: per-display health, recorded where every device write and read settles.

Each board's ``OutputRuntime`` keeps ``health``: when the device last answered
the hub (``last_connected_at``), when a frame last landed (``last_update_at``),
how long that device call took (``latency_ms``), and the last failed contact
with a reason code. All outputs, first-party ones included, write through
``OutputPluginDriver``, so recording there covers every display type. In
memory only: nothing is written to disk per send.
"""

from __future__ import annotations

import time

import pytest

from src.outputs.breaker import OUTPUT_BREAKER_THRESHOLD, output_breakers
from src.outputs.hooks import ReadBack
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.outputs.runtime import OutputRuntime
from src.send_outcome import WriteResult
from tests.test_output_breaker_timeout import Clock, Sign, boom, fail, frame

WALL = 1_762_568_280.0  # 2026-11-08T02:18:00Z


class ReadableSign(Sign):
    def __init__(self, *args, read=None, delivery="push", **kwargs):
        super().__init__(*args, **kwargs)
        self.read = read or (lambda: frame(1))
        self.delivery = delivery

    def capabilities(self) -> OutputCapabilities:
        return OutputCapabilities(
            technology="led_matrix",
            delivery=self.delivery,
            animation="stream",
            native_transitions=frozenset(),
            read_back=ReadBack(supported=True, cost="cheap", suggested_interval_s=30),
            write_timeout_ms=self.write_timeout_ms,
        )

    def read_current(self):
        return self.read()


@pytest.fixture(autouse=True)
def _fresh_breakers():
    output_breakers().clear()
    yield
    output_breakers().clear()


def _driver(plugin, *, first_party=False):
    runtime = OutputRuntime("b1")
    runtime.health.clock = lambda: WALL
    driver = OutputPluginDriver(plugin, clock=Clock(), first_party=first_party)
    driver.set_output_runtime(runtime)
    return driver, runtime


def _health(runtime):
    return runtime.health.as_dict()


# --- Writes ----------------------------------------------------------------------


def test_a_landed_write_is_contact_and_an_update():
    plugin = Sign()

    def slow(_n):
        time.sleep(0.05)
        return WriteResult(True, True)

    plugin.behave = slow
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    health = _health(runtime)
    assert health["last_connected_at"] == "2026-11-08T02:18:00+00:00"
    assert health["last_update_at"] == "2026-11-08T02:18:00+00:00"
    assert health["latency_ms"] >= 50
    assert (health["last_error_at"], health["last_error"], health["reachable"]) == (None, None, True)


def test_an_unchanged_write_is_contact_but_not_an_update():
    plugin = Sign()
    plugin.behave = lambda n: WriteResult(True, False)  # the device already showed it
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    health = _health(runtime)
    assert health["last_connected_at"] is not None and health["last_update_at"] is None


def test_a_device_throttled_write_is_contact_not_an_error():
    plugin = Sign()
    plugin.behave = lambda n: WriteResult(True, False, throttled=True, retry_after_seconds=10)
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    health = _health(runtime)
    assert health["last_connected_at"] is not None and health["last_error"] is None and health["reachable"] is True


def test_a_reported_failure_is_a_write_failed_error():
    plugin = Sign()
    plugin.behave = fail
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    health = _health(runtime)
    assert (health["last_error_at"], health["last_error"]) == ("2026-11-08T02:18:00+00:00", "write_failed")
    assert health["reachable"] is False and health["last_connected_at"] is None


def test_a_raised_write_is_recorded_for_a_third_party_output():
    plugin = Sign()
    plugin.behave = boom
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    assert _health(runtime)["last_error"] == "raised"


def test_a_raised_write_is_recorded_before_a_first_party_output_reraises():
    plugin = Sign()
    plugin.behave = boom
    driver, runtime = _driver(plugin, first_party=True)
    with pytest.raises(RuntimeError):
        driver.send_characters(frame(2))
    assert _health(runtime)["last_error"] == "raised"


def test_a_write_past_its_budget_is_a_timeout():
    plugin = Sign(write_timeout_ms=50)

    def hang(_n):
        time.sleep(0.5)
        return WriteResult(True, True)

    plugin.behave = hang
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    assert _health(runtime)["last_error"] == "timeout"


def test_an_open_breaker_is_reported():
    plugin = Sign()
    plugin.behave = fail
    driver, runtime = _driver(plugin)
    for code in range(OUTPUT_BREAKER_THRESHOLD):
        driver.send_characters(frame(10 + code))
    calls = plugin.calls
    driver.send_characters(frame(30))
    assert plugin.calls == calls  # refused without calling the plugin
    assert _health(runtime)["last_error"] == "breaker_open"


def test_a_success_after_a_failure_is_reachable_again():
    plugin = Sign()
    outcomes = iter([WriteResult(False, False), WriteResult(True, True)])
    plugin.behave = lambda n: next(outcomes)
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    runtime.health.clock = lambda: WALL + 60
    driver.send_characters(frame(3))
    health = _health(runtime)
    assert health["reachable"] is True and health["last_error"] == "write_failed"
    assert health["last_connected_at"] == "2026-11-08T02:19:00+00:00"


# --- Reads -----------------------------------------------------------------------


def test_a_successful_read_is_contact():
    driver, runtime = _driver(ReadableSign())
    assert driver.read_current_message() is not None
    health = _health(runtime)
    assert health["last_connected_at"] == "2026-11-08T02:18:00+00:00" and health["last_update_at"] is None


def test_a_failed_read_is_a_read_failed_error():
    def broken():
        raise OSError("no route to host")

    driver, runtime = _driver(ReadableSign(read=broken))
    assert driver.read_current_message() is None
    assert _health(runtime)["last_error"] == "read_failed"


# --- Pull outputs (FiestaPanel) ---------------------------------------------------


def test_a_pull_output_records_updates_but_never_contact():
    plugin = ReadableSign(delivery="pull")
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    health = _health(runtime)
    assert health["last_update_at"] == "2026-11-08T02:18:00+00:00"
    assert (health["last_connected_at"], health["latency_ms"], health["reachable"]) == (None, None, None)


# --- Lifetime and shape -------------------------------------------------------------


def test_health_lives_on_the_runtime_across_a_driver_rebuild():
    plugin = Sign()
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    rebuilt = OutputPluginDriver(Sign(), clock=Clock())
    rebuilt.set_output_runtime(runtime)
    assert _health(runtime)["last_update_at"] == "2026-11-08T02:18:00+00:00"


def test_nothing_known_yet_is_all_null():
    assert OutputRuntime("b1").health.as_dict() == {
        "last_connected_at": None,
        "last_update_at": None,
        "latency_ms": None,
        "last_error_at": None,
        "last_error": None,
        "reachable": None,
    }


# --- On the wire --------------------------------------------------------------------


def test_status_and_v1_carry_each_boards_health(monkeypatch):
    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.settings.service import get_settings_service

    board_id = get_settings_service().set_boards([{"device_type": "flagship", "name": "Kitchen"}]).boards[0]["id"]
    runtime = OutputRuntime(board_id)
    runtime.health.clock = lambda: WALL
    runtime.health.record_contact(0.38)
    runtime.health.record_update()

    from unittest.mock import Mock

    service = Mock()
    service.runtime_for.side_effect = lambda bid=None: Mock(output=runtime) if bid in (None, board_id) else None
    service.get_runtime.side_effect = lambda bid: Mock(output=runtime) if bid == board_id else None
    service.board_init_errors = {}
    monkeypatch.setattr("src.api_server.get_service", lambda: service)
    monkeypatch.setattr("src.display_runtime.get_service", lambda: service)

    client = TestClient(app)
    expected = {
        "last_connected_at": "2026-11-08T02:18:00+00:00",
        "last_update_at": "2026-11-08T02:18:00+00:00",
        "latency_ms": 380,
        "last_error_at": None,
        "last_error": None,
        "reachable": True,
    }
    assert client.get(f"/v1/boards/{board_id}").json()["health"] == expected
    assert client.get("/status").json()["boards"][board_id]["health"] == expected
