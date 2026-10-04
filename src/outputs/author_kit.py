"""Helpers an output plugin may use, re-exported from :mod:`src.plugins`.

Part of the output-plugin author API (versioned with ``output_api``): what
the first-party outputs needed from core once they became self-contained
packages (plan Phase 4), offered to every output on the same terms.

- **Host guards** for a device address the user typed:
  :func:`validate_board_host` (a bare IPv4 address or hostname: no scheme,
  port, path or credentials) and :func:`validate_board_host_is_local_network`
  (it resolves only to private, loopback or link-local IPv4 addresses).
  Both raise an HTTP 400 the route returns as is. :func:`check_output_host`
  applies ``FIESTABOARD_OUTPUTS_ALLOW_HOSTS`` to a bare host (``self.http``
  applies it to every URL itself).
- **Network checks** for an output's diagnostics section:
  :func:`check_dns_resolution`, :func:`check_port_reachable`,
  :func:`describe_request_error` and :func:`unconfigured_board_section` —
  the same checks, with the same result shapes, core's own diagnostics run.
- :func:`local_ipv4` — this host's LAN address, for a ``discover`` hook that
  scans the local subnet.
- :func:`text_to_board_array` — text to a rows × cols grid of character
  codes, laid out exactly as core lays out a page.

Every helper looks its implementation up when called, so this module
imports nothing heavy, and a test that patches the implementation where it
lives steers the plugin too.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "check_dns_resolution",
    "check_output_host",
    "check_port_reachable",
    "describe_request_error",
    "local_ipv4",
    "text_to_board_array",
    "unconfigured_board_section",
    "validate_board_host",
    "validate_board_host_is_local_network",
]


def validate_board_host(host: str) -> None:
    """Refuse (HTTP 400) anything but a bare IPv4 address or hostname."""
    from src import board_guards

    board_guards.validate_board_host(host)


def validate_board_host_is_local_network(host: str) -> None:
    """Refuse (HTTP 400) a host that resolves outside private/loopback/link-local IPv4."""
    from src import board_guards

    board_guards.validate_board_host_is_local_network(host)


def check_output_host(host: str | None) -> None:
    """Raise :class:`~src.output_allowlist.OutputHostBlocked` unless *host*
    may receive device traffic (``FIESTABOARD_OUTPUTS_ALLOW_HOSTS``)."""
    from src import output_allowlist

    output_allowlist.check_output_host(host)


def check_dns_resolution(hostname: str, *args: Any, **kwargs: Any) -> dict:
    """``{"ok", "hostname", ...}`` for one DNS lookup (``timeout`` optional)."""
    from src import network_diagnostics

    return network_diagnostics.check_dns_resolution(hostname, *args, **kwargs)


def check_port_reachable(host: str, port: int, *args: Any, **kwargs: Any) -> dict:
    """``{"ok", "host", "port", ...}`` for one TCP connect (``timeout`` optional)."""
    from src import network_diagnostics

    return network_diagnostics.check_port_reachable(host, port, *args, **kwargs)


def describe_request_error(exc: Any) -> str:
    """A plain-English description of a ``requests`` exception."""
    from src import network_diagnostics

    return network_diagnostics._describe_request_error(exc)


def unconfigured_board_section() -> dict:
    """The diagnostics section of a board with nothing configured to check."""
    from src import network_diagnostics

    return network_diagnostics.unconfigured_board_section()


def local_ipv4() -> str:
    """This host's best-guess LAN IPv4 address (``127.0.0.1`` when unknown)."""
    from src.system import mdns

    return mdns.local_ipv4()


def text_to_board_array(text: str, rows: int, cols: int) -> list[list[int]]:
    """*text* laid out as a ``rows`` × ``cols`` grid of character codes."""
    from src import text_to_board

    return text_to_board.text_to_board_array(text, rows=rows, cols=cols)
