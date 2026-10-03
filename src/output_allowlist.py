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
        logger.warning("Refused board request to %r: not in %s (%s)", host, ENV_VAR, ", ".join(sorted(allowed)))
        raise OutputHostBlocked(host)


def check_output_url(url: str) -> None:
    """:func:`check_output_host` for the host part of *url*."""
    check_output_host(urlparse(url).hostname)
