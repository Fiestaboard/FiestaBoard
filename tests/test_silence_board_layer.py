"""Silence mode verified at the board layer (issue #1733, epic #1730 Phase 0).

Silence mode has plenty of unit coverage, but all of it stops at settings
shapes and internal flags. Nothing asserted the thing an owner actually
observes: that the board **stops receiving their content** when the window
opens, shows whatever the silence mode calls for, and gets their content back
when the window closes.

These tests drive ``DisplayService`` the way the run loop does — one tick at a
time — and assert only on the frames a stub board client receives. The only
thing that changes between ticks is the clock: the silence window is crossed
by time passing, never by rewriting config mid-test, so what is locked down is
the real boundary behaviour that Phase 1 is about to refactor.

Real production code stays in the loop on purpose: ``Config.silence_config_for``
/ ``Config.is_silence_mode_active``, the UTC window math in ``TimeService``, and
the whole ``check_and_send_for_board`` dispatch. Only the clock, the config
store, and the board client are substituted.

Per-board silence (#1788 / PR #1801): the silence schedule is configured here
on the **install-wide** layer with an empty ``by_board``, which is exactly the
"board with no override of its own" case. That resolves identically before and
after per-board silence lands, so these assertions hold either way.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.main import BoardRuntime, DisplayService
from tests.fake_clock import FakeClock, install_fake_time_service
from tests.helpers import decode_board_rows, decode_board_text

# A single flagship board. Silence geometry resolves from the first configured
# board both before and after PR #1801, so a 6x22 grid is expected either way.
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

PAGE_TEXT = "GOOD MORNING"

# Quiet hours 22:00-07:00 UTC, stored in the UTC ISO format the config carries
# once migrated. Spans midnight, which is the interesting case for the window
# math.
SILENCE_START = "22:00+00:00"
SILENCE_END = "07:00+00:00"

BEFORE_WINDOW = datetime(2026, 7, 15, 21, 59, tzinfo=UTC)
INSIDE_WINDOW = datetime(2026, 7, 15, 23, 30, tzinfo=UTC)
AFTER_WINDOW = datetime(2026, 7, 16, 7, 30, tzinfo=UTC)

TRANSITIONS = SimpleNamespace(strategy="instant", step_interval_ms=0, step_size=1)


class RecordingBoardClient:
    """Stub board client that records every frame handed to the hardware."""

    def __init__(self):
        self.frames: list[list[list[int]]] = []
        self._last_characters = None
        self.use_cloud = False

    def render(self, board_array, **_kwargs):
        self.frames.append([row[:] for row in board_array])
        self._last_characters = [row[:] for row in board_array]
        return True, True

    def read_current_message(self, sync_cache: bool = False):
        return None

    def clear_cache(self):
        self._last_characters = None

    @property
    def texts(self) -> list[str]:
        return [decode_board_text(frame) for frame in self.frames]


class StubConfigManager:
    """Config store holding just the silence feature, so nothing touches disk.

    The migration hooks are no-ops: the window is already in UTC ISO form, and
    per-board seeding (#1788) has nothing to do for an install-wide schedule.
    """

    def __init__(self, silence: dict):
        self.silence = silence

    def get_feature(self, name: str) -> dict:
        return dict(self.silence) if name == "silence_schedule" else {}

    def get_general(self) -> dict:
        return {}

    def get_board(self) -> dict:
        return {}

    def migrate_silence_schedule_to_utc(self) -> bool:
        return False

    def migrate_silence_schedule_to_per_board(self) -> int:
        return 0


def silence_feature(*, enabled=True, mode="indicator", **overrides) -> dict:
    """An install-wide silence schedule with no per-board overrides."""
    feature = {
        "enabled": enabled,
        "start_time": SILENCE_START,
        "end_time": SILENCE_END,
        "mode": mode,
        "page_id": None,
        "indicator_text": "SNOOZING",
        "indicator_position": "center",
        # Empty per-board layer (#1788): board-1 has no override, so it
        # resolves to the install-wide values above.
        "by_board": {},
    }
    feature.update(overrides)
    return feature


@pytest.fixture
def clock():
    return FakeClock(BEFORE_WINDOW)


@pytest.fixture
def board():
    """A DisplayService wired to one recording client, plus that client."""
    service = DisplayService()
    client = RecordingBoardClient()
    service.runtimes = {BOARD["id"]: BoardRuntime(client=client, board_id=BOARD["id"])}
    service._primary_board_id = BOARD["id"]
    return service, client


@pytest.fixture
def settings_service():
    svc = MagicMock()
    svc.get_board_settings.return_value = SimpleNamespace(boards=[BOARD])
    svc.get_primary_board_id.return_value = BOARD["id"]
    svc.is_paused.return_value = False
    svc.is_schedule_enabled.return_value = False
    svc.get_active_page_id.return_value = "page-morning"
    svc.get_transition_settings.return_value = TRANSITIONS
    svc.consume_temporary_override.return_value = None
    return svc


def page_service(specs: dict[str, str]) -> MagicMock:
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

    svc = MagicMock()
    svc.get_page.side_effect = _page
    svc.preview_page.side_effect = lambda pid, force_refresh=False: SimpleNamespace(
        available=pid in specs, formatted=specs.get(pid, ""), error=None
    )
    svc.list_pages.return_value = [_page(pid) for pid in specs]
    return svc


class Ticker:
    """Runs single display ticks against a fixed set of stubbed services."""

    def __init__(self, service, settings, pages, config_manager, monkeypatch, clock):
        self.service = service
        self.settings = settings
        self.pages = pages
        self.clock = clock
        install_fake_time_service(monkeypatch, clock)
        monkeypatch.setattr("src.config.get_config_manager", lambda: config_manager)
        monkeypatch.setattr("src.config_manager.get_config_manager", lambda: config_manager)

    def tick(self, at: datetime | None = None) -> bool:
        """Run one display cycle, optionally moving the clock there first."""
        if at is not None:
            self.clock.set(at)
        with (
            patch("src.main.get_settings_service", return_value=self.settings),
            patch("src.main.get_page_service", return_value=self.pages),
            patch("src.main.get_schedule_service", return_value=MagicMock()),
            patch("src.main.get_collection_service", return_value=MagicMock()),
            patch.object(self.service, "_check_trigger_override", return_value=None),
            patch.object(self.service, "request_board_refresh"),
        ):
            return self.service.check_and_send_active_page()


@pytest.fixture
def ticker(board, settings_service, monkeypatch, clock):
    """Factory: build a Ticker for a given silence feature configuration."""

    def _build(feature: dict, pages: dict[str, str] | None = None) -> Ticker:
        return Ticker(
            service=board[0],
            settings=settings_service,
            pages=page_service(pages if pages is not None else {"page-morning": PAGE_TEXT}),
            config_manager=StubConfigManager(feature),
            monkeypatch=monkeypatch,
            clock=clock,
        )

    return _build


class TestSilenceWindowAtTheBoardLayer:
    def test_board_shows_page_content_before_the_window_opens(self, board, ticker):
        _service, client = board
        ticker(silence_feature()).tick(BEFORE_WINDOW)

        assert client.texts == [PAGE_TEXT]

    def test_crossing_into_the_window_replaces_page_content_with_the_indicator(self, board, ticker):
        _service, client = board
        tick = ticker(silence_feature()).tick

        tick(BEFORE_WINDOW)
        tick(INSIDE_WINDOW)

        assert client.texts == [PAGE_TEXT, "SNOOZING"]

    def test_page_content_is_never_sent_while_the_window_is_open(self, board, ticker):
        """Repeated ticks inside the window must not put content back on the board."""
        _service, client = board
        tick = ticker(silence_feature()).tick

        tick(INSIDE_WINDOW)
        tick(datetime(2026, 7, 16, 1, 0, tzinfo=UTC))
        tick(datetime(2026, 7, 16, 4, 0, tzinfo=UTC))

        assert client.texts == ["SNOOZING"]

    def test_crossing_out_of_the_window_restores_page_content(self, board, ticker):
        _service, client = board
        tick = ticker(silence_feature()).tick

        tick(BEFORE_WINDOW)
        tick(INSIDE_WINDOW)
        tick(AFTER_WINDOW)

        assert client.texts == [PAGE_TEXT, "SNOOZING", PAGE_TEXT]

    def test_freeze_mode_leaves_the_board_untouched_for_the_whole_window(self, board, ticker):
        """Freeze sends nothing at all — the pre-silence frame stays on the flaps."""
        _service, client = board
        tick = ticker(silence_feature(mode="freeze")).tick

        tick(BEFORE_WINDOW)
        frames_before = len(client.frames)
        tick(INSIDE_WINDOW)
        tick(datetime(2026, 7, 16, 3, 0, tzinfo=UTC))

        assert client.texts == [PAGE_TEXT]
        assert len(client.frames) == frames_before

    def test_freeze_mode_resumes_driving_the_board_after_the_window(self, board, ticker):
        _service, client = board
        tick = ticker(silence_feature(mode="freeze")).tick

        tick(BEFORE_WINDOW)
        tick(INSIDE_WINDOW)
        tick(AFTER_WINDOW)

        assert client.texts == [PAGE_TEXT, PAGE_TEXT]

    def test_page_mode_freezes_the_configured_silence_page_on_the_board(self, board, ticker):
        _service, client = board
        pages = {"page-morning": PAGE_TEXT, "page-night": "SLEEP WELL"}
        tick = ticker(silence_feature(mode="page", page_id="page-night"), pages=pages).tick

        tick(BEFORE_WINDOW)
        tick(INSIDE_WINDOW)
        tick(datetime(2026, 7, 16, 2, 0, tzinfo=UTC))

        assert client.texts == [PAGE_TEXT, "SLEEP WELL"]

    def test_indicator_frame_is_a_clean_board_sized_to_the_device(self, board, ticker):
        """The indicator replaces the content; it is not overlaid on it."""
        _service, client = board
        ticker(silence_feature()).tick(INSIDE_WINDOW)

        (frame,) = client.frames
        assert len(frame) == 6
        assert all(len(row) == 22 for row in frame)
        # Centered on a 6x22 flagship, every other flap blank.
        assert decode_board_rows(frame) == [
            " " * 22,
            " " * 22,
            " " * 22,
            "       SNOOZING       ",
            " " * 22,
            " " * 22,
        ]

    def test_a_disabled_schedule_never_silences_the_board(self, board, ticker):
        """Same clock, same window — only ``enabled`` differs."""
        _service, client = board
        tick = ticker(silence_feature(enabled=False)).tick

        tick(BEFORE_WINDOW)
        tick(INSIDE_WINDOW)

        assert client.texts == [PAGE_TEXT]

    def test_board_without_its_own_override_inherits_the_install_wide_window(self, board, ticker):
        """The #1788 inheritance rule, asserted at the board layer.

        ``by_board`` carries an entry for some *other* board and none for the
        board being driven, so the only way the indicator reaches this board is
        by resolving to the install-wide schedule.
        """
        _service, client = board
        feature = silence_feature()
        feature["by_board"] = {"some-other-board": {"enabled": False}}
        tick = ticker(feature).tick

        tick(BEFORE_WINDOW)
        tick(INSIDE_WINDOW)

        assert client.texts == [PAGE_TEXT, "SNOOZING"]
