"""Core per-board send policy, owned by the platform rather than the driver.

One :class:`OutputRuntime` exists per board. The display engine's
``BoardRuntime`` creates it and binds it to the board's client, which then
takes its send lock and cancel token from here instead of owning them.

This layer holds only the **send lock** and the **cancel token**. The rest
of the policy the output-plugin program moves into core (frame dedupe, the
send floor, transition driving, the last-frame store) still lives in the
clients and moves in later layers.

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
from collections.abc import Iterator
from contextlib import contextmanager


class OutputRuntime:
    """One board's send lock and cancel token.

    Args:
        board_id: The board this runtime serves, for logs and identity.
            ``None`` for a client built outside the engine (a throwaway
            client in an API route), which gets a private runtime of its own.
    """

    def __init__(self, board_id: str | None = None) -> None:
        self.board_id = board_id
        self._send_lock = threading.RLock()
        self._cancel = threading.Event()

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
