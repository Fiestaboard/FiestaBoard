"""Network diagnostics for troubleshooting Vestaboard connectivity.

Provides checks for:
- Local network connectivity (DNS resolution, gateway reachability)
- Internet connectivity (external DNS resolution, HTTPS reachability)
- Vestaboard connectivity (board reachable, API responsive, auth valid)

Each check returns actionable troubleshooting recommendations when it fails,
so users can quickly identify and resolve connectivity issues.
"""

import logging
import socket
import time

import requests

logger = logging.getLogger(__name__)

# Timeouts for diagnostic checks (seconds)
_DNS_TIMEOUT = 5
_CONNECT_TIMEOUT = 5
_HTTP_TIMEOUT = 10


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
        return {"ok": False, "hostname": hostname, "ip": None, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "hostname": hostname, "ip": None, "error": str(exc)}
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
        return {
            "ok": False,
            "url": url,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": str(exc),
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
        return {"ok": False, "host": host, "port": port, "latency_ms": latency_ms, "error": str(exc)}


def check_vestaboard_connection(
    host: str,
    port: int = 7000,
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
        url = "https://rw.vestaboard.com/"
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
            steps["cloud_api"] = {
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "error": str(exc),
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
        steps["api"] = {
            "ok": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": str(exc),
        }

    overall = all(step.get("ok", False) for step in steps.values())
    return {"ok": overall, "mode": "local", "steps": steps}


# ---------------------------------------------------------------------------
# Troubleshooting recommendations
# ---------------------------------------------------------------------------


def _build_recommendations(results: dict) -> list[dict]:
    """Build user-friendly troubleshooting recommendations based on diagnostics.

    Each recommendation is a dict with:
    - ``summary``: A short, non-technical headline (e.g. "Your board can't be found
      on the network").
    - ``steps``: A list of plain-English actions the user can take to fix the issue.

    When everything is healthy the list contains a single "all clear" entry.

    Args:
        results: The diagnostics dict produced by ``run_full_diagnostics``.

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

    # --- Vestaboard ---
    vb = results.get("vestaboard", {})
    if not vb.get("ok", False):
        mode = vb.get("mode")
        steps = vb.get("steps", {})

        if mode is None:
            # No board configured — still helpful to tell user what to do
            pass  # Handled by overall_ok being False; no extra recommendation

        elif mode == "local":
            vb_dns = steps.get("dns", {})
            vb_port = steps.get("port", {})
            vb_api = steps.get("api", {})

            if not vb_dns.get("ok", True):
                hostname = vb_dns.get("hostname", "your board")
                recommendations.append(
                    {
                        "summary": f"FiestaBoard cannot find your Vestaboard ({hostname}) on the network",
                        "steps": [
                            "Make sure your Vestaboard is powered on (look for the LED on the back).",
                            "Make sure both FiestaBoard and the Vestaboard are on the same Wi-Fi network.",
                            "If you're using a name like 'vestaboard.local', try using the board's IP address instead — you can find it on your router's admin page or use FiestaBoard's network scan.",
                            "Restart FiestaBoard after updating the address.",
                        ],
                    }
                )
            elif not vb_port.get("ok", True):
                port_num = vb_port.get("port", 7000)
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

    if not recommendations:
        # Check if everything truly passed
        overall = all(v.get("ok", False) for v in results.values() if isinstance(v, dict))
        if overall:
            recommendations.append(
                {
                    "summary": "All checks passed — your Vestaboard connection is healthy",
                    "steps": [],
                }
            )

    return recommendations


def run_full_diagnostics(
    board_host: str | None = None,
    board_port: int = 7000,
    board_api_key: str | None = None,
    use_cloud: bool = False,
    cloud_key: str | None = None,
) -> dict:
    """Run a comprehensive set of network diagnostics.

    Checks performed:
    1. DNS resolution (can we resolve external hostnames?).
    2. Internet connectivity (can we reach the outside world?).
    3. Vestaboard connectivity (can we talk to the board?).

    The result includes a ``recommendations`` list with plain-English
    troubleshooting steps for every issue detected.

    Args:
        board_host: Vestaboard hostname/IP (for local API).
        board_port: Vestaboard local API port.
        board_api_key: Local API key.
        use_cloud: Whether to check cloud API.
        cloud_key: Cloud Read/Write API key.

    Returns:
        Dict keyed by check name with results for each.
    """
    results: dict = {}

    # 1. DNS check
    results["dns"] = check_dns_resolution()

    # 2. Internet connectivity
    results["internet"] = check_internet_connectivity()

    # 3. Vestaboard connectivity (only if board info provided)
    if use_cloud and cloud_key:
        results["vestaboard"] = check_vestaboard_connection(
            host=board_host or "",
            use_cloud=True,
            cloud_key=cloud_key,
        )
    elif board_host:
        results["vestaboard"] = check_vestaboard_connection(
            host=board_host,
            port=board_port,
            api_key=board_api_key,
        )
    else:
        results["vestaboard"] = {
            "ok": False,
            "mode": None,
            "steps": {},
            "error": "No board host or cloud key configured",
        }

    # Overall status
    results["overall_ok"] = all(v.get("ok", False) for v in results.values() if isinstance(v, dict))

    # Actionable troubleshooting recommendations
    results["recommendations"] = _build_recommendations(results)

    return results
