# ruff: noqa: F811 - pytest fixtures are imported from their home modules
"""H9b: what happened the last 20 times a page was sent (Figma 04d 1.7 "Sent").

Recorded: a frame that landed (``sent``), a write that failed (``failed``,
with the board's H12 failure code), and Show now refused by pause or quiet
hours (``paused`` / ``silenced`` / ``held``). Not recorded: unchanged skips,
throttled and superseded writes, UI-only targets, previews. Kept in memory and
written to ``<data>/page_sends.json`` at most every 180 s (and on shutdown),
like H12's board health: never once per frame.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from src.board_guards import SilenceVerdict
from src.pages.history import iso
from tests.test_render_short_circuit import PAGE_ID, Rig
from tests.test_v1_contract import _seed_page, board_client, boards, client  # noqa: F401 - fixtures


class Clock:
    def __init__(self, now: float = 1_800_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeTimer:
    """A timer that only fires when the test says so."""

    armed: list[FakeTimer] = []

    def __init__(self, delay, fn):
        self.delay, self.fn, self.cancelled, self.daemon = delay, fn, False, False
        FakeTimer.armed.append(self)

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.fn()


@pytest.fixture
def page(client, boards):
    return _seed_page(client, "Commute")


@pytest.fixture
def board(board_client):
    """The reachable board client, also behind the pages router's own service seam."""
    service = Mock()
    service.get_board_client.return_value = board_client
    service.vb_client = board_client
    with patch("src.pages.routes.get_service", return_value=service):
        yield board_client


def _sends(client, page_id) -> list[dict]:
    response = client.get(f"/pages/{page_id}/sends")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_id"] == page_id
    assert body["total"] == len(body["sends"])
    return body["sends"]


def _iso_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _health_stamped_by_render(board, *, code: str, result: tuple[bool, bool]):
    """A fake H12 that records *code* while the board renders, as the real one does.

    Stamping it in the test before the send would race the send's start time:
    across a second boundary the error is honestly older than the send.
    """
    from src.outputs.health import HealthSummary

    stamped: list[str] = []

    def render(*args, **kwargs):
        stamped.append(_iso_now())
        return result

    board.render.side_effect = render
    return lambda *a: HealthSummary(last_error=code, last_error_at=stamped[-1] if stamped else None)


def _show_now(client, page_id, board_id):
    return client.post(f"/pages/{page_id}/send", json={"target": "board", "board_id": board_id})


# ── Show now ────────────────────────────────────────────────────────────────


def test_show_now_records_a_sent_entry(client, boards, page, board):
    primary, _ = boards
    assert _show_now(client, page, primary).status_code == 200
    (entry,) = _sends(client, page)
    assert entry["outcome"] == "sent"
    assert entry["via"] == "show_now"
    assert entry["board_id"] == primary
    assert entry["board_name"] == "Kitchen"
    assert entry["error"] is None
    assert entry["at"].endswith("+00:00")


def test_a_page_never_sent_has_no_history(client, page):
    assert _sends(client, page) == []


def test_an_unknown_page_is_404(client):
    assert client.get("/pages/nope/sends").status_code == 404


def test_show_now_on_a_paused_board_records_paused(client, boards, page, board):
    primary, _ = boards
    with patch("src.pages.routes._board_is_paused", return_value=True):
        assert _show_now(client, page, primary).status_code == 200
    assert [e["outcome"] for e in _sends(client, page)] == ["paused"]


def test_show_now_in_quiet_hours_records_silenced(client, boards, page, board):
    primary, _ = boards
    with patch("src.pages.routes.silence_verdict", return_value=SilenceVerdict(silenced=True)):
        assert _show_now(client, page, primary).status_code == 200
    assert [e["outcome"] for e in _sends(client, page)] == ["silenced"]


def test_show_now_held_for_the_end_of_quiet_hours_records_held(client, boards, page, board):
    primary, _ = boards
    with patch("src.pages.routes.silence_verdict", return_value=SilenceVerdict(silenced=True, held=True)):
        assert _show_now(client, page, primary).status_code == 200
    assert [e["outcome"] for e in _sends(client, page)] == ["held"]


def test_a_failed_show_now_records_the_boards_failure_code(client, boards, page, board):
    primary, _ = boards
    health = _health_stamped_by_render(board, code="auth", result=(False, False))
    with patch("src.pages.sends.board_health", side_effect=health):
        assert _show_now(client, page, primary).status_code == 500
    (entry,) = _sends(client, page)
    assert (entry["outcome"], entry["error"]) == ("failed", "auth")


