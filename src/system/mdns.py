"""mDNS/Bonjour service for local network discovery.

Registers the FiestaBoard instance via mDNS so it can be accessed
at a friendly local URL (e.g. fiestaboard.local) on networks that
support mDNS/Bonjour.

Also provides board scanning to discover Vestaboards on the local network
via mDNS service browsing and port probing.
"""

import logging
import os
import socket
import threading
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Default hostname advertised via mDNS (without the .local suffix)
DEFAULT_MDNS_HOSTNAME = "fiestaboard"
DEFAULT_SERVICE_PORT = 4420

_mdns_service: Optional["MDNSService"] = None
_mdns_lock = threading.Lock()


class MDNSService:
    """Manages mDNS advertisement for FiestaBoard.

    Advertises an HTTP service so the instance is discoverable via
    ``<hostname>.local`` on the local network.
    """

    def __init__(
        self,
        hostname: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        self._hostname = (
            hostname
            or os.environ.get("MDNS_HOSTNAME", DEFAULT_MDNS_HOSTNAME)
        )
        self._port = port or int(
            os.environ.get("MDNS_PORT", str(DEFAULT_SERVICE_PORT))
        )
        self._zeroconf = None
        self._service_info = None
        self._started = False

    # -- public helpers ------------------------------------------------

    @property
    def hostname(self) -> str:
        return self._hostname

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def local_url(self) -> str:
        """Return the friendly local URL (e.g. ``http://fiestaboard.local:4420``)."""
        if self._port == 80:
            return f"http://{self._hostname}.local"
        return f"http://{self._hostname}.local:{self._port}"

    # -- lifecycle -----------------------------------------------------

    def start(self) -> bool:
        """Register the mDNS service.  Returns True on success."""
        if self._started:
            logger.debug("mDNS service already running")
            return True

        try:
            from zeroconf import Zeroconf, ServiceInfo

            ip_address = _get_local_ip()

            self._service_info = ServiceInfo(
                type_="_http._tcp.local.",
                name=f"FiestaBoard._http._tcp.local.",
                server=f"{self._hostname}.local.",
                port=self._port,
                properties={
                    "path": "/",
                    "product": "FiestaBoard",
                },
                addresses=[socket.inet_aton(ip_address)],
            )

            self._zeroconf = Zeroconf()
            self._zeroconf.register_service(self._service_info)
            self._started = True
            logger.info(
                "mDNS service registered: %s (http://%s.local:%s)",
                self._service_info.name,
                self._hostname,
                self._port,
            )
            return True
        except ImportError:
            logger.warning(
                "zeroconf package not installed – mDNS advertisement disabled"
            )
            return False
        except Exception:
            logger.warning("Failed to start mDNS service", exc_info=True)
            return False

    def stop(self) -> None:
        """Unregister and shut down the mDNS service."""
        if not self._started:
            return
        try:
            if self._zeroconf and self._service_info:
                self._zeroconf.unregister_service(self._service_info)
            if self._zeroconf:
                self._zeroconf.close()
            logger.info("mDNS service stopped")
        except Exception:
            logger.warning("Error stopping mDNS service", exc_info=True)
        finally:
            self._started = False
            self._zeroconf = None
            self._service_info = None


def _get_local_ip() -> str:
    """Return a best-guess non-loopback IPv4 address for this host."""
    try:
        # Connect to an external address (doesn't actually send data)
        # to determine which local interface would be used.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


# -- module-level singleton helpers ------------------------------------


def get_mdns_service() -> MDNSService:
    """Return (and lazily create) the singleton :class:`MDNSService`."""
    global _mdns_service
    if _mdns_service is None:
        with _mdns_lock:
            if _mdns_service is None:
                _mdns_service = MDNSService()
    return _mdns_service


def start_mdns() -> bool:
    """Convenience wrapper – create the singleton and start advertising."""
    return get_mdns_service().start()


def stop_mdns() -> None:
    """Convenience wrapper – stop the singleton service."""
    global _mdns_service
    if _mdns_service is not None:
        _mdns_service.stop()


# -- Board scanning / discovery -------------------------------------------

# Vestaboard Local API port
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
    except (OSError, socket.timeout):
        return False


def scan_for_boards(timeout: float = 4.0) -> List[Dict[str, Any]]:
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
    results: List[Dict[str, Any]] = []

    # -- Phase 1: mDNS browse ------------------------------------------------
    try:
        from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo
        import time

        discovered: List[Dict[str, Any]] = []
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
                is_vestaboard = (
                    "vestaboard" in svc_name
                    or port == _VESTABOARD_LOCAL_API_PORT
                )
                if is_vestaboard:
                    for addr in addresses:
                        with lock:
                            discovered.append({
                                "ip": addr,
                                "port": port,
                                "hostname": hostname,
                                "source": "mdns",
                            })

            def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                pass

            def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                pass

        zc = Zeroconf()
        listener = _Listener()
        browsers = [
            ServiceBrowser(zc, stype, listener)
            for stype in _BROWSE_SERVICE_TYPES
        ]

        time.sleep(timeout)
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

        local_ip = _get_local_ip()
        if local_ip and local_ip != "127.0.0.1":
            prefix = ".".join(local_ip.split(".")[:3])
            probe_results: List[str] = []
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
                    results.append({
                        "ip": ip,
                        "port": _VESTABOARD_LOCAL_API_PORT,
                        "hostname": "",
                        "source": "port_scan",
                    })
    except Exception:
        logger.warning("Subnet port-probe phase failed", exc_info=True)

    logger.info("Board scan complete: found %d device(s)", len(results))
    return results
