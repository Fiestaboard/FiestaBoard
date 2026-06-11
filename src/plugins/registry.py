"""Plugin registry - singleton for managing all loaded plugins.

The PluginRegistry is the central point for:
- Loading and unloading plugins (built-in and external)
- Getting plugin instances by ID
- Managing plugin configurations
- Providing plugin data to other services
- Installing plugins from the registry or arbitrary git URLs
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from pathlib import Path
from typing import Any, Optional

from .base import PluginBase, PluginResult
from .loader import PluginLoader
from .manifest import PluginManifest, VariableMetadata
from .sources import (
    PluginSource,
    check_plugin_update_available,
    get_external_plugins_dir,
    install_git_plugin,
    install_registry_plugin,
    load_registry,
    remove_external_plugin,
)

logger = logging.getLogger(__name__)

# Singleton instance
_registry: Optional["PluginRegistry"] = None


# Separator between base plugin ID and instance label in compound keys.
# Example: "weather:sf" means plugin_id="weather", instance_label="sf".
INSTANCE_SEPARATOR = ":"

# Valid instance label pattern: alphanumeric, underscores, and hyphens, 1-40 chars.
_INSTANCE_LABEL_RE = re.compile(r"^[a-zA-Z0-9_-]{1,40}$")


class PluginRegistry:
    """Central registry for all loaded plugins.

    The registry manages:
    - Plugin loading via PluginLoader
    - Plugin enable/disable state
    - Plugin configuration
    - Aggregated variable schemas for templates
    - Periodic update availability checking for external plugins
    """

    def __init__(self, plugins_dir: Path | None = None):
        """Initialize the registry.

        Args:
            plugins_dir: Path to plugins directory
        """
        self._loader = PluginLoader(plugins_dir)
        self._plugins: dict[str, PluginBase] = {}
        self._manifests: dict[str, PluginManifest] = {}
        self._configs: dict[str, dict[str, Any]] = {}
        self._enabled: dict[str, bool] = {}

        # Cached results from the most recent check_for_updates() call.
        # Maps plugin_id -> bool (True = update available).
        self._update_status: dict[str, bool] = {}

        # Auto-discovery cache: maps plugin_id -> discovered variable names
        self._discovered_vars: dict[str, list[str]] = {}

        logger.info("PluginRegistry initialized")

    # ── instance key helpers ────────────────────────────────────────────

    @staticmethod
    def make_instance_key(plugin_id: str, instance_label: str) -> str:
        """Build a compound key from a base plugin ID and instance label.

        Example: ``make_instance_key("weather", "sf")`` → ``"weather:sf"``
        """
        return f"{plugin_id}{INSTANCE_SEPARATOR}{instance_label}"

    @staticmethod
    def parse_instance_key(key: str) -> tuple[str, str | None]:
        """Split a compound key into (base_plugin_id, instance_label).

        If *key* has no separator the label is ``None`` (default instance).

        Example: ``parse_instance_key("weather:sf")`` → ``("weather", "sf")``
        """
        if INSTANCE_SEPARATOR in key:
            base, label = key.split(INSTANCE_SEPARATOR, 1)
            return base, label
        return key, None

    @staticmethod
    def is_instance_key(key: str) -> bool:
        """Return ``True`` when *key* contains an instance separator."""
        return INSTANCE_SEPARATOR in key

    # ── instance CRUD ───────────────────────────────────────────────────

    def create_instance(self, plugin_id: str, instance_label: str) -> list[str]:
        """Create a new instance of an existing plugin.

        A new :class:`PluginBase` object of the same class is instantiated
        with the same manifest.  The instance is registered under the
        compound key ``plugin_id:instance_label`` and starts **disabled**
        with an empty configuration.

        Args:
            plugin_id: Base plugin ID (must already be loaded).
            instance_label: Short alphanumeric label for the instance.
                Normalized to lowercase so compound keys match the
                lowercase plugin-id convention used by the template
                engine's case-insensitive variable lookup.

        Returns:
            List of error messages (empty on success).
        """
        # Validate label, then normalize to lowercase.  Plugin IDs are required
        # to be lowercase (see manifest validation); instance labels follow the
        # same rule so that `{{plugin:label.field}}` template references — which
        # are resolved case-insensitively by the engine — match the stored key.
        if not _INSTANCE_LABEL_RE.match(instance_label):
            return [
                f"Invalid instance label '{instance_label}': must be 1-40 "
                "alphanumeric characters, underscores, or hyphens."
            ]
        instance_label = instance_label.lower()

        # Base plugin must exist
        if plugin_id not in self._plugins:
            return [f"Plugin not found: {plugin_id}"]

        compound_key = self.make_instance_key(plugin_id, instance_label)

        # Must not already exist
        if compound_key in self._plugins:
            return [f"Instance already exists: {compound_key}"]

        # Create a fresh plugin object
        new_plugin = self._loader.create_instance(plugin_id)
        if new_plugin is None:
            return [f"Failed to create instance of {plugin_id}"]

        # Register under compound key
        base_manifest = self._manifests[plugin_id]
        self._plugins[compound_key] = new_plugin
        self._manifests[compound_key] = base_manifest
        self._enabled[compound_key] = False
        self._configs[compound_key] = {}

        logger.info("Created plugin instance: %s", compound_key)
        return []

    def delete_instance(self, plugin_id: str, instance_label: str) -> list[str]:
        """Delete a plugin instance.

        Only instances (compound keys) can be deleted; base plugins cannot.

        Args:
            plugin_id: Base plugin ID.
            instance_label: Instance label.

        Returns:
            List of error messages (empty on success).
        """
        compound_key = self.make_instance_key(plugin_id, instance_label)

        if compound_key not in self._plugins:
            return [f"Instance not found: {compound_key}"]

        # Clean up the plugin
        self._plugins[compound_key].cleanup()
        del self._plugins[compound_key]
        self._manifests.pop(compound_key, None)
        self._enabled.pop(compound_key, None)
        self._configs.pop(compound_key, None)
        self._discovered_vars.pop(compound_key, None)

        logger.info("Deleted plugin instance: %s", compound_key)
        return []

    def list_instances(self, plugin_id: str) -> list[dict[str, Any]]:
        """List all instances of a plugin (excluding the base).

        Args:
            plugin_id: Base plugin ID.

        Returns:
            List of instance info dicts with ``label``, ``key``,
            ``enabled``, and ``has_config`` fields.
        """
        instances: list[dict[str, Any]] = []
        prefix = f"{plugin_id}{INSTANCE_SEPARATOR}"

        for key in sorted(self._plugins):
            if key.startswith(prefix):
                label = key[len(prefix) :]
                instances.append(
                    {
                        "label": label,
                        "key": key,
                        "enabled": self._enabled.get(key, False),
                        "has_config": bool(self._configs.get(key)),
                    }
                )

        return instances

    @property
    def plugins(self) -> dict[str, PluginBase]:
        """Return all loaded plugins."""
        return self._plugins.copy()

    @property
    def enabled_plugins(self) -> dict[str, PluginBase]:
        """Return only enabled plugins."""
        return {pid: plugin for pid, plugin in self._plugins.items() if self._enabled.get(pid, False)}

    def initialize(self) -> None:
        """Load all discovered plugins.

        This should be called once at startup. It will:
        1. Load all plugin modules from the plugins directory
        2. Read stored configurations from config manager
        3. Enable plugins that have enabled=true in their config
        """
        loaded = self._loader.load_all_plugins()

        # Try to get stored configs from config manager
        stored_configs: dict[str, dict[str, Any]] = {}
        try:
            from src.config_manager import get_config_manager

            config_manager = get_config_manager()
            # Get all plugin configs
            stored_configs = config_manager.get_all_plugin_configs()
        except Exception as e:
            logger.warning(f"Could not load stored plugin configs: {e}")

        for plugin_id, plugin in loaded.items():
            manifest = self._loader.get_manifest(plugin_id)
            if manifest:
                self._plugins[plugin_id] = plugin
                self._manifests[plugin_id] = manifest

                # Check if plugin has stored config with enabled=true
                plugin_config = stored_configs.get(plugin_id, {})
                is_enabled = plugin_config.get("enabled", False)

                self._enabled[plugin_id] = is_enabled

                # Apply stored config to the plugin
                if plugin_config:
                    self._configs[plugin_id] = plugin_config
                    plugin.config = plugin_config
                    plugin.enabled = is_enabled

                if is_enabled:
                    logger.info(f"Loaded and enabled plugin: {plugin_id}")
                else:
                    logger.debug(f"Loaded plugin (disabled): {plugin_id}")

        # Auto-install any plugins that were configured in V2 but are no longer
        # built-in (extracted to external repos in V3).
        self._auto_migrate_v2_plugins(stored_configs)

        # Restore plugin instances from stored configs.
        # Instance configs have compound keys like "weather:sf".
        self._restore_instances(stored_configs)

        enabled_count = sum(1 for e in self._enabled.values() if e)
        logger.info(f"Initialized {len(self._plugins)} plugins ({enabled_count} enabled)")

    def _restore_instances(self, stored_configs: dict[str, dict[str, Any]]) -> None:
        """Restore plugin instances from stored configuration.

        Scans *stored_configs* for compound keys (containing the instance
        separator ``:``) and creates the corresponding plugin instances
        with their stored configuration and enabled state.

        Compound keys with a mixed-case instance label (created before
        labels were normalized to lowercase) are migrated to the lowercase
        form on disk so subsequent template renders resolve correctly.
        """
        restored = 0
        for config_key, config in stored_configs.items():
            if not self.is_instance_key(config_key):
                continue

            base_id, label = self.parse_instance_key(config_key)
            if not label:
                continue

            # Base plugin must be loaded for us to create an instance
            if base_id not in self._plugins:
                logger.warning(
                    "Cannot restore instance '%s': base plugin '%s' not loaded",
                    config_key,
                    base_id,
                )
                continue

            normalized_key = self.make_instance_key(base_id, label.lower())

            # Skip if already registered (shouldn't happen, but be safe)
            if normalized_key in self._plugins:
                continue

            errors = self.create_instance(base_id, label)
            if errors:
                logger.warning("Failed to restore instance '%s': %s", config_key, errors)
                continue

            # Apply stored config via the proper pipeline so any future
            # side-effects (e.g. validation hooks) are consistently triggered.
            config_errors = self.set_plugin_config(normalized_key, config)
            if config_errors:
                logger.warning(
                    "Instance '%s' config failed validation on restore: %s — applying raw config to avoid data loss",
                    normalized_key,
                    config_errors,
                )
                # Fall back to direct assignment so we don't silently discard config
                self._configs[normalized_key] = config
                self._plugins[normalized_key].config = config

            # Enable via the proper pipeline so any future side-effects are
            # consistently triggered.
            is_enabled = config.get("enabled", False)
            if is_enabled:
                self.enable_plugin(normalized_key)

            # If the on-disk key was mixed-case, migrate it to lowercase so
            # subsequent restarts don't carry a stale duplicate.
            if config_key != normalized_key:
                try:
                    from src.config_manager import get_config_manager

                    config_manager = get_config_manager()
                    config_manager.set_plugin_config(normalized_key, config)
                    config_manager.delete_plugin_config(config_key)
                    logger.info(
                        "Migrated instance key '%s' -> '%s' (lowercase normalization)",
                        config_key,
                        normalized_key,
                    )
                except Exception:
                    logger.exception(
                        "Failed to migrate instance key '%s' to '%s'",
                        config_key,
                        normalized_key,
                    )

            restored += 1

        if restored:
            logger.info("Restored %d plugin instance(s) from config", restored)

    def _auto_migrate_v2_plugins(self, stored_configs: dict[str, dict[str, Any]]) -> None:
        """Install external plugins that were configured in V2 but are no longer built-in.

        When upgrading from V2 to V3, previously built-in plugins (weather, muni,
        stocks, etc.) are extracted into standalone external repositories.  Users
        who had those plugins configured will have entries in ``config.json`` whose
        plugin code no longer exists on disk.

        This method detects those "orphaned" configs, installs the matching plugin
        from the registry, and restores the stored configuration and enabled state
        — giving users a seamless, zero-data-loss upgrade experience.

        One-shot semantics with bounded retry (issues #937, #948):

        * The migration sets a persisted ``v2_completed`` flag so an
          "orphaned" config is treated as a deliberate uninstall on every
          subsequent boot — not silently re-installed. (Without this the
          next boot would resurrect any plugin the user just deleted.)
        * Per-plugin install failures (e.g. transient network blip while
          cloning from the registry) are recorded in
          ``plugin_migrations.v2_failed_installs``. On the next boot,
          if any of those ids still appear as orphaned stored configs,
          we retry just those — preserving the "stop reinstalling
          deliberately-deleted plugins" invariant while letting a flaky
          first boot recover. Once the list is empty the migration goes
          fully dormant.
        """
        try:
            from src.config_manager import get_config_manager

            cm = get_config_manager()
        except Exception as exc:
            logger.warning("V3 migration: could not access config manager — skipping: %s", exc)
            return

        first_run = not cm.is_v2_plugin_migration_done()
        if first_run:
            loaded_ids = set(self._plugins.keys())
            orphan_subset: set[str] | None = None
        else:
            # Subsequent boots: only retry plugins that failed on a previous
            # run AND still have a stored config (i.e. the user hasn't
            # uninstalled them in the meantime).
            failed = cm.get_v2_plugin_failed_installs()
            if not failed:
                return
            loaded_ids = set(self._plugins.keys())
            orphan_subset = {
                pid for pid in failed if pid in stored_configs and pid not in loaded_ids
            }
            if not orphan_subset:
                # Everything that failed has since been resolved (installed
                # manually, uninstalled deliberately, or otherwise reconciled).
                cm.clear_v2_plugin_failed_installs()
                return

        failures = self._run_v2_plugin_migration(
            stored_configs,
            loaded_ids=loaded_ids,
            orphan_subset=orphan_subset,
        )

        if first_run:
            cm.mark_v2_plugin_migration_done()
        cm.set_v2_plugin_failed_installs(failures)

    def _run_v2_plugin_migration(
        self,
        stored_configs: dict[str, dict[str, Any]],
        *,
        loaded_ids: set[str] | None = None,
        orphan_subset: set[str] | None = None,
    ) -> list[str]:
        """Body of the v2→v3 migration. See `_auto_migrate_v2_plugins`.

        Returns the list of plugin ids that we attempted to install but
        could not (registry-clone failure). The caller persists this so
        we can retry just those on the next boot.
        """
        if loaded_ids is None:
            loaded_ids = set(self._plugins.keys())
        # Instance keys (e.g. "countdown:fijiaustralia") are restored separately
        # by ``_restore_instances`` and must not be treated as orphaned base
        # plugins — their base ID is what gets installed from the registry.
        orphaned = [pid for pid in stored_configs if pid not in loaded_ids and not self.is_instance_key(pid)]
        if orphan_subset is not None:
            orphaned = [pid for pid in orphaned if pid in orphan_subset]
        if not orphaned:
            return []

        logger.info(
            "V3 migration: found %d plugin config(s) with no matching installed plugin: %s",
            len(orphaned),
            orphaned,
        )

        try:
            registry_entries = load_registry()
            registry_map = {e.plugin_id: e for e in registry_entries}
        except Exception as exc:
            logger.warning(
                "V3 migration: could not load plugin registry — skipping auto-install: %s",
                exc,
            )
            # Treat as "everything in scope is currently a transient failure"
            # so we get one more shot at it on the next boot.
            return list(orphaned)

        failed: list[str] = []
        migrated: list[str] = []
        for plugin_id in orphaned:
            if plugin_id not in registry_map:
                logger.warning(
                    "V3 migration: plugin '%s' has stored config but is not in the registry. "
                    "Install it manually via the Integrations page or remove its config entry.",
                    plugin_id,
                )
                continue

            logger.info("V3 migration: auto-installing '%s' from registry…", plugin_id)
            errors = self.install_from_registry(plugin_id)
            if errors:
                logger.error(
                    "V3 migration: failed to install '%s': %s. "
                    "Will retry on the next boot if the config is still present.",
                    plugin_id,
                    errors,
                )
                failed.append(plugin_id)
                continue

            # install_from_registry() registers the plugin with enabled=False and
            # no config applied.  Restore the full stored config and enabled state.
            plugin = self._plugins.get(plugin_id)
            if plugin:
                cfg = stored_configs[plugin_id]
                is_enabled = cfg.get("enabled", False)
                self._enabled[plugin_id] = is_enabled
                self._configs[plugin_id] = cfg
                plugin.config = cfg
                plugin.enabled = is_enabled
                migrated.append(plugin_id)
                logger.info("V3 migration: restored '%s' (enabled=%s)", plugin_id, is_enabled)

        if migrated:
            logger.info(
                "V3 migration complete: auto-installed %d plugin(s): %s",
                len(migrated),
                migrated,
            )

        return failed

    def get_plugin(self, plugin_id: str) -> PluginBase | None:
        """Get a plugin by ID.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Plugin instance or None if not loaded
        """
        return self._plugins.get(plugin_id)

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        """Get a plugin's manifest.

        Args:
            plugin_id: Plugin identifier

        Returns:
            PluginManifest or None if not loaded
        """
        return self._manifests.get(plugin_id)

    def is_enabled(self, plugin_id: str) -> bool:
        """Check if a plugin is enabled.

        Args:
            plugin_id: Plugin identifier

        Returns:
            True if enabled, False otherwise
        """
        return self._enabled.get(plugin_id, False)

    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            True if enabled successfully, False if plugin not found
        """
        if plugin_id not in self._plugins:
            logger.warning(f"Cannot enable unknown plugin: {plugin_id}")
            return False

        plugin = self._plugins[plugin_id]
        plugin.enabled = True
        self._enabled[plugin_id] = True

        # Apply stored config
        if plugin_id in self._configs:
            plugin.config = self._configs[plugin_id]

        logger.info(f"Enabled plugin: {plugin_id}")
        return True

    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            True if disabled successfully, False if plugin not found
        """
        if plugin_id not in self._plugins:
            return False

        plugin = self._plugins[plugin_id]
        plugin.enabled = False
        self._enabled[plugin_id] = False

        logger.info(f"Disabled plugin: {plugin_id}")
        return True

    def set_plugin_config(self, plugin_id: str, config: dict[str, Any]) -> list[str]:
        """Set configuration for a plugin.

        Args:
            plugin_id: Plugin identifier
            config: Configuration dictionary

        Returns:
            List of validation errors (empty if valid)
        """
        if plugin_id not in self._plugins:
            return [f"Plugin not found: {plugin_id}"]

        plugin = self._plugins[plugin_id]

        # Validate config (base refresh_seconds + plugin-specific)
        errors = plugin._validate_refresh_seconds(config)
        errors.extend(plugin.validate_config(config))
        if errors:
            return errors

        # Store and apply config
        self._configs[plugin_id] = config
        plugin.config = config

        logger.debug(f"Updated config for {plugin_id}")
        return []

    def get_plugin_config(self, plugin_id: str) -> dict[str, Any] | None:
        """Get configuration for a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Configuration dictionary or None if not found
        """
        return self._configs.get(plugin_id)

    def fetch_plugin_data(self, plugin_id: str) -> PluginResult:
        """Fetch data from a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            PluginResult with data or error
        """
        if plugin_id not in self._plugins:
            return PluginResult(available=False, error=f"Plugin not found: {plugin_id}")

        if not self._enabled.get(plugin_id, False):
            return PluginResult(available=False, error=f"Plugin not enabled: {plugin_id}")

        plugin = self._plugins[plugin_id]

        try:
            return plugin.get_data()
        except Exception as e:
            logger.exception(f"Error fetching data from {plugin_id}")
            return PluginResult(available=False, error=str(e))

    def _discover_variables(self, plugin_id: str) -> list[str]:
        """Introspect a plugin's live data to discover top-level variable names.

        Only scalar values (str, int, float, bool) are surfaced; lists and
        dicts are skipped (those should be declared as arrays in the manifest).
        Results are cached so the discovery fetch only happens once per
        plugin lifecycle.
        """
        if plugin_id in self._discovered_vars:
            return self._discovered_vars[plugin_id]

        try:
            result = self.fetch_plugin_data(plugin_id)
            if result.available and result.data:
                discovered = [key for key, val in result.data.items() if isinstance(val, str | int | float | bool)]
                self._discovered_vars[plugin_id] = discovered
                return discovered
        except Exception:
            logger.debug("Auto-discovery fetch failed for %s", plugin_id)

        self._discovered_vars[plugin_id] = []
        return []

    def clear_discovered_cache(self, plugin_id: str | None = None) -> None:
        """Clear auto-discovery cache for one or all plugins."""
        if plugin_id:
            self._discovered_vars.pop(plugin_id, None)
        else:
            self._discovered_vars.clear()

    def get_all_variables(self) -> dict[str, list[str]]:
        """Get all template variables from enabled plugins.

        When a plugin has ``auto_discover`` enabled, the manifest-declared
        variable list is merged with keys discovered from live data so that
        beginners who omit a ``variables`` section still see their data.

        Returns:
            Dictionary mapping plugin_id to list of variable names
        """
        variables: dict[str, list[str]] = {}

        for plugin_id, _plugin in self._plugins.items():
            if not self._enabled.get(plugin_id, False):
                continue

            manifest = self._manifests.get(plugin_id)
            if not manifest:
                continue

            var_names = manifest.variables.get_all_variable_names(plugin_id)

            if manifest.variables.auto_discover:
                discovered = self._discover_variables(plugin_id)
                existing = set(var_names)
                for name in discovered:
                    if name not in existing:
                        var_names.append(name)

            if var_names:
                variables[plugin_id] = var_names

        return variables

    def get_all_variables_with_metadata(
        self,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Get variables with rich metadata for every enabled plugin.

        Returns:
            ``{plugin_id: {var_name: {description, type, max_length, group, example, preview}}}``
        """
        all_vars = self.get_all_variables()
        context = self.build_template_context()
        result: dict[str, dict[str, dict[str, Any]]] = {}

        for plugin_id, var_names in all_vars.items():
            manifest = self._manifests.get(plugin_id)
            plugin_data = context.get(plugin_id, {})
            var_dict: dict[str, dict[str, Any]] = {}

            for name in var_names:
                # Skip array path patterns (e.g. "stops.*.field")
                if ".*." in name:
                    continue
                # Skip array aggregate names (they match an array key)
                if manifest and name in manifest.variables.arrays:
                    continue

                meta = manifest.variables.get_variable_metadata(name) if manifest else VariableMetadata()
                preview = ""
                raw_val = plugin_data.get(name)
                if raw_val is not None and isinstance(raw_val, str | int | float | bool):
                    preview = str(raw_val)

                var_dict[name] = {
                    "description": meta.description,
                    "type": meta.type,
                    "max_length": meta.max_length,
                    "group": meta.group,
                    "example": meta.example,
                    "preview": preview,
                }

            if var_dict:
                result[plugin_id] = var_dict

        return result

    def get_all_variable_groups(self) -> dict[str, dict[str, dict[str, str]]]:
        """Get variable groups for every enabled plugin.

        Returns:
            ``{plugin_id: {group_id: {"label": "..."}}}``
        """
        result: dict[str, dict[str, dict[str, str]]] = {}
        for plugin_id in self._plugins:
            if not self._enabled.get(plugin_id, False):
                continue
            manifest = self._manifests.get(plugin_id)
            if manifest and manifest.variables.groups:
                result[plugin_id] = {gid: {"label": g.label} for gid, g in manifest.variables.groups.items()}
        return result

    def get_all_max_lengths(self) -> dict[str, int]:
        """Get all max lengths from enabled plugins.

        Returns:
            Dictionary mapping "plugin_id.variable" to max length
        """
        max_lengths: dict[str, int] = {}

        for plugin_id in self._plugins:
            if not self._enabled.get(plugin_id, False):
                continue

            manifest = self._manifests.get(plugin_id)
            if not manifest:
                continue

            # Prefix variable names with plugin_id
            for var_name, max_len in manifest.max_lengths.items():
                full_name = f"{plugin_id}.{var_name}"
                max_lengths[full_name] = max_len

        return max_lengths

    def get_variables_schema(self, plugin_id: str) -> dict[str, Any] | None:
        """Get the variables schema for a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Variables schema dictionary or None
        """
        manifest = self._manifests.get(plugin_id)
        if manifest:
            return manifest.raw.get("variables", {})
        return None

    def list_plugins(self) -> list[dict[str, Any]]:
        """List all plugins with their status.

        Returns:
            List of plugin info dictionaries.  Each dict includes an
            ``instance_label`` (string or None) and ``base_plugin_id``
            for plugin instances.
        """
        plugins = []

        for plugin_id, _plugin in self._plugins.items():
            manifest = self._manifests.get(plugin_id)
            base_id, instance_label = self.parse_instance_key(plugin_id)
            source = self._loader.get_source(base_id)
            display_name = manifest.name if manifest else plugin_id
            if instance_label:
                display_name = f"{display_name} ({instance_label})"
            info = {
                "id": plugin_id,
                "name": display_name,
                "version": manifest.version if manifest else "unknown",
                "description": manifest.description if manifest else "",
                "author": manifest.author if manifest else "Unknown",
                "enabled": self._enabled.get(plugin_id, False),
                "icon": manifest.icon if manifest else "puzzle",
                "category": manifest.category if manifest else "utility",
                "fiestaboard_version": manifest.fiestaboard_version if manifest else "",
                "source": source.to_dict() if source else {"source_type": "builtin"},
                "update_available": self._update_status.get(plugin_id, False),
                "supports_triggers": manifest.supports_triggers if manifest else False,
                "instance_label": instance_label,
                "base_plugin_id": base_id,
                "settings_schema": manifest.settings_schema if manifest else {},
            }
            plugins.append(info)

        # Sort by name
        plugins.sort(key=lambda p: p["name"].lower())

        return plugins

    def reload_plugin(self, plugin_id: str) -> PluginBase | None:
        """Reload a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Reloaded plugin instance or None if failed
        """
        # Remember enabled state and config
        was_enabled = self._enabled.get(plugin_id, False)
        config = self._configs.get(plugin_id, {})

        # Unload
        if plugin_id in self._plugins:
            self._plugins[plugin_id].cleanup()
            del self._plugins[plugin_id]
        if plugin_id in self._manifests:
            del self._manifests[plugin_id]

        # Reload
        plugin = self._loader.reload_plugin(plugin_id)
        if plugin:
            manifest = self._loader.get_manifest(plugin_id)
            if manifest:
                self._plugins[plugin_id] = plugin
                self._manifests[plugin_id] = manifest

                # Restore state
                if was_enabled:
                    self.enable_plugin(plugin_id)
                if config:
                    errors = self.set_plugin_config(plugin_id, config)
                    if errors:
                        # New version's validate_config rejected the old config
                        # (e.g. a required field was added/renamed).  Apply the
                        # config directly so the user's data isn't silently lost.
                        # The user can re-save through the UI to normalise it.
                        logger.warning(
                            "Config validation failed after reload for '%s': %s"
                            " — applying raw config to avoid data loss",
                            plugin_id,
                            errors,
                        )
                        self._configs[plugin_id] = config
                        plugin.config = config

                return plugin

        return None

    def get_load_errors(self) -> dict[str, list[str]]:
        """Get plugin load errors.

        Returns:
            Dictionary mapping plugin directory names to error lists
        """
        return self._loader.load_errors

    def check_for_updates(self) -> dict[str, bool]:
        """Check all external plugins for available upstream updates.

        Runs ``git ls-remote`` against each external plugin's origin and
        compares with the local HEAD.  Results are cached in
        ``_update_status`` so the ``/plugins/updates`` endpoint can return
        instantly between checks.

        Returns:
            Mapping of plugin_id -> True if an update is available.
        """
        results: dict[str, bool] = {}
        for plugin_id, source in self._loader.plugin_sources.items():
            if source.source_type != "external" or not source.local_path:
                continue
            local_path = Path(source.local_path)
            update_available = check_plugin_update_available(local_path)
            results[plugin_id] = update_available
            if update_available:
                logger.info("Update available for external plugin: %s", plugin_id)

        self._update_status = results
        return results

    def get_update_status(self) -> dict[str, bool]:
        """Return cached update status from the last check_for_updates() call."""
        return self._update_status.copy()

    def get_plugin_source(self, plugin_id: str) -> PluginSource | None:
        """Get the source information for a loaded plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            :class:`PluginSource` or *None* if not loaded.
        """
        return self._loader.get_source(plugin_id)

    # ── external plugin management ───────────────────────────────────────

    def get_registry_entries(self) -> list[dict[str, Any]]:
        """Return all entries from the plugin registry file.

        Returns:
            List of registry entry dictionaries.
        """
        entries = load_registry()
        return [
            {
                "id": e.plugin_id,
                "name": e.name,
                "description": e.description,
                "repository": e.repository,
                "branch": e.branch,
                "author": e.author,
                "fiestaboard_version": e.fiestaboard_version,
                "icon": e.icon,
                "category": e.category,
                "installed": e.plugin_id in self._plugins,
            }
            for e in entries
        ]

    def install_from_registry(self, plugin_id: str) -> list[str]:
        """Install a plugin from the registry by its id.

        Args:
            plugin_id: The id of the registry entry to install.

        Returns:
            List of error messages (empty on success).
        """
        entries = load_registry()
        entry = next((e for e in entries if e.plugin_id == plugin_id), None)
        if entry is None:
            return [f"Plugin '{plugin_id}' not found in the registry"]

        ok, err = install_registry_plugin(entry)
        if not ok:
            return [err]

        # Reload external dirs and load the new plugin
        self._loader._external_dirs = [get_external_plugins_dir()]
        plugin = self._loader.load_plugin(plugin_id)
        if plugin is None:
            errors = self._loader.load_errors.get(plugin_id, [])
            return errors or [f"Failed to load plugin after install: {plugin_id}"]

        manifest = self._loader.get_manifest(plugin_id)
        if manifest:
            self._plugins[plugin_id] = plugin
            self._manifests[plugin_id] = manifest
            self._enabled[plugin_id] = False
            logger.info("Installed registry plugin: %s", plugin_id)

        return []

    def install_from_git(self, repo_url: str, plugin_id: str | None = None, branch: str = "") -> list[str]:
        """Install a plugin from an arbitrary public git repository.

        Custom git plugins do **not** need to follow the
        ``fiestaboard-plugin--`` naming convention.

        Args:
            repo_url: HTTPS URL of the git repository.
            plugin_id: Override the derived plugin id.
            branch: Optional branch or tag.

        Returns:
            List of error messages (empty on success).
        """
        ok, err = install_git_plugin(repo_url, plugin_id=plugin_id, branch=branch)
        if not ok:
            return [err]

        # Determine the id if not given
        if plugin_id is None:
            from .sources import plugin_id_from_repo_name, repo_name_from_url

            repo_name = repo_name_from_url(repo_url)
            plugin_id = plugin_id_from_repo_name(repo_name)

        # Reload external dirs and load the new plugin
        self._loader._external_dirs = [get_external_plugins_dir()]
        plugin = self._loader.load_plugin(plugin_id)
        if plugin is None:
            errors = self._loader.load_errors.get(plugin_id, [])
            return errors or [f"Failed to load plugin after install: {plugin_id}"]

        manifest = self._loader.get_manifest(plugin_id)
        if manifest:
            self._plugins[plugin_id] = plugin
            self._manifests[plugin_id] = manifest
            self._enabled[plugin_id] = False
            logger.info("Installed git plugin: %s from %s", plugin_id, repo_url)

        return []

    def uninstall_external_plugin(self, plugin_id: str) -> list[str]:
        """Remove an external (non-built-in) plugin.

        Built-in plugins cannot be uninstalled via this method.

        Args:
            plugin_id: Plugin identifier to remove.

        Returns:
            List of error messages (empty on success).
        """
        source = self._loader.get_source(plugin_id)
        if source is None:
            return [f"Plugin not found: {plugin_id}"]
        if source.source_type == "builtin":
            return ["Cannot uninstall a built-in plugin"]

        # Cascade-delete all named instances first
        instance_prefix = f"{plugin_id}{INSTANCE_SEPARATOR}"
        for compound_key in [k for k in list(self._plugins) if k.startswith(instance_prefix)]:
            self._plugins[compound_key].cleanup()
            del self._plugins[compound_key]
            self._manifests.pop(compound_key, None)
            self._enabled.pop(compound_key, None)
            self._configs.pop(compound_key, None)
            self._discovered_vars.pop(compound_key, None)
            logger.info("Removed instance on uninstall: %s", compound_key)

        # Disable and unload base plugin
        if plugin_id in self._plugins:
            self._plugins[plugin_id].cleanup()
            del self._plugins[plugin_id]
        self._manifests.pop(plugin_id, None)
        self._enabled.pop(plugin_id, None)
        self._configs.pop(plugin_id, None)

        self._loader.unload_plugin(plugin_id)

        # Remove the directory
        local_path = Path(source.local_path)
        remove_external_plugin(local_path)
        logger.info("Uninstalled external plugin: %s", plugin_id)
        return []

    @property
    def trigger_plugins(self) -> dict[str, PluginBase]:
        """Return enabled plugins that support event-based triggers."""
        return {
            pid: plugin
            for pid, plugin in self._plugins.items()
            if self._enabled.get(pid, False) and plugin.supports_triggers
        }

    def build_template_context(self) -> dict[str, Any]:
        """Build context dictionary for template rendering.

        Fetches data from all enabled plugins in parallel so that slow or
        unresponsive external data sources do not block each other.

        Returns:
            Dictionary mapping plugin_id to plugin data
        """
        context: dict[str, Any] = {}
        enabled = list(self.enabled_plugins)

        if not enabled:
            return context

        # Fetch every plugin concurrently; cap the pool to avoid spawning an
        # unbounded number of threads when many plugins are enabled.
        max_workers = min(len(enabled), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetch_plugin_data, plugin_id): plugin_id for plugin_id in enabled}
            done, not_done = futures_wait(futures, timeout=15)

            if not_done:
                slow_ids = [futures[f] for f in not_done]
                logger.warning(
                    f"{len(not_done)} plugin(s) did not complete within the "
                    f"context-build timeout and will be skipped: {slow_ids}"
                )

            for future in done:
                plugin_id = futures[future]
                try:
                    result = future.result()
                    if result.available and result.data:
                        context[plugin_id] = result.data
                except Exception:
                    logger.exception(f"Plugin {plugin_id} raised an error during context build")

        return context


def get_plugin_registry() -> PluginRegistry:
    """Get or create the global plugin registry singleton.

    Returns:
        The global PluginRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
        _registry.initialize()  # Load all plugins on first access
    return _registry


def reset_plugin_registry() -> None:
    """Reset the global plugin registry.

    Use this when you need to reinitialize the registry,
    e.g., in tests or after configuration changes.
    """
    global _registry
    _registry = None
    logger.info("Plugin registry reset")
