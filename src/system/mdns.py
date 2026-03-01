"""mDNS/Bonjour service for local network discovery.

Registers the FiestaBoard instance via mDNS so it can be accessed
at a friendly local URL (e.g. fiestaboard.local) on networks that
support mDNS/Bonjour.
"""

import logging
import os
import socket
import threading
from typing import Optional

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
