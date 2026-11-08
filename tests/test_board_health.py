"""H12: per-display health, recorded where the hub actually talks to the device.

Each board's ``OutputRuntime`` keeps ``health``:

- contact (``last_connected_at``, ``latency_ms``) is recorded by ``OutputHttp``
  only when the device answered: a 2xx/3xx, or a 429 the device sends. Core's
  own dedupe and floor short-circuits, and a plugin "unchanged" that made no
  request, prove nothing;
- failures are classified at the HTTP layer with the ``FailureClass`` taxonomy
  (auth, unreachable, timeout, server_error, unexpected_status, blocked), so a
  plugin that swallows its exception still reports the real cause; the driver
  adds what HTTP cannot see (write_failed, raised, timeout, breaker_open,
  bad_response, read_failed);
- ``last_update_at`` is a frame that landed;
- ``last_connected_at``, ``last_update_at`` and ``last_error`` persist lightly
  (at most every 180 s, and on shutdown); ``reachable`` and ``latency_ms`` are
  unknown again after a restart.
"""

from __future__ import annotations

import json
import time

import pytest
import requests

from src.outputs.breaker import OUTPUT_BREAKER_THRESHOLD, output_breakers
from src.outputs.hooks import ReadBack
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.outputs.runtime import OutputRuntime
from src.send_outcome import WriteResult
from tests.test_output_breaker_timeout import Clock, Sign, boom, frame
from tests.test_v1_contract import board_client, boards, client  # noqa: F401 - fixtures

WALL = 1_794_104_280.0  # 2026-11-08T02:18:00Z
AT = "2026-11-08T02:18:00+00:00"
URL = "http://192.0.2.10/frame"


def _response(status: int) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = b"{}"
    return response


class HttpSign(Sign):
    """A sign that talks HTTP through core's client, like every in-tree output.

    ``answer`` is what the device does: an HTTP status, or an exception to
    raise. ``swallow`` makes the plugin hide errors behind WriteResult(False,
    False), the way TC001 does.
    """

    def __init__(self, *args, answer=200, swallow=False, read_body=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.answer = answer
        self.swallow = swallow
        self.read_body = read_body

        def transport(request):
            time.sleep(0.02)
            if isinstance(self.answer, BaseException):
                raise self.answer
            return _response(self.answer)

        self.http.use_transport(transport)

    def capabilities(self) -> OutputCapabilities:
        return OutputCapabilities(
            technology="led_matrix",
            delivery="push",
            animation="stream",
            native_transitions=frozenset(),
            read_back=ReadBack(supported=True, cost="cheap", suggested_interval_s=30),
            write_timeout_ms=self.write_timeout_ms,
        )

    def write(self, frame, *, native, cancel):
        self.calls += 1
        try:
            response = self.http.post(URL, json={"frame": frame})
        except Exception:
            if self.swallow:
                return WriteResult(False, False)
            raise
        if response.status_code == 429:
            return WriteResult(True, False, throttled=True, retry_after_seconds=10)
        return WriteResult(response.status_code < 300, response.status_code < 300)

    def read_current(self):
        self.http.get(URL)
        if self.read_body is not None:
            return self.read_body()
        return frame(1)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch, tmp_path):
    output_breakers().clear()
    monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(tmp_path / "data"))
    from src.outputs import health

    health.reset_health_store()
    yield
    health.reset_health_store()
    output_breakers().clear()


def _driver(plugin, *, first_party=False, board_id="b1"):
    runtime = OutputRuntime(board_id)
    runtime.health.clock = lambda: WALL
    driver = OutputPluginDriver(plugin, clock=Clock(), first_party=first_party)
    driver.set_output_runtime(runtime)
    return driver, runtime


def _health(runtime):
    return runtime.health.as_dict()


# --- Contact: only a device that answered ------------------------------------------


def test_a_landed_write_is_contact_and_an_update_with_its_latency():
    driver, runtime = _driver(HttpSign())
    driver.send_characters(frame(2))
    health = _health(runtime)
    assert (health["last_connected_at"], health["last_update_at"]) == (AT, AT)
    assert health["latency_ms"] >= 20
    assert (health["last_error"], health["reachable"]) == (None, True)


