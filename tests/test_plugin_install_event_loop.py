"""Watchdog tests: installing or updating a plugin must not freeze the API.

The plugin install/update endpoints shell out to ``git`` with timeouts of up
to 120 s.  Every one of them is an ``async def``, so running that subprocess
inline seizes the single asyncio event loop for its whole duration and the
entire web UI — every board, every page, every poll — stops answering until
the clone finishes (#1750).

These tests assert the *symptom* rather than the mechanism: a cheap endpoint
(``GET /health``) must answer while a slow install is still in flight.  Any
correct fix (``asyncio.to_thread``, ``run_in_executor``, a plain ``def``
handler) satisfies them; no particular one is required.
"""

import asyncio
import threading
import time
from pathlib import Path
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
# separate "answered immediately" from "answered after the git subprocess".
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
        # The stopwatch starts *before* the yield that lets the install reach
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


@pytest.mark.asyncio
async def test_a_slow_registry_install_does_not_block_the_event_loop():
    """POST /plugins/registry/{id}/install runs ``git fetch`` with a 120 s timeout."""

    async def _install(ac, release):
        registry = Mock()
        registry.install_from_registry = _blocking(release, [])
        with (
            patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True),
            patch("src.api_server.get_plugin_registry", return_value=registry),
        ):
            return await ac.post("/plugins/registry/dad_jokes/install")

    health, waited, still_running = await _health_while_in_flight(_install)
    _assert_loop_stayed_free(health, waited, still_running, "registry install")


@pytest.mark.asyncio
async def test_a_slow_git_install_does_not_block_the_event_loop():
    """POST /plugins/install clones an arbitrary repository over the network."""

    async def _install(ac, release):
        registry = Mock()
        registry.install_from_git = _blocking(release, [])
        with (
            patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True),
            patch("src.api_server.get_plugin_registry", return_value=registry),
            patch("src.plugins.sources.repo_name_from_url", return_value="fiestaboard-plugin--x"),
            patch("src.plugins.sources.plugin_id_from_repo_name", return_value="x"),
        ):
            return await ac.post("/plugins/install", json={"repository": "https://github.com/example/repo"})

    health, waited, still_running = await _health_while_in_flight(_install)
    _assert_loop_stayed_free(health, waited, still_running, "git install")


@pytest.mark.asyncio
async def test_a_slow_plugin_update_does_not_block_the_event_loop():
    """POST /plugins/{id}/update calls the same 120 s ``git fetch``."""

    async def _update(ac, release):
        registry = Mock()
        registry.get_plugin_source.return_value = Mock(source_type="external", local_path="/fake/path")
        registry.reload_plugin.return_value = Mock()
        registry._update_status = {}
        with (
            patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True),
            patch("src.api_server.get_plugin_registry", return_value=registry),
            patch("pathlib.Path.is_dir", return_value=True),
            patch("src.plugins.sources.get_external_plugins_dir", return_value=Path("/fake")),
            patch("src.plugins.sources.clone_or_update_repo", _blocking(release, (True, ""))),
        ):
            return await ac.post("/plugins/test_plugin/update")

    health, waited, still_running = await _health_while_in_flight(_update)
    _assert_loop_stayed_free(health, waited, still_running, "plugin update")


@pytest.mark.asyncio
async def test_a_slow_bulk_update_does_not_block_the_event_loop():
    """POST /plugins/updates/apply fetches every pending plugin in a loop."""

    async def _apply(ac, release):
        registry = Mock()
        registry.get_update_status.return_value = {"plugin_a": True}
        registry.get_plugin_source.return_value = Mock(source_type="external", local_path="/fake/path")
        registry.reload_plugin.return_value = Mock()
        registry._update_status = {"plugin_a": True}
        with (
            patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True),
            patch("src.api_server.get_plugin_registry", return_value=registry),
            patch("pathlib.Path.is_dir", return_value=True),
            patch("src.plugins.sources.get_external_plugins_dir", return_value=Path("/fake")),
            patch("src.plugins.sources.clone_or_update_repo", _blocking(release, (True, ""))),
        ):
            return await ac.post("/plugins/updates/apply")

    health, waited, still_running = await _health_while_in_flight(_apply)
    _assert_loop_stayed_free(health, waited, still_running, "bulk update")
