"""mDNS/Bonjour service for local network discovery.

Registers the FiestaBoard instance via mDNS so it can be accessed
at a friendly local URL (e.g. fiestaboard.local) on networks that
support mDNS/Bonjour.

Finding *devices* on the network is not this module's job: each output
answers that through its own ``discover`` hook (the Vestaboard scan lives in
``fiestaboard-output--vestaboard/discovery.py``), using :func:`local_ipv4` from here.
"""

import logging
import os
import socket
import threading
from collections.abc import Callable
from typing import Optional

logger = logging.getLogger(__name__)

# Default hostname advertised via mDNS (without the .local suffix)
DEFAULT_MDNS_HOSTNAME = "fiestaboard"
DEFAULT_SERVICE_PORT = 4420

_mdns_service: Optional["MDNSService"] = None
_mdns_lock = threading.Lock()

#: Set while the app is shutting down, so a registration still in flight on
#: the background thread tears itself down instead of leaving an
#: advertisement up. See :func:`start_mdns_background`.
_mdns_shutdown = threading.Event()


class MDNSService:
    """Manages mDNS advertisement for FiestaBoard.

    Advertises an HTTP service so the instance is discoverable via
    ``<hostname>.local`` on the local network.
    """

    def __init__(
        self,
        hostname: str | None = None,
        port: int | None = None,
    ) -> None:
        self._hostname = hostname or os.environ.get("MDNS_HOSTNAME", DEFAULT_MDNS_HOSTNAME)
        self._port = port or int(os.environ.get("MDNS_PORT", str(DEFAULT_SERVICE_PORT)))
        self._zeroconf = None
        self._service_info = None
        self._started = False

        #: Serialises refresh (on its own thread) against stop.
        self._lock = threading.RLock()

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
            from zeroconf import ServiceInfo, Zeroconf

            ip_address = _get_local_ip()

            self._service_info = ServiceInfo(
                type_="_http._tcp.local.",
                name="FiestaBoard._http._tcp.local.",
                server=f"{self._hostname}.local.",
                port=self._port,
                properties=self._txt_properties(),
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
            logger.warning("zeroconf package not installed – mDNS advertisement disabled")
            return False
        except Exception as exc:
            # zeroconf raises EventLoopBlocked when its internal asyncio loop
            # can't process the registration within its timeout. On slow
            # hardware (e.g. Raspberry Pi 3) this happens during a busy
            # startup. The app is fine — users just lose the .local URL and
            # can still reach FiestaBoard by IP.
            if type(exc).__name__ == "EventLoopBlocked":
                logger.info(
                    "mDNS registration timed out during startup; "
                    "%s.local will be unavailable but FiestaBoard is reachable by IP",
                    self._hostname,
                )
                return False
            logger.warning("Failed to start mDNS service", exc_info=True)
            return False

    def _txt_properties(self) -> dict[str, str]:
        """The TXT record (H13 PR 3).

        ``host`` is the ``<hostname>.local`` name this hub answers to (the SRV
        target, so nothing new is disclosed), for the TVs' "hostname · IP"
        line. ``name`` is the install's friendly name, present only while
        sign-in is off: the same rule as ``GET /discover``
        (:func:`src.system.hub_identity.public_instance_name`).
        """
        properties = {"path": "/", "product": "FiestaBoard", "host": f"{self._hostname}.local"}
        try:
            from src.system.hub_identity import public_instance_name

            name = _txt_value(public_instance_name())
        except Exception:
            # A missing name only changes a label on a discovery card; never fail the advertisement for it.
            logger.debug("Could not read the instance name for the mDNS TXT record", exc_info=True)
            name = ""
        if name:
            properties["name"] = name
        return properties

    def refresh(self) -> bool:
        """Re-announce the TXT record if it changed (a rename, sign-in turned on or off).

        Returns True when an update was sent. Blocks while zeroconf
        announces; callers on a request path use :func:`refresh_mdns_advertisement`.
        """
        with self._lock:
            if not self._started or self._zeroconf is None or self._service_info is None:
                return False
            properties = self._txt_properties()
            current = {
                (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                for k, v in (self._service_info.properties or {}).items()
            }
            if current == properties:
                return False
            from zeroconf import ServiceInfo

            info = ServiceInfo(
                type_=self._service_info.type,
                name=self._service_info.name,
                server=self._service_info.server,
                port=self._service_info.port,
                properties=properties,
                addresses=self._service_info.addresses,
            )
            self._zeroconf.update_service(info)
            self._service_info = info
            logger.info("mDNS TXT record updated")
            return True

    def stop(self) -> None:
        """Unregister and shut down the mDNS service."""
        if not self._started:
            return
        # The lock only orders this against a TXT refresh still on the air.
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
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


#: A TXT entry is at most 255 bytes, ``name=`` included.
_TXT_VALUE_BYTES = 255 - len("name=")
#: The pairing offer's cap on the same name (src/auth/device_service.py).
_NAME_CHARS = 100


def _txt_value(value: str) -> str:
    """*value* cut to fit one TXT entry, never mid-character."""
    return value[:_NAME_CHARS].encode("utf-8")[:_TXT_VALUE_BYTES].decode("utf-8", errors="ignore")


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


def local_ipv4() -> str:
    """This host's best-guess LAN IPv4 address (``127.0.0.1`` when unknown).

    The public face of :func:`_get_local_ip`, for the outputs' ``discover``
    hooks; it looks the helper up at call time, so a test that patches
    ``_get_local_ip`` steers both.
    """
    return _get_local_ip()


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
    """Convenience wrapper – create the singleton and start advertising.

    Blocks until zeroconf accepts the registration or gives up. Callers on
    a latency-sensitive path want :func:`start_mdns_background` instead.
    """
    return get_mdns_service().start()


def start_mdns_background(on_registered: Callable[[str], None] | None = None) -> threading.Thread:
    """Register the mDNS service without holding the calling thread (#1955).

    ``zeroconf.register_service()`` blocks for the whole of its internal
    timeout when multicast does not reach a responder — measured at 5.2 s
    in a container with no multicast route, and :meth:`MDNSService.start`
    already documents the Raspberry Pi 3 case. Run from the app's startup
    path that is 5.2 s during which nothing is served, to learn something
    the app treats as optional either way: losing ``<host>.local`` is a
    logged, survivable outcome, because the box stays reachable by IP.

    So the registration runs on a daemon thread and the caller continues.
    *on_registered* is invoked with the local URL if — and only if — the
    registration actually succeeded, so the announcement is deferred
    rather than dropped.

    Returns the thread, which callers may join in tests. Nothing in the
    product joins it: it is a daemon, so it can never hold process exit.
    """
    _mdns_shutdown.clear()

    def _register() -> None:
        try:
            registered = start_mdns()
        except Exception:
            logger.warning("mDNS service could not be started", exc_info=True)
            return
        if not registered:
            return
        if _mdns_shutdown.is_set():
            # The lifespan ended while we were still registering. Undo it
            # rather than leaving an advertisement behind for a process
            # that is going away.
            stop_mdns()
            return
        # A rename or sign-in change during the (blocking) registration found
        # nothing running to refresh; catch it up now. A no-op when unchanged.
        try:
            get_mdns_service().refresh()
        except Exception:
            logger.warning("Could not update the mDNS TXT record", exc_info=True)
        if on_registered is not None:
            try:
                on_registered(get_mdns_service().local_url)
            except Exception:
                logger.debug("mDNS registration callback failed", exc_info=True)

    thread = threading.Thread(target=_register, name="mdns-register", daemon=True)
    thread.start()
    return thread


def refresh_mdns_advertisement() -> threading.Thread | None:
    """Re-announce the TXT record on a daemon thread, if the hub is advertising.

    Called after the friendly name or the sign-in mode changes. Returns the
    thread (tests join it), or None when nothing is advertised.
    """
    service = _mdns_service
    if service is None or not service.is_running:
        return None

    def _refresh() -> None:
        try:
            service.refresh()
        except Exception:
            logger.warning("Could not update the mDNS TXT record", exc_info=True)

    thread = threading.Thread(target=_refresh, name="mdns-refresh", daemon=True)
    thread.start()
    return thread


def stop_mdns() -> None:
    """Convenience wrapper – stop the singleton service.

    Sets the shutdown flag first so a registration still in flight on the
    background thread tears itself down when it lands, instead of this
    call blocking to wait for it.
    """
    _mdns_shutdown.set()
    if _mdns_service is not None:
        _mdns_service.stop()
