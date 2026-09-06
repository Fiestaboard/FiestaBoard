"""Display-engine equivalence corpus (issue #1850, Track B1).

Each test runs the CURRENT ``DisplayService`` engine through a fake-clock
scenario and asserts the resulting send sequence — the ``(simulated time,
board, frame)`` triples handed to the board clients — is EXACTLY the
committed golden in ``tests/golden/engine/<scenario>.json``. The goldens were
recorded from today's engine; the redesigned engine
(#1751/#1752/#1754/#1755) must reproduce them byte for byte.

Golden format::

    {"scenario": "<name>", "sends": [{"t": ISO, "board": id, "rows": [...]}, ...]}

Only the send sequence is pinned. Internal wake cadence (the run loop can
evaluate the drive path up to 3x per simulated second) is deliberately NOT
encoded — see tests/engine_harness.py.

Re-recording: ``RECORD_ENGINE_GOLDEN=1 pytest tests/test_engine_equivalence.py``
rewrites every golden from the current engine and passes. (An env var rather
than a pytest option because tests/conftest.py is owned by another branch.)
Only re-record when a behavior change is INTENDED and reviewed.

Every scenario here runs through the real ``run()`` loop; none needed the
tick-at-instant fallback.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import schedule

from src.collections.models import Collection, TimeModeConfig
from src.collections.service import CollectionService
from src.plugins.base import TriggerResult
from src.settings.service import TemporaryOverride
from src.triggers.service import reset_trigger_service
from tests.engine_harness import (
    FakeClock,
    SilenceConfigManager,
    StubPluginRegistry,
    StubTriggerPlugin,
    make_board,
    make_page_service,
    make_settings_service,
    run_engine_scenario,
    silence_feature,
)

GOLDEN_DIR = Path(__file__).parent / "golden" / "engine"
RECORD = os.environ.get("RECORD_ENGINE_GOLDEN") == "1"

T0 = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
COLLECTION_ID = "collection:11111111-2222-3333-4444-555555555555"


def check_golden(name: str, sends: list[dict]) -> None:
    """Compare a run's sends against the committed golden (or re-record it)."""
    path = GOLDEN_DIR / f"{name}.json"
    payload = {"scenario": name, "sends": sends}
    if RECORD:
        path.write_text(json.dumps(payload, indent=2) + "\n")
        return
    assert path.exists(), f"Missing golden {path}; record with RECORD_ENGINE_GOLDEN=1"
    golden = json.loads(path.read_text())
    got = [(s["t"], s["board"]) for s in sends]
    expected = [(s["t"], s["board"]) for s in golden["sends"]]
    assert payload == golden, (
        f"Send sequence diverged from golden {path.name}: "
        f"{len(sends)} sends {got} vs golden {len(golden['sends'])} sends {expected}"
    )


@pytest.fixture(autouse=True)
def _clear_schedule():
    """``run()`` registers jobs on the library's global scheduler."""
    schedule.clear()
    yield
    schedule.clear()


@pytest.fixture(autouse=True)
def _reset_triggers():
    """The trigger-service singleton must never leak state across scenarios."""
    reset_trigger_service()
    yield
    reset_trigger_service()


def counting_page(prefix: str):
    """Page content that differs on every render — a cadence readout."""
    counter = {"n": 0}

    def _content():
        counter["n"] += 1
        return f"{prefix} {counter['n']}"

    return _content


def test_static_page_dedupe(monkeypatch):
    """Pins: unchanged content is sent exactly once, not once per poll.

    One board, one static page, 60 simulated seconds at 15s polling — the
    dedupe cache must swallow every re-render after the initial send.
    """
    result = run_engine_scenario(
        monkeypatch,
        start=T0,
        run_until=T0 + timedelta(seconds=60),
        boards=[make_board("board-1")],
        settings=make_settings_service(
            boards=[make_board("board-1")], polling_interval=15, active_page_ids={"board-1": "page-static"}
        ),
        pages=make_page_service({"page-static": "HELLO WORLD"}),
    )
    check_golden("static_page_dedupe", result.sends)


