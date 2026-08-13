"""Tests for ``POST /plugins/{plugin_id}/options/{options_id}``.

The HTTP half of the generic plugin options primitive: authorization against
the manifest, off-loop dispatch, caching, and core-enforced sanitisation of
whatever the plugin hands back.
"""

import asyncio
import logging
import threading
import time
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.plugins.base import Option, OptionsRequest, OptionsResult, OptionsUnavailable

OPTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbols": {
            "type": "array",
            "ui:widget": "remote-options",
            "ui:options": {"options_id": "symbols"},
        },
    },
}


class _FakeManifest:
    """Just enough manifest for the route to read declared options ids."""

    def __init__(self, settings_schema: dict[str, Any]):
        self.settings_schema = settings_schema


class _FakeRegistry:
    """A registry stand-in that records every options dispatch."""

    def __init__(self) -> None:
        self.plugins: dict[str, object] = {"stocks": object()}
        self.manifests: dict[str, _FakeManifest] = {"stocks": _FakeManifest(OPTIONS_SCHEMA)}
        self.configs: dict[str, dict[str, Any]] = {"stocks": {"api_key": "real-key"}}
        self.calls: list[tuple[str, str, OptionsRequest, dict[str, Any] | None]] = []
        self.result: Any = OptionsResult(options=[Option(value="AAPL", label="Apple")])
        self.enabled: dict[str, bool] = {"stocks": True}

    # -- registry surface the route uses -------------------------------
    def get_plugin(self, plugin_id: str) -> object | None:
        return self.plugins.get(plugin_id)

    def get_manifest(self, plugin_id: str) -> _FakeManifest | None:
        return self.manifests.get(plugin_id)

    def get_plugin_config(self, plugin_id: str) -> dict[str, Any] | None:
        return self.configs.get(plugin_id)

    def is_enabled(self, plugin_id: str) -> bool:
        return self.enabled.get(plugin_id, False)

    def get_plugin_options(
        self,
        plugin_id: str,
        options_id: str,
        request: OptionsRequest,
        draft_config: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((plugin_id, options_id, request, draft_config))
        if callable(self.result):
            return self.result(plugin_id, options_id, request, draft_config)
        return self.result


@pytest.fixture
def registry(monkeypatch):
    """Install a fake plugin registry and reset the route's module state."""
    from src import api_server

    fake = _FakeRegistry()
    monkeypatch.setattr(api_server, "PLUGIN_SYSTEM_AVAILABLE", True)
    monkeypatch.setattr(api_server, "get_plugin_registry", lambda: fake)
    # Both caches are process-global; give every test its own.
    monkeypatch.setattr(api_server, "_PLUGIN_OPTIONS_CACHE", {})
    monkeypatch.setattr(api_server, "_plugin_options_last_refresh", {})
    return fake


@pytest.fixture
def client():
    return TestClient(app)


def _post(client: TestClient, plugin_id: str = "stocks", options_id: str = "symbols", **body: Any):
    return client.post(f"/plugins/{plugin_id}/options/{options_id}", json=body)


def test_an_options_id_the_manifest_never_declared_is_rejected(registry, client):
    """Without this the route is an arbitrary-string channel into plugin code."""
    response = _post(client, options_id="not_declared")

    assert response.status_code == 400
    assert registry.calls == [], "the plugin must not be dispatched at all"


def test_unknown_plugin_is_a_404(registry, client):
    """A missing plugin is not the same failure as a bad provider name."""
    response = _post(client, plugin_id="nope")

    assert response.status_code == 404


def test_plugin_system_unavailable_is_a_503(registry, client, monkeypatch):
    """No plugin system at all is an infrastructure problem, not a bad request."""
    from src import api_server

    monkeypatch.setattr(api_server, "PLUGIN_SYSTEM_AVAILABLE", False)

    response = _post(client)

    assert response.status_code == 503


def test_a_successful_lookup_returns_the_documented_envelope(registry, client):
    """The widget reads a fixed set of keys; all of them are always present."""
    registry.result = OptionsResult(
        options=[Option(value="AAPL", label="Apple", description="Apple Inc.", group="Tech", preview="AAPL 190")],
        has_more=True,
        cursor="page-2",
        total=42,
    )

    response = _post(client, query="app", limit=25, parent={"exchange": "NASDAQ"})

    assert response.status_code == 200
    assert response.json() == {
        "plugin_id": "stocks",
        "options_id": "symbols",
        "options": [
            {
                "value": "AAPL",
                "label": "Apple",
                "description": "Apple Inc.",
                "group": "Tech",
                "preview": "AAPL 190",
                "disabled": False,
                "meta": None,
            }
        ],
        "has_more": True,
        "cursor": "page-2",
        "total": 42,
        "error": None,
        "cached": False,
        "stale": False,
        "cache_seconds": 300,
    }


def test_the_request_body_reaches_the_plugin_as_an_options_request(registry, client):
    """``parent``/``query``/``limit``/``cursor`` are the plugin's search inputs."""
    _post(client, query="app", limit=25, parent={"exchange": "NASDAQ"}, cursor="page-1")

    (plugin_id, options_id, request, _draft) = registry.calls[0]
    assert plugin_id == "stocks"
    assert options_id == "symbols"
    assert isinstance(request, OptionsRequest)
    assert request.options_id == "symbols"
    assert request.parent == {"exchange": "NASDAQ"}
    assert request.query == "app"
    assert request.limit == 25
    assert request.cursor == "page-1"


def _raises(exc: BaseException):
    """Build a fake-registry behaviour that always raises *exc*."""

    def _behaviour(*_args: Any, **_kwargs: Any):
        raise exc

    return _behaviour


def test_a_plugin_that_does_not_implement_get_options_is_a_501(registry, client):
    """501 Not Implemented is the semantically correct answer, and it lets the
    widget fall back to a plain input instead of showing an error."""
    registry.result = _raises(NotImplementedError("Plugin stocks does not provide options"))

    response = _post(client)

    assert response.status_code == 501


def test_options_unavailable_is_a_200_carrying_the_reason(registry, client):
    """A not-configured-yet plugin is the expected mid-setup state. The widget
    needs an inline hint next to the field, not a red toast on a 5xx."""
    registry.result = _raises(OptionsUnavailable("Add an API key first"))

    response = _post(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] == "Add an API key first"
    assert payload["options"] == []


def test_an_unexpected_plugin_exception_is_a_502(registry, client):
    """A genuine bug in the plugin is an upstream failure, not a 500 on core."""
    registry.result = _raises(RuntimeError("boom"))

    response = _post(client)

    assert response.status_code == 502


def test_an_unexpected_plugin_exception_does_not_leak_its_text(registry, client):
    """Plugin tracebacks carry keys/URLs/paths. The 502 detail is a static
    message; the real exception goes to the server log only (CodeQL
    py/stack-trace-exposure, alert #72)."""
    registry.result = _raises(RuntimeError("SECRET_INTERNAL_XYZ token=abc123"))

    response = _post(client)

    assert response.status_code == 502
    assert "SECRET_INTERNAL_XYZ" not in response.text
    assert response.json()["detail"] == "Options provider failed"


def test_a_stale_fallback_does_not_leak_the_new_failures_text(registry, client):
    """The stale payload's ``error`` field is shown inline in the widget — it
    must describe the failure without echoing the raw exception (CodeQL
    py/stack-trace-exposure, alert #72)."""
    _post(client)
    registry.result = _raises(RuntimeError("SECRET_INTERNAL_XYZ token=abc123"))

    response = _post(client, refresh=True)

    assert response.status_code == 200
    assert "SECRET_INTERNAL_XYZ" not in response.text
    payload = response.json()
    assert payload["stale"] is True
    assert payload["error"] == "Options provider failed"


def _blocking_provider(release: threading.Event, seconds: float = 1.0):
    """A plugin behaviour that hangs until *release* is set (or *seconds* pass).

    The wall-clock cap is what keeps the suite bounded: the worker thread
    survives the route's timeout by design, and ``TestClient`` tears its
    portal down only once that thread has finished.
    """

    def _behaviour(*_args: Any, **_kwargs: Any):
        release.wait(seconds)
        return OptionsResult(options=[Option(value="late", label="Late")])

    return _behaviour


def test_a_plugin_that_hangs_gets_cut_off_with_a_504(registry, client, monkeypatch):
    """A settings dialog cannot wait on an unbounded upstream call."""
    from src import api_server

    monkeypatch.setattr(api_server, "PLUGIN_OPTIONS_TIMEOUT_SECONDS", 0.2)
    release = threading.Event()
    registry.result = _blocking_provider(release)

    try:
        response = _post(client)
    finally:
        release.set()

    assert response.status_code == 504


@pytest.mark.asyncio
async def test_a_slow_plugin_does_not_block_the_event_loop(registry, monkeypatch):
    """The load-bearing test for requirement 2.

    ``GET /plugins/{id}/data`` calls ``fetch_plugin_data`` inline inside an
    ``async def``, so one slow plugin stalls the whole process. Options are
    fetched on every keystroke in a settings search box, which would make that
    bug continuous rather than occasional. Assert directly on the symptom: a
    cheap endpoint must answer *while* a slow options lookup is in flight.
    """
    from src import api_server

    monkeypatch.setattr(api_server, "PLUGIN_OPTIONS_TIMEOUT_SECONDS", 2.0)
    release = threading.Event()
    registry.result = _blocking_provider(release, seconds=2.0)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        # The stopwatch has to start *before* the yield that lets the options
        # request reach its handler. A blocking handler seizes the loop during
        # that yield, so timing only the /health await would measure the world
        # after the block had already finished — and pass either way.
        started = time.monotonic()
        in_flight = asyncio.create_task(ac.post("/plugins/stocks/options/symbols", json={}))
        await asyncio.sleep(0.05)

        health = await ac.get("/health")
        waited = time.monotonic() - started
        still_running = not in_flight.done()

        release.set()
        await in_flight

    assert health.status_code == 200
    assert waited < 0.5, f"/health waited {waited:.2f}s behind the options call — the event loop was blocked"
    assert still_running, "the options call finished too early to prove anything"


def test_a_second_identical_call_inside_the_ttl_skips_the_plugin(registry, client):
    """A picker refetches on every keystroke; the upstream must not."""
    first = _post(client, query="app")
    second = _post(client, query="app")

    assert len(registry.calls) == 1, "the plugin was invoked twice for the same question"
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["options"] == first.json()["options"]


def _echo_plugin_id(plugin_id: str, _options_id: str, _request: OptionsRequest, _draft: Any) -> OptionsResult:
    """A behaviour whose answer identifies which install asked."""
    return OptionsResult(options=[Option(value=plugin_id, label=plugin_id)])


def test_two_instances_of_one_plugin_do_not_share_a_cache_entry(registry, client):
    """``stocks:growth`` and ``stocks:income`` are separate installs and must
    never be served each other's catalog.

    Both are given the *same* config on purpose: the config fingerprint would
    otherwise separate them on its own, and the point here is that the full
    instance key — not just the base plugin id — is part of the cache key.
    """
    for key in ("stocks:growth", "stocks:income"):
        registry.plugins[key] = object()
        registry.manifests[key] = _FakeManifest(OPTIONS_SCHEMA)
        registry.configs[key] = {"api_key": "shared-key"}
    registry.result = _echo_plugin_id

    growth = _post(client, plugin_id="stocks:growth")
    income = _post(client, plugin_id="stocks:income")

    assert len(registry.calls) == 2, "the second instance was served from the first instance's cache"
    assert growth.json()["options"][0]["value"] == "stocks:growth"
    assert income.json()["options"][0]["value"] == "stocks:income"


def test_a_config_change_invalidates_the_cache(registry, client):
    """The cache key fingerprints the effective config, so re-keying a plugin
    cannot serve the answers the old credentials produced."""
    _post(client)
    registry.configs["stocks"] = {"api_key": "a-different-key"}
    _post(client)

    assert len(registry.calls) == 2


def test_refresh_bypasses_the_cache(registry, client):
    """The widget's Retry button has to actually reach the upstream."""
    _post(client)
    response = _post(client, refresh=True)

    assert len(registry.calls) == 2
    assert response.json()["cached"] is False


def test_hammering_refresh_is_throttled(registry, client):
    """Retry bypasses the cache by design, so it is the one lever a stuck
    client can pull to hammer somebody else's API."""
    _post(client, refresh=True)
    second = _post(client, refresh=True)

    assert second.status_code == 429
    assert len(registry.calls) == 1


def test_the_refresh_throttle_is_per_question_not_global(registry, client):
    """One slow provider must not lock out Retry for every other field."""
    _post(client, refresh=True)
    other = _post(client, refresh=True, query="different")

    assert other.status_code == 200


def test_a_failing_refresh_falls_back_to_the_last_good_answer(registry, client):
    """A transient upstream failure should not empty a picker the user is
    already looking at — show yesterday's list and say that it is stale."""
    good = _post(client)
    registry.result = _raises(RuntimeError("upstream down"))

    response = _post(client, refresh=True)

    assert response.status_code == 200
    assert response.json()["stale"] is True
    assert response.json()["options"] == good.json()["options"]


def test_a_timeout_after_a_good_answer_also_serves_stale(registry, client, monkeypatch):
    """Same reasoning as a failing refresh: a hung upstream is not a reason to
    throw away a list we already have."""
    from src import api_server

    good = _post(client)
    monkeypatch.setattr(api_server, "PLUGIN_OPTIONS_TIMEOUT_SECONDS", 0.2)
    release = threading.Event()
    registry.result = _blocking_provider(release)

    try:
        response = _post(client, refresh=True)
    finally:
        release.set()

    assert response.status_code == 200
    assert response.json()["stale"] is True
    assert response.json()["options"] == good.json()["options"]


def _schema_with_cache_seconds(seconds: int) -> dict[str, Any]:
    """The standard options schema with an explicit per-provider TTL."""
    return {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "ui:widget": "remote-options",
                "ui:options": {"options_id": "symbols", "cache_seconds": seconds},
            },
        },
    }


