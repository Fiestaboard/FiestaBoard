"""Transition plugins outside the retired Transition Lab.

The Lab (``/transitions`` page and its ``/transitions/*`` beta API) is gone
(plan D22). What stays is the runtime: a page or board whose strategy is
``plugin:<id>`` still animates through ``TransitionRunner``, and the strategy
pickers find the installed transition plugins in ``GET /plugins`` by
``plugin_type`` — the listing they read now that ``/transitions/plugins`` is
removed.
"""

import asyncio
from collections.abc import Iterator

import pytest

from src.plugins.base import TransitionPluginBase
from src.plugins.manifest import PluginManifest


class _FakeTypewriter(TransitionPluginBase):
    @property
    def plugin_id(self) -> str:
        return "fake_typewriter"

    def generate_frames(self, from_grid, to_grid, device, config) -> Iterator[tuple[list[list[int]], int]]:
        yield [list(row) for row in from_grid], 100
        yield to_grid, 0


_TYPEWRITER_MANIFEST = {
    "id": "fake_typewriter",
    "name": "Fake Typewriter",
    "version": "1.0.0",
    "description": "test",
    "author": "test",
    "icon": "type",
    "category": "transition",
    "plugin_type": "transition",
    "settings_schema": {"type": "object", "properties": {}},
    "transition_settings": {
        "interruptible": True,
        "min_interval_ms": 25,
        "max_frames": 5,
        "max_runtime_seconds": 60,
    },
}


@pytest.fixture
def patched_registry(monkeypatch):
    """A blank registry holding one transition plugin, installed but NOT enabled.

    ``PluginRegistry.initialize()`` is skipped on purpose: it imports every
    plugin and clobbers ``sys.modules["plugins.<name>"]`` for other tests.
    """
    from src.plugins import registry as registry_mod

    fresh = registry_mod.PluginRegistry()
    plugin = _FakeTypewriter(_TYPEWRITER_MANIFEST)
    fresh._plugins["fake_typewriter"] = plugin
    fresh._manifests["fake_typewriter"] = PluginManifest.from_dict(_TYPEWRITER_MANIFEST)
    fresh._enabled["fake_typewriter"] = False
    plugin.config = {}
    monkeypatch.setattr(registry_mod, "_registry", fresh)
    yield fresh


def test_plugin_listing_reports_an_installed_transition_plugin_by_type(patched_registry, monkeypatch):
    """The pickers' source: ``GET /plugins`` lists a transition plugin as such,
    even disabled — installing one is opting in."""
    from src.plugins import routes as plugin_routes

    monkeypatch.setattr(plugin_routes, "_require_plugin_system", lambda: None)
    monkeypatch.setattr(plugin_routes, "get_plugin_registry", lambda: patched_registry)

    response = asyncio.run(plugin_routes.list_plugins())

    entry = next(p for p in response.plugins if p.id == "fake_typewriter")
    assert entry.plugin_type == "transition"
    assert entry.name == "Fake Typewriter"


def test_fetch_plugin_data_answers_cleanly_for_transition_plugins(patched_registry):
    """Data sweeps (variable discovery, displays) hit every enabled plugin;
    a transition plugin must yield an unavailable result, not AttributeError."""
    patched_registry._enabled["fake_typewriter"] = True
    result = patched_registry.fetch_plugin_data("fake_typewriter")
    assert result.available is False
    assert "transition" in (result.error or "").lower()


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
