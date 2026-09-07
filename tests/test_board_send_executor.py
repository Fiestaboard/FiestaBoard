"""Board sends get their own bounded pool so they cannot starve the app (#1878).

Every ``asyncio.to_thread`` site in the process shares asyncio's default
executor — ``min(32, cpu_count + 4)``, i.e. eight threads on a four-core Pi.
Board sends are the one blocking family that can hold a thread for minutes: a
queued send occupies its worker while merely blocked on the per-board send
lock, and a transition plugin can hold that lock for its full runtime (up to
the 120s manifest cap). A handful of concurrent sends therefore takes the whole
shared pool and stalls unrelated blocking work — plugin installs, Wi-Fi scans,
page previews.

The test shrinks the default executor to the Pi's size so the arithmetic is
deterministic, saturates it with concurrent board sends, and then asks an
unrelated ``asyncio.to_thread`` endpoint (``POST /pages/{id}/preview``) for an
answer. It must arrive promptly.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import httpx
import pytest

import src.board_send_executor as board_send_executor
from src.api_server import app

# Stand-in for the shared pool on a four-core Pi.
_DEFAULT_EXECUTOR_WORKERS = 8
# More concurrent sends than that pool has threads.
_CONCURRENT_SENDS = 12
# Safety valve on the blocking stub; the assertions resolve long before it.
_BLOCK_SECONDS = 5.0
# An unrelated to_thread endpoint answering "promptly" means it did not queue
# behind a send. The gap being measured is 0.05s vs _BLOCK_SECONDS.
_BUDGET_SECONDS = 1.0
# How many sends must be provably blocking on a thread before the measurement.
# Below both pool sizes so the wait means the same thing on both sides of the fix.
_BLOCKED_SENDS_FLOOR = 3


@pytest.fixture(autouse=True)
def _fresh_send_pool():
    board_send_executor.shutdown_board_send_executor()
    yield
    board_send_executor.shutdown_board_send_executor()


def _preview_result_mock() -> Mock:
    return Mock(available=True, formatted="HELLO", display_type="text", raw=None, error=None)


@pytest.mark.asyncio
async def test_concurrent_board_sends_do_not_starve_unrelated_thread_work():
    """N slow sends must not delay an unrelated ``to_thread`` endpoint."""
    loop = asyncio.get_running_loop()
    shared = ThreadPoolExecutor(max_workers=_DEFAULT_EXECUTOR_WORKERS, thread_name_prefix="shared-pool")
    loop.set_default_executor(shared)

    release = threading.Event()
    entered = threading.Semaphore(0)

    def _blocking_send(*_args, **_kwargs):
        entered.release()
        release.wait(_BLOCK_SECONDS)
        return True, None

    service = Mock()
    service.check_and_send_active_page_with_status = _blocking_send
    page_service = Mock()
    page_service.preview_page.return_value = _preview_result_mock()
    settings = Mock()
    settings.get_active_page_id.return_value = None

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            with (
                patch("src.api_server.get_service", return_value=service),
                patch("src.api_server.get_page_service", return_value=page_service),
                patch("src.api_server.get_settings_service", return_value=settings),
            ):
                sends = [asyncio.create_task(ac.post("/refresh")) for _ in range(_CONCURRENT_SENDS)]

                # Wait until sends are genuinely blocking on worker threads.
                # The floor is below BOTH pool sizes so the wait means the same
                # thing before and after the fix; the non-vacuity claim below
                # rests on how many sends are OUTSTANDING, which is what would
                # have consumed the shared pool.
                deadline = time.monotonic() + 5.0
                occupied = 0
                while occupied < _BLOCKED_SENDS_FLOOR and time.monotonic() < deadline:
                    if entered.acquire(blocking=False):
                        occupied += 1
                    else:
                        await asyncio.sleep(0.01)
                # Let the remaining sends reach the handler and queue.
                await asyncio.sleep(0.2)

                # Snapshotted BEFORE the measurement: if the preview queues
                # behind the sends it necessarily outlives them, so counting
                # afterwards would count the very starvation under test as
                # evidence that no starvation was possible.
                outstanding = sum(1 for t in sends if not t.done())

                started = time.monotonic()
                preview = await ac.post("/pages/p1/preview")
                waited = time.monotonic() - started

                release.set()
                await asyncio.gather(*sends)
    finally:
        release.set()
        shared.shutdown(wait=False)

    # Non-vacuity: sends really were blocking on threads, and enough of them
    # were outstanding to have taken every thread of the shared pool.
    assert occupied >= _BLOCKED_SENDS_FLOOR, (
        f"only {occupied} sends reached a worker thread; the saturation never happened"
    )
    assert outstanding >= _DEFAULT_EXECUTOR_WORKERS, (
        f"only {outstanding} sends were still in flight when the preview ran; "
        f"fewer than the {_DEFAULT_EXECUTOR_WORKERS}-thread shared pool, so nothing was proven"
    )

    assert preview.status_code == 200
    assert waited < _BUDGET_SECONDS, (
        f"an unrelated to_thread endpoint waited {waited:.2f}s behind {_CONCURRENT_SENDS} "
        "board sends — the sends are on the shared default executor"
    )


@pytest.mark.asyncio
async def test_run_board_send_uses_the_dedicated_pool_not_the_default_executor():
    """The helper's contract, pinned directly rather than only through a route."""
    loop = asyncio.get_running_loop()
    shared = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shared-pool")
    loop.set_default_executor(shared)
    try:
        via_helper = await board_send_executor.run_board_send(threading.current_thread)
        via_to_thread = await asyncio.to_thread(threading.current_thread)
    finally:
        shared.shutdown(wait=False)

    assert via_helper.name.startswith("board-send")
    assert via_to_thread.name.startswith("shared-pool")


@pytest.mark.asyncio
async def test_run_board_send_forwards_arguments_and_propagates_exceptions():
    """Same call contract as ``asyncio.to_thread``, including the failure path."""

    def _work(a, *, b):
        if a == "boom":
            raise ValueError(b)
        return f"{a}-{b}"

    assert await board_send_executor.run_board_send(_work, "x", b="y") == "x-y"
    with pytest.raises(ValueError, match="detail"):
        await board_send_executor.run_board_send(_work, "boom", b="detail")
