"""Network diagnostics for troubleshooting Vestaboard connectivity.

Provides checks for:
- Local network connectivity (DNS resolution, gateway reachability)
- Internet connectivity (external DNS resolution, HTTPS reachability)
- Vestaboard connectivity (board reachable, API responsive, auth valid)
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
        v.get("ok", False) for k, v in results.items() if k != "overall_ok" and isinstance(v, dict)
    )

    return results
