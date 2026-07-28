"""Tests for /transitions/* endpoint handlers.

Tests call the endpoint handler functions directly rather than going
through TestClient, because spinning up TestClient triggers the FastAPI
lifespan which initializes the plugin registry and the resulting
sys.modules pollution interferes with other plugin tests that patch
their own module's datetime.
"""

import asyncio
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import src.api_server as api_server
from src.api_server import (
    list_transition_plugins,
    preview_transition,
    restore_after_transition_test,
    run_live_transition_test,
)
from src.plugins.base import TransitionPluginBase
from src.plugins.manifest import PluginManifest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeTypewriter(TransitionPluginBase):
    @property
    def plugin_id(self) -> str:
        return "fake_typewriter"

    def generate_frames(self, from_grid, to_grid, device, config) -> Iterator[tuple[list[list[int]], int]]:
        intermediate = [list(row) for row in from_grid]
        yield intermediate, int(config.get("frame_interval_ms", 100))
        yield to_grid, 0


class _FakeForever(TransitionPluginBase):
    @property
    def plugin_id(self) -> str:
        return "fake_forever"

    def generate_frames(self, from_grid, to_grid, device, config):
        while True:
            yield to_grid, 10


_TYPEWRITER_MANIFEST = {
    "id": "fake_typewriter",
    "name": "Fake Typewriter",
    "version": "1.0.0",
    "description": "test",
    "author": "test",
    "icon": "type",
    "category": "transition",
    "plugin_type": "transition",
    "settings_schema": {
        "type": "object",
        "properties": {"frame_interval_ms": {"type": "integer", "default": 100}},
    },
    "transition_settings": {
        "interruptible": True,
        "min_interval_ms": 25,
        "max_frames": 5,
        "max_runtime_seconds": 60,
    },
}

_FOREVER_MANIFEST = {
    "id": "fake_forever",
    "name": "Fake Forever",
    "version": "1.0.0",
    "description": "test",
    "author": "test",
    "icon": "infinity",
    "category": "transition",
    "plugin_type": "transition",
    "settings_schema": {"type": "object", "properties": {}},
    "transition_settings": {
        "interruptible": True,
        "min_interval_ms": 1,
        "max_frames": 3,
        "max_runtime_seconds": 60,
    },
}


@pytest.fixture(autouse=True)
def _enable_transitions_beta(monkeypatch):
    """Enable the beta flag for every test in this file.

    The /transitions endpoints are gated behind
    ``beta.transition_plugins_enabled``; without this fixture the
    handlers would return 404 before reaching the registry.
    """
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    original = settings.get_beta_settings().transition_plugins_enabled
    settings.update_beta_settings({"transition_plugins_enabled": True})
    yield
    settings.update_beta_settings({"transition_plugins_enabled": original})


@pytest.fixture
def patched_registry(monkeypatch):
    """Swap the global plugin registry singleton for a hand-built stub.

    We deliberately skip ``PluginRegistry.initialize()`` -- that method
    loads every plugin via importlib.util and clobbers
    ``sys.modules["plugins.<name>"]``, which would break other plugin
    test files that hold imported references to those modules.
    Instead we construct a blank registry and inject only the fakes we
    need.  After the test, the original singleton is restored.
    """
    from src.plugins import registry as registry_mod

    # Build a fresh, uninitialized registry.  ``PluginRegistry.__init__``
    # constructs a loader but doesn't scan/import anything.
    fresh = registry_mod.PluginRegistry()

    type_plug = _FakeTypewriter(_TYPEWRITER_MANIFEST)
    forever_plug = _FakeForever(_FOREVER_MANIFEST)
    fresh._plugins["fake_typewriter"] = type_plug
    fresh._plugins["fake_forever"] = forever_plug
    fresh._manifests["fake_typewriter"] = PluginManifest.from_dict(_TYPEWRITER_MANIFEST)
    fresh._manifests["fake_forever"] = PluginManifest.from_dict(_FOREVER_MANIFEST)
    fresh._enabled["fake_typewriter"] = True
    fresh._enabled["fake_forever"] = True
    type_plug.config = {"frame_interval_ms": 50}
    forever_plug.config = {}

    monkeypatch.setattr(registry_mod, "_registry", fresh)
    yield fresh


