"""Display-loop timing under a fake clock (issue #1734, epic #1730 Phase 0).

``DisplayService.run()`` is the heartbeat of the whole product — tick cadence,
schedule-boundary detection, collection rotation — and until now it was only
ever exercised for crash resilience. Every hardware E2E forces a single tick.
Nothing crossed a real time boundary, and nothing asserted that a rotating
collection actually changes what is on the flaps. Phase 2 rewrites this loop.

So these tests run the real ``run()`` — the real ``schedule`` jobs, the real
collection resolution math — through *simulated* seconds, and assert on the
frames a stub board client receives and the (fake) instant each one arrived.
Nothing sleeps: the loop's own ``time.sleep(1)`` is the hook the harness uses
to advance the clock, so the suite stays instantaneous and fully deterministic.

What is deliberately NOT asserted: how often the loop wakes up internally.
The 1 Hz wake-up is an implementation detail that issue #1740 is changing.
These tests pin the *observable* contract instead — the board is redriven at
the polling interval, a schedule boundary reaches the flaps within one polling
interval of the boundary, and a collection advances on its own cadence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import time as clock_time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import schedule

from src.collections.models import Collection, TimeModeConfig
from src.collections.service import CollectionService
from src.main import BoardRuntime, DisplayService
from tests.fake_clock import FakeClock, FakeTimeModule, fake_schedule_datetime, install_fake_time_service
from tests.helpers import decode_board_text

BOARD = {
    "id": "board-1",
    "name": "Living Room",
    "device_type": "flagship",
    "enabled": True,
    "paused": False,
    "api_mode": "local",
    "host": "mock-host",
    "port": 7000,
    "local_api_key": "test-key",
}

TRANSITIONS = SimpleNamespace(strategy="instant", step_interval_ms=0, step_size=1)

# 2026-07-15 is a Wednesday. 09:00:00Z is the schedule boundary these tests
# cross, and it also lands exactly on a 30-second collection slice boundary
# whose slice index is even — so a two-page time-mode collection with a 30s
# interval shows page_ids[0] from 09:00:00 and page_ids[1] from 09:00:30.
SCHEDULE_BOUNDARY = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
TEN_SECONDS_BEFORE = datetime(2026, 7, 15, 8, 59, 50, tzinfo=UTC)
TWENTY_SECONDS_IN = datetime(2026, 7, 15, 9, 0, 20, tzinfo=UTC)
THIRTY_SECONDS_IN = datetime(2026, 7, 15, 9, 0, 30, tzinfo=UTC)
FORTY_SECONDS_IN = datetime(2026, 7, 15, 9, 0, 40, tzinfo=UTC)
ONE_MINUTE_LATER = datetime(2026, 7, 15, 9, 1, tzinfo=UTC)
TWO_MINUTES_LATER = datetime(2026, 7, 15, 9, 2, tzinfo=UTC)
FIVE_MINUTES_LATER = datetime(2026, 7, 15, 9, 5, tzinfo=UTC)

COLLECTION_ID = "collection:11111111-2222-3333-4444-555555555555"


class RecordingBoardClient:
    """Stub board client recording every frame and the instant it arrived."""

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.sends: list[tuple[datetime, list[list[int]]]] = []
        self._last_characters = None
        self.use_cloud = False

    def render(self, board_array, **_kwargs):
        self.sends.append((self.clock.utc, [row[:] for row in board_array]))
        self._last_characters = [row[:] for row in board_array]
        return True, True

    def read_current_message(self, sync_cache: bool = False):
        return None

    def clear_cache(self):
        self._last_characters = None

    @property
    def timeline(self) -> list[tuple[datetime, str]]:
        """(when it was sent, what it said) for every frame the board got."""
        return [(when, decode_board_text(frame)) for when, frame in self.sends]

    @property
    def texts(self) -> list[str]:
        return [text for _when, text in self.timeline]

    @property
    def times(self) -> list[datetime]:
        return [when for when, _text in self.timeline]

    def first_sent_at(self, text: str) -> datetime:
        """When the board first showed ``text``. Fails loudly if it never did."""
        for when, sent in self.timeline:
            if sent == text:
                return when
        raise AssertionError(f"{text!r} never reached the board; got {self.texts}")


class SilenceOffConfigManager:
    """Config store with silence disabled — this suite is about the loop only.

    Kept real (rather than mocking ``Config``) so the loop's per-second silence
    boundary check runs its production code path and is proven not to disturb
    the cadence under test.
    """

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


def settings_service(*, polling_interval: int, schedule_enabled: bool, active_page_id: str | None = None) -> MagicMock:
    svc = MagicMock()
    svc.get_board_settings.return_value = SimpleNamespace(boards=[BOARD])
    svc.get_primary_board_id.return_value = BOARD["id"]
    svc.is_paused.return_value = False
    svc.is_schedule_enabled.return_value = schedule_enabled
    svc.get_active_page_id.return_value = active_page_id
    svc.get_transition_settings.return_value = TRANSITIONS
    svc.consume_temporary_override.return_value = None
    svc.get_polling_interval.return_value = polling_interval
    return svc


def page_service(specs) -> MagicMock:
    """``specs`` maps page id -> content, or page id -> callable returning it."""

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
    svc.list_pages.return_value = [_page(pid) for pid in specs]
    return svc


class LoopHarness:
    """Drives ``DisplayService.run()`` through simulated time.

    The loop's ``time.sleep`` is redirected here: each call advances the clock
    by the requested amount and, once the clock has passed ``run_until``, flips
    the service's ``running`` flag so the loop exits on its own terms.
    ``run_until`` is inclusive — the work scheduled for that exact instant runs
    before the loop stops. ``max_ticks`` is a safety net: a loop that stopped
    sleeping would otherwise hang the suite.
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


