"""Tests for /transitions/* endpoint handlers.

Tests call the endpoint handler functions directly rather than going
through TestClient, because spinning up TestClient triggers the FastAPI
lifespan which initializes the plugin registry and the resulting
sys.modules pollution interferes with other plugin tests that patch
their own module's datetime.
"""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import HTTPException

from src.api_server import list_transition_plugins, preview_transition
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
