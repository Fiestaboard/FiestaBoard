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


# ═══════════════════════════════════════════════════════════════════════════
# A failed store write surfaces (Phase 2 audit: the fourth swallowing persist
# path). Phase 2 Task 10 closed three — src/settings/service.py::_save_to_file
# re-raises, the backup service aborts before overwriting, the SSRF 400 stopped
# being downgraded to 200 — and this one was introduced alongside them: it
# logged an error and returned, so a dismissal the user made was reported as
# successful while being silently non-durable.
#
# It is NOT deliberate. The in-memory suppression does hold for the life of the
# process, so the failure is invisible until a restart brings the dismissed
# trigger back and overrides the user's page again — which is exactly the bug
# persistence was added to fix (#1850). Nothing logged an ERROR the user could
# see, and the API answered 200.
#
# The one deliberate exception is kept and pinned below: the startup prune,
# which carries no user decision.
# ═══════════════════════════════════════════════════════════════════════════


def _break_store_writes(monkeypatch):
    """Make every dismissal-store write fail the way a full/read-only disk does."""
    import src.triggers.service as trigger_service_module

    def boom(*args, **kwargs):
        raise OSError("[Errno 28] No space left on device")

    monkeypatch.setattr(trigger_service_module, "write_json_atomic", boom)


def test_a_suppressed_dismissal_that_cannot_be_persisted_surfaces_to_the_caller(monkeypatch, tmp_path):
    import pytest

    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    svc = TriggerService(dismissals_file=tmp_path / "trigger_dismissals.json")
    svc.activate_trigger("stub_plugin", _result())

    _break_store_writes(monkeypatch)

    with pytest.raises(OSError):
        svc.dismiss_trigger("door-open", suppress=True)


def test_a_failed_store_write_still_leaves_the_dismissal_fully_applied_in_memory(monkeypatch, tmp_path):
    """A raise must mean "not durable", never "half-applied".

    If the trigger were left in ``_active_triggers`` the board would keep
    showing the thing the user just dismissed.
    """
    import pytest

    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    svc = TriggerService(dismissals_file=tmp_path / "trigger_dismissals.json")
    svc.activate_trigger("stub_plugin", _result())

    _break_store_writes(monkeypatch)
    with pytest.raises(OSError):
        svc.dismiss_trigger("door-open", suppress=True)

    assert svc.get_active_trigger() is None, "the dismissed trigger is still on the board"
    svc.activate_trigger("stub_plugin", _result())  # plugin re-emits
    assert svc.get_active_trigger() is None, "the suppression was not applied in memory"


def test_a_user_override_that_cannot_be_persisted_surfaces_to_the_caller(monkeypatch, tmp_path):
    """The page-change path (``POST /settings/active-page``).

    Propagating is also the consistent answer here: the statement right after
    ``dismiss_active_for_user_override()`` writes ``settings.json`` into the
    same data directory, so a dismissal-store write that fails predicts a page
    change that cannot be persisted either. Swallowing only moved the error one
    line later — or, when settings.json happened to be writable, left the user
    with a page change a restart silently undoes.
    """
    import pytest

    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    svc = TriggerService(dismissals_file=tmp_path / "trigger_dismissals.json")
    svc.activate_trigger("stub_plugin", _result())

    _break_store_writes(monkeypatch)

    with pytest.raises(OSError):
        svc.dismiss_active_for_user_override()


def test_clear_all_that_cannot_be_persisted_surfaces_to_the_caller(monkeypatch, tmp_path):
    import pytest

    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    store = tmp_path / "trigger_dismissals.json"
    svc = TriggerService(dismissals_file=store)
    svc.activate_trigger("stub_plugin", _result())
    svc.dismiss_trigger("door-open", suppress=True)
    assert store.exists()

    _break_store_writes(monkeypatch)

    with pytest.raises(OSError):
        svc.clear_all()


def test_the_startup_prune_is_the_one_deliberate_best_effort_write(monkeypatch, tmp_path):
    """Documented exception: the prune in ``_load_dismissals``.

    It rewrites the store without entries that had already lapsed — no user
    decision is being recorded, the in-memory state is already correct, and the
    caller is ``__init__``. Refusing to construct the service (and so taking
    the whole app down on boot) over a cosmetic rewrite would be strictly
    worse. Every write that carries a user decision raises; this one does not.
    """
    clock = FakeClock(T0)
    install_fake_time_service(monkeypatch, clock)
    store = tmp_path / "trigger_dismissals.json"
    store.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dismissals": {
                    "lapsed": {
                        "suppressed_until": (T0 - timedelta(seconds=1)).isoformat(),
                        "dismissed_at": (T0 - timedelta(hours=2)).isoformat(),
                    },
                    "live": {
                        "suppressed_until": (T0 + timedelta(hours=1)).isoformat(),
                        "dismissed_at": T0.isoformat(),
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    _break_store_writes(monkeypatch)

    svc = TriggerService(dismissals_file=store)  # must not raise

    assert "live" in svc._suppressed_until
    assert "lapsed" not in svc._suppressed_until


def test_the_default_store_path_honors_the_data_dir_seam(monkeypatch, tmp_path):
    """#1762: the dismissal store was the last one resolving ``<repo>/data``
    with its own ``Path(__file__)`` walk, so the suite wrote the checkout."""
    from pathlib import Path

    import src.triggers.service as trigger_service_module
    from src.paths import get_data_dir

    repo_root = Path(trigger_service_module.__file__).resolve().parent.parent.parent
    monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(tmp_path / "isolated-data"))

    resolved = Path(trigger_service_module._default_dismissals_file()).resolve()

    assert not resolved.is_relative_to(repo_root / "data"), f"leaked into the repo data/: {resolved}"
    assert resolved.is_relative_to(get_data_dir().resolve())