def test_the_ttl_comes_from_the_providers_own_manifest_entry(registry, client):
    """A departure board goes stale in seconds; a list of airports does not.
    Only the plugin author knows which one this is."""
    registry.manifests["stocks"] = _FakeManifest(_schema_with_cache_seconds(60))

    response = _post(client)

    assert response.json()["cache_seconds"] == 60


def test_a_zero_ttl_disables_caching_entirely(registry, client):
    """``cache_seconds: 0`` is how a plugin says "always ask me"."""
    registry.manifests["stocks"] = _FakeManifest(_schema_with_cache_seconds(0))

    first = _post(client)
    second = _post(client)

    assert len(registry.calls) == 2
    assert first.json()["cache_seconds"] == 0
    assert second.json()["cached"] is False


def test_a_runaway_option_list_is_capped_with_has_more(registry, client):
    """Core enforces the ceiling so a buggy plugin cannot wedge the browser.

    The client asks for more than the ceiling to prove the ceiling is core's,
    not just the default page size doing the work.
    """
    registry.result = OptionsResult(options=[Option(value=i, label=f"Row {i}") for i in range(5000)])

    payload = _post(client, limit=5000).json()

    assert len(payload["options"]) == 1000
    assert payload["has_more"] is True


def test_the_requested_limit_is_honoured_below_the_ceiling(registry, client):
    """A picker that asked for 5 rows should not be handed 200."""
    registry.result = OptionsResult(options=[Option(value=i, label=f"Row {i}") for i in range(50)])

    payload = _post(client, limit=5).json()

    assert len(payload["options"]) == 5
    assert payload["has_more"] is True


