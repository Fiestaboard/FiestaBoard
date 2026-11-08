"""H12: per-display health, recorded where the hub actually talks to the device.

Each board's ``OutputRuntime`` keeps ``health``:

- contact (``last_connected_at``, ``latency_ms``) is recorded by ``OutputHttp``
  only when the device answered: a 2xx/3xx, or a 429 the device sends. Core's
  own dedupe and floor short-circuits, and a plugin "unchanged" that made no
  request, prove nothing;
- failures are classified at the HTTP layer with the ``FailureClass`` taxonomy
  (auth, unreachable, timeout, server_error, unexpected_status, blocked), so a
  plugin that swallows its exception still reports the real cause; the driver
  adds what HTTP cannot see (write_failed, raised, timeout, bad_response,
  read_failed);
- an open circuit breaker is ``breaker_open: true``, beside the failure that
  opened it: a refused write is not a contact attempt, so it never replaces
  the cause in ``last_error``;
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
        # A connect timeout never reached the board: unreachable, not slow.
        (requests.ConnectTimeout("connect timed out"), "unreachable"),
        (500, "server_error"),
        (404, "unexpected_status"),
        # A bad address in the board's settings: the board was never tried.
        (requests.exceptions.InvalidURL("bad host"), "misconfigured"),
        (requests.exceptions.MissingSchema("no scheme"), "misconfigured"),
        (requests.exceptions.InvalidSchema("gopher://"), "misconfigured"),
        (requests.exceptions.InvalidHeader("bad token header"), "misconfigured"),
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


def test_an_open_breaker_keeps_the_cause_and_is_reported_beside_it():
    # A wrong token (401): the Fix it screen needs "auth", not "the hub gave up".
    plugin = HttpSign(answer=401)
    driver, runtime = _driver(plugin)
    for code in range(OUTPUT_BREAKER_THRESHOLD):
        driver.send_characters(frame(10 + code))
    assert _health(runtime)["breaker_open"] is True
    calls = plugin.calls
    for code in range(3):
        driver.send_characters(frame(30 + code))  # refused by the breaker
    assert plugin.calls == calls
    health = _health(runtime)
    assert (health["last_error"], health["breaker_open"], health["reachable"]) == ("auth", True, False)


def test_a_breaker_probe_that_fails_again_still_names_the_cause():
    plugin = HttpSign(answer=500)
    driver, runtime = _driver(plugin)
    for code in range(OUTPUT_BREAKER_THRESHOLD):
        driver.send_characters(frame(10 + code))
    driver._clock.now += output_breakers().cooldown_seconds + 1  # the probe goes through
    driver.send_characters(frame(40))
    driver.send_characters(frame(41))  # refused again
    health = _health(runtime)
    assert (health["last_error"], health["breaker_open"]) == ("server_error", True)


def test_a_breaker_closes_when_the_device_answers_again():
    plugin = HttpSign(answer=500)
    driver, runtime = _driver(plugin)
    for code in range(OUTPUT_BREAKER_THRESHOLD):
        driver.send_characters(frame(10 + code))
    driver._clock.now += output_breakers().cooldown_seconds + 1
    plugin.answer = 200
    runtime.health.clock = lambda: WALL + 400
    driver.send_characters(frame(40))
    health = _health(runtime)
    assert (health["breaker_open"], health["reachable"], health["last_error"]) == (False, True, "server_error")


def test_a_first_party_output_has_no_breaker_to_report():
    driver, runtime = _driver(HttpSign(answer=500), first_party=True)
    for code in range(OUTPUT_BREAKER_THRESHOLD + 1):
        driver.send_characters(frame(10 + code))
    assert _health(runtime)["breaker_open"] is False


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
        "breaker_open": False,
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

    driver, _runtime = _driver(HttpSign())
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
        "breaker_open": False,
    }
    assert client.get(f"/v1/boards/{primary}").json()["health"] == expected
    assert client.get("/status").json()["boards"][primary]["health"] == expected


def test_a_board_without_a_runtime_reports_nothing_known(client, boards, board_client):  # noqa: F811
    from src.display_runtime import get_service

    primary, _ = boards
    get_service().runtime_for.return_value = None
    assert client.get(f"/v1/boards/{primary}").json()["health"]["reachable"] is None


# --- Review follow-ups: what is on disk, how it is written --------------------------------------


def _seed_file(tmp_path, content: str):
    path = _store_file(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_a_corrupt_file_starts_empty_and_is_rewritten(tmp_path):
    from src.outputs import health as module

    _seed_file(tmp_path, "{not json")
    runtime = OutputRuntime("b1")
    assert runtime.health.as_dict()["last_update_at"] is None
    runtime.health.clock = lambda: WALL
    runtime.health.record_update()
    module.flush_board_health()
    assert json.loads(_store_file(tmp_path).read_text())["b1"]["last_update_at"] == WALL


def test_a_file_that_is_not_an_object_starts_empty(tmp_path):
    _seed_file(tmp_path, json.dumps(["b1", WALL]))
    assert OutputRuntime("b1").health.as_dict()["last_update_at"] is None


def test_what_this_build_cannot_read_is_dropped_on_load(tmp_path):
    # After a rollback the file can hold a newer build's codes; a hand edit or
    # bug can leave anything. Keep what is valid, drop the rest.
    _seed_file(
        tmp_path,
        json.dumps(
            {
                "b1": {
                    "last_connected_at": "2026-11-08T02:18:00Z",  # a string, not an instant
                    "last_update_at": WALL,
                    "last_error_at": WALL,
                    "last_error": "cloud_down",  # a code from a newer build
                },
                "b2": {"last_connected_at": True, "last_update_at": 1e300, "last_error_at": -5, "last_error": 7},
                "b3": "not an entry",
                "b4": {"last_error_at": WALL, "last_error": "auth", "surplus": "ignored"},
            }
        ).replace("1e+300", "Infinity"),
    )
    b1 = OutputRuntime("b1").health.as_dict()
    assert (b1["last_connected_at"], b1["last_update_at"]) == (None, AT)
    assert (b1["last_error_at"], b1["last_error"]) == (AT, None)
    b2 = OutputRuntime("b2").health.as_dict()
    assert all(b2[key] is None for key in ("last_connected_at", "last_update_at", "last_error_at", "last_error"))
    assert OutputRuntime("b3").health.as_dict()["last_update_at"] is None
    b4 = OutputRuntime("b4").health.as_dict()
    assert (b4["last_error_at"], b4["last_error"]) == (AT, "auth")


def test_the_routes_survive_health_they_cannot_read(client, boards, board_client):  # noqa: F811
    from src.display_runtime import get_service

    primary, secondary = boards
    health = get_service().runtime_for(primary).output.health
    health._error, health._error_at = "cloud_down", "not an instant"  # state no summary can serialise
    detail = client.get(f"/v1/boards/{primary}")
    assert detail.status_code == 200
    assert detail.json()["health"]["reachable"] is None
    status = client.get("/status").json()
    assert set(status["boards"]) == {primary, secondary}


def test_one_failing_board_does_not_hide_the_others_from_status(client, boards, board_client, monkeypatch):  # noqa: F811
    from src.service_api import routes

    primary, secondary = boards
    real = routes._output_status

    def flaky(board):
        if board.get("id") == primary:
            raise RuntimeError("one bad row")
        return real(board)

    monkeypatch.setattr(routes, "_output_status", flaky)
    status = client.get("/status").json()
    assert secondary in status["boards"]


def test_a_failed_rename_leaves_the_previous_file_whole(tmp_path, monkeypatch):
    from pathlib import Path

    from src.outputs import health as module

    path = _seed_file(tmp_path, json.dumps({"b1": {"last_update_at": WALL}}))
    before = path.read_text()
    runtime = OutputRuntime("b1")
    runtime.health.clock = lambda: WALL + 600

    def refuse(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)
    runtime.health.record_update()  # first change: written now, and the rename fails
    module.flush_board_health()
    assert path.read_text() == before


def test_the_apps_shutdown_flushes_board_health(monkeypatch):
    from src.api_server import app
    from src.outputs import health as module
    from fastapi.testclient import TestClient

    flushed = []
    monkeypatch.setattr("src.system.mdns.start_mdns", lambda *a, **k: True)
    monkeypatch.setattr(module, "flush_board_health", lambda: flushed.append(1))
    with TestClient(app):
        assert flushed == []
    assert flushed == [1]


def test_a_deferred_change_is_written_by_a_timer_without_another_change(tmp_path):
    from src.outputs import health as module

    timers = []

    class FakeTimer:
        def __init__(self, interval, function):
            self.interval, self.function, self.daemon, self.cancelled = interval, function, False, False
            timers.append(self)

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

    now = [WALL]
    store = module.HealthStore(_store_file(tmp_path), clock=lambda: now[0], timer=FakeTimer)
    store.update("b1", {"last_update_at": WALL})  # written at once
    now[0] += 60
    store.update("b1", {"last_update_at": WALL + 60})  # deferred: a timer is armed
    store.update("b1", {"last_update_at": WALL + 61})  # still the same timer
    assert len(timers) == 1 and timers[0].interval == module.HEALTH_FLUSH_INTERVAL_SECONDS - 60
    assert timers[0].daemon is True
    timers[0].function()  # the idle board's change lands without a later write
    assert json.loads(_store_file(tmp_path).read_text())["b1"]["last_update_at"] == WALL + 61


def test_a_removed_board_leaves_the_health_file(tmp_path, client, boards):  # noqa: F811
    from src.outputs import health as module
    from src.settings.service import get_settings_service

    primary, secondary = boards
    for board_id in (primary, secondary):
        runtime = OutputRuntime(board_id)
        runtime.health.clock = lambda: WALL
        runtime.health.record_update()
    module.flush_board_health()
    get_settings_service().remove_board(secondary)
    module.flush_board_health()
    stored = json.loads(_store_file(tmp_path).read_text())
    assert primary in stored and secondary not in stored


def test_reachable_follows_this_process_events_not_a_stepped_clock(tmp_path):
    # A FiestaPi has no RTC: until NTP syncs, its clock can read earlier than
    # an error persisted before the reboot. Its first contact must still read reachable.
    _seed_file(tmp_path, json.dumps({"b1": {"last_error_at": WALL + 3600, "last_error": "unreachable"}}))
    runtime = OutputRuntime("b1")
    runtime.health.clock = lambda: WALL
    runtime.health.record_contact(0.05)
    assert runtime.health.as_dict()["reachable"] is True
