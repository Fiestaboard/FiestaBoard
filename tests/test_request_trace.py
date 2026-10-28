"""Correlated timeout diagnostics must be visible while a request is still stalled."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest

from tests.test_v1_contract import BLANK_FLAGSHIP, _seed_page, board_client, boards, client  # noqa: F401


def traces(caplog):
    return [record for record in caplog.records if record.name == "src.request_trace"]


def phases(caplog):
    return [record.trace_phase for record in traces(caplog)]


@pytest.mark.parametrize("body", [{"characters": BLANK_FLAGSHIP}, {"text": "private message"}])
def test_send_trace_is_visible_before_blocked_render_returns(client, boards, board_client, caplog, body):  # noqa: F811
    caplog.set_level(logging.INFO, logger="src.request_trace")
    entered, release = threading.Event(), threading.Event()

    def render(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return True, True

    board_client.render.side_effect = render
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, "/v1/boards/primary/message", json=body)
        try:
            assert entered.wait(3)
            assert phases(caplog) == [
                "request_started",
                "prepare_started",
                "prepare_returned",
                "worker_queued",
                "worker_started",
                "render_started",
            ]
            assert not future.done()
        finally:
            release.set()
        response = future.result(timeout=3)
    assert response.status_code == 200
    assert phases(caplog)[-7:] == [
        "render_returned",
        "after_send_started",
        "after_send_returned",
        "worker_returned",
        "await_returned",
        "response_started",
        "response_body_sent",
    ]
    trace_id = response.headers["X-FiestaBoard-Trace-ID"]
    UUID(trace_id)
    assert {record.trace_id for record in traces(caplog)} == {trace_id}
    assert all(record.elapsed_ms >= 0 for record in traces(caplog))
    assert "private message" not in " ".join(record.getMessage() for record in traces(caplog))


def test_page_save_trace_tracks_storage_and_cache_without_private_values(client, caplog):  # noqa: F811
    page_id = _seed_page(client)
    caplog.set_level(logging.INFO, logger="src.request_trace")
    response = client.put(
        f"/v1/pages/{page_id}?secret=query",
        json={"name": "private page name"},
        headers={"X-FiestaBoard-Trace-ID": "untrusted-trace"},
    )
    assert response.status_code == 200
    assert phases(caplog) == [
        "request_started",
        "page_update_started",
        "storage_started",
        "storage_returned",
        "cache_invalidation_started",
        "cache_invalidation_returned",
        "page_update_returned",
        "response_started",
        "response_body_sent",
    ]
    messages = " ".join(record.getMessage() for record in traces(caplog))
    assert all(secret not in messages for secret in (page_id, "private page name", "secret", "untrusted-trace"))
    assert {record.trace_id for record in traces(caplog)} == {response.headers["X-FiestaBoard-Trace-ID"]}


@pytest.mark.asyncio
async def test_final_body_marker_waits_for_send_return_and_context_does_not_leak(caplog):
    import asyncio

    from src.request_trace import RequestTraceMiddleware, trace_phase

    caplog.set_level(logging.INFO, logger="src.request_trace")
    sending, release = asyncio.Event(), asyncio.Event()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        await send({"type": "http.response.body", "body": b"last"})

    async def send(message):
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            sending.set()
            await release.wait()

    async def receive():
        raise AssertionError("Diagnostics must not consume the request body")

    middleware = RequestTraceMiddleware(app)
    task = asyncio.create_task(middleware({"type": "http", "method": "PUT", "path": "/pages/private"}, receive, send))
    try:
        await asyncio.wait_for(sending.wait(), 2)
        assert phases(caplog) == ["request_started", "response_started"]
    finally:
        release.set()
        await task
    assert phases(caplog) == ["request_started", "response_started", "response_body_sent"]
    caplog.clear()
    # Run again in this task, then test that the same context was reset.
    await middleware({"type": "http", "method": "PUT", "path": "/pages/private"}, receive, send)
    trace_phase("must_not_leak")
    assert "must_not_leak" not in phases(caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_terminal_error_marker_is_safe_and_context_is_reset(caplog, cancelled):
    import asyncio

    from src.request_trace import RequestTraceMiddleware, trace_phase

    caplog.set_level(logging.INFO, logger="src.request_trace")
    error = asyncio.CancelledError if cancelled else ValueError

    async def app(scope, receive, send):
        raise error("private exception detail")

    with pytest.raises(error):
        await RequestTraceMiddleware(app)({"type": "http", "method": "PUT", "path": "/v1/pages/private"}, None, None)
    assert phases(caplog) == ["request_started", "request_cancelled" if cancelled else "request_failed"]
    assert "private" not in " ".join(record.getMessage() for record in traces(caplog))
    trace_phase("must_not_leak")
    assert "must_not_leak" not in phases(caplog)


@pytest.mark.asyncio
async def test_unrelated_requests_do_not_emit_traces_or_headers(caplog):
    from src.request_trace import RequestTraceMiddleware, trace_phase

    caplog.set_level(logging.INFO, logger="src.request_trace")
    sent = []

    async def app(scope, receive, send):
        trace_phase("unrelated_work")
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(message):
        sent.append(message)

    for method, path in [("GET", "/v1/pages/private"), ("POST", "/health"), ("PUT", "/v1/pages/private/extra")]:
        await RequestTraceMiddleware(app)({"type": "http", "method": method, "path": path}, None, send)
    assert traces(caplog) == []
    assert all(message["headers"] == [] for message in sent)


@pytest.mark.asyncio
async def test_queue_wait_is_distinct_from_running_work_and_requests_have_unique_ids(caplog):
    import asyncio

    from src.board_send_executor import _BoundedPool
    from src.request_trace import RequestTraceMiddleware

    caplog.set_level(logging.INFO, logger="src.request_trace")
    pool = _BoundedPool(1, "trace-test")
    entered, release = threading.Event(), threading.Event()

    def work():
        entered.set()
        assert release.wait(5)

    async def app(scope, receive, send):
        await pool.run(work)

    middleware = RequestTraceMiddleware(app)
    scope = {"type": "http", "method": "POST", "path": "/v1/boards/private/message"}
    first = asyncio.create_task(middleware(scope, None, None))
    second = None
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        second = asyncio.create_task(middleware(scope, None, None))

        # Synchronize on queued log emission rather than guessing a worker delay.
        async def queued():
            while phases(caplog).count("worker_queued") != 2:
                await asyncio.sleep(0)

        await asyncio.wait_for(queued(), 2)
        assert phases(caplog).count("worker_started") == 1
        assert not first.done() and not second.done()
        ids = {record.trace_id for record in traces(caplog)}
        assert len(ids) == 2
    finally:
        release.set()
        await first
        if second is not None:
            await second
        pool.shutdown()
    for trace_id in ids:
        assert [record.trace_phase for record in traces(caplog) if record.trace_id == trace_id] == [
            "request_started",
            "worker_queued",
            "worker_started",
            "worker_returned",
            "await_returned",
        ]


def test_page_storage_stall_emits_entry_before_write_returns(client, monkeypatch, caplog):  # noqa: F811
    from src.pages.service import get_page_service

    page_id = _seed_page(client)
    storage = get_page_service().storage
    original_update = storage.update
    entered, release = threading.Event(), threading.Event()

    def blocked_update(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original_update(*args, **kwargs)

    monkeypatch.setattr(storage, "update", blocked_update)
    caplog.set_level(logging.INFO, logger="src.request_trace")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.put, f"/v1/pages/{page_id}", json={"name": "updated"})
        try:
            assert entered.wait(3)
            assert phases(caplog) == ["request_started", "page_update_started", "storage_started"]
            assert not future.done()
        finally:
            release.set()
        assert future.result(timeout=3).status_code == 200
    assert "storage_returned" in phases(caplog)
