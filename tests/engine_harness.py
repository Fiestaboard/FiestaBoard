"""Shared harness for the display-engine equivalence corpus (issue #1850).

The engine redesign (#1751/#1752/#1754/#1755) must reproduce, byte for byte,
the sequence of board sends today's ``DisplayService`` produces. This module
provides the pieces ``tests/test_engine_equivalence.py`` uses to run the
CURRENT engine over a fake clock and capture that sequence as JSON goldens.

The clock/service plumbing here is deliberately duplicated-and-extended from
``tests/test_display_loop_timing.py`` (``RecordingBoardClient``,
``SilenceOffConfigManager``, the service factories, ``LoopHarness``) rather
than refactoring that file — it is the proven model for driving the real
``run()`` loop through simulated seconds, and this PR must not touch existing
suites. Once the redesign lands, the two can be unified.

Four clock seams MUST always be patched together, or part of the engine runs
on wall-clock time and the goldens stop being deterministic:

1. ``src.time_service._time_service`` — via ``install_fake_time_service``
   (silence-window math, schedule-mode page lookup).
2. ``src.main.time`` — the run loop's ``time.sleep`` / ``time.time``.
3. ``src.collections.service.time`` — collection slice math.
4. ``schedule.datetime`` — the schedule library's job-due decisions.

Scenarios that exercise the REAL ``TriggerService`` patch a fifth seam,
``src.triggers.service.datetime``, because trigger activation/expiry math
calls ``datetime.now()`` at module scope.

What the goldens pin is ONLY the send sequence — the (simulated time, board,
frame) triples handed to each board client. The run loop may evaluate
``check_and_send_active_page`` up to three times per simulated second (the
schedule job, the 1 Hz silence probe, and the collection gate); that internal
cadence is an implementation detail the redesign is free to change, so it is
never encoded here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import schedule

from src.main import BoardRuntime, DisplayService
from tests.fake_clock import (
    FakeClock,
    FakeTimeModule,
    fake_schedule_datetime,
    install_fake_time_service,
)
from tests.helpers import decode_board_rows

TRANSITIONS = SimpleNamespace(strategy="instant", step_interval_ms=0, step_size=1)


def make_board(board_id: str, *, name: str = "Board", device_type: str = "flagship", enabled: bool = True) -> dict:
    """A minimal-but-complete board dict of the shape settings storage holds."""
    return {
        "id": board_id,
        "name": name,
        "device_type": device_type,
        "enabled": enabled,
        "paused": False,
        "api_mode": "local",
        "host": "mock-host",
        "port": 7000,
        "local_api_key": "test-key",
    }


class GoldenRecordingClient:
    """Stub board client that records every render into a shared sink.

    Unlike ``RecordingBoardClient`` in test_display_loop_timing.py, records
    land in a caller-supplied ``sink`` list shared by every board's client,
    so CROSS-BOARD ordering within a pass is captured. Each record is the
    golden-file dict::

        {"t": "<sim-time ISO>", "board": "<board_id>", "rows": [...]}

    ``fail_when`` (a ``datetime -> bool`` predicate over the simulated UTC
    instant) injects hardware failure: while it returns True, ``render``
    returns ``(False, False)`` and does not update the client-side cache —
    but the attempt is still recorded in the sink, because the retry cadence
    the engine produces after a failure IS observable behavior worth pinning.
    Per-attempt success is additionally kept in ``attempts`` for assertions
    that need to tell the failed attempt from the successful retry.
    """

    def __init__(
        self,
        clock: FakeClock,
        board_id: str,
        sink: list[dict],
        fail_when: Callable[[datetime], bool] | None = None,
    ):
        self.clock = clock
        self.board_id = board_id
        self.sink = sink
        self.fail_when = fail_when
        self.attempts: list[tuple[datetime, bool]] = []
        self._last_characters = None
        self.use_cloud = False

    def render(self, board_array, **_kwargs):
        ok = not (self.fail_when is not None and self.fail_when(self.clock.utc))
        self.sink.append(
            {
                "t": self.clock.utc.isoformat(),
                "board": self.board_id,
                "rows": decode_board_rows(board_array),
            }
        )
        self.attempts.append((self.clock.utc, ok))
        if not ok:
            return False, False
        self._last_characters = [row[:] for row in board_array]
        return True, True

    def read_current_message(self, sync_cache: bool = False):
        return None

    def clear_cache(self):
        self._last_characters = None


# --------------------------------------------------------------------------
# Config-manager stubs (silence off / silence configured)
# --------------------------------------------------------------------------


class SilenceOffConfigManager:
    """Config store with silence disabled — scenarios not about silence."""

    def get_feature(self, name: str) -> dict:
        if name == "silence_schedule":
            return {"enabled": False, "by_board": {}}
        return {}

    def get_general(self) -> dict:
        return {}

    def get_board(self) -> dict:
        return {}

    def migrate_silence_schedule_to_utc(self) -> bool:
        return False

    def migrate_silence_schedule_to_per_board(self) -> int:
        return 0


class SilenceConfigManager(SilenceOffConfigManager):
    """Config store holding one install-wide silence schedule (no per-board overrides)."""

    def __init__(self, silence: dict):
        self.silence = silence

    def get_feature(self, name: str) -> dict:
        return dict(self.silence) if name == "silence_schedule" else {}


def silence_feature(
    *, start_time: str, end_time: str, enabled: bool = True, mode: str = "indicator", **overrides
) -> dict:
    """An install-wide silence schedule, times in the UTC ISO form config carries."""
    feature = {
        "enabled": enabled,
        "start_time": start_time,
        "end_time": end_time,
        "mode": mode,
        "page_id": None,
        "indicator_text": "SNOOZING",
        "indicator_position": "center",
        "by_board": {},
    }
    feature.update(overrides)
    return feature


# --------------------------------------------------------------------------
# Service-mock factories (multi-board generalizations of the loop-test ones)
# --------------------------------------------------------------------------


def make_settings_service(
    *,
    boards: list[dict],
    polling_interval: int,
    schedule_enabled: bool = False,
    active_page_ids: dict[str, str] | None = None,
    temporary_overrides: list | None = None,
) -> MagicMock:
    """Settings stub for N boards.

    ``active_page_ids`` maps board id -> active page/collection id; a call
    with ``board_id=None`` (the run loop's collection gate) resolves to the
    primary board. ``temporary_overrides`` are consumed one per call, in
    order, then ``consume_temporary_override`` returns None.
    """
    primary_id = boards[0]["id"]
    pages_by_board = dict(active_page_ids or {})
    pending_overrides = list(temporary_overrides or [])

    svc = MagicMock()
    svc.get_board_settings.return_value = SimpleNamespace(boards=boards)
    svc.get_primary_board_id.return_value = primary_id
    svc.is_paused.side_effect = lambda board_id=None: False
    svc.is_schedule_enabled.side_effect = lambda board_id=None: schedule_enabled
    svc.get_active_page_id.side_effect = lambda board_id=None: pages_by_board.get(board_id or primary_id)
    svc.get_transition_settings.return_value = TRANSITIONS
    svc.get_polling_interval.return_value = polling_interval
    svc.should_send_to_board.return_value = True
    svc.consume_temporary_override.side_effect = lambda: pending_overrides.pop(0) if pending_overrides else None
    return svc


def make_page_service(specs: dict) -> MagicMock:
    """Page stub: ``specs`` maps page id -> content, or -> callable returning it.

    ``render_page`` (the inline-override path) renders a Page object's own
    ``template`` lines, so one-off overrides flow through without a spec entry.
    """

    def _page(page_id):
        if page_id not in specs:
            return None
        return SimpleNamespace(
            id=page_id,
            device_type="flagship",
            notes_wide=1,
            notes_tall=1,
            transition_strategy=None,
            transition_interval_ms=None,
            transition_step_size=None,
        )

    def _content(page_id):
        value = specs[page_id]
        return value() if callable(value) else value

    svc = MagicMock()
    svc.get_page.side_effect = _page
    svc.preview_page.side_effect = lambda pid, force_refresh=False: SimpleNamespace(
        available=pid in specs, formatted=_content(pid) if pid in specs else "", error=None
    )
    svc.render_page.side_effect = lambda page, context=None: SimpleNamespace(
        available=True,
        formatted="\n".join(page.template) if getattr(page, "template", None) else "",
        error=None,
    )
    svc.list_pages.return_value = [_page(pid) for pid in specs]
    return svc


# --------------------------------------------------------------------------
# Trigger stubs (driven through the REAL TriggerService)
# --------------------------------------------------------------------------


class StubTriggerPlugin:
    """A trigger-capable plugin whose condition is a clock-time window.

    ``check_triggers`` returns the given results only while the simulated
    instant is inside ``[fire_from, fire_until)`` — a momentary real-world
    event. The REAL ``TriggerService`` then owns activation, priority
    selection, and duration-based expiry.
    """

    def __init__(self, clock: FakeClock, *, fire_from: datetime, fire_until: datetime, results: list):
        self.clock = clock
        self.fire_from = fire_from
        self.fire_until = fire_until
        self.results = results
        self.plugin_id = "stub_trigger"
        self.enabled = True
        self.supports_triggers = True
        self.config: dict = {}

    def check_triggers(self):
        if self.fire_from <= self.clock.utc < self.fire_until:
            return list(self.results)
        return []


class StubPluginRegistry:
    """Registry double exposing exactly what ``_check_trigger_override`` reads."""

    def __init__(self, plugins: list):
        self.trigger_plugins = {p.plugin_id: p for p in plugins}

    def get_plugin(self, plugin_id):
        return self.trigger_plugins.get(plugin_id)


def fake_trigger_datetime(clock: FakeClock):
    """Stand-in for ``datetime`` as ``src.triggers.service`` sees it.

    ``TriggerService`` stamps/compares activation with naive
    ``datetime.now()`` at module scope; this pins those calls to the fake
    clock so trigger expiry is simulated-time math, not wall-clock math.
    (``ActiveTrigger``'s ``default_factory`` captured the real ``datetime.now``
    at import time, but ``activate_trigger`` always passes ``activated_at``
    explicitly, so the module-attribute patch covers every live call site.)
    """

    class _Datetime:
        @staticmethod
        def now(tz=None):
            if tz is None:
                return clock.utc.replace(tzinfo=None)
            return clock.utc.astimezone(tz)

    return _Datetime


# --------------------------------------------------------------------------
# Scenario runner
# --------------------------------------------------------------------------


class LoopHarness:
    """Drives ``DisplayService.run()`` through simulated time.

    The loop's ``time.sleep`` is redirected here: each call advances the
    clock and, once past ``run_until`` (inclusive — work scheduled for that
    exact instant still runs), flips ``service.running`` so the loop exits on
    its own terms. ``max_ticks`` guards against a loop that stops sleeping.
    """

    def __init__(self, service: DisplayService, clock: FakeClock, run_until: datetime, max_ticks: int = 5000):
        self.service = service
        self.clock = clock
        self.run_until = run_until
        self.max_ticks = max_ticks
        self.ticks = 0

    def _on_sleep(self, seconds: float) -> None:
        self.ticks += 1
        if self.ticks > self.max_ticks:
            raise AssertionError(f"run() slept {self.ticks} times without reaching {self.run_until}")
        self.clock.advance(seconds)
        if self.clock.utc > self.run_until:
            self.service.running = False


@dataclass
class ScenarioResult:
    """What one scenario run produced: the golden send records plus handles."""

    sends: list[dict]
    service: DisplayService
    clients: dict[str, GoldenRecordingClient] = field(default_factory=dict)


def run_engine_scenario(
    monkeypatch,
    *,
    start: datetime,
    run_until: datetime,
    boards: list[dict],
    settings: MagicMock,
    pages: MagicMock,
    schedules: MagicMock | None = None,
    collections=None,
    config_manager=None,
    trigger_registry_factory: Callable[[FakeClock], StubPluginRegistry] | None = None,
    fail_when: dict[str, Callable[[datetime], bool]] | None = None,
) -> ScenarioResult:
    """Run the REAL ``DisplayService.run()`` over ``[start, run_until]``.

    Builds one ``GoldenRecordingClient``/``BoardRuntime`` per board dict (the
    first board is primary), patches the four clock seams plus the service
    getters, and returns every board send in cross-board order.

    ``trigger_registry_factory`` chooses the trigger seam: ``None`` stubs
    ``_check_trigger_override`` out entirely (the model suites' default);
    a factory (called with the scenario's clock) instead builds a
    ``StubPluginRegistry`` and patches ``get_plugin_registry`` plus the
    trigger clock so the REAL ``TriggerService`` runs. Callers using triggers
    must reset the trigger-service singleton around the test.

    ``fail_when`` maps board id -> predicate for injected render failures.
    """
    clock = FakeClock(start)
    service = DisplayService()
    sink: list[dict] = []
    clients: dict[str, GoldenRecordingClient] = {}
    for board in boards:
        board_id = board["id"]
        clients[board_id] = GoldenRecordingClient(clock, board_id, sink, fail_when=(fail_when or {}).get(board_id))
        service.runtimes[board_id] = BoardRuntime(client=clients[board_id], board_id=board_id)
    service._primary_board_id = boards[0]["id"]

    harness = LoopHarness(service, clock, run_until)
    fake_time = FakeTimeModule(clock, on_sleep=harness._on_sleep)
    cm = config_manager if config_manager is not None else SilenceOffConfigManager()

    install_fake_time_service(monkeypatch, clock)
    monkeypatch.setattr("src.config.get_config_manager", lambda: cm)
    monkeypatch.setattr("src.config_manager.get_config_manager", lambda: cm)
    # The loop's own clock, the schedule library's clock, and the clock the
    # collection resolver reads — all pointing at the same fake instant.
    monkeypatch.setattr("src.main.time", fake_time)
    monkeypatch.setattr("src.collections.service.time", FakeTimeModule(clock))
    monkeypatch.setattr(schedule, "datetime", fake_schedule_datetime(clock))

    monkeypatch.setattr("src.main.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.main.get_page_service", lambda: pages)
    monkeypatch.setattr("src.main.get_schedule_service", lambda: schedules if schedules is not None else MagicMock())
    monkeypatch.setattr(
        "src.main.get_collection_service", lambda: collections if collections is not None else MagicMock()
    )
    monkeypatch.setattr(service, "request_board_refresh", lambda *a, **k: None)

    if trigger_registry_factory is None:
        monkeypatch.setattr(service, "_check_trigger_override", lambda: None)
    else:
        trigger_registry = trigger_registry_factory(clock)
        monkeypatch.setattr("src.plugins.registry.get_plugin_registry", lambda: trigger_registry)
        monkeypatch.setattr("src.triggers.service.datetime", fake_trigger_datetime(clock))

    service.run()

    return ScenarioResult(sends=sink, service=service, clients=clients)
