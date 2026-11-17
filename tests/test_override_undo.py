"""Atomic cancel authority never becomes an unconditional override write."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from unittest.mock import patch

import pytest

from src.auth.scopes import CONTROL, TV_PANELS, permits
from src.settings.service import SettingsService, TemporaryOverride


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"board": {"boards": [
        {"id": "a", "name": "A", "device_type": "flagship"},
        {"id": "b", "name": "B", "device_type": "flagship"},
    ]}}))
    return SettingsService(str(path))


def start(store, **kwargs):
    value = TemporaryOverride(template=["HELLO"], line_metadata=[{"align": "center"}],
        expires_at=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(), **kwargs)
    store.set_temporary_override(value, "a")
    return value.to_dict()


def cancel(store, actor="phone-1"):
    return store.cancel_temporary_override("a", actor=actor, undo=True)


def restore(store, token, board="a", actor="phone-1"):
    return store.undo_temporary_override(board, token, actor=actor)


def test_cancel_restores_exact_payload_and_original_expiry_and_run(store):
    original = start(store)
    _, token, deadline = cancel(store)
    assert store.get_temporary_override("a") is None
    assert datetime.fromisoformat(deadline) <= datetime.now(UTC) + timedelta(seconds=30)
    assert restore(store, token).to_dict() == original
    assert SettingsService(str(store.settings_file)).get_temporary_override("a").to_dict() == original
    with pytest.raises(ValueError):
        restore(store, token)


def test_receipt_is_bound_to_display_and_actor(store):
    start(store)
    _, token, _ = cancel(store)
    for board, actor in [("b", "phone-1"), ("a", "phone-2")]:
        with pytest.raises(ValueError):
            restore(store, token, board, actor)
    assert restore(store, token).template == ["HELLO"]


def test_receipt_cannot_restore_a_replacement_even_after_replacement_cancel(store):
    start(store)
    _, token, _ = cancel(store)
    store.set_temporary_override(TemporaryOverride(page_id="replacement"), "a")
    store.clear_temporary_override("a")
    with pytest.raises(ValueError):
        restore(store, token)
    assert store.get_temporary_override("a") is None


def test_original_expiry_and_short_receipt_deadline_are_both_enforced(store):
    start(store)
    _, token, _ = cancel(store)
    with patch("src.settings.service.time.monotonic", return_value=10**15):
        with pytest.raises(ValueError):
            restore(store, token)
    start(store)
    _, token, _ = cancel(store)
    with patch.object(TemporaryOverride, "is_expired", return_value=True):
        with pytest.raises(ValueError):
            restore(store, token)


def test_restart_and_reload_discard_receipt_authority(store):
    start(store)
    _, token, _ = cancel(store)
    with pytest.raises(ValueError):
        restore(SettingsService(str(store.settings_file)), token)
    store.reload()
    with pytest.raises(ValueError):
        restore(store, token)


def test_cancel_applies_page_revert_before_issuing_receipt(store):
    start(store, revert_mode="page", revert_page_id="after")
    _, token, _ = cancel(store)
    assert store.get_active_page_id("a") == "after"
    assert restore(store, token).revert_page_id == "after"


def test_concurrent_restores_have_one_winner(store):
    start(store)
    _, token, _ = cancel(store)
    def attempt(_):
        try:
            restore(store, token)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(16))) == 1


def test_pending_mutation_blocks_without_consuming_and_failure_preserves_receipt(store):
    start(store)
    _, token, _ = cancel(store)
    store.begin_override_mutation()
    with pytest.raises(ValueError):
        restore(store, token)
    store.finish_override_mutation(success=False)
    assert restore(store, token).template == ["HELLO"]


def test_successful_relevant_mutation_invalidates_receipt(store):
    start(store)
    _, token, _ = cancel(store)
    store.begin_override_mutation()
    store.finish_override_mutation(success=True)
    with pytest.raises(ValueError):
        restore(store, token)


def test_unrelated_settings_save_conservatively_invalidates_receipt(store):
    start(store)
    _, token, _ = cancel(store)
    store.set_polling_interval(42)
    with pytest.raises(ValueError):
        restore(store, token)


def test_failed_restore_persistence_consumes_receipt(store):
    start(store)
    _, token, _ = cancel(store)
    with patch.object(store, "_save_to_file", side_effect=OSError("full")):
        with pytest.raises(OSError):
            restore(store, token)
    with pytest.raises(ValueError):
        restore(store, token)


def test_exact_mobile_scope_addition_does_not_grant_admin_or_tv_access():
    assert permits(CONTROL, "POST", "/settings/temporary-override/undo")
    assert not permits(CONTROL, "PUT", "/settings/temporary-override/undo")
    assert not permits(TV_PANELS, "POST", "/settings/temporary-override/undo")
    assert not permits(CONTROL, "POST", "/settings/reload")
