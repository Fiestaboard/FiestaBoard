"""H2: when a display is next expected to change, from the hub's own rules.

``next_change_at`` (with ``next_change_reason`` and, when knowable,
``next_page_id``) is the earliest instant after now at which what drives the
display changes: its H1 override ends, its schedule hands over to a different
page, its silence window opens or closes, or the collection in force rotates.
Paused boards and boards with nothing ahead in the 8-day horizon report null.
Triggers are unknowable and never modelled.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.board_guards import SilenceTiming
from src.config import Config
from src.time_service import TimeService
from tests.test_v1_contract import _seed_page, board_client, boards, client  # noqa: F401 - fixtures

LA = ZoneInfo("America/Los_Angeles")


class FrozenTime(TimeService):
    """The real time service, pinned to one instant."""

    def __init__(self, instant: datetime):
        super().__init__("America/Los_Angeles")
        self.instant = instant.astimezone(UTC)

    def get_current_utc(self) -> datetime:
        return self.instant

    def get_current_time(self, timezone: str | None = None) -> datetime:
        return self.instant.astimezone(LA)


def _la(*args) -> datetime:
    return datetime(*args, tzinfo=LA)


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


@pytest.fixture
def clock(monkeypatch):
    def freeze(instant: datetime) -> FrozenTime:
        frozen = FrozenTime(instant)
        monkeypatch.setattr("src.time_service.get_time_service", lambda: frozen)
        monkeypatch.setattr("src.v1.routes_boards.get_time_service", lambda: frozen, raising=False)
        return frozen

    return freeze


@pytest.fixture
def quiet(monkeypatch):
    """No silence anywhere unless a test says otherwise."""
    monkeypatch.setattr(Config, "silence_config_for", staticmethod(lambda board_id=None: {"enabled": False}))
    monkeypatch.setattr(
        "src.board_guards.silence_timing",
        lambda config: SilenceTiming(
            active=False, next_change_utc=None, seconds_until_next_change=None, next_change_at=None
        ),
    )


@pytest.fixture
def board(client, boards, quiet):  # noqa: F811
    """The primary (flagship) board with schedule mode on and three pages."""
    from src.settings.service import get_settings_service

    primary, _ = boards
    get_settings_service().set_schedule_enabled(True, board_id=primary)
    pages = {name: _seed_page(client, name) for name in ("Breakfast", "Work", "Evening")}
    return primary, pages


def _schedule(board_id, page_id, start, end=None, **extra):
    from src.schedules.models import ScheduleCreate
    from src.schedules.service import get_schedule_service

    return get_schedule_service().create_schedule(
        ScheduleCreate(board_id=board_id, page_id=page_id, start_time=start, end_time=end, **extra)
    )


def _next(board_id):
    from src.schedules.next_change import next_change

    return next_change(board_id)


# --- The schedule -------------------------------------------------------------------


def test_the_next_schedule_boundary_where_the_page_changes(board, clock):
    board_id, pages = board
    _schedule(board_id, pages["Breakfast"], "07:00", "09:00")
    _schedule(board_id, pages["Work"], "09:00", "17:00")
    clock(_la(2026, 11, 9, 8, 15))
    change = _next(board_id)
    assert (change.at, change.reason, change.page_id) == (
        _utc(_la(2026, 11, 9, 9, 0)),
        "schedule",
        pages["Work"],
    )


def test_back_to_back_windows_on_the_same_page_are_not_a_change(board, clock):
    board_id, pages = board
    _schedule(board_id, pages["Work"], "09:00", "12:00")
    _schedule(board_id, pages["Work"], "12:00", "17:00")
    clock(_la(2026, 11, 9, 10, 0))
    change = _next(board_id)
    assert change.at == _utc(_la(2026, 11, 9, 17, 0)) and change.page_id is None


def test_the_default_page_fills_a_gap(board, clock):
    from src.schedules.service import get_schedule_service

    board_id, pages = board
    get_schedule_service().set_default_page(pages["Evening"], board_id=board_id)
    _schedule(board_id, pages["Work"], "09:00", "17:00")
    clock(_la(2026, 11, 9, 16, 0))
    change = _next(board_id)
    assert (change.at, change.page_id) == (_utc(_la(2026, 11, 9, 17, 0)), pages["Evening"])


def test_an_overnight_window_ends_the_next_morning(board, clock):
    board_id, pages = board
    _schedule(board_id, pages["Evening"], "22:00", "06:00")
    clock(_la(2026, 11, 9, 23, 0))
    change = _next(board_id)
    assert change.at == _utc(_la(2026, 11, 10, 6, 0)) and change.reason == "schedule"


def test_a_weekly_entry_on_another_day(board, clock):
    board_id, pages = board
    # 2026-11-09 is a Monday; the only entry is on Wednesdays.
    _schedule(board_id, pages["Work"], "09:00", "10:00", day_pattern="custom", custom_days=["wednesday"])
    clock(_la(2026, 11, 9, 12, 0))
    assert _next(board_id).at == _utc(_la(2026, 11, 11, 9, 0))


def test_nothing_within_the_horizon_is_null(board, clock):
    board_id, pages = board
    _schedule(board_id, pages["Work"], "09:00", "10:00", recurrence_type="one_off_date", one_off_date="2026-12-25")
    clock(_la(2026, 11, 9, 12, 0))
    change = _next(board_id)
    assert (change.at, change.reason, change.page_id) == (None, None, None)


def test_manual_mode_has_no_schedule_boundary(board, clock):
    from src.settings.service import get_settings_service

    board_id, pages = board
    _schedule(board_id, pages["Work"], "09:00", "17:00")
    get_settings_service().set_schedule_enabled(False, board_id=board_id)
    clock(_la(2026, 11, 9, 8, 0))
    assert _next(board_id).at is None


# --- DST -----------------------------------------------------------------------------


def test_a_boundary_in_the_spring_forward_gap_is_reported_at_the_end_of_the_gap(board, clock):
    board_id, pages = board
    _schedule(board_id, pages["Work"], "02:30", "05:00")
    clock(_la(2027, 3, 13, 23, 0))
    # 02:30 never happens on 2027-03-14; the wall clock jumps 02:00 -> 03:00 PDT (10:00 UTC).
    assert _next(board_id).at == "2027-03-14T10:00:00+00:00"


def test_a_repeated_fall_back_time_is_its_first_occurrence(board, clock):
    board_id, pages = board
    _schedule(board_id, pages["Work"], "01:30", "04:00")
    clock(_la(2026, 10, 31, 23, 0))
    # 01:30 happens twice on 2026-11-01; the first is 01:30 PDT (08:30 UTC).
    assert _next(board_id).at == "2026-11-01T08:30:00+00:00"


# --- The H1 override -------------------------------------------------------------------


def _override(board_id, expires_at, **kw):
    from src.settings.service import TemporaryOverride, get_settings_service

    get_settings_service().set_temporary_override(
        TemporaryOverride(template=["HI"], expires_at=expires_at.isoformat() if expires_at else None, **kw),
        board_id=board_id,
    )


def _tomorrow_at(hour, minute=0):
    # Overrides expire on the real clock; keep the frozen clock a day ahead of it.
    day = (datetime.now(LA) + timedelta(days=1)).date()
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=LA)


def test_a_timed_override_changes_when_it_ends_and_the_schedule_resumes(board, clock):
    board_id, pages = board
    _schedule(board_id, pages["Breakfast"], "07:00", "09:00")
    _schedule(board_id, pages["Work"], "09:00", "17:00")
    clock(_tomorrow_at(8, 0))
    _override(board_id, _tomorrow_at(9, 30))
    change = _next(board_id)
    assert (change.at, change.reason, change.page_id) == (_utc(_tomorrow_at(9, 30)), "override_ends", pages["Work"])


def test_an_override_reverting_to_a_page_names_it(board, clock):
    board_id, pages = board
    clock(_tomorrow_at(8, 0))
    _override(board_id, _tomorrow_at(8, 30), revert_mode="page", revert_page_id=pages["Evening"])
    assert _next(board_id).page_id == pages["Evening"]


def test_an_override_reverting_to_blank_names_no_page(board, clock):
    board_id, pages = board
    clock(_tomorrow_at(8, 0))
    _override(board_id, _tomorrow_at(8, 30), revert_mode="blank")
    change = _next(board_id)
    assert (change.reason, change.page_id) == ("override_ends", None)


def test_an_indefinite_override_holds(board, clock):
    board_id, pages = board
    _schedule(board_id, pages["Work"], "09:00", "17:00")
    clock(_tomorrow_at(8, 0))
    _override(board_id, None)
    assert _next(board_id).at is None


def test_another_displays_override_does_not_count(board, boards, clock):  # noqa: F811
    board_id, pages = board
    _, second = boards
    _schedule(board_id, pages["Work"], "09:00", "17:00")
    clock(_tomorrow_at(8, 0))
    _override(second, _tomorrow_at(8, 10))
    assert _next(board_id).reason == "schedule"


# --- Silence and pause ---------------------------------------------------------------------


def _silence(monkeypatch, *, active, at, mode="indicator", page_id=None):
    config = {"enabled": True, "mode": mode, "page_id": page_id}
    monkeypatch.setattr(Config, "silence_config_for", staticmethod(lambda board_id=None: config))
    monkeypatch.setattr(
        "src.board_guards.silence_timing",
        lambda cfg: SilenceTiming(
            active=active, next_change_utc=None, seconds_until_next_change=None, next_change_at=at
        ),
    )


def test_silenced_changes_when_the_window_ends(board, clock, monkeypatch):
    board_id, pages = board
    _schedule(board_id, pages["Breakfast"], "06:00", "08:00")
    _schedule(board_id, pages["Work"], "08:00", "17:00")
    clock(_la(2026, 11, 9, 5, 0))
    _silence(monkeypatch, active=True, at=_la(2026, 11, 9, 7, 0).astimezone(UTC).isoformat())
    change = _next(board_id)
    # The 06:00 schedule boundary is hidden by the silence treatment.
    assert (change.at, change.reason, change.page_id) == (
        _utc(_la(2026, 11, 9, 7, 0)),
        "silence_ends",
        pages["Breakfast"],
    )


def test_a_window_opening_before_the_next_boundary(board, clock, monkeypatch):
    board_id, pages = board
    _schedule(board_id, pages["Work"], "09:00", "23:00")
    clock(_la(2026, 11, 9, 20, 0))
    _silence(
        monkeypatch,
        active=False,
        at=_la(2026, 11, 9, 22, 0).astimezone(UTC).isoformat(),
        mode="page",
        page_id=pages["Evening"],
    )
    change = _next(board_id)
    assert (change.at, change.reason, change.page_id) == (
        _utc(_la(2026, 11, 9, 22, 0)),
        "silence_starts",
        pages["Evening"],
    )


def test_an_override_beats_silence(board, clock, monkeypatch):
    board_id, pages = board
    clock(_tomorrow_at(1, 0))
    _silence(monkeypatch, active=True, at=_tomorrow_at(7, 0).astimezone(UTC).isoformat())
    _override(board_id, _tomorrow_at(2, 0))
    assert _next(board_id).reason == "override_ends"


def test_a_paused_board_has_no_next_change(board, clock):
    from src.settings.service import get_settings_service

    board_id, pages = board
    _schedule(board_id, pages["Work"], "09:00", "17:00")
    get_settings_service().set_paused(True, board_id=board_id)
    clock(_la(2026, 11, 9, 8, 0))
    change = _next(board_id)
    assert (change.at, change.reason, change.page_id) == (None, None, None)


# --- Collections ------------------------------------------------------------------------------


def test_a_rotating_collection_changes_at_its_next_boundary(board, clock):
    from src.collections.models import CollectionCreate, TimeModeConfig
    from src.collections.service import get_collection_service

    board_id, pages = board
    collection = get_collection_service().create_collection(
        CollectionCreate(
            name="Mix", page_ids=[pages["Work"], pages["Evening"]], time=TimeModeConfig(interval_seconds=300)
        )
    )
    _schedule(board_id, collection.id, "09:00", "17:00")
    clock(datetime(2026, 11, 9, 18, 2, 0, tzinfo=UTC))  # 10:02 PST, 120 s into a 300 s slot
    change = _next(board_id)
    assert (change.at, change.reason, change.page_id) == ("2026-11-09T18:05:00+00:00", "collection", None)


# --- On the wire ------------------------------------------------------------------------------


def test_get_board_reports_the_next_change(client, board, clock, board_client):  # noqa: F811
    board_id, pages = board
    _schedule(board_id, pages["Breakfast"], "07:00", "09:00")
    _schedule(board_id, pages["Work"], "09:00", "17:00")
    clock(_la(2026, 11, 9, 8, 15))
    detail = client.get(f"/v1/boards/{board_id}").json()
    assert detail["next_change_at"] == "2026-11-09T17:00:00+00:00"
    assert detail["next_change_reason"] == "schedule"
    assert detail["next_page_id"] == pages["Work"]