def _run(coro):
    """Synchronously run an async endpoint coroutine."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# list_transition_plugins
# ---------------------------------------------------------------------------


def test_list_transition_plugins_returns_enabled(patched_registry):
    data = _run(list_transition_plugins())
    ids = {p["id"] for p in data["plugins"]}
    assert {"fake_typewriter", "fake_forever"} <= ids


def test_list_transition_plugins_includes_settings_schema(patched_registry):
    data = _run(list_transition_plugins())
    by_id = {p["id"]: p for p in data["plugins"]}
    tw = by_id["fake_typewriter"]
    assert tw["settings_schema"]["properties"]["frame_interval_ms"]["default"] == 100
    assert tw["transition_settings"]["max_frames"] == 5
    assert tw["strategy"] == "plugin:fake_typewriter"


def test_list_transition_plugins_excludes_disabled(patched_registry):
    patched_registry._enabled["fake_typewriter"] = False
    data = _run(list_transition_plugins())
    ids = {p["id"] for p in data["plugins"]}
    assert "fake_typewriter" not in ids


def test_list_transition_plugins_omits_data_plugins(patched_registry):
    """Only TransitionPluginBase subclasses should be listed."""
    data = _run(list_transition_plugins())
    for entry in data["plugins"]:
        assert entry["strategy"].startswith("plugin:")


# ---------------------------------------------------------------------------
# preview_transition
# ---------------------------------------------------------------------------


def test_preview_requires_plugin_id(patched_registry):
    with pytest.raises(HTTPException) as exc:
        _run(preview_transition({"to_text": "HELLO"}))
    assert exc.value.status_code == 400


def test_preview_unknown_plugin_returns_404(patched_registry):
    with pytest.raises(HTTPException) as exc:
        _run(preview_transition({"plugin_id": "ghost", "to_text": "HELLO"}))
    assert exc.value.status_code == 404


def test_preview_returns_frames_with_grid_and_delay(patched_registry):
    data = _run(
        preview_transition(
            {
                "plugin_id": "fake_typewriter",
                "from_text": "",
                "to_text": "HELLO",
                "device_type": "flagship",
                "config": {"frame_interval_ms": 50},
            }
        )
    )
    assert data["plugin_id"] == "fake_typewriter"
    assert data["device_type"] == "flagship"
    assert data["frame_count"] == 2
    for frame in data["frames"]:
        assert len(frame["grid"]) == 6
        assert all(len(row) == 22 for row in frame["grid"])
        assert isinstance(frame["delay_ms"], int)
    # Total delay = 50 + max(0, 25) (clamped to min_interval_ms).
    assert data["total_delay_ms"] == 50 + 25


def test_preview_honors_max_frames_cap_and_sets_capped(patched_registry):
    """Forever plugin yields infinitely; preview caps at max_frames=3."""
    data = _run(
        preview_transition(
            {
                "plugin_id": "fake_forever",
                "from_text": "",
                "to_text": "X",
                "device_type": "flagship",
            }
        )
    )
    assert data["frame_count"] == 3
    assert data["capped"] is True


def test_preview_rejects_bad_device_type(patched_registry):
    with pytest.raises(HTTPException) as exc:
        _run(preview_transition({"plugin_id": "fake_typewriter", "to_text": "HI", "device_type": "wat"}))
    assert exc.value.status_code == 400


def test_preview_handles_note_device(patched_registry):
    data = _run(
        preview_transition(
            {
                "plugin_id": "fake_typewriter",
                "to_text": "HI",
                "device_type": "note",
            }
        )
    )
    for frame in data["frames"]:
        assert len(frame["grid"]) == 3
        assert all(len(row) == 15 for row in frame["grid"])


# ---------------------------------------------------------------------------
# Beta gating
# ---------------------------------------------------------------------------


def test_endpoints_404_when_beta_disabled(patched_registry):
    """With the beta flag off, both endpoints return 404."""
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    settings.update_beta_settings({"transition_plugins_enabled": False})
    try:
        with pytest.raises(HTTPException) as exc:
            _run(list_transition_plugins())
        assert exc.value.status_code == 404
        assert "beta" in exc.value.detail.lower()

        with pytest.raises(HTTPException) as exc:
            _run(preview_transition({"plugin_id": "fake_typewriter", "to_text": "HI"}))
        assert exc.value.status_code == 404
    finally:
        settings.update_beta_settings({"transition_plugins_enabled": True})


# ---------------------------------------------------------------------------
# Integration seams surfaced by mock-board e2e
# ---------------------------------------------------------------------------


def test_fetch_plugin_data_answers_cleanly_for_transition_plugins(patched_registry):
    """Data sweeps (variable discovery, displays) hit every enabled plugin;
    a transition plugin must yield an unavailable result, not AttributeError."""
    result = patched_registry.fetch_plugin_data("fake_typewriter")
    assert result.available is False
    assert "transition" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# run_live_transition_test / restore_after_transition_test
# ---------------------------------------------------------------------------


class _FakeBoardClient:
    """Records send_characters/render calls; always reports success."""

    def __init__(self):
        self.calls = []

    def send_characters(self, grid, strategy=None, force=False, **kwargs):
        self.calls.append(("send", strategy, force))
        return (True, True)

    def render(self, grid, strategy=None, force=False, device_type=None, transition_config=None, **kwargs):
        self.calls.append(("render", strategy, device_type, transition_config))
        return (True, True)


class _FakePageService:
    """Serves two flagship template pages: page-from and page-to."""

    def __init__(self):
        self.pages = {
            pid: SimpleNamespace(id=pid, device_type="flagship", notes_wide=None, notes_tall=None)
            for pid in ("page-from", "page-to")
        }

    def get_page(self, page_id):
        return self.pages.get(page_id)

    def preview_page(self, page_id, force_refresh=False):
        if page_id not in self.pages:
            return None
        return SimpleNamespace(available=True, formatted="HELLO", error=None)


@pytest.fixture
def live_env(monkeypatch, patched_registry):
    """Wire the live-test endpoints to fakes: board client, page service,
    no silence, no pause, zero from-page hold."""
    board_client = _FakeBoardClient()
    fake_service = SimpleNamespace(vb_client=board_client, get_board_client=lambda board_id: board_client)
    monkeypatch.setattr(api_server, "get_service", lambda: fake_service)
    monkeypatch.setattr(api_server, "get_page_service", _FakePageService)
    monkeypatch.setattr(api_server.Config, "is_silence_mode_active", staticmethod(lambda: False))
    monkeypatch.setattr(api_server, "_board_is_paused", lambda board_id=None: False)
    monkeypatch.setattr(api_server, "LIVE_TEST_FROM_HOLD_SECONDS", 0)
    return board_client


def test_live_requires_plugin_id(live_env):
    with pytest.raises(HTTPException) as exc:
        _run(run_live_transition_test({"to_page_id": "page-to"}))
    assert exc.value.status_code == 400


def test_live_requires_to_page_id(live_env):
    with pytest.raises(HTTPException) as exc:
        _run(run_live_transition_test({"plugin_id": "fake_typewriter"}))
    assert exc.value.status_code == 400


def test_live_unknown_plugin_returns_404(live_env):
    with pytest.raises(HTTPException) as exc:
        _run(run_live_transition_test({"plugin_id": "ghost", "to_page_id": "page-to"}))
    assert exc.value.status_code == 404


def test_live_unknown_page_returns_404(live_env):
    with pytest.raises(HTTPException) as exc:
        _run(run_live_transition_test({"plugin_id": "fake_typewriter", "to_page_id": "nope"}))
    assert exc.value.status_code == 404


def test_live_snaps_from_page_then_runs_plugin(live_env):
    data = _run(
        run_live_transition_test(
            {
                "plugin_id": "fake_typewriter",
                "from_page_id": "page-from",
                "to_page_id": "page-to",
                "config": {"frame_interval_ms": 30},
            }
        )
    )
    assert data["status"] == "success"
    assert data["sent"] is True
    # First a forced plain snap to the from-page, then the plugin render.
    assert live_env.calls[0] == ("send", None, True)
    kind, strategy, device_type, config = live_env.calls[1]
    assert (kind, strategy, device_type) == ("render", "plugin:fake_typewriter", "flagship")
    # Override merged on top of the plugin's bound config ({frame_interval_ms: 50}).
    assert config == {"frame_interval_ms": 30}


def test_live_without_from_page_skips_snap(live_env):
    data = _run(run_live_transition_test({"plugin_id": "fake_typewriter", "to_page_id": "page-to"}))
    assert data["status"] == "success"
    assert [c[0] for c in live_env.calls] == ["render"]


def test_live_blocked_by_silence_mode(live_env, monkeypatch):
    monkeypatch.setattr(api_server.Config, "is_silence_mode_active", staticmethod(lambda: True))
    with pytest.raises(HTTPException) as exc:
        _run(run_live_transition_test({"plugin_id": "fake_typewriter", "to_page_id": "page-to"}))
    assert exc.value.status_code == 409


def test_live_blocked_when_board_paused(live_env, monkeypatch):
    monkeypatch.setattr(api_server, "_board_is_paused", lambda board_id=None: True)
    with pytest.raises(HTTPException) as exc:
        _run(run_live_transition_test({"plugin_id": "fake_typewriter", "to_page_id": "page-to"}))
    assert exc.value.status_code == 409


def test_restore_sends_active_page_plainly(live_env, monkeypatch):
    fake_settings = SimpleNamespace(
        get_active_page_id=lambda board_id=None: "page-to",
        get_beta_settings=lambda: SimpleNamespace(transition_plugins_enabled=True),
    )
    monkeypatch.setattr(api_server, "get_settings_service", lambda: fake_settings)
    data = _run(restore_after_transition_test({}))
    assert data["status"] == "success"
    assert data["page_id"] == "page-to"
    # Restore is a plain render (no transition strategy).
    assert live_env.calls == [("render", None, None, None)]


def test_restore_without_active_page_returns_404(live_env, monkeypatch):
    fake_settings = SimpleNamespace(
        get_active_page_id=lambda board_id=None: None,
        get_beta_settings=lambda: SimpleNamespace(transition_plugins_enabled=True),
    )
    monkeypatch.setattr(api_server, "get_settings_service", lambda: fake_settings)
    with pytest.raises(HTTPException) as exc:
        _run(restore_after_transition_test({}))
    assert exc.value.status_code == 404


def test_live_endpoints_404_when_beta_disabled(live_env):
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    settings.update_beta_settings({"transition_plugins_enabled": False})
    try:
        with pytest.raises(HTTPException) as exc:
            _run(run_live_transition_test({"plugin_id": "fake_typewriter", "to_page_id": "page-to"}))
        assert exc.value.status_code == 404

        with pytest.raises(HTTPException) as exc:
            _run(restore_after_transition_test({}))
        assert exc.value.status_code == 404
    finally:
        settings.update_beta_settings({"transition_plugins_enabled": True})


def test_page_create_persists_transition_fields(tmp_path):
    """PageCreate.transition_* must survive create_page (not only update_page).

    Regression: create_page dropped the three transition fields, so a page
    created with a plugin strategy silently sent with no animation.
    """
    from src.pages.models import PageCreate
    from src.pages.service import PageService
    from src.pages.storage import PageStorage

    service = PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))
    page = service.create_page(
        PageCreate(
            name="Transition Persist",
            type="template",
            template=["HELLO"],
            transition_strategy="plugin:fake_typewriter",
            transition_interval_ms=50,
            transition_step_size=2,
        )
    )
    stored = service.get_page(page.id)
    assert stored.transition_strategy == "plugin:fake_typewriter"
    assert stored.transition_interval_ms == 50
    assert stored.transition_step_size == 2