@pytest.fixture(autouse=True)
def _clear_schedule():
    """``run()`` registers jobs on the library's global scheduler."""
    schedule.clear()
    yield
    schedule.clear()


@pytest.fixture
def loop(monkeypatch):
    """Factory that runs ``DisplayService.run()`` over a simulated window."""

    def _run(
        *,
        start: datetime,
        run_until: datetime,
        settings,
        pages,
        schedules=None,
        collections=None,
    ) -> RecordingBoardClient:
        clock = FakeClock(start)
        service = DisplayService()
        client = RecordingBoardClient(clock)
        service.runtimes = {BOARD["id"]: BoardRuntime(client=client, board_id=BOARD["id"])}
        service._primary_board_id = BOARD["id"]

        harness = LoopHarness(service, clock, run_until)
        fake_time = FakeTimeModule(clock, on_sleep=harness._on_sleep)

        install_fake_time_service(monkeypatch, clock)
        monkeypatch.setattr("src.config.get_config_manager", SilenceOffConfigManager)
        monkeypatch.setattr("src.config_manager.get_config_manager", SilenceOffConfigManager)
        # The loop's own clock, the schedule library's clock, and the clock the
        # collection resolver reads — all three point at the same fake instant.
        monkeypatch.setattr("src.main.time", fake_time)
        monkeypatch.setattr("src.collections.service.time", FakeTimeModule(clock))
        monkeypatch.setattr(schedule, "datetime", fake_schedule_datetime(clock))

        with (
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_page_service", return_value=pages),
            patch("src.main.get_schedule_service", return_value=schedules or MagicMock()),
            patch("src.main.get_collection_service", return_value=collections or MagicMock()),
            patch.object(service, "_check_trigger_override", return_value=None),
            patch.object(service, "request_board_refresh"),
        ):
            service.run()

        return client

    return _run


class TestScheduleBoundary:
    """A schedule entry taking over must reach the board, and reach it soon."""

    @staticmethod
    def _schedule_service():
        """Morning page until 09:00, day page from 09:00 — by wall-clock time."""
        svc = MagicMock()
        svc.get_active_page_id.side_effect = lambda t, day, board_id=None: (
            "page-day" if t >= clock_time(9, 0) else "page-morning"
        )
        return svc

    def test_board_switches_pages_when_the_clock_crosses_a_schedule_boundary(self, loop):
        client = loop(
            start=TEN_SECONDS_BEFORE,
            run_until=THIRTY_SECONDS_IN,
            settings=settings_service(polling_interval=15, schedule_enabled=True),
            pages=page_service({"page-morning": "MORNING", "page-day": "DAY"}),
            schedules=self._schedule_service(),
        )

        assert client.texts == ["MORNING", "DAY"]

    def test_the_new_page_reaches_the_board_within_one_polling_interval(self, loop):
        polling_interval = 15
        client = loop(
            start=TEN_SECONDS_BEFORE,
            run_until=TWO_MINUTES_LATER,
            settings=settings_service(polling_interval=polling_interval, schedule_enabled=True),
            pages=page_service({"page-morning": "MORNING", "page-day": "DAY"}),
            schedules=self._schedule_service(),
        )

        lag = (client.first_sent_at("DAY") - SCHEDULE_BOUNDARY).total_seconds()
        assert 0 <= lag <= polling_interval

    def test_no_further_sends_once_the_schedule_settles_on_a_page(self, loop):
        """Unchanged content is not re-pushed tick after tick."""
        client = loop(
            start=SCHEDULE_BOUNDARY,
            run_until=FIVE_MINUTES_LATER,
            settings=settings_service(polling_interval=15, schedule_enabled=True),
            pages=page_service({"page-morning": "MORNING", "page-day": "DAY"}),
            schedules=self._schedule_service(),
        )

        assert client.texts == ["DAY"]


