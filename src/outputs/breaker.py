"""Third-party output safety: the write timeout and the per-output circuit breaker.

An output plugin is code FiestaBoard did not write, driving a board (plan
Phase 2.4). Two limits keep a sick one from taking the engine with it; both
are applied by :class:`~src.outputs.plugin_driver.OutputPluginDriver`, so the
in-tree Vestaboard and FiestaPanel drivers are untouched.

**Write timeout.** Core stops waiting for a write that runs past the output's
budget — :data:`DEFAULT_WRITE_TIMEOUT_MS`, which a manifest may *lower* with
``output.write_timeout_ms`` and never raise — marks it failed, and fires the
run's cancel token so the plugin is told to stop. A thread cannot be killed:
the write runs on a thread of its own, and when the budget is spent core
simply stops waiting for it, exactly as the engine stops waiting on a board
send at ``SEND_WAIT_TIMEOUT`` (``src/main.py``). The floor slot the write
reserved is kept: the device may still be receiving it.

**Circuit breaker.** Mirrors the plugin fetch breaker
(``src/plugins/registry.py``, issue #1884). After
:data:`OUTPUT_BREAKER_THRESHOLD` consecutive failed writes — raised, timed
out, or reported failed (a *partial* write is a device that answered, and
does not count) — the breaker opens for
:data:`OUTPUT_BREAKER_COOLDOWN_SECONDS`: writes are refused without calling
the plugin, and the board's send error says why. After the cool-down one
write goes through as a probe; a success closes the breaker, a failure
re-opens it at once. A wedged plugin therefore holds at most one stuck write
thread per device per cool-down, never one per tick.

It is keyed by output **and device** — ``plugin_id`` plus the plugin's
``device_key()`` — like the send floor: a board re-save (a new instance for
the same device) does not reset it, and one sick device never trips another.
The registry is process-wide.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: Consecutive failed writes that open a device's breaker.
OUTPUT_BREAKER_THRESHOLD = 3
#: How long an open breaker refuses writes before letting one probe through.
OUTPUT_BREAKER_COOLDOWN_SECONDS = 300.0
#: The longest core waits for one plugin write (or one sequence upload).
#: Generous for a LAN or cloud device answering one request, and well inside
#: the engine's SEND_WAIT_TIMEOUT (240 s), so a wedged plugin is failed and
#: cancelled long before the job waiting on it gives up.
DEFAULT_WRITE_TIMEOUT_MS = 30_000


@dataclass
class _Streak:
    failures: int = 0
    open_until: float = 0.0
    last_failure: str = ""


@dataclass(frozen=True)
class BreakerState:
    """One device's breaker, as reported."""

    consecutive_failures: int
    open: bool
    cooldown_remaining_seconds: float
    last_failure: str


class OutputBreakers:
    """Consecutive write failures per output device, and who is in cool-down."""

    def __init__(
        self,
        threshold: int = OUTPUT_BREAKER_THRESHOLD,
        cooldown_seconds: float = OUTPUT_BREAKER_COOLDOWN_SECONDS,
    ) -> None:
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._streaks: dict[str, _Streak] = {}

    def refusal(self, key: str, now: float) -> _Streak | None:
        """The streak holding *key* shut, or ``None`` when a write may go.

        ``None`` too once the cool-down has run out: that write is the probe.
        """
        with self._lock:
            streak = self._streaks.get(key)
            if streak is None or streak.open_until <= now:
                return None
            return _Streak(streak.failures, streak.open_until, streak.last_failure)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._streaks.pop(key, None)

    def record_failure(self, key: str, reason: str, now: float) -> bool:
        """Charge one failure to *key*; True when that opened (or re-opened) it."""
        with self._lock:
            streak = self._streaks.setdefault(key, _Streak())
            streak.failures += 1
            streak.last_failure = reason
            if streak.failures < self.threshold:
                return False
            streak.open_until = now + self.cooldown_seconds
        logger.warning(
            "Output breaker OPEN for %s after %d consecutive failed writes; refusing writes for %.0fs (last: %s)",
            key,
            streak.failures,
            self.cooldown_seconds,
            reason,
        )
        return True

    def state(self, key: str, now: float) -> BreakerState | None:
        """*key*'s breaker, or ``None`` when it has no failure streak."""
        with self._lock:
            streak = self._streaks.get(key)
            if streak is None:
                return None
            remaining = max(0.0, streak.open_until - now)
            return BreakerState(streak.failures, remaining > 0.0, round(remaining, 1), streak.last_failure)

    def clear(self) -> None:
        """Forget every streak (tests)."""
        with self._lock:
            self._streaks.clear()


_breakers = OutputBreakers()


def output_breakers() -> OutputBreakers:
    """The process-wide breaker registry."""
    return _breakers


def write_failure_reason(driver: Any) -> str | None:
    """Why *driver*'s last write failed, when the driver can say.

    Only output-plugin drivers carry a reason (``last_write_error``); every
    other driver — and a test double — answers ``None``, so the messages they
    produce are unchanged.
    """
    reason = getattr(driver, "last_write_error", None)
    return reason if isinstance(reason, str) and reason else None
