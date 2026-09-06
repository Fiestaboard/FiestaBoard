"""Watchdog tests: refresh/preview/send endpoints must not freeze the API.

PR #1809 moved the plugin install/update family off the event loop (#1750);
seven more ``async def`` handlers still did their blocking work inline — full
multi-board send passes, plugin-fan-out page renders, and board network sends
with up-to-seconds transition animations.  While any of them ran, the single
asyncio event loop was seized: the board stopped being driven, the web UI
hung, and ``GET /health`` did not answer (#1826).

These tests assert the *symptom* rather than the mechanism: a cheap endpoint
(``GET /health``) must answer while a slow request is still in flight.  Any
correct fix (``asyncio.to_thread``, ``run_in_executor``, a plain ``def``
handler) satisfies them; no particular one is required.
"""

import asyncio
import threading
import time
from unittest.mock import Mock, patch

import httpx
import pytest

from src.api_server import app

# Wall-clock cap on every blocking stub.  The worker keeps running after the
# request that started it, so an uncapped stub would wedge the suite; the cap
# is a safety valve, not the thing under test — the assertions below fire on
# ordering and latency, both of which resolve long before it.
_BLOCK_SECONDS = 5.0

# A blocked event loop cannot serve /health at all, so the bar only has to
# separate "answered immediately" from "answered after the blocking call".
_HEALTH_BUDGET_SECONDS = 0.5


def _blocking(release: threading.Event, result):
    """Return a callable that hangs until *release* is set, then returns *result*."""

    def _stub(*_args, **_kwargs):
        release.wait(_BLOCK_SECONDS)
        return result

    return _stub


async def _health_while_in_flight(request_factory):
    """Fire *request_factory* then race ``GET /health`` against it.

    Returns ``(health_response, seconds_waited, still_running)``.
    """
    release = threading.Event()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        # The stopwatch starts *before* the yield that lets the request reach
        # its handler: a blocking handler seizes the loop during that yield, so
        # timing only the /health await would measure the world after the block
        # had already ended and would pass either way.
        started = time.monotonic()
        in_flight = asyncio.create_task(request_factory(ac, release))
        await asyncio.sleep(0.05)

        health = await ac.get("/health")
        waited = time.monotonic() - started
        still_running = not in_flight.done()

        release.set()
        await in_flight

    return health, waited, still_running


def _assert_loop_stayed_free(health, waited, still_running, what: str):
    assert health.status_code == 200
    assert waited < _HEALTH_BUDGET_SECONDS, (
        f"/health waited {waited:.2f}s behind the {what} — the event loop was blocked"
    )
    assert still_running, f"the {what} finished too early to prove anything"


def _page_mock() -> Mock:
    """A page whose attributes are all real values, so responses serialize."""
    page = Mock()
    page.id = "p1"
    page.name = "Watchdog Page"
    page.type = "single"
    page.device_type = "flagship"
    page.notes_wide = None
    page.notes_tall = None
    page.template = None
    page.transition_strategy = None
    page.transition_interval_ms = None
    page.transition_step_size = None
    return page


def _preview_result_mock() -> Mock:
    return Mock(available=True, formatted="HELLO", display_type="text", raw=None, error=None)


def _transition_settings_mock() -> Mock:
    return Mock(strategy=None, step_interval_ms=None, step_size=None)


@pytest.mark.asyncio
async def test_a_slow_refresh_does_not_block_the_event_loop():
    """POST /refresh runs a full multi-board check-and-send pass inline."""

    async def _refresh(ac, release):
        service = Mock()
        service.check_and_send_active_page_with_status = _blocking(release, (True, None))
        with patch("src.api_server.get_service", return_value=service):
            return await ac.post("/refresh")

    health, waited, still_running = await _health_while_in_flight(_refresh)
    _assert_loop_stayed_free(health, waited, still_running, "refresh")


@pytest.mark.asyncio
async def test_a_slow_force_refresh_does_not_block_the_event_loop():
    """POST /force-refresh clears every client cache then does a full send pass."""

    async def _force_refresh(ac, release):
        service = Mock()
        service.vb_client = Mock()
        service.board_clients = {}
        service.check_and_send_active_page_with_status = _blocking(release, (True, None))
        with patch("src.api_server.get_service", return_value=service):
            return await ac.post("/force-refresh")

    health, waited, still_running = await _health_while_in_flight(_force_refresh)
    _assert_loop_stayed_free(health, waited, still_running, "force refresh")


@pytest.mark.asyncio
async def test_a_slow_page_preview_does_not_block_the_event_loop():
    """POST /pages/{id}/preview renders the page (plugin fan-out) inline."""

    async def _preview(ac, release):
        page_service = Mock()
        page_service.preview_page = _blocking(release, _preview_result_mock())
        settings = Mock()
        settings.get_active_page_id.return_value = None
        with (
            patch("src.api_server.get_page_service", return_value=page_service),
            patch("src.api_server.get_settings_service", return_value=settings),
        ):
            return await ac.post("/pages/p1/preview")

    health, waited, still_running = await _health_while_in_flight(_preview)
    _assert_loop_stayed_free(health, waited, still_running, "page preview")


