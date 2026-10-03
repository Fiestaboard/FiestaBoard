"""Core per-board send policy, owned by the platform rather than the driver.

One :class:`OutputRuntime` exists per board. The display engine's
``BoardRuntime`` creates it and binds it to the board's client, which then
takes its send lock and cancel token from here instead of owning them.

It holds the **send lock**, the **cancel token**, the board's
:class:`~src.outputs.frames.FrameCache` (frame dedupe and the last-frame
store), **external-write detection** over it, and the door to the **send
floor** (:mod:`src.outputs.floor`), which is keyed by device rather than by
runtime so it outlives any one client. Transition driving still lives in the
clients and moves in a later layer.

The contract, unchanged from when it lived in ``TransitionRenderMixin``:

- **Preemption before the lock.** :meth:`run` signals the in-flight run's
  token *before* it waits on the lock, so a running transition winds down
  between frames instead of being waited out. :meth:`preempt` does the same
  without running anything; the engine calls it when it enqueues a newer
  frame, so a transition learns about it at once rather than when the
  board's worker dequeues the job.
- **A fresh token per run.** Each run installs a new ``Event`` under the
  lock. A signal meant for the previous run can never pre-cancel the next
  one, and the preempted run keeps its own reference to the old, signalled
  token, so its cancellation is never lost.
- **Re-entrant lock.** ``render()`` holds the lock around
  ``send_characters()``, which takes it again.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from .floor import Admission, send_floors
from .frames import FrameCache, Grid


class OutputRuntime:
    """One board's send lock, cancel token, frame cache and write detector.

    Args:
        board_id: The board this runtime serves, for logs and identity.
            ``None`` for a client built outside the engine (a throwaway
            client in an API route), which gets a private runtime of its own.
        frames: The frame cache to start from; a fresh one by default. A
            virtual board passes its per-board shared "glass" here.
    """

    def __init__(self, board_id: str | None = None, *, frames: FrameCache | None = None) -> None:
        self.board_id = board_id
        self._send_lock = threading.RLock()
        self._cancel = threading.Event()
        self._frames = frames if frames is not None else FrameCache()
        # Generation of the dedupe cache the previous read-back mismatched
        # against, or None. See observe_read().
        self._external_suspect: int | None = None

    # --- frames ------------------------------------------------------------------

    @property
    def frames(self) -> FrameCache:
        """What the board shows (dedupe cache) and what was last sent (store)."""
        return self._frames

    def adopt_frames(self, frames: FrameCache) -> None:
        """Take over a driver's frame cache when the driver is bound here.

        The cache follows the driver exactly as it did when it was the
        driver's own attribute: binding a fresh client starts clean, and a
        virtual board keeps sharing its per-board "glass" with the throwaway
        clients an API route builds for the same board. Once every driver is
        built by its runtime (a later layer), the runtime creates the cache
        and this hand-off goes away.
        """
        self._frames = frames

    @property
    def last_frame(self) -> Grid | None:
        """The grid last sent to this board (survives a dedupe-cache clear)."""
        return self._frames.last_frame

    @property
    def last_sent_at(self) -> float | None:
        """When :attr:`last_frame` was sent, in epoch seconds."""
        return self._frames.last_sent_at

    # --- the send floor ----------------------------------------------------------

    def admit_send(
        self,
        device_key: str,
        floor_seconds: float,
        clock: Callable[[], float],
        is_unchanged: Callable[[], bool],
    ) -> Admission:
        """Floor, then dedupe, atomically; reserves the device's slot on "send".

        The floor is the device's (``device_key``), so it holds across client
        rebuilds and throwaway clients for the same board.
        """
        return send_floors().admit(device_key, floor_seconds, clock, is_unchanged)

    def release_send(self, admission: Admission) -> None:
        """The write failed: give the reserved slot back."""
        send_floors().release(admission)

    def hold_send(self, admission: Admission, floor_seconds: float, seconds: float) -> None:
        """The device asked to wait *seconds* (HTTP 429): keep it closed that long."""
        send_floors().hold(admission, floor_seconds, seconds)

    # --- external-write detection (#1946) ----------------------------------------

    @property
    def external_write_suspected(self) -> bool:
        """True after one read-back mismatched and no send has happened since."""
        return self._external_suspect is not None

    def observe_read(self, read: Callable[[], Grid | None]) -> tuple[Grid | None, bool]:
        """Read the board back and judge whether someone else wrote it.

        Returns ``(characters, external_write)``. ``characters`` is whatever
        *read* returned; ``external_write`` is True only on the **second**
        consecutive mismatch against the same, unchanged dedupe cache. One
        mismatch can be FiestaBoard's own send still propagating — the cloud
        read API lags a POST by seconds, and the cache is written only after
        the POST returns — while a genuine external write persists to the
        next poll. The cache's generation is read on both sides of the read,
        so any send (or cache sync or clear) in between restarts the cycle.

        A matching read never reports anything: it only proves the board
        shows FiestaBoard's last write, which may itself be out-of-band.
        """
        _, baseline = self._frames.snapshot()
        characters = read()
        if not characters:
            return characters, False
        current, generation = self._frames.snapshot()
        if current is None or generation != baseline:
            # No cache to judge against, or a send raced the read — whatever
            # was read proves nothing about external writers.
            self._external_suspect = None
            return characters, False
        if characters == current:
            self._external_suspect = None
            return characters, False
        if self._external_suspect == generation:
            # Second consecutive mismatch with no send in between.
            self._external_suspect = None
            return characters, True
        self._external_suspect = generation
        return characters, False

    @property
    def send_lock(self) -> threading.RLock:
        """The per-board lock serializing every device write."""
        return self._send_lock

    @property
    def cancel_event(self) -> threading.Event:
        """The current run's cancel token; send-retry backoffs wait on it."""
        return self._cancel

    @cancel_event.setter
    def cancel_event(self, event: threading.Event) -> None:
        # Replaces the current token. Only tests inject one directly; runs
        # install theirs through run().
        self._cancel = event

    def preempt(self) -> None:
        """Signal the current run to wind down. Never blocks."""
        self._cancel.set()

    @contextmanager
    def run(self) -> Iterator[threading.Event]:
        """Preempt the run in flight, take the lock, and yield a fresh token.

        The token is the one this run's transition runner watches; it is set
        when a later run (or :meth:`preempt`) supersedes this one.
        """
        self.preempt()
        with self._send_lock:
            token = threading.Event()
            self._cancel = token
            yield token