def test_an_absurd_limit_is_clamped_rather_than_rejected(registry, client):
    """The clamp is on the way in, so the plugin never sees a silly number."""
    _post(client, limit=999_999)
    _post(client, limit=-4, query="second")

    assert registry.calls[0][2].limit == 1000
    assert registry.calls[1][2].limit == 1


def test_an_oversized_label_is_truncated_not_rejected(registry, client):
    """Dropping the option would lose data the user needs; a long label just
    breaks the layout, so trim it and keep the choice."""
    registry.result = OptionsResult(options=[Option(value="x", label="L" * 10_000)])

    option = _post(client).json()["options"][0]

    assert len(option["label"]) == 200
    assert option["value"] == "x"


def test_every_display_field_has_its_own_ceiling(registry, client):
    """Each field has a different amount of room in the picker."""
    registry.result = OptionsResult(
        options=[
            Option(
                value="x",
                label="L" * 500,
                description="D" * 500,
                preview="P" * 500,
                group="G" * 500,
            )
        ]
    )

    option = _post(client).json()["options"][0]

    assert (len(option["label"]), len(option["description"])) == (200, 200)
    assert (len(option["preview"]), len(option["group"])) == (120, 80)


def test_an_option_whose_value_is_not_a_json_scalar_is_dropped(registry, client):
    """``value`` is written verbatim into config.json. A dict there becomes an
    un-comparable blob that only fails much later, so refuse it at the door."""
    registry.result = OptionsResult(
        options=[
            SimpleNamespace(
                value={"nested": "object"},
                label="Bad",
                description=None,
                group=None,
                preview=None,
                disabled=False,
                meta=None,
            ),
            Option(value="good", label="Good"),
        ]
    )

    payload = _post(client).json()

    assert [o["value"] for o in payload["options"]] == ["good"]