def test_a_plugin_unchanged_without_a_request_is_not_contact():
    plugin = Sign()  # makes no request at all
    plugin.behave = lambda n: WriteResult(True, False)
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    health = _health(runtime)
    assert (health["last_connected_at"], health["last_update_at"], health["reachable"]) == (None, None, None)


def test_a_core_dedupe_skip_is_not_new_contact():
    driver, runtime = _driver(HttpSign())
    driver.send_characters(frame(2))
    runtime.health.clock = lambda: WALL + 60
    driver.send_characters(frame(2))  # unchanged: core never calls the plugin
    assert _health(runtime)["last_connected_at"] == AT


def test_a_throttle_the_device_reports_is_contact():
    driver, runtime = _driver(HttpSign(answer=429))
    driver.send_characters(frame(2))
    health = _health(runtime)
    assert health["last_connected_at"] == AT and health["last_error"] is None and health["last_update_at"] is None


# --- Failure classes, at the HTTP layer --------------------------------------------


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (401, "auth"),
        (403, "auth"),
        (requests.ConnectionError("no route to host"), "unreachable"),
        (requests.Timeout("read timed out"), "timeout"),
        (500, "server_error"),
        (404, "unexpected_status"),
    ],
)
def test_each_failure_is_classified(answer, code):
    driver, runtime = _driver(HttpSign(answer=answer))
    driver.send_characters(frame(2))
    health = _health(runtime)
    assert (health["last_error_at"], health["last_error"], health["reachable"]) == (AT, code, False)


