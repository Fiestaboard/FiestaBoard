"""Live-editor previews cannot starve real board sends (#1878, second half).

#1892 moved every board-send endpoint off asyncio's default executor onto a
dedicated four-worker pool, which closed the audit's measurement: 40 concurrent
2s requests no longer take the whole shared pool. What it did NOT close is the
same failure mode *inside* that pool.

``POST /templates/render/live`` is the live template editor's send. Its own
handler calls it "rapid-fire": every keystroke in the editor is a board write,
and a board write is seconds of blocking network I/O (a cloud board paces
frames 15s apart). #1892 put it on the four-worker send pool alongside
``/refresh``, ``/force-refresh``, ``PUT /settings/active-page`` and
``POST /pages/{id}/send`` — so a handful of concurrent live previews occupies
every send worker and a real send, to a completely different board, queues
behind them.

The fix is the same shape as #1892's: previews get their own bounded pool, so
preview saturation degrades only previews.
"""

import asyncio
import threading
import time
from unittest.mock import Mock, patch

import httpx
import pytest

import src.board_send_executor as board_send_executor
from src.api_server import app
from src.board_send_executor import BOARD_PREVIEW_MAX_WORKERS, BOARD_SEND_MAX_WORKERS

# More concurrent live previews than the send pool has threads.
_CONCURRENT_PREVIEWS = 12
# Safety valve on the blocking stub; the assertions resolve long before it.
_BLOCK_SECONDS = 5.0
# A real send answering "promptly" means it did not queue behind the previews.
# The gap being measured is ~0.05s vs _BLOCK_SECONDS.
_BUDGET_SECONDS = 1.0
# How many previews must provably be blocking on a thread before the
# measurement. Deliberately the SMALLER of the two pool widths: post-fix only
# BOARD_PREVIEW_MAX_WORKERS previews can be on threads at once, so a floor of
# BOARD_SEND_MAX_WORKERS would be unreachable and the test would fail for the
# wrong reason. The claim that the send pool could have been consumed rests on
# ``outstanding`` below, which is measured the same way on both sides.
_BLOCKED_PREVIEWS_FLOOR = BOARD_PREVIEW_MAX_WORKERS

BOARD = {
    "id": "board-1",
    "name": "Board",
    "device_type": "flagship",
    "enabled": True,
    "api_mode": "local",
    "host": "mock-host",
    "port": 7000,
    "local_api_key": "k",
}


@pytest.fixture(autouse=True)
def _fresh_pools():
    board_send_executor.shutdown_board_send_executor()
    board_send_executor.shutdown_board_preview_executor()
    yield
    board_send_executor.shutdown_board_send_executor()
    board_send_executor.shutdown_board_preview_executor()


@pytest.mark.asyncio
async def test_live_preview_burst_does_not_starve_a_real_send():
    """N slow live previews must not delay ``POST /refresh``."""
    release = threading.Event()
    entered = threading.Semaphore(0)

    def _blocking_preview(*_args, **_kwargs):
        entered.release()
        release.wait(_BLOCK_SECONDS)
        return True, True

    preview_client = Mock()
    preview_client.send_characters = _blocking_preview

    engine = Mock()
    engine.render_lines.return_value = "\n".join(["HELLO"] + [""] * 5)

    settings = Mock()
    settings.get_board_settings.return_value = Mock(boards=[BOARD])
    settings.get_transition_settings.return_value = Mock(strategy="instant", step_interval_ms=0, step_size=1)

    service = Mock()
    service.check_and_send_active_page_with_status = lambda *a, **k: (True, None)

    body = {"template": ["HELLO", "", "", "", "", ""], "board_id": BOARD["id"]}

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            with (
                patch("src.templates.routes.get_template_engine", return_value=engine),
                patch("src.templates.routes.get_settings_service", return_value=settings),
                patch("src.api_server.get_settings_service", return_value=settings),
                # `_require_board` resolves the boards list through
                # `src.board_guards` since the pages slice moved it there, so
                # stubbing only `api_server` leaves the lookup 404ing.
                patch("src.board_guards.get_settings_service", return_value=settings),
                patch("src.templates.routes.board_client_from_board_dict", return_value=preview_client),
                patch("src.templates.routes._board_is_paused", return_value=False),
                # /refresh is still an api_server handler; the live preview
                # resolves its collaborators through src.templates.routes since
                # Phase 2 slice 8.
                patch("src.api_server.get_service", return_value=service),
            ):
                previews = [
                    asyncio.create_task(ac.post("/templates/render/live", json=body))
                    for _ in range(_CONCURRENT_PREVIEWS)
                ]

                deadline = time.monotonic() + 5.0
                occupied = 0
                while occupied < _BLOCKED_PREVIEWS_FLOOR and time.monotonic() < deadline:
                    if entered.acquire(blocking=False):
                        occupied += 1
                    else:
                        await asyncio.sleep(0.01)
                # Let the remaining previews reach the handler and queue.
                await asyncio.sleep(0.2)

                # Snapshotted BEFORE the measurement: a send that queues behind
                # the previews necessarily outlives them, so counting
                # afterwards would read the starvation under test as proof that
                # starvation was impossible.
                outstanding = sum(1 for t in previews if not t.done())

                started = time.monotonic()
                refresh = await ac.post("/refresh")
                waited = time.monotonic() - started

                release.set()
                await asyncio.gather(*previews)
    finally:
        release.set()

    # Non-vacuity: previews really were blocking on threads, and enough were
    # outstanding to have taken every thread of the send pool.
    assert occupied >= _BLOCKED_PREVIEWS_FLOOR, (
        f"only {occupied} previews reached a worker thread; the saturation never happened"
    )
    assert outstanding >= BOARD_SEND_MAX_WORKERS, (
        f"only {outstanding} previews were still in flight when the send ran; fewer than the "
        f"{BOARD_SEND_MAX_WORKERS}-thread send pool, so nothing was proven"
    )

    assert refresh.status_code == 200
    assert waited < _BUDGET_SECONDS, (
        f"a real board send waited {waited:.2f}s behind {_CONCURRENT_PREVIEWS} live-editor "
        "previews — previews and sends share one bounded pool"
    )


@pytest.mark.asyncio
async def test_run_board_preview_uses_its_own_pool():
    """The helper's contract, pinned directly rather than only through a route."""
    via_preview = await board_send_executor.run_board_preview(threading.current_thread)
    via_send = await board_send_executor.run_board_send(threading.current_thread)

    assert via_preview.name.startswith("board-preview")
    assert via_send.name.startswith("board-send")


@pytest.mark.asyncio
async def test_run_board_preview_forwards_arguments_and_propagates_exceptions():
    """Same call contract as ``asyncio.to_thread``, including the failure path."""

    def _work(a, *, b):
        if a == "boom":
            raise ValueError(b)
        return f"{a}-{b}"

    assert await board_send_executor.run_board_preview(_work, "x", b="y") == "x-y"
    with pytest.raises(ValueError, match="detail"):
        await board_send_executor.run_board_preview(_work, "boom", b="detail")