def test_changing_page_cadence(monkeypatch):
    """Pins: changing content is re-driven once per polling interval.

    An always-changing page over 60s at 15s polling sends at offsets
    0, 15, 30, 45, 60 — never at the loop's internal 1 Hz wake-up rate.
    """
    result = run_engine_scenario(
        monkeypatch,
        start=T0,
        run_until=T0 + timedelta(seconds=60),
        boards=[make_board("board-1")],
        settings=make_settings_service(
            boards=[make_board("board-1")], polling_interval=15, active_page_ids={"board-1": "page-x"}
        ),
        pages=make_page_service({"page-x": counting_page("FRAME")}),
    )
    check_golden("changing_page_cadence", result.sends)


def test_schedule_boundary(monkeypatch):
    """Pins: a schedule boundary swaps the page within one polling interval.

    Schedule mode: page A before 09:00, page B from 09:00. Starting 10s
    before the boundary, the board shows MORNING then DAY — and nothing else.
    """
    from datetime import time as clock_time

    schedules = MagicMock()
    schedules.get_active_page_id.side_effect = lambda t, day, board_id=None: (
        "page-day" if t >= clock_time(9, 0) else "page-morning"
    )
    result = run_engine_scenario(
        monkeypatch,
        start=T0 - timedelta(seconds=10),
        run_until=T0 + timedelta(seconds=30),
        boards=[make_board("board-1")],
        settings=make_settings_service(boards=[make_board("board-1")], polling_interval=15, schedule_enabled=True),
        pages=make_page_service({"page-morning": "MORNING", "page-day": "DAY"}),
        schedules=schedules,
    )
    check_golden("schedule_boundary", result.sends)


def test_collection_rotation_time_mode(monkeypatch):
    """Pins: a time-mode collection rotates on its own interval boundaries.

    Real ``CollectionService`` math over a two-page 30s collection; polling
    is 5 minutes, so every send after the first is driven by the run loop's
    collection gate, on the slice boundaries — not by the poll job.
    """
    collection = Collection(
        id=COLLECTION_ID,
        name="Rotation",
        page_ids=["page-a", "page-b"],
        selection_mode="time",
        time=TimeModeConfig(interval_seconds=30),
    )
    storage = MagicMock()
    storage.get.side_effect = lambda cid: collection if cid == COLLECTION_ID else None
    result = run_engine_scenario(
        monkeypatch,
        start=T0 + timedelta(seconds=20),
        run_until=T0 + timedelta(minutes=2),
        boards=[make_board("board-1")],
        settings=make_settings_service(
            boards=[make_board("board-1")], polling_interval=300, active_page_ids={"board-1": COLLECTION_ID}
        ),
        pages=make_page_service({"page-a": "ALPHA", "page-b": "BETA"}),
        collections=CollectionService(storage=storage),
    )
    check_golden("collection_rotation_time_mode", result.sends)


def test_silence_window_indicator(monkeypatch):
    """Pins: a silence window opening mid-run swaps in the SNOOZING indicator
    within ~1s (the run loop's silence probe), holds it for the whole window,
    and restores page content when the window closes.

    Window 09:01-09:02 UTC; polling is 60s so only the 1 Hz probe can catch
    the boundaries this tightly. Real ``Config`` silence resolution and real
    ``TimeService`` window math stay in the loop.
    """
    result = run_engine_scenario(
        monkeypatch,
        start=T0 + timedelta(seconds=30),
        run_until=T0 + timedelta(minutes=3),
        boards=[make_board("board-1")],
        settings=make_settings_service(
            boards=[make_board("board-1")], polling_interval=60, active_page_ids={"board-1": "page-morning"}
        ),
        pages=make_page_service({"page-morning": "GOOD MORNING"}),
        config_manager=SilenceConfigManager(silence_feature(start_time="09:01+00:00", end_time="09:02+00:00")),
    )
    check_golden("silence_window_indicator", result.sends)


