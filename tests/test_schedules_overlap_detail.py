"""BB-C-1 / BB-C-2: overlaps say when they happen and which entry the hub shows.

The web entry sheet explains a conflict before save. It needs the hub's own
answer, not a client re-implementation: which days (in week order), which
minutes, and which of the two entries ``get_active_schedule_entry`` picks
during the overlap. ``POST /schedules/validate`` can also evaluate an unsaved
candidate entry (a new one, or an edit replacing a saved one) without
persisting it.
"""

from __future__ import annotations

import tempfile
from datetime import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.schedules.models import ScheduleCreate
from src.schedules.service import CANDIDATE_ID, ScheduleService
from src.schedules.storage import ScheduleStorage

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]


@pytest.fixture
def service():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as handle:
        path = handle.name
    yield ScheduleService(storage=ScheduleStorage(storage_file=path))
    Path(path).unlink(missing_ok=True)


def _add(service: ScheduleService, page: str, start: str, end: str | None, days: str = "weekdays"):
    return service.create_schedule(ScheduleCreate(page_id=page, start_time=start, end_time=end, day_pattern=days))


def _hub_winner(service: ScheduleService, day: str, at: str) -> str | None:
    hour, minute = (int(part) for part in at.split(":"))
    entry = service.get_active_schedule_entry(time(hour, minute), day)
    return entry.id if entry else None


def test_overlap_names_week_ordered_days_window_and_the_later_start_as_winner(service):
    clock = _add(service, "clock", "09:00", "12:00")
    blank = _add(service, "blank", "10:00", "11:00")

    [overlap] = service.validate_schedules().overlaps

    assert overlap.days == WEEKDAYS
    assert (overlap.start_time, overlap.end_time) == ("10:00", "11:00")
    assert overlap.winner_id == blank.id
    assert _hub_winner(service, "monday", "10:00") == blank.id
    assert {overlap.schedule1_id, overlap.schedule2_id} == {clock.id, blank.id}
    # The English fallback text lists days in week order, not alphabetically.
    assert "monday, tuesday, wednesday, thursday, friday" in overlap.conflict_description


def test_winner_does_not_depend_on_creation_order_when_starts_differ(service):
    blank = _add(service, "blank", "10:00", "11:00")
    _add(service, "clock", "09:00", "12:00")

    [overlap] = service.validate_schedules().overlaps

    assert overlap.winner_id == blank.id == _hub_winner(service, "friday", "10:30")


def test_same_start_tie_goes_to_the_newer_entry_like_the_hub(service):
    _add(service, "older", "09:00", "12:00")
    newer = _add(service, "newer", "09:00", "10:00")

    [overlap] = service.validate_schedules().overlaps

    assert overlap.winner_id == newer.id == _hub_winner(service, "monday", "09:00")


def test_overnight_window_started_yesterday_loses_to_one_starting_at_midnight(service):
    early = _add(service, "midnight", "00:00", "03:00", days="all")
    _add(service, "late", "22:00", "02:00", days="all")

    [overlap] = service.validate_schedules().overlaps

    assert (overlap.start_time, overlap.end_time) == ("00:00", "02:00")
    assert overlap.days == ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    assert overlap.winner_id == early.id == _hub_winner(service, "tuesday", "01:00")


def test_a_pair_meeting_both_sides_of_midnight_reports_each_window_and_its_winner(service):
    night = _add(service, "night", "22:00", "02:00", days="all")
    day = _add(service, "day", "00:00", "23:00", days="all")

    overlaps = service.validate_schedules().overlaps

    by_window = {(o.start_time, o.end_time): o.winner_id for o in overlaps}
    assert by_window == {("22:00", "23:00"): night.id, ("00:00", "02:00"): day.id}
    assert by_window[("22:00", "23:00")] == _hub_winner(service, "tuesday", "22:30")
    assert by_window[("00:00", "02:00")] == _hub_winner(service, "tuesday", "01:00")
    assert all(len(o.days) == 7 for o in overlaps)


def test_open_ended_overlap_ends_at_midnight(service):
    _add(service, "evening", "17:00", None, days="all")
    _add(service, "late", "21:00", "23:00", days="all")
    [first] = service.validate_schedules().overlaps
    assert (first.start_time, first.end_time) == ("21:00", "23:00")

    other = _add(service, "night", "22:30", None, days="weekends")
    overlaps = [o for o in service.validate_schedules().overlaps if other.id in (o.schedule1_id, o.schedule2_id)]
    assert {(o.start_time, o.end_time) for o in overlaps} == {("22:30", "00:00"), ("22:30", "23:00")}


def test_candidate_is_evaluated_without_being_saved(service):
    clock = _add(service, "clock", "09:00", "12:00")

    result = service.validate_schedules(
        candidate=ScheduleCreate(page_id="blank", start_time="10:00", end_time="11:00", day_pattern="weekdays")
    )

    [overlap] = result.overlaps
    assert {overlap.schedule1_id, overlap.schedule2_id} == {clock.id, CANDIDATE_ID}
    assert overlap.winner_id == CANDIDATE_ID
    assert [entry.id for entry in service.list_schedules()] == [clock.id]


def test_candidate_replaces_the_entry_being_edited(service):
    _add(service, "clock", "09:00", "12:00")
    blank = _add(service, "blank", "10:00", "11:00")
    assert service.validate_schedules().overlaps

    moved = service.validate_schedules(
        candidate=ScheduleCreate(page_id="blank", start_time="12:00", end_time="13:00", day_pattern="weekdays"),
        candidate_id=blank.id,
    )

    assert moved.overlaps == []
    assert service.get_schedule(blank.id).start_time == "10:00"


def test_editing_keeps_the_entry_age_for_the_tie_break(service):
    edited = _add(service, "older", "09:00", "10:00")
    newer = _add(service, "newer", "09:00", "12:00")

    [overlap] = service.validate_schedules(
        candidate=ScheduleCreate(page_id="older", start_time="09:00", end_time="11:00", day_pattern="weekdays"),
        candidate_id=edited.id,
    ).overlaps

    assert overlap.winner_id == newer.id


# ── HTTP ────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


def test_validate_route_evaluates_a_candidate(client):
    page = client.post(
        "/pages",
        json={"name": "P", "type": "template", "device_type": "flagship", "template": ["A", "", "", "", "", ""]},
    ).json()["id"]
    saved = client.post(
        "/schedules", json={"page_id": page, "start_time": "09:00", "end_time": "12:00", "day_pattern": "weekdays"}
    ).json()

    response = client.post(
        "/schedules/validate",
        json={
            "candidate": {"page_id": page, "start_time": "10:00", "end_time": "11:00", "day_pattern": "weekdays"},
        },
    )

    assert response.status_code == 200, response.text
    [overlap] = response.json()["overlaps"]
    assert {overlap["schedule1_id"], overlap["schedule2_id"]} == {saved["id"], CANDIDATE_ID}
    assert overlap["winner_id"] == CANDIDATE_ID
    assert overlap["days"] == WEEKDAYS
    assert (overlap["start_time"], overlap["end_time"]) == ("10:00", "11:00")
    assert len(client.get("/schedules").json()["schedules"]) == 1


def test_validate_route_rejects_an_incomplete_candidate(client):
    response = client.post(
        "/schedules/validate",
        json={"candidate": {"page_id": "p", "start_time": "10:00", "end_time": "11:00", "day_pattern": "custom"}},
    )

    assert response.status_code == 400
