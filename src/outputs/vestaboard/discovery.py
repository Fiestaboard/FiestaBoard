"""The ``vestaboard`` output's ``discover`` hook: find Vestaboards on the LAN.

Moved whole from ``src/system/mdns.py`` (which keeps FiestaBoard's own mDNS
advertisement and the local-IP helper this module uses). ``POST
/config/board/scan`` delegates here through
:func:`src.outputs.registry.discover_devices`.
"""

import logging
import socket
import threading
from typing import Any

from src.system import mdns as _mdns

logger = logging.getLogger(__name__)

_VESTABOARD_LOCAL_API_PORT = 7000

# mDNS service types to browse when looking for Vestaboards
_BROWSE_SERVICE_TYPES = [
    "_vestaboard._tcp.local.",
    "_http._tcp.local.",
]


def _probe_vestaboard_port(ip: str, port: int = _VESTABOARD_LOCAL_API_PORT, timeout: float = 0.5) -> bool:
    """Return True if *ip*:*port* accepts a TCP connection."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, port))
            return True
    except (TimeoutError, OSError):
        return False


def discover(timeout: float = 4.0) -> list[dict[str, Any]]:
    """Scan the local network for Vestaboard devices.

    Uses two complementary strategies:
    1. **mDNS browse** – listens for ``_vestaboard._tcp`` and ``_http._tcp``
       service advertisements.  Any service whose name contains "vestaboard"
       (case-insensitive) or that has port 7000 is included.
    2. **Subnet port probe** – iterates over the /24 subnet of this host and
       checks whether port 7000 (Vestaboard Local API) is open.

    Args:
        timeout: How long (seconds) to wait for mDNS responses and port
            probes.  The mDNS browse phase uses the full *timeout*; the
            port-probe phase uses a 0.5 s connect timeout per host.

    Returns:
        A list of dicts, each with at least ``ip`` and ``port`` keys plus
        optional ``hostname`` and ``source`` fields.
    """
    seen_ips: set = set()
    results: list[dict[str, Any]] = []

    # -- Phase 1: mDNS browse ------------------------------------------------
    try:
        import time

        from zeroconf import ServiceBrowser, Zeroconf

        discovered: list[dict[str, Any]] = []
        lock = threading.Lock()

        class _Listener:
            """Collect service info as boards are discovered."""

            def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                info = zc.get_service_info(type_, name)
                if info is None:
                    return
                addresses = info.parsed_addresses()
                port = info.port
                hostname = (info.server or "").rstrip(".")
                svc_name = name.lower()
                is_vestaboard = "vestaboard" in svc_name or port == _VESTABOARD_LOCAL_API_PORT
                if is_vestaboard:
                    for addr in addresses:
                        with lock:
                            discovered.append(
                                {
                                    "ip": addr,
                                    "port": port,
                                    "hostname": hostname,
                                    "source": "mdns",
                                }
                            )

            def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                pass

            def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                pass

        zc = Zeroconf()
        listener = _Listener()
        browsers = [ServiceBrowser(zc, stype, listener) for stype in _BROWSE_SERVICE_TYPES]

        time.sleep(timeout)
        for browser in browsers:
            browser.cancel()
        zc.close()

        for entry in discovered:
            ip = entry["ip"]
            if ip not in seen_ips:
                seen_ips.add(ip)
                results.append(entry)

    except ImportError:
        logger.debug("zeroconf not installed – skipping mDNS browse phase")
    except Exception:
        logger.warning("mDNS browse phase failed", exc_info=True)

    # -- Phase 2: subnet port probe ------------------------------------------
    try:
        from concurrent.futures import ThreadPoolExecutor

        local_ip = _mdns.local_ipv4()
        if local_ip and local_ip != "127.0.0.1":
            prefix = ".".join(local_ip.split(".")[:3])
            probe_results: list[str] = []
            probe_lock = threading.Lock()

            def _check(ip: str) -> None:
                if _probe_vestaboard_port(ip):
                    with probe_lock:
                        probe_results.append(ip)

            candidates = [
                f"{prefix}.{i}"
                for i in range(1, 255)
                if f"{prefix}.{i}" != local_ip and f"{prefix}.{i}" not in seen_ips
            ]

            with ThreadPoolExecutor(max_workers=50) as pool:
                pool.map(_check, candidates)

            for ip in probe_results:
                if ip not in seen_ips:
                    seen_ips.add(ip)
                    results.append(
                        {
                            "ip": ip,
                            "port": _VESTABOARD_LOCAL_API_PORT,
                            "hostname": "",
                            "source": "port_scan",
                        }
                    )
    except Exception:
        logger.warning("Subnet port-probe phase failed", exc_info=True)

    logger.info("Board scan complete: found %d device(s)", len(results))
    return results
