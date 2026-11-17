"""H22: status reads cannot steal the display engine's pending expiry action.

The settings store is real, including its lock and JSON writes. Only board
transport and unrelated page/schedule rendering use the existing engine
harness. Events control thread ordering; timeouts only detect deadlocks.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.board_chars import characters_to_message
from src.settings.service import SettingsService, TemporaryOverride, get_settings_service
from tests.test_per_board_engine import _board, _drive, _page_service, _schedule_service, _service_with_runtimes
from tests.test_v1_contract import board_client, client  # noqa: F401 - fixtures

START = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
END = START + timedelta(minutes=1)


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=START)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now.astimezone(tz) if tz is not None else clock.now.replace(tzinfo=None)

    monkeypatch.setattr("src.settings.service.datetime", FrozenDatetime)
    # The baseline has no main.datetime import yet; the shared-instant fix
    # adds it. Both versions must reach the behavior assertions below.
    monkeypatch.setattr("src.main.datetime", FrozenDatetime, raising=False)
    return clock


@pytest.fixture
def store(clock):
    store = get_settings_service()
    store.set_boards([_board("b1", "One"), _board("b2", "Two", port=7001)])
    store.set_output_target("board")
    for board_id, page_id in (("b1", "manual"), ("b2", "other")):
        store.set_schedule_enabled(False, board_id=board_id)
        store.set_active_page_id(page_id, board_id=board_id)
    return store


@pytest.fixture
def engine(store):
    boards = store.get_board_settings().boards
    service, clients = _service_with_runtimes(boards)
    pages = _page_service(
        {
            "manual": {"content": "MANUAL"},
            "other": {"content": "OTHER"},
            "override": {"content": "OVERRIDE"},
            "reverted": {"content": "REVERTED"},
            "scheduled": {"content": "SCHEDULED"},
        }
    )
    schedules = _schedule_service({"b1": "scheduled"})

    def tick():
        return _drive(service, boards, settings=store, pages=pages, schedule=schedules)

    def frames(board_id="b1"):
        return [characters_to_message(call.args[0]).strip() for call in clients[board_id].render.call_args_list]

    return SimpleNamespace(tick=tick, frames=frames, service=service)


def _arm(store, mode="page", board_id="b1"):
    override = TemporaryOverride(
        page_id="override",
        expires_at=END.isoformat(),
        revert_mode=mode,
        revert_page_id="reverted" if mode == "page" else None,
    )
    store.set_temporary_override(override, board_id=board_id)
    return override


def _thread(name, action, errors):
    def run():
        try:
            action()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    return thread


def _join(threads, errors):
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive(), f"{thread.name} did not finish"
    if errors:
        raise errors[0]


@pytest.mark.parametrize("mode", ["schedule", "page", "blank"])
def test_expired_reads_leave_one_pending_consumption(store, clock, mode):
    override = _arm(store, mode)
    clock.now = END
    before = store._store.path.read_bytes()

    for _ in range(3):
        assert store.get_temporary_override("b1") is None
        assert store.list_temporary_overrides() == {}

    assert store._store.path.read_bytes() == before
    assert store.consume_temporary_override("b1") is override
    assert store.consume_temporary_override("b1") is None
    assert json.loads(store._store.path.read_text())["temporary_override"] is None


@pytest.mark.parametrize(
    ("mode", "expected_frames", "expected_page"),
    [
        ("schedule", ["OVERRIDE", "SCHEDULED"], "manual"),
        ("page", ["OVERRIDE", "REVERTED"], "reverted"),
        ("blank", ["OVERRIDE", "", "MANUAL"], "manual"),
    ],
)
def test_reader_before_engine_does_not_steal_revert(store, clock, engine, mode, expected_frames, expected_page):
    store.set_schedule_enabled(mode == "schedule", board_id="b1")
    _arm(store, mode)
    engine.tick()
    assert engine.frames() == ["OVERRIDE"]
    clock.now = END
    read_done = threading.Event()
    errors = []

    def read():
        try:
            for _ in range(3):
                assert store.get_temporary_override("b1") is None
        finally:
            read_done.set()

    def consume():
        assert read_done.wait(5), "reader did not finish"
        engine.tick()

    with patch.object(store, "set_active_page_id", wraps=store.set_active_page_id) as set_page:
        threads = [_thread("engine", consume, errors), _thread("reader", read, errors)]
        _join(threads, errors)
        engine.tick()
        assert set_page.call_count == (1 if mode == "page" else 0)

    assert engine.frames() == expected_frames
    assert engine.frames("b2") == ["OTHER"]
    assert store.get_active_page_id("b1") == expected_page
    assert store.get_active_page_id("b2") == "other"
    assert json.loads(store._store.path.read_text())["active_page"]["by_board"]["b1"] == expected_page
    assert store.peek_temporary_override("b1") is None


@pytest.mark.parametrize("mode", ["schedule", "page", "blank"])
def test_clock_crossing_after_consume_does_not_apply_an_unclaimed_revert(store, clock, engine, monkeypatch, mode):
    store.set_schedule_enabled(mode == "schedule", board_id="b1")
    _arm(store, mode)
    clock.now = END - timedelta(microseconds=1)
    consume = store.consume_temporary_override
    advanced = False

    def cross_boundary(board_id=None, **kwargs):
        nonlocal advanced
        result = consume(board_id=board_id, **kwargs)
        if board_id == "b1" and not advanced:
            advanced = True
            clock.now = END
        return result

    monkeypatch.setattr(store, "consume_temporary_override", cross_boundary)
    with patch.object(store, "set_active_page_id", wraps=store.set_active_page_id) as set_page:
        engine.tick()
        # This pass claimed a live override. Crossing expiry afterwards
        # must not apply a revert while leaving the same pending object.
        assert engine.frames() == ["OVERRIDE"]
        assert store.get_active_page_id("b1") == "manual"
        engine.tick()
        engine.tick()
        assert set_page.call_count == (1 if mode == "page" else 0)

    expected = {
        "schedule": ["OVERRIDE", "SCHEDULED"],
        "page": ["OVERRIDE", "REVERTED"],
        "blank": ["OVERRIDE", "", "MANUAL"],
    }
    assert engine.frames() == expected[mode]
    assert store.peek_temporary_override("b1") is None


@pytest.mark.parametrize("contender", ["consume", "replace"])
def test_consume_serializes_with_another_consumer_or_replacement(store, clock, monkeypatch, contender):
    old = _arm(store)
    other = _arm(store, board_id="b2")
    clock.now = END
    evaluating = threading.Event()
    release = threading.Event()
    attempted = threading.Event()
    errors = []
    results = {}
    original_expired = old.is_expired
    original_lock = store._store.lock
    replacement = TemporaryOverride(page_id="replacement")

    class ObservedLock:
        def __enter__(self):
            if threading.current_thread().name == "contender":
                attempted.set()
            original_lock.acquire()
            return self

        def __exit__(self, *_exc):
            original_lock.release()

    def pause_expiry(*args, **kwargs):
        if threading.current_thread().name == "consumer":
            evaluating.set()
            assert release.wait(5), "expiry evaluation was not released"
        return original_expired(*args, **kwargs)

    monkeypatch.setattr(store._store, "_lock", ObservedLock())
    monkeypatch.setattr(old, "is_expired", pause_expiry)

    def first():
        results["first"] = store.consume_temporary_override("b1")

    def second():
        if contender == "replace":
            store.set_temporary_override(replacement, board_id="b1")
        else:
            results["second"] = store.consume_temporary_override("b1")

    threads = [_thread("consumer", first, errors)]
    try:
        assert evaluating.wait(5), "consumer did not reach expiry evaluation"
        threads.append(_thread("contender", second, errors))
        assert attempted.wait(5), "contender did not attempt the settings lock"
    finally:
        release.set()
        _join(threads, errors)

    assert results["first"] is old
    if contender == "replace":
        assert store.get_temporary_override("b1") is replacement
        assert store.consume_temporary_override("b1") is replacement
        assert json.loads(store._store.path.read_text())["temporary_override"]["page_id"] == "replacement"
    else:
        assert results["second"] is None
        assert store.consume_temporary_override("b1") is None
    assert store.consume_temporary_override("b2") is other
    assert store.consume_temporary_override("b2") is None


def test_replacement_before_consume_supersedes_expired_revert(store, clock):
    _arm(store)
    clock.now = END
    replacement = TemporaryOverride(page_id="replacement")
    store.set_temporary_override(replacement, board_id="b1")
    assert store.consume_temporary_override("b1") is replacement
    assert store.get_active_page_id("b1") == "manual"


@pytest.mark.parametrize("endpoint", ["override", "schedule", "board"])
@pytest.mark.parametrize("board_id", ["b1", "b2"])
def test_http_status_is_inactive_without_consuming_pending_revert(
    client,  # noqa: F811
    board_client,  # noqa: F811
    store,
    clock,
    endpoint,
    board_id,
):
    override = _arm(store, board_id=board_id)
    clock.now = END
    paths = {
        "override": f"/settings/temporary-override?board_id={board_id}",
        "schedule": f"/schedules/active/page?board_id={board_id}",
        "board": f"/v1/boards/{board_id}",
    }
    for _ in range(2):
        response = client.get(paths[endpoint])
        assert response.status_code == 200, response.text
        payload = response.json()
        if endpoint == "board":
            assert payload["override_expires_at"] is None
            assert payload["override_started_at"] is None
        else:
            status = payload["temporary_override"] if endpoint == "schedule" else payload
            assert status["active"] is False
    assert store.consume_temporary_override(board_id) is override
    assert store.consume_temporary_override(board_id) is None


@pytest.mark.parametrize("mode", ["schedule", "page", "blank"])
@pytest.mark.parametrize("expired", [False, True])
def test_explicit_cancellation_preserves_its_existing_revert_contract(
    client,  # noqa: F811
    board_client,  # noqa: F811
    store,
    clock,
    mode,
    expired,
):
    _arm(store, mode, board_id="b2")
    unaffected = _arm(store, board_id="b1")
    if expired:
        clock.now = END
    response = client.delete("/settings/temporary-override?board_id=b2")
    assert response.status_code == 200, response.text
    assert response.json()["revert_mode"] == (None if expired else mode)
    assert store.get_active_page_id("b2") == ("reverted" if mode == "page" and not expired else "other")
    assert store.consume_temporary_override("b2") is None
    assert store.peek_temporary_override("b1") is unaffected
    assert store.get_active_page_id("b1") == "manual"


@pytest.mark.parametrize("expired", [False, True])
def test_legacy_primary_override_keeps_restart_semantics(store, clock, expired):
    _arm(store)
    path = store._store.path
    raw = json.loads(path.read_text())
    raw["temporary_override"].pop("started_at")
    path.write_text(json.dumps(raw))
    if expired:
        clock.now = END

    reloaded = SettingsService(settings_file=str(path))
    assert reloaded.peek_temporary_override("b2") is None
    loaded = reloaded.peek_temporary_override("b1")
    if expired:
        assert loaded is None
    else:
        assert loaded.page_id == "override"
        assert loaded.started_at is None
        clock.now = END
        assert reloaded.get_temporary_override("b1") is None
        assert reloaded.consume_temporary_override("b1") is loaded
