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

**No opt-in.** Every registered output plugin is usable — bundled, seeded,
from the marketplace or a git URL. Until settings v7 the ones the image did
not carry sat behind ``plugins.output_plugins_enabled``; that switch is gone.
What every output plugin still runs behind is unchanged: the write timeout
and breaker (:mod:`src.outputs.breaker`), the network allowlist
(:mod:`src.outputs.http`) and the ``output_api`` gate at install and load.

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


def _board_grid(board: dict) -> tuple[int, int] | None:
    """The board's saved content grid (an output-plugin board is a custom
    ``panel`` grid, plan D8); ``None`` when it saved none, and the plugin
    falls back to its model's own grid."""
    rows, cols = board.get("grid_rows"), board.get("grid_cols")
    if isinstance(rows, int) and isinstance(cols, int) and rows > 0 and cols > 0:
        return rows, cols
    return None


def _builder(plugin_class: type[OutputPluginBase], manifest: PluginManifest):
    output_manifest = manifest.output

    def build(board: dict) -> OutputDriver | None:
        from .board_profile import board_character_set, board_device_model
        from .plugin_driver import OutputPluginDriver

        instance = plugin_class(board.get("id"), dict(board.get("output_config") or {}))
        instance.bind_manifest(output_manifest)
        character_set = board_character_set(board)
        instance.bind_board(
            device_model=board_device_model(board),
            character_set=character_set,
            geometry=_board_grid(board),
        )
        instance.open()
        return OutputPluginDriver(instance, character_set=character_set)

    return build


def register_output_plugin(plugin_class: type[OutputPluginBase], manifest: PluginManifest) -> None:
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
            build=_builder(plugin_class, manifest),
            hooks=OutputHooks(discover=plugin_class.discover),
            plugin=True,
            settings_schema=manifest.output.settings_schema,
            output_manifest=manifest.output,
            description=manifest.description,
            icon=manifest.icon,
            actions=manifest.output.actions,
            offered_device_models=manifest.output.device_model_ids,
            plugin_class=plugin_class,
        )
    )
    logger.info("Registered output plugin %s", manifest.id)


def unregister_output_plugin(plugin_id: str) -> None:
    output_registry().remove_plugin(plugin_id)


def release_driver(driver: Any) -> None:
    """End an output-plugin instance's lifetime when core drops its board's
    runtime. Every other driver has nothing to release."""
    from .plugin_driver import OutputPluginDriver

    if isinstance(driver, OutputPluginDriver):
        driver.close()
