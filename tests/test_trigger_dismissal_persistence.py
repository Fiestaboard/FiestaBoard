"""Persisted trigger dismissals + TimeService clock (issue #1850, Track B7).

Two platform gaps closed per the #1767 decision (triggers stay a live
plugin-facing feature; the plugin contract — ``supports_triggers`` /
``check_triggers()`` / ``trigger_page_id`` — is unchanged):

1. Dismissals were in-memory only, so a dismissed trigger came back after a
   restart. Suppressed dismissals now persist to a schema-versioned JSON
   store and are honored by a fresh ``TriggerService`` instance.
2. ``TriggerService`` told time with module-level naive ``datetime.now()``
   instead of the app's TimeService, so trigger timing ignored the app's
   clock discipline.

Every test here drives the service through the fake TimeService ONLY — the
engine harness's old fifth clock seam (``src.triggers.service.datetime``)
is gone, and no test patches it — proving trigger timing is deterministic
through the app's one clock.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from src.plugins.base import TriggerResult
from src.triggers.service import TriggerService
from tests.fake_clock import FakeClock, install_fake_time_service

T0 = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)


def _result(trigger_id: str = "door-open", duration: int = 3600, priority: int = 5) -> TriggerResult:
    return TriggerResult(
        triggered=True,
        trigger_id=trigger_id,
        message="DOOR OPEN",
        priority=priority,
        duration_seconds=duration,
    )


def test_suppressed_dismissal_survives_restart(monkeypatch, tmp_path):
    """Dismiss with suppress=True, restart, plugin re-emits: still suppressed.

    "Restart" is a fresh TriggerService instance reading the same store file
    — exactly what process restart does through get_trigger_service().
    """
    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    store = tmp_path / "trigger_dismissals.json"

    svc = TriggerService(dismissals_file=store)
    svc.activate_trigger("stub_plugin", _result())
    assert svc.dismiss_trigger("door-open", suppress=True) is True
    assert svc.get_active_trigger() is None

    svc2 = TriggerService(dismissals_file=store)
    svc2.activate_trigger("stub_plugin", _result())  # plugin re-emits after reboot
    assert svc2.get_active_trigger() is None, "a suppressed dismissal must survive a restart"


def test_suppression_expires_after_suppressed_until(monkeypatch, tmp_path):
    """Past the persisted suppressed_until horizon the trigger fires again.

    Suppression covers what was left of the trigger's natural duration
    (activated_at + duration_seconds) — the pre-existing semantics, now
    surviving a restart.
    """
    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    store = tmp_path / "trigger_dismissals.json"

    svc = TriggerService(dismissals_file=store)
    svc.activate_trigger("stub_plugin", _result(duration=60))
    svc.dismiss_trigger("door-open", suppress=True)

    clock.advance(61)  # past the suppression horizon
    svc2 = TriggerService(dismissals_file=store)
    svc2.activate_trigger("stub_plugin", _result(duration=60))
    active = svc2.get_active_trigger()
    assert active is not None and active.trigger_id == "door-open"


def test_store_is_schema_versioned_with_suppression_horizon(monkeypatch, tmp_path):
    """The store carries schema_version 1 and per-trigger horizon + stamp."""
    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    store = tmp_path / "trigger_dismissals.json"

    svc = TriggerService(dismissals_file=store)
    svc.activate_trigger("stub_plugin", _result(duration=120))
    svc.dismiss_trigger("door-open", suppress=True)

    data = json.loads(store.read_text())
    assert data["schema_version"] == 1
    entry = data["dismissals"]["door-open"]
    assert entry["suppressed_until"] == (T0 + timedelta(seconds=120)).isoformat()
    assert entry["dismissed_at"] == T0.isoformat()


def test_expired_entries_are_pruned_on_load(monkeypatch, tmp_path):
    """Loading drops entries whose suppression already lapsed (and junk)."""
    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    store = tmp_path / "trigger_dismissals.json"
    store.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dismissals": {
                    "live": {
                        "suppressed_until": (T0 + timedelta(seconds=300)).isoformat(),
                        "dismissed_at": (T0 - timedelta(seconds=60)).isoformat(),
                    },
                    "lapsed": {
                        "suppressed_until": (T0 - timedelta(seconds=1)).isoformat(),
                        "dismissed_at": (T0 - timedelta(seconds=600)).isoformat(),
                    },
                    "junk": {"suppressed_until": None, "dismissed_at": None},
                },
            }
        )
    )

    svc = TriggerService(dismissals_file=store)
    assert set(svc._suppressed_until) == {"live"}
    svc.activate_trigger("stub_plugin", _result(trigger_id="lapsed"))
    assert svc.get_active_trigger() is not None, "a lapsed suppression must not block re-activation"


def test_unsuppressed_dismissal_leaves_no_durable_state(monkeypatch, tmp_path):
    """suppress=False keeps today's semantics: nothing survives the dismissal."""
    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    store = tmp_path / "trigger_dismissals.json"

    svc = TriggerService(dismissals_file=store)
    svc.activate_trigger("stub_plugin", _result())
    svc.dismiss_trigger("door-open", suppress=False)

    svc2 = TriggerService(dismissals_file=store)
    svc2.activate_trigger("stub_plugin", _result())
    assert svc2.get_active_trigger() is not None


