"""mDNS registration must not hold the startup path (issue #1955).

``zeroconf.register_service()`` blocks until the multicast registration is
accepted or zeroconf's internal event loop gives up. On a network where
multicast is filtered — a container without a usable multicast route, a
segmented office VLAN, a Pi behind a bridge — that wait is the whole of
its timeout, and the API answers nothing until it expires. Measured at
**5.2 s** on this project's own container; ``src/system/mdns.py`` already
carried a comment naming the real-world case ("On slow hardware (e.g.
Raspberry Pi 3) this happens during a busy startup").

Losing ``fiestaboard.local`` is a documented, survivable outcome — the box
is still reachable by IP. Losing five seconds of boot to *discovering*
that is not, so the registration belongs off the startup path.

These tests assert the symptom — how much startup slows down when
registration is slow — rather than the mechanism, so they keep their
meaning if the off-path implementation changes. Each one calibrates
against a fast registration in the same process, so it measures the
mDNS contribution rather than the cost of the rest of the lifespan.
"""

from __future__ import annotations

import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from src.api_server import app

#: Long enough that a blocking implementation cannot hide inside timing
#: noise, short enough to keep the suite quick.
SLOW_SECONDS = 3.0


def _time_lifespan(monkeypatch, registration) -> float:
    """Run the app's full lifespan with *registration* as the mDNS start."""
    monkeypatch.setattr("src.system.mdns.start_mdns", registration)
    started = time.perf_counter()
    with TestClient(app):
        pass
    return time.perf_counter() - started


def test_a_slow_mdns_registration_does_not_hold_startup(monkeypatch):
    baseline = _time_lifespan(monkeypatch, lambda: True)

    entered = threading.Event()
    release = threading.Event()

    def slow_registration() -> bool:
        entered.set()
        release.wait(SLOW_SECONDS)
        return True

    try:
        with_slow = _time_lifespan(monkeypatch, slow_registration)
    finally:
        release.set()

    assert entered.is_set(), "the registration never ran at all"
    added = with_slow - baseline
    assert added < SLOW_SECONDS / 2, (
        f"a {SLOW_SECONDS}s mDNS registration added {added:.2f}s to startup "
        f"({baseline:.2f}s -> {with_slow:.2f}s): startup is waiting for it"
    )


def test_the_local_url_is_announced_once_a_slow_registration_succeeds(monkeypatch):
    """Moving the work off the startup path must not drop the announcement.

    This one passes on the unmodified tree — it is the guard that the fix
    defers the announcement rather than deleting it.
    """
    announced = threading.Event()

    def slow_registration() -> bool:
        time.sleep(0.3)
        return True

    monkeypatch.setattr("src.system.mdns.start_mdns", slow_registration)

    class _Watch(logging.Handler):
        def emit(self, record):
            if "Access FiestaBoard at" in record.getMessage():
                announced.set()

    watcher = _Watch()
    api_logger = logging.getLogger("src.api_server")
    previous_level = api_logger.level
    # The announcement is logged at INFO; the suite's root level is higher,
    # so without this the record is never created and the test would pass
    # or fail for a reason that has nothing to do with mDNS.
    api_logger.setLevel(logging.INFO)
    api_logger.addHandler(watcher)
    try:
        # Stay inside the lifespan while the registration lands, the way a
        # running app does. A registration that only completes after
        # shutdown is deliberately not announced — see
        # ``test_a_registration_that_lands_after_shutdown_is_torn_down``.
        with TestClient(app):
            assert announced.wait(10), (
                "a registration that eventually succeeded never logged the "
                ".local URL: the announcement was dropped, not deferred"
            )
    finally:
        api_logger.removeHandler(watcher)
        api_logger.setLevel(previous_level)


def test_shutdown_while_a_registration_is_still_pending_does_not_raise(monkeypatch):
    """The lifespan may exit before a slow registration has returned."""
    release = threading.Event()

    def never_finishes() -> bool:
        release.wait(SLOW_SECONDS)
        return True

    monkeypatch.setattr("src.system.mdns.start_mdns", never_finishes)
    try:
        with TestClient(app):
            pass  # exits while the registration is still in flight
    finally:
        release.set()


def test_a_registration_that_lands_after_shutdown_is_torn_down(monkeypatch):
    """A late registration must not leave an advertisement up for a dead process."""
    import src.system.mdns as mdns

    gate = threading.Event()
    registered = threading.Event()
    stopped_after_registering = threading.Event()

    def gated_registration() -> bool:
        gate.wait(SLOW_SECONDS * 2)
        registered.set()
        return True

    real_stop = mdns.stop_mdns

    def recording_stop() -> None:
        real_stop()
        if registered.is_set():
            stopped_after_registering.set()

    monkeypatch.setattr("src.system.mdns.start_mdns", gated_registration)
    monkeypatch.setattr("src.system.mdns.stop_mdns", recording_stop)

    with TestClient(app):
        pass  # shut down while the registration is still gated
    gate.set()  # now let it land, after shutdown

    assert stopped_after_registering.wait(SLOW_SECONDS * 2), (
        "a registration that completed after shutdown never tore itself down: "
        "the advertisement outlives the process that owns it"
    )


@pytest.mark.parametrize("outcome", [True, False])
def test_a_registration_that_fails_or_raises_never_reaches_the_caller(monkeypatch, outcome):
    """Neither a False return nor an exception may surface as a boot failure."""

    def registration() -> bool:
        if outcome:
            raise RuntimeError("zeroconf exploded")
        return False

    monkeypatch.setattr("src.system.mdns.start_mdns", registration)
    with TestClient(app):
        pass
