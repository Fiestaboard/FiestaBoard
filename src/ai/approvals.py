"""The hub's own record of which chat tool calls are waiting for approval.

``POST /pages/ai/chat`` is stateless: the client replays the transcript on
every request, so the transcript is the client's account of what happened.
That is fine for prose, but it cannot be the authority for *running* a tool.
When the agent loop pauses on a call it records the call here: the caller it
paused for, the call id (a random id the hub minted), and the exact tool
name and arguments. A ``resume: approve`` runs only a call it can take back
out of this store — once, before it expires, for the same caller, with the
same name and args the transcript claims. A transcript that names a call the
hub never paused on runs nothing.

The store is in memory. FiestaBoard runs one API process (supervisord starts
a single uvicorn worker), and a pause that does not survive a restart is the
safe failure: the user is asked to send the request again.
"""

from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: How long a paused call can wait for its approval.
DEFAULT_TTL_SECONDS = 30 * 60

#: Pauses kept at once; the oldest goes first when a new one would exceed it.
DEFAULT_MAX_ENTRIES = 256

#: Pauses kept per caller, so one caller cannot push out another's.
DEFAULT_MAX_PER_OWNER = 16


@dataclass(frozen=True)
class PendingCall:
    """A tool call the agent loop paused on, as the hub recorded it."""

    owner: str
    call_id: str
    name: str
    args: dict[str, Any]
    expires_at: float


class PendingCallStore:
    """Single-use, expiring pauses keyed by (caller, call id).

    Bounded per caller and in total. Per caller, a new pause pushes out that
    caller's own oldest; the global bound (with distinct callers capped, so
    it is reached only by many callers at once) pushes out the oldest of all.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_per_owner: int = DEFAULT_MAX_PER_OWNER,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._max_per_owner = max_per_owner
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, str], PendingCall] = OrderedDict()

    def record(self, owner: str, call_id: str, name: str, args: dict[str, Any]) -> None:
        """Remember that the loop paused on this call for ``owner``."""
        entry = PendingCall(
            owner=owner, call_id=call_id, name=name, args=copy.deepcopy(args), expires_at=self._clock() + self._ttl
        )
        with self._lock:
            self._prune()
            self._entries.pop((owner, call_id), None)
            mine = [key for key in self._entries if key[0] == owner]
            # This caller's oldest pauses go first, then (only if the global
            # bound is still exceeded) anyone's oldest.
            for key in mine[: max(0, len(mine) + 1 - self._max_per_owner)]:
                del self._entries[key]
            self._entries[(owner, call_id)] = entry
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)

    def take(self, owner: str, call_id: str) -> PendingCall | None:
        """Remove and return ``owner``'s pause on ``call_id``, if it is still live."""
        with self._lock:
            entry = self._entries.pop((owner, call_id), None)
        if entry is None or entry.expires_at <= self._clock():
            return None
        return entry

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _prune(self) -> None:
        now = self._clock()
        for key in [key for key, entry in self._entries.items() if entry.expires_at <= now]:
            del self._entries[key]


#: The process's store, shared by every chat request.
PENDING_CALLS = PendingCallStore()


__all__ = ["DEFAULT_TTL_SECONDS", "PENDING_CALLS", "PendingCall", "PendingCallStore"]
