"""A bounded, dedicated thread pool for board-send endpoints (issue #1878).

Every ``asyncio.to_thread`` call in the process — ~61 sites: plugin installs,
Wi-Fi scans, system updates, page previews, snapshot restores — shares
asyncio's *default* executor, whose size is ``min(32, cpu_count + 4)``. On a
four-core Pi that is eight threads for the whole application.

Board sends are the one family of blocking work that can hold a thread for
minutes rather than seconds. A queued send occupies its worker while merely
*blocked on the per-board send lock*, and a transition plugin can hold that
lock for its full runtime (up to the 120s manifest cap). So a handful of
concurrent sends can occupy every default-executor thread and starve unrelated
work: a plugin install, a Wi-Fi scan, a live-editor preview. Measured in the
Phase 2 audit: 40 concurrent 2s requests completed in exactly three waves of
18 workers.

Giving the send endpoints their own bounded pool decouples the two failure
modes. Send saturation now degrades only sends; the shared pool stays free for
everything else. The pool is deliberately SMALL: sends are serialized per board
by the send worker anyway (#1755), so extra threads would only queue deeper.

The same argument then applies one level down. ``POST /templates/render/live``
is the live template editor's board write, and its own handler calls it
"rapid-fire" — one board write per keystroke, each of them seconds of blocking
network I/O. Sharing the send pool with it recreated the original failure mode
inside the fix: measured here, a ``POST /refresh`` queued 14.80s behind twelve
concurrent live previews (three waves of the four send workers). Previews
therefore get a second, smaller pool of their own, so a burst of them degrades
only previews.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")


class _BoundedPool:
    """One lazily-created, bounded thread pool plus its ``to_thread`` helper.

    The two board pools are the same machinery with different bounds and
    thread names. The bounds and the separation are the whole point (see the
    module docstring); the lazy-init / lock / shutdown plumbing is not, so it
    lives here once.
    """

    def __init__(self, max_workers: int, thread_name_prefix: str) -> None:
        self._max_workers = max_workers
        self._thread_name_prefix = thread_name_prefix
        self._lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None

    def _get(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self._max_workers, thread_name_prefix=self._thread_name_prefix
                )
            return self._executor

    def shutdown(self) -> None:
        """Shut the pool down (process teardown and tests only).

        Safe to call repeatedly; a later submission lazily creates a fresh
        pool. ``wait=False`` so a wedged board cannot stall shutdown.
        """
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None

    async def run(self, func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
        """``asyncio.to_thread`` for this pool, context propagation included.

        Same contract as ``asyncio.to_thread``: runs *func* on a worker thread
        and awaits its result. Only the pool differs, which is the entire
        point — saturating one pool cannot starve the other, nor the default
        executor every other blocking handler in the process depends on.
        """
        loop = asyncio.get_running_loop()
        ctx = contextvars.copy_context()
        return await loop.run_in_executor(self._get(), functools.partial(ctx.run, func, *args, **kwargs))


# Concurrency ceiling for board sends. Sends are already serialized per board
# by that board's send worker, so this only needs to cover a handful of boards
# being driven at once plus the occasional out-of-band send.
BOARD_SEND_MAX_WORKERS = 4

# Concurrency ceiling for live-editor previews. Smaller than the send pool on
# purpose: a preview burst is one human typing, and the value of the pool is
# the BOUND, not the throughput. It must stay below BOARD_SEND_MAX_WORKERS so
# that even a preview flood cannot consume send capacity indirectly.
BOARD_PREVIEW_MAX_WORKERS = 2

_send_pool = _BoundedPool(BOARD_SEND_MAX_WORKERS, "board-send")
_preview_pool = _BoundedPool(BOARD_PREVIEW_MAX_WORKERS, "board-preview")

# Public API. Two pools, four entry points; the docstrings live on
# :class:`_BoundedPool` because both pools honour exactly the same contract.
run_board_send = _send_pool.run
shutdown_board_send_executor = _send_pool.shutdown

run_board_preview = _preview_pool.run
shutdown_board_preview_executor = _preview_pool.shutdown
