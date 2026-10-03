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

# A plugin with nothing configured may answer ``available=False`` and render
# nothing, which passes conformance without checking a single row. Each
# entry here is a config that makes the plugin actually draw, so its
# formatted output is held to every geometry — including the per-character
# panel grids. One case per distinct layout the plugin can produce.
CONFORMANCE_CONFIGS: dict[str, dict[str, dict]] = {
    "countdown": {
        "counting down": {"event_name": "Launch Day", "target_datetime": "2099-01-01T00:00:00", "timezone": "UTC"},
        "event passed": {"event_name": "Launch Day", "target_datetime": "2000-01-01T00:00:00", "timezone": "UTC"},
        "counting up": {
            "event_name": "Launch Day",
            "target_datetime": "2000-01-01T00:00:00",
            "timezone": "UTC",
            "count_up": True,
        },
    },
}

BUILTIN_CASES = [
    pytest.param(plugin_id, config, id=f"{plugin_id}[{label}]")
    for plugin_id in BUILTIN_PLUGIN_IDS
    for label, config in (CONFORMANCE_CONFIGS.get(plugin_id) or {"unconfigured": {}}).items()
]


def _load(plugin_id: str, config: dict | None = None):
    """Return ``(factory, manifest)`` for a bundled plugin, or skip."""
    manifest = json.loads((PLUGINS_DIR / plugin_id / "manifest.json").read_text())
    module = importlib.import_module(f"plugins.{plugin_id}")
    plugin_class = getattr(module, "Plugin", None)
    if plugin_class is None:
        pytest.skip(f"{plugin_id} exposes no Plugin class")

    def factory():
        plugin = plugin_class(manifest)
        plugin.enabled = True
        if config:
            plugin.config = dict(config)
        return plugin

    return factory, manifest


def test_discovery_found_the_bundled_plugins():
    # Guards against this whole module silently becoming a no-op if the
    # plugins directory moves or the discovery filter gets too aggressive.
    assert BUILTIN_PLUGIN_IDS, "no bundled plugins discovered"
    assert "date_time" in BUILTIN_PLUGIN_IDS


@pytest.mark.parametrize(("plugin_id", "config"), BUILTIN_CASES)
def test_builtin_plugin_is_board_conformant(plugin_id, config):
    """No bundled plugin may overflow, crash, or misdeclare on any board —
    flagship, Note, note arrays, or a per-character panel of any size."""
    factory, manifest = _load(plugin_id, config)
    report = run_conformance(factory, manifest=manifest)
    assert report.ok, "\n" + report.summary()


@pytest.mark.parametrize("plugin_id", sorted(CONFORMANCE_CONFIGS))
def test_configured_conformance_cases_really_draw(plugin_id):
    """A configured case must produce rows, or it checks nothing."""
    from src.plugins.geometry_conformance import panel

    for config in CONFORMANCE_CONFIGS[plugin_id].values():
        factory, _ = _load(plugin_id, config)
        result = factory().get_data(panel(12, 29))
        assert result.available and result.formatted_lines, f"{plugin_id} {config} drew nothing"
