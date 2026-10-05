"""Network diagnostics for troubleshooting board connectivity.

Provides checks for:
- Local network connectivity (DNS resolution, gateway reachability)
- Internet connectivity (external DNS resolution, HTTPS reachability)
- The board — asked of the board's **output** through its diagnostics hook
  (:class:`src.outputs.hooks.OutputDiagnostics`); the Vestaboard check lives
  in ``src/outputs/vestaboard/diagnostics.py``.

Each check returns actionable troubleshooting recommendations when it fails,
so users can quickly identify and resolve connectivity issues.
"""

from __future__ import annotations

import logging
import socket
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from src.outputs.hooks import OutputDiagnostics

logger = logging.getLogger(__name__)

# Timeouts for diagnostic checks (seconds)
_DNS_TIMEOUT = 5
_CONNECT_TIMEOUT = 5
_HTTP_TIMEOUT = 10

#: The response key the board section is served under. It predates outputs
#: and stays for every output (``NetworkDiagnosticsResponse.vestaboard``,
#: plan D8: public API shapes unchanged).
BOARD_SECTION = "vestaboard"


def _describe_socket_error(exc: OSError) -> str:
    """Classify a socket-level failure into a static, user-facing message.

    The diagnostics dict is returned verbatim to the browser, so error text
    must never echo the raw exception (CodeQL py/stack-trace-exposure) — the
    full detail is logged server-side at each call site instead.
    """
    if isinstance(exc, socket.gaierror):
        return "DNS lookup failed"
    if isinstance(exc, TimeoutError):
        return "Connection timed out"
    if isinstance(exc, ConnectionRefusedError):
        return "Connection refused"
    return "Connection failed"


def _describe_request_error(exc: requests.exceptions.RequestException) -> str:
    """Classify a requests-level failure into a static, user-facing message."""
    if isinstance(exc, requests.exceptions.SSLError):
        return "SSL/TLS error"
    if isinstance(exc, requests.exceptions.Timeout):
        return "Connection timed out"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Could not connect"
    return "Request failed"


def check_dns_resolution(hostname: str = "google.com", timeout: float = _DNS_TIMEOUT) -> dict:
    """Check if DNS resolution is working.

    Args:
        hostname: Hostname to resolve.
        timeout: Socket timeout in seconds.

    Returns:
        Dict with ``ok`` bool, resolved ``ip`` (if successful), and ``error`` (if failed).
    """
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        ip = socket.gethostbyname(hostname)
        return {"ok": True, "hostname": hostname, "ip": ip}
    except socket.gaierror as exc:
        logger.warning("DNS resolution for %s failed: %s", hostname, exc)
        return {"ok": False, "hostname": hostname, "ip": None, "error": "DNS lookup failed"}
    except Exception as exc:
        logger.warning("DNS check for %s failed: %s", hostname, exc)
        return {"ok": False, "hostname": hostname, "ip": None, "error": "DNS check failed"}
    finally:
        socket.setdefaulttimeout(old_timeout)


def check_internet_connectivity(
    url: str = "https://www.google.com",
    timeout: float = _HTTP_TIMEOUT,
) -> dict:
    """Check that we can reach an external HTTPS endpoint.

    Args:
        url: URL to test.
        timeout: Request timeout in seconds.

    Returns:
        Dict with ``ok`` bool, ``status_code``, ``latency_ms``, and ``error``.
    """
    start = time.time()
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        latency_ms = round((time.time() - start) * 1000)
        return {
            "ok": response.status_code < 400,
            "url": url,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        }
    except requests.exceptions.RequestException as exc:
        latency_ms = round((time.time() - start) * 1000)
        logger.warning("Internet connectivity check against %s failed: %s", url, exc)
        return {
            "ok": False,
            "url": url,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": _describe_request_error(exc),
        }


def check_port_reachable(host: str, port: int, timeout: float = _CONNECT_TIMEOUT) -> dict:
    """Check whether a TCP port on a host is reachable.

    Args:
        host: IP address or hostname.
        port: TCP port number.
        timeout: Connection timeout in seconds.

    Returns:
        Dict with ``ok`` bool, ``latency_ms``, and ``error``.
    """
    start = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        latency_ms = round((time.time() - start) * 1000)
        return {"ok": True, "host": host, "port": port, "latency_ms": latency_ms}
    except OSError as exc:
        latency_ms = round((time.time() - start) * 1000)
        logger.warning("Port check for %s:%s failed: %s", host, port, exc)
        return {"ok": False, "host": host, "port": port, "latency_ms": latency_ms, "error": _describe_socket_error(exc)}