def test_an_oversized_cursor_is_truncated(registry, client):
    """A continuation token is opaque, but it still has to fit in a request."""
    registry.result = OptionsResult(options=[], cursor="c" * 4000)

    assert len(_post(client).json()["cursor"]) == 512


def test_a_payload_over_the_byte_budget_is_trimmed(registry, client):
    """1000 options is a count ceiling, not a size one — 1000 fat options is
    still megabytes down a LAN connection to a Raspberry Pi."""
    registry.result = OptionsResult(
        options=[
            Option(value=i, label="L" * 200, description="D" * 200, preview="P" * 120, group="G" * 80)
            for i in range(1000)
        ]
    )

    # Ask for the full 1000 so the count ceiling cannot do the trimming for us.
    response = _post(client, limit=1000)
    payload = response.json()

    assert len(response.content) <= 512 * 1024
    assert len(payload["options"]) < 1000
    assert payload["has_more"] is True


def test_a_masked_secret_in_draft_config_is_replaced_with_the_stored_one(registry, client):
    """The settings form only ever holds ``"***"`` for a sensitive field, so
    forwarding the draft verbatim would hand the plugin a literal ``"***"`` as
    its API key and every lookup would fail while the user was mid-setup."""
    _post(client, draft_config={"api_key": "***", "exchange": "NASDAQ"})

    (_plugin_id, _options_id, _request, draft) = registry.calls[0]
    assert draft == {"api_key": "real-key", "exchange": "NASDAQ"}


