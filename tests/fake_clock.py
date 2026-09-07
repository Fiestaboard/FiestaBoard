"""Deterministic clock control for the display engine's timing tests.

Phase 0 of the engine-cleanup epic (#1730) needs tests that cross real time
boundaries — a silence window opening, a schedule entry taking over, a
collection rotating — without any ``sleep``. Everything here exists so a test
can *state* what time it is and drive production code at that instant.

Three seams are covered:

``FakeClock``
    The single source of "now" for a test. Holds one timezone-aware UTC
    instant and moves only when a test moves it.

``FakeTimeService``
    A real :class:`~src.time_service.TimeService` with only the two
    "what time is it" primitives overridden. Every piece of production logic
    (ISO parsing, silence-window math, timezone conversion) is inherited, so
    a test asserts against the real implementation at a controlled instant.

``FakeTimeModule`` / ``fake_schedule_datetime``
    Stand-ins for the ``time`` module and the ``schedule`` library's clock, so
    ``DisplayService.run()`` can be driven through simulated seconds. The fake
    ``sleep`` is where a test advances the clock — the suite never blocks.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from types import SimpleNamespace

from src.time_service import TimeService, _resolve_timezone


class FakeClock:
    """A movable "now", stored as a timezone-aware UTC datetime."""

    def __init__(self, start: datetime):
        if start.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware start instant")
        self.utc = start.astimezone(UTC)

    @property
    def epoch(self) -> float:
        """Unix timestamp, for the ``time.time()``-shaped call sites."""
        return self.utc.timestamp()

    def advance(self, seconds: float) -> datetime:
        self.utc = self.utc + timedelta(seconds=seconds)
        return self.utc

    def set(self, when: datetime) -> datetime:
        self.utc = when.astimezone(UTC)
        return self.utc


class FakeTimeService(TimeService):
    """A ``TimeService`` that reads its "now" from a :class:`FakeClock`."""

    def __init__(self, clock: FakeClock, default_timezone: str = "UTC"):
        super().__init__(default_timezone=default_timezone)
        self.clock = clock

    def get_current_utc(self) -> datetime:
        return self.clock.utc

    def get_current_time(self, timezone: str | None = None) -> datetime:
        if timezone is None:
            tz = self._default_tz
        else:
            tz, ok = _resolve_timezone(timezone)
            if not ok:
                tz = self._default_tz
        return self.clock.utc.astimezone(tz)


def install_fake_time_service(monkeypatch, clock: FakeClock, timezone: str = "UTC") -> FakeTimeService:
    """Point the process-wide ``get_time_service()`` singleton at ``clock``.

    Every production caller goes through that singleton, so this is the one
    seam needed to make silence windows and schedule lookups deterministic.
    """
    service = FakeTimeService(clock, default_timezone=timezone)
    monkeypatch.setattr("src.time_service._time_service", service)
    return service


class FakeTimeModule:
    """Drop-in for the ``time`` module, backed by a :class:`FakeClock`.

    ``sleep`` does not sleep: it hands the requested duration to ``on_sleep``,
    which is where the driving test advances the clock and decides when the
    loop under test should stop.
    """

    def __init__(self, clock: FakeClock, on_sleep=None):
        self.clock = clock
        self._on_sleep = on_sleep

    def time(self) -> float:
        return self.clock.epoch

    def monotonic(self) -> float:
        return self.clock.epoch

    def sleep(self, seconds: float) -> None:
        if self._on_sleep is None:
            self.clock.advance(seconds)
        else:
            self._on_sleep(seconds)


def fake_schedule_datetime(clock: FakeClock) -> SimpleNamespace:
    """A stand-in for the ``datetime`` module as the ``schedule`` library sees it.

    ``schedule`` decides whether a job is due with naive ``datetime.now()``
    comparisons. Swapping the module reference it holds lets a test move a
    real ``schedule.Scheduler`` through simulated time — the cadence logic
    under test stays the library's own, not a mock's.
    """

    class _Datetime:
        @staticmethod
        def now(tz=None):
            if tz is None:
                return clock.utc.replace(tzinfo=None)
            return clock.utc.astimezone(tz)

        @staticmethod
        def combine(*args, **kwargs):
            return datetime.combine(*args, **kwargs)

    return SimpleNamespace(datetime=_Datetime, timedelta=timedelta, time=dt_time)
