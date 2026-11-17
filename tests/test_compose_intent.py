"""I8: one captured Compose intent survives Hold without inventing duration."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest


def request(**overrides):
    value = {
        "protocol": "compose-intent-v1", "request_id": str(uuid4()),
        "template": ["HELLO {{red:WORLD}}"],
        "line_metadata": [{"alignment": "center", "wrap": False}],
        "geometry": {"device_type": "flagship", "notes_wide": 1, "notes_tall": 1},
        "duration": {"kind": "minutes", "minutes": 120}, "silence": "hold",
    }
    return {**value, **overrides}


def decode(**overrides):
    from src.compose.models import ComposeRequest
    return ComposeRequest.model_validate(request(**overrides))


def test_duration_has_no_implicit_indefinite_fallback():
    from pydantic import ValidationError
    for invalid in ({}, {"kind": "minutes"}, {"kind": "minutes", "minutes": 0},
                    {"kind": "minutes", "minutes": 481}, {"kind": "until"},
                    {"kind": "until_cancel", "minutes": 2}):
        with pytest.raises(ValidationError):
            decode(duration=invalid)


def test_absolute_end_cannot_become_indefinite_at_release():
    from src.compose.models import ExpiredComposeIntent
    end = datetime.now(UTC) + timedelta(minutes=5)
    value = decode(duration={"kind": "until", "ends_at": end.isoformat()})
    assert value.expires_at(released_at=end-timedelta(seconds=1)) == end.isoformat()
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
    from src.silence_queue import HeldSend, _from_dict
    from dataclasses import asdict
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


@pytest.mark.parametrize("value", ["2026-11-17T20:00:00", "NaN", "Infinity", "2026-11-17T20:00:00+25:00",
    "2026-11-17T20:00:00+00:00:01", "2026-11-17T20:00:00+0000"])
def test_absolute_end_requires_a_finite_rfc3339_offset_instant(value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        decode(duration={"kind": "until", "ends_at": value})
