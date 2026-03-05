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

def _build_recommendations(results: dict) -> list[str]:
    """Build actionable troubleshooting recommendations based on diagnostics.

    Examines each check result and returns a list of clear, user-facing steps
    to resolve detected issues.  When everything is healthy the list contains
    a single "all clear" message.

    Args:
        results: The diagnostics dict produced by ``run_full_diagnostics``.

    Returns:
        List of recommendation strings.
    """
    recommendations: list[str] = []

    # --- DNS ---
    dns = results.get("dns", {})
    if not dns.get("ok", False):
        recommendations.append(
            "DNS resolution failed. Your device cannot resolve hostnames. "
            "Check that your network connection is active, your DNS server is "
            "reachable (try 8.8.8.8 or 1.1.1.1), and that no firewall is "
            "blocking outbound DNS (port 53)."
        )

    # --- Internet ---
    internet = results.get("internet", {})
    if not internet.get("ok", False):
        if dns.get("ok", False):
            # DNS works but internet doesn't – likely a routing / firewall issue
            recommendations.append(
                "Internet connectivity failed. DNS works, so your network is "
                "partially up. Verify that your router has an active WAN "
                "connection, check for firewall rules blocking outbound HTTPS "
                "(port 443), and confirm no proxy or captive portal is "
                "interfering."
            )
        else:
            recommendations.append(
                "Internet connectivity failed. This is likely because DNS is "
                "also down — resolve the DNS issue first and internet access "
                "should recover."
            )

    # --- Vestaboard ---
    vb = results.get("vestaboard", {})
    if not vb.get("ok", False):
        mode = vb.get("mode")
        steps = vb.get("steps", {})

        if mode is None:
            # No board configured at all
            recommendations.append(
                "No Vestaboard connection configured. Set BOARD_HOST and "
                "BOARD_LOCAL_API_KEY (for local mode) or BOARD_READ_WRITE_KEY "
                "(for cloud mode) in your environment or .env file, then "
                "restart FiestaBoard."
            )

        elif mode == "local":
            vb_dns = steps.get("dns", {})
            vb_port = steps.get("port", {})
            vb_api = steps.get("api", {})

            if not vb_dns.get("ok", True):
                recommendations.append(
                    f"Cannot resolve Vestaboard hostname "
                    f"'{vb_dns.get('hostname', 'unknown')}'. Verify the board "
                    f"is powered on and connected to your local network. If "
                    f"using a .local hostname, ensure mDNS/Bonjour is working "
                    f"on your network. Alternatively, use the board's IP "
                    f"address directly in BOARD_HOST."
                )
            elif not vb_port.get("ok", True):
                recommendations.append(
                    f"Vestaboard host resolved but port "
                    f"{vb_port.get('port', 7000)} is not reachable. Confirm "
                    f"the board is powered on and the Local API is enabled in "
                    f"the Vestaboard app settings. Check that no firewall is "
                    f"blocking traffic between FiestaBoard and the board on "
                    f"port {vb_port.get('port', 7000)}."
                )
            elif not vb_api.get("ok", True):
                status = vb_api.get("status_code")
                if status == 401 or status == 403:
                    recommendations.append(
                        "Vestaboard is reachable but rejected the API key "
                        "(HTTP 401/403). Double-check that BOARD_LOCAL_API_KEY "
                        "matches the key shown in the Vestaboard app under "
                        "Settings > Local API."
                    )
                elif status is not None:
                    recommendations.append(
                        f"Vestaboard responded with HTTP {status}. The board "
                        f"may be updating or temporarily unavailable. Try "
                        f"power-cycling the board and retrying."
                    )
                else:
                    recommendations.append(
                        "Vestaboard port is open but the API did not respond. "
                        "The board may still be starting up. Wait a moment and "
                        "retry, or power-cycle the board."
                    )

        elif mode == "cloud":
            cloud_api = steps.get("cloud_api", {})
            status = cloud_api.get("status_code")
            if status == 401 or status == 403:
                recommendations.append(
                    "Vestaboard Cloud API rejected your credentials (HTTP "
                    "401/403). Verify BOARD_READ_WRITE_KEY in your .env file "
                    "matches the key from your Vestaboard account at "
                    "https://web.vestaboard.com."
                )
            elif status is not None and status >= 500:
                recommendations.append(
                    "Vestaboard Cloud API returned a server error. This is "
                    "likely a temporary issue on Vestaboard's end. Wait a few "
                    "minutes and try again."
                )
            elif cloud_api.get("error"):
                recommendations.append(
                    "Could not reach the Vestaboard Cloud API "
                    "(rw.vestaboard.com). Verify your internet connection is "
                    "working and no firewall is blocking HTTPS traffic to "
                    "rw.vestaboard.com."
                )
            else:
                recommendations.append(
                    "Vestaboard Cloud API check failed. Verify your "
                    "BOARD_READ_WRITE_KEY and internet connection."
                )

    if not recommendations:
        recommendations.append(
            "All connectivity checks passed. Your Vestaboard connection is "
            "healthy."
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
    results["overall_ok"] = all(
        v.get("ok", False) for v in results.values() if isinstance(v, dict)
    )

    # Actionable troubleshooting recommendations
    results["recommendations"] = _build_recommendations(results)

    return results
