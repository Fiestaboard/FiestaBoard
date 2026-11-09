# ruff: noqa: F811 - pytest fixtures are imported from their home modules
"""H8: ``GET /schedules/active/page?at=``, the schedule at a given instant.

The same answer as "now", for ``at``: the page the schedule (or the manual
pin) names then, its collection resolved then, the per-display override in
force then, and whether quiet hours cover it. Without ``at`` the answer is
unchanged except for the new ``silenced`` field. Pinned here, against the
real schedule and collection services.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.config import Config
from tests.test_v1_contract import _seed_page, board_client, boards, client  # noqa: F401 - fixtures

LA = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def la_hub(monkeypatch):
    from src.time_service import TimeService

    hub = TimeService("America/Los_Angeles")
    monkeypatch.setattr("src.time_service.get_time_service", lambda: hub)
    return hub


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(Config, "silence_config_for", staticmethod(lambda board_id=None: {"enabled": False}))


@pytest.fixture
def board(client, boards, la_hub, quiet):
    from src.settings.service import get_settings_service

    primary, _ = boards
    get_settings_service().set_schedule_enabled(True, board_id=primary)
    pages = {name: _seed_page(client, name) for name in ("Breakfast", "Work", "Evening")}
    return primary, pages


@pytest.fixture
def date_time_on(monkeypatch):
    """The real ``date_time`` plugin, enabled, in the hub's timezone: the
    plugin the hub's own rule editor seeds (``date_time.hour >= 17``)."""
    import json
    from pathlib import Path

    from src.plugins.registry import get_plugin_registry

    registry = get_plugin_registry()
    loaded = registry._plugins.get("date_time")
    if loaded is None:
        from plugins.date_time import DateTimePlugin as plugin_class
    else:
        plugin_class = type(loaded)
    manifest = json.loads((Path(__file__).parents[1] / "plugins/date_time/manifest.json").read_text())
    plugin = plugin_class(manifest)
    plugin.config = {"enabled": True, "timezone": "America/Los_Angeles"}
    monkeypatch.setitem(registry._plugins, "date_time", plugin)
    monkeypatch.setitem(registry._enabled, "date_time", True)
    return plugin


def _schedule(board_id, page_id, start, end=None, **extra):
    from src.schedules.models import ScheduleCreate
    from src.schedules.service import get_schedule_service

    return get_schedule_service().create_schedule(
        ScheduleCreate(board_id=board_id, page_id=page_id, start_time=start, end_time=end, **extra)
    )


def _collection(pages, **kw):
    from src.collections.models import CollectionCreate
    from src.collections.service import get_collection_service

    return get_collection_service().create_collection(CollectionCreate(name="Mix", page_ids=pages, **kw))


def _day(offset_days: int = 2):
    return (datetime.now(LA) + timedelta(days=offset_days)).date()


def _at(hour, minute=0, day=None) -> datetime:
    day = day or _day()
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=LA)


def _get(client, board_id, at=None):
    params = {"board_id": board_id}
    if at is not None:
        params["at"] = at if isinstance(at, str) else at.isoformat()
    return client.get("/schedules/active/page", params=params)


def _ok(client, board_id, at=None):
    response = _get(client, board_id, at)
    assert response.status_code == 200, response.text
    return response.json()


# ── what the schedule names at `at` ─────────────────────────────────────────


def test_the_schedule_is_answered_for_the_instant_asked(client, board):
    board_id, pages = board
    _schedule(board_id, pages["Breakfast"], "07:00", "09:00")
    _schedule(board_id, pages["Evening"], "18:00", "22:00")

    morning = _ok(client, board_id, _at(8, 15))
    evening = _ok(client, board_id, _at(19, 0))

    assert (morning["page_id"], morning["source"]) == (pages["Breakfast"], "schedule")
    assert (evening["page_id"], evening["current_time"]) == (pages["Evening"], "19:00")
    assert morning["current_day"] == _day().strftime("%A").lower()