def test_a_fenced_host_is_blocked(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_OUTPUTS_ALLOW_HOSTS", "198.51.100.1")
    driver, runtime = _driver(HttpSign(swallow=True))
    driver.send_characters(frame(2))
    assert _health(runtime)["last_error"] == "blocked"


def test_a_plugin_that_swallows_the_error_still_reports_the_cause():
    # TC001 catches its own exceptions and returns WriteResult(False, False).
    driver, runtime = _driver(HttpSign(answer=requests.ConnectionError("unplugged"), swallow=True))
    driver.send_characters(frame(2))
    assert _health(runtime)["last_error"] == "unreachable"


def test_a_reported_failure_with_no_http_cause_is_write_failed():
    plugin = Sign()
    plugin.behave = lambda n: WriteResult(False, False)
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    assert _health(runtime)["last_error"] == "write_failed"


# --- What only the driver can see ----------------------------------------------------


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
    plugin = HttpSign(answer=500)
    driver, runtime = _driver(plugin)
    for code in range(OUTPUT_BREAKER_THRESHOLD):
        driver.send_characters(frame(10 + code))
    calls = plugin.calls
    driver.send_characters(frame(30))
    assert plugin.calls == calls
    assert _health(runtime)["last_error"] == "breaker_open"


def test_a_success_after_a_failure_is_reachable_again():
    plugin = HttpSign(answer=500)
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    plugin.answer = 200
    runtime.health.clock = lambda: WALL + 60
    driver.send_characters(frame(3))
    health = _health(runtime)
    assert health["reachable"] is True and health["last_error"] == "server_error"
    assert health["last_connected_at"] == "2026-11-08T02:19:00+00:00"


# --- Reads ------------------------------------------------------------------------------


def test_a_read_is_contact():
    driver, runtime = _driver(HttpSign())
    assert driver.read_current_message() is not None
    health = _health(runtime)
    assert health["last_connected_at"] == AT and health["last_update_at"] is None


def test_a_read_the_output_cannot_parse_is_a_bad_response():
    def garbled():
        raise ValueError("not the read shape")

    driver, runtime = _driver(HttpSign(read_body=garbled))
    assert driver.read_current_message() is None
    assert _health(runtime)["last_error"] == "bad_response"


# --- Pull outputs (FiestaPanel) ---------------------------------------------------------


def test_a_pull_output_records_updates_but_never_contact():
    plugin = Sign()
    plugin.capabilities = lambda: OutputCapabilities(
        technology="led_matrix",
        delivery="pull",
        animation="stream",
        native_transitions=frozenset(),
        read_back=ReadBack(supported=True, cost="cheap", suggested_interval_s=30),
    )
    driver, runtime = _driver(plugin)
    driver.send_characters(frame(2))
    health = _health(runtime)
    assert health["last_update_at"] == AT
    assert (health["last_connected_at"], health["latency_ms"], health["reachable"]) == (None, None, None)


# --- Lifetime -------------------------------------------------------------------------------


def test_health_lives_on_the_runtime_across_a_driver_rebuild():
    driver, runtime = _driver(HttpSign())
    driver.send_characters(frame(2))
    OutputPluginDriver(HttpSign(), clock=Clock()).set_output_runtime(runtime)
    assert _health(runtime)["last_update_at"] == AT


def test_nothing_known_yet_is_all_null():
    assert OutputRuntime("fresh").health.as_dict() == {
        "last_connected_at": None,
        "last_update_at": None,
        "latency_ms": None,
        "last_error_at": None,
        "last_error": None,
        "reachable": None,
    }


# --- Light persistence ------------------------------------------------------------------------


def _store_file(tmp_path):
    return tmp_path / "data" / "board_health.json"


def test_changes_are_flushed_at_most_every_few_minutes(tmp_path, monkeypatch):
    from src.outputs import health as module

    writes = []
    real_write = module.HealthStore._write
    monkeypatch.setattr(module.HealthStore, "_write", lambda self: (writes.append(1), real_write(self)))
    now = [WALL]
    module.health_store().clock = lambda: now[0]
    runtime = OutputRuntime("b1")
    runtime.health.clock = lambda: now[0]
    runtime.health.record_update()  # first change: written
    now[0] += 60
    runtime.health.record_update()  # within the interval: deferred
    assert len(writes) == 1
    now[0] += module.HEALTH_FLUSH_INTERVAL_SECONDS
    runtime.health.record_update()  # interval passed: written
    assert len(writes) == 2
    stored = json.loads(_store_file(tmp_path).read_text())
    assert stored["b1"]["last_update_at"] == now[0]


def test_shutdown_flushes_what_is_pending(tmp_path):
    from src.outputs import health as module

    now = [WALL]
    module.health_store().clock = lambda: now[0]
    runtime = OutputRuntime("b1")
    runtime.health.clock = lambda: now[0]
    runtime.health.record_update()
    now[0] += 30
    runtime.health.record_error("unreachable")  # deferred
    module.flush_board_health()
    stored = json.loads(_store_file(tmp_path).read_text())
    assert stored["b1"]["last_error"] == "unreachable"


def test_a_restart_restores_the_times_but_not_reachability(tmp_path):
    from src.outputs import health as module

    driver, runtime = _driver(HttpSign())
    driver.send_characters(frame(2))
    module.flush_board_health()
    module.reset_health_store()  # a new process

    restored = OutputRuntime("b1").health.as_dict()
    assert (restored["last_connected_at"], restored["last_update_at"]) == (AT, AT)
    assert (restored["reachable"], restored["latency_ms"]) == (None, None)


def test_a_draft_runtime_never_persists(tmp_path):
    from src.outputs import health as module

    runtime = OutputRuntime()  # a draft driver's private runtime has no board
    runtime.health.record_update()
    module.flush_board_health()
    assert not _store_file(tmp_path).exists()


# --- On the wire ------------------------------------------------------------------------------


def test_status_and_v1_carry_each_boards_health(client, boards, board_client):  # noqa: F811
    from src.display_runtime import get_service

    primary, _ = boards
    health = get_service().runtime_for(primary).output.health
    health.clock = lambda: WALL
    health.record_contact(0.38)
    health.record_update()

    expected = {
        "last_connected_at": AT,
        "last_update_at": AT,
        "latency_ms": 380,
        "last_error_at": None,
        "last_error": None,
        "reachable": True,
    }
    assert client.get(f"/v1/boards/{primary}").json()["health"] == expected
    assert client.get("/status").json()["boards"][primary]["health"] == expected


def test_a_board_without_a_runtime_reports_nothing_known(client, boards, board_client):  # noqa: F811
    from src.display_runtime import get_service

    primary, _ = boards
    get_service().runtime_for.return_value = None
    assert client.get(f"/v1/boards/{primary}").json()["health"]["reachable"] is None
