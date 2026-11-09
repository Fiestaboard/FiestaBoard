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
    from src.outputs.health import HealthSummary

    primary, _ = boards
    board.render.return_value = (False, False)
    with patch("src.pages.sends.board_health", return_value=HealthSummary(last_error="auth")):
        assert _show_now(client, page, primary).status_code == 500
    (entry,) = _sends(client, page)
    assert (entry["outcome"], entry["error"]) == ("failed", "auth")


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

    primary, _ = boards
    for n in range(25):
        send_history().record(page, outcome="sent", via="auto", board_id=primary, board_name=f"B{n}")
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
    history.record("p", outcome="sent", via="auto", board_id="b", board_name="B")
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