def test_two_boards_independent_pages(monkeypatch):
    """Pins: how the CURRENT engine drives a secondary board under run().

    Two runtimes with per-board active pages, both always-changing so every
    drive pass is visible. The golden IS the discovery: it records the
    secondary's actual cadence and its ordering relative to the primary
    within each pass (primary first, then secondaries).
    """
    boards = [make_board("board-1", name="Primary"), make_board("board-2", name="Secondary")]
    result = run_engine_scenario(
        monkeypatch,
        start=T0,
        run_until=T0 + timedelta(seconds=60),
        boards=boards,
        settings=make_settings_service(
            boards=boards,
            polling_interval=15,
            active_page_ids={"board-1": "page-p", "board-2": "page-s"},
        ),
        pages=make_page_service({"page-p": counting_page("PRIMARY"), "page-s": counting_page("SECOND")}),
    )
    check_golden("two_boards_independent_pages", result.sends)


def test_trigger_override_lifecycle(monkeypatch):
    """Pins: a plugin trigger overrides the page for its duration, then the
    page returns — through the REAL ``TriggerService``.

    The stub plugin's condition is true only for 09:00:20-09:00:25 (a
    momentary event); the engine's next drive pass (poll at +20s) activates
    it with duration 30s, so the override is sent at +20 and expires at +50,
    when the normal page is re-sent. ``_check_trigger_override`` is NOT
    stubbed here.
    """

    def build_registry(run_clock: FakeClock) -> StubPluginRegistry:
        plugin = StubTriggerPlugin(
            run_clock,
            fire_from=T0 + timedelta(seconds=20),
            fire_until=T0 + timedelta(seconds=25),
            results=[
                TriggerResult(
                    triggered=True,
                    trigger_id="stub-1",
                    message="DOOR OPEN",
                    priority=5,
                    duration_seconds=30,
                )
            ],
        )
        return StubPluginRegistry([plugin])

    result = run_engine_scenario(
        monkeypatch,
        start=T0,
        run_until=T0 + timedelta(seconds=60),
        boards=[make_board("board-1")],
        settings=make_settings_service(
            boards=[make_board("board-1")], polling_interval=10, active_page_ids={"board-1": "page-home"}
        ),
        pages=make_page_service({"page-home": "HELLO HOME"}),
        trigger_registry_factory=build_registry,
    )
    check_golden("trigger_override_lifecycle", result.sends)


def test_board_send_failure(monkeypatch):
    """Pins: a failed send is retried on the next poll, not cached as sent.

    The client rejects renders for the first 10 simulated seconds. The
    initial attempt at +0 fails; the dedupe cache stays clear, so the +15
    poll retries the SAME content and succeeds; later polls dedupe again.
    """
    fail_until = T0 + timedelta(seconds=10)
    result = run_engine_scenario(
        monkeypatch,
        start=T0,
        run_until=T0 + timedelta(seconds=60),
        boards=[make_board("board-1")],
        settings=make_settings_service(
            boards=[make_board("board-1")], polling_interval=15, active_page_ids={"board-1": "page-static"}
        ),
        pages=make_page_service({"page-static": "HELLO WORLD"}),
        fail_when={"board-1": lambda t: t < fail_until},
    )
    check_golden("board_send_failure", result.sends)

    client = result.clients["board-1"]
    assert client.attempts[0][1] is False, "first attempt should have been the injected failure"
    assert all(ok for _t, ok in client.attempts[1:]), "every later attempt should have succeeded"
    rt = result.service.runtimes["board-1"]
    assert rt.last_send_error is None, "the successful retry must clear the recorded send error"


def test_temporary_override_inline(monkeypatch):
    """Pins: an inline (one-off) temporary override is sent exactly once,
    then the normal active page returns on the next poll.

    ``consume_temporary_override`` yields a real ``TemporaryOverride`` with
    inline template content on the first drive pass only (issue #1787 shape).
    """
    override = TemporaryOverride(template=["ONE OFF"], device_type="flagship")
    result = run_engine_scenario(
        monkeypatch,
        start=T0,
        run_until=T0 + timedelta(seconds=45),
        boards=[make_board("board-1")],
        settings=make_settings_service(
            boards=[make_board("board-1")],
            polling_interval=15,
            active_page_ids={"board-1": "page-home"},
            temporary_overrides=[override],
        ),
        pages=make_page_service({"page-home": "HELLO HOME"}),
    )
    check_golden("temporary_override_inline", result.sends)
