"""The send floor: the minimum spacing between writes to one device.

Owned by core, keyed by the ``device_key()`` a driver declares — host+port
for a LAN device, a hash of the credential for a cloud one — so the floor
belongs to the *device*, not to whichever client object happens to send:

- a board re-save rebuilds its client and the window survives;
- a throwaway client an API route builds for the same board (welcome, live
  render) sees the window the engine's client opened.

The registry is process-wide. A driver declares *how long* its floor is
(``min_send_interval_ms``); core decides *whether* a send may go.

Concurrency: a slot is reserved *before* the write, under the registry
lock, so concurrent per-board send workers can never double-send inside one
window; a write that fails gives the slot back with :meth:`SendFloors.release`.
The dedupe check runs under the same lock, so "throttled" and "unchanged"
are decided atomically, exactly as when this lived in the client.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

Verdict = Literal["send", "throttled", "unchanged"]


def credential_digest(secret: str) -> str:
    """A short, stable, non-reversible id for a credential, for device keys.

    Device keys appear in logs; a raw API key or token never may.
    """
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Admission:
    """One send's verdict and the slot it holds.

    ``retry_after`` is the remaining window in whole seconds (rounded up,
    never 0) for a throttled verdict, else ``None``. ``reserved_at`` is the
    clock reading the slot was reserved at (``None`` when unfloored), and
    ``prev_last`` what it replaced, so a failed write can give it back.
    """

    verdict: Verdict
    device_key: str
    prev_last: float | None = None
    reserved_at: float | None = None
    retry_after: int | None = None


class SendFloors:
    """Last-send times per device key, and the admit/release protocol over them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}

    def admit(
        self,
        device_key: str,
        floor_seconds: float,
        clock: Callable[[], float],
        is_unchanged: Callable[[], bool],
    ) -> Admission:
        """Decide whether a send may proceed, reserving its slot if so.

        Floor first, then the unchanged-content check; only a send that will
        actually go out records ``now`` as the device's last send.
        """
        with self._lock:
            now = clock() if floor_seconds > 0 else None
            prev_last: float | None = None
            if floor_seconds > 0:
                prev_last = self._last.get(device_key)
                if prev_last is not None:
                    elapsed = now - prev_last
                    if elapsed < floor_seconds:
                        retry_after = max(1, math.ceil(floor_seconds - elapsed))
                        logger.warning(
                            "Send to %s throttled: %.1fs since last send (min %.0fs); skipping.",
                            device_key,
                            elapsed,
                            floor_seconds,
                        )
                        return Admission("throttled", device_key, prev_last, now, retry_after)
            if is_unchanged():
                return Admission("unchanged", device_key, prev_last, now)
            if floor_seconds > 0:
                self._last[device_key] = now
            return Admission("send", device_key, prev_last, now)

    def release(self, admission: Admission) -> None:
        """Give back a slot reserved by :meth:`admit` after the write failed.

        Restores the previous time only if this reservation is still the
        current one, so a slot legitimately taken since is never clobbered.
        """
        if admission.reserved_at is None:
            return
        with self._lock:
            if self._last.get(admission.device_key) == admission.reserved_at:
                if admission.prev_last is None:
                    self._last.pop(admission.device_key, None)
                else:
                    self._last[admission.device_key] = admission.prev_last

    def hold(self, admission: Admission, floor_seconds: float, seconds: float) -> None:
        """Keep the device closed for *seconds* from the reservation.

        The device said "slow down" (an HTTP 429). The reserved slot already
        closes it for one floor; a longer ``Retry-After`` pushes the slot
        forward so the window ends when the device asked, never earlier.
        """
        if admission.reserved_at is None or seconds <= floor_seconds:
            return
        with self._lock:
            held = admission.reserved_at + seconds - floor_seconds
            if self._last.get(admission.device_key, float("-inf")) < held:
                self._last[admission.device_key] = held

    def clear(self) -> None:
        """Forget every device's window. Tests only."""
        with self._lock:
            self._last.clear()


_SEND_FLOORS = SendFloors()


def send_floors() -> SendFloors:
    """The process-wide floor registry."""
    return _SEND_FLOORS