def test_an_unmasked_secret_in_draft_config_is_passed_through(registry, client):
    """A key the user has just typed is the whole point of a draft config —
    the picker has to work before Save."""
    _post(client, draft_config={"api_key": "freshly-typed-key"})

    assert registry.calls[0][3] == {"api_key": "freshly-typed-key"}


def test_draft_config_values_are_never_logged(registry, client, caplog):
    """Debug logging around a settings dialog is exactly where credentials
    leak. Key names are useful; values are not worth the risk."""
    with caplog.at_level(logging.DEBUG, logger="src.api_server"):
        _post(client, draft_config={"api_key": "s3cr3t-do-not-log", "exchange": "NASDAQ"})

    assert "s3cr3t-do-not-log" not in caplog.text


def test_a_draft_config_changes_the_cache_key(registry, client):
    """Two different unsaved credentials must not read each other's answers."""
    _post(client, draft_config={"api_key": "first"})
    _post(client, draft_config={"api_key": "second"})

    assert len(registry.calls) == 2


def test_options_work_while_the_plugin_is_still_disabled(registry, client):
    """You browse the catalog *in order to* configure the plugin, and nobody
    enables a plugin before they have picked what it should show. Gating this
    on ``is_enabled`` — as ``GET /plugins/{id}/data`` does — would make the
    picker useless exactly when it is needed."""
    registry.enabled = {"stocks": False}

    response = _post(client)

    assert response.status_code == 200
    assert response.json()["options"] != []