@pytest.mark.asyncio
async def test_a_slow_batch_preview_does_not_block_the_event_loop():
    """POST /pages/preview/batch renders N pages in one call — the worst offender."""

    async def _batch(ac, release):
        page_service = Mock()
        page_service.preview_pages_batch = _blocking(release, {})
        settings = Mock()
        settings.get_active_page_id.return_value = None
        with (
            patch("src.api_server.get_page_service", return_value=page_service),
            patch("src.api_server.get_settings_service", return_value=settings),
        ):
            return await ac.post("/pages/preview/batch", json={"page_ids": ["p1", "p2"]})

    health, waited, still_running = await _health_while_in_flight(_batch)
    _assert_loop_stayed_free(health, waited, still_running, "batch preview")


@pytest.mark.asyncio
async def test_a_slow_current_display_lookup_does_not_block_the_event_loop():
    """GET /pages/current-display force-renders non-template pages inline."""

    async def _current_display(ac, release):
        settings = Mock()
        settings.is_schedule_enabled.return_value = False
        settings.get_active_page_id.return_value = "p1"
        page_service = Mock()
        page_service.get_page.return_value = _page_mock()
        page_service.preview_page = _blocking(release, _preview_result_mock())
        with (
            patch("src.api_server.get_settings_service", return_value=settings),
            patch("src.api_server.get_page_service", return_value=page_service),
            patch("src.api_server.get_collection_service", return_value=Mock()),
        ):
            return await ac.get("/pages/current-display")

    health, waited, still_running = await _health_while_in_flight(_current_display)
    _assert_loop_stayed_free(health, waited, still_running, "current-display lookup")


@pytest.mark.asyncio
async def test_a_slow_active_page_send_does_not_block_the_event_loop():
    """PUT /settings/active-page persists, renders, and sends to the board inline.

    The board send is the deep end: ``render`` drives the network call plus an
    up-to-seconds transition animation, all of which used to run on the loop.
    """

    async def _set_active(ac, release):
        settings = Mock()
        settings.should_send_to_board.return_value = True
        settings.get_primary_board_id.return_value = "board-1"
        settings.get_transition_settings.return_value = _transition_settings_mock()
        page_service = Mock()
        page_service.get_page.return_value = _page_mock()
        page_service.preview_page.return_value = _preview_result_mock()
        service = Mock()
        service.vb_client = Mock()
        service.vb_client.render = _blocking(release, (True, True))
        with (
            patch("src.api_server.get_settings_service", return_value=settings),
            patch("src.api_server.get_page_service", return_value=page_service),
            patch("src.api_server.get_service", return_value=service),
            patch("src.api_server.get_collection_service", return_value=Mock()),
            patch("src.api_server.check_ref_board_compatibility", return_value=Mock(ok=True, warnings=[])),
            patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False),
            patch("src.api_server._board_is_paused", return_value=False),
        ):
            return await ac.put("/settings/active-page", json={"page_id": "p1"})

    health, waited, still_running = await _health_while_in_flight(_set_active)
    _assert_loop_stayed_free(health, waited, still_running, "active-page send")


@pytest.mark.asyncio
async def test_a_slow_page_send_does_not_block_the_event_loop():
    """POST /pages/{id}/send renders fresh and sends to the board inline."""

    async def _send(ac, release):
        settings = Mock()
        settings.get_primary_board_id.return_value = "board-1"
        settings.get_transition_settings.return_value = _transition_settings_mock()
        page_service = Mock()
        page_service.get_page.return_value = _page_mock()
        page_service.preview_page.return_value = _preview_result_mock()
        service = Mock()
        service.vb_client = Mock()
        service.vb_client.render = _blocking(release, (True, True))
        with (
            patch("src.api_server.get_settings_service", return_value=settings),
            patch("src.api_server.get_page_service", return_value=page_service),
            patch("src.api_server.get_service", return_value=service),
            patch("src.api_server._silence_active", return_value=False),
            patch("src.api_server._board_is_paused", return_value=False),
        ):
            return await ac.post("/pages/p1/send?target=board")

    health, waited, still_running = await _health_while_in_flight(_send)
    _assert_loop_stayed_free(health, waited, still_running, "page send")


def test_concurrent_renders_on_one_client_serialize():
    """Two threads calling ``render`` on one client never overlap their sends.

    Off-loop handlers (#1826) can now hit the same ``BoardClient`` from two
    worker threads at once; the event loop used to serialize them for free.
    ``TransitionRenderMixin.render`` holds ``_send_lock`` around the whole
    send (including the ``_last_characters`` read-then-write inside
    ``send_characters``), so no new lock is required — this test pins that
    guarantee so it cannot be refactored away silently.
    """
    from src.board_client import BoardClient

    client = BoardClient.__new__(BoardClient)
    client._init_transition_state()

    active = threading.Semaphore(1)
    overlaps: list[str] = []
    calls: list[int] = []

    def _instrumented_send(characters, **_kwargs):
        if not active.acquire(blocking=False):
            overlaps.append("send_characters ran concurrently")
        try:
            calls.append(1)
            time.sleep(0.05)
        finally:
            active.release()
        return (True, True)

    client.send_characters = _instrumented_send

    grid = [[0] * 22 for _ in range(6)]
    threads = [threading.Thread(target=client.render, args=(grid,), kwargs={"force": True}) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls == [1, 1, 1, 1]
    assert overlaps == [], overlaps
