"""Output plugins in the output registry, beside the built-ins.

The plugin loader finds an output plugin like any other (``plugin_type:
"output"``), but never constructs it: it loads the **class** and the
manifest (plan D2) and calls :func:`register_output_plugin`. That puts an
:class:`~src.outputs.registry.OutputDefinition` in the output registry whose
``build`` makes one instance per board — ``cls(board_id, output_config)``,
the manifest's ``output`` block bound, :meth:`open` called — wrapped in the
:class:`~src.outputs.plugin_driver.OutputPluginDriver` adapter. A board
uses it by naming the plugin id as its ``output``; the derivation rule for
boards that name none is unchanged.

**Beta gate.** An output plugin installed from the registry or a git URL is
usable only while ``beta.output_plugins_enabled`` is on: with it off, a
board naming it builds no driver and stays down with the reason recorded —
never a Vestaboard in its place. Plugins bundled with FiestaBoard (the
``plugins/`` directory) are always usable.

The plugin registry keeps an :class:`OutputPluginEntry` for each output
plugin where it keeps data-plugin instances, so listing, install, reload and
uninstall treat it like any plugin; the entry is inert (no plugin code runs).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .hooks import OutputHooks
from .registry import OutputDefinition, output_registry

if TYPE_CHECKING:
    from src.plugins.manifest import PluginManifest

    from .driver import OutputDriver
    from .plugin_base import OutputPluginBase

logger = logging.getLogger(__name__)


class OutputPluginsDisabledError(ValueError):
    """A board names a third-party output plugin while the beta is off."""

    def __init__(self, output_id: str) -> None:
        super().__init__(f"Output plugin '{output_id}' needs the output plugins beta (Settings > Beta)")
        self.output_id = output_id


def output_plugins_enabled() -> bool:
    """Whether the ``output_plugins`` beta flag is on. Failures read as off."""
    try:
        from src.settings.service import get_settings_service

        return bool(get_settings_service().get_beta_settings().output_plugins_enabled)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not read the output_plugins beta flag: %s", exc)
        return False


class OutputPluginEntry:
    """What the plugin registry holds for an output plugin: its class and
    manifest, inert. Mirrors the passive surface the registry expects of a
    loaded plugin (``plugin_id``, ``manifest``, ``config``, ``enabled``,
    ``cleanup``...) so every listing and lifecycle path works unchanged, and
    no data path ever mistakes it for a data source."""

    supports_triggers = False

    def __init__(self, plugin_class: type[OutputPluginBase], manifest: PluginManifest) -> None:
        self.plugin_class = plugin_class
        self.parsed_manifest = manifest
        self.config: dict[str, Any] = {}
        self.enabled = False

    @property
    def plugin_id(self) -> str:
        return self.parsed_manifest.id

    @property
    def manifest(self) -> dict[str, Any]:
        return self.parsed_manifest.raw

    def get_settings_schema(self) -> dict[str, Any]:
        return self.parsed_manifest.settings_schema

    def _validate_refresh_seconds(self, config: dict[str, Any]) -> list[str]:
        return []

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        return []

    def clear_cache(self) -> None:
        """Nothing cached: an output plugin fetches no data."""

    def cleanup(self) -> None:
        """Nothing to release: the class is never instantiated here."""


def _builder(plugin_class: type[OutputPluginBase], manifest: PluginManifest, *, gated: bool):
    output_manifest = manifest.output

    def build(board: dict) -> OutputDriver | None:
        from .board_profile import board_character_set
        from .plugin_driver import OutputPluginDriver

        if gated and not output_plugins_enabled():
            raise OutputPluginsDisabledError(manifest.id)
        instance = plugin_class(board.get("id"), dict(board.get("output_config") or {}))
        instance.bind_manifest(output_manifest)
        instance.open()
        return OutputPluginDriver(instance, character_set=board_character_set(board))

    return build


def register_output_plugin(plugin_class: type[OutputPluginBase], manifest: PluginManifest, *, gated: bool) -> None:
    """Put a loaded output plugin in the output registry (replacing an
    earlier load of it).

    Raises:
        ValueError: the id belongs to a built-in output.
    """
    assert manifest.output is not None
    if not plugin_class.plugin_id:
        plugin_class.plugin_id = manifest.id
    output_registry().put_plugin(
        OutputDefinition(
            id=manifest.id,
            name=manifest.name,
            capabilities=manifest.output.capabilities,
            build=_builder(plugin_class, manifest, gated=gated),
            hooks=OutputHooks(discover=plugin_class.discover),
            plugin=True,
            settings_schema=manifest.output.settings_schema,
            output_manifest=manifest.output,
            beta_gated=gated,
        )
    )
    logger.info("Registered output plugin %s (%s)", manifest.id, "beta-gated" if gated else "bundled")


def unregister_output_plugin(plugin_id: str) -> None:
    output_registry().remove_plugin(plugin_id)


def release_driver(driver: Any) -> None:
    """End an output-plugin instance's lifetime when core drops its board's
    runtime. Every other driver has nothing to release."""
    from .plugin_driver import OutputPluginDriver

    if isinstance(driver, OutputPluginDriver):
        driver.close()