@pytest.mark.asyncio
async def test_concurrent_lookups_cannot_exhaust_the_thread_pool(registry, monkeypatch):
    """``asyncio.to_thread`` shares one bounded default executor with the rest
    of the process. Without a cap, a plugin that is merely slow would let a
    settings dialog starve every other background call."""
    from src import api_server

    monkeypatch.setattr(api_server, "_PLUGIN_OPTIONS_SEMAPHORE", asyncio.Semaphore(2))
    monkeypatch.setattr(api_server, "PLUGIN_OPTIONS_TIMEOUT_SECONDS", 10.0)

    counter_lock = threading.Lock()
    state = {"in_flight": 0, "peak": 0}

    def _behaviour(*_args: Any, **_kwargs: Any):
        with counter_lock:
            state["in_flight"] += 1
            state["peak"] = max(state["peak"], state["in_flight"])
        time.sleep(0.1)
        with counter_lock:
            state["in_flight"] -= 1
        return OptionsResult(options=[Option(value="x", label="X")])

    registry.result = _behaviour

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        responses = await asyncio.gather(
            *(ac.post("/plugins/stocks/options/symbols", json={"query": f"q{i}"}) for i in range(8))
        )

    assert all(r.status_code == 200 for r in responses)
    assert state["peak"] <= 2, f"{state['peak']} lookups ran at once against a cap of 2"


@pytest.mark.asyncio
async def test_a_timed_out_lookup_holds_its_slot_until_the_thread_really_ends(registry, monkeypatch):
    """The cap only caps anything if it counts *threads*, not waiters.

    ``wait_for`` cancels the await, never the thread. Releasing the slot on
    timeout would let hung lookups free their slots one after another and start
    fresh threads forever, which is precisely the exhaustion the cap exists to
    prevent.
    """
    from src import api_server

    monkeypatch.setattr(api_server, "_PLUGIN_OPTIONS_SEMAPHORE", asyncio.Semaphore(1))
    monkeypatch.setattr(api_server, "PLUGIN_OPTIONS_TIMEOUT_SECONDS", 0.2)
    release = threading.Event()
    registry.result = _blocking_provider(release, seconds=3.0)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        first = await ac.post("/plugins/stocks/options/symbols", json={})
        assert first.status_code == 504, "the first lookup should have timed out"

        second = asyncio.create_task(ac.post("/plugins/stocks/options/symbols", json={"query": "other"}))
        await asyncio.sleep(0.2)
        # Count dispatches, not response timing: a naive implementation frees
        # the slot on timeout and the second lookup would already have started
        # its own thread by now, even though it will time out too.
        dispatches_while_stuck = len(registry.calls)

        release.set()
        await second

    assert dispatches_while_stuck == 1, "a second thread started while the abandoned one was still running"


def test_a_plugin_uninstalled_mid_dialog_is_a_404_not_a_502(registry, client):
    """The registry raises ``KeyError`` when the class has gone away — an
    uninstall racing an open settings dialog. That is still "no such plugin",
    not an upstream failure."""
    registry.result = _raises(KeyError("Cannot create sandbox instance for plugin: stocks"))

    response = _post(client)

    assert response.status_code == 404


def test_a_plugin_with_no_manifest_declares_no_providers(registry, client):
    """A plugin can be loaded with its manifest missing from the registry. It
    has declared nothing, so it authorizes nothing."""
    registry.manifests.pop("stocks")

    response = _post(client)

    assert response.status_code == 400
    assert registry.calls == []


def test_the_caches_are_bounded(registry, client, monkeypatch):
    """A settings search box makes one cache entry per keystroke, and this
    process runs for months."""
    from src import api_server

    monkeypatch.setattr(api_server, "PLUGIN_OPTIONS_CACHE_MAX_ENTRIES", 3)

    for i in range(8):
        _post(client, query=f"q{i}")
        _post(client, query=f"q{i}", refresh=True)

    assert len(api_server._PLUGIN_OPTIONS_CACHE) <= 3
    assert len(api_server._plugin_options_last_refresh) <= 4