@pytest.mark.parametrize(
    ("started", "error_at", "copied"),
    [
        (1_800_000_000.9, "2027-01-15T08:00:00+00:00", True),  # same whole second as the start: this send
        (1_800_000_000.0, "2027-01-15T08:00:00+00:00", True),  # exactly the start
        (1_800_000_000.9, "2027-01-15T08:00:01+00:00", True),  # later
        (1_800_000_000.0, "2027-01-15T07:59:59+00:00", False),  # a second before: an older failure
    ],
)
def test_the_freshness_check_compares_whole_seconds(started, error_at, copied):
    # last_error_at has whole seconds (floored), so the start is floored too:
    # an error H12 stamps during this send can never read as older than it.
    from src.outputs.health import HealthSummary
    from src.pages.sends import board_error_code

    health = HealthSummary(last_error="auth", last_error_at=error_at)
    with patch("src.pages.sends.board_health", return_value=health):
        assert board_error_code(None, "b", started) == ("auth" if copied else None)


def test_a_failed_show_now_does_not_copy_a_stale_failure_code(client, boards, page, board):
    # Review #2464 must-fix 2 (probe P7): an "auth" from January, with a
    # contact since, must not name a new failure that has nothing to do with the token.
    from src.outputs.health import HealthSummary

    primary, _ = boards
    board.render.return_value = (False, False)
    stale = HealthSummary(
        last_error="auth",
        last_error_at="2026-01-12T08:00:00+00:00",
        last_connected_at=_iso_now(),
        reachable=True,
    )
    with patch("src.pages.sends.board_health", return_value=stale):
        assert _show_now(client, page, primary).status_code == 500
    (entry,) = _sends(client, page)
    assert (entry["outcome"], entry["error"]) == ("failed", None)


def test_a_sent_entry_never_carries_a_failure_code(client, boards, page, board):
    # Mutant B11: even with a fresh last_error on the board, a landed send has no error.
    primary, _ = boards
    health = _health_stamped_by_render(board, code="timeout", result=(True, True))
    with patch("src.pages.sends.board_health", side_effect=health):
        assert _show_now(client, page, primary).status_code == 200
    (entry,) = _sends(client, page)
    assert (entry["outcome"], entry["error"]) == ("sent", None)


def test_a_show_now_whose_render_raises_records_failed(client, boards, page, board):
    primary, _ = boards
    board.render.side_effect = RuntimeError("driver blew up")
    with pytest.raises(RuntimeError):
        _show_now(client, page, primary)
    assert [e["outcome"] for e in _sends(client, page)] == ["failed"]


def test_repeated_show_now_refusals_merge_into_one_entry(client, boards, page, board):
    primary, _ = boards
    with patch("src.pages.routes._board_is_paused", return_value=True):
        for _ in range(3):
            assert _show_now(client, page, primary).status_code == 200
    (entry,) = _sends(client, page)
    assert (entry["outcome"], entry["count"]) == ("paused", 3)
    assert entry["last_at"] is not None


def test_an_unchanged_show_now_records_nothing(client, boards, page, board):
    primary, _ = boards
    board.render.return_value = (True, False)  # the board already shows it
    assert _show_now(client, page, primary).status_code == 200
    assert _sends(client, page) == []


def test_a_ui_only_target_records_nothing(client, boards, page, board):
    primary, _ = boards
    response = client.post(f"/pages/{page}/send", json={"target": "ui", "board_id": primary})
    assert response.status_code == 200
    assert _sends(client, page) == []


def test_at_most_twenty_entries_newest_first(client, boards, page, board):
    from src.pages.sends import send_history

    for n in range(25):  # a different board each time, so nothing merges
        send_history().record(page, outcome="sent", via="auto", board_id=f"b{n}", board_name=f"B{n}")
    sends = _sends(client, page)
    assert len(sends) == 20
    assert sends[0]["board_name"] == "B24"
    assert sends[-1]["board_name"] == "B5"


def test_deleting_the_page_forgets_its_history(client, boards, page, board, _isolated_data_dir):
    from src.pages.sends import send_history

    primary, _ = boards
    _seed_page(client, "Keep one")
    _show_now(client, page, primary)
    assert client.delete(f"/pages/{page}").status_code == 200
    assert send_history().sends(page) == []
    stored = json.loads((_isolated_data_dir / "page_sends.json").read_text())
    assert page not in stored["pages"]


