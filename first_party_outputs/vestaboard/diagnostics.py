"""The Vestaboard diagnostics hook: is the board reachable?

FiestaBoard's ``GET /debug/network-diagnostics`` runs its device-agnostic
checks (DNS, internet) and asks the board's output for its own section.
This module layers its checks on FiestaBoard's shared ones (``src.plugins``:
``check_dns_resolution``, ``check_port_reachable``).

- :func:`diagnose` — the board section of ``GET /debug/network-diagnostics``,
  from the saved board dict.
- :func:`check_vestaboard_connection` — the layered check itself: DNS, TCP,
  then the API call (local), or the RW Cloud API call (cloud).
- :func:`advise` — the Vestaboard troubleshooting text for a failed section.

A test steers the shared checks by patching them where this module binds
them (``<package>.diagnostics.check_dns_resolution``).
"""

import logging
import time
from collections.abc import Mapping

import requests

from src.plugins import (
    check_dns_resolution,
    check_port_reachable,
    describe_request_error,
    unconfigured_board_section,
)

from . import transport
from .transport import LOCAL_API_PORT as _LOCAL_API_PORT

logger = logging.getLogger(__name__)

#: Seconds an API check waits for the board's answer.
_HTTP_TIMEOUT = 10

#: The diagnostics summary when every check passed.
ALL_CLEAR_SUMMARY = "All checks passed — your Vestaboard connection is healthy"


def check_vestaboard_connection(
    host: str,
    port: int = _LOCAL_API_PORT,
    api_key: str | None = None,
    use_cloud: bool = False,
    cloud_key: str | None = None,
    timeout: float = _HTTP_TIMEOUT,
) -> dict:
    """Validate connectivity to a Vestaboard.

    Performs a layered check:
    1. DNS resolution of the board host (local API only).
    2. TCP port reachability (local API only).
    3. HTTP API health (GET the message endpoint).

    Args:
        host: Board hostname or IP (for local API).
        port: Board local API port (default 7000).
        api_key: Local API key.
        use_cloud: If True, check the Cloud API instead.
        cloud_key: Cloud Read/Write API key.
        timeout: HTTP timeout in seconds.

    Returns:
        Dict with per-step results and overall ``ok`` bool.
    """
    steps = {}

    if use_cloud:
        # Cloud API check
        # Probe the endpoint sends actually use, so an overridden
        # VESTABOARD_RW_API_URL is what gets diagnosed.
        url = transport.CLOUD_API_URL
        headers = {
            "X-Vestaboard-Read-Write-Key": cloud_key or "",
            "Content-Type": "application/json",
        }
        start = time.time()
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            latency_ms = round((time.time() - start) * 1000)
            api_ok = resp.status_code < 500
            steps["cloud_api"] = {
                "ok": api_ok,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
            }
        except requests.exceptions.RequestException as exc:
            latency_ms = round((time.time() - start) * 1000)
            logger.warning("Vestaboard cloud API check failed: %s", exc)
            steps["cloud_api"] = {
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "error": describe_request_error(exc),
            }

        overall = steps.get("cloud_api", {}).get("ok", False)
        return {"ok": overall, "mode": "cloud", "steps": steps}

    # --- Local API checks ---
    # Step 1: DNS resolution
    dns_result = check_dns_resolution(host)
    steps["dns"] = dns_result
    if not dns_result["ok"]:
        return {"ok": False, "mode": "local", "steps": steps}

    # Step 2: TCP port reachability
    port_result = check_port_reachable(host, port)
    steps["port"] = port_result
    if not port_result["ok"]:
        return {"ok": False, "mode": "local", "steps": steps}

    # Step 3: HTTP API call
    url = f"http://{host}:{port}/local-api/message"
    headers = {
        "X-Vestaboard-Local-Api-Key": api_key or "",
        "Content-Type": "application/json",
    }
    start = time.time()
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        latency_ms = round((time.time() - start) * 1000)
        api_ok = resp.status_code < 500
        steps["api"] = {
            "ok": api_ok,
            "status_code": resp.status_code,
            "latency_ms": latency_ms,
        }
    except requests.exceptions.RequestException as exc:
        latency_ms = round((time.time() - start) * 1000)
        logger.warning("Vestaboard local API check for %s failed: %s", host, exc)
        steps["api"] = {
            "ok": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": describe_request_error(exc),
        }

    overall = all(step.get("ok", False) for step in steps.values())
    return {"ok": overall, "mode": "local", "steps": steps}


def diagnose(board: Mapping) -> dict:
    """The board section of the network diagnostics, for a saved board dict.

    Diagnoses the connection the send path actually uses — the boards[]
    entry's own credentials (issue #1760). A cloud board with a key checks
    the RW Cloud API; otherwise a board with a host checks the Local API;
    otherwise there is nothing to diagnose.
    """
    board_host = board.get("host") or None
    board_port = board.get("port") or _LOCAL_API_PORT
    board_api_key = board.get("local_api_key") or None
    use_cloud = (board.get("api_mode") or "local").lower() == "cloud"
    cloud_key = board.get("cloud_key") or None

    if use_cloud and cloud_key:
        return check_vestaboard_connection(
            host=board_host or "",
            use_cloud=True,
            cloud_key=cloud_key,
        )
    if board_host:
        return check_vestaboard_connection(
            host=board_host,
            port=board_port,
            api_key=board_api_key,
        )
    return unconfigured_board_section()


