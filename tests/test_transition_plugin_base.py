"""Tests for TransitionPluginBase and its manifest / loader integration."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.plugins.base import (
    DEFAULT_TRANSITION_INTERRUPTIBLE,
    DEFAULT_TRANSITION_MAX_FRAMES,
    DEFAULT_TRANSITION_MAX_RUNTIME_SECONDS,
    DEFAULT_TRANSITION_MIN_INTERVAL_MS,
    TransitionFrame,
    TransitionPluginBase,
)
from src.plugins.loader import PluginLoader
from src.plugins.manifest import PluginManifest, validate_manifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeTransition(TransitionPluginBase):
    """Minimal in-memory transition plugin for unit tests."""

    @property
    def plugin_id(self) -> str:
        return self._manifest.get("id", "fake_transition")

    def generate_frames(
        self,
        from_grid: list[list[int]],
        to_grid: list[list[int]],
        device: Any,
        config: dict[str, Any],
    ) -> Iterator[TransitionFrame]:
        yield from_grid, 10
        yield to_grid, 0


def _manifest(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "fake_transition",
        "name": "Fake Transition",
        "version": "0.0.1",
        "plugin_type": "transition",
        "transition_settings": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Base class behavior
# ---------------------------------------------------------------------------


def test_plugin_id_required():
    """TransitionPluginBase cannot be instantiated without plugin_id."""
    with pytest.raises(TypeError):
        TransitionPluginBase(_manifest())  # type: ignore[abstract]


def test_info_pulls_from_manifest():
    plugin = _FakeTransition(
        _manifest(
            id="my_t",
            name="My Transition",
            version="1.2.3",
            description="d",
            author="a",
        )
    )
    info = plugin.info
    assert info.id == "my_t"
    assert info.name == "My Transition"
    assert info.version == "1.2.3"
    assert info.description == "d"
    assert info.author == "a"


def test_transition_settings_defaults_when_missing():
    plugin = _FakeTransition(_manifest(transition_settings={}))
    settings = plugin.transition_settings
    assert settings == {
        "interruptible": DEFAULT_TRANSITION_INTERRUPTIBLE,
        "min_interval_ms": DEFAULT_TRANSITION_MIN_INTERVAL_MS,
        "max_frames": DEFAULT_TRANSITION_MAX_FRAMES,
        "max_runtime_seconds": DEFAULT_TRANSITION_MAX_RUNTIME_SECONDS,
    }


def test_transition_settings_uses_manifest_values():
    plugin = _FakeTransition(
        _manifest(
            transition_settings={
                "interruptible": False,
                "min_interval_ms": 250,
                "max_frames": 10,
                "max_runtime_seconds": 5,
            }
        )
    )
    settings = plugin.transition_settings
    assert settings["interruptible"] is False
    assert settings["min_interval_ms"] == 250
    assert settings["max_frames"] == 10
    assert settings["max_runtime_seconds"] == 5


def test_transition_settings_no_block_in_manifest():
    """Missing transition_settings block falls back to all defaults."""
    plugin = _FakeTransition({"id": "x", "name": "x", "version": "0.0.1"})
    settings = plugin.transition_settings
    assert settings["interruptible"] == DEFAULT_TRANSITION_INTERRUPTIBLE
    assert settings["max_frames"] == DEFAULT_TRANSITION_MAX_FRAMES


def test_enabled_setter_fires_cleanup_on_disable():
    cleanup_calls: list[int] = []

    class _T(_FakeTransition):
        def cleanup(self) -> None:
            cleanup_calls.append(1)

    plugin = _T(_manifest())
    plugin.enabled = True
    assert plugin.enabled is True
    plugin.enabled = False
    assert cleanup_calls == [1]


def test_config_setter_triggers_on_config_change():
    captured: list[tuple] = []

    class _T(_FakeTransition):
        def on_config_change(self, old, new):
            captured.append((old, new))

    plugin = _T(_manifest())
    plugin.config = {"a": 1}
    plugin.config = {"a": 1}  # identical — should not trigger
    plugin.config = {"a": 2}
    assert captured == [({}, {"a": 1}), ({"a": 1}, {"a": 2})]


def test_default_validate_config_is_empty():
    plugin = _FakeTransition(_manifest())
    assert plugin.validate_config({"anything": True}) == []


def test_generate_frames_yields_expected_sequence():
    plugin = _FakeTransition(_manifest())
    from_grid = [[0, 0], [0, 0]]
    to_grid = [[1, 1], [1, 1]]
    frames = list(plugin.generate_frames(from_grid, to_grid, None, {}))
    assert frames == [(from_grid, 10), (to_grid, 0)]


def test_supports_triggers_always_false():
    # Even a manifest that (wrongly) claims trigger support: transition
    # plugins never participate in trigger sweeps.
    plugin = _FakeTransition(_manifest(supports_triggers=True))
    assert plugin.supports_triggers is False


def test_validate_refresh_seconds_is_noop():
    plugin = _FakeTransition(_manifest())
    assert plugin._validate_refresh_seconds({"refresh_seconds": "bogus"}) == []


def test_registry_config_and_trigger_paths_accept_transition_plugin():
    """Regression: set_plugin_config raised AttributeError (API 500) and
    trigger_plugins crashed the trigger sweep for transition plugins."""
    from unittest.mock import MagicMock, patch

    from src.plugins.registry import PluginRegistry

    plugin = _FakeTransition(_manifest())
    loader = MagicMock()
    loader.load_all_plugins.return_value = {"fake_transition": plugin}
    loader.get_manifest.side_effect = lambda pid: (
        MagicMock(supports_triggers=False) if pid == "fake_transition" else None
    )
    with patch("src.plugins.registry.PluginLoader", return_value=loader):
        registry = PluginRegistry(plugins_dir=Path("/fake/plugins"))
    registry.initialize()
    registry.enable_plugin("fake_transition")

    errors = registry.set_plugin_config("fake_transition", {"step_delay_ms": 1000})
    assert errors == []
    assert plugin.config == {"step_delay_ms": 1000}
    assert registry.trigger_plugins == {}


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------


def test_manifest_accepts_transition_plugin_type():
    ok, errors = validate_manifest(
        {
            "id": "t",
            "name": "T",
            "version": "1.0.0",
            "plugin_type": "transition",
            "category": "transition",
        }
    )
    assert ok, errors


def test_manifest_rejects_bad_plugin_type():
    ok, errors = validate_manifest(
        {
            "id": "t",
            "name": "T",
            "version": "1.0.0",
            "plugin_type": "weird",
        }
    )
    assert not ok
    assert any("plugin_type" in e for e in errors)


def test_manifest_rejects_bad_transition_settings_types():
    ok, errors = validate_manifest(
        {
            "id": "t",
            "name": "T",
            "version": "1.0.0",
            "plugin_type": "transition",
            "transition_settings": {
                "min_interval_ms": "fast",
                "max_frames": 0,
                "interruptible": "yes",
            },
        }
    )
    assert not ok
    joined = "\n".join(errors)
    assert "min_interval_ms" in joined
    assert "max_frames" in joined
    assert "interruptible" in joined


def test_manifest_rejects_non_object_transition_settings():
    ok, errors = validate_manifest(
        {
            "id": "t",
            "name": "T",
            "version": "1.0.0",
            "transition_settings": "broken",
        }
    )
    assert not ok
    assert any("transition_settings" in e for e in errors)


def test_manifest_data_plugin_default():
    """Manifests with no plugin_type field still parse as data plugins."""
    parsed = PluginManifest.from_dict({"id": "d", "name": "D", "version": "1.0.0"})
    assert parsed.plugin_type == "data"
    assert parsed.transition_settings == {}


def test_manifest_transition_round_trip():
    """plugin_type and transition_settings survive to_dict."""
    parsed = PluginManifest.from_dict(
        {
            "id": "t",
            "name": "T",
            "version": "1.0.0",
            "plugin_type": "transition",
            "transition_settings": {"max_frames": 99, "interruptible": False},
        }
    )
    out = parsed.to_dict()
    assert out["plugin_type"] == "transition"
    assert out["transition_settings"]["max_frames"] == 99
    assert out["transition_settings"]["interruptible"] is False


def test_manifest_category_transition_allowed():
    """'transition' is a valid category."""
    parsed = PluginManifest.from_dict(
        {
            "id": "t",
            "name": "T",
            "version": "1.0.0",
            "plugin_type": "transition",
            "category": "transition",
        }
    )
    assert parsed.category == "transition"


# ---------------------------------------------------------------------------
# Loader: dual registry
# ---------------------------------------------------------------------------


def _write_transition_plugin(plugins_dir: Path, plugin_id: str) -> Path:
    plugin_dir = plugins_dir / plugin_id
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": plugin_id,
                "name": "T",
                "version": "1.0.0",
                "plugin_type": "transition",
                "category": "transition",
            }
        )
    )
    (plugin_dir / "__init__.py").write_text(
        f'''"""Test transition plugin {plugin_id}."""
from src.plugins.base import TransitionPluginBase

class Plugin(TransitionPluginBase):
    @property
    def plugin_id(self) -> str:
        return "{plugin_id}"

    def generate_frames(self, from_grid, to_grid, device, config):
        yield to_grid, 0
'''
    )
    return plugin_dir


def _write_data_plugin(plugins_dir: Path, plugin_id: str) -> Path:
    plugin_dir = plugins_dir / plugin_id
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": plugin_id,
                "name": "D",
                "version": "1.0.0",
                "variables": {"simple": ["x"]},
            }
        )
    )
    (plugin_dir / "__init__.py").write_text(
        f'''"""Test data plugin {plugin_id}."""
from src.plugins.base import PluginBase, PluginResult

class Plugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "{plugin_id}"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={{"x": 1}})
'''
    )
    return plugin_dir


def test_loader_loads_transition_plugin(tmp_path):
    _write_transition_plugin(tmp_path, "t_only")
    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])
    plugin = loader.load_plugin("t_only")
    assert plugin is not None
    assert isinstance(plugin, TransitionPluginBase)
    assert plugin.plugin_id == "t_only"


def test_loader_dual_registry_separates_types(tmp_path):
    _write_data_plugin(tmp_path, "d_one")
    _write_transition_plugin(tmp_path, "t_one")

    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])
    loader.load_all_plugins()

    assert set(loader.data_plugins.keys()) == {"d_one"}
    assert set(loader.transition_plugins.keys()) == {"t_one"}
    assert set(loader.loaded_plugins.keys()) == {"d_one", "t_one"}


def test_loader_get_transition_plugin_returns_none_for_data(tmp_path):
    _write_data_plugin(tmp_path, "d_two")
    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])
    loader.load_all_plugins()
    assert loader.get_transition_plugin("d_two") is None
    assert loader.get_transition_plugin("missing") is None


def test_loader_get_transition_plugin_returns_instance(tmp_path):
    _write_transition_plugin(tmp_path, "t_two")
    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])
    loader.load_all_plugins()
    plugin = loader.get_transition_plugin("t_two")
    assert plugin is not None
    assert plugin.plugin_id == "t_two"


def test_loader_errors_on_missing_transition_subclass(tmp_path):
    """A manifest declaring plugin_type=transition needs a TransitionPluginBase subclass."""
    plugin_dir = tmp_path / "broken"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "broken",
                "name": "B",
                "version": "1.0.0",
                "plugin_type": "transition",
            }
        )
    )
    (plugin_dir / "__init__.py").write_text(
        '''"""Wrong base class — uses PluginBase instead of TransitionPluginBase."""
from src.plugins.base import PluginBase, PluginResult

class Plugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "broken"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={})
'''
    )
    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])
    plugin = loader.load_plugin("broken")
    assert plugin is None
    errors = loader.load_errors["broken"]
    assert any("TransitionPluginBase" in e for e in errors)
