"""The per-test singleton reset must also stop the threads that rewrite them.

``tests/conftest.py``'s autouse ``_isolated_data_dir`` drops every cached
service between tests. Dropping the *reference* is not the whole job: a
``DisplayService`` that reached ``initialize()`` owns a daemon
``board-state-poll`` thread, and that thread keeps re-entering
``get_settings_service()`` — which, with the singleton just nulled, builds a
fresh ``SettingsService`` and stores it in the process global, then builds a
fresh default-path ``ConfigManager`` through
``SettingsService.__init__`` -> ``_load_transition_settings`` ->
``Config._get_board()``.

Under ``pytest -n auto`` that lands in whichever test the worker is running 30
seconds later, which is how ``test_transitions_contract``,
``test_silence_per_board_composition`` and ``test_tick_shared_context``
failed on CI at SHAs containing none of their changes.

These tests pin the reset, not the symptom: after ``_drop_all_singletons()``
the poll thread is gone and the globals it used to rewrite stay dropped.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import src.display_runtime as display_runtime
import src.settings.service as settings_service_module
from src.main import DisplayService
from tests.conftest import _drop_all_singletons


def _service_with_a_hot_poll_thread(monkeypatch) -> tuple[DisplayService, threading.Event]:
    """A real ``DisplayService`` running the real ``_board_poll_loop``.

    Only the poll *interval* is shortened — from the 30s production default to
    1ms — so the loop's re-entry into ``get_settings_service()`` (which is what
    leaks) happens on a test's timescale instead of a CI worker's. The loop
    body, the accessor it calls and the global it writes are all the real ones.
    """
    entered = threading.Event()
    service = DisplayService()

    real_interval = DisplayService._get_board_read_interval

    def fast_interval(self):
        entered.set()
        real_interval(self)  # the real accessor: get_settings_service()
        return 0.001

    monkeypatch.setattr(DisplayService, "_get_board_read_interval", fast_interval)
    service._poll_thread = threading.Thread(target=service._board_poll_loop, daemon=True, name="board-state-poll")
    service._poll_thread.start()
    assert entered.wait(5), "the poll loop never ran; the fixture is not exercising it"
    return service, entered


def test_dropping_the_display_service_singleton_stops_its_board_poll_thread(monkeypatch):
    service, _ = _service_with_a_hot_poll_thread(monkeypatch)
    display_runtime._service = service

    _drop_all_singletons()

    service._poll_thread.join(timeout=5)
    assert not service._poll_thread.is_alive(), (
        "board-state-poll outlived the singleton reset; it will rebuild "
        "get_settings_service()/ConfigManager inside a later test"
    )


def test_a_dropped_services_poll_thread_stops_rebuilding_the_settings_singleton(monkeypatch):
    """The observable dirt: the settings global does not come back by itself."""
    service, _ = _service_with_a_hot_poll_thread(monkeypatch)
    display_runtime._service = service

    _drop_all_singletons()

    # Join before clearing, rather than allowing a fixed grace period for a
    # construction already in flight. A 50ms grace outran the poll thread on an
    # unloaded machine and lost to it on a loaded xdist worker, which made this
    # test flake in CI twice — and sleeping longer would make the race rarer,
    # not absent. Once the thread has exited nothing can reassign the global,
    # so the observation below is deterministic.
    #
    # This also sharpens the failure: revert the conftest fix and the join times
    # out here, naming the live thread, instead of surfacing as a mystery
    # reassignment 250ms later.
    service._poll_thread.join(timeout=5)
    assert not service._poll_thread.is_alive(), (
        "board-state-poll outlived the singleton reset, so it can still rebuild the settings global inside a later test"
    )
    settings_service_module._settings_service = None

    # Long enough for a 1ms-interval loop to have rebuilt it a hundred times.
    time.sleep(0.25)

    assert settings_service_module._settings_service is None, (
        "a dropped service's poll thread reconstructed the settings singleton "
        "after the reset; whatever test is running now sees a service it never "
        "configured"
    )


def test_a_log_record_during_time_service_construction_does_not_recurse(monkeypatch):
    """The third CI shape: an unraisable RecursionError charged to a bystander.

    ``Config.GENERAL_TIMEZONE`` is ``""`` whenever ``general.timezone`` is
    unset — which every stub config manager in the suite leaves it — and
    ``TimeService.__init__`` logs a warning for a timezone it cannot resolve.
    ``src.log_store``'s handler timestamps that warning by calling
    ``get_time_service()``, which, with the singleton still unassigned, started
    construction over, warned again, and recursed to the interpreter's limit.

    ``LogBufferHandler.emit`` swallows the ``RecursionError``, so the count of
    constructions — not an exception — is what makes this test fail without the
    guard. On CI the same recursion escaped on a background thread and failed
    ``tests/test_tick_shared_context.py::TestSilenceWindowCache::
    test_sixty_probes_at_idle_parse_the_window_once`` with ``RuntimeError:
    Failed to process unraisable exception``, a test that never touches the
    time service.
    """
    import logging

    import src.time_service as time_service_module
    from src.log_store import LogBufferHandler

    config_manager = MagicMock()
    config_manager.get_general.return_value = {}  # no "timezone" key -> ""
    monkeypatch.setattr("src.config.get_config_manager", lambda: config_manager)
    monkeypatch.setattr("src.config_manager.get_config_manager", lambda: config_manager)
    time_service_module.reset_time_service()

    constructions: list[str] = []
    real_init = time_service_module.TimeService.__init__

    def counting_init(self, default_timezone="America/Los_Angeles"):
        constructions.append(default_timezone)
        real_init(self, default_timezone=default_timezone)

    monkeypatch.setattr(time_service_module.TimeService, "__init__", counting_init)

    handler = LogBufferHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        # Non-vacuity: the timezone really is unresolvable, so __init__ really
        # does log while the singleton is still unassigned.
        assert time_service_module._get_configured_timezone() == ""
        service = time_service_module.get_time_service()
    finally:
        root.removeHandler(handler)

    assert service is time_service_module._time_service
    # The configured (empty) timezone, plus at most the one-off UTC bootstrap
    # handed to the re-entrant log record.
    assert len(constructions) <= 2, f"get_time_service() re-entered its own construction {len(constructions)} times"
