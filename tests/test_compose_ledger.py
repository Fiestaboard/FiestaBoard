"""A UUID is correlation, not permission to retry physical output."""

from datetime import UTC, datetime, timedelta

import pytest

from tests.test_compose_intent import decode


def ledger(tmp_path, **kwargs):
    from src.compose.ledger import ComposeLedger

    return ComposeLedger(tmp_path / "compose_requests.json", **kwargs)


def test_exact_duplicate_returns_cached_receipt_without_new_dispatch(tmp_path):
    store = ledger(tmp_path)
    request = decode()
    first, fresh = store.begin(request, board_id="a", actor="phone-one")
    assert fresh and first.request_id == request.request_id
    store.mark_dispatching(request, board_id="a")
    accepted = store.delivered(request, board_id="a", released_at=datetime.now(UTC), sent=True)
    repeated, fresh = store.begin(request, board_id="a", actor="phone-one")
    assert not fresh and repeated == accepted
    late = store.delivered(request, board_id="a", released_at=datetime.now(UTC) + timedelta(minutes=5), sent=True)
    assert late.expires_at == accepted.expires_at


def test_uuid_cannot_change_payload_display_or_actor(tmp_path):
    from src.compose.ledger import ComposeRequestConflict

    store = ledger(tmp_path)
    value = decode()
    store.begin(value, board_id="a", actor="phone-one")
    changed = value.model_copy(update={"template": ["OTHER"]})
    for request, board, actor in [(changed, "a", "phone-one"), (value, "b", "phone-one"), (value, "a", "phone-two")]:
        with pytest.raises(ComposeRequestConflict):
            store.begin(request, board_id=board, actor=actor)


def test_restart_turns_in_flight_into_unknown_and_never_redispatches(tmp_path):
    store = ledger(tmp_path)
    request = decode()
    store.begin(request, board_id="a", actor="phone-one")
    store.mark_dispatching(request, board_id="a")
    restarted = ledger(tmp_path)
    receipt, fresh = restarted.begin(request, board_id="a", actor="phone-one")
    assert not fresh and receipt.status == "unknown" and receipt.sent is None
    assert not restarted.mark_dispatching(request, board_id="a")


def test_held_request_survives_restart_and_duration_starts_only_on_release(tmp_path):
    now = datetime.now(UTC)
    request = decode(prepared_at=now.isoformat())
    store = ledger(tmp_path)
    store.begin(request, board_id="a", actor="phone-one")
    store.mark_held(request, board_id="a", held_until=(now + timedelta(hours=7)).isoformat())
    restarted = ledger(tmp_path)
    release = now + timedelta(hours=7)
    assert restarted.mark_dispatching(request, board_id="a")
    receipt = restarted.delivered(request, board_id="a", released_at=release, sent=True)
    assert datetime.fromisoformat(receipt.expires_at) == release + timedelta(minutes=120)


def test_bounded_history_refuses_new_requests_instead_of_forgetting_live_ids(tmp_path):
    from src.compose.ledger import ComposeHistoryFull

    store = ledger(tmp_path, maximum_records=2)
    store.begin(decode(), board_id="a", actor="phone-one")
    store.begin(decode(), board_id="b", actor="phone-one")
    with pytest.raises(ComposeHistoryFull):
        store.begin(decode(), board_id="c", actor="phone-one")


def test_failed_reservation_persistence_never_claims_a_new_intent(tmp_path, monkeypatch):
    store = ledger(tmp_path)
    value = decode()
    monkeypatch.setattr(store._store, "save", lambda data: (_ for _ in ()).throw(OSError("read only")))
    with pytest.raises(OSError):
        store.begin(value, board_id="a", actor="phone-one")
    assert store.get(value.request_id, board_id="a", actor="phone-one") is None


def test_missing_receipt_in_durable_history_fails_closed_as_unavailable(tmp_path):
    import json

    path = tmp_path / "compose_requests.json"
    path.write_text(json.dumps({"records": {"bad": {}}}))
    with pytest.raises(ValueError, match="history is unavailable"):
        ledger(tmp_path)
    assert json.loads(path.read_text()) == {"records": {"bad": {}}}