class TestCollectionRotation:
    """A time-mode collection must advance what is on the board on its own."""

    @staticmethod
    def _collection_service():
        """A real CollectionService over one in-memory two-page collection."""
        collection = Collection(
            id=COLLECTION_ID,
            name="Rotation",
            page_ids=["page-a", "page-b"],
            selection_mode="time",
            time=TimeModeConfig(interval_seconds=30),
        )
        storage = MagicMock()
        storage.get.side_effect = lambda cid: collection if cid == COLLECTION_ID else None
        return CollectionService(storage=storage)

    def test_collection_advances_to_its_next_page_at_the_interval_boundary(self, loop):
        """The polling interval is 5 minutes, so only rotation can drive this."""
        client = loop(
            start=TWENTY_SECONDS_IN,
            run_until=FORTY_SECONDS_IN,
            settings=settings_service(polling_interval=300, schedule_enabled=False, active_page_id=COLLECTION_ID),
            pages=page_service({"page-a": "ALPHA", "page-b": "BETA"}),
            collections=self._collection_service(),
        )

        assert client.texts == ["ALPHA", "BETA"]

    def test_the_next_page_arrives_on_the_interval_boundary_not_at_the_next_poll(self, loop):
        client = loop(
            start=TWENTY_SECONDS_IN,
            run_until=ONE_MINUTE_LATER,
            settings=settings_service(polling_interval=300, schedule_enabled=False, active_page_id=COLLECTION_ID),
            pages=page_service({"page-a": "ALPHA", "page-b": "BETA"}),
            collections=self._collection_service(),
        )

        assert (client.first_sent_at("BETA") - THIRTY_SECONDS_IN).total_seconds() <= 1

    def test_collection_keeps_rotating_across_several_intervals(self, loop):
        client = loop(
            start=TWENTY_SECONDS_IN,
            run_until=TWO_MINUTES_LATER,
            settings=settings_service(polling_interval=300, schedule_enabled=False, active_page_id=COLLECTION_ID),
            pages=page_service({"page-a": "ALPHA", "page-b": "BETA"}),
            collections=self._collection_service(),
        )

        # 09:00:20 -> 09:02:00 crosses a 30s boundary at :30, 1:00, 1:30 and 2:00.
        assert client.texts == ["ALPHA", "BETA", "ALPHA", "BETA", "ALPHA"]


def always_changing_page() -> MagicMock:
    """A page that renders differently every time it is asked.

    With this, a frame is missing from the board only because the loop did not
    poll — never because the dedupe cache swallowed an unchanged render. That
    makes the send timeline a direct readout of the loop's cadence.
    """
    counter = {"n": 0}

    def _content():
        counter["n"] += 1
        return f"FRAME {counter['n']}"

    return page_service({"page-x": _content})


class TestPollingCadence:
    """Board work happens at the configured polling interval."""

    def test_the_board_is_redriven_once_per_polling_interval(self, loop):
        start = SCHEDULE_BOUNDARY
        client = loop(
            start=start,
            run_until=ONE_MINUTE_LATER,
            settings=settings_service(polling_interval=15, schedule_enabled=False, active_page_id="page-x"),
            pages=always_changing_page(),
        )

        # 60 simulated seconds at a 15s interval: the initial send plus one per
        # interval. A board driven at 1 Hz would show ~60 frames instead.
        offsets = [(when - start).total_seconds() for when in client.times]
        assert offsets == [0, 15, 30, 45, 60]

    def test_raising_the_polling_interval_slows_the_board_down(self, loop):
        """Same simulated window, double the interval, half the frames."""
        start = SCHEDULE_BOUNDARY
        client = loop(
            start=start,
            run_until=ONE_MINUTE_LATER,
            settings=settings_service(polling_interval=30, schedule_enabled=False, active_page_id="page-x"),
            pages=always_changing_page(),
        )

        offsets = [(when - start).total_seconds() for when in client.times]
        assert offsets == [0, 30, 60]