# ── the engine ──────────────────────────────────────────────────────────────


@pytest.fixture
def rig(monkeypatch):
    rig = Rig(monkeypatch, template=["HELLO"], data={})
    yield rig
    rig.stop()


def test_the_engine_records_a_page_that_landed(rig):
    from src.pages.sends import send_history

    rig.tick()
    (entry,) = send_history().sends(PAGE_ID)
    assert (entry["outcome"], entry["via"], entry["board_id"], entry["board_name"]) == (
        "sent",
        "auto",
        "board-1",
        "Board",
    )


def test_the_engine_records_nothing_for_unchanged_content(rig):
    from src.pages.sends import send_history

    rig.tick(3)
    assert len(send_history().sends(PAGE_ID)) == 1


def test_the_engine_records_a_failed_write(rig):
    from src.pages.sends import send_history

    rig.client.fail = True
    rig.tick()
    assert [e["outcome"] for e in send_history().sends(PAGE_ID)] == ["failed"]


def test_a_board_that_keeps_failing_does_not_wipe_the_history(rig):
    # Review #2464 must-fix 1 (probe P8): the engine retries a failed send on
    # every pass; 25 of them must not push the earlier sends out of the window.
    from src.pages.sends import send_history

    send_history().record(PAGE_ID, outcome="sent", via="show_now", board_id="board-1", board_name="Board")
    for _ in range(3):
        send_history().record(PAGE_ID, outcome="sent", via="auto", board_id="board-1", board_name="Board")
    rig.client.fail = True
    rig.tick(25)
    sends = send_history().sends(PAGE_ID)
    assert [(e["outcome"], e["via"], e["count"]) for e in sends] == [
        ("failed", "auto", 25),
        ("sent", "auto", 3),
        ("sent", "show_now", 1),
    ]


def test_the_engine_records_a_send_that_raised(rig):
    # Mutant B1: the engine's exception branch records failed too.
    from src.pages.sends import send_history

    def boom(*args, **kwargs):
        raise RuntimeError("driver blew up")

    rig.client.render = boom
    rig.tick()
    assert [e["outcome"] for e in send_history().sends(PAGE_ID)] == ["failed"]


def test_the_engine_does_not_copy_a_stale_failure_code(rig):
    from src.outputs.health import HealthSummary
    from src.pages.sends import send_history

    rig.client.fail = True
    stale = HealthSummary(last_error="auth", last_error_at="2026-01-12T08:00:00+00:00", reachable=True)
    with patch("src.pages.sends.board_health", return_value=stale):
        rig.tick()
    assert [(e["outcome"], e["error"]) for e in send_history().sends(PAGE_ID)] == [("failed", None)]


def test_the_engine_copies_a_failure_code_from_this_send(rig):
    from src.outputs.health import HealthSummary
    from src.pages.sends import send_history

    rig.client.fail = True
    with patch(
        "src.pages.sends.board_health",
        side_effect=lambda *a: HealthSummary(last_error="timeout", last_error_at=_iso_now()),
    ):
        rig.tick()
    assert [(e["outcome"], e["error"]) for e in send_history().sends(PAGE_ID)] == [("failed", "timeout")]


def test_the_engine_records_nothing_for_a_throttled_write(rig):
    from src.pages.sends import send_history

    rig.client.last_send_throttled = True
    rig.tick()
    assert send_history().sends(PAGE_ID) == []


# ── persistence ─────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path):
    from src.pages.sends import SendHistory

    FakeTimer.armed = []
    clock = Clock()
    history = SendHistory(tmp_path / "page_sends.json", clock=clock, timer=FakeTimer)
    yield history, clock, tmp_path / "page_sends.json"
    history.close()


def _on_disk(path) -> dict:
    return json.loads(path.read_text())["pages"]


def test_the_first_entry_is_written_at_once(store):
    history, _, path = store
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    assert len(_on_disk(path)["p"]) == 1


def test_entries_within_the_interval_wait_for_the_timer(store):
    history, clock, path = store
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    clock.now += 60
    history.record("p", outcome="sent", via="auto", board_id="c", board_name="C")
    assert len(_on_disk(path)["p"]) == 1
    (timer,) = [t for t in FakeTimer.armed if not t.cancelled]
    assert timer.delay == pytest.approx(120)
    timer.fire()
    assert len(_on_disk(path)["p"]) == 2


