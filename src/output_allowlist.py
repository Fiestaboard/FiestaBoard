"""FIESTABOARD_OUTPUTS_ALLOW_HOSTS: a runtime fence on board traffic.

When the variable is set to a comma-separated list of hosts, the app refuses
every board request — sends, reads, connection tests, local-API enablement —
to a host outside the list. The dev stack sets it to the bundled mock board
and mock cloud, so a developer's ``settings.json`` that still points at a
real Vestaboard cannot reach it while they work on something else. Unset or
blank (production), every host is allowed, exactly as before.

The variable is read on every check rather than cached, so a test or an
operator can change it without restarting anything.

A refusal raises :class:`OutputHostBlocked`, a ``requests`` ``ConnectionError``:
every board call site already treats that as "the board is unreachable", so
a fenced board degrades the way an unplugged one does instead of crashing.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

ENV_VAR = "FIESTABOARD_OUTPUTS_ALLOW_HOSTS"


class OutputHostBlocked(requests.exceptions.ConnectionError):
    """A board request was refused because its host is not allow-listed."""

    def __init__(self, host: str | None) -> None:
        super().__init__(f"{host!r} is not in {ENV_VAR}")
        self.host = host


def _allowed_hosts() -> frozenset[str] | None:
    """The allow-listed hosts, lowercased, or ``None`` when every host is allowed."""
    raw = os.environ.get(ENV_VAR, "")
    hosts = frozenset(h.strip().lower() for h in raw.split(",") if h.strip())
    return hosts or None


def check_output_host(host: str | None) -> None:
    """Raise :class:`OutputHostBlocked` unless *host* may receive board traffic."""
    allowed = _allowed_hosts()
    if allowed is None:
        return
    if (host or "").strip().lower() not in allowed:
        _log_refusal(host, allowed)
        raise OutputHostBlocked(host)


# --- the refusal log -------------------------------------------------------------------------
#
# A discovery sweep asks every address of a /24 (254 hosts, from a thread
# pool): one warning per refused host buried the log under a thousand lines
# in the output-plugins POC. The first refusal of a burst is a warning; the
# rest within REFUSAL_WINDOW_S are counted (debug), and the count is one
# summary warning — when the next burst starts, or when an action ends
# (:func:`flush_refusal_summary`).

REFUSAL_WINDOW_S = 30.0

_refusals_lock = threading.Lock()
_window_started: float | None = None
_suppressed = 0


def _summary(count: int) -> None:
    logger.warning("Refused %d more board requests: their hosts are not in %s", count, ENV_VAR)


def _log_refusal(host: str | None, allowed: frozenset[str]) -> None:
    global _window_started, _suppressed
    now = time.monotonic()
    with _refusals_lock:
        opens = _window_started is None or now - _window_started >= REFUSAL_WINDOW_S
        if opens:
            pending, _suppressed, _window_started = _suppressed, 0, now
        else:
            _suppressed += 1
    message = "Refused board request to %r: not in %s (%s)"
    args = (host, ENV_VAR, ", ".join(sorted(allowed)))
    if not opens:
        logger.debug(message, *args)
        return
    if pending:
        _summary(pending)
    logger.warning(message, *args)


def flush_refusal_summary() -> None:
    """Log how many refusals the current burst counted (if any) and close it."""
    global _window_started, _suppressed
    with _refusals_lock:
        pending, _suppressed, _window_started = _suppressed, 0, None
    if pending:
        _summary(pending)


def check_output_url(url: str) -> None:
    """:func:`check_output_host` for the host part of *url*."""
    check_output_host(urlparse(url).hostname)