def advise(vb: Mapping) -> list[dict]:
    """Plain-English troubleshooting for a failed board section.

    Each recommendation is a dict with ``summary`` (a short, non-technical
    headline) and ``steps`` (plain-English actions). A healthy section, or
    one with nothing configured to diagnose, gets none.
    """
    recommendations: list[dict] = []
    if vb.get("ok", False):
        return recommendations

    mode = vb.get("mode")
    steps = vb.get("steps", {})

    if mode == "local":
        vb_dns = steps.get("dns", {})
        vb_port = steps.get("port", {})
        vb_api = steps.get("api", {})

        if not vb_dns.get("ok", True):
            hostname = vb_dns.get("hostname", "your board")
            recommendations.append(
                {
                    "summary": f"FiestaBoard cannot find your Vestaboard ({hostname}) on the network",
                    "steps": [
                        "Make sure your Vestaboard is powered on.",
                        "Make sure both FiestaBoard and the Vestaboard are on the same Wi-Fi network.",
                        "If you're using a name like 'vestaboard.local', try using the board's IP address instead — you can find it on your router's admin page or use FiestaBoard's network scan.",
                        "Restart FiestaBoard after updating the address.",
                    ],
                }
            )
        elif not vb_port.get("ok", True):
            port_num = vb_port.get("port", _LOCAL_API_PORT)
            recommendations.append(
                {
                    "summary": "FiestaBoard found the board's address but cannot connect to it",
                    "steps": [
                        "Make sure the Vestaboard is powered on.",
                        f"Make sure the Local API is enabled on your board (port {port_num}). See https://docs.vestaboard.com/docs/local-api/authentication for details.",
                        "If you recently changed networks, the board's address may have changed — check your router's admin page for the new IP.",
                        "Try restarting the Vestaboard by unplugging it for 10 seconds.",
                    ],
                }
            )
        elif not vb_api.get("ok", True):
            status = vb_api.get("status_code")
            if status == 401 or status == 403:
                recommendations.append(
                    {
                        "summary": "FiestaBoard connected to the Vestaboard but the API key was rejected",
                        "steps": [
                            "Verify your Local API key is correct — it was provided when you enabled the Local API with your enablement token.",
                            "If you need a new key, request an enablement token at https://www.vestaboard.com/local-api and use it to re-enable the Local API.",
                            "Restart FiestaBoard after updating the key.",
                        ],
                    }
                )
            elif status is not None:
                recommendations.append(
                    {
                        "summary": f"The Vestaboard responded with an error (HTTP {status})",
                        "steps": [
                            "Try unplugging the Vestaboard for 10 seconds and plugging it back in.",
                            "Wait about a minute for it to restart, then try again.",
                            "If this keeps happening, the board may need a firmware update — check the Vestaboard app.",
                        ],
                    }
                )
            else:
                recommendations.append(
                    {
                        "summary": "FiestaBoard reached the board but got no response from its API",
                        "steps": [
                            "The board may still be starting up — wait 30 seconds and try again.",
                            "If it still doesn't respond, unplug the board for 10 seconds and plug it back in.",
                        ],
                    }
                )

    elif mode == "cloud":
        cloud_api = steps.get("cloud_api", {})
        status = cloud_api.get("status_code")
        if status == 401 or status == 403:
            recommendations.append(
                {
                    "summary": "The Vestaboard cloud service rejected your API key",
                    "steps": [
                        "Go to https://web.vestaboard.com and sign in to your account.",
                        "Copy your Read/Write API key from the Vestaboard web dashboard.",
                        "Paste it into your FiestaBoard .env file as BOARD_READ_WRITE_KEY.",
                        "Restart FiestaBoard after updating the key.",
                    ],
                }
            )
        elif status is not None and status >= 500:
            recommendations.append(
                {
                    "summary": "The Vestaboard cloud service is temporarily down",
                    "steps": [
                        "This is a problem on Vestaboard's end, not yours.",
                        "Wait a few minutes and try again.",
                        "If the problem continues, check https://twitter.com/vestaboard or https://vestaboard.com for service updates.",
                    ],
                }
            )
        elif cloud_api.get("error"):
            recommendations.append(
                {
                    "summary": "FiestaBoard cannot reach the Vestaboard cloud service",
                    "steps": [
                        "Make sure the device running FiestaBoard has a working internet connection.",
                        "Try opening https://rw.vestaboard.com in a browser on the same device.",
                        "If you use a VPN or corporate network, make sure it allows connections to rw.vestaboard.com.",
                    ],
                }
            )
        else:
            recommendations.append(
                {
                    "summary": "Vestaboard cloud connection check failed",
                    "steps": [
                        "Double-check your BOARD_READ_WRITE_KEY in the .env file.",
                        "Make sure your internet connection is working.",
                        "Restart FiestaBoard and try again.",
                    ],
                }
            )

    # mode None: nothing configured to diagnose — no recommendation (the
    # overall verdict is already False).
    return recommendations