def test_flush_writes_what_is_pending(store):
    history, clock, path = store
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    clock.now += 1
    history.record("p", outcome="failed", via="auto", board_id="b", board_name="B", error="timeout")
    history.flush()
    assert [e["outcome"] for e in _on_disk(path)["p"]] == ["sent", "failed"]


def test_a_reload_reads_the_file_and_drops_bad_entries(tmp_path):
    from src.pages.sends import SendHistory

    path = tmp_path / "page_sends.json"
    good = {"at": 1_800_000_000.0, "outcome": "sent", "via": "auto", "board_id": "b", "board_name": "B", "error": None}
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pages": {
                    "p": [
                        good,
                        {**good, "outcome": "exploded"},
                        {**good, "error": "cloud_down"},
                        {**good, "at": "yesterday"},
                        "junk",
                    ],
                    "q": "junk",
                },
            }
        )
    )
    history = SendHistory(path)
    sends = history.sends("p")
    assert [(e["outcome"], e["error"]) for e in sends] == [("sent", None), ("sent", None)]
    assert history.sends("q") == []
    history.close()


def test_repeats_merge_and_cost_no_write_until_flush(store, monkeypatch):
    from src.pages import sends

    history, clock, path = store
    writes = []
    real = sends.write_json_atomic
    monkeypatch.setattr(sends, "write_json_atomic", lambda *a, **k: (writes.append(1), real(*a, **k)))
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    clock.now += 200
    history.record("p", outcome="failed", via="auto", board_id="b", board_name="B", error="unreachable")
    assert len(writes) == 2
    for _ in range(25):
        clock.now += 200  # a whole interval each time: the old code wrote on every one
        history.record("p", outcome="failed", via="auto", board_id="b", board_name="B", error="unreachable")
    assert len(writes) == 2
    assert not [t for t in FakeTimer.armed if not t.cancelled]
    history.flush()  # shutdown
    assert len(writes) == 3
    (_sent, failed) = _on_disk(path)["p"]
    assert (failed["outcome"], failed["count"]) == ("failed", 26)
    assert failed["last_at"] == clock.now
    assert failed["at"] < failed["last_at"]


def test_a_different_cause_or_board_starts_a_new_entry(store):
    history, _, _ = store
    history.record("p", outcome="failed", via="auto", board_id="b", board_name="B", error="unreachable")
    history.record("p", outcome="failed", via="auto", board_id="b", board_name="B", error="timeout")
    history.record("p", outcome="failed", via="auto", board_id="c", board_name="C", error="timeout")
    history.record("p", outcome="failed", via="show_now", board_id="c", board_name="C", error="timeout")
    assert [e["count"] for e in history.sends("p")] == [1, 1, 1, 1]


def test_consecutive_landings_on_one_board_merge(store):
    # Coordinator ruling on #2464: a live page's landings are one entry with a count.
    history, clock, _ = store
    start = clock.now
    for _ in range(3):
        clock.now += 60
        history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    (entry,) = history.sends("p")
    assert entry["count"] == 3
    assert entry["at"] == iso(start + 60)
    assert entry["last_at"] == iso(start + 180)


def test_a_landing_on_another_board_or_via_starts_a_new_entry(store):
    history, _, _ = store
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    history.record("p", outcome="sent", via="auto", board_id="c", board_name="C")
    history.record("p", outcome="sent", via="show_now", board_id="c", board_name="C")
    assert [e["count"] for e in history.sends("p")] == [1, 1, 1]


def test_one_failure_then_twenty_landings_keeps_the_failure(store):
    # The re-review probe: twenty landings used to push the failure out of the
    # window, so a live page kept about twenty minutes of history.
    history, clock, _ = store
    history.record("p", outcome="failed", via="auto", board_id="b", board_name="B", error="timeout")
    for _ in range(20):
        clock.now += 60
        history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    assert [(e["outcome"], e["count"]) for e in history.sends("p")] == [("sent", 20), ("failed", 1)]


