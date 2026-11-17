"""I8: one captured Compose intent survives Hold without inventing duration."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest


def request(**overrides):
    value = {
        "protocol": "compose-intent-v1",
        "request_id": str(uuid4()),
        "prepared_at": datetime.now(UTC).isoformat(),
        "template": ["HELLO {{red:WORLD}}"],
        "line_metadata": [{"alignment": "center", "wrap": False}],
        "geometry": {"device_type": "flagship", "notes_wide": 1, "notes_tall": 1},
        "duration": {"kind": "minutes", "minutes": 120},
        "silence": "hold",
    }
    return {**value, **overrides}


def decode(**overrides):
    from src.compose.models import ComposeRequest

    return ComposeRequest.model_validate(request(**overrides))


def test_duration_has_no_implicit_indefinite_fallback():
    from pydantic import ValidationError

    for invalid in (
        {},
        {"kind": "minutes"},
        {"kind": "minutes", "minutes": 0},
        {"kind": "minutes", "minutes": 481},
        {"kind": "until"},
        {"kind": "until_cancel", "minutes": 2},
    ):
        with pytest.raises(ValidationError):
            decode(duration=invalid)


def test_absolute_end_cannot_become_indefinite_at_release():
    from src.compose.models import ExpiredComposeIntent

    end = datetime.now(UTC) + timedelta(minutes=5)
    value = decode(duration={"kind": "until", "ends_at": end.isoformat()})
    assert value.expires_at(released_at=end - timedelta(seconds=1)) == end.isoformat()
    with pytest.raises(ExpiredComposeIntent):
        value.expires_at(released_at=end)


def test_relative_duration_starts_at_release_not_enqueue():
    enqueued = datetime.now(UTC)
    release = enqueued + timedelta(hours=7)
    value = decode()
    assert datetime.fromisoformat(value.expires_at(released_at=release)) == release + timedelta(minutes=120)


def test_until_cancel_is_explicit_and_metadata_is_preserved():
    value = decode(duration={"kind": "until_cancel"})
    assert value.expires_at(released_at=datetime.now(UTC)) is None
    assert value.model_dump(mode="json")["line_metadata"] == [{"alignment": "center", "wrap": False}]


def test_held_compose_round_trip_retains_original_payload_and_uuid():
    from dataclasses import asdict

    from src.silence_queue import HeldSend, _from_dict

    value = decode()
    held = HeldSend.compose(value.model_dump(mode="json"), board_id="display-a")
    recovered = _from_dict(asdict(held))
    assert recovered == held
    assert recovered.payload == value.model_dump(mode="json")
    assert recovered.payload["duration"]["minutes"] == 120


def test_conditional_discard_never_removes_newer_held_intent():
    from src import silence_queue

    first = silence_queue.HeldSend.compose(decode().model_dump(mode="json"), board_id="display-a")
    newer = silence_queue.HeldSend.compose(decode().model_dump(mode="json"), board_id="display-a")
    silence_queue.hold(first)
    silence_queue.hold(newer)
    assert not silence_queue.discard_if_current(first)
    assert silence_queue.peek("display-a") == newer
    assert silence_queue.discard_if_current(newer)
    assert silence_queue.peek("display-a") is None


def test_absolute_end_must_not_bypass_eight_hour_limit_at_admission_or_release():
    from src.compose.models import InvalidComposeDuration

    now = datetime.now(UTC)
    value = decode(duration={"kind": "until", "ends_at": (now + timedelta(minutes=481)).isoformat()})
    with pytest.raises(InvalidComposeDuration):
        value.validate_admission(now=now)
    with pytest.raises(InvalidComposeDuration):
        value.expires_at(released_at=now)


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-17T20:00:00",
        "NaN",
        "Infinity",
        "2026-11-17T20:00:00+25:00",
        "2026-11-17T20:00:00+00:00:01",
        "2026-11-17T20:00:00+0000",
    ],
)
def test_absolute_end_requires_a_finite_rfc3339_offset_instant(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        decode(duration={"kind": "until", "ends_at": value})


@pytest.mark.parametrize("value", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"])
def test_offset_normalization_overflow_is_a_validation_refusal(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        decode(duration={"kind": "until", "ends_at": value})


def test_prepared_request_has_a_bounded_replay_window():
    from src.compose.models import InvalidComposeDuration

    now = datetime.now(UTC)
    for prepared in (now - timedelta(minutes=6), now + timedelta(minutes=6)):
        value = decode(prepared_at=prepared.isoformat())
        with pytest.raises(InvalidComposeDuration):
            value.validate_admission(now=now)


def test_strict_compose_hold_failure_does_not_claim_persistence(monkeypatch):
    from src import silence_queue

    held = silence_queue.HeldSend.compose(decode().model_dump(mode="json"), board_id="strict-a")
    monkeypatch.setattr(silence_queue, "_save_locked", lambda **kwargs: (_ for _ in ()).throw(OSError("read only")))
    with pytest.raises(OSError):
        silence_queue.hold(held, strict=True)
    assert silence_queue.peek("strict-a") is None


def test_queue_compare_and_commit_is_atomic_with_exact_captured_entry():
    from src import silence_queue

    old = silence_queue.HeldSend.compose(decode().model_dump(mode="json"), board_id="atomic-a")
    newer = silence_queue.HeldSend.compose(decode().model_dump(mode="json"), board_id="atomic-a")
    silence_queue.hold(old)
    silence_queue.hold(newer)
    committed = []
    assert not silence_queue.commit_if_current(old, lambda: committed.append("old"))
    assert committed == []
    assert silence_queue.commit_if_current(newer, lambda: committed.append("new"))
    assert committed == ["new"] and silence_queue.peek("atomic-a") is None


def test_nested_old_operation_cannot_revive_its_control_generation():
    import contextvars

    from src.override_undo import _manual_operation
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    with _manual_operation():
        old = settings.control_revision

        def newer_operation():
            with _manual_operation():
                pass

        contextvars.Context().run(newer_operation)
        new = settings.control_revision
        assert new != old
        with _manual_operation():
            assert settings.control_revision == new


def test_failed_queue_consumption_preserves_exact_entry_for_reconciliation(monkeypatch):
    from src import silence_queue

    held = silence_queue.HeldSend.compose(decode().model_dump(mode="json"), board_id="consume-failure")
    silence_queue.hold(held)
    saved = silence_queue._save_locked

    def fail_strict(**kwargs):
        if kwargs.get("strict"):
            raise OSError("read only")
        return saved(**kwargs)

    monkeypatch.setattr(silence_queue, "_save_locked", fail_strict)
    with pytest.raises(OSError):
        silence_queue.discard_if_current(held)
    assert silence_queue.peek(held.board_id) == held