def test_a_dated_entry_counts_only_on_its_date(client, board):
    board_id, pages = board
    day = _day(3)
    _schedule(board_id, pages["Work"], "10:00", "11:00", recurrence_type="one_off_date", one_off_date=day.isoformat())

    assert _ok(client, board_id, _at(10, 30, day))["page_id"] == pages["Work"]
    assert _ok(client, board_id, _at(10, 30, _day(4)))["page_id"] != pages["Work"]


def test_with_the_schedule_off_the_pin_is_the_answer(client, board):
    from src.settings.service import get_settings_service

    board_id, pages = board
    get_settings_service().set_schedule_enabled(False, board_id=board_id)
    get_settings_service().set_active_page_id(pages["Work"], board_id=board_id)

    body = _ok(client, board_id, _at(3, 0))

    assert (body["page_id"], body["source"], body["schedule_enabled"]) == (pages["Work"], "manual", False)


def test_an_offset_is_read_in_the_hubs_timezone(client, board):
    board_id, pages = board
    _schedule(board_id, pages["Breakfast"], "07:00", "09:00")
    at_utc = _at(8, 0).astimezone(UTC)

    body = _ok(client, board_id, at_utc.isoformat())

    assert body["page_id"] == pages["Breakfast"]
    assert body["at"] == at_utc.replace(microsecond=0).isoformat()


def test_a_now_query_echoes_no_instant(client, board):
    board_id, _ = board

    body = _ok(client, board_id)

    assert body["at"] is None
    assert body["silenced"] is False


# ── collections resolved at `at` ────────────────────────────────────────────


def test_a_rotating_collection_is_resolved_at_the_instant(client, board):
    board_id, pages = board
    members = [pages["Breakfast"], pages["Work"], pages["Evening"]]
    collection = _collection(members, selection_mode="time", time={"interval_seconds": 60})
    _schedule(board_id, collection.id, "00:00", "23:59")
    at = _at(12, 0, _day(2)).replace(second=30)

    body = _ok(client, board_id, at)

    assert body["page_id"] == collection.id
    assert body["resolved_page_id"] == collection.current_page_id_time(at.timestamp())
    assert body["resolved_next_check_seconds"] == 30


def test_a_formula_collection_sees_the_instant_as_now(client, board):
    board_id, pages = board
    rules = [{"expression": "HOUR(NOW()) >= 15", "page_id": pages["Evening"]}]
    collection = _collection(
        [pages["Breakfast"], pages["Evening"]],
        selection_mode="variable",
        variable={"rules": rules, "default_page_id": pages["Breakfast"]},
    )
    _schedule(board_id, collection.id, "00:00", "23:59")

    assert _ok(client, board_id, _at(16, 0))["resolved_page_id"] == pages["Evening"]
    assert _ok(client, board_id, _at(9, 0))["resolved_page_id"] == pages["Breakfast"]


def test_a_date_time_rule_reads_the_plugin_at_the_instant(client, board, date_time_on):
    """``date_time`` is computed at ``at``, not at the real current time: the
    16:00 and 18:00 answers differ whatever the hour is now."""
    board_id, pages = board
    rules = [{"expression": "date_time.hour >= 17", "page_id": pages["Evening"]}]
    collection = _collection(
        [pages["Breakfast"], pages["Evening"]],
        selection_mode="variable",
        variable={"rules": rules, "default_page_id": pages["Breakfast"]},
    )
    _schedule(board_id, collection.id, "00:00", "23:59")

    assert _ok(client, board_id, _at(16, 0))["resolved_page_id"] == pages["Breakfast"]
    assert _ok(client, board_id, _at(18, 0))["resolved_page_id"] == pages["Evening"]


# ── the per-display override in force at `at` (H1) ──────────────────────────


def _override(board_id, expires_at, **kw):
    from src.settings.service import TemporaryOverride, get_settings_service

    get_settings_service().set_temporary_override(
        TemporaryOverride(template=["HI"], expires_at=expires_at.isoformat() if expires_at else None, **kw),
        board_id=board_id,
    )


