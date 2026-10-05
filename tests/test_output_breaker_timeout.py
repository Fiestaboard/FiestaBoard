"""Third-party output safety: the per-output circuit breaker and the write timeout.

An output plugin is somebody else's code driving a board (plan Phase 2.4).
Core keeps two promises about it, both in :class:`OutputPluginDriver` (the
in-tree Vestaboard and FiestaPanel drivers are untouched):

- **write timeout** — core stops waiting for a write that runs past the
  output's budget (30 s by default; a manifest may lower it with
  ``output.write_timeout_ms``, never raise it), marks it failed and fires the
  run's cancel token. Threads cannot be killed: the plugin is told to stop,
  and nothing waits for it — the same model as the engine's
  ``SEND_WAIT_TIMEOUT``;
- **circuit breaker** — after repeated failed writes (raised, timed out, or
  reported failed) the breaker opens for a cool-down: writes are refused
  without calling the plugin, and the board says why. It is keyed by output
  and device (``device_key()``), like the send floor, so a board re-save does
  not reset it and one sick device never trips another.

And the A17 follow-up, refused-release memory: a release of an output
plugin that was rolled back (failed verification or did not load) is
remembered by commit, so the hourly update check does not offer it again;
the memory clears when a newer commit appears.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from src.outputs.breaker import (
    DEFAULT_WRITE_TIMEOUT_MS,
    OUTPUT_BREAKER_COOLDOWN_SECONDS,
    OUTPUT_BREAKER_THRESHOLD,
    output_breakers,
    write_failure_reason,
)
from src.outputs.hooks import ReadBack
from src.outputs.output_manifest import parse_output_block
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.send_outcome import WriteResult
from tests.test_output_seed_and_gate import PLUGIN_ID, commit_all, git, output_repo, set_output_api

GRID = [[1] * 22 for _ in range(6)]


def frame(code: int) -> list[list[int]]:
    return [[code] * 22 for _ in range(6)]


class Sign(OutputPluginBase):
    """A scriptable output plugin: ``behave(n)`` decides the n-th write."""

    plugin_id = "acme_sign"

    def __init__(self, board_id="b1", config=None, *, write_timeout_ms=None, host="192.0.2.10"):
        super().__init__(board_id, config or {})
        self.host = host
        self.calls = 0
        self.behave = lambda n: WriteResult(True, True)
        self.write_timeout_ms = write_timeout_ms

    def capabilities(self) -> OutputCapabilities:
        return OutputCapabilities(
            technology="led_matrix",
            delivery="push",
            animation="stream",
            native_transitions=frozenset(),
            read_back=ReadBack(supported=False, cost="cheap", suggested_interval_s=30),
            write_timeout_ms=self.write_timeout_ms,
        )

    def device_key(self) -> str:
        return f"acme:{self.host}"

    def write(self, frame, *, native, cancel):
        self.calls += 1
        return self.behave(self.calls)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def driver_for(plugin: Sign, clock: Clock | None = None) -> OutputPluginDriver:
    return OutputPluginDriver(plugin, clock=clock or Clock())


def fail(_n):
    return WriteResult(False, False)


def boom(_n):
    raise RuntimeError("device on fire")


@pytest.fixture(autouse=True)
def _fresh_breakers():
    output_breakers().clear()
    yield
    output_breakers().clear()


# --- the write timeout -------------------------------------------------------------------


class TestWriteTimeout:
    def test_a_write_past_its_budget_is_failed_without_waiting_for_it(self):
        plugin = Sign(write_timeout_ms=100)
        release = threading.Event()
        plugin.behave = lambda _n: (release.wait(5), WriteResult(True, True))[1]
        driver = driver_for(plugin)
        started = time.monotonic()
        result = driver.send_characters(GRID, with_outcome=True)
        took = time.monotonic() - started
        release.set()
        assert (result.success, result.was_sent) == (False, False)
        assert took < 2.0

    def test_the_timeout_fires_the_runs_cancel_token(self):
        plugin = Sign(write_timeout_ms=100)
        seen = threading.Event()

        def behave(_n):
            token = driver._output_runtime.cancel_event
            seen.set() if token.wait(5) else None
            return WriteResult(True, True)

        plugin.behave = behave
        driver = driver_for(plugin)
        driver.send_characters(GRID)
        assert seen.wait(2), "the plugin was never told to stop"

    def test_the_board_says_the_write_timed_out(self):
        plugin = Sign(write_timeout_ms=100)
        release = threading.Event()
        plugin.behave = lambda _n: (release.wait(5), WriteResult(True, True))[1]
        driver = driver_for(plugin)
        driver.send_characters(GRID)
        release.set()
        assert driver.last_write_error == "Output acme_sign: the write did not finish within 0.1s; it was cancelled."

    def test_a_timed_out_frame_is_not_recorded_as_shown(self):
        plugin = Sign(write_timeout_ms=100)
        release = threading.Event()
        plugin.behave = lambda _n: (release.wait(5), WriteResult(True, True))[1]
        driver = driver_for(plugin)
        driver.send_characters(GRID)
        release.set()
        assert driver._frames.last_frame is None

    def test_the_default_budget_is_thirty_seconds(self):
        assert DEFAULT_WRITE_TIMEOUT_MS == 30_000
        assert driver_for(Sign()).write_timeout_seconds == 30.0

    def test_a_plugin_cannot_raise_its_budget_past_the_default(self):
        assert driver_for(Sign(write_timeout_ms=600_000)).write_timeout_seconds == 30.0

    def test_a_fast_write_is_unaffected(self):
        driver = driver_for(Sign(write_timeout_ms=1000))
        assert driver.send_characters(GRID) == (True, True)
        assert driver.last_write_error is None


class TestManifestWriteTimeout:
    BLOCK = {"output_api": 1, "device_models": ["divoom_pixoo64"]}

    def test_a_manifest_may_lower_the_budget(self):
        manifest, errors = parse_output_block({**self.BLOCK, "write_timeout_ms": 5000}, base_dir=None, data_files=[])
        assert errors == []
        assert manifest.capabilities.write_timeout_ms == 5000

    @pytest.mark.parametrize("value", [0, -1, 30_001, "5000", True])
    def test_a_manifest_may_not_raise_it_or_declare_nonsense(self, value):
        _, errors = parse_output_block({**self.BLOCK, "write_timeout_ms": value}, base_dir=None, data_files=[])
        assert errors == ["output.write_timeout_ms must be an integer from 1 to 30000 (it may only lower the default)"]

    def test_left_out_it_is_the_default(self):
        manifest, _ = parse_output_block(self.BLOCK, base_dir=None, data_files=[])
        assert manifest.capabilities.write_timeout_ms is None


# --- the circuit breaker -------------------------------------------------------------------


class TestBreaker:
    def test_repeated_failures_open_it_and_the_plugin_is_left_alone(self):
        plugin = Sign()
        plugin.behave = fail
        driver = driver_for(plugin)
        for i in range(OUTPUT_BREAKER_THRESHOLD):
            assert driver.send_characters(frame(i)) == (False, False)
        assert plugin.calls == OUTPUT_BREAKER_THRESHOLD
        assert driver.send_characters(frame(9)) == (False, False)
        assert plugin.calls == OUTPUT_BREAKER_THRESHOLD

    def test_raised_and_timed_out_writes_count_too(self):
        plugin = Sign(write_timeout_ms=50)
        release = threading.Event()
        plan = {1: boom, 2: lambda _n: (release.wait(5), WriteResult(True, True))[1], 3: fail}
        plugin.behave = lambda n: plan[n](n)
        driver = driver_for(plugin)
        for i in range(3):
            driver.send_characters(frame(i))
        release.set()
        driver.send_characters(frame(9))
        assert plugin.calls == 3

    def test_the_board_says_why_while_it_is_open(self):
        plugin = Sign()
        plugin.behave = fail
        driver = driver_for(plugin)
        for i in range(OUTPUT_BREAKER_THRESHOLD + 1):
            driver.send_characters(frame(i))
        assert driver.last_write_error == (
            f"Output acme_sign stopped after {OUTPUT_BREAKER_THRESHOLD} failed writes in a row; "
            f"retrying in {OUTPUT_BREAKER_COOLDOWN_SECONDS:.0f}s. Last failure: the output reported the write failed."
        )
        assert write_failure_reason(driver) == driver.last_write_error

    def test_a_success_in_between_resets_the_count(self):
        plugin = Sign()
        plan = [False, False, True, False, False, True]
        plugin.behave = lambda n: WriteResult(plan[n - 1], plan[n - 1])
        driver = driver_for(plugin)
        for i in range(len(plan)):
            driver.send_characters(frame(i))
        assert plugin.calls == len(plan)

    def test_after_the_cool_down_one_probe_goes_through(self):
        clock = Clock()
        plugin = Sign()
        plugin.behave = fail
        driver = driver_for(plugin, clock)
        for i in range(OUTPUT_BREAKER_THRESHOLD):
            driver.send_characters(frame(i))
        clock.now += OUTPUT_BREAKER_COOLDOWN_SECONDS + 1
        plugin.behave = lambda _n: WriteResult(True, True)
        assert driver.send_characters(frame(7)) == (True, True)
        assert driver.last_write_error is None

    def test_a_failed_probe_reopens_it_at_once(self):
        clock = Clock()
        plugin = Sign()
        plugin.behave = fail
        driver = driver_for(plugin, clock)
        for i in range(OUTPUT_BREAKER_THRESHOLD):
            driver.send_characters(frame(i))
        clock.now += OUTPUT_BREAKER_COOLDOWN_SECONDS + 1
        driver.send_characters(frame(7))  # the probe, failing
        calls = plugin.calls
        driver.send_characters(frame(8))
        assert plugin.calls == calls

    def test_it_outlives_a_rebuilt_driver_for_the_same_device(self):
        clock = Clock()
        first = Sign()
        first.behave = fail
        driver = driver_for(first, clock)
        for i in range(OUTPUT_BREAKER_THRESHOLD):
            driver.send_characters(frame(i))
        rebuilt = Sign()  # a board re-save: a new instance, the same device
        assert driver_for(rebuilt, clock).send_characters(frame(5)) == (False, False)
        assert rebuilt.calls == 0

    def test_another_device_is_not_tripped(self):
        clock = Clock()
        sick = Sign(host="192.0.2.10")
        sick.behave = fail
        driver = driver_for(sick, clock)
        for i in range(OUTPUT_BREAKER_THRESHOLD):
            driver.send_characters(frame(i))
        healthy = Sign(host="192.0.2.11")
        assert driver_for(healthy, clock).send_characters(frame(5)) == (True, True)

    def test_an_open_breaker_keeps_the_floor_slot_free(self):
        clock = Clock()
        plugin = Sign()
        plugin.behave = fail
        driver = driver_for(plugin, clock)
        for i in range(OUTPUT_BREAKER_THRESHOLD + 2):
            driver.send_characters(frame(i))
        clock.now += OUTPUT_BREAKER_COOLDOWN_SECONDS + 1
        plugin.behave = lambda _n: WriteResult(True, True)
        outcome = driver.send_characters(frame(9), with_outcome=True)
        assert (outcome.success, outcome.was_sent, outcome.throttled) == (True, True, False)

    def test_unchanged_frames_still_report_success_while_it_is_open(self):
        plugin = Sign()
        driver = driver_for(plugin)
        assert driver.send_characters(GRID) == (True, True)
        plugin.behave = fail
        for i in range(OUTPUT_BREAKER_THRESHOLD):
            driver.send_characters(frame(i + 2))
        # The board still shows GRID (the failed writes never landed).
        assert driver.send_characters(GRID) == (True, False)

    def test_a_sequence_upload_is_refused_too(self):
        from src.outputs.plugin_base import TimedFrame

        plugin = Sign()
        plugin.behave = fail
        sequences = []
        plugin.write_sequence = lambda frames, cancel: sequences.append(frames) or WriteResult(True, True)
        driver = driver_for(plugin)
        for i in range(OUTPUT_BREAKER_THRESHOLD):
            driver.send_characters(frame(i))
        result = driver.write_sequence([TimedFrame(GRID, 0)])
        assert (result.success, result.was_sent) == (False, False)
        assert sequences == []

    def test_a_partial_write_does_not_count(self):
        from src.send_outcome import FrameRegion

        plugin = Sign()
        plugin.behave = lambda _n: WriteResult(False, True, partial=True, failed_regions=(FrameRegion(0, 0, 3, 15),))
        driver = driver_for(plugin)
        for i in range(OUTPUT_BREAKER_THRESHOLD + 1):
            driver.send_characters(frame(i))
        assert plugin.calls == OUTPUT_BREAKER_THRESHOLD + 1


class TestTheBoardReportsWhy:
    """The engine's recorded send error carries the output's reason."""

    def test_a_failed_engine_send_names_the_outputs_reason(self):
        from tests.test_per_board_engine import _board, _drive, _page_service, _schedule_service, _service_with_runtimes

        boards = [_board("b1", "One")]
        svc, clients = _service_with_runtimes(boards)
        clients["b1"].render.return_value = (False, False)
        clients["b1"].last_write_error = "Output acme_sign stopped after 3 failed writes in a row."
        sent = _drive(
            svc, boards, pages=_page_service({"pA": {"content": "ALPHA"}}), schedule=_schedule_service({"b1": "pA"})
        )
        assert sent is False
        assert svc.get_last_send_error("b1") == (
            "Failed to send active page to board: pA (Output acme_sign stopped after 3 failed writes in a row.)"
        )

    def test_a_failed_manual_write_names_the_outputs_reason(self):
        from src.ops.executors import _settle_send

        target = SimpleNamespace(client=SimpleNamespace(last_write_error="Output acme_sign: it timed out."))
        result = _settle_send(target, WriteResult(False, False), failure="Failed to send message", success="Sent")
        assert result["error"] == "Failed to send message (Output acme_sign: it timed out.)"

    def test_a_driver_without_a_reason_keeps_todays_message(self):
        assert write_failure_reason(SimpleNamespace()) is None
        from unittest.mock import MagicMock

        assert write_failure_reason(MagicMock()) is None


# --- refused releases are remembered (A17 follow-up) ------------------------------------------


@pytest.fixture
def installed(tmp_path, monkeypatch):
    """The recording output installed from a local origin; (origin, external, head)."""
    from src.plugins import sources
    from src.plugins.sources import clone_or_update_repo

    monkeypatch.setattr(sources, "_validate_git_url", lambda url: (True, ""))
    origin, head = output_repo(tmp_path / "origin")
    external = tmp_path / "external"
    external.mkdir()
    assert clone_or_update_repo(origin.as_uri(), PLUGIN_ID, external_dir=external) == (True, "")
    return origin, external, head


def _check(clone, remote_sha):
    from unittest import mock

    from src.plugins.sources import check_plugin_update_available

    # get_remote_head_sha refuses non-https remotes; the local SHA and the
    # incoming manifest are the real ones.
    with mock.patch("src.plugins.sources.get_remote_head_sha", return_value=remote_sha):
        return check_plugin_update_available(clone)


def _broken_release(origin):
    (origin / "__init__.py").write_text("raise ImportError('broken release')\n", "utf-8")
    return commit_all(origin, "broken")


def _reload_failing_once():
    calls = []

    def reload():
        calls.append(1)
        return "Failed to import plugin module: broken release" if len(calls) == 1 else None

    return reload


class TestRefusedReleaseMemory:
    def test_a_rolled_back_release_is_not_offered_again(self, installed):
        from src.plugins.sources import update_external_plugin

        origin, external, _ = installed
        bad = _broken_release(origin)
        assert update_external_plugin(PLUGIN_ID, external, reload=_reload_failing_once()).stage == "rolled_back"
        result = _check(external / PLUGIN_ID, bad)
        assert result.available is False
        assert result.blocked_reason == (
            f"Release {bad[:12]} was refused when it was applied and is not offered again "
            "(a newer release will be): Failed to import plugin module: broken release"
        )

    def test_the_memory_survives_a_restart(self, installed):
        from src.config_manager import ConfigManager
        from src.plugins.sources import update_external_plugin

        origin, external, _ = installed
        bad = _broken_release(origin)
        update_external_plugin(PLUGIN_ID, external, reload=_reload_failing_once())
        ConfigManager._instance = None  # a restart: the store is re-read from disk
        assert _check(external / PLUGIN_ID, bad).available is False

    def test_a_newer_release_is_offered_and_clears_it(self, installed):
        from src.plugins.sources import update_external_plugin
        from src.plugins.update_refusals import refused_update

        origin, external, _ = installed
        good_init = (origin / "__init__.py").read_text("utf-8")
        _broken_release(origin)
        update_external_plugin(PLUGIN_ID, external, reload=_reload_failing_once())
        (origin / "__init__.py").write_text(good_init + "\n# fixed\n", "utf-8")
        fixed = commit_all(origin, "fixed")
        assert _check(external / PLUGIN_ID, fixed).available is True
        assert refused_update(PLUGIN_ID) is None

    def test_a_release_refused_by_verification_is_remembered(self, installed):
        from src.plugins.sources import update_external_plugin
        from src.plugins.update_refusals import refused_update

        origin, external, _ = installed
        set_output_api(origin, 2)
        bad = commit_all(origin, "api 2")
        update_external_plugin(PLUGIN_ID, external)
        assert refused_update(PLUGIN_ID).sha == bad

    def test_a_reinstall_that_is_rolled_back_is_remembered(self, installed):
        from src.plugins.sources import install_git_plugin
        from src.plugins.update_refusals import refused_update

        origin, external, _ = installed
        set_output_api(origin, 2)
        bad = commit_all(origin, "api 2")
        install_git_plugin(origin.as_uri(), plugin_id=PLUGIN_ID, external_dir=external)
        assert refused_update(PLUGIN_ID).sha == bad

    def test_a_good_update_remembers_nothing(self, installed):
        from src.plugins.sources import update_external_plugin
        from src.plugins.update_refusals import refused_update

        origin, external, head = installed
        (origin / "CHANGELOG.txt").write_text("next", "utf-8")
        commit_all(origin, "good")
        assert update_external_plugin(PLUGIN_ID, external, reload=lambda: None).ok is True
        assert refused_update(PLUGIN_ID) is None
        assert git(external / PLUGIN_ID, "rev-parse", "HEAD") != head
