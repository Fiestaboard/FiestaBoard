"""Unit tests for the TemporaryOverride dataclass."""

from datetime import UTC, datetime, timedelta

from src.settings.service import TemporaryOverride


def _future_iso(minutes: int = 10) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def _past_iso(minutes: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


class TestTemporaryOverrideExpiry:
    def test_is_expired_false_when_future(self):
        o = TemporaryOverride(page_id="p1", expires_at=_future_iso(10), revert_mode="schedule")
        assert not o.is_expired()

    def test_is_expired_true_when_past(self):
        o = TemporaryOverride(page_id="p1", expires_at=_past_iso(1), revert_mode="schedule")
        assert o.is_expired()

    def test_is_expired_handles_naive_datetime(self):
        # Naive ISO string (no tz) should be treated as UTC
        naive = (datetime.now(UTC) - timedelta(minutes=1)).replace(tzinfo=None).isoformat()
        o = TemporaryOverride(page_id="p1", expires_at=naive, revert_mode="schedule")
        assert o.is_expired()

    def test_is_expired_handles_malformed_string(self):
        o = TemporaryOverride(page_id="p1", expires_at="not-a-date", revert_mode="schedule")
        assert o.is_expired()

    def test_remaining_seconds_positive_when_active(self):
        o = TemporaryOverride(page_id="p1", expires_at=_future_iso(5), revert_mode="schedule")
        remaining = o.remaining_seconds()
        assert 200 < remaining <= 300

    def test_remaining_seconds_zero_when_expired(self):
        o = TemporaryOverride(page_id="p1", expires_at=_past_iso(1), revert_mode="schedule")
        assert o.remaining_seconds() == 0.0

    def test_remaining_seconds_handles_malformed_string(self):
        o = TemporaryOverride(page_id="p1", expires_at="bad", revert_mode="schedule")
        assert o.remaining_seconds() == 0.0


class TestTemporaryOverrideSerialization:
    def test_to_dict_roundtrip(self):
        o = TemporaryOverride(
            page_id="abc-123",
            expires_at=_future_iso(15),
            revert_mode="page",
            revert_page_id="xyz-456",
        )
        d = o.to_dict()
        restored = TemporaryOverride.from_dict(d)
        assert restored.page_id == o.page_id
        assert restored.expires_at == o.expires_at
        assert restored.revert_mode == o.revert_mode
        assert restored.revert_page_id == o.revert_page_id

    def test_from_dict_defaults_revert_mode(self):
        d = {"page_id": "p1", "expires_at": _future_iso()}
        o = TemporaryOverride.from_dict(d)
        assert o.revert_mode == "schedule"
        assert o.revert_page_id is None

    def test_to_dict_contains_all_keys(self):
        o = TemporaryOverride(page_id="p1", expires_at=_future_iso(), revert_mode="blank")
        d = o.to_dict()
        assert "page_id" in d
        assert "expires_at" in d
        assert "revert_mode" in d
        assert "revert_page_id" in d
