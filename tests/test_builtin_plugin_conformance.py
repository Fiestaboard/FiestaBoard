"""Every bundled plugin must render on every board shape the platform supports.

This is the core-side half of the conformance contract: plugin repositories
run :mod:`src.plugins.geometry_conformance` against themselves in their own
CI, and this module holds the built-in plugins to the same bar so a
regression in `plugins/` is caught here rather than on someone's panel.
"""

import importlib
import json
from pathlib import Path

import pytest

from src.plugins.geometry_conformance import run_conformance

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"


def _discover() -> list[str]:
    """Plugin ids of every bundled data plugin.

    Templates and transition plugins are skipped: a `_template` is a
    scaffold, and transitions animate frames rather than composing board
    content, so the geometry contract here does not describe them.
    """
    found = []
    for entry in sorted(PLUGINS_DIR.iterdir()):
        manifest_path = entry / "manifest.json"
        if not entry.is_dir() or entry.name.startswith("_") or not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("plugin_type") == "transition":
            continue
        found.append(entry.name)
    return found


BUILTIN_PLUGIN_IDS = _discover()


def _load(plugin_id: str):
    """Return ``(factory, manifest)`` for a bundled plugin, or skip."""
    manifest = json.loads((PLUGINS_DIR / plugin_id / "manifest.json").read_text())
    module = importlib.import_module(f"plugins.{plugin_id}")
    plugin_class = getattr(module, "Plugin", None)
    if plugin_class is None:
        pytest.skip(f"{plugin_id} exposes no Plugin class")

    def factory():
        plugin = plugin_class(manifest)
        plugin.enabled = True
        return plugin

    return factory, manifest


def test_discovery_found_the_bundled_plugins():
    # Guards against this whole module silently becoming a no-op if the
    # plugins directory moves or the discovery filter gets too aggressive.
    assert BUILTIN_PLUGIN_IDS, "no bundled plugins discovered"
    assert "date_time" in BUILTIN_PLUGIN_IDS


@pytest.mark.parametrize("plugin_id", BUILTIN_PLUGIN_IDS)
def test_builtin_plugin_is_board_conformant(plugin_id):
    """No bundled plugin may overflow, crash, or misdeclare on any board."""
    factory, manifest = _load(plugin_id)
    report = run_conformance(factory, manifest=manifest)
    assert report.ok, "\n" + report.summary()
