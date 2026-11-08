"""The run loop must honor every board's collection cadence."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from src.collections.models import Collection
from src.collections.service import CollectionService
from src.main import BoardRuntime, DisplayService


@pytest.mark.parametrize("mode,cadence", [("time", 5), ("random", 5), ("variable", 2)])
@pytest.mark.parametrize("scheduled", [False, True])
def test_secondary_collection_drives_loop_with_paused_noncollection_primary(mode, cadence, scheduled):
    ticks = run_clock(mode=mode, scheduled=scheduled)
    assert cadence in ticks
    assert cadence * 2 in ticks


def test_paused_collection_does_not_add_engine_passes():
    assert run_clock(paused=True) == [0, 14, 28]


def test_noncollection_preserves_ordinary_polling():
    assert run_clock(collection=False) == [0, 14, 28]


def test_two_collections_keep_independent_deadlines_and_coalesce_shared_boundaries():
    ticks = run_clock(primary_collection=True)
    assert ticks == [0, 0, 5, 7, 10, 14, 14, 15, 20, 21, 25, 28, 28]


def test_deferred_schedule_uses_manual_collections_cadence():
    ticks = run_clock(scheduled=True, deferred=True)
    assert 5 in ticks
    assert 10 in ticks


@pytest.mark.parametrize(
    "mode,old_cadence,new_cadence,boundaries",
    [
        ("time", 86400, 5, (5, 10, 15, 20)),
        ("random", 86400, 5, (5, 10, 15, 20)),
        ("variable", 600, 2, (3, 5, 17, 19)),
    ],
)
def test_shortened_collection_cadence_replaces_the_previous_deadline(mode, old_cadence, new_cadence, boundaries):
    ticks = run_clock(mode=mode, initial_cadence=old_cadence, changed_cadence=new_cadence)
    for boundary in boundaries:
        assert boundary in ticks, ticks


@pytest.mark.parametrize("deferred", [False, True])
@pytest.mark.parametrize(
    "mode,old_cadence,new_cadence,boundaries",
    [
        ("time", 86400, 5, (5, 10, 15, 20)),
        ("random", 86400, 5, (5, 10, 15, 20)),
        ("variable", 600, 2, (3, 5, 17, 19)),
    ],
)
def test_shortened_scheduled_and_deferred_collection_cadence(mode, old_cadence, new_cadence, boundaries, deferred):
    ticks = run_clock(
        mode=mode,
        scheduled=True,
        deferred=deferred,
        initial_cadence=old_cadence,
        changed_cadence=new_cadence,
    )
    for boundary in boundaries:
        assert boundary in ticks, ticks


def test_shortened_cadence_with_fractional_clock_keeps_the_one_second_loop_resolution():
    ticks = run_clock(initial_cadence=86400, changed_cadence=5, clock_start=0.25)
    assert 5.25 in ticks, ticks
    assert 10.25 in ticks, ticks


def test_changed_collection_cadence_does_not_unpause_the_board():
    assert run_clock(paused=True, initial_cadence=86400, changed_cadence=5) == [0, 14, 28]


def test_lengthened_collection_cadence_stops_the_previous_fast_rotation():
    ticks = run_clock(initial_cadence=5, changed_cadence=86400)
    assert 10 not in ticks
    assert 20 not in ticks


def run_clock(
    *,
    mode="time",
    scheduled=False,
    paused=False,
    collection=True,
    primary_collection=False,
    deferred=False,
    initial_cadence=None,
    changed_cadence=None,
    clock_start=0,
):
    """Run real loop/cadence service with a deterministic clock and fake sends."""
    clock = [clock_start]
    ticks = []
    selected = Collection(
        name="Secondary",
        page_ids=["a", "b", "c"],
        selection_mode=mode,
        time={"interval_seconds": initial_cadence or 5},
        random={"interval_seconds": initial_cadence or 5},
        variable={"default_page_id": "a", "poll_seconds": (initial_cadence or 2) if mode == "variable" else 2},
    )
    storage = Mock()
    primary = Collection(name="Primary", page_ids=["a", "b"], time={"interval_seconds": 7})
    storage.get.side_effect = lambda ref: primary if ref == primary.id else selected
    collections = CollectionService(storage=storage)
    settings = Mock()
    settings.get_polling_interval.return_value = 14
    settings.get_primary_board_id.return_value = "primary"
    settings.is_paused.side_effect = lambda board_id=None: (board_id == "primary" and not primary_collection) or paused
    settings.is_schedule_enabled.side_effect = lambda board_id=None: scheduled and board_id == "secondary"
    settings.get_active_page_id.side_effect = lambda board_id=None: (
        selected.id if board_id == "secondary" and collection else primary.id if primary_collection else "ordinary-page"
    )
    settings.get_schedule_settings.return_value.defer_on_reenable = deferred
    schedules = Mock()
    schedules.get_active_page_id.return_value = "ordinary-page" if deferred else selected.id
    schedules.get_active_schedule_entry.return_value.id = "current-window"
    timer = Mock()
    timer.get_current_time.return_value = datetime(2026, 10, 17, tzinfo=UTC)
    scheduler = Mock()

    with (
        patch("src.main.Config"),
        patch("src.main.get_settings_service", return_value=settings),
        patch("src.main.get_collection_service", return_value=collections),
        patch("src.main.get_schedule_service", return_value=schedules),
        patch("src.time_service.get_time_service", return_value=timer),
        patch("src.main.schedule", scheduler),
        patch("src.main.time.time", side_effect=lambda: clock[0]),
    ):
        service = DisplayService()
        service.runtimes = {bid: BoardRuntime(Mock(), bid) for bid in ("primary", "secondary")}
        service._primary_board_id = "primary"
        if deferred:
            service.runtimes["secondary"].last_schedule_enabled = False

        def send(*, wait, board_ids=None):
            assert wait is False
            ticks.append(clock[0])

        def sleep(seconds):
            nonlocal selected
            assert seconds == 1
            clock[0] += seconds
            if clock[0] == clock_start + 1 and changed_cadence is not None:
                # Storage publishes a replacement model after an accepted edit.
                updated = selected.model_dump()
                field = "poll_seconds" if mode == "variable" else "interval_seconds"
                updated[mode][field] = changed_cadence
                selected = Collection.model_validate(updated)
            if clock[0] == clock_start + 30:
                service.running = False

        with (
            patch.object(service, "check_and_send_active_page", side_effect=send),
            patch.object(service, "_silence_state_changed", return_value=False),
            patch("src.main.time.sleep", side_effect=sleep),
        ):
            service.run()
        scheduler.every.assert_not_called()
    return ticks