def test_trigger_expiry_honors_time_service_without_datetime_seam(monkeypatch, tmp_path):
    """Expiry follows the fake TimeService — no datetime-module patch anywhere.

    Pre-#1850 this fails: the service read wall-clock ``datetime.now()``, so
    advancing the fake clock never expired the trigger.
    """
    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)

    svc = TriggerService(dismissals_file=tmp_path / "trigger_dismissals.json")
    svc.activate_trigger("stub_plugin", _result(duration=30))
    clock.advance(29)
    assert svc.get_active_trigger() is not None
    clock.advance(2)
    assert svc.get_active_trigger() is None, "trigger expiry must follow the app's TimeService clock"


def test_suppression_lapse_honors_time_service_without_datetime_seam(monkeypatch, tmp_path):
    """Suppression lapse also runs on the TimeService clock (same instance)."""
    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)

    svc = TriggerService(dismissals_file=tmp_path / "trigger_dismissals.json")
    svc.activate_trigger("stub_plugin", _result(duration=60))
    svc.dismiss_trigger("door-open", suppress=True)

    svc.activate_trigger("stub_plugin", _result(duration=60))
    assert svc.get_active_trigger() is None, "still inside the suppression window"

    clock.advance(61)
    svc.activate_trigger("stub_plugin", _result(duration=60))
    assert svc.get_active_trigger() is not None


def test_engine_prune_during_dismissal_save_neither_raises_nor_loses_the_write(monkeypatch, tmp_path):
    """#1871 review: _save_dismissals built its snapshot of _suppressed_until
    OUTSIDE the lock and outside the try — an engine-tick prune
    (clear_expired) mutating the dict mid-comprehension raised RuntimeError
    INTO the API caller, aborting the user's page change with a 500.

    Event-sequenced repro: the snapshot's first item spawns the engine's
    prune on another thread and gives it a beat to run. Unserialized, the
    prune deletes a lapsed entry from the dict the snapshot is iterating
    (RuntimeError escapes dismiss_trigger); serialized under the state lock,
    the prune waits, the dismissal persists, and the prune lands after.
    """
    import threading

    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    store = tmp_path / "trigger_dismissals.json"
    svc = TriggerService(dismissals_file=store)

    # A lapsed suppression for the engine's prune to collect (inserted first,
    # so the snapshot yields it before the hook fires)...
    svc._suppressed_until["aa-lapsed"] = T0 - timedelta(seconds=1)
    # ...and the trigger the user is dismissing.
    svc.activate_trigger("stub_plugin", _result("zz-dismissed"))

    prune_threads: list = []

    class RacingSuppressions(dict):
        """items() whose first snapshot fires a concurrent engine prune."""

        fired = False

        def items(self):
            iterator = iter(dict.items(self))

            def gen():
                if not RacingSuppressions.fired and len(self) > 1:
                    RacingSuppressions.fired = True
                    yield next(iterator)
                    prune = threading.Thread(target=svc.clear_expired)
                    prune.start()
                    prune_threads.append(prune)
                    prune.join(timeout=0.2)  # unserialized: completes (mutating us); locked: still waiting
                yield from iterator

            return gen()

    svc._suppressed_until = RacingSuppressions(svc._suppressed_until)

    assert svc.dismiss_trigger("zz-dismissed", suppress=True) is True

    for prune in prune_threads:
        prune.join(timeout=5)
        assert not prune.is_alive()

    data = json.loads(store.read_text(encoding="utf-8"))
    assert "zz-dismissed" in data["dismissals"], "the user's dismissal must be persisted, not lost to the race"
    assert "aa-lapsed" not in svc._suppressed_until  # the prune still landed