def test_merged_landings_are_written_at_the_normal_cadence(store):
    # A live page's merged landings must reach disk within an interval (a
    # crash loses at most that), unlike a retrying failure, which waits.
    history, clock, path = store
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    clock.now += 60
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    (timer,) = [t for t in FakeTimer.armed if not t.cancelled]
    timer.fire()
    (entry,) = _on_disk(path)["p"]
    assert entry["count"] == 2


def test_show_now_twice_is_one_entry_with_a_count(client, boards, page, board):
    primary, _ = boards
    for _ in range(2):
        assert _show_now(client, page, primary).status_code == 200
    (entry,) = _sends(client, page)
    assert (entry["outcome"], entry["count"]) == ("sent", 2)


def test_a_merged_entry_survives_a_reload(store):
    from src.pages.sends import SendHistory

    history, clock, path = store
    for _ in range(4):
        clock.now += 10
        history.record("p", outcome="held", via="show_now", board_id="b", board_name="B")
    history.flush()
    (entry,) = SendHistory(path).sends("p")
    assert entry["count"] == 4
    assert entry["last_at"] is not None


@pytest.mark.parametrize("at", ["NaN", "Infinity", "-Infinity", "-5", "1e20"])
def test_a_reload_drops_entries_with_an_impossible_instant(tmp_path, at):
    # Mutant B2: json.loads reads NaN and Infinity, so the finite check matters.
    from src.pages.sends import SendHistory

    path = tmp_path / "page_sends.json"
    good = '{"at": 1800000000.0, "outcome": "sent", "via": "auto", "board_id": "b", "board_name": "B", "error": null}'
    bad = good.replace("1800000000.0", at)
    path.write_text(f'{{"schema_version": 1, "pages": {{"p": [{good}, {bad}]}}}}')
    history = SendHistory(path)
    assert len(history.sends("p")) == 1
    history.close()


def test_a_reload_reads_a_bad_count_or_last_at_as_a_single_entry(tmp_path):
    from src.pages.sends import SendHistory

    path = tmp_path / "page_sends.json"
    base = {"at": 1_800_000_000.0, "outcome": "failed", "via": "auto", "board_id": "b", "board_name": "B"}
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pages": {
                    "p": [
                        {**base, "count": 0, "last_at": 1_700_000_000.0},
                        {**base, "count": True, "last_at": "later"},
                    ]
                },
            }
        )
    )
    history = SendHistory(path)
    assert [(e["count"], e["last_at"]) for e in history.sends("p")] == [(1, None), (1, None)]
    history.close()


def test_a_failed_write_is_retried_by_the_next_flush(store, monkeypatch):
    # Mutant B6: a failed write stays pending.
    from src.pages import sends

    history, _, path = store
    real = sends.write_json_atomic

    def full_disk(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(sends, "write_json_atomic", full_disk)
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    assert not path.exists()
    monkeypatch.setattr(sends, "write_json_atomic", real)
    history.flush()
    assert len(_on_disk(path)["p"]) == 1


def test_a_clock_step_back_never_arms_a_timer_past_the_interval(store):
    history, clock, _ = store
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    clock.now -= 3600  # NTP stepped the clock back an hour
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    (timer,) = [t for t in FakeTimer.armed if not t.cancelled]
    assert 0 <= timer.delay <= 180


def test_a_send_landing_after_the_page_was_deleted_is_not_recorded(store):
    # Probe P10: an in-flight engine send finishing after delete_page.
    history, _, path = store
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    history.forget("p")
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
    history.flush()
    assert history.sends("p") == []
    assert "p" not in _on_disk(path)


def test_a_corrupt_file_starts_empty(tmp_path):
    from src.pages.sends import SendHistory

    path = tmp_path / "page_sends.json"
    path.write_text("{not json")
    history = SendHistory(path)
    assert history.sends("p") == []
    history.close()


def test_the_apps_shutdown_flushes_send_history(monkeypatch):
    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.pages import sends

    flushed = []
    monkeypatch.setattr("src.system.mdns.start_mdns", lambda *a, **k: True)
    monkeypatch.setattr(sends, "flush_send_history", lambda: flushed.append(1))
    with TestClient(app):
        assert flushed == []
    assert flushed == [1]


# ── the phone scope ─────────────────────────────────────────────────────────


def test_the_phone_reads_send_history_and_a_tv_does_not():
    from src.auth import scopes

    assert scopes.permits(scopes.CONTROL, "GET", "/pages/x/sends")
    assert not scopes.permits(scopes.TV_PANELS, "GET", "/pages/x/sends")
