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
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

# Concurrency ceiling for board sends. Sends are already serialized per board
# by that board's send worker, so this only needs to cover a handful of boards
# being driven at once plus the occasional out-of-band send.
BOARD_SEND_MAX_WORKERS = 4

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()

T = TypeVar("T")


def get_board_send_executor() -> ThreadPoolExecutor:
    """Lazily create (once) the shared board-send pool."""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=BOARD_SEND_MAX_WORKERS, thread_name_prefix="board-send")
        return _executor


def shutdown_board_send_executor() -> None:
    """Shut down the board-send pool (process teardown and tests only).

    Safe to call repeatedly; a later send lazily creates a fresh pool.
    ``wait=False`` so a wedged board cannot stall shutdown.
    """
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


async def run_board_send(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """``asyncio.to_thread`` for board sends, on the dedicated bounded pool.

    Same contract as ``asyncio.to_thread``, context propagation included: runs
    *func* on a worker thread and awaits its result. Only the pool differs,
    which is the entire point — saturating it cannot starve the default
    executor every other blocking handler in the process depends on.
    """
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    return await loop.run_in_executor(get_board_send_executor(), functools.partial(ctx.run, func, *args, **kwargs))