def test_an_override_still_running_at_the_instant_is_reported_with_its_time_left(client, board):
    board_id, _ = board
    now = datetime.now(UTC)
    _override(board_id, now + timedelta(hours=2))

    body = _ok(client, board_id, now + timedelta(hours=1))

    assert body["temporary_override"]["active"] is True
    assert 3500 <= body["temporary_override"]["remaining_seconds"] <= 3600


def test_an_override_that_will_have_ended_is_not(client, board):
    board_id, _ = board
    now = datetime.now(UTC)
    _override(board_id, now + timedelta(hours=2))

    assert _ok(client, board_id, now + timedelta(hours=3))["temporary_override"]["active"] is False


def test_an_override_until_cancelled_runs_at_any_later_instant(client, board):
    board_id, _ = board
    _override(board_id, None)

    assert _ok(client, board_id, datetime.now(UTC) + timedelta(days=30))["temporary_override"]["active"] is True


def test_an_override_had_not_started_at_an_earlier_instant(client, board):
    board_id, _ = board
    now = datetime.now(UTC)
    _override(board_id, now + timedelta(hours=2))

    assert _ok(client, board_id, now - timedelta(hours=1))["temporary_override"]["active"] is False


# ── quiet hours at `at` ─────────────────────────────────────────────────────


def test_silenced_says_whether_quiet_hours_cover_the_instant(client, board, monkeypatch):
    board_id, _ = board
    window = {"enabled": True, "mode": "indicator", "start_time": "22:00-08:00", "end_time": "07:00-08:00"}
    monkeypatch.setattr(Config, "silence_config_for", staticmethod(lambda board_id=None: window))

    assert _ok(client, board_id, _at(23, 30))["silenced"] is True
    assert _ok(client, board_id, _at(6, 30))["silenced"] is True
    assert _ok(client, board_id, _at(12, 0))["silenced"] is False


# ── bounds and fallbacks ────────────────────────────────────────────────────


@pytest.mark.parametrize("at", ["yesterday", "400-days-ahead"])
def test_a_malformed_or_far_instant_is_rejected(client, board, at):
    board_id, _ = board
    if at == "400-days-ahead":
        at = (datetime.now(UTC) + timedelta(days=400)).isoformat()

    assert _get(client, board_id, at).status_code == 422


def test_an_unknown_board_still_reads(client, board):
    _, _ = board

    assert _get(client, "no-such-board", _at(8, 0)).status_code == 200


def test_a_quiet_window_that_crosses_midnight_utc_still_covers_both_sides(client, board, monkeypatch):
    board_id, _ = board
    # 3-5 PM in Los Angeles is 23:00-01:00 UTC: the window wraps in UTC.
    window = {"enabled": True, "mode": "indicator", "start_time": "15:00-08:00", "end_time": "17:00-08:00"}
    monkeypatch.setattr(Config, "silence_config_for", staticmethod(lambda board_id=None: window))

    assert _ok(client, board_id, _at(15, 30))["silenced"] is True
    assert _ok(client, board_id, _at(16, 30))["silenced"] is True
    assert _ok(client, board_id, _at(18, 0))["silenced"] is False


@pytest.mark.parametrize(
    ("start", "end", "last", "after"),
    [
        # 22:00-07:00 in Los Angeles: the window crosses local midnight.
        ("22:00-08:00", "07:00-08:00", (7, 0), (7, 1)),
        # 01:00-03:00 in Los Angeles is 09:00-11:00 UTC: a same-day window.
        ("01:00-08:00", "03:00-08:00", (3, 0), (3, 1)),
    ],
    ids=["crossing-midnight", "same-day"],
)
def test_the_end_minute_of_quiet_hours_is_still_quiet(client, board, monkeypatch, start, end, last, after):
    """Inclusive at the end, as the engine's ``is_time_in_window`` is."""
    board_id, _ = board
    window = {"enabled": True, "mode": "indicator", "start_time": start, "end_time": end}
    monkeypatch.setattr(Config, "silence_config_for", staticmethod(lambda board_id=None: window))

    assert _ok(client, board_id, _at(*last))["silenced"] is True
    assert _ok(client, board_id, _at(*after))["silenced"] is False