def unconfigured_board_section() -> dict:
    """The board section when there is no board connection to diagnose.

    Answered for an install with no board, a board with no credentials, and
    a board whose output declares no diagnostics hook (a FiestaPanel).
    """
    return {
        "ok": False,
        "mode": None,
        "steps": {},
        "error": "No board host or cloud key configured",
    }


# ---------------------------------------------------------------------------
# Troubleshooting recommendations
# ---------------------------------------------------------------------------


def _build_recommendations(results: dict, board_diagnostics: OutputDiagnostics | None = None) -> list[dict]:
    """Build user-friendly troubleshooting recommendations based on diagnostics.

    Each recommendation is a dict with:
    - ``summary``: A short, non-technical headline (e.g. "Your board can't be found
      on the network").
    - ``steps``: A list of plain-English actions the user can take to fix the issue.

    Core advises on its own checks (DNS, internet); the board section's
    advice comes from the board's output (*board_diagnostics*'s ``advise``).
    When everything is healthy the list contains a single "all clear" entry,
    worded by the output.

    Args:
        results: The diagnostics dict produced by ``run_full_diagnostics``.
        board_diagnostics: The board's output's diagnostics hook, if any.

    Returns:
        List of recommendation dicts.
    """
    recommendations: list[dict] = []

    # --- DNS ---
    dns = results.get("dns", {})
    if not dns.get("ok", False):
        recommendations.append(
            {
                "summary": "FiestaBoard cannot look up addresses on the internet",
                "steps": [
                    "Make sure the device running FiestaBoard is connected to your Wi-Fi or ethernet.",
                    "Restart your router or modem.",
                    "If the problem persists, try setting your DNS server to 8.8.8.8 or 1.1.1.1 in your router settings.",
                ],
            }
        )

    # --- Internet ---
    internet = results.get("internet", {})
    if not internet.get("ok", False):
        if dns.get("ok", False):
            # DNS works but internet doesn't
            recommendations.append(
                {
                    "summary": "FiestaBoard can look up addresses but cannot reach the internet",
                    "steps": [
                        "Check that your router is online and has an active internet connection.",
                        "Try opening a website on another device connected to the same network.",
                        "If other devices work, restart the device running FiestaBoard.",
                        "If you use a VPN or corporate network, make sure it allows outbound HTTPS traffic.",
                    ],
                }
            )
        else:
            recommendations.append(
                {
                    "summary": "No internet connection detected",
                    "steps": [
                        "This is most likely caused by the DNS issue above — fix that first and internet access should come back.",
                    ],
                }
            )

    # --- The board (its output's own advice) ---
    if board_diagnostics is not None:
        recommendations.extend(board_diagnostics.advise(results.get(BOARD_SECTION, {})))

    if not recommendations and board_diagnostics is not None:
        # Check if everything truly passed. (Without a diagnostics hook the
        # board section is the unconfigured placeholder, never ok.)
        overall = all(v.get("ok", False) for v in results.values() if isinstance(v, dict))
        if overall:
            recommendations.append(
                {
                    "summary": board_diagnostics.all_clear,
                    "steps": [],
                }
            )

    return recommendations


def run_full_diagnostics(board: Mapping | None = None) -> dict:
    """Run a comprehensive set of network diagnostics.

    Checks performed:
    1. DNS resolution (can we resolve external hostnames?).
    2. Internet connectivity (can we reach the outside world?).
    3. The board (can we talk to it?) — asked of the board's output through
       its diagnostics hook; an output without one, or no board, reports
       the unconfigured placeholder.

    The result includes a ``recommendations`` list with plain-English
    troubleshooting steps for every issue detected.

    Args:
        board: The saved board dict to diagnose (the primary board), or
            ``None`` when there is none.

    Returns:
        Dict keyed by check name with results for each.
    """
    from src.outputs.registry import diagnostics_for

    board = board or {}
    results: dict = {}

    # 1. DNS check
    results["dns"] = check_dns_resolution()

    # 2. Internet connectivity
    results["internet"] = check_internet_connectivity()

    # 3. The board, through its output
    board_diagnostics = diagnostics_for(board)
    results[BOARD_SECTION] = (
        board_diagnostics.run(board) if board_diagnostics is not None else unconfigured_board_section()
    )

    # Overall status
    results["overall_ok"] = all(v.get("ok", False) for v in results.values() if isinstance(v, dict))

    # Actionable troubleshooting recommendations
    results["recommendations"] = _build_recommendations(results, board_diagnostics)

    return results
