"""WiFi management for FiestaPi via NetworkManager (`nmcli`).

Only usable on the FiestaPi image, where the main container is granted
``cap_add: NET_ADMIN`` and a bind mount of ``/var/run/dbus`` so that the
host NetworkManager can be driven from inside the container. On a plain
Docker deployment ``is_available()`` returns False and the API surfaces
HTTP 501 for every endpoint, so non-Pi users see nothing.

The implementation talks to NM via `nmcli` (Debian ``network-manager``
package, installed in the runtime stage of the main image) rather than
re-implementing the D-Bus protocol.

Profiles are created with ``connection.autoconnect yes`` and persist on
the host (mirroring the first-boot provisioning in
``pi-image/.../firstboot.sh``), so connections survive container restarts
and reboots even if the API container is destroyed.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from src.network_diagnostics import check_internet_connectivity

logger = logging.getLogger(__name__)

# Per-call timeouts (seconds).
_NMCLI_QUICK_TIMEOUT = 10
_NMCLI_SCAN_TIMEOUT = 30
_NMCLI_CONNECT_TIMEOUT = 60
_NM_ONLINE_TIMEOUT = 30

# Path NM exposes its D-Bus on inside the container. When the Pi compose
# file mounts /var/run/dbus this socket is reachable; otherwise nmcli will
# refuse and we treat WiFi management as unavailable.
_DBUS_SOCKET = "/var/run/dbus/system_bus_socket"

# Env var set in the Pi image's docker-compose. Used (alongside the binary
# + D-Bus checks) to gate the feature so non-Pi deployments never even try.
_PI_PROFILE_ENV = "FIESTABOARD_PROFILE"
_PI_PROFILE_VALUE = "pi"


class WiFiError(Exception):
    """Domain error for any nmcli-related failure surfaced to the API."""


@dataclass
class WiFiNetwork:
    """A scan result row, one per unique SSID (strongest signal wins)."""

    ssid: str
    signal: int  # 0..100 as nmcli reports
    security: str  # e.g. "WPA2", "OPEN"
    in_use: bool


@dataclass
class SavedNetwork:
    """A persisted NM connection profile of type 802-11-wireless."""

    name: str
    autoconnect: bool


@dataclass
class WiFiStatus:
    """Current WiFi state plus an internet-reachability probe."""

    connected: bool
    ssid: Optional[str]
    ip_address: Optional[str]
    gateway: Optional[str]
    signal: Optional[int]
    internet_reachable: bool


@dataclass
class WiFiConnectResult:
    """Outcome of a connect attempt."""

    status: WiFiStatus
    connectivity_confirmed: bool  # nm-online succeeded
    message: str


@dataclass
class WiFiCapability:
    """Feature probe: is WiFi management available on this deployment?"""

    available: bool
    reason: Optional[str] = None


def _profile_is_pi() -> bool:
    return os.environ.get(_PI_PROFILE_ENV, "").lower() == _PI_PROFILE_VALUE


def _redact_args(args: Iterable[str]) -> list[str]:
    """Mask the WPA PSK so it never appears in logs.

    `nmcli connection add ... wifi-sec.psk <SECRET>` is the only place a
    password reaches us — we redact the value right after the key.
    """
    out: list[str] = []
    redact_next = False
    for arg in args:
        if redact_next:
            out.append("***")
            redact_next = False
            continue
        out.append(arg)
        if arg in ("wifi-sec.psk", "password"):
            redact_next = True
    return out


class WiFiService:
    """Async-safe nmcli wrapper.

    All public methods that mutate NM state (`connect`, `disconnect`,
    `forget`) serialize behind ``_lock`` so the UI can't queue conflicting
    profile changes. Read-only methods (`status`, `scan`,
    `saved_networks`) do not take the lock — multiple readers are fine.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cached_capability: Optional[WiFiCapability] = None

    # ---- capability probe ------------------------------------------------

    def capability(self) -> WiFiCapability:
        """Probe whether WiFi management is wired up on this deployment.

        Cached after first call — the result depends on env + filesystem
        state at startup, neither of which changes at runtime.
        """
        if self._cached_capability is not None:
            return self._cached_capability

        if not _profile_is_pi():
            cap = WiFiCapability(
                available=False,
                reason="WiFi management is only available on the FiestaPi image.",
            )
        elif shutil.which("nmcli") is None:
            cap = WiFiCapability(
                available=False,
                reason="nmcli is not installed in this container image.",
            )
        elif not Path(_DBUS_SOCKET).exists():
            cap = WiFiCapability(
                available=False,
                reason=(
                    "The host D-Bus socket is not mounted into the "
                    "container; cannot reach NetworkManager."
                ),
            )
        else:
            cap = WiFiCapability(available=True)

        self._cached_capability = cap
        return cap

    def _require_available(self) -> None:
        cap = self.capability()
        if not cap.available:
            raise WiFiError(cap.reason or "WiFi management unavailable")

    # ---- subprocess plumbing --------------------------------------------

    def _run_nmcli(self, args: list[str], timeout: int = _NMCLI_QUICK_TIMEOUT) -> str:
        """Run an nmcli invocation, returning stdout.

        Always passes a list (no shell), enforces a timeout, redacts
        secrets in log messages, and translates failures into ``WiFiError``
        with the stderr message so the API can return a useful response.
        """
        cmd = ["nmcli"] + args
        logger.debug("nmcli: %s", " ".join(_redact_args(cmd)))
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise WiFiError("nmcli binary not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise WiFiError(
                f"nmcli timed out after {timeout}s: {' '.join(_redact_args(cmd))}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise WiFiError(stderr or f"nmcli exited with status {exc.returncode}") from exc
        return result.stdout

    def _run_nm_online(self, timeout: int = _NM_ONLINE_TIMEOUT) -> bool:
        """Block until NM reports full connectivity (DHCP + DNS) or fail.

        Mirrors the firstboot.sh probe — `nm-online` returns 0 only when
        NM has at least one active connection that's *online*, not just
        *associated*. If the binary is missing we conservatively return
        False so the UI can warn the user.
        """
        if shutil.which("nm-online") is None:
            return False
        try:
            subprocess.run(
                ["nm-online", "--timeout", str(timeout)],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout + 5,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    # ---- parsers ---------------------------------------------------------

    @staticmethod
    def _parse_terse(line: str) -> list[str]:
        """Split an `nmcli -t` line on unescaped colons.

        nmcli's terse output escapes embedded colons as ``\\:`` (so an
        SSID like ``foo:bar`` survives the round trip). A naive
        ``line.split(":")`` would corrupt those SSIDs.
        """
        fields: list[str] = []
        buf: list[str] = []
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "\\" and i + 1 < len(line):
                buf.append(line[i + 1])
                i += 2
                continue
            if ch == ":":
                fields.append("".join(buf))
                buf = []
                i += 1
                continue
            buf.append(ch)
            i += 1
        fields.append("".join(buf))
        return fields

    # ---- public read methods --------------------------------------------

    def status(self) -> WiFiStatus:
        """Return the current WiFi state plus an internet probe.

        Walks `nmcli -t -f NAME,TYPE,DEVICE connection show --active`
        looking for the active WiFi connection, then pulls IP + gateway
        from `nmcli -t -f IP4.ADDRESS,IP4.GATEWAY connection show <name>`.
        """
        self._require_available()

        active_out = self._run_nmcli(
            ["-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"]
        )
        active_ssid: Optional[str] = None
        active_name: Optional[str] = None
        for line in active_out.splitlines():
            parts = self._parse_terse(line)
            if len(parts) >= 2 and parts[1] == "802-11-wireless":
                active_name = parts[0]
                active_ssid = parts[0]  # NM uses the SSID as the con-name by default
                break

        ip_address: Optional[str] = None
        gateway: Optional[str] = None
        signal: Optional[int] = None

        if active_name:
            try:
                detail = self._run_nmcli(
                    ["-t", "-f", "IP4.ADDRESS,IP4.GATEWAY", "connection", "show", active_name]
                )
                for line in detail.splitlines():
                    parts = self._parse_terse(line)
                    if len(parts) < 2:
                        continue
                    key, val = parts[0], parts[1]
                    if key.startswith("IP4.ADDRESS") and val:
                        ip_address = val.split("/")[0]
                    elif key == "IP4.GATEWAY" and val:
                        gateway = val
            except WiFiError as exc:
                logger.warning("could not read IP details for %s: %s", active_name, exc)

            # Pull current signal strength from the scan-cache row marked
            # in-use, which is the active AP. Best-effort — missing signal
            # isn't an error.
            try:
                scan_out = self._run_nmcli(
                    ["-t", "-f", "IN-USE,SSID,SIGNAL", "device", "wifi", "list"]
                )
                for line in scan_out.splitlines():
                    parts = self._parse_terse(line)
                    if len(parts) >= 3 and parts[0] == "*" and parts[1] == active_ssid:
                        try:
                            signal = int(parts[2])
                        except ValueError:
                            pass
                        break
            except WiFiError:
                pass

        internet = check_internet_connectivity().get("ok", False)
        return WiFiStatus(
            connected=active_ssid is not None,
            ssid=active_ssid,
            ip_address=ip_address,
            gateway=gateway,
            signal=signal,
            internet_reachable=internet,
        )

    def scan(self) -> list[WiFiNetwork]:
        """Rescan and return de-duplicated SSIDs (strongest signal kept).

        Uses ``--rescan auto`` so NM re-scans if the cache is stale (about
        every 30 s on idle) but reuses recent results otherwise — keeps
        the UI snappy on rapid refreshes.
        """
        self._require_available()
        out = self._run_nmcli(
            [
                "-t",
                "-f",
                "IN-USE,SSID,SIGNAL,SECURITY",
                "device",
                "wifi",
                "list",
                "--rescan",
                "auto",
            ],
            timeout=_NMCLI_SCAN_TIMEOUT,
        )
        # Dedupe by SSID; keep the row with the highest signal.
        best: dict[str, WiFiNetwork] = {}
        for line in out.splitlines():
            parts = self._parse_terse(line)
            if len(parts) < 4:
                continue
            in_use, ssid, signal_str, security = parts[0], parts[1], parts[2], parts[3]
            if not ssid:
                continue  # skip hidden SSIDs (nmcli reports them as empty)
            try:
                signal = int(signal_str)
            except ValueError:
                signal = 0
            entry = WiFiNetwork(
                ssid=ssid,
                signal=signal,
                security=security or "OPEN",
                in_use=in_use == "*",
            )
            current = best.get(ssid)
            if current is None or entry.signal > current.signal:
                best[ssid] = entry
        return sorted(best.values(), key=lambda n: n.signal, reverse=True)

    def saved_networks(self) -> list[SavedNetwork]:
        """List persisted wifi profiles (the ones NM will autoconnect)."""
        self._require_available()
        out = self._run_nmcli(
            ["-t", "-f", "NAME,TYPE,AUTOCONNECT", "connection", "show"]
        )
        saved: list[SavedNetwork] = []
        for line in out.splitlines():
            parts = self._parse_terse(line)
            if len(parts) < 3:
                continue
            name, conn_type, autoconnect = parts[0], parts[1], parts[2]
            if conn_type != "802-11-wireless":
                continue
            saved.append(SavedNetwork(name=name, autoconnect=autoconnect == "yes"))
        return saved

    # ---- public mutating methods ----------------------------------------

    async def connect(
        self,
        ssid: str,
        password: Optional[str] = None,
        hidden: bool = False,
    ) -> WiFiConnectResult:
        """Create/replace a persistent profile and bring it up.

        Same shape as the firstboot provisioning flow: delete any existing
        profile of the same name (for idempotence — switching networks
        with the same SSID would otherwise fail at `connection add`), then
        `nmcli connection add` with autoconnect=yes, `connection up`, and
        finally `nm-online` to confirm DHCP + DNS actually came up.

        Returns the new `WiFiStatus` plus a `connectivity_confirmed` flag
        so the UI can show a warning if the AP joined but the internet
        check failed (wrong password manifests this way on some APs).
        """
        self._require_available()
        if not ssid:
            raise WiFiError("SSID is required")

        async with self._lock:
            # Idempotent delete first — same reasoning as firstboot.sh
            # comment about preventing silent failures on con-name reuse.
            try:
                await asyncio.to_thread(
                    self._run_nmcli, ["connection", "delete", ssid]
                )
            except WiFiError:
                pass  # not found is fine

            add_args = [
                "connection",
                "add",
                "type",
                "wifi",
                "ifname",
                "wlan0",
                "con-name",
                ssid,
                "ssid",
                ssid,
                "connection.autoconnect",
                "yes",
            ]
            if hidden:
                add_args += ["wifi.hidden", "yes"]
            if password:
                add_args += [
                    "wifi-sec.key-mgmt",
                    "wpa-psk",
                    "wifi-sec.psk",
                    password,
                ]
            await asyncio.to_thread(self._run_nmcli, add_args)

            try:
                await asyncio.to_thread(
                    self._run_nmcli,
                    ["connection", "up", ssid],
                    _NMCLI_CONNECT_TIMEOUT,
                )
            except WiFiError as exc:
                # The activation failed (bad password, AP gone). Clean up
                # the profile we just created so a retry isn't blocked by
                # the stale entry. Failure of the cleanup itself is non-fatal.
                try:
                    await asyncio.to_thread(
                        self._run_nmcli, ["connection", "delete", ssid]
                    )
                except WiFiError:
                    pass
                raise WiFiError(f"Could not join '{ssid}': {exc}") from exc

            confirmed = await asyncio.to_thread(self._run_nm_online)
            status = await asyncio.to_thread(self.status)

        message = (
            f"Connected to {ssid}."
            if confirmed
            else f"Joined {ssid} but could not verify internet connectivity."
        )
        return WiFiConnectResult(
            status=status,
            connectivity_confirmed=confirmed,
            message=message,
        )

    async def disconnect(self) -> WiFiStatus:
        """Bring down the active wifi connection (keeps the saved profile)."""
        self._require_available()
        async with self._lock:
            active_out = await asyncio.to_thread(
                self._run_nmcli,
                ["-t", "-f", "NAME,TYPE", "connection", "show", "--active"],
            )
            target: Optional[str] = None
            for line in active_out.splitlines():
                parts = self._parse_terse(line)
                if len(parts) >= 2 and parts[1] == "802-11-wireless":
                    target = parts[0]
                    break
            if not target:
                raise WiFiError("No active WiFi connection to disconnect")
            await asyncio.to_thread(self._run_nmcli, ["connection", "down", target])
            return await asyncio.to_thread(self.status)

    async def forget(self, con_name: str) -> None:
        """Delete a saved profile so NM won't autoconnect to it again."""
        self._require_available()
        if not con_name:
            raise WiFiError("Connection name is required")
        async with self._lock:
            await asyncio.to_thread(
                self._run_nmcli, ["connection", "delete", con_name]
            )


# Singleton — there's only one NetworkManager per host.
_service: Optional[WiFiService] = None


def get_wifi_service() -> WiFiService:
    global _service
    if _service is None:
        _service = WiFiService()
    return _service
