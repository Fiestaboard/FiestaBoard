"""Per-board send worker: runs board sends off the engine tick thread (#1755).

Transitions can hold a board's send for up to ~120s. When the engine tick
thread performed the send inline, one board's animation stalled every other
board, the 1 Hz silence-boundary detector, and collection rotation. Each
:class:`~src.main.BoardRuntime` now owns a :class:`BoardSendWorker`; the tick
thread computes everything (page resolution, render-to-array, dedupe) exactly
as before and hands the finished send to the worker as a :class:`SendJob`.

Queue discipline is **latest-wins**: a worker holds at most ONE pending job,
and a new submission replaces it — the board should always end up showing the
newest frame, never play back a backlog of stale ones. The job that is
*currently executing* is preempted through the existing client machinery: the
service signals the client's ``_cancel_transition`` event at enqueue time
(mirroring what ``render()`` itself does first-thing), so an in-flight
interruptible transition winds down promptly and the worker picks up the
replacement. Per-board serialization is unchanged — every send still funnels
through the client's ``_send_lock`` inside ``render()``.

A job replaced while still pending never runs; its waiters are adopted by the
replacement so a caller in ``wait=True`` mode (the ``*_with_status`` API
paths) observes the outcome of the send that actually superseded theirs.

Worker threads are daemon and demand-scoped: one drains the queue and exits
when it is empty, so idle boards (and the thousands of short-lived
``DisplayService`` instances the test suite creates) hold no live thread. A
wedged send cannot block :meth:`BoardSendWorker.stop` — the join is bounded —
so a runtime rebuild can always discard the old worker and start fresh.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class SendJob:
    """One board send plus its post-send bookkeeping, ready to execute.

    ``run`` performs the client ``render`` call and the engine's post-send
    bookkeeping, and returns the boolean the originating ``check_and_send``
    path would have returned inline; it must not raise. ``key`` identifies
    the send semantically (page id + content, "silence", ...) so the engine
    tick can tell "this exact send is already in flight" from "new content".

    ``sink``/``board_id`` (optional) are the submitter's send-error capture
    list and the board it belongs to (#1867 review): when a job resolves
    unsuccessfully WITH a reason it did not record itself — it was superseded
    and adopted, or failed by ``stop()`` before running — the reason is
    appended to that sink as ``(board_id, reason)`` so a ``wait=True`` caller
    (the ``*_with_status`` API paths) still learns WHY its send failed.
    The executing job's own bookkeeping writes its sink directly; it records
    the message in ``fail_reason`` so ``_finish`` can hand it to every
    adopted job's sink without double-writing its own.
    """

    def __init__(
        self,
        key: tuple,
        run: Callable[[], bool],
        sink: list | None = None,
        board_id=None,
    ):
        self.key = key
        self._run = run
        self.sink = sink
        self.board_id = board_id
        self.return_value = False
        self.fail_reason: str | None = None
        self._done = threading.Event()
        # Jobs this one replaced in the pending slot; they resolve with this
        # job's outcome (see BoardSendWorker.submit).
        self._absorbed: list[SendJob] = []

    def execute(self) -> None:
        """Run the send; always resolves this job and every absorbed one."""
        value = False
        try:
            value = self._run()
        finally:
            self._finish(value)

    def _finish(self, value: bool, reason: str | None = None) -> None:
        # A reason handed in from outside (adoption, stop()) is one this
        # job's own bookkeeping did NOT already write to its sink; deliver
        # it. A job that recorded its own failure (fail_reason already set
        # by its run callable) must not double-write its sink.
        if reason is not None and self.fail_reason is None:
            self.fail_reason = reason
            if self.sink is not None:
                self.sink.append((self.board_id, reason))
        self.return_value = value
        self._done.set()
        for job in self._absorbed:
            job._finish(value, self.fail_reason)
        self._absorbed = []

    def adopt(self, superseded: SendJob) -> None:
        """Take over a replaced pending job's waiters (latest-wins)."""
        self._absorbed.append(superseded)
        self._absorbed.extend(superseded._absorbed)
        superseded._absorbed = []

    def wait(self, timeout: float) -> bool:
        """Block until the job (or its replacement) resolves. True if it did."""
        return self._done.wait(timeout)


class BoardSendWorker:
    """Latest-wins send queue for one board, drained by a daemon thread."""

    def __init__(self, name: str):
        self._name = name
        self._cond = threading.Condition()
        self._pending: SendJob | None = None
        self._current: SendJob | None = None
        self._draining = False
        self._thread: threading.Thread | None = None
        self._stopped = False

    @property
    def stopped(self) -> bool:
        return self._stopped

    def submit(self, job: SendJob) -> SendJob:
        """Enqueue ``job``, replacing any still-pending one (latest-wins)."""
        with self._cond:
            if self._stopped:
                job._finish(False, reason="Board send worker is stopped; the send was not queued")
                return job
            if self._pending is not None:
                job.adopt(self._pending)
            self._pending = job
            if not self._draining:
                # _draining flips False only under this lock, right before the
                # drain thread exits, so a stale-but-alive thread can never
                # strand a freshly submitted job.
                self._draining = True
                self._thread = threading.Thread(target=self._drain, daemon=True, name=f"board-send-{self._name}")
                self._thread.start()
        return job

    def active_keys(self) -> set[tuple]:
        """Keys of the pending and currently-executing jobs (either may be absent)."""
        with self._cond:
            keys = set()
            if self._pending is not None:
                keys.add(self._pending.key)
            if self._current is not None:
                keys.add(self._current.key)
            return keys

    def wait_idle(self, timeout: float) -> bool:
        """Block (real time) until no job is pending or executing."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._pending is not None or self._current is not None or self._draining:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def stop(self, timeout: float = 1.0) -> None:
        """Refuse new work, fail the pending job, and join briefly.

        The join is bounded so a send wedged inside the client cannot block a
        runtime rebuild; the daemon drain thread is simply abandoned and its
        post-send bookkeeping is dropped by the caller's runtime-epoch guard.
        """
        with self._cond:
            self._stopped = True
            pending, self._pending = self._pending, None
            thread = self._thread
            self._cond.notify_all()
        if pending is not None:
            pending._finish(False, reason="Board send worker stopped before this send ran")
        if thread is not None and thread.is_alive():
            thread.join(timeout)

    def _drain(self) -> None:
        while True:
            with self._cond:
                job = self._pending
                self._pending = None
                if job is None or self._stopped:
                    self._draining = False
                    self._cond.notify_all()
                    if job is not None:
                        job._finish(False, reason="Board send worker stopped before this send ran")
                    return
                self._current = job
            try:
                job.execute()
            except Exception:  # execute() must not raise; survive anyway
                logger.exception("Board send worker %s: job raised unexpectedly", self._name)
            finally:
                with self._cond:
                    self._current = None
                    self._cond.notify_all()
